"""旧版现场实验会话（兼容层）。

逐题答卷、旧版固定 SAM 量表答卷和会话共用 SQLite。以下接口用于：

1. 读取历史会话（``/api/experiment/sessions*``、``/api/experiment/responses*``）；
2. 为公开问卷的媒体播放服务提供会话级视频路径（``/experiment/video``）。

被删掉的是旧版前端页面（固定量表界面），而不是数据通路——删数据通路会让
历史会话读不出来。
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from .. import survey_meta
from ..common import media_response
from ..experiment import (
    abort_session,
    create_session,
    list_sessions,
    load_session,
    public_session,
    responses_csv,
    responses_payload,
    submit_response,
    summary as experiment_summary,
    video_for_session,
)
from ..schemas import ExperimentCreateRequest, ExperimentResponseRequest

router = APIRouter()


# --- 旧页面重定向（保留 URL 可用性） --------------------------------------


@router.get("/experiment")
async def experiment_page(request: Request) -> Response:
    """旧版现场采集页已下线，统一收敛到问卷数据页。

    公开问卷的会话与旧版共用会话表，旧页面
    会把这些会话误当成「现场实验」并渲染固定量表。带 session 参数访问时
    直接定位到该轮答卷详情；旧版会话（无 survey_id）则回到总览。
    """

    session_id = request.query_params.get("session", "").strip()
    if session_id:
        try:
            session = await run_in_threadpool(load_session, session_id)
        except (FileNotFoundError, ValueError):
            session = None
        if session and session.get("survey_id"):
            survey_id = str(session["survey_id"])
            records = await run_in_threadpool(
                survey_meta.responses_for_session, survey_id, session_id
            )
            params = {"survey_id": survey_id, "session_id": session_id, "tab": "responses"}
            if records:
                params["response_id"] = str(records[-1]["response_id"])
            return RedirectResponse(f"/survey-data?{urlencode(params)}", status_code=302)
    return RedirectResponse("/survey-data", status_code=302)


@router.get("/responses")
async def responses_page() -> Response:
    """旧版「实验问卷」统计页已下线；逐题答卷统一在问卷数据页查看。"""

    return RedirectResponse("/survey-data", status_code=302)


# --- 媒体播放 -------------------------------------------------------------


@router.get("/experiment/video/{session_id}")
@router.get("/experiment/media/{session_id}")
async def experiment_video(session_id: str, request: Request) -> Response:
    try:
        path = video_for_session(session_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return media_response(path, request, "video/mp4")


# --- 旧版会话 API ---------------------------------------------------------


@router.get("/api/experiment/sessions")
async def api_experiment_sessions() -> dict[str, Any]:
    return {"sessions": await run_in_threadpool(list_sessions), "summary": await run_in_threadpool(experiment_summary)}


@router.post("/api/experiment/sessions")
async def api_experiment_create(payload: ExperimentCreateRequest) -> dict[str, Any]:
    try:
        session = await run_in_threadpool(
            create_session,
            payload.participant_code,
            payload.limit,
            payload.age,
            payload.gender,
            payload.consent,
            payload.note,
            payload.sleep_hours,
            payload.fatigue,
            payload.mood,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"session": session}


@router.get("/api/experiment/sessions/{session_id}")
async def api_experiment_session(session_id: str) -> dict[str, Any]:
    try:
        session = await run_in_threadpool(load_session, session_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"session": public_session(session)}


@router.post("/api/experiment/sessions/{session_id}/abort")
async def api_experiment_abort(session_id: str) -> dict[str, Any]:
    try:
        session = await run_in_threadpool(abort_session, session_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"session": session}


@router.post("/api/experiment/sessions/{session_id}/responses")
async def api_experiment_response(session_id: str, payload: ExperimentResponseRequest) -> dict[str, Any]:
    try:
        session = await run_in_threadpool(submit_response, session_id, payload.model_dump())
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"session": session}


@router.get("/api/experiment/responses")
async def api_experiment_responses() -> dict[str, Any]:
    return await run_in_threadpool(responses_payload)


@router.get("/api/experiment/responses.csv")
async def api_experiment_responses_csv() -> Response:
    content = await run_in_threadpool(responses_csv)
    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="eeg_experiment_responses.csv"'},
    )
