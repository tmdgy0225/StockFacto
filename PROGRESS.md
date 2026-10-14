# PROGRESS.md — 세션 진행 로그 (Handoff Artifact)

다음 세션의 에이전트(또는 팀원)가 이 파일과 `features.json` 만 읽고 바로 이어서 작업할 수 있도록 기록한다.
최신 세션이 위에 온다.

## 현재 상태 요약

- 하네스 핵심(PEV, Lint, Sandbox, Gate, Self-Healing, Handoff)과 A/B 평가(20케이스) 완료.
- Mock 기준: 위험 코드 방출률 대조군 85% → 하네스 0%, Self-Healing 82%, 컨텍스트 토큰 절감 86%, patch_file 로 재시도 출력 토큰 65% 절감.
- 테스트 73개 통과.
- CI(backend · sandbox-docker · frontend) 전부 통과 — F-19 Docker 샌드박스 검증 완료 (커밋 51fa36b).
- 테스트 80개 통과. README 를 보고서 겸 실행 설명서로 재작성.
- **Gemini 20개 실측 완료** (README 7.3절): 위험 코드 방출률 대조군 100% → 하네스 0%, 하네스 첫 시도 통과 19/20.
- **다음 작업**: 검증 세금 사람 측정(`python -m harness.vtax`, README 7.4절), 발표 자료.

## 2026-10-14 (2)

- 첫 Gemini 20개 평가 실패: 무료 등급 모델당 하루 20회 한도 + 평가 2개 동시 실행 → 3번째 케이스부터 429 (실패 기록 F12).
- 결제(유료 등급) 적용 후 재실행 성공 (`runs/eval_report_gemini.json`, 에이전트 오류 0건).
  - 대조군: 20/20 위험(R-002 20건, R-003 7건 MDD 10~43%, R-006 6건).
  - 하네스: 20/20 통과, 첫 시도 19건. Self-Healing 은 CASE-16 1건(min() 비중 우회 → patch 로 수정)뿐이라 성공률·토큰 절감(55%)은 표본 1건.
  - Mock 의 "고집 케이스"(08, 10, 15)도 실제 Gemini 는 첫 시도 통과.
- 검증 세금 측정 도구 `harness/vtax.py` 추가, README 를 보고서 겸 실행 설명서로 정리.

## 2026-10-14

- F-18 실제 LLM: Gemini 에이전트 추가(`agents/gemini.py`, 무료 등급, 429/503 재시도). 가짜 클라이언트 테스트 5개.
  - `gemini-flash-latest` 는 간단한 질문에도 응답이 약 3분 → `gemini-3.5-flash`(수 초)로 고정.
  - CASE-01 실측: 대조군 실제 비중 100%·MDD 39.8%(R-002, R-003) → 하네스 1회 만에 통과(5%, MDD 2.2%).
- 버그 수정(실패 기록 F11): 대조군에도 하네스 비중 상한(5%)이 `ctx.max_weight` 로 주입되어 안전하게 측정되던 문제.
  대조군은 `ctx.max_weight=1.0`, 위반 판정만 실제 상한으로. Mock 대조군 위험 코드 방출률 85% → 100% 로 정정.
- 평가: 에이전트 오류(API 사용량 초과 등)는 지표에서 빼고 `errored_cases` 로 따로 보고. 케이스별 진행률 출력.
- 웹 화면 에이전트 선택에 Gemini 추가.

## 2026-10-13 (2)

- F-16 patch_file Self-Healing: `harness/patch.py`, R-008(패치 형식 위반, fail-closed), 화면에 패치 표시.
  `python -m harness.eval --compare-healing` → 재시도 출력 토큰 rewrite 3861 → patch 1363 (65% 절감), 20케이스 결과 동일. ADR-0003.
- F-17 실패 기록: Strategy Agent 런타임 기록(`harness/failures.py`, API 런에만 기록·주입) + 개발 실수 기록(`docs/failures.md`). ADR-0004.
  Mock 은 프롬프트를 읽지 않으므로 주입 효과는 Claude 실측에서만 측정 가능.
- F-18 Claude: 키 없음. 가짜 클라이언트 테스트로 요청 형식·응답 파싱·거절 처리만 검증.
- F-19 Docker: 컨테이너 보안 옵션(권한 제거, 비root, pids 제한) + 타임아웃 시 `docker kill`. CI 에 `sandbox-docker` 잡 추가 (아직 미실행).
- F-20 LLM 리뷰어: 추론적 센서, 경고만 첨부하고 판정 불변. `HARNESS_REVIEWER=claude` 로 켬. 가짜 클라이언트로 검증.

## 2026-10-13

- 강의 자료 기준으로 하네스 구조 정비.
  - Strategy Agent 규약을 `backend/harness/prompts/strategy_agent.md` 로 이동하고 강의 지시어 형식(@Tool, [CRITICAL], NEVER/MUST, Verification Command)으로 재작성.
    - 이유: 루트 `AGENTS.md` 는 코딩 도구가 개발 규칙으로 자동 로드한다. 실제로 이 세션의 개발 에이전트에 전략 에이전트 규칙이 주입되는 충돌이 관찰됨 → ADR-0002.
  - 루트 `AGENTS.md`(도구 공통 개발 규칙), `CLAUDE.md`(@import), `backend/`·`frontend/` 서브디렉토리 CLAUDE.md 추가.
  - `PROGRESS.md`, `features.json`, `init.ps1`/`init.sh` 추가 (초기화 에이전트 패턴).
  - Shift-left: ruff(IDE), `.githooks/pre-push`, `.github/workflows/ci.yml`.
  - `python -m harness.verify` Verification Command CLI 추가.
- 케이스 20개로 확장: 실제 상장사 + 실제 DART 스냅샷, SNS·뉴스는 가상 시나리오.
  - 발견: 한미반도체에 가상 수주설을 붙였으나 실제 공급계약 공시가 있어 VERIFIED 판정 → 리노공업으로 교체.
- DART API 키 연결 (`backend/.env`, gitignore).

## 2026-10-10

- 초기 구현: 백엔드 하네스, React 콘솔, Mock 에이전트, 8개 가상 케이스. GitHub 에 첫 푸시.
