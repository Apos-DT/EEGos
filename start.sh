#!/usr/bin/env sh
# ---------------------------------------------------------------------------
#  EEG-EmoStudio one-click launcher (Linux / macOS / WSL).
#
#  Only locates an interpreter; everything else (dependency check, port
#  conflict, browser) is handled by scripts/launch.py so both platforms agree.
#
#  Usage:  ./start.sh [--restart] [--no-browser] [--port 8771]
# ---------------------------------------------------------------------------
set -eu
cd "$(dirname "$0")"

if [ -n "${EEG_PYTHON:-}" ]; then
  PYRUN=$EEG_PYTHON
elif [ -x ".venv/bin/python" ]; then
  PYRUN=".venv/bin/python"
elif command -v python3.12 >/dev/null 2>&1; then
  PYRUN=python3.12
elif command -v python3 >/dev/null 2>&1; then
  PYRUN=python3
elif command -v python >/dev/null 2>&1; then
  PYRUN=python
else
  echo "[error] 找不到 Python 3.10+，请安装后重试，或设置 EEG_PYTHON 指定解释器。" >&2
  exit 1
fi

exec $PYRUN scripts/launch.py "$@"
