#!/bin/bash
# 启动 Hy3 数学解题过程评估 Web 应用
set -e

cd "$(dirname "$0")/.."

HOST="${WEBAPP_HOST:-0.0.0.0}"
PORT="${WEBAPP_PORT:-7860}"

echo "启动 Hy3 Math Process Evaluation Web App on http://${HOST}:${PORT}"
. /path/to/venv/bin/activate
exec python3 -m uvicorn app.web_app:app --host "${HOST}" --port "${PORT}" "$@"
