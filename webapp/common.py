"""路由层共享的渲染与响应工具。

这里只放「多个 router 都要用」的东西：模板环境、页面渲染、任务序列化、
Range 媒体响应、CSV 下载、问卷读取。放在一处可以避免每个 router 各自
重复实现一遍（历史上 ``_csv_response`` 就写了两份）。
"""

from __future__ import annotations

import re
import socket
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from .content import APP_NAME, APP_SUBTITLE, APP_VERSION, DOCS, NAV, NAV_GROUPS, PAGE_META, PAGE_DESCRIPTIONS
from .surveys import load_survey

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

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


def render(request: Request, page: str, template: str, **context: Any) -> HTMLResponse:
    """统一注入 page / page_title / now，避免模板变量缺失导致 500。"""

    context.update(
        {
            "request": request,
            "page": page,
            "page_title": PAGE_META.get(page, "工作台"),
            "page_description": PAGE_DESCRIPTIONS.get(page, ""),
            "now": datetime.now(),
        }
    )
    return templates.TemplateResponse(request=request, name=template, context=context)


def job_payload(job) -> dict[str, Any]:
    return job.to_dict(include_logs=True)


def share_base(request: Request) -> str:
    """生成分享链接的基地址（优先用本机在局域网中的地址）。

    默认只监听 127.0.0.1 时拿到的是回环地址，链接只能本机打开——
    这正是「不把问卷管理端暴露到局域网」的预期行为。
    """

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        host = sock.getsockname()[0]
        sock.close()
    except Exception:
        host = request.url.hostname or "127.0.0.1"
    port = request.url.port or 8770
    return f"http://{host}:{port}"


def media_response(path: Path, request: Request, media_type: str = "video/mp4") -> Response:
    """带 Range 支持的媒体响应，保证本地大视频可以拖动进度条。"""

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


def csv_response(content: str, filename: str) -> Response:
    """问卷星导出使用 UTF-8 BOM，Excel 直接打开不乱码。"""

    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "", value)[:64] or "survey"


async def get_survey(survey_id: str) -> dict[str, Any]:
    """读取问卷，不存在则 404；供各问卷端点复用。"""

    try:
        return await run_in_threadpool(load_survey, survey_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
