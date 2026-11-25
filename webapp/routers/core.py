"""工作台首页、系统状态与任务队列查询。"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from starlette.concurrency import run_in_threadpool

from ..common import csv_response, job_payload, render
from ..content import APP_NAME, APP_VERSION
from ..jobs import manager
from ..services import list_docs, overview, system_info
from ..record_resources import job_records

router = APIRouter()

MER_FILTERS = (
    {"id": "all", "label": "全部"},
    {"id": "fusion", "label": "多模态融合"},
    {"id": "unimodal", "label": "单模态基线"},
    {"id": "transfer", "label": "跨域迁移 (UDDA/SDDA)"},
)


def _dashboard_view(dataset: str, kind: str):
    from ..dashboard import get_dashboard_context

    data = get_dashboard_context(dataset)
    kind = kind if kind in {item["id"] for item in MER_FILTERS} else "all"
    runs = [run for run in data["runs"] if kind == "all" or run["category"] == kind]
    return data, kind, runs


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    from ..dashboard import get_dashboard_overview
    data = await run_in_threadpool(get_dashboard_overview)
    return render(request, "dashboard", "dashboard.html", dashboard=data)


@router.get("/dashboard/comparison.csv")
async def dashboard_comparison(
    dataset: str = Query("", max_length=200), kind: str = "all",
) -> Response:
    _, _, runs = await run_in_threadpool(_dashboard_view, dataset, kind)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(("实验 ID", "数据集", "模型", "模态", "融合方式", "评估协议", "记录时间", "Accuracy", "Macro-F1", "复现备注", "合成演示"))

    def cell(value):
        text = str(value or "")
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text

    for run in runs:
        writer.writerow([
            cell(run["id"]), cell(run.get("dataset_label") or run.get("dataset")), cell(run.get("model")),
            cell("+".join(run.get("modalities") or [])), cell(run.get("fusion")),
            cell(run.get("setting_label")), cell(run.get("created_at")),
            run.get("accuracy"), run.get("macro_f1"), cell("、".join(run.get("caveats") or [])),
            "是" if run.get("is_demo") else "否",
        ])
    return csv_response(output.getvalue(), "emostudio-comparison.csv")


@router.get("/system", response_class=HTMLResponse)
async def system_page(request: Request) -> HTMLResponse:
    info = await run_in_threadpool(system_info)
    data = await run_in_threadpool(overview)
    jobs = await run_in_threadpool(job_records, 100)
    return render(request, "system", "system.html", info=info, data=data, jobs=jobs)


@router.get("/documents", response_class=HTMLResponse)
async def documents_page(request: Request) -> HTMLResponse:
    docs = await run_in_threadpool(list_docs)
    return render(request, "documents", "documents.html", docs=docs)


@router.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION, "time": datetime.now().isoformat()}


@router.get("/api/overview")
async def api_overview() -> dict[str, Any]:
    return await run_in_threadpool(overview)


@router.get("/api/docs")
async def api_docs() -> dict[str, Any]:
    return {"docs": await run_in_threadpool(list_docs)}


@router.get("/api/system")
async def api_system() -> dict[str, Any]:
    return await run_in_threadpool(system_info)


@router.get("/api/jobs")
async def api_jobs(limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    return {"jobs": await run_in_threadpool(manager.history, limit)}


@router.get("/api/jobs/{job_id}")
async def api_job(job_id: str) -> dict[str, Any]:
    job = await run_in_threadpool(manager.get, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job_payload(job)
