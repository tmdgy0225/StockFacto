import pytest

from harness import failures
from harness.agents import MockAgent
from harness.config import get_case
from harness.pipeline import run_pipeline


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(failures, "FAILURES_PATH", tmp_path / "failures.json")


def _attempt(*rule_ids):
    return {"violations": [{"rule_id": r, "message": f"{r} 위반"} for r in rule_ids]}


def test_record_counts_runs_and_occurrences():
    failures.record([_attempt("R-001", "R-002"), _attempt("R-002")])
    data = failures.record([_attempt("R-002")])
    assert data["runs"] == 2
    assert data["rules"]["R-002"] == {**data["rules"]["R-002"], "runs": 2, "count": 3}
    assert failures.top(1)[0][0] == "R-002"


def test_render_for_prompt_includes_fix_hint():
    assert failures.render_for_prompt() is None
    failures.record([_attempt("R-001")])
    text = failures.render_for_prompt()
    assert "R-001" in text and "stop_loss" in text


def test_memory_is_injected_only_when_enabled():
    failures.record([_attempt("R-001")])
    case = get_case("CASE-01")

    seen: list[str] = []

    class Spy(MockAgent):
        def generate(self, req):
            seen.append(req.user)
            return super().generate(req)

    run_pipeline(case, Spy(case), "harness", write=False)
    assert "과거 실패 기록" not in seen[0]

    seen.clear()
    trace = run_pipeline(case, Spy(case), "harness", write=False, use_memory=True)
    assert "과거 실패 기록" in seen[0]
    assert trace.plan["failure_memory"] == ["R-001"]


def test_pipeline_records_only_when_writing(tmp_path, monkeypatch):
    from harness import handoff

    monkeypatch.setattr(handoff, "RUNS_DIR", tmp_path / "runs")
    case = get_case("CASE-01")
    run_pipeline(case, MockAgent(case), "harness", write=False)
    assert failures.load()["runs"] == 0
    run_pipeline(case, MockAgent(case), "harness", write=True)
    assert set(failures.load()["rules"]) == {"R-001", "R-002"}
