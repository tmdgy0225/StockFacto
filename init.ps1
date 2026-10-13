# StockFacto 개발 환경 초기화 (Windows PowerShell)
#   ./init.ps1
# 초기화 에이전트 패턴: 다음 세션의 에이전트/팀원이 즉시 작업 가능한 환경을 만든다.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host "[1/4] backend 가상환경 및 의존성"
Push-Location "$root\backend"
if (-not (Test-Path ".venv")) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
if (-not (Test-Path ".env")) { Write-Host "  ! backend/.env 없음 - DART_API_KEY 를 넣어야 스냅샷 갱신이 가능합니다 (테스트는 키 없이 동작)" }
Pop-Location

Write-Host "[2/4] frontend 의존성"
Push-Location "$root\frontend"
npm install --no-audit --no-fund --os=win32
Pop-Location

Write-Host "[3/4] git pre-push 훅 활성화"
git -C $root config core.hooksPath .githooks

Write-Host "[4/4] Verification Command"
Push-Location "$root\backend"
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
Pop-Location

Write-Host "`n완료. 다음 작업은 PROGRESS.md 와 features.json 을 확인하세요."
