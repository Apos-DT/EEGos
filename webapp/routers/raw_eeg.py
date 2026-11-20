"""Local raw SEED-IV discovery, processing jobs and reproducibility records."""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from eeg_emostudio.data.raw_processing import RawConfig, inspect_raw, raw_file
from ..config import ROOT, SEED_IV_DIR, OUTPUT_DIR, invalidate
from ..jobs import manager
from ..common import job_payload
from ..services import _id_for
from ..record_store import managed

router=APIRouter(prefix="/api/eeg/raw")
EEG_PYTHON=os.environ.get("EEG_PROCESS_PYTHON",str(ROOT/".venv-eeg"/"Scripts"/"python.exe"))


class RawRequest(BaseModel):
    sessions: list[int] = Field(default_factory=lambda:[1],min_length=1,max_length=3)
    subjects: list[int] = Field(default_factory=lambda:[1],min_length=1,max_length=15)
    fs: float = Field(200,ge=100,le=5000)
    unit: Literal["uV","V"] = "uV"
    low: float = Field(1,gt=0,le=1)
    high: float = Field(75,ge=50,le=200)
    notch: float = Field(50,ge=0,le=120)
    target_fs: float = Field(200,ge=100,le=5000)
    reref: Literal["car","none"] = "car"
    window: float = Field(4,ge=.5,le=30)
    step: float = Field(4,ge=.5,le=30)
    edge: float = Field(1,ge=0,le=5)
    reject_uv: float = Field(200,ge=0,le=2000)
    flat_uv: float = Field(.1,ge=0,le=10)
    bad_channels: list[str] = Field(default_factory=list,max_length=12)
    save_windows: bool = False
    ica_mode: Literal["off","review","apply"] = "off"
    ica_components: int = Field(20,ge=2,le=40)
    ica_reference: str = Field("",max_length=64)
    ica_exclude: list[int] = Field(default_factory=list,max_length=39)
    seed: int = Field(42,ge=0,le=2**31-1)


def run_directory(run_id):
    if not re.fullmatch(r"raw-[A-Za-z0-9_-]{1,60}",run_id): raise HTTPException(404,"非法处理记录 ID")
    path=(OUTPUT_DIR/run_id).resolve()
    if not path.is_relative_to(OUTPUT_DIR.resolve()) or not (path/"eeg_report.json").exists(): raise HTTPException(404,"处理记录不存在")
    return path


def catalog():
    records=[]
    for session in (1,2,3):
        for subject in range(1,16):
            try:
                path=raw_file(SEED_IV_DIR,session,subject)
                records.append({"session":session,"subject":subject,"filename":path.name,"size_mb":round(path.stat().st_size/2**20,1)})
            except ValueError: pass
    return {"dataset":"SEED-IV","files":records,"sampling_rate":200,"n_channels":62,"ica_available":Path(EEG_PYTHON).is_file()}


@router.get("/catalog")
async def raw_catalog(): return await run_in_threadpool(catalog)


@router.get("/inspect")
async def raw_inspect(session:int=1,subject:int=1):
    if session not in (1,2,3) or not 1<=subject<=15: raise HTTPException(422,"非法会话或被试")
    try: return await run_in_threadpool(inspect_raw,SEED_IV_DIR,session,subject)
    except (ValueError,OSError) as exc: raise HTTPException(422,str(exc)) from exc


@managed("eeg_runs", id_key="run_id", title_key="display_name")
def list_runs(limit=30):
    runs=[]
    paths=sorted(OUTPUT_DIR.glob("raw-*/eeg_report.json"),key=lambda p:p.stat().st_mtime,reverse=True)
    for path in paths if limit is None else paths[:limit]:
        try:
            r=json.loads(path.read_text(encoding="utf-8"))
            runs.append({k:r.get(k) for k in ("run_id","status","started_at","finished_at","n_samples","n_trials","n_rejected","config","ica","error")})
        except (ValueError,OSError): pass
    return runs


@router.get("/runs")
async def raw_runs(): return {"runs":await run_in_threadpool(list_runs)}


@router.get("/runs/{run_id}")
async def raw_run(run_id:str):
    path=run_directory(run_id)
    r=json.loads((path/"eeg_report.json").read_text(encoding="utf-8"))
    r["dataset_id"]=_id_for(path/"features.npz") if r.get("status")=="success" and (path/"features.npz").exists() else None
    return r


@router.get("/runs/{run_id}/report", response_class=HTMLResponse)
async def raw_report_page(run_id:str):
    path=run_directory(run_id)
    if not (path/"report.html").exists(): raise HTTPException(404,"报告未生成")
    text=(path/"report.html").read_text(encoding="utf-8")
    for name in ("waveform.png","spectrum.png","ica_components.png"):
        text=text.replace(f'src="{name}"',f'src="/files/eeg/{run_id}/{name}"')
    return HTMLResponse(text)


def process_task(job,config):
    run_id=f"raw-{datetime.now():%Y%m%d-%H%M%S}-{job.id[-6:]}";output=OUTPUT_DIR/run_id
    request_file=OUTPUT_DIR/f"{run_id}.request.json"
    request_file.write_text(json.dumps({"root":str(SEED_IV_DIR),"output":str(output),"config":config},ensure_ascii=False),encoding="utf-8")
    python=EEG_PYTHON if Path(EEG_PYTHON).is_file() else sys.executable
    args=[python,"-m","eeg_emostudio.data.raw_processing","--request",str(request_file)]
    env=os.environ.copy();env.update(PYTHONUNBUFFERED="1",PYTHONIOENCODING="utf-8",OMP_NUM_THREADS="2",MKL_NUM_THREADS="2",OPENBLAS_NUM_THREADS="2")
    manager.log(job,f"SEED-IV 原始数据处理 · {run_id}")
    process=subprocess.Popen(args,cwd=str(ROOT),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace",creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    manager.bind_process(job,process.pid,output)
    log_path=OUTPUT_DIR/f"{run_id}.log"
    with log_path.open("w",encoding="utf-8",buffering=1) as log:
        for line in process.stdout: log.write(line);manager.log(job,line)
    code=process.wait()
    if code: raise RuntimeError(f"原始 EEG 处理失败（退出码 {code}），见任务日志和质量报告")
    report=json.loads((output/"eeg_report.json").read_text(encoding="utf-8"))
    invalidate("feature_datasets","raw_datasets")
    return {"kind":"raw_eeg","run_id":run_id,"report":report,"dataset_id":_id_for(output/"features.npz")}


@router.post("/process")
async def raw_process(payload:RawRequest):
    values=payload.model_dump()
    if values["ica_reference"]: values["ica_reference"]=str(run_directory(values["ica_reference"]))
    try:
        RawConfig(**values).validate()
        for session in values["sessions"]:
            for subject in values["subjects"]: raw_file(SEED_IV_DIR,session,subject)
        if payload.ica_mode!="off" and not Path(EEG_PYTHON).is_file(): raise ValueError("MNE 独立环境尚未就绪")
    except (ValueError,OSError) as exc: raise HTTPException(422,str(exc)) from exc
    job=manager.submit("eeg_raw","SEED-IV 原始 EEG 预处理",lambda item:process_task(item,values),payload.model_dump())
    return {"job":job_payload(job)}
