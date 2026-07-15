#!/usr/bin/env bash
set -euo pipefail

# 进入脚本所在目录（类似 Java 中使用当前 jar 所在目录）
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# 连接配置现在优先在页面里维护。
# 如果项目目录下已经有旧 .env，系统首次启动时会自动迁移出一个 default 配置。

# 创建虚拟环境（隔离依赖，类似 Java 的独立运行时）
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

# 激活虚拟环境
# shellcheck disable=SC1091
source .venv/bin/activate

# 安装依赖
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

# 启动服务（默认 0.0.0.0:8000）
exec uvicorn main:app --host 0.0.0.0 --port 8000
