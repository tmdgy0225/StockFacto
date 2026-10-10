"""③ Quality Gate (Non-AI): 백테스트 결과에 대한 최종 출하 판정."""
from __future__ import annotations

from ..config import load_rules
from ..violations import Violation, violation
from .sandbox import SandboxResult

STAGE = "gate"


def evaluate(result: SandboxResult, max_weight: float) -> list[Violation]:
    risk = load_rules()["risk"]
    found: list[Violation] = []
    mdd = result.metrics.get("mdd")
    if mdd is not None and mdd > risk["max_mdd"]:
        found.append(violation("R-003", STAGE, f"백테스트 MDD {mdd:.1%} 가 한도 {risk['max_mdd']:.0%} 를 초과합니다."))
    used = result.metrics.get("max_weight_used", 0.0)
    if used > max_weight + 1e-9:
        found.append(violation("R-002", STAGE, f"실제 체결 비중 {used:.0%} 가 상한 {max_weight:.0%} 를 초과했습니다."))
    return found
