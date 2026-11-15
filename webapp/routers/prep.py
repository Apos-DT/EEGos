"""数据制备：历史质量审计与平衡选材。

这两步是「一次性数据制备」——素材库定稿时跑一遍，产出落 ``artifacts/``。
放到独立模块是为了让 ``media.py`` 只负责日常浏览，不被批处理逻辑撑大。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from ..common import job_payload, render
from ..jobs import manager
from ..schemas import AuditRequest, SelectionRequest
from ..services import audit_payload, selection_payload
from ..tasks import audit_task, selection_task

router = APIRouter()


@router.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request) -> HTMLResponse:
    data = await run_in_threadpool(audit_payload)
    jobs = [job_payload(job) for job in manager.list(6)]
    return render(request, "audit", "audit.html", data=data, jobs=jobs)


@router.get("/api/audit")
async def api_audit() -> dict[str, Any]:
    return await run_in_threadpool(audit_payload)


@router.get("/api/selection")
async def api_selection() -> dict[str, Any]:
    return await run_in_threadpool(selection_payload)


@router.post("/api/audit/run")
async def api_audit_run(payload: AuditRequest) -> dict[str, Any]:
    job = manager.submit(
        "audit",
        "数据审计" + ("（含媒体探测）" if payload.probe_media else ""),
        lambda item: audit_task(item, probe_media=payload.probe_media),
        payload.model_dump(),
    )
    return {"job": job_payload(job)}


@router.post("/api/selection/run")
async def api_selection_run(payload: SelectionRequest) -> dict[str, Any]:
    valid = [item for item in payload.modalities if item in {"video", "audio"}]
    if not valid:
        raise HTTPException(status_code=400, detail="至少选择一个模态")
    job = manager.submit(
        "selection",
        f"平衡选材 · 每层 {payload.per_class} 条",
        lambda item: selection_task(
            item,
            per_class=payload.per_class,
            min_grade=payload.min_grade,
            modalities=",".join(valid),
        ),
        payload.model_dump(),
    )
    return {"job": job_payload(job)}
