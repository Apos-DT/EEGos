"""Managed stimulus library for videos and music.

All daily experiments read from ``data/media`` rather than from ad-hoc source
folders.  The source folders are still supported as a fallback so that a path
change cannot break existing sessions; ``sync`` copies them into the managed
library once.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .config import (
    AUDIO_DIR,
    MANIFEST,
    MAPPING,
    MEDIA_DIR,
    QUALITY,
    ROOT,
    SELECTED,
    SOURCE_AUDIO_CANDIDATES,
    SOURCE_VIDEO_CANDIDATES,
    VIDEO_DIR,
    cache_by,
)


def _first_existing(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def source_dir(modality: str) -> Path:
    return _first_existing(SOURCE_VIDEO_CANDIDATES if modality == "video" else SOURCE_AUDIO_CANDIDATES)


def managed_dir(modality: str) -> Path:
    return VIDEO_DIR if modality == "video" else AUDIO_DIR


def media_path(modality: str, filename: str) -> Path | None:
    target = managed_dir(modality) / Path(filename).name
    if target.exists():
        return target
    fallback = source_dir(modality) / Path(filename).name
    return fallback if fallback.exists() else None


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame()


def _metadata(modality: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    mapping = _read_csv(MAPPING[modality])
    quality = _read_csv(QUALITY[modality])
    mapping_by_name: dict[str, dict[str, Any]] = {}
    name_col = "新文件名"
    if not mapping.empty and name_col in mapping.columns:
        for _, row in mapping.iterrows():
            mapping_by_name[str(row[name_col])] = {
                "category": str(row.get("类别", "") or ""),
                "original_name": str(row.get("原始名称", "") or ""),
            }
    quality_by_name: dict[str, dict[str, Any]] = {}
    if not quality.empty:
        id_col = "视频编号" if modality == "video" else "音乐歌曲编号"
        if id_col in quality.columns:
            for _, row in quality.iterrows():
                quality_by_name[str(row[id_col])] = {
                    "quality_score": float(row.get("质量总分", 0) or 0),
                    "grade": str(row.get("质量等级", "") or ""),
                    "discrete_label": str(row.get("离散标签", "") or ""),
                    "mean_valence": float(row.get("平均效价", 0) or 0),
                    "mean_arousal": float(row.get("平均唤醒", 0) or 0),
                }
    selected: dict[str, int] = {}
    frame = _read_csv(SELECTED)
    if not frame.empty and "stimulus_id" in frame.columns:
        for _, row in frame.iterrows():
            if str(row.get("modality", "")) == modality:
                selected[str(row["stimulus_id"])] = int(row.get("selection_rank", 0) or 0)
    return mapping_by_name, {"quality": quality_by_name, "selected": selected}


def build_manifest(copy_missing: bool = False) -> dict[str, Any]:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for modality in ("video", "audio"):
        mapping, meta = _metadata(modality)
        quality = meta["quality"]
        selected = meta["selected"]
        directory = managed_dir(modality)
        source = source_dir(modality)
        source_files = sorted(
            [p for p in source.glob("*.mp4" if modality == "video" else "*.mp3") if p.is_file()]
        ) if source.exists() else []
        if copy_missing:
            for path in source_files:
                target = directory / path.name
                if not target.exists() or target.stat().st_size != path.stat().st_size:
                    shutil.copy2(path, target)
        filenames = {p.name for p in directory.glob("*.mp4" if modality == "video" else "*.mp3")}
        filenames.update(p.name for p in source_files)
        for filename in sorted(filenames, key=lambda value: (len(value), value)):
            path = media_path(modality, filename)
            info = mapping.get(filename, {})
            q = quality.get(filename, {})
            items.append(
                {
                    "id": f"{modality}/{filename}",
                    "modality": modality,
                    "filename": filename,
                    "category": info.get("category", ""),
                    "original_name": info.get("original_name", ""),
                    "discrete_label": q.get("discrete_label", ""),
                    "quality_score": q.get("quality_score"),
                    "grade": q.get("grade", ""),
                    "mean_valence": q.get("mean_valence"),
                    "mean_arousal": q.get("mean_arousal"),
                    "selected": filename in selected,
                    "selection_rank": selected.get(filename, 0),
                    "available": bool(path and path.exists()),
                    "managed": bool((directory / filename).exists()),
                    "size_mb": round(path.stat().st_size / 1024 / 1024, 2) if path and path.exists() else 0,
                }
            )
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "managed_dir": str(MEDIA_DIR.relative_to(ROOT)),
        "source": {
            "video": str(source_dir("video").relative_to(ROOT)),
            "audio": str(source_dir("audio").relative_to(ROOT)),
        },
        "items": items,
        "counts": {
            "video": sum(1 for item in items if item["modality"] == "video"),
            "audio": sum(1 for item in items if item["modality"] == "audio"),
            "managed": sum(1 for item in items if item["managed"]),
            "available": sum(1 for item in items if item["available"]),
        },
    }
    MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def load_manifest(refresh: bool = True) -> dict[str, Any]:
    if refresh or not MANIFEST.exists():
        return build_manifest(copy_missing=False)
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return build_manifest(copy_missing=False)


# 按「输入源」签名缓存，而不是按 manifest 自身：build_manifest 每次都会重写
# manifest.json，若把 manifest 的 mtime 纳入签名，就会写一次失效一次、永不命中。
@cache_by(
    "media_library",
    lambda: VIDEO_DIR,
    lambda: AUDIO_DIR,
    lambda: list(MAPPING.values()),
    lambda: list(QUALITY.values()),
    lambda: SELECTED,
)
def _library_payload() -> dict[str, Any]:
    data = load_manifest(refresh=True)
    items = data["items"]
    for item in items:
        if item["available"]:
            item["preview_url"] = f"/media/preview/{item['modality']}/{item['filename']}"
            item["media_url"] = f"/media/file/{item['modality']}/{item['filename']}"
        else:
            item["preview_url"] = ""
            item["media_url"] = ""
    data["selected_count"] = sum(1 for item in items if item["selected"])
    return data


def library_payload() -> dict[str, Any]:
    from .record_store import decorate_rows
    data = _library_payload()
    data["items"] = decorate_rows("media", data["items"], title_key="display_name")
    data["selected_count"] = sum(1 for item in data["items"] if item["selected"])
    for kind in ("video", "audio"):
        data["counts"][kind] = sum(1 for item in data["items"] if item["modality"] == kind)
    for flag in ("managed", "available"):
        data["counts"][flag] = sum(1 for item in data["items"] if item[flag])
    return data


def item_by_id(item_id: str) -> dict[str, Any] | None:
    for item in load_manifest(refresh=True)["items"]:
        if item["id"] == item_id:
            return item
    return None


def sync_library() -> dict[str, Any]:
    return build_manifest(copy_missing=True)
