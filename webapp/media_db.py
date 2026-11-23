"""Persistent index of managed and referenced media files."""

from __future__ import annotations

import math

from .db import transaction

_COLUMNS = (
    "id", "modality", "filename", "category", "original_name", "discrete_label",
    "quality_score", "grade", "mean_valence", "mean_arousal", "selected",
    "selection_rank", "available", "managed", "size_mb",
)
_UPSERT_ASSET = (
    f"INSERT INTO media_assets ({', '.join(_COLUMNS)}) "
    f"VALUES ({', '.join('?' for _ in _COLUMNS)}) "
    "ON CONFLICT (id) DO UPDATE SET "
    + ", ".join(f"{column} = excluded.{column}" for column in _COLUMNS[1:])
)
_FLAGS = ("selected", "available", "managed")
_NUMBERS = {"quality_score", "mean_valence", "mean_arousal"}


def _row_values(item):
    modality, filename = item.get("modality"), item.get("filename")
    if modality not in {"video", "audio"} or not filename or item.get("id") != f"{modality}/{filename}":
        raise ValueError("素材清单中的素材编号无效")
    values = []
    for column in _COLUMNS:
        value = item.get(column)
        if column in _FLAGS:
            value = int(bool(value))
        elif column == "selection_rank":
            value = int(value or 0)
        elif column in _NUMBERS:
            value = float(value) if value is not None else None
            if value is not None and not math.isfinite(value):
                value = None
        elif column == "size_mb":
            value = float(value or 0)
            if not math.isfinite(value):
                value = 0
        else:
            value = str(value or "")
        values.append(value)
    return values


def read_snapshot():
    with transaction() as conn:
        state = conn.execute("SELECT * FROM media_library_state WHERE singleton = 1").fetchone()
        if state is None:
            return None, None
        items = []
        for row in conn.execute(
            "SELECT * FROM media_assets ORDER BY modality DESC, length(filename), filename",
        ):
            item = dict(row)
            for flag in _FLAGS:
                item[flag] = bool(item[flag])
            items.append(item)
        return {
            "generated_at": state["generated_at"],
            "managed_dir": state["managed_dir"],
            "source": {"video": state["source_video"], "audio": state["source_audio"]},
            "items": items,
            "counts": {
                "video": sum(item["modality"] == "video" for item in items),
                "audio": sum(item["modality"] == "audio" for item in items),
                "managed": sum(item["managed"] for item in items),
                "available": sum(item["available"] for item in items),
            },
        }, state["input_signature"]


def write_snapshot(payload, signature, *, initial=False):
    rows = [_row_values(item) for item in payload["items"]]
    with transaction(write=True) as conn:
        if initial and conn.execute("SELECT 1 FROM media_library_state").fetchone() is not None:
            return
        # Keep identifiers and descriptive metadata for offline files, since an
        # existing questionnaire can reference them. Found files are upserted.
        conn.execute("UPDATE media_assets SET available = 0, managed = 0, size_mb = 0")
        conn.executemany(_UPSERT_ASSET, rows)
        source = payload.get("source") or {}
        conn.execute(
            """
            INSERT INTO media_library_state (singleton, generated_at, managed_dir, source_video,
                                             source_audio, input_signature)
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT (singleton) DO UPDATE SET
                generated_at = excluded.generated_at, managed_dir = excluded.managed_dir,
                source_video = excluded.source_video, source_audio = excluded.source_audio,
                input_signature = excluded.input_signature
            """,
            (payload.get("generated_at", ""), payload.get("managed_dir", ""),
             source.get("video", ""), source.get("audio", ""), signature),
        )
