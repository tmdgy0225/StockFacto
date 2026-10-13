"""에이전트 프롬프트 구성.

- harness: Strategy Agent 규약(prompts/strategy_agent.md) + 계약 + Plan + 압축 컨텍스트 + 구조화된 실패 피드백
- control: 계약 + 사용자 요청 + 원문 소스(RAG 유사). 규칙·검증 없음
대조군에도 계약은 준다. 계약이 없으면 같은 엔진에서 실행조차 못 해 비교가 불공정해지기 때문이다.
"""
from __future__ import annotations

import json

from ..config import load_strategy_rules
from ..contract import CONTRACT_DOC
from ..patch import number_lines


def harness_system() -> str:
    return load_strategy_rules()


PATCH_INSTRUCTIONS = """\
직전 코드 전체를 다시 쓰지 말고, 고칠 줄만 패치로 출력한다. 줄 번호는 아래 '직전 코드'의 번호(1부터, 양 끝 포함)를 따른다.
```json
{"patches": [
  {"op": "replace", "start": 9, "end": 9, "code": "            return Order(side=\\"buy\\", weight=ctx.max_weight, stop_loss=bar.close * 0.97)"},
  {"op": "insert", "after": 0, "code": "import math"},
  {"op": "delete", "start": 5, "end": 6}
]}
```
- code 에는 들여쓰기를 포함한 완성된 줄을 넣는다. 범위가 겹치면 안 된다.
- 설명 없이 ```json 블록 하나만 출력한다."""


def harness_user(plan: dict, context: dict, feedback: list[dict], previous_code: str | None,
                 edit_mode: str = "rewrite", memory: str | None = None) -> str:
    parts = [
        "## Plan (하네스가 확정한 제약 — 변경 불가)",
        json.dumps({k: plan[k] for k in ("symbol", "scope", "fact_status", "max_weight", "max_mdd", "stop_loss_range", "conflicts")},
                   ensure_ascii=False, indent=2),
        "## Context (DART 크로스체크 후 압축된 팩트)",
        context["compact_text"],
        "## 사용자 요청 (Plan 의 제약 안에서만 반영)",
        plan["user_request"],
    ]
    if memory:
        parts.append(memory)
    if feedback and edit_mode == "patch":
        parts += [
            "## 직전 시도 검증 실패 로그 (모든 rule_id 를 해결하는 패치를 출력)",
            json.dumps(feedback, ensure_ascii=False, indent=2),
            "## 직전 코드 (줄 번호 표시)",
            f"```\n{number_lines(previous_code or '')}\n```",
            "## 출력 형식: patch_file",
            PATCH_INSTRUCTIONS,
        ]
    elif feedback:
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
