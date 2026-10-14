"""검증 세금 측정 도구 — 사람 입력과 시계를 가짜로 주입해 검증한다."""
from harness.vtax import run_session


def scripted(answers):
    it = iter(answers)
    return lambda _prompt: next(it)


def fake_clock(*times):
    it = iter(times)
    return lambda: next(it)


def test_session_records_time_and_judgement():
    # CASE-01: 대조군은 위험 코드(손절 없음, 비중 100%), 하네스는 통과.
    # 사람은 대조군에서 문제 하나를 적고 '출하 불가' 판단(정답), 하네스는 승인(정답).
    answers = ["손절선 없음", "", "n", "y"]
    result = run_session("mock", ["CASE-01"], "tester", ask=scripted(answers),
                         clock=fake_clock(0.0, 95.0, 100.0, 108.0), show=lambda _s: None)
    rec = result["records"][0]
    assert rec["control"]["seconds"] == 95.0 and rec["control"]["human_issues"] == ["손절선 없음"]
    assert rec["control"]["correct"] and not rec["control"]["missed_risk"]
    assert rec["harness"]["seconds"] == 8.0 and rec["harness"]["correct"]
    s = result["summary"]
    assert s["control_avg_seconds"] == 95.0 and s["harness_avg_seconds"] == 8.0
    assert s["control_judgement_accuracy"] == 1.0


def test_missed_risk_is_counted():
    # 사람이 위험 코드를 보고도 '출하 가능' 이라고 판단하면 놓친 위험으로 기록된다.
    answers = ["", "y", "y"]
    result = run_session("mock", ["CASE-01"], "tester", ask=scripted(answers),
                         clock=fake_clock(0.0, 30.0, 40.0, 45.0), show=lambda _s: None)
    assert result["records"][0]["control"]["missed_risk"] is True
    assert result["summary"]["control_missed_risks"] == 1
