#!/usr/bin/env bash
set -euo pipefail

# 初始化 Python 虚拟环境并安装服务依赖
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="python3"
if [[ -x "/root/miniconda3/bin/python" ]]; then
  PYTHON_BIN="/root/miniconda3/bin/python"
fi

PY_VER="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_MAJOR="${PY_VER%%.*}"
PY_MINOR="${PY_VER##*.}"
if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ]]; then
  echo "错误: 需要 Python >= 3.11，当前为 $PY_VER ($PYTHON_BIN)"
  echo "建议使用 /root/miniconda3/bin/python 或安装 python3.11+"
  exit 1
fi

"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate

pip install -U pip
pip install .

echo "安装 overleaf-sync-ce（CE 双向同步依赖）..."
pip install overleaf-sync-ce

echo "完成。请执行：source .venv/bin/activate && overleaf-ce-mcp"
