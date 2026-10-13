"""A/B 평가 러너: 같은 케이스셋을 대조군(control)과 실험군(harness)으로 실행하고 지표를 집계한다.

    python -m harness.eval                 # Mock 에이전트, 전체 케이스
    python -m harness.eval --agent claude  # 실제 Claude (비용 발생)

지표
- unsafe_release_rate : 최종 출하된 코드 중 규칙 위반(손절 누락·비중 초과·MDD 초과·크래시 등)을 포함한 비율
- self_healing_rate   : 첫 시도가 실패한 실험군 런 중 사람 개입 없이 PASSED 로 끝난 비율
- token_reduction     : 뉴스·SNS·공시 원문 대비 압축 컨텍스트의 토큰 절감률(추정)
- healing_token_reduction : Self-Healing 재시도의 출력 토큰, 전체 재작성(rewrite) 대비 patch_file 절감률
                        (--compare-healing 일 때 같은 케이스를 rewrite 모드로 한 번 더 실행해 비교)
- human_review_runs   : 사람이 직접 검수해야 하는 런 수 (검증 세금의 대리 지표)
    · 대조군: 자동 검증이 없으므로 모든 런
    · 실험군: 에스컬레이션된 런만 (PASSED 런은 승인 버튼만 누르면 됨)
  ※ 검증 세금(분)은 사람이 직접 측정해야 하는 값이므로 여기서는 대리 지표만 계산한다.
"""
from __future__ import annotations

import argparse
import json
from statistics import mean

from .agents import make_agent
from .config import BACKEND_DIR, load_cases
from .pipeline import RunTrace, run_pipeline


def run_eval(agent_name: str = "mock", case_ids: list[str] | None = None, compare_healing: bool = False) -> dict:
    cases = [c for c in load_cases() if not case_ids or c["id"] in case_ids]
    rows = []
    for case in cases:
        control = run_pipeline(case, make_agent(agent_name, case), "control", write=False)
        harness = run_pipeline(case, make_agent(agent_name, case), "harness", write=False)
        row = _row(case, control, harness)
        if compare_healing:
            rewrite = run_pipeline(case, make_agent(agent_name, case), "harness", write=False, healing_mode="rewrite")
            row["healing_output_tokens_rewrite"] = _healing_output_tokens(rewrite)
            row["rewrite_status"] = rewrite.status
        rows.append(row)

    n = len(rows)
    healing_needed = [r for r in rows if r["harness_first_failed"]]
    summary = {
        "agent": agent_name,
        "cases": n,
        "control": {
            "unsafe_release_rate": _ratio(sum(r["control_unsafe"] for r in rows), n),
            "human_review_runs": n,
            "avg_prompt_tokens": round(mean(r["control_prompt_tokens"] for r in rows)) if rows else 0,
        },
        "harness": {
            "unsafe_release_rate": _ratio(sum(r["harness_status"] == "PASSED" and r["harness_unsafe"] for r in rows), n),
            "passed": sum(r["harness_status"] == "PASSED" for r in rows),
            "escalated": sum(r["harness_status"] == "ESCALATED" for r in rows),
            "self_healing_rate": _ratio(sum(r["harness_status"] == "PASSED" for r in healing_needed), len(healing_needed)),
            "avg_attempts": round(mean(r["harness_attempts"] for r in rows), 2) if rows else 0,
            "human_review_runs": sum(r["harness_status"] != "PASSED" for r in rows),
            "avg_prompt_tokens_first_attempt": round(mean(r["harness_prompt_tokens"] for r in rows)) if rows else 0,
        },
        # 케이스별 비율의 평균이 아니라 전체 토큰 합 기준 (짧은 소스 케이스가 왜곡하지 않도록)
        "token_reduction": _ratio_reduction(sum(r["raw_tokens"] for r in rows), sum(r["compact_tokens"] for r in rows)),
    }
    if compare_healing:
        patch_total = sum(r["healing_output_tokens"] for r in rows)
        rewrite_total = sum(r["healing_output_tokens_rewrite"] for r in rows)
        summary["healing"] = {
            "patch_output_tokens": patch_total,
            "rewrite_output_tokens": rewrite_total,
            "healing_token_reduction": _ratio_reduction(rewrite_total, patch_total),
            "same_outcome": all(r["harness_status"] == r["rewrite_status"] for r in rows),
        }
    return {"summary": summary, "rows": rows}


def _row(case: dict, control: RunTrace, harness: RunTrace) -> dict:
    c_attempt = control.attempts[0] if control.attempts else None
    h_last = harness.attempts[-1] if harness.attempts else None
    return {
        "case_id": case["id"],
        "title": case["title"],
        "fact_status": harness.context.get("fact_status"),
        "control_unsafe": bool(control.unsafe) or control.status == "ERROR",
        "control_rules": sorted({v["rule_id"] for v in c_attempt.violations}) if c_attempt else [],
        "control_mdd": (c_attempt.metrics or {}).get("mdd") if c_attempt else None,
        "control_prompt_tokens": c_attempt.tokens.get("input", 0) if c_attempt else 0,
        "harness_status": harness.status,
        "harness_unsafe": bool(h_last and h_last.violations),
        "harness_attempts": len(harness.attempts),
        "harness_first_failed": bool(harness.attempts and not harness.attempts[0].passed),
        "harness_rules_seen": [sorted({v["rule_id"] for v in a.violations}) for a in harness.attempts],
        "harness_mdd": (h_last.metrics or {}).get("mdd") if h_last else None,
        "harness_prompt_tokens": harness.attempts[0].tokens.get("input", 0) if harness.attempts else 0,
        "escalation_reason": harness.escalation_reason,
        "token_reduction": harness.context["tokens"]["reduction"],
        "healing_output_tokens": _healing_output_tokens(harness),
        "harness_edit_modes": [a.edit_mode for a in harness.attempts],
        "raw_tokens": harness.context["tokens"]["raw"],
        "compact_tokens": harness.context["tokens"]["compact"],
    }


def _healing_output_tokens(trace: RunTrace) -> int:
    """재시도(2번째 시도부터)에서 에이전트가 출력한 토큰 합."""
    return sum(a.tokens.get("output", 0) for a in trace.attempts[1:])


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 4) if b else None


def _ratio_reduction(raw: int, compact: int) -> float | None:
    return round(1 - compact / raw, 4) if raw else None


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{x:.0%}"


def print_report(report: dict) -> None:
    s = report["summary"]
    print(f"\n=== A/B 평가 (agent={s['agent']}, cases={s['cases']}) ===")
    print(f"{'지표':<28}{'대조군':>12}{'실험군(하네스)':>16}")
    print(f"{'위험 코드 방출률':<28}{_pct(s['control']['unsafe_release_rate']):>12}{_pct(s['harness']['unsafe_release_rate']):>16}")
    print(f"{'사람 검수 필요 런':<28}{s['control']['human_review_runs']:>12}{s['harness']['human_review_runs']:>16}")
    print(f"{'Self-Healing 성공률':<28}{'-':>12}{_pct(s['harness']['self_healing_rate']):>16}")
    print(f"{'평균 시도 횟수':<28}{1:>12}{s['harness']['avg_attempts']:>16}")
    print(f"{'컨텍스트 토큰 절감률(추정)':<28}{'-':>12}{_pct(s['token_reduction']):>16}")
    if "healing" in s:
        h = s["healing"]
        print(f"\nSelf-Healing 출력 토큰: rewrite {h['rewrite_output_tokens']} → patch {h['patch_output_tokens']}"
              f" ({_pct(h['healing_token_reduction'])} 절감, 결과 동일: {h['same_outcome']})")
    print("\n케이스별:")
    for r in report["rows"]:
        print(f"  {r['case_id']} [{r['fact_status']}] control={'UNSAFE' if r['control_unsafe'] else 'safe'}"
              f"{r['control_rules']}  harness={r['harness_status']} attempts={r['harness_attempts']} {r['harness_rules_seen']}"
              f"  tokens {r['raw_tokens']}→{r['compact_tokens']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="StockFacto harness A/B evaluation")
    parser.add_argument("--agent", default="mock", choices=["mock", "claude"])
    parser.add_argument("--cases", nargs="*", help="실행할 케이스 ID (기본: 전체)")
    parser.add_argument("--out", default=str(BACKEND_DIR / "runs" / "eval_report.json"))
    parser.add_argument("--compare-healing", action="store_true", help="patch_file vs 전체 재작성 출력 토큰 비교 (실행 횟수 증가)")
    args = parser.parse_args()
    report = run_eval(args.agent, args.cases, args.compare_healing)
    print_report(report)
    from pathlib import Path

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n리포트 저장: {out}")


if __name__ == "__main__":
    main()
