"""素材库：浏览、筛选、预览、同步。

预览接口只允许访问**已在选材清单内**的文件：``/stimuli/preview`` 会先查清单，
``/media/preview`` 限定在受管素材目录内，两者都做路径穿越校验。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from ..common import job_payload, media_response, render
from ..config import AUDIO_DIR, VIDEO_DIR
from ..jobs import manager
from ..media import library_payload, media_path, sync_library
from ..services import stimuli_payload

router = APIRouter()


@router.get("/media", response_class=HTMLResponse)
async def media_page(request: Request) -> HTMLResponse:
    data = await run_in_threadpool(library_payload)
    return render(request, "media", "media.html", data=data)


@router.get("/stimuli", response_class=HTMLResponse)
@router.get("/selection", response_class=HTMLResponse)
async def legacy_stimuli_redirect() -> RedirectResponse:
    return RedirectResponse("/media", status_code=307)


@router.get("/media/preview/{modality}/{filename}")
@router.get("/media/file/{modality}/{filename}")
async def media_file(modality: str, filename: str, request: Request) -> Response:
    if modality not in {"video", "audio"}:
        raise HTTPException(status_code=404, detail="未知素材类型")
    safe = Path(filename).name
    if safe != filename or not safe:
        raise HTTPException(status_code=404, detail="非法文件名")
    path = media_path(modality, safe)
    if not path:
        raise HTTPException(status_code=404, detail="素材不存在")
    return media_response(path, request, "video/mp4" if modality == "video" else "audio/mpeg")


@router.get("/stimuli/preview/{modality}/{stimulus_id}")
async def stimulus_preview(modality: str, stimulus_id: str, request: Request) -> Response:
    directory = VIDEO_DIR if modality == "video" else AUDIO_DIR if modality == "audio" else None
    if directory is None:
        raise HTTPException(status_code=404, detail="未知刺激类型")
    safe_name = Path(stimulus_id).name
    if safe_name != stimulus_id or not safe_name:
        raise HTTPException(status_code=404, detail="非法刺激名")
    rows = (await run_in_threadpool(stimuli_payload))["rows"]
    allowed = {
        str(row["stimulus_id"])
        for row in rows
        if str(row.get("modality")) == modality and row.get("available")
    }
    if safe_name not in allowed:
        raise HTTPException(status_code=404, detail="刺激不在选材清单")
    path = directory / safe_name
    media_type = "video/mp4" if modality == "video" else "audio/mpeg"
    return media_response(path, request, media_type)


@router.get("/api/media")
async def api_media() -> dict[str, Any]:
    return await run_in_threadpool(library_payload)


@router.post("/api/media/sync")
async def api_media_sync() -> dict[str, Any]:
    job = manager.submit(
        "media",
        "同步素材库",
        lambda item: {"counts": sync_library()["counts"]},
        {},
    )
    return {"job": job_payload(job)}
