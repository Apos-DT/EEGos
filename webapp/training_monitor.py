"""Read-only monitoring of this workspace's training jobs and external workers.

No torch imports and no process control. Windows CIM + nvidia-smi are sampled
at most once per five seconds; inaccessible processes are not guessed alive.
"""
from __future__ import annotations
import csv
import io
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .config import ROOT, EXPERIMENTS_DIR
from . import run_store
from .jobs import manager

_lock = threading.Lock()
_cache: dict[str, Any] = {}
_cache_at = 0.0


def _json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _tail(path, limit=16000):
    try:
        with Path(path).open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size-limit))
            data = f.read().decode("utf-8", errors="replace")
        return data.splitlines()[-60:]
    except OSError:
        return []


def _run(args):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=8, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout


def processes():
    if os.name != "nt":
        raise RuntimeError("当前进程发现使用 Windows CIM，此平台暂不支持")
    script = "[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); @(Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | Select-Object ProcessId,ParentProcessId,CommandLine,@{Name='started_at';Expression={$_.CreationDate.ToString('o')}}) | ConvertTo-Json -Compress"
    rows = json.loads(_run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script]) or "[]")
    return rows if isinstance(rows, list) else [rows]


def gpu_snapshot():
    try:
        text = _run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu", "--format=csv,noheader,nounits"])
        def number(v):
            try: return float(v.strip())
            except ValueError: return None
        return {"available": True, "devices": [dict(zip(("name","utilization","memory_used_mb","memory_total_mb","temperature"), [r[0].strip(), *[number(v) for v in r[1:]]])) for r in csv.reader(io.StringIO(text)) if len(r)==5],
                "scope": "整张显卡的总占用，包含其他应用，不是单个任务的独占使用量"}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "devices": [], "message": f"GPU 信息暂不可用（{type(exc).__name__}）"}


def flags(command):
    pattern = r"--([\w-]+)(?:=|\s+)(\"[^\"]*\"|'[^']*'|.*?)(?=\s+--[\w-]+(?:=|\s)|$)"
    return {m.group(1): m.group(2).strip().strip('\"').strip("'") for m in re.finditer(pattern, command)}


def _output(value):
    if not value:
        return None
    try:
        p = Path(value)
        p = (ROOT / p).resolve() if not p.is_absolute() else p.resolve()
        return p if p.is_relative_to(EXPERIMENTS_DIR.resolve()) and p != EXPERIMENTS_DIR.resolve() else None
    except (OSError, ValueError):
        return None


def _elapsed(started, finished=None):
    try:
        start = datetime.fromisoformat(started)
        if start.tzinfo is None: start = start.astimezone()
        end = datetime.fromisoformat(finished) if finished else datetime.now(timezone.utc)
        if end.tzinfo is None: end = end.astimezone()
        return max(0, int((end-start).total_seconds()))
    except (TypeError, ValueError):
        return None


def _integer(value, default=0):
    try: return int(value)
    except (TypeError, ValueError): return default


def _progress(output, params, status):
    progress = _json(output / "progress.json")
    heartbeat = _json(output / "heartbeat.json")
    events = []
    for line in _tail(output / "timeline.jsonl"):
        try: events.append(json.loads(line))
        except ValueError: pass
    folds = progress.get("folds", [])
    total = _integer(progress.get("planned_folds"))
    if not total:
        sessions = 1 if params.get("target_session", params.get("target-session")) else 3
        total = sessions if params.get("setting") == "cross-session" else sessions * (1 if params.get("target_subject", params.get("target-subject")) else 15)
        limit = _integer(params.get("max_folds", params.get("max-folds")))
        if limit: total = min(total, limit)
    current_fold = None
    current_epoch = None
    latest = heartbeat or (events[-1] if events else {})
    # Only epochs from the current fold are used; never carry over a previous fold's epoch.
    for event in events:
        if event.get("event") == "fold_started":
            current_fold = event.get("fold")
            current_epoch = None
        elif event.get("event") == "epoch_evaluated":
            current_epoch = event.get("epoch")
    if heartbeat:
        current_fold = heartbeat.get("fold", current_fold)
        current_epoch = heartbeat.get("epoch", current_epoch)
    known = bool(progress or events or heartbeat)
    if "algorithm" not in params:
        completed = re.findall(r"\[LOSO\s+(\d+)/(\d+)\]", "\n".join(_tail(output / "training.log")))
        if completed:
            done, total = map(int, completed[-1])
            return {"completed_folds": done, "total_folds": total, "current_fold": min(total,done+1),
                    "epoch": None, "epochs": _integer(params.get("epochs")),
                    "fraction": 1 if status == "success" else done/total,
                    "updated_at": None, "note": "此模型按完成折更新进度，轮内进度未记录"}
        if not known:
            return {"fraction": 1 if status == "success" else None, "note": "尚无逐折进度记录"}
    epochs = _integer(params.get("epochs"))
    fraction = None
    if known and total:
        done = len(folds)
        fraction = min(1, (done + (current_epoch / epochs if epochs and current_epoch and current_fold and current_fold > done else 0)) / total)
    if status == "success": fraction = 1
    return {"completed_folds": len(folds) if known else None, "total_folds": total,
            "current_fold": current_fold, "epoch": current_epoch, "epochs": epochs or None,
            "fraction": fraction, "updated_at": latest.get("at"),
            "note": "进度在评估与折结束时更新" if known else "此任务未写出实时进度；只能确认进程状态"}


def _snapshot():
    global _cache_at, _cache
    with _lock:
        if _cache and time.monotonic()-_cache_at < 5:
            return _cache
        errors = []
        reliable = True
        try: rows = processes()
        except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as exc:
            rows = []
            reliable = False
            errors.append(f"本机进程状态暂不可用（{type(exc).__name__}）")
        groups = {}
        for proc in rows:
            command = proc.get("CommandLine") or ""
            if not ("run_seed4_dda.py" in command or re.search(r"-m\s+eeg_emostudio\s+train(?:\s|$)", command)):
                continue
            options = flags(command)
            if "run_seed4_dda.py" in command:
                options.setdefault("algorithm", "UDDA")
                options.setdefault("setting", "cross-subject")
                options.setdefault("epochs", "600")
            output = _output(options.get("output-dir") or options.get("out"))
            if output is None: continue
            group = groups.setdefault(str(output), {"output": output, "params": options, "processes": []})
            group["processes"].append(proc)
        observed = run_store.list_observations()
        new_observations = {
            key: {"params": group["params"], "started_at": group["processes"][0].get("started_at")}
            for key, group in groups.items() if key not in observed
        }
        run_store.observe_workers(new_observations)
        observed.update(new_observations)
        for key, observation in observed.items():
            output = _output(key)
            if output:
                groups.setdefault(str(output), {"output": output, "params": observation.get("params", {}), "processes": [], "observation": observation})
        jobs = manager.history(kinds=("train", "external_reproduction"), log_limit=60, recover=False)
        live_ids = manager.live_ids()
        for job in jobs:
            runtime = job.get("runtime", {})
            output = _output(runtime.get("output") or job.get("result", {}).get("output"))
            if output is None:
                for line in job.get("logs", []):
                    if line.startswith("$ "):
                        options = flags(line)
                        output = _output(options.get("output-dir") or options.get("out"))
                        if output: break
            if output:
                group = groups.setdefault(str(output), {"output": output, "params": job.get("params", {}), "processes": []})
                group.setdefault("job", job)
            elif job.get("status") in ("queued", "running") and job.get("id") in live_ids:
                groups[job["id"]] = {"output": None, "params": job.get("params", {}), "processes": [], "job": job}
        tasks = []
        for group in groups.values():
            output = group["output"]
            job = group.get("job", {})
            procs = group["processes"]
            meta = _json(output / "run_meta.json") if output else {}
            params = {**group["params"], **job.get("params", {}), **meta.get("parameters", {})}
            status = job.get("status") or meta.get("status") or "unknown"
            if not procs and status not in ("success", "failed") and meta.get("status") in ("success", "failed"):
                status = meta["status"]
            if not procs and not job and not meta.get("status") and group.get("observation"):
                status = "success" if output and (output / "metrics.json").exists() else ("interrupted" if reliable else "unknown")
            if procs: status = "running"
            elif reliable and status in ("queued", "running"):
                if job.get("id") not in live_ids:
                    status = "interrupted"
            elif not reliable and status in ("queued", "running"): status = "unknown"
            parents = {p.get("ParentProcessId") for p in procs}
            worker = next((p for p in procs if p.get("ProcessId") not in parents), procs[0] if procs else {})
            start = meta.get("started_at") or job.get("started_at") or worker.get("started_at") or group.get("observation", {}).get("started_at")
            run_id = output.name if output else None
            logs = _tail(output / "training.log") if output else []
            if not logs: logs = job.get("logs", [])[-60:]
            tasks.append({"id": run_id or job.get("id"), "run_id": run_id, "job_id": job.get("id"),
                "title": job.get("title") or ("DDA · " + params.get("algorithm", "UDDA") if "algorithm" in params else params.get("model", "训练任务")),
                "status": status, "pid": worker.get("ProcessId"), "process_count": len(procs),
                "started_at": start, "finished_at": meta.get("finished_at") or job.get("finished_at"),
                "elapsed_seconds": _elapsed(start, meta.get("finished_at") or job.get("finished_at")) if status == "running" or (meta.get("finished_at") or job.get("finished_at")) else None,
                "dataset": meta.get("dataset", params.get("data", params.get("dataset_id", "SEED-IV" if "algorithm" in params else "未记录"))),
                "setting": params.get("setting"), "params": params,
                "progress": _progress(output, params, status) if output else {}, "logs": logs,
                "error": job.get("error") or meta.get("error"),
                "report_url": f"/api/experiments/{run_id}/report" if output and (output / "report.html").exists() else None})
        active = [t for t in tasks if t["status"] in ("running", "queued", "unknown")]
        recent = sorted([t for t in tasks if t not in active], key=lambda t:t.get("finished_at") or t.get("started_at") or "", reverse=True)
        active.sort(key=lambda t:t.get("started_at") or "", reverse=True)
        _cache = {"sampled_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "process_scan_ok": reliable, "errors": errors, "gpu": gpu_snapshot(),
            "active_count": len(active), "tasks": active + recent}
        _cache_at = time.monotonic()
        return _cache


def snapshot(all_tasks=False):
    import copy
    from .record_store import decorate_rows
    data = copy.deepcopy(_snapshot())
    tasks = decorate_rows("jobs", data["tasks"], id_key="job_id", title_key="title")
    tasks = decorate_rows("training_tasks", tasks, title_key="title")
    active = [task for task in tasks if task["status"] in {"running", "queued", "unknown"}]
    recent = [task for task in tasks if task not in active]
    data["tasks"] = active + (recent if all_tasks else recent[:6])
    data["active_count"] = len(active)
    return data
