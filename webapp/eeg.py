"""Upload/resolve helpers for the raw EEG processing page."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from eeg_emostudio.data.eeglab import load_eeglab_set, safe_extract_zip

from .config import EEG_UPLOAD_DIR as UPLOAD_DIR
from .config import OUTPUT_DIR, ROOT
from .record_store import managed


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "", value)[:64]


def save_upload(body: bytes, filename: str) -> dict[str, Any]:
    if not body:
        raise ValueError("文件为空")
    if len(body) > 500 * 1024 * 1024:
        raise ValueError("文件超过 500 MB 限制")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".set", ".zip"}:
        raise ValueError("请上传 .set（数据内嵌）或包含 .set/.fdt 的 .zip")
    upload_id = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
    directory = UPLOAD_DIR / upload_id
    directory.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.\-\u4e00-\u9fff]+", "_", Path(filename).name)
    target = directory / safe_name
    target.write_bytes(body)
    if suffix == ".zip":
        set_path = safe_extract_zip(target, directory / "unpacked")
    else:
        set_path = target
    raw = load_eeglab_set(set_path)
    summary = {
        "upload_id": upload_id,
        "filename": safe_name,
        "set_path": str(set_path.relative_to(ROOT)),
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "setname": raw.setname,
        "subject": raw.subject,
        "fs": raw.fs,
        "n_channels": int(raw.data.shape[0]),
        "n_samples": int(raw.data.shape[1]),
        "duration_s": round(raw.data.shape[1] / raw.fs, 2),
        "n_events": len(raw.events),
        "event_types": sorted({item["type"] for item in raw.events}),
        "channels": raw.channel_names,
        "status": "uploaded",
        "report": "",
        "preview": "",
    }
    (directory / "upload.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


@managed("eeg_uploads", id_key="upload_id", title_key="filename")
def list_uploads() -> list[dict[str, Any]]:
    if not UPLOAD_DIR.exists():
        return []
    items = []
    for path in sorted(UPLOAD_DIR.glob("*/upload.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            report = OUTPUT_DIR / data["upload_id"] / "eeg_report.json"
            if report.exists():
                data["status"] = "processed"
                data["report"] = str(report.relative_to(ROOT))
                data["preview"] = str((report.parent / "eeg_preview.png").relative_to(ROOT)) if (report.parent / "eeg_preview.png").exists() else ""
            items.append(data)
        except Exception:
            continue
    return items


def resolve_upload(upload_id: str) -> dict[str, Any]:
    safe = _safe_id(upload_id)
    if not safe or safe != upload_id:
        raise ValueError("非法 upload id")
    path = UPLOAD_DIR / safe / "upload.json"
    if not path.exists():
        raise FileNotFoundError("上传记录不存在")
    data = json.loads(path.read_text(encoding="utf-8"))
    set_path = (ROOT / data["set_path"]).resolve()
    if not set_path.exists():
        raise FileNotFoundError("EEGLAB .set 文件不存在")
    data["_set_path"] = set_path
    return data


def output_for(upload_id: str) -> Path:
    return OUTPUT_DIR / _safe_id(upload_id)


def report_for(upload_id: str) -> dict[str, Any]:
    path = output_for(upload_id) / "eeg_report.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
