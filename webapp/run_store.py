"""SQLite persistence for background jobs and observations of external workers."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from . import config
from .db import transaction


def _json_mapping(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


_INSERT_JOB = """
    INSERT INTO jobs (
        id, kind, title, status, created_at, started_at, finished_at, error,
        pid, output_path, params_json, result_json, runtime_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _job_values(job: dict[str, Any]) -> tuple:
    runtime = job.get("runtime") or {}
    result = job.get("result") or {}
    params = job.get("params") or {}
    return (
        job["id"], job.get("kind") or "", job.get("title") or job["id"],
        job.get("status") or "unknown", job.get("created_at") or "",
        job.get("started_at"), job.get("finished_at"), job.get("error"),
        runtime.get("pid"), runtime.get("output") or result.get("output"),
        _dump(params), _dump(result), _dump(runtime),
    )


def _insert_logs(conn: sqlite3.Connection, job_id: str, logs: Iterable[tuple[str | None, str]]) -> None:
    conn.executemany(
        "INSERT INTO job_logs(job_id, recorded_at, message) VALUES (?, ?, ?)",
        ((job_id, at, message) for at, message in logs),
    )


def save_job(job: dict[str, Any], logs: Iterable[tuple[str | None, str]] = ()) -> None:
    with transaction(write=True) as conn:
        conn.execute(_INSERT_JOB + """
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                started_at = excluded.started_at,
                finished_at = excluded.finished_at,
                error = excluded.error,
                pid = excluded.pid,
                output_path = excluded.output_path,
                result_json = excluded.result_json,
                runtime_json = excluded.runtime_json
        """, _job_values(job))
        _insert_logs(conn, job["id"], logs)


def append_job_logs(job_id: str, logs: Iterable[tuple[str | None, str]]) -> None:
    with transaction(write=True) as conn:
        _insert_logs(conn, job_id, logs)


def _decode_job(row: sqlite3.Row) -> dict[str, Any]:
    result = {column: row[column] for column in (
        "id", "kind", "title", "status", "created_at", "started_at", "finished_at", "error",
    )}
    for column in ("params", "result", "runtime"):
        result[column] = json.loads(row[f"{column}_json"])
    return result


def _log_tail(conn: sqlite3.Connection, job_id: str, limit: int) -> list[str]:
    rows = conn.execute(
        "SELECT message FROM job_logs WHERE job_id = ? ORDER BY id DESC LIMIT ?",
        (job_id, limit),
    ).fetchall()
    return [row["message"] for row in reversed(rows)]


def read_job(job_id: str, log_limit: int = 1200) -> dict[str, Any] | None:
    with transaction() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        job = _decode_job(row)
        job["logs"] = _log_tail(conn, job_id, log_limit)
        return job


def list_jobs(limit: int | None = None, *, kinds: tuple[str, ...] = (), log_limit: int = 0) -> list[dict[str, Any]]:
    with transaction() as conn:
        filters = ""
        values: tuple = ()
        if kinds:
            filters = "WHERE kind IN (" + ", ".join("?" for _ in kinds) + ")"
            values = kinds
        rows = conn.execute(
            f"SELECT * FROM jobs {filters} ORDER BY created_at DESC, id DESC LIMIT ?",
            (*values, limit if limit is not None else -1),
        ).fetchall()
        jobs = [_decode_job(row) for row in rows]
        if log_limit:
            for job in jobs:
                job["logs"] = _log_tail(conn, job["id"], log_limit)
        return jobs


def set_recovered_status(job_id: str, status: str, finished_at: str | None) -> None:
    with transaction(write=True) as conn:
        conn.execute("""
            UPDATE jobs SET status = ?, finished_at = coalesce(?, finished_at)
            WHERE id = ? AND status IN ('queued', 'running')
        """, (status, finished_at, job_id))


def observe_workers(observations: dict[str, Any]) -> None:
    if not observations:
        return
    with transaction(write=True) as conn:
        conn.executemany("""
            INSERT INTO training_observations(output_path, started_at, parameters_json)
            VALUES (?, ?, ?) ON CONFLICT(output_path) DO NOTHING
        """, (
            (path, observation.get("started_at"), _dump(observation.get("params") or {}))
            for path, observation in observations.items()
        ))


def list_observations() -> dict[str, dict[str, Any]]:
    with transaction() as conn:
        rows = conn.execute("SELECT * FROM training_observations")
        return {row["output_path"]: {
            "started_at": row["started_at"], "params": json.loads(row["parameters_json"]),
        } for row in rows}


def migrate_legacy(jobs_dir: Path | None = None, observed_path: Path | None = None) -> None:
    """Import the previous JSON stores once without altering the originals."""
    jobs_dir = jobs_dir if jobs_dir is not None else config.WEB_JOBS_DIR
    observed_path = observed_path if observed_path is not None else config.ARTIFACTS / "training_monitor_observed.json"
    with transaction(write=True) as conn:
        imported = {row["source_path"] for row in conn.execute("SELECT source_path FROM run_legacy_imports")}
        jobs_key = str(jobs_dir.resolve())
        if jobs_key not in imported:
            for path in sorted(jobs_dir.glob("*.json")):
                job = _json_mapping(path)
                if not isinstance(job.get("id"), str) or not job["id"]:
                    continue
                inserted = conn.execute(_INSERT_JOB + " ON CONFLICT(id) DO NOTHING", _job_values(job)).rowcount
                lines = job.get("logs") or []
                if inserted and isinstance(lines, list):
                    _insert_logs(conn, job["id"], ((None, line) for line in lines if isinstance(line, str)))
            conn.execute("INSERT INTO run_legacy_imports(source_path) VALUES (?)", (jobs_key,))
        observed_key = str(observed_path.resolve())
        if observed_key not in imported:
            rows = _json_mapping(observed_path)
            conn.executemany("""
                INSERT INTO training_observations(output_path, started_at, parameters_json)
                VALUES (?, ?, ?) ON CONFLICT(output_path) DO NOTHING
            """, ((path, row.get("started_at"), _dump(row.get("params") or {}))
                  for path, row in rows.items() if isinstance(row, dict)))
            conn.execute("INSERT INTO run_legacy_imports(source_path) VALUES (?)", (observed_key,))
