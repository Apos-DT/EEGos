"""Run the local web console: ``python -m webapp``."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("EEG_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("EEG_WEB_PORT", "8770"))
    uvicorn.run("webapp.main:app", host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
