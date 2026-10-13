# PROGRESS.md — 세션 진행 로그 (Handoff Artifact)

다음 세션의 에이전트(또는 팀원)가 이 파일과 `features.json` 만 읽고 바로 이어서 작업할 수 있도록 기록한다.
최신 세션이 위에 온다.

## 현재 상태 요약

- 하네스 핵심(PEV, Lint, Sandbox, Gate, Self-Healing, Handoff)과 A/B 평가(20케이스) 완료.
- Mock 기준: 위험 코드 방출률 대조군 85% → 하네스 0%, Self-Healing 82%, 토큰 절감 86%.
- **다음 작업**: `features.json` 의 F-16 (patch_file 방식 Self-Healing).
- **차단 요소**: Claude 실측(F-18)은 `ANTHROPIC_API_KEY` 필요, Docker(F-19)는 미설치.

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
