# AGENTS.md — StockFacto 개발 에이전트 규칙 (도구 공통)

> 이 저장소를 **개발하는** AI 코딩 에이전트(Claude Code, Cursor, Codex …)가 따르는 공통 규칙이다.
> 런타임에 매매 전략을 생성하는 Strategy Agent 의 규약은 별도 파일이다: `backend/harness/prompts/strategy_agent.md`

## 1. Project Overview

- **Description**: SNS·뉴스·DART 데이터 기반 트레이딩 전략 코드 생성을 결정론적 하네스(PEV 루프, Static Linter, Sandbox, Quality Gate, Self-Healing)로 통제하는 대학교 하네스 엔지니어링 프로젝트.
- **Tech Stack**: Python 3.12+ · FastAPI · PyYAML · pytest · ruff / React 18 · TypeScript 5.6 · Vite 5
- **External**: Open DART API (실제 공시), Anthropic Claude API (선택)

## 2. Directory Map

```
backend/harness/rules.yaml                 규칙의 단일 진실 공급원 (R-000~R-007, 리스크 한도)
backend/harness/prompts/strategy_agent.md  Strategy Agent 시스템 프롬프트 (rules.yaml 과 동기화)
backend/harness/pipeline.py                PEV 루프 + Self-Healing
backend/harness/verify/                    Lint · Sandbox · Quality Gate (Non-AI)
backend/harness/agents/                    Mock / Claude 에이전트
backend/data/cases.json                    테스트 케이스 20개 (실제 DART 스냅샷 포함)
backend/tests/                             pytest
frontend/src/                              React 콘솔
docs/adr/                                  설계 결정 기록
PROGRESS.md · features.json                세션 간 상태 (Handoff Artifacts)
```

## 3. Developer Commands

- Setup: `./init.ps1` (Windows) / `./init.sh` (macOS·Linux·Git Bash)
- Backend tests: `cd backend && .venv/Scripts/python -m pytest -q`
- Lint: `cd backend && .venv/Scripts/python -m ruff check .`
- A/B eval (Mock): `cd backend && .venv/Scripts/python -m harness.eval`
- DART snapshot: `cd backend && .venv/Scripts/python -m harness.snapshot --check`
- API server: `cd backend && .venv/Scripts/python -m uvicorn api.main:app --reload --port 8000`
- Frontend: `cd frontend && npm run dev` / `npm run build`

## 4. Code Style & Architecture Rules

- [CRITICAL] **검증 노드는 Non-AI 로 유지한다.** `verify/`, `context.py`, `plan.py` 에 LLM 호출을 넣지 않는다 (블루프린트 아키텍처: 결정론적 노드 ↔ 에이전트 노드 분리).
- [CRITICAL] 규칙 추가·변경은 `rules.yaml` → `strategy_agent.md` → 집행 코드(`verify/`) → 테스트 순서로 **모두** 반영한다.
- [REQUIRED] 새 위반 유형에는 반드시 우회 시도(adversarial) 테스트를 함께 추가한다.
- [REQUIRED] `sandbox_runner.py` 는 harness 패키지를 import 하지 않는 자기완결 스크립트로 유지한다 (`python -I`/Docker 에서 실행).
- Python: 타입 힌트 사용, `from __future__ import annotations`, 주석·docstring 은 한국어.
- Frontend: 함수형 컴포넌트, API 호출은 `src/api.ts`, 타입은 `src/types.ts` 에만 정의.

## 5. Strict Constraints

- **NEVER** commit `backend/.env`, API 키, `backend/runs/`, `node_modules/`.
- **NEVER** 테스트를 통과시키려고 검증 규칙을 완화하거나 테스트를 삭제·skip 하지 않는다.
- **NEVER** `cases.json` 의 `dart` 필드를 손으로 수정하지 않는다. `harness.snapshot` 으로만 갱신한다.
- **NEVER** SNS·뉴스 가상 데이터에 실존 인물·실존 언론사 이름을 쓰지 않는다 (`[가상]`, `(테스트용)` 표기 유지).
- **MUST** 작업 완료 전 Verification Command 를 실행해 통과를 확인한다.

## 6. Tools

## @Tool[Allowed]
- `read_file`, `write_file`, `run_command` (위 Developer Commands 범위)

## @Tool[Restricted]
- `delete_file` on `backend/data/`, `docs/adr/` — **NEVER**
- `git push --force`, `git reset --hard` — **NEVER**

## @RequiresApproval
- `git commit`, `git push`
- `python -m harness.eval --agent claude` (Claude API 비용 발생)
- `python -m harness.snapshot` (cases.json 의 DART 스냅샷 변경)
- 의존성 추가 (`requirements.txt`, `package.json`)

## 7. Verification Command

```
cd backend && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m pytest -q
cd frontend && npx tsc --noEmit
```
같은 검사가 pre-push 훅(`.githooks/pre-push`)과 CI(`.github/workflows/ci.yml`)에서도 자동 실행된다.

## 8. Session Protocol (상태 관리)

1. 세션 시작 시 **MUST** `PROGRESS.md` 와 `features.json` 을 먼저 읽는다.
2. 한 번에 **하나의 기능**만 구현한다 (`features.json` 의 `todo` 항목).
3. 완료 후 Verification Command 통과 → `features.json` 상태 갱신 → `PROGRESS.md` 에 세션 로그 추가.
4. 설계 결정을 내렸다면 `docs/adr/` 에 ADR 을 추가한다.
