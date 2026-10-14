"""검증 세금(Verification Tax) 측정 도구 — 사람이 직접 검수하는 시간을 기록한다.

    python -m harness.vtax --agent gemini --reviewer 홍길동
    python -m harness.vtax --agent mock --cases CASE-01 CASE-04 CASE-12

케이스마다 두 번 검수한다.
  1) 대조군: 하네스 없이 AI 가 쓴 코드만 보고, 문제를 찾아 출하 가능 여부를 판단한다.
  2) 하네스: 하네스의 검증 보고서와 최종 코드를 보고 승인 여부를 판단한다.
각 판단에 걸린 시간과, 사람의 판단이 하네스 판정(정답)과 일치했는지를 runs/vtax_<검수자>.json 에 저장한다.

주의: Mock 의 대조군 코드는 개발자가 만든 것이므로, 공정한 측정에는 실제 LLM(--agent gemini)을 권장한다.
"""
from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from datetime import datetime
from statistics import mean

from .agents import make_agent
from .config import RUNS_DIR, load_cases
from .patch import number_lines
from .pipeline import RunTrace, run_pipeline

DEFAULT_CASES = ["CASE-01", "CASE-04", "CASE-09", "CASE-12", "CASE-14"]

Ask = Callable[[str], str]
Clock = Callable[[], float]


def _yes(answer: str) -> bool:
    return answer.strip().lower() in ("y", "yes", "ㅇ", "예", "네")


def _read_issues(ask: Ask) -> list[str]:
    issues = []
    while True:
        line = ask("  문제점 (없으면 빈 줄로 종료) > ").strip()
        if not line:
            return issues
        issues.append(line)


def review_control(case: dict, trace: RunTrace, ask: Ask, clock: Clock, show: Callable[[str], None]) -> dict:
    code = trace.attempts[0].code if trace.attempts else ""
    show(f"\n{'=' * 70}\n[대조군 검수] {case['id']} {case['symbol']}\n요청: {case['request']}\n{'-' * 70}")
    show(number_lines(code))
    show("-" * 70 + "\n이 코드를 실제 계좌에 출하해도 되는지 직접 검수하세요. (손절선, 비중, 오류 위험 등)")
    start = clock()
    issues = _read_issues(ask)
    ship = _yes(ask("  출하해도 되나요? (y/n) > "))
    seconds = round(clock() - start, 1)
    truth_unsafe = bool(trace.unsafe) or trace.status == "ERROR"
    return {
        "seconds": seconds,
        "human_issues": issues,
        "human_ship": ship,
        "truth_unsafe": truth_unsafe,
        "truth_rules": sorted({v["rule_id"] for a in trace.attempts for v in a.violations}),
        "correct": ship != truth_unsafe,
        "missed_risk": ship and truth_unsafe,  # 위험한데 출하하겠다고 판단 = 사람이 놓친 위험
    }


def review_harness(case: dict, trace: RunTrace, ask: Ask, clock: Clock, show: Callable[[str], None]) -> dict:
    show(f"\n{'=' * 70}\n[하네스 승인] {case['id']} {case['symbol']}  판정={trace.status}\n{'-' * 70}")
    for a in trace.attempts:
        rules = sorted({v["rule_id"] for v in a.violations})
        show(f"  시도 #{a.n} [{a.edit_mode}] {'통과' if a.passed else '위반 ' + ', '.join(rules)}")
    final = trace.attempts[-1] if trace.attempts else None
    if final and final.metrics:
        m = final.metrics
        show(f"  최종: MDD {m['mdd']:.1%}, 체결 비중 {m['max_weight_used']:.0%}, 손절 {m['stop_hits']}회")
    if trace.escalation_reason:
        show(f"  에스컬레이션: {trace.escalation_reason}")
    if final:
        show("-" * 70 + "\n" + number_lines(final.code))
    show("-" * 70 + "\n하네스 보고서를 보고 승인 여부를 판단하세요.")
    start = clock()
    approve = _yes(ask("  승인할까요? (y/n) > "))
    seconds = round(clock() - start, 1)
    return {"seconds": seconds, "status": trace.status, "human_approve": approve,
            "correct": approve == (trace.status == "PASSED")}


def run_session(agent_name: str, case_ids: list[str], reviewer: str, ask: Ask = input,
                clock: Clock = time.perf_counter, show: Callable[[str], None] = print) -> dict:
    cases = [c for c in load_cases() if c["id"] in case_ids]
    records = []
    for case in cases:
        show(f"\n{case['id']} 준비 중... (AI 호출)")
        control = run_pipeline(case, make_agent(agent_name, case), "control", write=False)
        harness = run_pipeline(case, make_agent(agent_name, case), "harness", write=False)
        records.append({
            "case_id": case["id"],
            "control": review_control(case, control, ask, clock, show),
            "harness": review_harness(case, harness, ask, clock, show),
        })
    return {"reviewer": reviewer, "agent": agent_name, "measured_at": datetime.now().isoformat(timespec="seconds"),
            "records": records, "summary": summarize(records)}


def summarize(records: list[dict]) -> dict:
    if not records:
        return {}
    c = [r["control"] for r in records]
    h = [r["harness"] for r in records]
    c_avg, h_avg = mean(x["seconds"] for x in c), mean(x["seconds"] for x in h)
    return {
        "cases": len(records),
        "control_avg_seconds": round(c_avg, 1),
        "harness_avg_seconds": round(h_avg, 1),
        "time_reduction": round(1 - h_avg / c_avg, 4) if c_avg else None,
        "control_total_seconds": round(sum(x["seconds"] for x in c), 1),
        "harness_total_seconds": round(sum(x["seconds"] for x in h), 1),
        "control_judgement_accuracy": round(sum(x["correct"] for x in c) / len(c), 4),
        "control_missed_risks": sum(x["missed_risk"] for x in c),
    }


def print_summary(s: dict) -> None:
    print(f"\n=== 검증 세금 측정 결과 ({s['cases']}건) ===")
    print(f"코드 1건 평균 검수 시간: 대조군 {s['control_avg_seconds']}초 → 하네스 {s['harness_avg_seconds']}초"
          f" ({s['time_reduction']:.0%} 감소)")
    print(f"총 시간: 대조군 {s['control_total_seconds']}초, 하네스 {s['harness_total_seconds']}초")
    print(f"대조군 판단 정확도 {s['control_judgement_accuracy']:.0%}, 사람이 놓친 위험 코드 {s['control_missed_risks']}건")


def main() -> None:
    parser = argparse.ArgumentParser(description="검증 세금(사람 검수 시간) 측정")
    parser.add_argument("--agent", default="gemini", choices=["mock", "claude", "gemini"])
    parser.add_argument("--cases", nargs="*", default=DEFAULT_CASES)
    parser.add_argument("--reviewer", default="reviewer")
    args = parser.parse_args()
    result = run_session(args.agent, args.cases, args.reviewer)
    out = RUNS_DIR / f"vtax_{args.reviewer}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print_summary(result["summary"])
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
