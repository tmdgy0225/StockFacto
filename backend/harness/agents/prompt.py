"""에이전트 프롬프트 구성.

- harness: Strategy Agent 규약(prompts/strategy_agent.md) + 계약 + Plan + 압축 컨텍스트 + 구조화된 실패 피드백
- control: 계약 + 사용자 요청 + 원문 소스(RAG 유사). 규칙·검증 없음
대조군에도 계약은 준다. 계약이 없으면 같은 엔진에서 실행조차 못 해 비교가 불공정해지기 때문이다.
"""
from __future__ import annotations

import json

from ..config import load_strategy_rules
from ..contract import CONTRACT_DOC


def harness_system() -> str:
    return load_strategy_rules()


def harness_user(plan: dict, context: dict, feedback: list[dict], previous_code: str | None) -> str:
    parts = [
        "## Plan (하네스가 확정한 제약 — 변경 불가)",
        json.dumps({k: plan[k] for k in ("symbol", "scope", "fact_status", "max_weight", "max_mdd", "stop_loss_range", "conflicts")},
                   ensure_ascii=False, indent=2),
        "## Context (DART 크로스체크 후 압축된 팩트)",
        context["compact_text"],
        "## 사용자 요청 (Plan 의 제약 안에서만 반영)",
        plan["user_request"],
    ]
    if feedback:
        parts += [
            "## 직전 시도 검증 실패 로그 (모두 해결한 전체 코드를 다시 출력)",
            json.dumps(feedback, ensure_ascii=False, indent=2),
            "## 직전 코드",
            f"```python\n{previous_code}```",
        ]
    return "\n\n".join(parts)


def control_system() -> str:
    return "당신은 파이썬 트레이딩 전략 코드를 작성하는 도우미입니다.\n\n" + CONTRACT_DOC


def control_user(case: dict, context: dict) -> str:
    return f"## 참고 자료\n{context['raw_text']}\n\n## 요청\n{case['request']}"
