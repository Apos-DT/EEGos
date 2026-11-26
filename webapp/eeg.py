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
from .db import transaction
from .record_store import managed


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "", value)[:64]


def _relative_path(path: Path) -> str:
    path = path.resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def _insert_upload(conn, data):
    conn.execute(
        """INSERT INTO eeg_uploads
           (id, filename, set_path, uploaded_at, fs, n_channels, n_samples, payload)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO NOTHING""",
        (data["upload_id"], data["filename"], data["set_path"], data["uploaded_at"],
         data["fs"], data["n_channels"], data["n_samples"], json.dumps(data, ensure_ascii=False)),
    )


def migrate_legacy() -> None:
    with transaction() as conn:
        if conn.execute("SELECT 1 FROM legacy_imports WHERE domain = 'eeg_uploads'").fetchone():
            return
    with transaction(write=True) as conn:
        if conn.execute("SELECT 1 FROM legacy_imports WHERE domain = 'eeg_uploads'").fetchone():
            return
        for path in sorted(UPLOAD_DIR.glob("*/upload.json")):
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            _insert_upload(conn, data)
        conn.execute("INSERT INTO legacy_imports (domain) VALUES ('eeg_uploads')")


def save_upload(body: bytes, filename: str) -> dict[str, Any]:
    if not body:
        raise ValueError("文件为空")
    if len(body) > 500 * 1024 * 1024:
        raise ValueError("文件超过 500 MB 限制")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".set", ".zip"}:
        raise ValueError("请上传 .set（数据内嵌）或包含 .set/.fdt 的 .zip")
    migrate_legacy()
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
        "set_path": _relative_path(set_path),
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
    with transaction(write=True) as conn:
        _insert_upload(conn, summary)
    return summary


@managed("eeg_uploads", id_key="upload_id", title_key="filename")
def list_uploads() -> list[dict[str, Any]]:
    migrate_legacy()
    with transaction() as conn:
        items = [json.loads(row["payload"]) for row in conn.execute(
            "SELECT payload FROM eeg_uploads ORDER BY uploaded_at DESC, id DESC"
        )]
    for item in items:
        report = output_for(item["upload_id"]) / "eeg_report.json"
        if report.is_file():
            item["status"] = "processed"
            item["report"] = _relative_path(report)
            preview = report.with_name("eeg_preview.png")
            item["preview"] = _relative_path(preview) if preview.is_file() else ""
    return items


def resolve_upload(upload_id: str) -> dict[str, Any]:
    safe = _safe_id(upload_id)
    if not safe or safe != upload_id:
        raise ValueError("非法 upload id")
    migrate_legacy()
    with transaction() as conn:
        row = conn.execute("SELECT payload FROM eeg_uploads WHERE id = ?", (safe,)).fetchone()
    if row is None:
        raise FileNotFoundError("上传记录不存在")
    data = json.loads(row["payload"])
    set_path = (ROOT / data["set_path"]).resolve()
    if not set_path.is_relative_to((UPLOAD_DIR / safe).resolve()) or not set_path.is_file():
        raise FileNotFoundError("EEGLAB .set 文件不存在")
    data["_set_path"] = set_path
    return data


def output_for(upload_id: str) -> Path:
    base = OUTPUT_DIR / _safe_id(upload_id)
    reports = list(OUTPUT_DIR.glob(f"{_safe_id(upload_id)}--*/eeg_report.json"))
    if reports:
        return max(reports, key=lambda p: p.stat().st_mtime_ns).parent
    return base


def report_for(upload_id: str) -> dict[str, Any]:
    path = output_for(upload_id) / "eeg_report.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
