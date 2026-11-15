"""文件下载统一出口。

所有下载都走白名单：文件名不直接拼路径，避免 ``../`` 穿越。集中在一处
而不是分散到各业务路由，是因为「下载」的威胁模型相同，白名单漏一个就是
全盘任意读。
"""

from __future__ import annotations

import io
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from ..config import AUDIT_DIR, DELIVERABLES_DIR, SELECTION_DIR
from ..content import DOCS
from ..eeg import output_for
from ..services import resolve_doc

router = APIRouter()

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

EEG_FILES = {
    "eeg_clean.npz": "application/octet-stream",
    "eeg_preview.png": "image/png",
    "eeg_report.json": "application/json",
    "raw.npz": "application/octet-stream",
    "features.npz": "application/octet-stream",
    "ica_components.npz": "application/octet-stream",
}


@router.get("/files/eeg/{upload_id}/{name}")
async def download_eeg(upload_id: str, name: str) -> FileResponse:
    if name not in EEG_FILES:
        raise HTTPException(status_code=404, detail="文件不在白名单")
    path = output_for(upload_id) / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, media_type=EEG_FILES[name], filename=name)


@router.get("/files/docx/{doc_no}")
async def download_docx(doc_no: str) -> FileResponse:
    from ..services import resolve_doc

    path = resolve_doc(doc_no, "docx")
    if not path:
        raise HTTPException(status_code=404, detail="文档不存在")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=path.name,
    )


@router.get("/files/pdf/{doc_no}")
async def download_pdf(doc_no: str) -> FileResponse:
    from ..services import resolve_doc

    path = resolve_doc(doc_no, "pdf")
    if not path:
        raise HTTPException(status_code=404, detail="PDF 不存在")
    return FileResponse(path, media_type="application/pdf", content_disposition_type="inline")


@router.get("/files/audit/{name}")
async def download_audit(name: str) -> FileResponse:
    if name not in AUDIT_FILES:
        raise HTTPException(status_code=404, detail="文件不在白名单")
    path = AUDIT_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    media = "application/json" if name.endswith(".json") else "text/csv" if name.endswith(".csv") else "text/markdown"
    return FileResponse(path, media_type=media, filename=name)


@router.get("/files/selection/{name}")
async def download_selection(name: str) -> FileResponse:
    if name not in SELECTION_FILES:
        raise HTTPException(status_code=404, detail="文件不在白名单")
    path = SELECTION_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    media = "application/json" if name.endswith(".json") else "text/csv" if name.endswith(".csv") else "text/markdown"
    return FileResponse(path, media_type=media, filename=name)


@router.get("/files/bundle")
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
