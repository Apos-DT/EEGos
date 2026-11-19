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
from typing import Any, Callable

from .services import WEB_JOBS_DIR

MAX_LOG_LINES = 1200


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
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="eeg-job")
        WEB_JOBS_DIR.mkdir(parents=True, exist_ok=True)

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
            self._jobs[job.id] = job
            self._save(job)
        self._executor.submit(self._run, job, runner)
        return job

    def _run(self, job: Job, runner: Callable[[Job], dict[str, Any] | None]) -> None:
        with self._lock:
            job.status = "running"
            job.started_at = _now()
            self._save(job)
        try:
            result = runner(job) or {}
            with self._lock:
                job.result = result
                job.status = "success"
                job.finished_at = _now()
                job.logs.append(f"[完成] {job.title} · {job.finished_at}")
                self._save(job)
        except Exception as exc:  # noqa: BLE001 - job boundary must report any error
            with self._lock:
                job.status = "failed"
                job.finished_at = _now()
                job.error = f"{type(exc).__name__}: {exc}"
                job.logs.append(f"[失败] {job.error}")
                job.logs.extend(traceback.format_exc().splitlines()[-20:])
                self._save(job)

    def log(self, job: Job, line: str) -> None:
        text = str(line).rstrip()
        if not text:
            return
        with self._lock:
            job.logs.append(text)
            if len(job.logs) > MAX_LOG_LINES:
                job.logs = job.logs[-MAX_LOG_LINES:]
            # Avoid writing every line to disk; keep the latest tail durable.
            if len(job.logs) % 8 == 0:
                self._save(job)

    def bind_process(self, job: Job, pid: int, output: Path | None = None) -> None:
        with self._lock:
            job.runtime = {"pid": pid, "output": str(output) if output else None}
            self._save(job)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, limit: int = 20) -> list[Job]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)
            return jobs[:limit]

    def _save(self, job: Job) -> None:
        target = WEB_JOBS_DIR / f"{job.id}.json"
        target.write_text(
            json.dumps(job.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


manager = JobManager()
