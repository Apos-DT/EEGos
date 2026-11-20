"""Shared, reversible list metadata. Scientific source files stay immutable."""
from __future__ import annotations

import copy
import functools
import json
import os
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from threading import RLock

from .config import DATA_DIR, invalidate

STORE_DIR = DATA_DIR / "record_management"
_lock = RLock()
_include_deleted = ContextVar("include_deleted_records", default=False)


class ConflictError(ValueError):
    pass


class StoreError(RuntimeError):
    pass


@contextmanager
def _transaction():
    # Also serialize writers from two Web processes, not just two threads.
    with _lock:
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        with (STORE_DIR / ".write.lock").open("a+b") as handle:
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"\0"); handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read():
    path = STORE_DIR / "state.json"
    if not path.exists():
        return {"records": {}, "events": [], "uploads": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise StoreError("记录管理存储无法读取，请检查本机文件；未覆盖已有记录") from exc
    if not isinstance(data, dict) or not isinstance(data.get("records"), dict) or not isinstance(data.get("events"), list):
        raise StoreError("记录管理文件格式异常，请恢复备份后重试")
    data.setdefault("uploads", {})
    return data


def snapshot():
    with _lock:
        return copy.deepcopy(_read())


def metadata(resource, record_id, state=None):
    state = state if state is not None else snapshot()
    return copy.deepcopy(state["records"].get(resource, {}).get(str(record_id), {
        "title": "", "notes": "", "tags": [], "revision": 0, "deleted_at": None,
    }))


def update(resource, record_id, changes, revision):
    """Atomic metadata, soft delete and restore with optimistic concurrency."""
    with _transaction():
        state = _read()
        before = metadata(resource, record_id, state)
        if revision != before["revision"]:
            raise ConflictError("记录已被更新，请重新打开后再保存")
        after = {**before, **changes, "revision": before["revision"] + 1,
                 "updated_at": datetime.now().astimezone().isoformat(timespec="seconds")}
        state["records"].setdefault(resource, {})[str(record_id)] = after
        state["events"].append({"resource": resource, "id": str(record_id),
                                "before": before, "after": after, "at": after["updated_at"]})
        _write(state)
    invalidate()
    return copy.deepcopy(after)


def _write(state):
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STORE_DIR / f".state-{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, STORE_DIR / "state.json")
    finally:
        temporary.unlink(missing_ok=True)


def register_upload(resource, record_id, row, title):
    with _transaction():
        state = _read()
        state["uploads"].setdefault(resource, {})[record_id] = row
        before = metadata(resource, record_id, state)
        after = {**before, "title": title, "revision": 1,
                 "updated_at": datetime.now().astimezone().isoformat(timespec="seconds")}
        state["records"].setdefault(resource, {})[record_id] = after
        state["events"].append({"resource": resource, "id": record_id, "before": before, "after": after, "at": after["updated_at"]})
        _write(state)
    invalidate()


@contextmanager
def including_deleted():
    token = _include_deleted.set(True)
    try:
        yield
    finally:
        _include_deleted.reset(token)


def decorate_rows(resource, rows, id_key="id", title_key="name"):
    state = snapshot()
    result = []
    for source in rows:
        row = copy.deepcopy(source)
        meta = metadata(resource, row[id_key], state)
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
