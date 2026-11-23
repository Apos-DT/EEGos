"""问卷管理：新建/编辑、量表版本、答卷数据、元数据与历史导入。

这一层只做「管理端」，被试端填答在 :mod:`.public_survey`。两者的权限边界
不同：管理端将来要加 token 保护，被试端必须保持公开。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from starlette.concurrency import run_in_threadpool

from .. import survey_meta
from ..common import csv_response, get_survey, render, safe_name, share_base
from ..questionnaire import SchemaError, schema_fingerprint
from ..schemas import ImportCommitRequest, SurveyCreateRequest, SurveyUpdateRequest
from ..media import library_payload
from ..surveys import (
    create_survey,
    get_schema,
    infer_kind,
    list_surveys,
    load_survey,
    question_templates,
    toggle_survey,
    update_survey,
)

router = APIRouter()


# --- 页面 -----------------------------------------------------------------


@router.get("/surveys", response_class=HTMLResponse)
async def surveys_page(request: Request) -> HTMLResponse:
    surveys = await run_in_threadpool(list_surveys)
    return render(request, "surveys", "surveys.html", surveys=surveys, share_base=share_base(request))


@router.get("/survey-data", response_class=HTMLResponse)
async def survey_data_page(request: Request) -> HTMLResponse:
    surveys = await run_in_threadpool(list_surveys)
    imports = await run_in_threadpool(survey_meta.list_imports)
    return render(
        request, "survey_data", "survey_data.html",
        surveys=surveys, imports=imports,
        templates=question_templates(),
        selected=request.query_params.get("survey_id", ""),
    )


@router.get("/surveys/new", response_class=HTMLResponse)
async def survey_new_page(request: Request) -> HTMLResponse:
    data = await run_in_threadpool(library_payload)
    questionnaire_templates = question_templates()
    return render(
        request, "survey_builder", "survey_builder.html",
        data=data, survey=None, questionnaire=questionnaire_templates,
        survey_schema=questionnaire_templates["templates"]["video"],
        survey_kind="video",
    )


@router.get("/surveys/{survey_id}/edit", response_class=HTMLResponse)
async def survey_edit_page(request: Request, survey_id: str) -> HTMLResponse:
    try:
        survey = await run_in_threadpool(load_survey, survey_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    data = await run_in_threadpool(library_payload)
    return render(
        request, "survey_builder", "survey_builder.html",
        data=data, survey=survey, questionnaire=question_templates(),
        survey_schema=get_schema(survey), survey_kind=infer_kind(survey),
    )


# --- 问卷增删改 -----------------------------------------------------------


@router.get("/api/surveys")
async def api_surveys() -> dict[str, Any]:
    return {"surveys": await run_in_threadpool(list_surveys)}


@router.post("/api/surveys")
async def api_survey_create(payload: SurveyCreateRequest) -> dict[str, Any]:
    try:
        survey = await run_in_threadpool(
            create_survey,
            payload.title,
            payload.description,
            payload.material_ids,
            payload.require_code,
            payload.allow_multiple,
            payload.kind,
            payload.questions,
            payload.target_n,
        )
    except (ValueError, SchemaError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"survey": survey}


@router.put("/api/surveys/{survey_id}")
async def api_survey_update(survey_id: str, payload: SurveyUpdateRequest) -> dict[str, Any]:
    try:
        survey = await run_in_threadpool(
            update_survey,
            survey_id,
            payload.title,
            payload.description,
            payload.material_ids,
            payload.questions,
            payload.target_n,
            payload.require_code,
            payload.allow_multiple,
            payload.kind,
        )
    except (ValueError, SchemaError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"survey": survey}


@router.post("/api/surveys/{survey_id}/toggle")
async def api_survey_toggle(survey_id: str) -> dict[str, Any]:
    try:
        survey = await run_in_threadpool(toggle_survey, survey_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"survey": survey}


# --- 量表与答卷 -----------------------------------------------------------


@router.get("/api/questionnaire/templates")
async def api_questionnaire_templates() -> dict[str, Any]:
    return question_templates()


@router.get("/api/surveys/{survey_id}/schema")
async def api_survey_schema(survey_id: str) -> dict[str, Any]:
    survey = await get_survey(survey_id)
    schema = get_schema(survey)
    return {
        "schema": schema,
        "schema_version": int(survey.get("schema_version", 1) or 1),
        "schema_hash": survey.get("schema_hash") or schema_fingerprint(schema),
        "schema_history": survey.get("schema_history", []),
        "kind": infer_kind(survey),
    }


@router.get("/api/surveys/{survey_id}/metadata")
async def api_survey_metadata(survey_id: str) -> dict[str, Any]:
    await get_survey(survey_id)
    try:
        return {"metadata": await run_in_threadpool(survey_meta.survey_metadata, survey_id)}
    except (SchemaError, ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/surveys/{survey_id}/quality")
async def api_survey_quality(survey_id: str) -> dict[str, Any]:
    await get_survey(survey_id)
    try:
        return {"quality": await run_in_threadpool(survey_meta.quality_report, survey_id)}
    except (SchemaError, ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/surveys/{survey_id}/responses")
async def api_survey_responses(survey_id: str, limit: int = Query(200, ge=1, le=5000)) -> dict[str, Any]:
    await get_survey(survey_id)
    return await run_in_threadpool(survey_meta.response_table, survey_id, limit)


@router.get("/api/surveys/{survey_id}/responses.csv")
async def api_survey_responses_wjx_csv(survey_id: str) -> Response:
    """导出问卷星兼容格式，可直接与历史 CSV 合并。"""

    await get_survey(survey_id)
    try:
        content = await run_in_threadpool(survey_meta.export_wjx_csv, survey_id)
    except SchemaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return csv_response(content, f"wjx_{safe_name(survey_id)}.csv")


@router.get("/api/surveys/{survey_id}/responses.clean.csv")
async def api_survey_responses_clean_csv(survey_id: str) -> Response:
    """导出分析用宽表：元数据 + 按 role 归一化的值。"""

    await get_survey(survey_id)
    content = await run_in_threadpool(survey_meta.export_clean_csv, survey_id)
    return csv_response(content, f"clean_{safe_name(survey_id)}.csv")


@router.get("/api/surveys/{survey_id}/responses/{response_id}")
async def api_survey_response_detail(survey_id: str, response_id: str) -> dict[str, Any]:
    """单份答卷详情：完整记录 + 题目定义，支持从会话链接直达。"""

    await get_survey(survey_id)
    try:
        return await run_in_threadpool(survey_meta.response_detail, survey_id, response_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# --- 历史 CSV 导入 --------------------------------------------------------


@router.post("/api/surveys/import/preview")
async def api_survey_import_preview(
    request: Request,
    filename: str = Query("问卷星导出.csv"),
    kind: str = Query(""),
) -> dict[str, Any]:
    """接收原始 CSV 字节（不依赖 multipart），返回字段映射预览。"""

    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="上传内容为空")
    try:
        preview = await run_in_threadpool(survey_meta.preview_import, body, filename, kind)
    except SchemaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"preview": preview}


@router.get("/api/surveys/imports")
async def api_survey_imports() -> dict[str, Any]:
    return {"imports": await run_in_threadpool(survey_meta.list_imports)}


@router.post("/api/surveys/import/commit")
async def api_survey_import_commit(payload: ImportCommitRequest) -> dict[str, Any]:
    try:
        return await run_in_threadpool(
            survey_meta.commit_import,
            payload.staging_id,
            payload.survey_id,
            payload.title,
            payload.description,
            payload.mark_duplicates,
        )
    except (SchemaError, ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/surveys/imports/{batch_id}/source.csv")
async def api_survey_import_source(batch_id: str) -> Response:
    batch = await run_in_threadpool(survey_meta.import_detail, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    path = survey_meta.IMPORTS_DIR / f"{batch['batch_id']}.source.csv"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="导入批次原始文件不存在")
    return FileResponse(path, media_type="text/csv; charset=utf-8", filename=path.name)
