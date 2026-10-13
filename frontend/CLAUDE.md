# frontend/CLAUDE.md — 프론트엔드 전용 규칙

이 폴더의 파일을 수정할 때만 적용된다.

## Commands
- Dev: `npm run dev` (백엔드 8000 포트로 `/api` 프록시)
- Type check: `npx tsc --noEmit`
- Build: `npm run build` (결과물 `dist/` 는 백엔드가 함께 서빙)
- Install (Windows): `npm install --os=win32` — 전역 `~/.npmrc` 에 `os=linux` 가 있음

## Rules
- [REQUIRED] 백엔드 응답 타입은 `src/types.ts` 에만 정의하고, 백엔드 스키마가 바뀌면 함께 갱신한다.
- [REQUIRED] 모든 API 호출은 `src/api.ts` 를 거친다.
- 화면은 하네스의 판정을 **보여주기만** 한다. 검증·판정 로직을 프론트에 두지 않는다.

## Constraints
- **NEVER** `any` 타입을 사용한다.
- **NEVER** 새 UI 라이브러리를 추가한다 (의존성 추가는 승인 필요).
