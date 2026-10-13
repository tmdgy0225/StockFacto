# PROGRESS.md — 세션 진행 로그 (Handoff Artifact)

다음 세션의 에이전트(또는 팀원)가 이 파일과 `features.json` 만 읽고 바로 이어서 작업할 수 있도록 기록한다.
최신 세션이 위에 온다.

## 현재 상태 요약

- 하네스 핵심(PEV, Lint, Sandbox, Gate, Self-Healing, Handoff)과 A/B 평가(20케이스) 완료.
- Mock 기준: 위험 코드 방출률 대조군 85% → 하네스 0%, Self-Healing 82%, 컨텍스트 토큰 절감 86%, patch_file 로 재시도 출력 토큰 65% 절감.
- 테스트 73개 통과.
- **다음 작업**: GitHub Actions 의 `sandbox-docker` 잡 결과 확인(F-19), API 키 확보 후 Claude 실측(F-18).
- **차단 요소**: F-18 은 `ANTHROPIC_API_KEY` 필요. F-19 는 로컬 Docker 없음 → CI 에서만 검증 가능.

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
