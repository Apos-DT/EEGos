"""Run the local web console: ``python -m webapp``."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("EEG_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("EEG_WEB_PORT", "8770"))
    # 开发期设置 EEG_WEB_RELOAD=1 可在改动代码/模板后自动重载，
    # 避免旧进程读新模板导致渲染变量缺失（曾使 /surveys/new 返回 500）。
    reload = os.environ.get("EEG_WEB_RELOAD", "0").strip().lower() in {"1", "true", "yes", "on"}
    uvicorn.run("webapp.main:app", host=host, port=port, reload=reload, log_level="info")


if __name__ == "__main__":
    main()
