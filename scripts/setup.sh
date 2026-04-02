#!/usr/bin/env bash
# 交付claw — 一键安装依赖（macOS / Linux）
# 用法：在仓库根目录执行
#   bash scripts/setup.sh
# 或：npm run setup

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[交付claw] 仓库根目录: $ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[交付claw] 错误: 未找到 python3，请先安装 Python 3.11+" >&2
  exit 1
fi

PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo 0)
PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo 0)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
  echo "[交付claw] 错误: 需要 Python >= 3.11" >&2
  exit 1
fi
echo "[交付claw] Python: $(python3 --version)"

echo "[交付claw] 安装/升级 pip 并安装 nanobot（可编辑模式）..."
python3 -m pip install -U pip
python3 -m pip install -e "."

if ! command -v node >/dev/null 2>&1; then
  echo "[交付claw] 错误: 未找到 node，请先安装 Node.js LTS" >&2
  exit 1
fi
echo "[交付claw] Node: $(node -v)"

echo "[交付claw] 安装前端依赖（frontend）..."
( cd frontend && npm ci )

echo "[交付claw] 安装根目录 npm 依赖（concurrently 等）..."
npm install

if [[ ! -f frontend/.env.local ]] && [[ -f frontend/.env.local.example ]]; then
  cp frontend/.env.local.example frontend/.env.local
  echo "[交付claw] 已创建 frontend/.env.local（可按需修改 NEXT_PUBLIC_*）"
fi

echo ""
echo "[交付claw] 安装完成。下一步在仓库根目录执行: npm run dev"
echo "  浏览器访问: http://localhost:3000  （AGUI 后端默认 http://127.0.0.1:8765 ）"
echo "  首次使用请在界面中打开「配置中心」填写模型与 API Key。"
echo ""
