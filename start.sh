#!/usr/bin/env sh
# EEG-EmoStudio launcher (Linux / macOS / WSL)
set -e
cd "$(dirname "$0")"

: "${EEG_WEB_HOST:=0.0.0.0}"
: "${EEG_WEB_PORT:=8770}"
export EEG_WEB_HOST EEG_WEB_PORT

if [ -z "${EEG_WEB_TOKEN:-}" ]; then
  echo "[warn] EEG_WEB_TOKEN not set: admin pages are visible to the whole LAN."
fi

exec "${EEG_PYTHON:-python3}" -m webapp
