"""工作台首页、系统状态与任务队列查询。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from ..common import job_payload, render
from ..content import APP_NAME, APP_VERSION
from ..jobs import manager
from ..services import list_docs, overview, system_info

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    data = await run_in_threadpool(overview)
    return render(request, "dashboard", "dashboard.html", data=data)


@router.get("/system", response_class=HTMLResponse)
async def system_page(request: Request) -> HTMLResponse:
    info = await run_in_threadpool(system_info)
    data = await run_in_threadpool(overview)
    jobs = [job_payload(job) for job in manager.list(12)]
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
    return {"jobs": [job.to_dict(include_logs=False) for job in manager.list(limit)]}


@router.get("/api/jobs/{job_id}")
async def api_job(job_id: str) -> dict[str, Any]:
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job_payload(job)
