"""Resource adapters: common list CRUD, domain-specific creation workflows."""
from __future__ import annotations

import math
import json
from urllib.parse import quote

from . import record_store as store

RESOURCES = {
    "surveys": {"label": "问卷", "create_url": "/surveys/new"},
    "responses": {"label": "答卷", "create_url": "/survey-data?tab=import"},
    "imports": {"label": "导入批次", "create_url": "/survey-data?tab=import"},
    "media": {"label": "素材", "upload": "/api/records/media/upload", "accept": ".mp4,.mp3"},
    "features": {"label": "特征数据集", "upload": "/api/records/features/upload", "accept": ".npz"},
    "raw_data": {"label": "原始数据集", "upload": "/api/raw/upload", "accept": ".npz"},
    "eeg_uploads": {"label": "EEGLAB 上传", "upload": "/api/eeg/upload", "accept": ".set,.zip"},
    "eeg_runs": {"label": "EEG 处理记录", "create_url": "/eeg"},
    "experiments": {"label": "实验记录", "create_url": "/training"},
    "documents": {"label": "项目文档", "upload": "/api/records/documents/upload", "accept": ".pdf,.docx,.md,.txt"},
    "jobs": {"label": "后台任务", "create_url": "/training"},
    "training_tasks": {"label": "训练监控任务", "create_url": "/training"},
}


@store.managed("jobs", title_key="title")
def job_records(limit=100):
    from .config import WEB_JOBS_DIR
    from .jobs import manager
    rows = {}
    for path in WEB_JOBS_DIR.glob("*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            row.pop("logs", None)
            if row.get("id"):
                rows[row["id"]] = row
        except (ValueError, OSError):
            continue
    live = manager.list(limit if limit is not None else 2**31)
    live_ids = {job.id for job in live}
    if any(row.get("status") in {"running", "queued"} and key not in live_ids for key, row in rows.items()):
        try:
            from .training_monitor import processes
            pids = {int(p["ProcessId"]) for p in processes()}
            for key, row in rows.items():
                if key not in live_ids and row.get("status") in {"running", "queued"} and row.get("runtime", {}).get("pid") not in pids:
                    row["status"] = "interrupted"
        except Exception:
            pass  # Unknown process state must not be presented as safely stopped.
    for job in live:
        rows[job.id] = job.to_dict(include_logs=False)
    ordered = sorted(rows.values(), key=lambda row: row.get("created_at", ""), reverse=True)
    return ordered if limit is None else ordered[:limit]


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items() if not str(k).startswith("_")}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def source_rows(resource):
    # Lazy imports keep the domain services independent of this registry.
    from . import services, surveys, survey_meta, media, eeg
    from .routers.raw_eeg import list_runs
    from .training_monitor import snapshot as training_snapshot
    loaders = {
        "surveys": (surveys.list_surveys, "id", "title"),
        "imports": (survey_meta.list_imports, "batch_id", "filename"),
        "media": (lambda: media.library_payload()["items"], "id", "filename"),
        "features": (services.list_feature_datasets, "id", "name"),
        "raw_data": (services.list_raw_datasets, "id", "name"),
        "eeg_uploads": (eeg.list_uploads, "upload_id", "filename"),
        "eeg_runs": (lambda: list_runs(limit=None), "run_id", "run_id"),
        "experiments": (services.list_experiments, "id", "label"),
        "documents": (services.list_docs, "no", "title"),
        "jobs": (lambda: job_records(limit=None), "id", "title"),
        "training_tasks": (lambda: training_snapshot(all_tasks=True)["tasks"], "id", "title"),
    }
    with store.including_deleted():
        if resource == "responses":
            rows = []
            for survey in surveys.list_surveys():
                for record in survey_meta.iter_responses(survey["id"]):
                    rows.append({**record, "survey_id": survey["id"]})
            return rows, "response_id", "response_id"
        loader, id_key, title_key = loaders[resource]
        return loader(), id_key, title_key


def records(resource):
    rows, id_key, title_key = source_rows(resource)
    state = store.snapshot()
    result = []
    for row in rows:
        record_id = str(row[id_key])
        meta = store.metadata(resource, record_id, state)
        original = row.get("record_meta", {}).get("original_title") or row.get(title_key) or record_id
        url = ""
        if resource == "experiments": url = row.get("report_url", "")
        elif resource == "media": url = row.get("preview_url", "")
        elif resource == "surveys": url = f"/surveys/{quote(record_id)}/edit"
        elif resource == "documents": url = row.get("pdf_url") or row.get("docx_url") or row.get("url", "")
        elif resource == "responses": url = f"/survey-data?survey_id={quote(row['survey_id'])}&tab=responses&response_id={quote(record_id)}"
        elif resource == "features": url = f"/training?dataset={quote(record_id)}"
        elif resource == "eeg_runs": url = f"/api/eeg/raw/runs/{quote(record_id)}/report"
        title = meta.get("title") or str(original)
        if resource == "experiments" and not meta.get("title"):
            title = f"{row.get('model') or '模型实验'} · {str(row.get('created_at') or '')[:16].replace('T', ' ')}"
        result.append({"id": record_id, "title": title, "metadata": meta,
                       "updated_at": meta.get("updated_at") or row.get("created_at") or row.get("started_at") or "",
                       "source": clean(row), "url": url,
                       "busy": resource in {"jobs", "eeg_runs", "training_tasks"} and row.get("status") in {"running", "queued", "unknown"}})
    return result


def get_record(resource, record_id):
    return next((item for item in records(resource) if item["id"] == record_id), None)
