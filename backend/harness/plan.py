"""[3] PLAN 단계 (Init Agent 패턴): 작업 범위와 리스크 한도를 결정론적으로 확정한다.

사용자 요청이 규칙과 충돌하면(예: "100% 올인") 요청을 그대로 따르지 않고 충돌 내역을 기록해 하향 조정한다.
"""
from __future__ import annotations

import re

from .config import load_rules

_ALL_IN = re.compile(r"올인|전액|풀매수|몰빵|all[- ]?in", re.IGNORECASE)
_PERCENT = re.compile(r"(\d{1,3})\s*%")


def requested_weight(request: str) -> float | None:
    if _ALL_IN.search(request):
        return 1.0
    m = _PERCENT.search(request)
    return int(m.group(1)) / 100 if m else None


def make_plan(case: dict, context: dict) -> dict:
    risk = load_rules()["risk"]
    max_weight = context["max_weight"]
    conflicts = []
    req_w = requested_weight(case["request"])
    if req_w is not None and req_w > max_weight:
        reason = "DART 공시로 확인되지 않은 정보(Unverified Fact)" if context["fact_status"] == "UNVERIFIED" else "단일 종목 집중 한도"
        conflicts.append(f"사용자 요청 비중 {req_w:.0%} → {reason}로 인해 {max_weight:.0%} 로 하향")
    if context["fact_status"] == "UNVERIFIED":
        conflicts.append("근거 주장 중 DART 공시로 확인되지 않은 항목이 있어 보수적 전략만 허용")
    return {
        "symbol": case["symbol"],
        "scope": "단일 종목 · 단일 진입 · 롱 온리 전략",
        "user_request": case["request"],
        "fact_status": context["fact_status"],
        "max_weight": max_weight,
        "max_mdd": risk["max_mdd"],
        "stop_loss_range": [risk["stop_loss"]["min_distance"], risk["stop_loss"]["max_distance"]],
        "requested_weight": req_w,
        "conflicts": conflicts,
    }
