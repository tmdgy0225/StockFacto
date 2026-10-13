# CLAUDE.md

공통 규칙은 AGENTS.md 에 있다 (도구 간 중복 방지).

@AGENTS.md

## Claude Code 전용

- 세션 시작 시 @PROGRESS.md 와 @features.json 을 읽고 다음 작업을 확인한다.
- `backend/`, `frontend/` 하위 작업 시 각 폴더의 CLAUDE.md 가 추가로 적용된다.
- 개인 설정(답변 언어, 로컬 경로 등)은 `CLAUDE.local.md` 에 둔다 (gitignore 됨).
