"""EEG 数据制备与模型训练：上传、清洗、特征、数据集、训练、实验记录。

这一组接口的共同点是**长任务**：真正干活的是 ``tasks.py`` 派生的 CLI 子进程，
HTTP 层只负责建任务并立刻返回 job id，前端轮询 ``/api/jobs/{id}``。因此这里
不能出现同步的重计算，否则会堵住事件循环。
"""

from __future__ import annotations

import json
import re
from io import BytesIO
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from zipfile import BadZipFile

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from starlette.concurrency import run_in_threadpool
from eeg_emostudio.data.raw_npz import raw_eeg_arrays

from ..common import job_payload, render
from ..config import ARTIFACTS, PROCESSED_DIR, RAW_DIR, ROOT
from ..content import MODELS
from ..dataset_catalog import list_source_datasets
from ..eeg import list_uploads, output_for, report_for, resolve_upload, save_upload
from ..jobs import manager
from ..schemas import EEGProcessRequest, FeatureRequest, MergeRequest, TrainRequest
from ..services import (
    experiments_payload,
    list_experiments,
    list_feature_datasets,
    list_raw_datasets,
    merge_feature_datasets,
    resolve_dataset,
    resolve_experiment,
    resolve_raw,
)
from ..tasks import demo_task, eeglab_task, features_task, training_task

router = APIRouter()


# --- 页面 -----------------------------------------------------------------


@router.get("/datasets", response_class=HTMLResponse)
async def datasets_page(request: Request, tab: str = "catalog") -> HTMLResponse:
    if tab != "eeg":
        catalog = await run_in_threadpool(list_source_datasets)
        return render(request, "datasets", "datasets.html", tab="catalog", catalog=catalog)
    datasets = await run_in_threadpool(list_feature_datasets)
    raws = await run_in_threadpool(list_raw_datasets)
    jobs = [job_payload(job) for job in manager.list(6)]
    return render(request, "datasets", "datasets.html", tab="eeg", datasets=datasets, raws=raws, jobs=jobs)


@router.get("/eeg", response_class=HTMLResponse)
async def eeg_page(request: Request) -> HTMLResponse:
    uploads = await run_in_threadpool(list_uploads)
    jobs = [job_payload(job) for job in manager.list(6)]
    return render(request, "eeg", "eeg.html", uploads=uploads, jobs=jobs)


@router.get("/training", response_class=HTMLResponse)
async def training_page(request: Request, dataset: str | None = None) -> HTMLResponse:
    datasets = await run_in_threadpool(list_feature_datasets)
    experiments = await run_in_threadpool(list_experiments)
    return render(
        request,
        "training",
        "training.html",
        datasets=datasets,
        experiments=experiments,
        models=MODELS,
        selected_dataset=dataset or (datasets[0]["id"] if datasets else ""),
    )


@router.get("/experiments", response_class=HTMLResponse)
async def experiments_page(request: Request) -> HTMLResponse:
    data = await run_in_threadpool(experiments_payload)
    return render(request, "experiments", "experiments.html", data=data)


# --- 只读查询 -------------------------------------------------------------


@router.get("/api/training/monitor")
async def training_monitor() -> dict[str, Any]:
    from ..training_monitor import snapshot

    return await run_in_threadpool(snapshot)


@router.get("/api/datasets")
async def api_datasets() -> dict[str, Any]:
    return {"datasets": await run_in_threadpool(list_feature_datasets)}


@router.get("/api/datasets/catalog")
async def api_dataset_catalog() -> dict[str, Any]:
    return {"datasets": await run_in_threadpool(list_source_datasets)}


@router.get("/api/raw")
async def api_raw() -> dict[str, Any]:
    return {"raws": await run_in_threadpool(list_raw_datasets)}


@router.get("/api/experiments")
async def api_experiments() -> dict[str, Any]:
    return await run_in_threadpool(experiments_payload)


@router.get("/api/experiments/{run_id}")
async def api_experiment(run_id: str) -> dict[str, Any]:
    path = resolve_experiment(run_id)
    if not path:
        raise HTTPException(status_code=404, detail="实验不存在")
    metrics_path = path / "metrics.json"
    if not metrics_path.exists():
        raise HTTPException(status_code=404, detail="指标文件不存在")
    return json.loads(metrics_path.read_text(encoding="utf-8"))


@router.get("/api/experiments/{run_id}/report", response_class=HTMLResponse)
async def experiment_report(run_id: str) -> HTMLResponse:
    path = resolve_experiment(run_id)
    if not path:
        raise HTTPException(status_code=404, detail="实验不存在")
    from ..integrations.dda import refresh_dda_report

    await run_in_threadpool(refresh_dda_report, path)
    report = path / "report.html"
    if not report.exists():
        raise HTTPException(status_code=404, detail="报告不存在")
    return HTMLResponse(report.read_text(encoding="utf-8"))


@router.get("/api/experiments/{run_id}/figure/{figure_name}")
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


# --- EEG 上传与清洗 -------------------------------------------------------


@router.post("/api/eeg/upload")
async def api_eeg_upload(request: Request, filename: str = Query("eeglab.zip")) -> dict[str, Any]:
    body = await request.body()
    try:
        summary = await run_in_threadpool(save_upload, body, filename)
    except (ValueError, FileNotFoundError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"upload": summary}


@router.get("/api/eeg/uploads")
async def api_eeg_uploads() -> dict[str, Any]:
    return {"uploads": await run_in_threadpool(list_uploads)}


@router.post("/api/eeg/process")
async def api_eeg_process(payload: EEGProcessRequest) -> dict[str, Any]:
    if payload.bandpass_high <= payload.bandpass_low:
        raise HTTPException(status_code=400, detail="低通截止频率必须大于高通截止频率")
    try:
        upload = await run_in_threadpool(resolve_upload, payload.upload_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    output_fs = payload.target_fs or upload["fs"]
    if payload.bandpass_high >= min(upload["fs"], output_fs) / 2:
        raise HTTPException(status_code=422, detail="低通截止必须小于输入和输出采样率的 Nyquist 频率")
    if payload.window > payload.epoch_end - payload.epoch_start:
        raise HTTPException(status_code=422, detail="DE 窗口不能超过事件分段长度")
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
    return {"job": job_payload(job), "output": str(output.relative_to(ROOT))}


@router.get("/api/eeg/report/{upload_id}")
async def api_eeg_report(upload_id: str) -> dict[str, Any]:
    try:
        upload = await run_in_threadpool(resolve_upload, upload_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"upload": {key: value for key, value in upload.items() if key != "_set_path"}, "report": await run_in_threadpool(report_for, upload_id)}


# --- 原始数据 / 特征 / 训练 -----------------------------------------------


@router.post("/api/raw/upload")
async def api_raw_upload(
    request: Request, filename: str = Query("upload.npz"), eeg_confirmed: bool = False,
) -> dict[str, Any]:
    original_name = Path(filename).name
    if Path(original_name).suffix.lower() != ".npz":
        raise HTTPException(status_code=400, detail="请上传 EEG 时间序列的 .npz 文件")
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(body) > 300 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件超过 300 MB 限制")
    try:
        await run_in_threadpool(_validate_raw_upload, body, eeg_confirmed)
    except (ValueError, TypeError, OSError, BadZipFile) as exc:
        raise HTTPException(status_code=400, detail=f"不是合法的 EEG raw.npz：{exc}") from exc

    safe = re.sub(r"[^A-Za-z0-9_.\-\u4e00-\u9fff]+", "_", original_name)
    safe = f"{Path(safe).stem}.npz"
    target = RAW_DIR / safe
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target = target.with_name(f"{target.stem}_{uuid4().hex[:12]}.npz")
    # This synchronous write keeps the filename check and save in one request step.
    target.write_bytes(body)

    raws = await run_in_threadpool(list_raw_datasets)
    info = next((item for item in raws if item["path"].endswith(target.name)), None)
    return {"uploaded": True, "raw": info, "path": str(target.relative_to(ROOT))}


def _validate_raw_upload(body: bytes, eeg_confirmed: bool) -> None:
    with np.load(BytesIO(body), allow_pickle=False) as data:
        if "modality" not in data.files and not eeg_confirmed:
            raise ValueError("文件未标注模态，请确认 x 来自 EEG 导联的时间序列")
        raw_eeg_arrays(data)


@router.post("/api/features/run")
async def api_features_run(payload: FeatureRequest) -> dict[str, Any]:
    raw_path = await run_in_threadpool(resolve_raw, payload.raw_id)
    if not raw_path:
        raise HTTPException(status_code=404, detail="请从 EEG 原始文件列表选择数据")
    stem = raw_path.stem.replace(" ", "_")
    output = PROCESSED_DIR / f"{stem}_features.npz"
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
    return {"job": job_payload(job)}


@router.post("/api/datasets/merge")
async def api_datasets_merge(payload: MergeRequest) -> dict[str, Any]:
    try:
        info = await run_in_threadpool(merge_feature_datasets, payload.dataset_ids)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"dataset": info}


@router.post("/api/train/run")
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
    return {"job": job_payload(job)}


@router.post("/api/demo/run")
async def api_demo_run() -> dict[str, Any]:
    output = ARTIFACTS / "web_demo" / datetime.now().strftime("%Y%m%d-%H%M%S")
    job = manager.submit(
        "demo",
        "合成数据演示",
        lambda item: demo_task(item, output=output),
        {"output": str(output)},
    )
    return {"job": job_payload(job)}
