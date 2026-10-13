"""[7] Handoff Artifacts + @RequiresApproval.

검증을 통과한 런만 승인 대기(PENDING) 상태가 되며, 사람이 승인해야 모의(PAPER) 주문 티켓이 생성된다.
실제 증권사 주문 연동은 이 티켓을 소비하는 별도 어댑터로 붙인다(예: 모의투자 API).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .config import RUNS_DIR

if TYPE_CHECKING:
    from .pipeline import RunTrace


class ApprovalError(ValueError):
    pass


def run_dir(run_id: str):
    if not run_id.replace("-", "").isalnum():
        raise ApprovalError("invalid run id")
    return RUNS_DIR / run_id


def write_artifacts(trace: RunTrace) -> None:
    d = run_dir(trace.run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "trace.json").write_text(json.dumps(trace.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    if trace.attempts:
        (d / "strategy.py").write_text(trace.attempts[-1].code, encoding="utf-8")


def load_trace(run_id: str) -> dict | None:
    path = run_dir(run_id) / "trace.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def decide(run_id: str, decision: str, approver: str = "user") -> dict:
    trace = load_trace(run_id)
    if trace is None:
        raise ApprovalError("run not found")
    if trace["status"] != "PASSED" or trace["approval"] != "PENDING":
        raise ApprovalError(f"승인 대기 상태가 아닙니다 (status={trace['status']}, approval={trace['approval']})")

    trace["approval"] = "APPROVED" if decision == "approve" else "REJECTED"
    d = run_dir(run_id)
    if trace["approval"] == "APPROVED":
        ticket = {
            "run_id": run_id,
            "mode": "PAPER",
            "symbol": trace["plan"]["symbol"],
            "max_weight": trace["plan"]["max_weight"],
            "strategy_file": "strategy.py",
            "approved_by": approver,
            "approved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        (d / "order_ticket.json").write_text(json.dumps(ticket, ensure_ascii=False, indent=2), encoding="utf-8")
        trace["order_ticket"] = ticket
    (d / "trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    return trace
