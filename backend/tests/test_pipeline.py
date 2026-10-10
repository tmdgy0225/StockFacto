from harness.agents import MockAgent
from harness.collect import collect
from harness.config import get_case, load_agents_md, load_rules
from harness.context import build_context
from harness.pipeline import run_pipeline


def run(case_id: str, mode: str = "harness"):
    case = get_case(case_id)
    return run_pipeline(case, MockAgent(case), mode, write=False)


def test_fact_check_unverified_rumor():
    case = get_case("CASE-01")
    ctx = build_context(case, collect(case))
    assert ctx["fact_status"] == "UNVERIFIED"
    assert ctx["max_weight"] == 0.05


def test_fact_check_verified_disclosure():
    case = get_case("CASE-02")
    ctx = build_context(case, collect(case))
    assert ctx["fact_status"] == "VERIFIED"
    assert ctx["facts"][0]["evidence"]["report_nm"] == "단일판매ㆍ공급계약체결"


def test_main_scenario_control_releases_unsafe_code():
    trace = run("CASE-01", "control")
    assert trace.status == "RELEASED" and trace.unsafe
    rules = {v["rule_id"] for v in trace.attempts[0].violations}
    assert {"R-001", "R-002", "R-003"} <= rules


def test_main_scenario_harness_self_heals():
    trace = run("CASE-01")
    assert trace.status == "PASSED" and trace.unsafe is False
    assert len(trace.attempts) >= 2 and not trace.attempts[0].passed
    final = trace.attempts[-1]
    assert final.violations == [] and final.metrics["max_weight_used"] <= 0.05
    assert any("100%" in c for c in trace.plan["conflicts"])


def test_gap_risk_is_caught_by_quality_gate():
    trace = run("CASE-03")
    assert "R-003" in {v["rule_id"] for v in trace.attempts[0].violations}
    assert trace.status == "PASSED"


def test_stubborn_agent_is_escalated_not_released():
    trace = run("CASE-08")
    assert trace.status == "ESCALATED" and trace.approval is None
    assert "진전 없음" in trace.escalation_reason


def test_every_harness_pass_has_zero_violations():
    from harness.config import load_cases

    for case in load_cases():
        trace = run_pipeline(case, MockAgent(case), "harness", write=False)
        if trace.status == "PASSED":
            assert trace.attempts[-1].violations == [], case["id"]


def test_agents_md_mentions_every_rule():
    md = load_agents_md()
    for rule in load_rules()["rules"]:
        assert rule["id"] in md, f"AGENTS.md 에 {rule['id']} 가 없습니다 (rules.yaml 과 동기화 필요)"
