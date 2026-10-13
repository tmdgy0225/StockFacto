"""추론적 센서(LLM 리뷰어) — 가짜 클라이언트로 검증. 경고는 판정에 영향을 주지 않아야 한다."""
from types import SimpleNamespace

from harness.agents import MockAgent
from harness.config import get_case
from harness.pipeline import run_pipeline
from harness.review import ClaudeReviewer, make_reviewer


def fake_client(text: str):
    def create(**kwargs):
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)],
                               usage=SimpleNamespace(input_tokens=500, output_tokens=40))
    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))


def test_warnings_are_attached_but_do_not_change_verdict():
    text = '```json\n{"warnings": [{"severity": "medium", "message": "청산 조건이 보유 기간뿐입니다."}, {"severity": "bogus", "message": "x"}]}\n```'
    case = get_case("CASE-01")
    trace = run_pipeline(case, MockAgent(case), "harness", write=False, reviewer=ClaudeReviewer(client=fake_client(text)))
    assert trace.status == "PASSED" and trace.approval == "PENDING"
    assert trace.review["status"] == "ok"
    assert trace.review["warnings"][0] == {"severity": "medium", "message": "청산 조건이 보유 기간뿐입니다."}
    assert trace.review["warnings"][1]["severity"] == "low"  # 잘못된 severity 는 low 로 정규화


def test_broken_reviewer_output_is_reported_not_fatal():
    case = get_case("CASE-01")
    trace = run_pipeline(case, MockAgent(case), "harness", write=False, reviewer=ClaudeReviewer(client=fake_client("모르겠어요")))
    assert trace.status == "PASSED"
    assert trace.review["status"] == "error"


def test_reviewer_is_off_by_default(monkeypatch):
    monkeypatch.delenv("HARNESS_REVIEWER", raising=False)
    assert make_reviewer() is None
    case = get_case("CASE-01")
    assert run_pipeline(case, MockAgent(case), "harness", write=False).review == {"status": "skipped", "warnings": []}


def test_escalated_runs_are_not_reviewed():
    case = get_case("CASE-08")
    trace = run_pipeline(case, MockAgent(case), "harness", write=False, reviewer=ClaudeReviewer(client=fake_client("{}")))
    assert trace.status == "ESCALATED" and trace.review is None
