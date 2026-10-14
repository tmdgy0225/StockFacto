from harness import eval as harness_eval
from harness.agents import AgentError, MockAgent


def test_agent_errors_are_excluded_from_metrics(monkeypatch):
    # API 사용량 초과 같은 에이전트 오류는 코드 안전성과 무관하다 → 지표에서 빼고 따로 보고해야 한다.
    class QuotaExceeded(MockAgent):
        def generate(self, req):
            raise AgentError("Gemini API 오류 429: quota exceeded")

    def fake_make_agent(name, case):
        return QuotaExceeded(case) if case["id"] == "CASE-02" else MockAgent(case)

    monkeypatch.setattr(harness_eval, "make_agent", fake_make_agent)
    report = harness_eval.run_eval("mock", ["CASE-01", "CASE-02", "CASE-09"])
    s = report["summary"]
    assert s["errored_cases"] == ["CASE-02"]
    assert s["cases"] == 2
    # CASE-01(위험) + CASE-09(안전) 만 집계 → 오류 케이스가 '위험 코드' 로 잘못 세지지 않는다
    assert s["control"]["unsafe_release_rate"] == 1.0
    assert len(report["rows"]) == 3
    assert next(r for r in report["rows"] if r["case_id"] == "CASE-02")["error_reason"].startswith("Gemini API 오류 429")
