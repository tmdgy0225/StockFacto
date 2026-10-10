from __future__ import annotations

from dataclasses import asdict, dataclass

from .config import rule_meta


@dataclass
class Violation:
    """검증 실패 1건. Self-Healing 루프에서 에이전트에게 그대로 재주입되는 구조화 피드백."""

    rule_id: str
    stage: str  # lint | sandbox | gate
    message: str
    line: int | None = None
    fix_hint: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def violation(rule_id: str, stage: str, message: str, line: int | None = None) -> Violation:
    return Violation(rule_id, stage, message, line, rule_meta(rule_id).get("fix_hint", ""))


def fingerprint(violations: list[Violation]) -> tuple[str, ...]:
    """진전 없음(no-progress) 판정용: 위반 rule_id 조합."""
    return tuple(sorted({v.rule_id for v in violations}))
