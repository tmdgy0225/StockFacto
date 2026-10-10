# StockFacto — 트레이딩 코드 생성 하네스

SNS·뉴스·DART 데이터를 기반으로 LLM 이 매매 전략 코드를 생성할 때, **결정론적 하네스**
(AGENTS.md 규약 · AST Static Linter · Sandbox Backtest · Quality Gate · Self-Healing)로
위험 코드의 출하를 차단하는 PEV(Plan-Execute-Verify) 파이프라인.

```
backend/                 Python 하네스 (핵심)
  harness/
    rules.yaml           규칙 단일 진실 공급원 (R-000 ~ R-007, 리스크 한도)
    collect.py           [1] 수집 (fixture / Open DART list.json)
    context.py           [2] Context Filter: DART Cross-Fact Check → VERIFIED/UNVERIFIED → 비중 상한
    plan.py              [3] PLAN: 리스크 한도 확정, 사용자 요청과의 충돌 기록
    agents/              [4] EXECUTE: Mock(결정론적) / Claude 에이전트, 프롬프트
    verify/lint.py       [5-①] AST Static Linter
    verify/sandbox*.py   [5-②] 격리 프로세스 백테스트 + 런타임 집행(fail-closed)
    verify/quality_gate  [5-③] MDD·비중 최종 판정
    pipeline.py          [6] Self-Healing 루프 (최대 5회, 진전 없음 감지 → 에스컬레이션)
    handoff.py           [7] Handoff Artifacts + 승인(@RequiresApproval) → 모의 주문 티켓
    eval.py              A/B 평가 러너 (대조군 vs 하네스)
  api/main.py            FastAPI (SSE 실시간 이벤트)
  data/cases.json        테스트 케이스 (현재 8개 → 20개로 확장 예정)
  tests/                 pytest (적대적 우회 케이스 포함)
frontend/                React + Vite 콘솔 (파이프라인 시각화, 승인, A/B 결과)
AGENTS.md                에이전트 행동 규약 (시스템 프롬프트로 주입)
```

## 실행

### 백엔드
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m pytest -q             # 테스트
.\.venv\Scripts\python -m harness.eval          # A/B 평가 (Mock)
.\.venv\Scripts\python -m uvicorn api.main:app --reload --port 8000
```

### 프론트엔드
```powershell
cd frontend
npm install --os=win32    # 전역 ~/.npmrc 에 os=linux 가 있어 Windows 에서는 이 플래그가 필요
npm run dev               # http://localhost:5173 (/api 는 8000 으로 프록시)
```
`npm run build` 후에는 백엔드가 `frontend/dist` 를 함께 서빙하므로 `http://localhost:8000` 하나로 배포할 수 있다.

### 환경 변수 (선택)
| 변수 | 용도 |
|---|---|
| `ANTHROPIC_API_KEY` | Claude 에이전트 사용 (`HARNESS_MODEL`, `HARNESS_EFFORT` 로 조정) |
| `DART_API_KEY` | 케이스에 `"live_dart": true` 일 때 Open DART 실조회 |
| `HARNESS_SANDBOX=docker` | 백테스트를 네트워크 차단 Docker 컨테이너에서 실행 (기본은 `python -I` 서브프로세스) |

## 규칙 추가 방법
1. `backend/harness/rules.yaml` 에 규칙(ID, fix_hint) 추가
2. `AGENTS.md` 표에 같은 ID 추가 (`tests/test_pipeline.py::test_agents_md_mentions_every_rule` 가 동기화 검사)
3. `verify/lint.py`(정적) 또는 `verify/sandbox_runner.py`(런타임) 또는 `verify/quality_gate.py` 에 집행 로직 추가
4. `tests/` 에 위반/우회 케이스 추가
