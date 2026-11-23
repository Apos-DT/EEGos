"""Index disk-generated artifacts without moving their underlying files."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path
from threading import RLock
from typing import Any

from .db import transaction

_index_lock = RLock()


def _stamp(path: Path) -> tuple[int, int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size


def index_records(
    kind: str,
    candidates: Iterable[Path],
    inspect: Callable[[Path], dict[str, Any] | None],
    *,
    sidecars: Callable[[Path], Iterable[Path]] | None = None,
) -> list[dict[str, Any]]:
    """Refresh changed paths and return records in the candidate order."""
    with _index_lock:
        with transaction() as conn:
            existing = {
                row["path"]: (row["signature"], row["payload"])
                for row in conn.execute(
                    "SELECT path, signature, payload FROM file_artifacts WHERE kind = ?", (kind,)
                )
            }
        active = set()
        updated = []
        records = []
        for candidate in candidates:
            primary = _stamp(candidate)
            if primary is None:
                continue
            key = str(candidate.resolve())
            if key in active:
                continue
            active.add(key)
            dependencies = tuple(sidecars(candidate)) if sidecars else ()
            signature = json.dumps([primary, *(_stamp(path) for path in dependencies)])
            previous_signature, previous_payload = existing.get(key, (None, None))
            if previous_signature == signature:
                record = json.loads(previous_payload) if previous_payload else None
            else:
                record = inspect(candidate)
                if _stamp(candidate) != primary:
                    # The producer is still writing this file. Retry on the next read.
                    continue
                record_id = record.get("id", record.get("run_id")) if record else None
                payload = json.dumps(record, ensure_ascii=False, allow_nan=False) if record else None
                updated.append((kind, key, signature, record_id, payload))
            if record is not None:
                records.append(record)
        removed = existing.keys() - active
        if updated or removed:
            with transaction(write=True) as conn:
                conn.executemany(
                    """INSERT INTO file_artifacts (kind, path, signature, record_id, payload)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT (kind, path) DO UPDATE SET
                         signature=excluded.signature, record_id=excluded.record_id, payload=excluded.payload""",
                    updated,
                )
                conn.executemany(
                    "DELETE FROM file_artifacts WHERE kind = ? AND path = ? AND signature = ?",
                    ((kind, path, existing[path][0]) for path in removed),
                )
        return records
