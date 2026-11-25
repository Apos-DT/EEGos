"""Small in-process job manager for long-running data and training tasks."""

from __future__ import annotations

import json
import secrets
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from subprocess import Popen, SubprocessError
from typing import Any, Callable

from . import config, run_store

MAX_LOG_LINES = 1200
LOG_BATCH_SIZE = 8


class JobCancelled(Exception):
    """Raised by a worker after it has handled a cooperative cancellation request."""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Job:
    id: str
    kind: str
    title: str
    params: dict[str, Any] = field(default_factory=dict)
    status: str = "queued"
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    logs: list[str] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    runtime: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, include_logs: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        if not include_logs:
            payload.pop("logs", None)
        return payload


class JobManager:
    def __init__(self, workers: int = 2) -> None:
        self._jobs: dict[str, Job] = {}
        self._processes: dict[str, tuple[Popen, Callable[[], None] | None]] = {}
        self._pending_logs: dict[str, list[tuple[str, str]]] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="eeg-job")

    def submit(
        self,
        kind: str,
        title: str,
        runner: Callable[[Job], dict[str, Any] | None],
        params: dict[str, Any] | None = None,
    ) -> Job:
        job = Job(
            id=f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(3)}",
            kind=kind,
            title=title,
            params=params or {},
        )
        with self._lock:
            self._save(job)
            self._jobs[job.id] = job
        self._executor.submit(self._run, job, runner)
        return job

    def _run(self, job: Job, runner: Callable[[Job], dict[str, Any] | None]) -> None:
        with self._lock:
            if job.status == "cancelled":
                return
            job.status = "running"
            job.started_at = _now()
            self._save(job)
        try:
            result = runner(job) or {}
            with self._lock:
                job.result = result
                job.status = "success"
                job.finished_at = _now()
                self._queue_log(job, f"[完成] {job.title} · {job.finished_at}")
                self._save(job)
        except Exception as exc:  # noqa: BLE001 - job boundary must report any error
            with self._lock:
                control = self._processes.get(job.id)
                if isinstance(exc, JobCancelled) or (job.status == "cancelling" and control and control[1] is None):
                    self._record_cancelled(job)
                    return
                job.status = "failed"
                job.finished_at = _now()
                job.error = f"{type(exc).__name__}: {exc}"
                self._queue_log(job, f"[失败] {job.error}")
                for line in traceback.format_exc().splitlines()[-20:]:
                    self._queue_log(job, line)
                self._save(job)
        finally:
            with self._lock:
                self._jobs.pop(job.id, None)
                self._processes.pop(job.id, None)
                self._pending_logs.pop(job.id, None)

    def log(self, job: Job, line: str) -> None:
        text = str(line).rstrip()
        if not text:
            return
        with self._lock:
            logs = self._queue_log(job, text)
            if len(logs) >= LOG_BATCH_SIZE:
                run_store.append_job_logs(job.id, logs)
                logs.clear()

    def _queue_log(self, job: Job, text: str) -> list[tuple[str, str]]:
        job.logs.append(text)
        if len(job.logs) > MAX_LOG_LINES:
            del job.logs[:-MAX_LOG_LINES]
        logs = self._pending_logs.setdefault(job.id, [])
        logs.append((_now(), text))
        return logs

    def bind_process(
        self, job: Job, pid: int, output: Path | None = None, *, cancellable_process: Popen | None = None,
        request_cancel: Callable[[], None] | None = None,
    ) -> None:
        with self._lock:
            job.runtime = {"pid": pid, "output": str(output) if output else None}
            if cancellable_process is not None and self._jobs.get(job.id) is job and cancellable_process.pid == pid:
                self._processes[job.id] = (cancellable_process, request_cancel)
            self._save(job)

    def active(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {**job.to_dict(include_logs=False), "can_cancel": self._can_cancel(job)}
                for job in self._jobs.values() if job.status in {"queued", "running", "cancelling"}
            ]

    def _can_cancel(self, job: Job) -> bool:
        control = self._processes.get(job.id)
        return job.status == "queued" or (job.status == "running" and control is not None and control[0].poll() is None)

    def cancel(self, job_id: str) -> str | None:
        """Cancel queued work or invoke the control registered for an owned child."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or not self._can_cancel(job):
                return None
            if job.status == "queued":
                self._record_cancelled(job)
                self._jobs.pop(job.id, None)
                self._pending_logs.pop(job.id, None)
            else:
                try:
                    process, request_cancel = self._processes[job.id]
                    (request_cancel or process.terminate)()
                except OSError:
                    return None
                job.status = "cancelling"
                self._queue_log(job, "[终止请求] 正在等待受管进程退出")
                self._save(job)
            return job.status

    def _record_cancelled(self, job: Job) -> None:
        job.status = "cancelled"
        job.finished_at = _now()
        self._queue_log(job, f"[已终止] {job.title} · {job.finished_at}")
        self._save(job)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            live = self._jobs.get(job_id)
            if live:
                return Job(**live.to_dict())
        job = run_store.read_job(job_id)
        if job:
            self.recover([job])
            return Job(**job)
        return None

    def list(self, limit: int = 20, *, include_logs: bool = True) -> list[Job]:
        return [Job(**row) for row in self.history(limit, log_limit=MAX_LOG_LINES if include_logs else 0)]

    def history(
        self, limit: int | None = None, *, kinds: tuple[str, ...] = (),
        log_limit: int = 0, recover: bool = True,
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = run_store.list_jobs(limit, kinds=kinds, log_limit=log_limit)
            for idx, row in enumerate(rows):
                live = self._jobs.get(row["id"])
                if live:
                    snapshot = live.to_dict(include_logs=False)
                    if log_limit:
                        snapshot["logs"] = live.logs[-log_limit:]
                    rows[idx] = snapshot
        if recover:
            self.recover(rows)
        return rows

    def live_ids(self) -> set[str]:
        with self._lock:
            return set(self._jobs)

    def recover(self, jobs: list[dict[str, Any]]) -> None:
        """Resolve stale status from old runs without treating an unavailable scan as failure."""
        active = self.live_ids()
        stale = [job for job in jobs if job["id"] not in active and job["status"] in {"running", "queued", "cancelling"}]
        if not stale:
            return
        process_ids = None
        if any(job["runtime"].get("pid") for job in stale):
            from .training_monitor import processes

            try:
                process_ids = {row.get("ProcessId") for row in processes()}
            except (OSError, ValueError, RuntimeError, SubprocessError):
                pass
        for job in stale:
            status, finished_at = _finished_run(job)
            pid = job["runtime"].get("pid")
            if not status:
                if pid and process_ids is None:
                    job["status"] = "unknown"
                    continue
                if pid and pid in process_ids:
                    continue
                status = "cancelled" if job["status"] == "cancelling" else "interrupted"
            run_store.set_recovered_status(job["id"], status, finished_at)
            job["status"] = status
            if finished_at:
                job["finished_at"] = finished_at

    def _save(self, job: Job) -> None:
        pending = self._pending_logs.get(job.id, [])
        run_store.save_job(job.to_dict(include_logs=False), pending)
        pending.clear()


def _finished_run(job: dict[str, Any]) -> tuple[str | None, str | None]:
    output = job["runtime"].get("output")
    if not output:
        return None, None
    if job["kind"] == "eeg_raw":
        allowed, filename = config.OUTPUT_DIR, "eeg_report.json"
    elif job["kind"] in {"train", "external_reproduction"}:
        allowed, filename = config.EXPERIMENTS_DIR, "run_meta.json"
    else:
        return None, None
    try:
        root = allowed.resolve()
        path = (config.ROOT / output).resolve()
        if path == root or not path.is_relative_to(root):
            return None, None
        meta = json.loads((path / filename).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None, None
    if isinstance(meta, dict) and meta.get("status") in {"success", "failed", "cancelled"}:
        return meta["status"], meta.get("finished_at")
    return None, None


manager = JobManager()
