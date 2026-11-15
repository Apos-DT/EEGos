"""被试端：打开链接、播放素材、填答、回看本轮作答。

这一组接口**必须保持公开**（被试扫码即用，没有账号）。因此它们不参与管理端
的 token 校验，也不会返回任何跨会话数据：``result`` 会先校验会话确实属于该
token 对应的问卷。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from starlette.concurrency import run_in_threadpool

from .. import survey_meta
from ..common import media_response, templates
from ..questionnaire import SchemaError
from ..schemas import ExperimentResponseRequest, PublicStartRequest, SchemaAnswersRequest
from ..surveys import (
    get_schema,
    infer_kind,
    public_media,
    public_submit,
    start_response,
    submit_schema_answers,
    survey_by_token,
    validate_public_session,
)

router = APIRouter()


@router.get("/q/{token}", response_class=HTMLResponse)
async def public_survey_page(request: Request, token: str) -> HTMLResponse:
    try:
        survey = await run_in_threadpool(survey_by_token, token)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # 历史导入问卷是归档证据，不对外发布：链接直接收回
    if survey.get("status") == "archived":
        raise HTTPException(status_code=404, detail="问卷链接不存在")
    return templates.TemplateResponse(
        request=request,
        name="public_survey.html",
        context={
            "survey": survey, "token": token, "now": datetime.now(),
            # 旧版问卷没有 schema，前端会回退到固定量表表单
            "schema": survey.get("schema") or [],
        },
    )


@router.get("/q/{token}/media/{session_id}")
async def public_media_file(token: str, session_id: str, request: Request) -> Response:
    try:
        path, media_type = public_media(token, session_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return media_response(path, request, media_type)


@router.get("/api/public/surveys/{token}")
async def api_public_survey(token: str) -> dict[str, Any]:
    try:
        survey = await run_in_threadpool(survey_by_token, token)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if survey.get("status") == "archived":
        raise HTTPException(status_code=404, detail="问卷链接不存在")
    return {
        "id": survey["id"],
        "title": survey["title"],
        "description": survey.get("description", ""),
        "status": survey.get("status", "open"),
        "n_materials": len(survey.get("materials", [])),
        "kind": infer_kind(survey),
        "schema_version": int(survey.get("schema_version", 1) or 1),
        # 旧版问卷返回空 schema，公开页会回退到固定量表表单
        "schema": survey.get("schema") or [],
    }


@router.post("/api/public/surveys/{token}/sessions")
async def api_public_start(token: str, payload: PublicStartRequest) -> dict[str, Any]:
    try:
        session = await run_in_threadpool(
            start_response,
            token,
            payload.participant_code,
            payload.age,
            payload.gender,
            payload.sleep_hours,
            payload.fatigue,
            payload.mood,
            payload.consent,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"session": session}


@router.post("/api/public/surveys/{token}/sessions/{session_id}/responses")
async def api_public_submit(token: str, session_id: str, payload: ExperimentResponseRequest) -> dict[str, Any]:
    try:
        session = await run_in_threadpool(public_submit, token, session_id, payload.model_dump())
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"session": session}


@router.post("/api/public/surveys/{token}/sessions/{session_id}/answers")
async def api_public_schema_submit(
    token: str,
    session_id: str,
    payload: SchemaAnswersRequest,
    request: Request,
) -> dict[str, Any]:
    """自定义量表答卷提交；IP 在仓库内只保留地区与不可逆哈希。"""

    client_ip = request.client.host if request.client else ""
    try:
        return await run_in_threadpool(
            submit_schema_answers,
            token,
            session_id,
            payload.answers,
            client_ip,
            payload.watch_seconds,
        )
    except (SchemaError, ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/public/surveys/{token}/sessions/{session_id}/result")
async def api_public_session_result(token: str, session_id: str) -> dict[str, Any]:
    """被试完成一轮后回看本轮逐题作答。

    仅返回该会话自己提交的答卷，并按 session 所属问卷校验，避免跨会话
    读取他人答案；归档问卷不提供公开访问。
    """

    try:
        survey = await run_in_threadpool(survey_by_token, token)
        if survey.get("status") == "archived":
            raise ValueError("问卷链接不存在")
        await run_in_threadpool(validate_public_session, token, session_id)
        records = await run_in_threadpool(
            survey_meta.responses_for_session, survey["id"], session_id
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "session_id": session_id,
        "survey": {"id": survey["id"], "title": survey.get("title", "")},
        "schema": get_schema(survey),
        "responses": records,
    }
