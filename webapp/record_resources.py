"""Resource adapters: common list CRUD, domain-specific creation workflows."""
from __future__ import annotations

import json
import math
from urllib.parse import quote

from . import record_store as store

RESOURCES = {
    "surveys": {"label": "问卷", "create_url": "/surveys/new"},
    "responses": {"label": "答卷", "create_url": "/survey-data?tab=import"},
    "imports": {"label": "导入批次", "create_url": "/survey-data?tab=import"},
    "media": {"label": "素材", "upload": "/api/records/media/upload", "accept": ".mp4,.mp3"},
    "features": {"label": "特征数据集", "upload": "/api/records/features/upload", "accept": ".npz"},
    "raw_data": {"label": "EEG 原始数据集", "create_url": "/datasets?tab=eeg#uploadCard"},
    "eeg_uploads": {"label": "EEGLAB 上传", "upload": "/api/eeg/upload", "accept": ".set,.zip"},
    "eeg_runs": {"label": "EEG 处理记录", "create_url": "/eeg"},
    "experiments": {"label": "实验记录", "create_url": "/training"},
    "documents": {"label": "项目文档", "upload": "/api/records/documents/upload", "accept": ".pdf,.docx,.md,.txt"},
    "jobs": {"label": "后台任务", "create_url": "/training"},
    "training_tasks": {"label": "训练监控任务", "create_url": "/training"},
}


@store.managed("jobs", title_key="title")
def job_records(limit=100):
    from .jobs import manager
    return manager.history(limit)


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


def records(resource, source=None):
    rows, id_key, title_key = source if source is not None else source_rows(resource)
    metadata = store.metadata_index(resource)
    result = []
    for row in rows:
        record_id = str(row[id_key])
        meta = metadata.get(record_id) or store.empty_metadata()
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
    if resource == "responses":
        from .db import transaction
        with transaction() as conn:
            row = conn.execute("SELECT payload_json FROM survey_responses WHERE response_id=?", (record_id,)).fetchone()
        if row:
            return records(resource, ([json.loads(row[0])], "response_id", "response_id"))[0]
    return next((item for item in records(resource) if item["id"] == record_id), None)


def query_response_records(query, view, page, page_size):
    from .db import transaction
    conditions, args = [], []
    if view != "all":
        conditions.append("m.deleted_at IS NOT NULL" if view == "trash" else "m.deleted_at IS NULL")
    if query:
        conditions.append("instr(lower(r.payload_json || coalesce(m.title,'') || coalesce(m.notes,'') || coalesce(m.tags_json,'')),lower(?))>0")
        args.append(query)
    where = " AND ".join(conditions) or "1=1"
    source = "survey_responses r LEFT JOIN record_metadata m ON m.resource='responses' AND m.record_id=r.response_id"
    with transaction() as conn:
        total = conn.execute(f"SELECT count(*) FROM {source} WHERE {where}", args).fetchone()[0]
        trash = conn.execute(f"SELECT count(*) FROM {source} WHERE m.deleted_at IS NOT NULL").fetchone()[0]
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        rows = conn.execute(f"SELECT r.payload_json FROM {source} WHERE {where} ORDER BY coalesce(m.updated_at,r.submitted_at) DESC,r.response_id DESC LIMIT ? OFFSET ?",
                            args + [page_size, (page-1)*page_size]).fetchall()
    return {"items": records("responses", ([json.loads(row[0]) for row in rows], "response_id", "response_id")),
            "total": total, "page": page, "pages": pages, "page_size": page_size, "trash_count": trash}
