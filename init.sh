#!/usr/bin/env bash
# StockFacto 개발 환경 초기화 (macOS / Linux / Git Bash)
#   ./init.sh
# 초기화 에이전트 패턴: 다음 세션의 에이전트/팀원이 즉시 작업 가능한 환경을 만든다.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ -x "$ROOT/backend/.venv/Scripts/python.exe" ] || [ "${OS:-}" = "Windows_NT" ]; then
  PY_BIN=".venv/Scripts/python.exe"; NPM_FLAGS="--os=win32"
else
  PY_BIN=".venv/bin/python"; NPM_FLAGS=""
fi

echo "[1/4] backend 가상환경 및 의존성"
cd "$ROOT/backend"
[ -d .venv ] || python3 -m venv .venv 2>/dev/null || python -m venv .venv
"$PY_BIN" -m pip install -q -r requirements.txt
[ -f .env ] || echo "  ! backend/.env 없음 - DART_API_KEY 를 넣어야 스냅샷 갱신이 가능합니다 (테스트는 키 없이 동작)"

echo "[2/4] frontend 의존성"
cd "$ROOT/frontend"
npm install --no-audit --no-fund $NPM_FLAGS

echo "[3/4] git pre-push 훅 활성화"
git -C "$ROOT" config core.hooksPath .githooks

echo "[4/4] Verification Command"
cd "$ROOT/backend"
"$PY_BIN" -m ruff check .
"$PY_BIN" -m pytest -q

echo
echo "완료. 다음 작업은 PROGRESS.md 와 features.json 을 확인하세요."
