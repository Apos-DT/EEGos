"""Process boundary for the external DDA paper reproduction sidecar."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import DDA_PYTHON, DDA_REPO_DIR, EXPERIMENTS_DIR, SEED_IV_DIR
from ..jobs import Job, manager


def refresh_dda_report(output: Path) -> None:
    """Upgrade legacy DDA reports through the external renderer only."""
    metadata = output / "run_meta.json"
    renderer = DDA_REPO_DIR / "dda_report.py"
    if not metadata.is_file() or not renderer.is_file():
        return
    meta = json.loads(metadata.read_text(encoding="utf-8"))
    if meta.get("external_engine") != "JC-Journal-Club/DDA":
        return
    report = output / "report.html"
    if report.exists() and 'data-dda-report-version="2"' in report.read_text(encoding="utf-8"):
        return
    subprocess.run(
        [DDA_PYTHON or sys.executable, str(renderer), str(output)],
        check=True, capture_output=True, timeout=30,
    )


def run_dda(
    job: Job,
    *,
    setting: str,
    algorithm: str,
    epochs: int,
    seed: int,
    target_labeled_trials: int,
    target_subject: str | None,
    target_session: str | None,
    max_folds: int,
    batch_size: int = 30,
    lr: float = 0.001,
    beta: float = 0.3,
    pseudo_threshold: float = 0.75,
    eval_interval: int = 10,
) -> dict[str, Any]:
    runner = DDA_REPO_DIR / "run_seed4_dda.py"
    upstream_model = DDA_REPO_DIR / "UDDA" / "seed4" / "network.py"
    if not runner.is_file() or not upstream_model.is_file():
        raise FileNotFoundError(
            "未找到 DDA 外部适配器。请将作者仓库及 run_seed4_dda.py 放在 "
            f"{DDA_REPO_DIR}，或设置 EEG_DDA_REPO 指向该目录。"
        )
    if not (SEED_IV_DIR / "eeg_feature_smooth").is_dir():
        raise FileNotFoundError(f"未找到本地 SEED-IV 官方特征目录：{SEED_IV_DIR / 'eeg_feature_smooth'}")

    run_id = f"{datetime.now():%Y%m%d-%H%M%S}_dda_{algorithm.lower()}_{setting.replace('-', '')}"
    output = EXPERIMENTS_DIR / run_id
    output.mkdir(parents=True, exist_ok=False)
    (output / "run_meta.json").write_text(
        json.dumps(
            {
                "dataset": "SEED-IV",
                "source": "real",
                "is_demo": False,
                "external_engine": "JC-Journal-Club/DDA",
                "external_engine_path": str(DDA_REPO_DIR),
                "setting": setting,
                "algorithm": algorithm,
                "submitted_at": job.created_at,
                "job_id": job.id,
                "run_id": run_id,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    python = DDA_PYTHON or sys.executable
    command = [
        python,
        str(runner),
        "--data-root", str(SEED_IV_DIR),
        "--output-dir", str(output),
        "--setting", setting,
        "--algorithm", algorithm,
        "--epochs", str(epochs),
        "--seed", str(seed),
        "--target-labeled-trials", str(target_labeled_trials),
        "--max-folds", str(max_folds),
        "--batch-size", str(batch_size),
        "--lr", str(lr),
        "--beta", str(beta),
        "--pseudo-threshold", str(pseudo_threshold),
        "--eval-interval", str(eval_interval),
    ]
    if target_subject:
        command.extend(["--target-subject", target_subject])
    if target_session:
        command.extend(["--target-session", target_session])

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    manager.log(job, f"$ {' '.join(command)}")
    manager.log(job, "外部 DDA sidecar 独立运行；训练实现未导入 EEG-EmoStudio 核心算法包。")
    process = subprocess.Popen(
        command,
        cwd=str(DDA_REPO_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    assert process.stdout is not None
    manager.bind_process(job, process.pid, output)
    with (output / "training.log").open("w", encoding="utf-8", buffering=1) as log:
        for line in process.stdout:
            log.write(line)
            manager.log(job, line)
    exit_code = process.wait()
    if exit_code:
        raise RuntimeError(
            f"DDA 外部进程退出码 {exit_code}。检查任务日志和训练解释器；"
            "Windows 上如遇 PyTorch DLL 错误，请为 EEG_DDA_PYTHON 配置可正常导入 torch 的环境。"
        )
    metrics_path = output / "metrics.json"
    if not metrics_path.is_file():
        raise RuntimeError("DDA 进程结束但没有生成 metrics.json")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    return {
        "kind": "external_reproduction",
        "run_id": run_id,
        "output": str(output),
        "metrics": metrics,
        "experiment_url": "/experiments",
    }
