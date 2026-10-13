# backend/CLAUDE.md — 백엔드(하네스) 전용 규칙

이 폴더의 파일을 수정할 때만 적용된다.

## Commands
- Tests: `.venv/Scripts/python -m pytest -q`
- Lint: `.venv/Scripts/python -m ruff check .` (자동 수정: `--fix`)
- 단일 전략 검증: `.venv/Scripts/python -m harness.verify <file.py> --max-weight 0.05`

## Rules
- [CRITICAL] `harness/verify/` 의 검증기는 **fail-closed** 로 작성한다. 판단할 수 없으면 통과가 아니라 위반으로 처리한다.
- [CRITICAL] 위반은 항상 `violations.violation(rule_id, stage, message, line)` 으로 만든다. rule_id 없는 에러 문자열을 에이전트에 넘기지 않는다 (피드백 품질 = Self-Healing 성공률).
- [REQUIRED] 새 rule_id 는 `rules.yaml` 과 `prompts/strategy_agent.md` 에 동시에 추가한다 (`test_strategy_rules_mention_every_rule` 가 검사).
- [REQUIRED] 네트워크가 필요한 코드(`dart.py`)는 테스트에서 호출되지 않게 한다. 테스트는 `cases.json` 스냅샷만 사용한다.
- 평가 지표를 바꾸면 `harness/eval.py` 상단 docstring 의 지표 정의도 갱신한다.

## Constraints
- **NEVER** `sandbox_runner.py` 에서 `harness` 패키지를 import 한다.
- **NEVER** `api/` 에 비즈니스 로직을 넣는다. API 는 `harness/` 를 호출만 한다.
