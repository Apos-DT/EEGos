"""FastAPI 应用装配。

本文件只做四件事：创建 app → 挂静态目录 → 注册访问保护 → 装载各域路由。
业务实现全部在 ``webapp/routers/`` 与 ``webapp/services.py``。

历史包袱说明：这一层原先是 1333 行的单体装配文件，85 条路由（30 个页面 +
55 个 API）全堆在一起，改一个问卷接口要跨屏查找。拆分后新增接口只需在
对应域的 router 里加一个函数，本文件不必再动。
"""

from __future__ import annotations

import logging
import secrets
import sqlite3
from contextlib import asynccontextmanager
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import accounts
from .common import BASE_DIR
from .config import ACCESS_TOKEN
from .content import APP_NAME, APP_VERSION
from .routers import ALL_ROUTERS
from .record_store import StoreError

logger = logging.getLogger(__name__)

PUBLIC_PREFIXES = ("/static/", "/q/", "/api/public/")
PUBLIC_PATHS = {"/login", "/register", "/api/health"}


async def _access_guard(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
        return await call_next(request)

    origin = request.headers.get("origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and (
        request.headers.get("sec-fetch-site") == "cross-site"
        or (origin and origin != f"{request.url.scheme}://{request.url.netloc}")
    ):
        return JSONResponse({"detail": "请从当前站点提交请求。"}, status_code=403)

    user = await run_in_threadpool(accounts.session_user, request.cookies.get(accounts.COOKIE))
    request.state.user = user
    supplied = (request.headers.get("x-access-token") or request.query_params.get("token")
                or request.cookies.get("eeg_token") or "")
    token_access = bool(ACCESS_TOKEN and secrets.compare_digest(supplied.encode(), ACCESS_TOKEN.encode()))
    if not user and not token_access:
        if path.startswith("/api/") and path != "/api/swagger":
            return JSONResponse({"detail": "请先登录 EmoStudio。"}, status_code=401)
        return RedirectResponse("/login?" + urlencode({"next": request.url.path + (
            "?" + request.url.query if request.url.query and "token" not in request.query_params else ""
        )}), status_code=303, headers={"Cache-Control": "no-store"})

    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    if token_access and request.query_params.get("token"):
        response.set_cookie("eeg_token", ACCESS_TOKEN, httponly=True, samesite="lax",
                            secure=request.url.scheme == "https", max_age=accounts.SESSION_SECONDS)
    return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .migrate import migrate_all

    await run_in_threadpool(migrate_all)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{APP_NAME} API",
        version=APP_VERSION,
        description="EEG 情绪识别数据制备与模型训练工作台的本地 API。",
        docs_url="/api/swagger",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    @app.exception_handler(StoreError)
    async def record_store_unavailable(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(sqlite3.OperationalError)
    async def database_unavailable(request, exc):
        logger.error("SQLite request failed", exc_info=exc)
        return JSONResponse({"detail": "数据库暂不可用，请稍后重试或检查服务日志。"}, status_code=503)

    for router in ALL_ROUTERS:
        app.include_router(router)
    app.middleware("http")(_access_guard)
    return app


app = create_app()
