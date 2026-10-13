# ADR-0002: 개발 에이전트 규칙과 Strategy Agent 규약을 분리한다

- 상태: 채택 (2026-10-13)

## 맥락
초기에는 Strategy Agent(런타임에 매매 전략 코드를 생성하는 LLM)의 규약을 루트 `AGENTS.md` 에 두었다.
그런데 `AGENTS.md` 는 Claude Code·Cursor 등 **코딩 도구가 개발 규칙으로 자동 로드하는 표준 파일**이다.
실제로 개발 세션에서 개발 에이전트에게 "설명 없이 python 코드 블록 하나만 출력" 같은 전략 에이전트 규칙이 주입되는 충돌이 관찰되었다.

## 결정
- 루트 `AGENTS.md`: 이 저장소를 개발하는 에이전트용 도구 공통 규칙.
- 루트 `CLAUDE.md`: `@AGENTS.md` 를 import 하고 Claude Code 전용 내용만 추가.
- `backend/CLAUDE.md`, `frontend/CLAUDE.md`: 서브디렉토리 규칙 (해당 폴더 작업 시에만 로드 → 컨텍스트 절약).
- Strategy Agent 규약: `backend/harness/prompts/strategy_agent.md` — 하네스가 런타임에 시스템 프롬프트로 주입.

## 결과
- 두 에이전트의 컨텍스트가 섞이지 않는다.
- 규약 파일의 rule_id 와 `rules.yaml` 의 동기화는 테스트로 강제한다 (문서 드리프트 방지).
