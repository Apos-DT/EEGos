"""Read the Dashboard queue and control jobs owned by the current web process."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .. import dashboard, dataset_catalog, record_store, services, training_monitor
from ..config import OUTPUT_DIR, ROOT
from ..jobs import manager

router = APIRouter(prefix="/api/dashboard")
_ACTIVE = {"queued", "running", "cancelling", "unknown"}
_TRAINING = {"train", "external_reproduction"}


def _raw_progress(row):
    if row["kind"] != "eeg_raw" or not (output := row["runtime"].get("output")):
        return {}
    directory = (ROOT / output).resolve()
    if directory == OUTPUT_DIR.resolve() or not directory.is_relative_to(OUTPUT_DIR.resolve()):
        return {}
    try:
        data = json.loads((directory / "progress.json").read_text(encoding="utf-8"))
        done, total = data["done_trials"], data["total_trials"]
        if type(done) is int and type(total) is int and 0 <= done <= total and total > 0:
            return {"fraction": done / total, "note": f"{done} / {total} 个试次"}
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return {}


def _scopes(row, options, features):
    params = row.get("params") or {}
    source = row.get("dataset") or params.get("dataset") or ""
    feature_id = params.get("dataset_id")
    feature = features.get(str(feature_id)) or features.get(str(source))
    if not feature and isinstance(source, str) and source.lower().endswith(".npz"):
        try:
            feature = features.get(str((ROOT / source).resolve()))
        except (OSError, RuntimeError, ValueError):
            pass
    scopes = dashboard._record_scope(params, options)
    if feature:
        scopes.add(f"feature:{feature['id']}")
        source = feature.get("source")
    if row.get("kind") in {"eeg_raw", "external_reproduction"}:
        source = "SEED-IV"
    if catalog_id := dashboard._source_id(source, options):
        scopes.add(catalog_id)
    return scopes


def _queue_data(dataset):
    monitored = training_monitor.snapshot()
    tasks = {row["id"]: row for row in record_store.decorate_rows("jobs", manager.active(), title_key="title")}
    rows = []
    for child in monitored["tasks"]:
        if child["status"] not in _ACTIVE:
            continue
        job_id = child.get("job_id")
        job = tasks.pop(job_id, None)
        if job:
            rows.append({**job, "progress": child["progress"], "dataset": child["dataset"], "training": True})
        elif not job_id or ((stored := manager.get(job_id)) and stored.status in _ACTIVE):
            rows.append({**child, "can_cancel": False, "training": True})
    for job in tasks.values():
        rows.append({**job, "progress": _raw_progress(job), "training": job["kind"] in _TRAINING})

    if dataset:
        options = {item["id"]: item["name"] for item in dataset_catalog.list_source_datasets()}
        features = {}
        if any(row.get("kind") == "train" or row.get("training") for row in rows):
            for feature in services.list_feature_datasets():
                features[feature["id"]] = feature
                features[feature["path"]] = feature
                features[str((ROOT / feature["path"]).resolve())] = feature
        rows = [row for row in rows if dataset in _scopes(row, options, features)]

    rows.sort(key=lambda row: row.get("started_at") or row.get("created_at") or "", reverse=True)
    jobs = [{
        "id": row["id"],
        "job_id": row.get("job_id") or (row["id"] if "kind" in row else None),
        "title": row["title"],
        "training": row["training"],
        "status": row["status"],
        "progress": row["progress"],
        "can_cancel": row["can_cancel"],
        "cancel_reason": _cancel_reason(row),
    } for row in rows]
    return {
        "jobs": jobs,
        "running_training_count": sum(row["training"] and row["status"] in {"running", "cancelling"} for row in rows),
        "process_scan_ok": monitored["process_scan_ok"],
    }


def _cancel_reason(row):
    if row["can_cancel"]:
        return ""
    if row["status"] == "cancelling":
        return "已提交终止请求"
    if row.get("kind") == "external_reproduction" or "kind" not in row:
        return "外部进程仅提供状态与日志"
    return "当前处理阶段无法终止"


@router.get("/queue")
async def dashboard_queue(dataset: str = Query("", max_length=240)):
    return await run_in_threadpool(_queue_data, dataset)


def _observed_log(task_id):
    return next((task for task in training_monitor.snapshot(all_tasks=True)["tasks"]
                 if task["id"] == task_id and not task.get("job_id")), None)


@router.get("/queue/log")
async def dashboard_observed_log(task_id: str = Query(max_length=200)):
    task = await run_in_threadpool(_observed_log, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="没有找到该进程的训练日志。")
    return {"status": task["status"], "logs": task["logs"]}


class CancelConfirmation(BaseModel):
    confirmed: Literal[True]


@router.post("/jobs/{job_id}/cancel")
async def dashboard_cancel(job_id: str, confirmation: CancelConfirmation, request: Request):
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    origin = request.headers.get("origin")
    if media_type != "application/json" or (origin and origin != f"{request.url.scheme}://{request.url.netloc}"):
        raise HTTPException(status_code=403, detail="请从当前工作台提交终止请求。")
    status = await run_in_threadpool(manager.cancel, job_id)
    if status is None:
        raise HTTPException(status_code=409, detail="任务已结束，或当前服务无法安全终止此任务。")
    return {"status": status}
