"""SQLite repositories and the one-time import of local survey data."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from sqlite3 import Connection
from typing import Any, Iterable

from .config import IMPORTS_DIR, RESPONSES_DIR, SESSIONS_DIR, STAGING_DIR, SURVEYS_DIR
from .db import transaction


_ACTIVE_RESPONSE = """
    NOT EXISTS (
        SELECT 1 FROM record_metadata m
        WHERE m.resource='responses' AND m.record_id=r.response_id
          AND m.deleted_at IS NOT NULL AND m.deleted_at<>''
    )
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _payloads(conn: Connection, sql: str, args: tuple = ()) -> list[dict]:
    return [json.loads(row["payload_json"]) for row in conn.execute(sql, args)]


def _payload(conn: Connection, sql: str, args: tuple) -> dict | None:
    row = conn.execute(sql, args).fetchone()
    return json.loads(row["payload_json"]) if row else None


def save_survey(conn: Connection, survey: dict, *, legacy: bool = False) -> None:
    conflict = "DO NOTHING" if legacy else """
        DO UPDATE SET token=excluded.token, title=excluded.title, status=excluded.status,
        kind=excluded.kind, schema_version=excluded.schema_version, schema_hash=excluded.schema_hash,
        updated_at=excluded.updated_at, payload_json=excluded.payload_json
    """
    conn.execute(f"""
        INSERT INTO surveys(id, token, title, status, kind, schema_version, schema_hash,
                            created_at, updated_at, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) {conflict}
    """, (
        survey["id"], survey["token"], survey["title"], survey.get("status", "open"),
        survey.get("kind", ""), int(survey.get("schema_version") or 1), survey.get("schema_hash") or "",
        survey["created_at"], survey.get("updated_at") or survey["created_at"], _json(survey),
    ))


def get_survey(conn: Connection, survey_id: str) -> dict | None:
    return _payload(conn, "SELECT payload_json FROM surveys WHERE id=?", (survey_id,))


def get_survey_by_token(token: str) -> dict | None:
    with transaction() as conn:
        return _payload(conn, "SELECT payload_json FROM surveys WHERE token=?", (token,))


def list_surveys() -> list[dict]:
    with transaction() as conn:
        return _payloads(conn, "SELECT payload_json FROM surveys ORDER BY updated_at DESC, rowid DESC")


def save_session(conn: Connection, session: dict, *, legacy: bool = False) -> None:
    conflict = "DO NOTHING" if legacy else """
        DO UPDATE SET status=excluded.status, current_index=excluded.current_index,
        updated_at=excluded.updated_at, payload_json=excluded.payload_json
    """
    payload = {key: value for key, value in session.items() if key != "responses"}
    result = conn.execute(f"""
        INSERT INTO survey_sessions(id, survey_id, participant_code, status, current_index,
                                    created_at, updated_at, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) {conflict}
    """, (
        session["id"], session.get("survey_id") or None, session["participant_code"],
        session["status"], int(session.get("current_index") or 0), session["created_at"],
        session.get("updated_at") or session["created_at"], _json(payload),
    ))
    if legacy and result.rowcount == 0:
        return
    conn.executemany("""
        INSERT INTO legacy_session_responses(session_id, ordinal, answered_at, payload_json)
        VALUES (?, ?, ?, ?) ON CONFLICT(session_id, ordinal) DO NOTHING
    """, (
        (session["id"], index, item.get("answered_at") or "", _json(item))
        for index, item in enumerate(session.get("responses") or [])
    ))


def get_session(conn: Connection, session_id: str) -> dict | None:
    session = _payload(conn, "SELECT payload_json FROM survey_sessions WHERE id=?", (session_id,))
    if session is not None:
        session["responses"] = _payloads(conn, """
            SELECT payload_json FROM legacy_session_responses WHERE session_id=? ORDER BY ordinal
        """, (session_id,))
    return session


def list_sessions() -> list[dict]:
    with transaction() as conn:
        sessions = _payloads(conn, "SELECT payload_json FROM survey_sessions ORDER BY updated_at DESC, rowid DESC")
        by_id = {session["id"]: session for session in sessions}
        for session in sessions:
            session["responses"] = []
        for row in conn.execute("""
            SELECT session_id, payload_json FROM legacy_session_responses ORDER BY session_id, ordinal
        """):
            by_id[row["session_id"]]["responses"].append(json.loads(row["payload_json"]))
        return sessions


def count_sessions(survey_id: str) -> int:
    with transaction() as conn:
        return conn.execute("SELECT COUNT(*) FROM survey_sessions WHERE survey_id=?", (survey_id,)).fetchone()[0]


def count_responses(survey_id: str | None = None) -> int:
    condition, args = ("", ()) if survey_id is None else ("AND r.survey_id=?", (survey_id,))
    with transaction() as conn:
        return conn.execute(
            f"SELECT COUNT(*) FROM survey_responses r WHERE {_ACTIVE_RESPONSE} {condition}", args
        ).fetchone()[0]


def save_responses(
    conn: Connection, survey_id: str, records: Iterable[dict], *,
    legacy: bool = False, submit_index: int | None = None,
) -> int:
    params = (
        (
            record["response_id"], survey_id, record.get("session_id") or None,
            record.get("batch_id") or None, submit_index, int(record.get("schema_version") or 1),
            record.get("schema_hash") or "", record.get("submitted_at") or "",
            record.get("origin") or "local", record.get("rater") or "",
            record.get("stimulus_id") or "", int(bool(record.get("valid", True))), _json(record),
        )
        for record in records
    )
    conflict = "ON CONFLICT(response_id) DO NOTHING" if legacy else ""
    return conn.executemany(f"""
        INSERT INTO survey_responses(response_id, survey_id, session_id, batch_id, submit_index,
                                     schema_version, schema_hash, submitted_at, origin, rater,
                                     stimulus_id, valid, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) {conflict}
    """, params).rowcount


def get_response(survey_id: str, response_id: str) -> dict | None:
    with transaction() as conn:
        return _payload(conn, """
            SELECT payload_json FROM survey_responses WHERE survey_id=? AND response_id=?
        """, (survey_id, response_id))


def list_responses(survey_id: str, session_id: str | None = None) -> list[dict]:
    with transaction() as conn:
        if session_id is None:
            return _payloads(conn, "SELECT payload_json FROM survey_responses WHERE survey_id=? ORDER BY rowid", (survey_id,))
        return _payloads(conn, """
            SELECT payload_json FROM survey_responses WHERE survey_id=? AND session_id=?
            ORDER BY submitted_at, rowid
        """, (survey_id, session_id))


def query_responses(survey_id, page=1, page_size=20, query="", validity="", session_id=""):
    clauses = ["r.survey_id=?", _ACTIVE_RESPONSE]
    args = [survey_id]
    if query:
        clauses.append("instr(lower(r.payload_json || coalesce(m.title,'') || coalesce(m.notes,'')), lower(?)) > 0")
        args.append(query)
    if validity:
        clauses.append("r.valid=?")
        args.append(int(validity == "valid"))
    if session_id:
        clauses.append("r.session_id=?")
        args.append(session_id)
    source = "survey_responses r LEFT JOIN record_metadata m ON m.resource='responses' AND m.record_id=r.response_id"
    where = " AND ".join(clauses)
    with transaction() as conn:
        total = conn.execute(f"SELECT count(*) FROM {source} WHERE {where}", args).fetchone()[0]
        all_total = conn.execute(f"SELECT count(*) FROM survey_responses r WHERE r.survey_id=? AND {_ACTIVE_RESPONSE}", (survey_id,)).fetchone()[0]
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        rows = _payloads(conn, f"SELECT r.payload_json FROM {source} WHERE {where} ORDER BY r.submitted_at DESC,r.response_id DESC LIMIT ? OFFSET ?",
                         tuple(args + [page_size, (page-1)*page_size]))
    return {"total": total, "all_total": all_total, "page": page, "pages": pages,
            "page_size": page_size, "responses": rows}


def recent_responses(survey_id: str, limit: int) -> tuple[int, list[dict]]:
    where = f"r.survey_id=? AND {_ACTIVE_RESPONSE}"
    with transaction() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM survey_responses r WHERE {where}", (survey_id,)).fetchone()[0]
        rows = _payloads(conn, f"""
            SELECT r.payload_json FROM survey_responses r WHERE {where}
            ORDER BY r.submitted_at DESC, r.rowid LIMIT ?
        """, (survey_id, limit))
        return total, rows


def save_import(conn: Connection, batch: dict, *, legacy: bool = False) -> None:
    conflict = "ON CONFLICT(batch_id) DO NOTHING" if legacy else ""
    conn.execute(f"""
        INSERT INTO survey_imports(batch_id, survey_id, filename, sha256, created_at, payload_json)
        VALUES (?, ?, ?, ?, ?, ?) {conflict}
    """, (
        batch["batch_id"], batch["survey_id"], batch["filename"], batch.get("sha256") or "",
        batch["created_at"], _json(batch),
    ))


def list_imports() -> list[dict]:
    with transaction() as conn:
        return _payloads(conn, "SELECT payload_json FROM survey_imports ORDER BY created_at DESC, rowid DESC")


def get_import(batch_id: str) -> dict | None:
    with transaction() as conn:
        return _payload(conn, "SELECT payload_json FROM survey_imports WHERE batch_id=?", (batch_id,))


def save_staging(conn: Connection, stage: dict, *, legacy: bool = False) -> None:
    conflict = "ON CONFLICT(token) DO NOTHING" if legacy else ""
    conn.execute(f"""
        INSERT INTO survey_import_staging(token, filename, created_at, payload_json)
        VALUES (?, ?, ?, ?) {conflict}
    """, (stage["token"], stage["filename"], stage["created_at"], _json(stage)))


def get_staging(conn: Connection, token: str) -> dict | None:
    return _payload(conn, "SELECT payload_json FROM survey_import_staging WHERE token=?", (token,))


def _read_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        raise ValueError(f"无法迁移旧问卷文件 {path.name}") from exc


def _read_lines(path: Path) -> Iterable[dict]:
    with path.open(encoding="utf-8-sig") as source:
        for number, line in enumerate(source, start=1):
            if line.strip():
                try:
                    yield json.loads(line)
                except ValueError as exc:
                    raise ValueError(f"无法迁移旧答卷文件 {path.name} 第 {number} 行") from exc


def migrate_legacy() -> None:
    """Copy historical records once in dependency order. Originals remain intact."""
    with transaction(write=True) as conn:
        if conn.execute("SELECT 1 FROM survey_legacy_migration WHERE id=1").fetchone():
            return
        for path in sorted(SURVEYS_DIR.glob("*.json")):
            save_survey(conn, _read_file(path), legacy=True)
        for path in sorted(SESSIONS_DIR.glob("*.json")):
            save_session(conn, _read_file(path), legacy=True)
        for path in sorted(IMPORTS_DIR.glob("*.json")):
            save_import(conn, _read_file(path), legacy=True)
        for path in sorted(RESPONSES_DIR.glob("*.jsonl")):
            save_responses(conn, path.stem, _read_lines(path), legacy=True)
        for path in sorted(STAGING_DIR.glob("*.json")):
            if path.with_suffix(".csv").is_file():
                save_staging(conn, _read_file(path), legacy=True)
        conn.execute(
            "INSERT INTO survey_legacy_migration(id, completed_at) VALUES (1, ?)",
            (datetime.now().astimezone().isoformat(timespec="seconds"),),
        )
