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

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .common import BASE_DIR
from .config import ACCESS_TOKEN
from .content import APP_NAME, APP_VERSION
from .routers import ALL_ROUTERS
from .record_store import StoreError

logger = logging.getLogger(__name__)

# 被试端与健康检查永远公开；管理端在设置了 EEG_WEB_TOKEN 时要求令牌。
PUBLIC_PREFIXES = ("/static/", "/q/", "/api/public/", "/api/health")
PUBLIC_PATHS = {"/api/swagger", "/openapi.json", "/docs/oauth2-redirect"}

_UNAUTHORIZED_PAGE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>需要访问令牌</title><style>
body{{font:14px/1.7 system-ui,sans-serif;margin:0;display:grid;place-items:center;height:100vh;color:#2c2c2a;background:#f7f7f5}}
main{{max-width:520px;padding:28px;border:1px solid #e3e3df;border-radius:12px;background:#fff}}
code{{background:#f1efe8;padding:2px 6px;border-radius:4px}}
</style></head><body><main>
<h2 style="margin:0 0 10px;font-size:16px">需要访问令牌</h2>
<p style="margin:0;color:#5f5e5a">管理端已启用访问保护。请在链接后追加
<code>?token=你的令牌</code> 访问一次，之后浏览器会记住（有效期 7 天）。</p>
</main></body></html>"""


async def _access_guard(request: Request, call_next):
    """可选的管理端访问保护。

    默认不启用（``EEG_WEB_TOKEN`` 为空），因为服务默认只监听 127.0.0.1。
    一旦把服务暴露到局域网给被试扫码，就必须设置令牌，否则任何能访问
    8770 端口的人都能看到并导出全部问卷与答卷。
    """

    path = request.url.path
    if not ACCESS_TOKEN:
        return await call_next(request)
    if path in PUBLIC_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
        return await call_next(request)

    supplied = (
        request.headers.get("x-access-token", "")
        or request.query_params.get("token", "")
        or request.cookies.get("eeg_token", "")
    )
    if not (supplied and secrets.compare_digest(supplied, ACCESS_TOKEN)):
        if path.startswith("/api/"):
            return JSONResponse(
                {"detail": "需要访问令牌：请带 X-Access-Token 请求头或 ?token= 参数"},
                status_code=401,
            )
        return HTMLResponse(_UNAUTHORIZED_PAGE, status_code=401)

    response = await call_next(request)
    # 从链接带 token 进入后写入 Cookie，后续点击导航不必重复拼参数
    if request.query_params.get("token"):
        response.set_cookie(
            "eeg_token", ACCESS_TOKEN, httponly=True, samesite="lax", max_age=7 * 24 * 3600
        )
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
    # 常驻注册：未设令牌时守卫直接放行。这样令牌逻辑可被测试覆盖，
    # 也不必为「开/关令牌」重建应用。
    app.middleware("http")(_access_guard)
    return app


app = create_app()
