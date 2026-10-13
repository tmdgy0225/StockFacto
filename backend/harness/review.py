"""추론적 센서(Inferential Sensor): LLM 리뷰어가 결정론적 게이트를 통과한 코드의 의미적 문제를 경고한다.

- **차단하지 않는다.** 판정(PASSED/ESCALATED)은 바꾸지 않고, 사람이 승인할 때 참고할 경고만 trace.review 에 남긴다 (ADR-0001).
- 연산적 센서(Lint·Sandbox·Gate)가 이미 검사한 R-000~R-008 은 다시 보지 않는다.
- 켜는 법: HARNESS_REVIEWER=claude (Claude API 인증 필요). 기본은 꺼짐.
"""
from __future__ import annotations

import json
import os
from typing import Protocol

from .agents.base import AgentError

REVIEW_SYSTEM = """\
너는 트레이딩 전략 코드 리뷰어다. 이 코드는 이미 결정론적 하네스의 검사(문법, 손절선 필수, 비중 상한, MDD, 금지 함수,
계약, 손절 거리, 실행 오류)를 모두 통과했다. 그 항목들은 다시 지적하지 마라.

대신 규칙으로는 잡기 어려운 **의미적 문제**만 찾아라. 예:
- 청산 로직이 없거나 도달할 수 없음, 진입 조건이 항상 참/거짓
- Plan 의 fact_status 가 UNVERIFIED 인데 소문을 사실로 가정한 로직 (주석·reason 포함)
- 사용자 요청 중 리스크를 키우는 의도가 코드에 남아 있음
- 미래 데이터 참조(look-ahead) 의심

문제가 없으면 빈 목록을 낸다. 설명 없이 ```json 블록 하나만 출력한다:
{"warnings": [{"severity": "low|medium|high", "message": "한국어 한 문장"}]}"""


class Reviewer(Protocol):
    name: str

    def review(self, code: str, plan: dict, context: dict) -> dict: ...


class ClaudeReviewer:
    name = "claude"

    def __init__(self, model: str | None = None, client=None):
        import anthropic  # 선택 의존성

        self._anthropic = anthropic
        self.client = client or anthropic.Anthropic()
        self.model = model or os.environ.get("HARNESS_REVIEW_MODEL", os.environ.get("HARNESS_MODEL", "claude-opus-5-5"))

    def review(self, code: str, plan: dict, context: dict) -> dict:
        user = "\n\n".join([
            "## Plan", json.dumps({k: plan.get(k) for k in ("fact_status", "max_weight", "scope", "conflicts", "user_request")},
                                  ensure_ascii=False, indent=2),
            "## Context", json.dumps(context, ensure_ascii=False),
            "## 코드", f"```python\n{code}```",
        ])
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=4000,
                thinking={"type": "adaptive"},
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=REVIEW_SYSTEM,
                messages=[{"role": "user", "content": user}],
            )
        except self._anthropic.APIError as e:
            raise AgentError(f"리뷰어 호출 실패: {e}") from e
        if response.stop_reason == "refusal":
            raise AgentError("리뷰어가 요청을 거절했습니다.")
        text = "".join(b.text for b in response.content if b.type == "text")
        return {"warnings": _parse_warnings(text),
                "tokens": {"input": response.usage.input_tokens, "output": response.usage.output_tokens}}


def _parse_warnings(text: str) -> list[dict]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise AgentError("리뷰어 응답에서 JSON 을 찾을 수 없습니다.")
    data = json.loads(text[start:end + 1])
    warnings = []
    for w in data.get("warnings", []):
        severity = w.get("severity") if w.get("severity") in ("low", "medium", "high") else "low"
        if isinstance(w.get("message"), str) and w["message"].strip():
            warnings.append({"severity": severity, "message": w["message"].strip()})
    return warnings


def make_reviewer() -> Reviewer | None:
    """환경변수로 켠다. 꺼져 있거나 초기화에 실패하면 None (파이프라인은 리뷰 없이 진행)."""
    if os.environ.get("HARNESS_REVIEWER") != "claude":
        return None
    try:
        return ClaudeReviewer()
    except Exception as e:  # 패키지 미설치·인증 누락 → 리뷰만 실패로 기록하고 파이프라인은 계속
        return _UnavailableReviewer(f"리뷰어 초기화 실패: {e}")


class _UnavailableReviewer:
    name = "claude"

    def __init__(self, reason: str):
        self.reason = reason

    def review(self, code: str, plan: dict, context: dict) -> dict:
        raise AgentError(self.reason)


def run_review(reviewer: Reviewer | None, code: str, plan: dict, context: dict) -> dict:
    if reviewer is None:
        return {"status": "skipped", "warnings": []}
    try:
        return {"status": "ok", "reviewer": reviewer.name, **reviewer.review(code, plan, context)}
    except (AgentError, json.JSONDecodeError) as e:
        # 리뷰 실패는 출하 판정에 영향을 주지 않는다. 사람에게 실패 사실만 알린다.
        return {"status": "error", "reviewer": reviewer.name, "warnings": [], "error": str(e)}
