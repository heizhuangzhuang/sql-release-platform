#!/usr/bin/env bash

set -e

# 进入脚本所在目录，避免从别的目录启动时找不到 main.py、templates、profiles.json。
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# 可以通过环境变量覆盖 uvicorn 路径：
# UVICORN_BIN=/home/your_user/.local/bin/uvicorn ./start_uvicorn.sh
UVICORN_BIN="${UVICORN_BIN:-uvicorn}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:---reload}"

if ! command -v "$UVICORN_BIN" >/dev/null 2>&1; then
  echo "启动失败：没有找到 uvicorn 命令：$UVICORN_BIN"
  echo "请先安装依赖：python3 -m pip install -r requirements.txt"
  exit 1
fi

echo "项目目录：$PROJECT_DIR"
echo "启动命令：$UVICORN_BIN main:app $RELOAD --host $HOST --port $PORT"

exec "$UVICORN_BIN" main:app $RELOAD --host "$HOST" --port "$PORT"
