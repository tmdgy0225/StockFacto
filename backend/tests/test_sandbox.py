from harness.prices import generate_bars
from harness.verify.sandbox import run_backtest

BARS = generate_bars({"pattern": "flat", "seed": 1, "n": 30})


def strategy(order: str, body: str = "") -> str:
    return f'''
class Strategy:
    def __init__(self):
        self.done = False

    def on_bar(self, bar, ctx):
{body}
        if not self.done:
            self.done = True
            return {order}
        return None
'''


def ids(result) -> set[str]:
    return {v.rule_id for v in result.violations}


def test_safe_strategy_runs():
    r = run_backtest(strategy('Order(side="buy", weight=ctx.max_weight, stop_loss=bar.close * 0.97)'), BARS, 0.05)
    assert r.ok, r.violations
    assert r.metrics["trades"] == 1
    assert r.metrics["max_weight_used"] == 0.05
    assert len(r.equity_curve) == len(BARS)


def test_runtime_weight_cap_is_enforced_fail_closed():
    # 정적 분석을 우회한 비중(동적 계산)도 런타임에서 차단되고, 주문은 체결되지 않는다.
    code = strategy('Order(side="buy", weight=self.w, stop_loss=bar.close * 0.97)', "        self.w = len(ctx.closes) * 10.0")
    r = run_backtest(code, BARS, 0.05, enforce=True)
    assert "R-002" in ids(r)
    assert r.metrics["trades"] == 0


def test_observe_only_mode_executes_but_records():
    r = run_backtest(strategy('Order(side="buy", weight=1.0)'), BARS, 0.05, enforce=False)
    assert {"R-001", "R-002"} <= ids(r)
    assert r.metrics["max_weight_used"] == 1.0


def test_runtime_error_reports_line():
    r = run_backtest(strategy("None", "        x = undefined_name"), BARS, 0.05)
    err = [v for v in r.violations if v.rule_id == "R-007"]
    assert err and "NameError" in err[0].message and err[0].line is not None


def test_import_blocked_at_runtime():
    r = run_backtest("import os\nclass Strategy:\n    def on_bar(self, bar, ctx):\n        return None\n", BARS, 0.05)
    assert "R-007" in ids(r)


def test_ctx_mutation_blocked_at_runtime():
    r = run_backtest(strategy("None", "        ctx.max_weight = 1.0"), BARS, 0.05)
    assert "R-007" in ids(r)


def test_infinite_loop_times_out():
    r = run_backtest(strategy("None", "        while True:\n            pass"), BARS, 0.05, timeout_sec=2)
    assert "R-007" in ids(r)
