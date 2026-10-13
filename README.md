# StockFacto — 트레이딩 코드 생성 하네스

SNS·뉴스·DART 데이터를 기반으로 LLM 이 매매 전략 코드를 생성할 때, **결정론적 하네스**
(Strategy Agent 규약 · AST Static Linter · Sandbox Backtest · Quality Gate · Self-Healing)로
위험 코드의 출하를 차단하는 PEV(Plan-Execute-Verify) 파이프라인.

하네스는 두 겹으로 적용된다.

| 대상 | 하네스 |
|---|---|
| **런타임**: 매매 전략 코드를 생성하는 Strategy Agent | `strategy_agent.md` 규약, `rules.yaml`, Lint · Sandbox · Gate, Self-Healing, 승인 |
| **개발**: 이 저장소를 만드는 코딩 에이전트(Claude Code 등) | `AGENTS.md` · 계층형 `CLAUDE.md`, `PROGRESS.md` · `features.json`, ruff · pre-push 훅 · CI |

```
AGENTS.md                개발 에이전트 공통 규칙 (도구 공통 표준)
CLAUDE.md                Claude Code 진입점 (@AGENTS.md import)
PROGRESS.md              세션 진행 로그 (Handoff Artifact)
features.json            기능 목록과 완료 상태
init.ps1 / init.sh       개발 환경 초기화 (초기화 에이전트 패턴)
docs/adr/                설계 결정 기록 (ADR)
.githooks/pre-push       Shift-left 2단계: push 전 ruff·pytest·tsc
.github/workflows/ci.yml Shift-left 3단계: CI 전체 테스트 + A/B 평가
backend/                 Python 하네스 (핵심)
  CLAUDE.md              백엔드 전용 규칙
  harness/
    rules.yaml           규칙 단일 진실 공급원 (R-000 ~ R-007, 리스크 한도)
    prompts/strategy_agent.md  Strategy Agent 규약 (시스템 프롬프트로 주입)
    collect.py           [1] 수집 (가상 SNS·뉴스 + 실제 DART 스냅샷 / 실시간)
    dart.py              Open DART 클라이언트 (공시검색, 고유번호)
    snapshot.py          케이스별 실제 DART 공시를 cases.json 에 고정
    context.py           [2] Context Filter: DART Cross-Fact Check → VERIFIED/UNVERIFIED → 비중 상한
    plan.py              [3] PLAN: 리스크 한도 확정, 사용자 요청과의 충돌 기록
    agents/              [4] EXECUTE: Mock(결정론적) / Claude 에이전트, 프롬프트
    verify/lint.py       [5-①] AST Static Linter
    verify/sandbox*.py   [5-②] 격리 프로세스 백테스트 + 런타임 집행(fail-closed)
    verify/quality_gate  [5-③] MDD·비중 최종 판정
    verify/__main__.py   Verification Command (python -m harness.verify)
    pipeline.py          [6] Self-Healing 루프 (최대 5회, 진전 없음 감지 → 에스컬레이션)
    handoff.py           [7] Handoff Artifacts + 승인(@RequiresApproval) → 모의 주문 티켓
    eval.py              A/B 평가 러너 (대조군 vs 하네스)
  api/main.py            FastAPI (SSE 실시간 이벤트)
  data/cases.json        테스트 케이스 20개 (실제 상장사 + 실제 DART 스냅샷)
  tests/                 pytest (적대적 우회 케이스 포함)
frontend/                React + Vite 콘솔 (파이프라인 시각화, 승인, A/B 결과)
  CLAUDE.md              프론트엔드 전용 규칙
```

## 실행

### 한 번에 설정
```powershell
./init.ps1      # Windows  (macOS·Linux·Git Bash: ./init.sh)
```
가상환경, 의존성, pre-push 훅 활성화, 검증까지 한 번에 실행한다.

### 백엔드
```powershell
cd backend
.\.venv\Scripts\python -m pytest -q             # 테스트
.\.venv\Scripts\python -m ruff check .          # 린트
.\.venv\Scripts\python -m harness.eval          # A/B 평가 (Mock)
.\.venv\Scripts\python -m harness.verify my_strategy.py --max-weight 0.05   # 전략 파일 단독 검증
.\.venv\Scripts\python -m uvicorn api.main:app --reload --port 8000
```

### 프론트엔드
```powershell
cd frontend
npm install --os=win32    # 전역 ~/.npmrc 에 os=linux 가 있어 Windows 에서는 이 플래그가 필요
npm run dev               # http://localhost:5173 (/api 는 8000 으로 프록시)
```
`npm run build` 후에는 백엔드가 `frontend/dist` 를 함께 서빙하므로 `http://localhost:8000` 하나로 실행할 수 있다.

### 환경 변수 (선택, `backend/.env` 에 넣으면 자동 로드)
| 변수 | 용도 |
|---|---|
| `ANTHROPIC_API_KEY` | Claude 에이전트 사용 (`HARNESS_MODEL`, `HARNESS_EFFORT` 로 조정) |
| `DART_API_KEY` | Open DART 조회 (스냅샷 갱신, 실시간 모드) |
| `HARNESS_LIVE_DART=1` | 스냅샷 대신 실행 시점에 DART 를 실시간 조회 |
| `HARNESS_SANDBOX=docker` | 백테스트를 네트워크 차단 Docker 컨테이너에서 실행 (기본은 `python -I` 서브프로세스) |
| `HARNESS_REVIEWER=claude` | 통과한 코드에 LLM 리뷰어 경고 첨부 (추론적 센서, 판정에는 영향 없음) |

## 센서 구성

| 종류 | 장치 | 역할 |
|---|---|---|
| 연산적 센서 (차단) | Lint · Sandbox · Quality Gate · patch 검증 | 규칙 위반 시 출하 차단, rule_id 피드백 |
| 추론적 센서 (경고) | LLM 리뷰어 (`harness/review.py`) | 의미적 문제를 승인자에게 경고만 함 |
| 기억 | 실패 기록 (`python -m harness.failures`) | 반복된 위반을 다음 런 프롬프트에 미리 주입 |

## Shift Feedback Left

| 단계 | 장치 | 검사 |
|---|---|---|
| 1. IDE | ruff (`backend/ruff.toml`, VS Code ruff 확장) | 실시간 린트 경고 |
| 2. Pre-push | `.githooks/pre-push` | ruff 자동 수정, pytest, tsc, `.env` 유출 차단 |
| 3. CI | `.github/workflows/ci.yml` | ruff, pytest, A/B 평가 리포트(patch vs rewrite 포함), Docker 샌드박스, 프론트 빌드 |

## 테스트 데이터
| 구분 | 출처 |
|---|---|
| 회사 | 실제 상장사 (DART 고유번호로 매핑) |
| DART 공시 | **실제 Open DART 데이터** — `python -m harness.snapshot --check` 로 갱신·검증 |
| SNS·뉴스 | **테스트용 가상 시나리오** (가상 계정·가상 언론사, 실제 사실과 무관) |
| 주가 | seed 고정 가상 시계열 (패턴: 상승, 횡보, 급등 후 급락, 갭 하락) |

케이스 20개 = 실제 공시가 있는 VERIFIED 8개 + 공시 없는 가상 소문 UNVERIFIED 12개.
각 케이스의 `expected_fact_status` 와 실제 DART 판정이 다르면 `--check` 와 테스트가 실패한다.

## 규칙 추가 방법
1. `backend/harness/rules.yaml` 에 규칙(ID, fix_hint) 추가
2. `backend/harness/prompts/strategy_agent.md` 표에 같은 ID 추가 (`test_strategy_rules_mention_every_rule` 가 동기화 검사)
3. `verify/lint.py`(정적) 또는 `verify/sandbox_runner.py`(런타임) 또는 `verify/quality_gate.py` 에 집행 로직 추가
4. `tests/` 에 위반/우회 케이스 추가
