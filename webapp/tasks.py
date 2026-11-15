"""Runners that connect web jobs to the existing CLI/pipeline."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .jobs import Job, manager
from .services import (
    AUDIT_DIR,
    EXPERIMENTS_DIR,
    PROCESSED_DIR,
    RAW_DIR,
    ROOT,
    SELECTION_DIR,
    _read_json,
)

PYTHON = sys.executable


def _run_cli(job: Job, args: list[str]) -> int:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    manager.log(job, f"$ {' '.join(str(item) for item in args)}")
    process = subprocess.Popen(
        args,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    assert process.stdout is not None
    for line in process.stdout:
        manager.log(job, line)
    code = process.wait()
    if code != 0:
        raise RuntimeError(f"命令退出码 {code}")
    return code


def audit_task(job: Job, probe_media: bool = False) -> dict[str, Any]:
    args = [
        PYTHON, "-m", "eeg_emostudio", "audit",
        "--workspace", str(ROOT),
        "--out", str(AUDIT_DIR),
    ]
    if probe_media:
        args.append("--probe-media")
    _run_cli(job, args)
    summary = _read_json(AUDIT_DIR / "audit_summary.json", {}) or {}
    return {
        "kind": "audit",
        "output": str(AUDIT_DIR),
        "generated_at": summary.get("generated_at", ""),
        "surveys": summary.get("surveys", {}),
    }


def selection_task(
    job: Job,
    per_class: int = 10,
    min_grade: str = "D",
    modalities: str = "video,audio",
) -> dict[str, Any]:
    args = [
        PYTHON, "-m", "eeg_emostudio", "select",
        "--workspace", str(ROOT),
        "--out", str(SELECTION_DIR),
        "--per-class", str(per_class),
        "--min-grade", min_grade,
        "--modalities", modalities,
    ]
    _run_cli(job, args)
    summary = _read_json(SELECTION_DIR / "selection_summary.json", {}) or {}
    return {"kind": "selection", "output": str(SELECTION_DIR), "summary": summary}


def training_task(
    job: Job,
    dataset_path: Path,
    model: str = "dualview",
    setting: str = "loso",
    epochs: int = 40,
    batch_size: int = 32,
    lr: float = 1e-3,
    seed: int = 42,
    hidden: int = 32,
    dropout: float = 0.25,
    prototypes: int = 2,
    proto_weight: float = 0.1,
) -> dict[str, Any]:
    if not dataset_path.exists():
        raise FileNotFoundError(f"数据集不存在：{dataset_path}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"{stamp}_{model}_{setting}"
    output = EXPERIMENTS_DIR / run_id
    output.mkdir(parents=True, exist_ok=True)
    is_demo = "demo" in dataset_path.parts or dataset_path.name.startswith("demo")
    (output / "run_meta.json").write_text(
        json.dumps(
            {"dataset": str(dataset_path), "is_demo": is_demo, "source": "synthetic" if is_demo else "real"},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    args = [
        PYTHON, "-m", "eeg_emostudio", "train",
        "--data", str(dataset_path),
        "--out", str(output),
        "--model", model,
        "--setting", setting,
        "--epochs", str(epochs),
        "--batch-size", str(batch_size),
        "--lr", str(lr),
        "--seed", str(seed),
        "--hidden", str(hidden),
        "--dropout", str(dropout),
        "--prototypes", str(prototypes),
        "--proto-weight", str(proto_weight),
    ]
    _run_cli(job, args)
    metrics = _read_json(output / "metrics.json", {}) or {}
    report = output / "report.html"
    return {
        "kind": "train",
        "run_id": run_id,
        "output": str(output),
        "metrics": metrics,
        "report_url": f"/api/experiments/{run_id}/report" if report.exists() else "",
    }


def eeglab_task(
    job: Job,
    set_path: Path,
    output: Path,
    subject: str = "",
    bandpass: str = "0.1,70",
    notch: float = 50.0,
    target_fs: float = 200.0,
    reref: str = "car",
    epoch_start: float = -0.2,
    epoch_end: float = 4.0,
    reject: float = 150.0,
    event_map: str = "1=0,2=1,3=2,4=3",
    window: float = 1.0,
    ica: bool = False,
) -> dict[str, Any]:
    args = [
        PYTHON, "-m", "eeg_emostudio", "eeglab",
        "--input", str(set_path),
        "--out", str(output),
        "--subject", subject,
        "--bandpass", bandpass,
        "--notch", str(notch),
        "--target-fs", str(target_fs),
        "--reref", reref,
        "--epoch-start", str(epoch_start),
        "--epoch-end", str(epoch_end),
        "--reject", str(reject),
        "--event-map", event_map,
        "--window", str(window),
    ]
    if ica:
        args.append("--ica")
    _run_cli(job, args)
    report = _read_json(output / "eeg_report.json", {}) or {}
    training = report.get("training") or {}
    copied: dict[str, str] = {}
    if training.get("features") and Path(training["features"]).exists():
        source = Path(training["features"])
        target = PROCESSED_DIR / f"{output.name}_features.npz"
        target.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(source, target)
        manifest = source.with_suffix(".manifest.json")
        if manifest.exists():
            shutil.copy2(manifest, target.with_suffix(".manifest.json"))
        copied["features"] = str(target)
    if training.get("raw") and Path(training["raw"]).exists():
        source = Path(training["raw"])
        target = RAW_DIR / f"{output.name}_raw.npz"
        target.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(source, target)
        copied["raw"] = str(target)
    return {"kind": "eeglab", "output": str(output), "report": report, "copied": copied}


def features_task(
    job: Job,
    raw_path: Path,
    output_path: Path,
    fs: float | None,
    target_fs: float | None,
    window: float,
    step: float | None,
    aggregate: str,
    notch: float | None,
) -> dict[str, Any]:
    if not raw_path.exists():
        raise FileNotFoundError(f"原始数据不存在：{raw_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        PYTHON, "-m", "eeg_emostudio", "features",
        "--raw", str(raw_path),
        "--out", str(output_path),
        "--window", str(window),
        "--aggregate", aggregate,
    ]
    if fs:
        args.extend(["--fs", str(fs)])
    if target_fs:
        args.extend(["--target-fs", str(target_fs)])
    if step:
        args.extend(["--step", str(step)])
    if notch is None:
        args.append("--no-notch")
    else:
        args.extend(["--notch", str(notch)])
    _run_cli(job, args)
    build = _read_json(output_path.with_suffix(".build.json"), {}) or {}
    return {
        "kind": "features",
        "output": str(output_path),
        "build": build,
    }


def demo_task(job: Job, output: Path, epochs: int = 40, model: str = "dualview") -> dict[str, Any]:
    args = [
        PYTHON, "-m", "eeg_emostudio", "demo",
        "--out", str(output),
        "--epochs", str(epochs),
        "--model", model,
    ]
    _run_cli(job, args)
    summary = _read_json(output / "demo_summary.json", {}) or {}
    return {"kind": "demo", "output": str(output), "summary": summary}
