"""One management API shared by every record list."""
from __future__ import annotations

import json
import re
import io
import zipfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from .. import record_resources as resources
from .. import record_store as store
from ..config import PROCESSED_DIR, invalidate

router = APIRouter(prefix="/api/records", tags=["统一记录管理"])


class RecordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=512)
    revision: int = Field(ge=0)
    title: str = Field("", max_length=160)
    notes: str = Field("", max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=20)


def config(resource):
    if resource not in resources.RESOURCES:
        raise HTTPException(404, "未知记录类型")
    return resources.RESOURCES[resource]


def existing(resource, record_id):
    config(resource)
    item = resources.get_record(resource, record_id)
    if item is None:
        raise HTTPException(404, "记录不存在")
    return item


@router.get("")
async def resource_definitions():
    return {"resources": resources.RESOURCES}


@router.get("/{resource}")
async def list_records(resource: str, q: str = Query("", max_length=200),
                       view: Literal["active", "trash", "all"] = "active",
                       page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    definition = config(resource)
    rows = await run_in_threadpool(resources.records, resource)
    query = q.strip().casefold()
    filtered = [row for row in rows if (
        view == "all" or bool(row["metadata"].get("deleted_at")) == (view == "trash")
    ) and (not query or query in json.dumps(row, ensure_ascii=False).casefold())]
    filtered.sort(key=lambda item: (item["updated_at"], item["id"]), reverse=True)
    pages = max(1, (len(filtered) + page_size - 1) // page_size)
    page = min(page, pages)
    return {"resource": resource, "definition": definition, "items": filtered[(page-1)*page_size:page*page_size],
            "total": len(filtered), "page": page, "pages": pages, "page_size": page_size,
            "trash_count": sum(bool(row["metadata"].get("deleted_at")) for row in rows)}


@router.get("/{resource}/item")
async def read_record(resource: str, id: str = Query(min_length=1, max_length=512)):
    return await run_in_threadpool(existing, resource, id)


def mutate(resource, payload, operation):
    item = existing(resource, payload.id)
    if operation == "delete" and item["busy"]:
        raise HTTPException(409, "任务仍在运行，结束后再移入回收站")
    if operation == "delete" and resource == "experiments":
        from ..training_monitor import snapshot
        if any(t.get("run_id") == payload.id and t.get("status") in {"running", "queued"} for t in snapshot()["tasks"]):
            raise HTTPException(409, "实验仍在运行，结束后再移入回收站")
    if operation == "edit":
        if item["metadata"].get("deleted_at"):
            raise HTTPException(409, "请先恢复记录再编辑")
        tags = list(dict.fromkeys(tag.strip() for tag in payload.tags if tag.strip()))
        if any(len(tag) > 40 for tag in tags):
            raise HTTPException(422, "每个标签最多 40 字")
        values = {"title": payload.title.strip(), "notes": payload.notes.strip(), "tags": tags}
        changes = {key:value for key,value in values.items() if key in payload.model_fields_set}
    else:
        changes = {"deleted_at": datetime.now().astimezone().isoformat(timespec="seconds") if operation == "delete" else None}
    try:
        meta = store.update(resource, payload.id, changes, payload.revision)
    except store.ConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"id": payload.id, "metadata": meta}


@router.patch("/{resource}/item")
async def edit_record(resource: str, payload: RecordChange):
    return await run_in_threadpool(mutate, resource, payload, "edit")


@router.post("/{resource}/delete")
async def delete_record(resource: str, payload: RecordChange):
    return await run_in_threadpool(mutate, resource, payload, "delete")


@router.post("/{resource}/restore")
async def restore_record(resource: str, payload: RecordChange):
    return await run_in_threadpool(mutate, resource, payload, "restore")


def save_file(resource, filename, body):
    if not body:
        raise HTTPException(422, "文件为空")
    suffix = Path(filename).suffix.lower()
    token = uuid.uuid4().hex
    if resource == "media":
        from ..media import managed_dir
        if suffix not in {".mp4", ".mp3"}:
            raise HTTPException(422, "素材仅支持 MP4 视频或 MP3 音乐")
        kind = "video" if suffix == ".mp4" else "audio"
        name = f"upload-{token}{suffix}"
        target = managed_dir(kind) / name
        record_id = f"{kind}/{name}"
    elif resource == "features":
        if suffix != ".npz":
            raise HTTPException(422, "特征数据仅支持 NPZ")
        target = PROCESSED_DIR / f"import-{token}.npz"
    elif resource == "documents":
        if suffix not in {".pdf", ".docx", ".md", ".txt"}:
            raise HTTPException(422, "文档支持 PDF、DOCX、Markdown 和 TXT")
        target = store.STORE_DIR / "uploads" / "documents" / f"{token}{suffix}"
    else:
        raise HTTPException(422, "请使用该类型的新增流程")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(body)
    try:
        if resource == "features":
            from ..services import _inspect_feature_npz
            with np.load(target, allow_pickle=False) as data:
                if not {"x", "y", "subjects"}.issubset(data.files):
                    raise HTTPException(422, "特征缺少 x / y / subjects")
                x, y, subjects = data["x"], data["y"], data["subjects"]
                if x.ndim != 3 or y.ndim != 1 or subjects.ndim != 1 or len(y) != len(x) or len(subjects) != len(x):
                    raise HTTPException(422, "特征形状或标签、被试数量不匹配")
                if not np.issubdtype(x.dtype, np.number) or np.iscomplexobj(x) or not np.isfinite(x).all():
                    raise HTTPException(422, "特征必须是有限实数")
                if not np.issubdtype(y.dtype, np.integer) or (y < 0).any():
                    raise HTTPException(422, "类别标签必须为非负整数")
            info = _inspect_feature_npz(target)
            if not info or info["n_samples"] < 1 or info["n_channels"] < 1 or info["n_features"] < 1:
                raise HTTPException(422, "特征 NPZ 需包含有效的 x / y / subjects，x 为样本×通道×特征")
            record_id = info["id"]
        elif resource == "documents":
            if suffix == ".pdf" and not body.startswith(b"%PDF-"):
                raise HTTPException(422, "不是有效的 PDF 文件")
            if suffix == ".docx":
                with zipfile.ZipFile(io.BytesIO(body)) as document:
                    if "word/document.xml" not in document.namelist():
                        raise HTTPException(422, "不是有效的 DOCX 文件")
            if suffix in {".md", ".txt"}:
                body.decode("utf-8-sig")
            record_id = f"upload-{token}"
            url = f"/api/records/documents/file/{record_id}"
            row = {"no": record_id, "title": Path(filename).stem, "desc": "本机上传文档", "category": "自建",
                   "docx_url": url if suffix == ".docx" else "", "pdf_url": url if suffix != ".docx" else "",
                   "file_key": target.name, "created_at": datetime.now().astimezone().isoformat()}
            store.register_upload(resource, record_id, row, Path(filename).name[:160])
        if resource != "documents":
            store.update(resource, record_id, {"title": Path(filename).name[:160]}, 0)
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(422, f"文件校验失败：{exc}") from exc
    except Exception:
        target.unlink(missing_ok=True)
        raise
    invalidate()
    return {"id": record_id, "uploaded": True}


@router.post("/{resource}/upload")
async def upload_record(resource: str, request: Request, filename: str = Query(max_length=200)):
    config(resource)
    limit = (20 if resource == "documents" else 300) * 1024 * 1024
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise HTTPException(413, f"文件超过 {limit // 1024 // 1024} MB")
    return await run_in_threadpool(save_file, resource, filename, bytes(body))


@router.get("/documents/file/{record_id}")
async def download_document(record_id: str):
    row = store.snapshot().get("uploads", {}).get("documents", {}).get(record_id)
    if not row or not re.fullmatch(r"[a-f0-9]{32}\.(pdf|docx|md|txt)", row.get("file_key", "")):
        raise HTTPException(404, "文档不存在")
    target = store.STORE_DIR / "uploads" / "documents" / row["file_key"]
    if not target.is_file():
        raise HTTPException(404, "文档文件不存在")
    return FileResponse(target, filename=row["title"] + target.suffix)
