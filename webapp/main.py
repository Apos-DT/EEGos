"""FastAPI application for the EEG-EmoStudio local research console."""

from __future__ import annotations

import io
import re
import socket
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import __version__
from .content import APP_NAME, APP_SUBTITLE, APP_VERSION, DOCS, MODELS, NAV, NAV_GROUPS, PAGE_META
from .eeg import list_uploads, output_for, report_for, resolve_upload, save_upload
from .experiment import (
    DISCRETE_CHOICES,
    abort_session,
    LIKERT_LABELS,
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
from .jobs import manager
from .media import library_payload, media_path, sync_library
from .surveys import (
    create_survey,
    list_surveys,
    load_survey,
    public_media,
    public_submit,
    start_response,
    survey_by_token,
    toggle_survey,
    update_survey,
)
from .services import (
    ARTIFACTS,
    AUDIT_DIR,
    DELIVERABLES_DIR,
    ROOT,
    AUDIO_DIR,
    SELECTION_DIR,
    VIDEO_DIR,
    audit_payload,
    experiments_payload,
    list_docs,
    list_experiments,
    list_feature_datasets,
    list_raw_datasets,
    merge_feature_datasets,
    overview,
    resolve_dataset,
    resolve_doc,
    resolve_experiment,
    resolve_raw,
    selection_payload,
    stimuli_payload,
    system_info,
)
from .tasks import audit_task, demo_task, eeglab_task, features_task, selection_task, training_task

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(
    title=f"{APP_NAME} API",
    version=APP_VERSION,
    description="EEG 情绪识别数据制备与模型训练工作台的本地 API。",
    docs_url="/api/swagger",
    redoc_url=None,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

templates.env.globals.update(
    app_name=APP_NAME,
    app_subtitle=APP_SUBTITLE,
    app_version=APP_VERSION,
    nav=NAV,
    nav_groups=NAV_GROUPS,
    page_meta=PAGE_META,
    docs_count=len(DOCS),
)


def _pct(value: Any, digits: int = 1) -> str:
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "—"


def _num(value: Any, digits: int = 0) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


templates.env.filters["pct"] = _pct
templates.env.filters["num"] = _num


def _render(request: Request, page: str, template: str, **context: Any) -> HTMLResponse:
    context.update(
        {
            "request": request,
            "page": page,
            "page_title": PAGE_META.get(page, "工作台"),
            "now": datetime.now(),
        }
    )
    return templates.TemplateResponse(request=request, name=template, context=context)


def _job_payload(job) -> dict[str, Any]:
    return job.to_dict(include_logs=True)


def _share_base(request: Request) -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        host = sock.getsockname()[0]
        sock.close()
    except Exception:
        host = request.url.hostname or "127.0.0.1"
    port = request.url.port or 8770
    return f"http://{host}:{port}"


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    data = await run_in_threadpool(overview)
    return _render(request, "dashboard", "dashboard.html", data=data)


@app.get("/experiment", response_class=HTMLResponse)
async def experiment_page(request: Request) -> HTMLResponse:
    data = await run_in_threadpool(experiment_summary)
    sessions = await run_in_threadpool(list_sessions)
    return _render(
        request,
        "experiment",
        "experiment.html",
        data=data,
        sessions=sessions,
        discrete_choices=DISCRETE_CHOICES,
        likert_labels=LIKERT_LABELS,
    )


@app.get("/responses", response_class=HTMLResponse)
async def responses_page(request: Request) -> HTMLResponse:
    data = await run_in_threadpool(responses_payload)
    return _render(request, "responses", "responses.html", data=data)


def _media_response(path: Path, request: Request, media_type: str = "video/mp4") -> Response:
    """Minimal HTTP Range support so large local videos can seek."""

    size = path.stat().st_size
    range_header = request.headers.get("range", "")
    if not range_header.startswith("bytes="):
        return FileResponse(
            path,
            media_type=media_type,
            headers={"Accept-Ranges": "bytes", "Content-Length": str(size)},
        )
    try:
        raw = range_header.replace("bytes=", "", 1).split(",")[0]
        start_text, end_text = raw.split("-", 1)
        start = int(start_text) if start_text else 0
        end = int(end_text) if end_text else size - 1
    except (ValueError, IndexError):
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    start = max(0, start)
    end = min(end, size - 1)
    if start > end or start >= size:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    length = end - start + 1

    def stream():
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        stream(),
        status_code=206,
        media_type=media_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
        },
    )


@app.get("/experiment/video/{session_id}")
@app.get("/experiment/media/{session_id}")
async def experiment_video(session_id: str, request: Request) -> Response:
    try:
        path = video_for_session(session_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _media_response(path, request, "video/mp4")


@app.get("/stimuli/preview/{modality}/{stimulus_id}")
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
    return _media_response(path, request, media_type)


@app.get("/media/preview/{modality}/{filename}")
@app.get("/media/file/{modality}/{filename}")
async def media_file(modality: str, filename: str, request: Request) -> Response:
    if modality not in {"video", "audio"}:
        raise HTTPException(status_code=404, detail="未知素材类型")
    safe = Path(filename).name
    if safe != filename or not safe:
        raise HTTPException(status_code=404, detail="非法文件名")
    path = media_path(modality, safe)
    if not path:
        raise HTTPException(status_code=404, detail="素材不存在")
    return _media_response(path, request, "video/mp4" if modality == "video" else "audio/mpeg")


@app.get("/q/{token}/media/{session_id}")
async def public_media_file(token: str, session_id: str, request: Request) -> Response:
    try:
        path, media_type = public_media(token, session_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _media_response(path, request, media_type)


@app.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request) -> HTMLResponse:
    data = await run_in_threadpool(audit_payload)
    jobs = [_job_payload(job) for job in manager.list(6)]
    return _render(request, "audit", "audit.html", data=data, jobs=jobs)


@app.get("/stimuli", response_class=HTMLResponse)
@app.get("/selection", response_class=HTMLResponse)
async def legacy_stimuli_redirect() -> RedirectResponse:
    return RedirectResponse("/media", status_code=307)


@app.get("/media", response_class=HTMLResponse)
async def media_page(request: Request) -> HTMLResponse:
    data = await run_in_threadpool(library_payload)
    return _render(request, "media", "media.html", data=data)


@app.get("/surveys", response_class=HTMLResponse)
async def surveys_page(request: Request) -> HTMLResponse:
    surveys = await run_in_threadpool(list_surveys)
    return _render(request, "surveys", "surveys.html", surveys=surveys, share_base=_share_base(request))


@app.get("/surveys/new", response_class=HTMLResponse)
async def survey_new_page(request: Request) -> HTMLResponse:
    data = await run_in_threadpool(library_payload)
    return _render(request, "survey_builder", "survey_builder.html", data=data, survey=None)


@app.get("/surveys/{survey_id}/edit", response_class=HTMLResponse)
async def survey_edit_page(request: Request, survey_id: str) -> HTMLResponse:
    try:
        survey = await run_in_threadpool(load_survey, survey_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    data = await run_in_threadpool(library_payload)
    return _render(request, "survey_builder", "survey_builder.html", data=data, survey=survey)


@app.get("/q/{token}", response_class=HTMLResponse)
async def public_survey_page(request: Request, token: str) -> HTMLResponse:
    try:
        survey = await run_in_threadpool(survey_by_token, token)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request=request,
        name="public_survey.html",
        context={"survey": survey, "token": token, "now": datetime.now()},
    )


@app.get("/datasets", response_class=HTMLResponse)
async def datasets_page(request: Request) -> HTMLResponse:
    datasets = await run_in_threadpool(list_feature_datasets)
    raws = await run_in_threadpool(list_raw_datasets)
    jobs = [_job_payload(job) for job in manager.list(6)]
    return _render(request, "datasets", "datasets.html", datasets=datasets, raws=raws, jobs=jobs)


@app.get("/eeg", response_class=HTMLResponse)
async def eeg_page(request: Request) -> HTMLResponse:
    uploads = await run_in_threadpool(list_uploads)
    jobs = [_job_payload(job) for job in manager.list(6)]
    return _render(request, "eeg", "eeg.html", uploads=uploads, jobs=jobs)


@app.get("/training", response_class=HTMLResponse)
async def training_page(request: Request, dataset: str | None = None) -> HTMLResponse:
    datasets = await run_in_threadpool(list_feature_datasets)
    experiments = await run_in_threadpool(list_experiments)
    return _render(
        request,
        "training",
        "training.html",
        datasets=datasets,
        experiments=experiments,
        models=MODELS,
        selected_dataset=dataset or (datasets[0]["id"] if datasets else ""),
    )


@app.get("/experiments", response_class=HTMLResponse)
async def experiments_page(request: Request) -> HTMLResponse:
    data = await run_in_threadpool(experiments_payload)
    return _render(request, "experiments", "experiments.html", data=data)


@app.get("/documents", response_class=HTMLResponse)
async def documents_page(request: Request) -> HTMLResponse:
    docs = await run_in_threadpool(list_docs)
    return _render(request, "documents", "documents.html", docs=docs)


@app.get("/system", response_class=HTMLResponse)
async def system_page(request: Request) -> HTMLResponse:
    info = await run_in_threadpool(system_info)
    data = await run_in_threadpool(overview)
    jobs = [_job_payload(job) for job in manager.list(12)]
    return _render(request, "system", "system.html", info=info, data=data, jobs=jobs)


# ---------------------------------------------------------------------------
# API: read
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION, "time": datetime.now().isoformat()}


@app.get("/api/overview")
async def api_overview() -> dict[str, Any]:
    return await run_in_threadpool(overview)


@app.get("/api/audit")
async def api_audit() -> dict[str, Any]:
    return await run_in_threadpool(audit_payload)


@app.get("/api/selection")
async def api_selection() -> dict[str, Any]:
    return await run_in_threadpool(selection_payload)


@app.get("/api/datasets")
async def api_datasets() -> dict[str, Any]:
    return {"datasets": await run_in_threadpool(list_feature_datasets)}


@app.get("/api/raw")
async def api_raw() -> dict[str, Any]:
    return {"raws": await run_in_threadpool(list_raw_datasets)}


@app.get("/api/experiments")
async def api_experiments() -> dict[str, Any]:
    return await run_in_threadpool(experiments_payload)


@app.get("/api/experiments/{run_id}")
async def api_experiment(run_id: str) -> dict[str, Any]:
    path = resolve_experiment(run_id)
    if not path:
        raise HTTPException(status_code=404, detail="实验不存在")
    import json

    metrics_path = path / "metrics.json"
    if not metrics_path.exists():
        raise HTTPException(status_code=404, detail="指标文件不存在")
    return json.loads(metrics_path.read_text(encoding="utf-8"))


@app.get("/api/experiments/{run_id}/report", response_class=HTMLResponse)
async def experiment_report(run_id: str) -> HTMLResponse:
    path = resolve_experiment(run_id)
    if not path:
        raise HTTPException(status_code=404, detail="实验不存在")
    report = path / "report.html"
    if not report.exists():
        raise HTTPException(status_code=404, detail="报告不存在")
    return HTMLResponse(report.read_text(encoding="utf-8"))


@app.get("/api/experiments/{run_id}/figure/{figure_name}")
async def experiment_figure(run_id: str, figure_name: str) -> FileResponse:
    path = resolve_experiment(run_id)
    if not path:
        raise HTTPException(status_code=404, detail="实验不存在")
    allowed = {"confusion_matrix.png", "per_subject_accuracy.png"}
    if figure_name not in allowed:
        raise HTTPException(status_code=404, detail="图片不在白名单")
    target = path / "figures" / figure_name
    if not target.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(target, media_type="image/png")


@app.get("/api/docs")
async def api_docs() -> dict[str, Any]:
    return {"docs": await run_in_threadpool(list_docs)}


@app.get("/api/system")
async def api_system() -> dict[str, Any]:
    return await run_in_threadpool(system_info)


@app.get("/api/jobs")
async def api_jobs(limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    return {"jobs": [job.to_dict(include_logs=False) for job in manager.list(limit)]}


@app.get("/api/jobs/{job_id}")
async def api_job(job_id: str) -> dict[str, Any]:
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _job_payload(job)


# ---------------------------------------------------------------------------
# API: write / jobs
# ---------------------------------------------------------------------------


class ExperimentCreateRequest(BaseModel):
    participant_code: str = Field(..., min_length=1, max_length=64)
    limit: int = Field(8, ge=1, le=40)
    age: int | None = Field(None, ge=10, le=100)
    gender: str = Field("", max_length=24)
    consent: bool = True
    note: str = Field("", max_length=500)
    sleep_hours: float | None = Field(None, ge=0, le=24)
    fatigue: int | None = Field(None, ge=1, le=5)
    mood: int | None = Field(None, ge=1, le=9)


class ExperimentResponseRequest(BaseModel):
    valence: int = Field(..., ge=1, le=9)
    arousal: int = Field(..., ge=1, le=9)
    discrete: str = Field(..., min_length=1, max_length=24)
    intensity: int = Field(..., ge=1, le=5)
    familiarity: int = Field(..., ge=1, le=5)
    previous_viewed: bool = False
    watch_seconds: int = Field(0, ge=0, le=86400)
    note: str = Field("", max_length=500)


class SurveyCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    description: str = Field("", max_length=1000)
    material_ids: list[str] = Field(..., min_length=1, max_length=240)
    require_code: bool = True
    allow_multiple: bool = True


class SurveyUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    description: str = Field("", max_length=1000)
    material_ids: list[str] | None = None


class PublicStartRequest(BaseModel):
    participant_code: str = Field(..., min_length=1, max_length=64)
    age: int | None = Field(None, ge=10, le=100)
    gender: str = Field("", max_length=24)
    sleep_hours: float | None = Field(None, ge=0, le=24)
    fatigue: int | None = Field(None, ge=1, le=5)
    mood: int | None = Field(None, ge=1, le=9)
    consent: bool = True


class EEGProcessRequest(BaseModel):
    upload_id: str
    subject: str = Field("", max_length=64)
    bandpass_low: float = Field(0.1, ge=0.1, le=45)
    bandpass_high: float = Field(70.0, ge=1, le=100)
    notch: float = Field(50.0, ge=0, le=120)
    target_fs: float = Field(200.0, ge=0, le=5000)
    reref: str = Field("car", pattern="^(none|car)$")
    epoch_start: float = Field(-0.2, ge=-5, le=0)
    epoch_end: float = Field(4.0, ge=0.5, le=20)
    reject: float = Field(150.0, ge=1, le=2000)
    event_map: str = Field("1=0,2=1,3=2,4=3", max_length=200)
    window: float = Field(1.0, ge=0.2, le=10)
    ica: bool = False


class AuditRequest(BaseModel):
    probe_media: bool = False


class SelectionRequest(BaseModel):
    per_class: int = Field(10, ge=1, le=50)
    min_grade: str = Field("D", pattern="^[SABCD]$")
    modalities: list[str] = Field(default_factory=lambda: ["video", "audio"])


class FeatureRequest(BaseModel):
    raw_id: str
    fs: float | None = Field(None, gt=0, le=5000)
    target_fs: float | None = Field(None, gt=0, le=5000)
    window: float = Field(1.0, gt=0, le=60)
    step: float | None = Field(None, gt=0, le=60)
    aggregate: str = Field("mean", pattern="^(mean|std|concat)$")
    notch: float | None = Field(50.0, ge=0, le=120)


class MergeRequest(BaseModel):
    dataset_ids: list[str] = Field(..., min_length=2, max_length=50)


class TrainRequest(BaseModel):
    dataset_id: str
    model: str = "dualview"
    setting: str = "loso"
    epochs: int = Field(40, ge=1, le=300)
    batch_size: int = Field(32, ge=1, le=512)
    lr: float = Field(1e-3, gt=0, le=1)
    seed: int = Field(42, ge=0, le=2**31 - 1)
    hidden: int = Field(32, ge=4, le=256)
    dropout: float = Field(0.25, ge=0, le=0.9)
    prototypes: int = Field(2, ge=1, le=12)
    proto_weight: float = Field(0.1, ge=0, le=10)


@app.get("/api/experiment/sessions")
async def api_experiment_sessions() -> dict[str, Any]:
    return {"sessions": await run_in_threadpool(list_sessions), "summary": await run_in_threadpool(experiment_summary)}


@app.post("/api/experiment/sessions")
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


@app.get("/api/experiment/sessions/{session_id}")
async def api_experiment_session(session_id: str) -> dict[str, Any]:
    try:
        session = await run_in_threadpool(load_session, session_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"session": public_session(session)}


@app.post("/api/experiment/sessions/{session_id}/abort")
async def api_experiment_abort(session_id: str) -> dict[str, Any]:
    try:
        session = await run_in_threadpool(abort_session, session_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"session": session}


@app.post("/api/experiment/sessions/{session_id}/responses")
async def api_experiment_response(session_id: str, payload: ExperimentResponseRequest) -> dict[str, Any]:
    try:
        session = await run_in_threadpool(submit_response, session_id, payload.model_dump())
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"session": session}


@app.get("/api/experiment/responses")
async def api_experiment_responses() -> dict[str, Any]:
    return await run_in_threadpool(responses_payload)


@app.get("/api/experiment/responses.csv")
async def api_experiment_responses_csv() -> Response:
    content = await run_in_threadpool(responses_csv)
    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="eeg_experiment_responses.csv"'},
    )


@app.post("/api/eeg/upload")
async def api_eeg_upload(request: Request, filename: str = Query("eeglab.zip")) -> dict[str, Any]:
    body = await request.body()
    try:
        summary = await run_in_threadpool(save_upload, body, filename)
    except (ValueError, FileNotFoundError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"upload": summary}


@app.get("/api/eeg/uploads")
async def api_eeg_uploads() -> dict[str, Any]:
    return {"uploads": await run_in_threadpool(list_uploads)}


@app.post("/api/eeg/process")
async def api_eeg_process(payload: EEGProcessRequest) -> dict[str, Any]:
    if payload.bandpass_high <= payload.bandpass_low:
        raise HTTPException(status_code=400, detail="高通必须大于低通")
    try:
        upload = await run_in_threadpool(resolve_upload, payload.upload_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    output = output_for(payload.upload_id)
    job = manager.submit(
        "eeg",
        f"EEG 清洗 · {upload.get('filename', payload.upload_id)}",
        lambda item: eeglab_task(
            item,
            set_path=upload["_set_path"],
            output=output,
            subject=payload.subject or upload.get("subject", ""),
            bandpass=f"{payload.bandpass_low},{payload.bandpass_high}",
            notch=payload.notch,
            target_fs=payload.target_fs,
            reref=payload.reref,
            epoch_start=payload.epoch_start,
            epoch_end=payload.epoch_end,
            reject=payload.reject,
            event_map=payload.event_map,
            window=payload.window,
            ica=payload.ica,
        ),
        payload.model_dump(),
    )
    return {"job": _job_payload(job), "output": str(output.relative_to(ROOT))}


@app.get("/api/eeg/report/{upload_id}")
async def api_eeg_report(upload_id: str) -> dict[str, Any]:
    try:
        upload = await run_in_threadpool(resolve_upload, upload_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"upload": {key: value for key, value in upload.items() if key != "_set_path"}, "report": await run_in_threadpool(report_for, upload_id)}


@app.get("/api/media")
async def api_media() -> dict[str, Any]:
    return await run_in_threadpool(library_payload)


@app.post("/api/media/sync")
async def api_media_sync() -> dict[str, Any]:
    job = manager.submit(
        "media",
        "同步素材库",
        lambda item: {"counts": sync_library()["counts"]},
        {},
    )
    return {"job": _job_payload(job)}


@app.get("/api/surveys")
async def api_surveys() -> dict[str, Any]:
    return {"surveys": await run_in_threadpool(list_surveys)}


@app.post("/api/surveys")
async def api_survey_create(payload: SurveyCreateRequest) -> dict[str, Any]:
    try:
        survey = await run_in_threadpool(
            create_survey,
            payload.title,
            payload.description,
            payload.material_ids,
            payload.require_code,
            payload.allow_multiple,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"survey": survey}


@app.put("/api/surveys/{survey_id}")
async def api_survey_update(survey_id: str, payload: SurveyUpdateRequest) -> dict[str, Any]:
    try:
        survey = await run_in_threadpool(
            update_survey,
            survey_id,
            payload.title,
            payload.description,
            payload.material_ids,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"survey": survey}


@app.post("/api/surveys/{survey_id}/toggle")
async def api_survey_toggle(survey_id: str) -> dict[str, Any]:
    try:
        survey = await run_in_threadpool(toggle_survey, survey_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"survey": survey}


@app.get("/api/public/surveys/{token}")
async def api_public_survey(token: str) -> dict[str, Any]:
    try:
        survey = await run_in_threadpool(survey_by_token, token)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "id": survey["id"],
        "title": survey["title"],
        "description": survey.get("description", ""),
        "status": survey.get("status", "open"),
        "n_materials": len(survey.get("materials", [])),
    }


@app.post("/api/public/surveys/{token}/sessions")
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


@app.post("/api/public/surveys/{token}/sessions/{session_id}/responses")
async def api_public_submit(token: str, session_id: str, payload: ExperimentResponseRequest) -> dict[str, Any]:
    try:
        session = await run_in_threadpool(public_submit, token, session_id, payload.model_dump())
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"session": session}


@app.post("/api/audit/run")
async def api_audit_run(payload: AuditRequest) -> dict[str, Any]:
    job = manager.submit(
        "audit",
        "数据审计" + ("（含媒体探测）" if payload.probe_media else ""),
        lambda item: audit_task(item, probe_media=payload.probe_media),
        payload.model_dump(),
    )
    return {"job": _job_payload(job)}


@app.post("/api/selection/run")
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
    return {"job": _job_payload(job)}


@app.post("/api/raw/upload")
async def api_raw_upload(request: Request, filename: str = Query("upload.npz")) -> dict[str, Any]:
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(body) > 300 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件超过 300 MB 限制")
    safe = re.sub(r"[^A-Za-z0-9_.\-\u4e00-\u9fff]+", "_", Path(filename).name)
    if not safe.lower().endswith(".npz"):
        safe += ".npz"
    target = ARTIFACTS.parent / "data" / "raw" / safe
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target = target.with_name(f"{target.stem}_{datetime.now():%Y%m%d%H%M%S}.npz")
    target.write_bytes(body)
    try:
        with np.load(target, allow_pickle=False) as data:
            missing = {"x", "y", "subjects"} - set(data.files)
            if missing:
                raise ValueError(f"缺少字段：{sorted(missing)}")
            shape = tuple(int(v) for v in np.asarray(data["x"]).shape)
            if len(shape) != 3:
                raise ValueError("x 必须为 (trials, channels, samples)")
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"不是合法的 raw.npz：{exc}") from exc
    from .services import list_raw_datasets

    raws = await run_in_threadpool(list_raw_datasets)
    info = next((item for item in raws if item["path"].endswith(target.name)), None)
    return {"uploaded": True, "raw": info, "path": str(target.relative_to(ARTIFACTS.parent))}


@app.post("/api/features/run")
async def api_features_run(payload: FeatureRequest) -> dict[str, Any]:
    raw_path = resolve_raw(payload.raw_id)
    if not raw_path:
        raise HTTPException(status_code=404, detail="原始数据不存在")
    stem = raw_path.stem.replace(" ", "_")
    output = ARTIFACTS.parent / "data" / "processed" / f"{stem}_features.npz"
    if output.exists():
        output = output.with_name(f"{stem}_features_{datetime.now():%Y%m%d%H%M%S}.npz")
    job = manager.submit(
        "features",
        f"DE 特征 · {raw_path.name}",
        lambda item: features_task(
            item,
            raw_path=raw_path,
            output_path=output,
            fs=payload.fs,
            target_fs=payload.target_fs,
            window=payload.window,
            step=payload.step,
            aggregate=payload.aggregate,
            notch=payload.notch,
        ),
        payload.model_dump(),
    )
    return {"job": _job_payload(job)}


@app.post("/api/datasets/merge")
async def api_datasets_merge(payload: MergeRequest) -> dict[str, Any]:
    try:
        info = await run_in_threadpool(merge_feature_datasets, payload.dataset_ids)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"dataset": info}


@app.post("/api/train/run")
async def api_train_run(payload: TrainRequest) -> dict[str, Any]:
    if payload.model not in {item["key"] for item in MODELS}:
        raise HTTPException(status_code=400, detail="未知模型")
    if payload.model == "eegnet":
        raise HTTPException(status_code=400, detail="EEGNet 需要 raw 时间序列；当前页面仅支持特征数据集")
    if payload.setting not in {"loso", "subject-dependent"}:
        raise HTTPException(status_code=400, detail="未知评估设置")
    dataset_path = resolve_dataset(payload.dataset_id)
    if not dataset_path:
        raise HTTPException(status_code=404, detail="数据集不存在")
    job = manager.submit(
        "train",
        f"训练 · {payload.model} · {payload.setting}",
        lambda item: training_task(
            item,
            dataset_path=dataset_path,
            model=payload.model,
            setting=payload.setting,
            epochs=payload.epochs,
            batch_size=payload.batch_size,
            lr=payload.lr,
            seed=payload.seed,
            hidden=payload.hidden,
            dropout=payload.dropout,
            prototypes=payload.prototypes,
            proto_weight=payload.proto_weight,
        ),
        payload.model_dump(),
    )
    return {"job": _job_payload(job)}


@app.post("/api/demo/run")
async def api_demo_run() -> dict[str, Any]:
    output = ARTIFACTS / "web_demo" / datetime.now().strftime("%Y%m%d-%H%M%S")
    job = manager.submit(
        "demo",
        "合成数据演示",
        lambda item: demo_task(item, output=output),
        {"output": str(output)},
    )
    return {"job": _job_payload(job)}


# ---------------------------------------------------------------------------
# File downloads
# ---------------------------------------------------------------------------

AUDIT_FILES = {
    "audit_summary.json",
    "audit_report.md",
    "video_ratings_clean.csv",
    "audio_ratings_clean.csv",
    "video_playback_issues.csv",
    "audio_playback_issues.csv",
    "quality_combined.csv",
}
SELECTION_FILES = {"selected_materials.csv", "selection_summary.json", "selection_report.md"}


@app.get("/files/eeg/{upload_id}/{name}")
async def download_eeg(upload_id: str, name: str) -> FileResponse:
    allowed = {
        "eeg_clean.npz": "application/octet-stream",
        "eeg_preview.png": "image/png",
        "eeg_report.json": "application/json",
        "raw.npz": "application/octet-stream",
        "features.npz": "application/octet-stream",
        "ica_components.npz": "application/octet-stream",
    }
    if name not in allowed:
        raise HTTPException(status_code=404, detail="文件不在白名单")
    path = output_for(upload_id) / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, media_type=allowed[name], filename=name)


@app.get("/files/docx/{doc_no}")
async def download_docx(doc_no: str) -> FileResponse:
    path = resolve_doc(doc_no, "docx")
    if not path:
        raise HTTPException(status_code=404, detail="文档不存在")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=path.name,
    )


@app.get("/files/pdf/{doc_no}")
async def download_pdf(doc_no: str) -> FileResponse:
    path = resolve_doc(doc_no, "pdf")
    if not path:
        raise HTTPException(status_code=404, detail="PDF 不存在")
    return FileResponse(path, media_type="application/pdf", content_disposition_type="inline")


@app.get("/files/audit/{name}")
async def download_audit(name: str) -> FileResponse:
    if name not in AUDIT_FILES:
        raise HTTPException(status_code=404, detail="文件不在白名单")
    path = AUDIT_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    media = "application/json" if name.endswith(".json") else "text/csv" if name.endswith(".csv") else "text/markdown"
    return FileResponse(path, media_type=media, filename=name)


@app.get("/files/selection/{name}")
async def download_selection(name: str) -> FileResponse:
    if name not in SELECTION_FILES:
        raise HTTPException(status_code=404, detail="文件不在白名单")
    path = SELECTION_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    media = "application/json" if name.endswith(".json") else "text/csv" if name.endswith(".csv") else "text/markdown"
    return FileResponse(path, media_type=media, filename=name)


@app.get("/files/bundle")
async def download_bundle() -> Response:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for doc in DOCS:
            for relative in (doc["docx"], f"pdf/{doc['pdf']}"):
                path = DELIVERABLES_DIR / relative
                if path.exists():
                    archive.write(path, arcname=f"EEG-EmoStudio/{relative}")
        for extra in ("README.md", "deliverables_manifest.json", "SHA256SUMS.txt"):
            path = DELIVERABLES_DIR / extra
            if path.exists():
                archive.write(path, arcname=f"EEG-EmoStudio/{extra}")
    buffer.seek(0)
    headers = {"Content-Disposition": 'attachment; filename="EEG-EmoStudio_deliverables.zip"'}
    return Response(content=buffer.getvalue(), media_type="application/zip", headers=headers)
