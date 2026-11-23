"""Shared, reversible list metadata. Scientific source files stay immutable."""
from __future__ import annotations

import copy
import functools
import json
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime

from .config import DATA_DIR, invalidate
from .db import transaction

STORE_DIR = DATA_DIR / "record_management"
_include_deleted = ContextVar("include_deleted_records", default=False)


class ConflictError(ValueError):
    pass


class StoreError(RuntimeError):
    pass


@contextmanager
def _store(write=False):
    try:
        with transaction(write=write) as conn:
            if _initialized(conn):
                yield conn
                return
            if write:
                _import_legacy(conn)
                yield conn
                return
        with transaction(write=True) as conn:
            if not _initialized(conn):
                _import_legacy(conn)
            yield conn
    except sqlite3.DatabaseError as exc:
        raise StoreError("记录管理数据库暂不可用") from exc


def _initialized(conn):
    return conn.execute("SELECT 1 FROM record_legacy_import WHERE singleton = 1").fetchone() is not None


def _read_legacy():
    path = STORE_DIR / "state.json"
    if not path.exists():
        return {"records": {}, "events": [], "uploads": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise StoreError("记录管理存储无法读取，请检查本机文件；未覆盖已有记录") from exc
    if (not isinstance(data, dict) or not isinstance(data.get("records"), dict)
            or not isinstance(data.get("events"), list) or not isinstance(data.get("uploads", {}), dict)):
        raise StoreError("记录管理文件格式异常，请恢复备份后重试")
    data.setdefault("uploads", {})
    return data


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _save_metadata(conn, resource, record_id, value):
    conn.execute(
        """
        INSERT INTO record_metadata (resource, record_id, title, notes, tags_json, revision, deleted_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (resource, record_id) DO UPDATE SET
            title = excluded.title, notes = excluded.notes, tags_json = excluded.tags_json,
            revision = excluded.revision, deleted_at = excluded.deleted_at, updated_at = excluded.updated_at
        """,
        (resource, str(record_id), value.get("title", ""), value.get("notes", ""), _json(value.get("tags", [])),
         value.get("revision", 0), value.get("deleted_at"), value.get("updated_at")),
    )


def _save_event(conn, resource, record_id, before, after, at):
    conn.execute(
        "INSERT INTO record_events (resource, record_id, before_json, after_json, event_at) VALUES (?, ?, ?, ?, ?)",
        (resource, str(record_id), _json(before), _json(after), at),
    )


def _save_upload(conn, resource, record_id, row):
    conn.execute(
        """INSERT INTO record_uploads (resource, record_id, payload_json) VALUES (?, ?, ?)
        ON CONFLICT (resource, record_id) DO UPDATE SET payload_json = excluded.payload_json""",
        (resource, str(record_id), _json(row)),
    )


def _import_legacy(conn):
    state = _read_legacy()
    try:
        for resource, rows in state["records"].items():
            for record_id, value in rows.items():
                _save_metadata(conn, resource, record_id, value)
        for event in state["events"]:
            _save_event(conn, event["resource"], event["id"], event["before"], event["after"], event["at"])
        for resource, rows in state["uploads"].items():
            for record_id, row in rows.items():
                _save_upload(conn, resource, record_id, row)
    except (AttributeError, KeyError, TypeError, ValueError, sqlite3.IntegrityError) as exc:
        raise StoreError("记录管理文件格式异常，数据库未接管该文件") from exc
    conn.execute("INSERT INTO record_legacy_import (singleton) VALUES (1)")


def migrate_legacy():
    """Import the previous overlay and history exactly once, leaving its source intact."""
    with _store():
        pass


def empty_metadata():
    return {"title": "", "notes": "", "tags": [], "revision": 0, "deleted_at": None}


def _decode_metadata(row):
    if row is None:
        return empty_metadata()
    result = {key: row[key] for key in ("title", "notes", "revision", "deleted_at")}
    result["tags"] = json.loads(row["tags_json"])
    if row["updated_at"] is not None:
        result["updated_at"] = row["updated_at"]
    return result


def _one_metadata(conn, resource, record_id):
    row = conn.execute(
        "SELECT * FROM record_metadata WHERE resource = ? AND record_id = ?", (resource, str(record_id)),
    ).fetchone()
    return _decode_metadata(row)


def metadata_index(resource):
    with _store() as conn:
        return {
            row["record_id"]: _decode_metadata(row)
            for row in conn.execute("SELECT * FROM record_metadata WHERE resource = ?", (resource,))
        }


def uploads(resource):
    with _store() as conn:
        return {
            row["record_id"]: json.loads(row["payload_json"])
            for row in conn.execute("SELECT record_id, payload_json FROM record_uploads WHERE resource = ?", (resource,))
        }


def snapshot():
    with _store() as conn:
        resources = {}
        for row in conn.execute("SELECT * FROM record_metadata"):
            resources.setdefault(row["resource"], {})[row["record_id"]] = _decode_metadata(row)
        events = [
            {"resource": row["resource"], "id": row["record_id"], "before": json.loads(row["before_json"]),
             "after": json.loads(row["after_json"]), "at": row["event_at"]}
            for row in conn.execute("SELECT * FROM record_events ORDER BY sequence")
        ]
        uploaded = {}
        for row in conn.execute("SELECT * FROM record_uploads"):
            uploaded.setdefault(row["resource"], {})[row["record_id"]] = json.loads(row["payload_json"])
    return {"records": resources, "events": events, "uploads": uploaded}


def metadata(resource, record_id, state=None):
    if state is not None:
        return copy.deepcopy(state["records"].get(resource, {}).get(str(record_id), empty_metadata()))
    with _store() as conn:
        return _one_metadata(conn, resource, record_id)


def update(resource, record_id, changes, revision):
    """Atomic metadata, soft delete and restore with optimistic concurrency."""
    with _store(write=True) as conn:
        before = _one_metadata(conn, resource, record_id)
        if revision != before["revision"]:
            raise ConflictError("记录已被更新，请重新打开后再保存")
        after = {**before, **changes, "revision": before["revision"] + 1,
                 "updated_at": datetime.now().astimezone().isoformat(timespec="seconds")}
        _save_metadata(conn, resource, record_id, after)
        _save_event(conn, resource, record_id, before, after, after["updated_at"])
    invalidate()
    return copy.deepcopy(after)


def register_upload(resource, record_id, row, title):
    with _store(write=True) as conn:
        before = _one_metadata(conn, resource, record_id)
        after = {**before, "title": title, "revision": before["revision"] + 1,
                 "updated_at": datetime.now().astimezone().isoformat(timespec="seconds")}
        _save_upload(conn, resource, record_id, row)
        _save_metadata(conn, resource, record_id, after)
        _save_event(conn, resource, record_id, before, after, after["updated_at"])
    invalidate()


@contextmanager
def including_deleted():
    token = _include_deleted.set(True)
    try:
        yield
    finally:
        _include_deleted.reset(token)


def decorate_rows(resource, rows, id_key="id", title_key="name"):
    stored = metadata_index(resource)
    result = []
    for source in rows:
        row = copy.deepcopy(source)
        meta = stored.get(str(row[id_key]), empty_metadata())
        if meta.get("deleted_at") and not _include_deleted.get():
            continue
        row["record_meta"] = {**meta, "original_title": str(row.get(title_key, ""))}
        if meta.get("title"):
            row[title_key] = meta["title"]
        result.append(row)
    return result


def managed(resource, id_key="id", title_key="name"):
    """Apply outside existing caches, so edits and trash affect every consumer."""
    def decorator(loader):
        @functools.wraps(loader)
        def wrapped(*args, **kwargs):
            return decorate_rows(resource, loader(*args, **kwargs), id_key, title_key)
        return wrapped
    return decorator
