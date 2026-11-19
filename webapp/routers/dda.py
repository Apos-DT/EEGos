"""API entry point for the external DDA reproduction sidecar."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException

from ..common import job_payload
from ..integrations.dda import run_dda
from ..jobs import manager
from ..schemas import DDARequest

router = APIRouter()


@router.post("/api/integrations/dda/run")
async def api_dda_run(payload: DDARequest) -> dict[str, Any]:
    if payload.setting == "cross-session" and payload.target_subject:
        raise HTTPException(status_code=422, detail="跨 session 协议按整次 session 留出，不接受 target_subject")
    if payload.algorithm == "SDDA" and payload.target_labeled_trials < 1:
        raise HTTPException(status_code=422, detail="SDDA 至少需要一个目标域有标签 trial")
    if payload.algorithm == "SDDA" and payload.target_labeled_trials >= 24:
        raise HTTPException(status_code=422, detail="SDDA 至少需要保留一个目标域 trial 用于测试")
    params = payload.model_dump()
    setting: Literal["cross-subject", "cross-session"] = payload.setting
    job = manager.submit(
        "external_reproduction",
        f"DDA 复现 · {payload.algorithm} · {setting}",
        lambda item: run_dda(
            item,
            setting=setting,
            algorithm=payload.algorithm,
            epochs=payload.epochs,
            seed=payload.seed,
            target_labeled_trials=payload.target_labeled_trials,
            target_subject=payload.target_subject,
            target_session=payload.target_session,
            max_folds=payload.max_folds,
            batch_size=payload.batch_size,
            lr=payload.lr,
            beta=payload.beta,
            pseudo_threshold=payload.pseudo_threshold,
            eval_interval=payload.eval_interval,
        ),
        params,
    )
    return {"job": job_payload(job)}
