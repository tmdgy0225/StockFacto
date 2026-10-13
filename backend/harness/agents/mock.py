"""결정론적 Mock Strategy Agent.

API 키 없이 하네스 전체 흐름을 재현·테스트하기 위한 가짜 LLM.
첫 시도는 케이스의 mock_profile 대로 "사용자 요청을 그대로 따른 위험한 코드"를 내고,
이후에는 **피드백으로 받은 rule_id 에 대해서만** 코드를 고친다. 따라서 Self-Healing 은
실제로 하네스 피드백 품질에 의존한다. profile.stubborn 에 있는 rule_id 는 끝까지 고치지 않는다
(고집 센 LLM → 진전 없음 감지 → 에스컬레이션 시나리오).
"""
from __future__ import annotations

import copy
import json

from ..context import estimate_tokens
from ..patch import make_patches
from .base import AgentOutput, AgentRequest

DEFAULT_PROFILE = {
    "weight": "1.0",
    "stop_pct": None,
    "imports": [],
    "extra_lines": [],
    "syntax_error": False,
    "wrong_contract": False,
    "runtime_bug": False,
    "mutate_ctx": False,
    "hold": 20,
    "stubborn": [],
}


def _apply_fix(state: dict, rule_id: str) -> None:
    if rule_id == "R-000":
        state["syntax_error"] = False
    elif rule_id == "R-001":
        if state["stop_pct"] is None:
            state["stop_pct"] = 0.03
    elif rule_id == "R-002":
        state["weight"] = "ctx.max_weight"
    elif rule_id == "R-003":
        state["weight"] = "ctx.max_weight * 0.5"
        state["stop_pct"] = 0.02
    elif rule_id == "R-004":
        state["imports"], state["extra_lines"], state["mutate_ctx"] = [], [], False
    elif rule_id == "R-005":
        state["wrong_contract"] = False
    elif rule_id == "R-006":
        state["stop_pct"] = 0.03
    elif rule_id == "R-007":
        state["runtime_bug"] = False


def render(state: dict, title: str) -> str:
    lines = list(state["imports"])
    if lines:
        lines.append("")
    lines += [
        "",
        "class Strategy:",
        f'    """{title}"""',
        "",
        "    def __init__(self):",
        "        self.entered = False",
        "        self.bars_held = 0",
        "",
        f"    def {'on_tick' if state['wrong_contract'] else 'on_bar'}(self, bar, ctx):",
    ]
    if state["syntax_error"]:
        lines.append("        if ctx.position == 0")
    lines += [f"        {e}" for e in state["extra_lines"]]
    if state["mutate_ctx"]:
        lines.append("        ctx.max_weight = 1.0")
    if state["runtime_bug"]:
        lines.append("        momentum = bar.close / prev_close - 1")
    args = ['side="buy"', f"weight={state['weight']}"]
    if state["stop_pct"] is not None:
        args.append(f"stop_loss=bar.close * {1 - state['stop_pct']:.4g}")
    args.append('reason="뉴스 기반 진입"')
    lines += [
        "        if not self.entered:",
        "            self.entered = True",
        f"            return Order({', '.join(args)})",
        "        if ctx.position > 0:",
        "            self.bars_held += 1",
        f"            if self.bars_held >= {state['hold']}:",
        '                return Order(side="sell", reason="보유 기간 만료")',
        "        return None",
    ]
    return "\n".join(lines).lstrip("\n") + "\n"


class MockAgent:
    name = "mock"

    def __init__(self, case: dict):
        self.title = case["title"]
        self.profile = {**DEFAULT_PROFILE, **case.get("mock_profile", {})}
        self.state = copy.deepcopy(self.profile)

    def generate(self, req: AgentRequest) -> AgentOutput:
        if req.attempt == 1:
            self.state = copy.deepcopy(self.profile)
        for rule_id in sorted({f["rule_id"] for f in req.feedback}):
            if rule_id not in self.profile["stubborn"]:
                _apply_fix(self.state, rule_id)
        code = render(self.state, self.title)
        input_tokens = estimate_tokens(req.system + req.user)
        if req.edit_mode == "patch" and req.previous_code is not None:
            patches = make_patches(req.previous_code, code)
            if patches:  # 고칠 게 없으면(고집 케이스) 같은 코드를 다시 내는 것과 동일하게 전체 코드로 응답
                payload = json.dumps({"patches": patches}, ensure_ascii=False)
                return AgentOutput("", input_tokens, estimate_tokens(payload), patches=patches)
        return AgentOutput(code, input_tokens, estimate_tokens(code))
