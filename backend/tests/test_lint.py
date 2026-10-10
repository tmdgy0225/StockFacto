import pytest

from harness.verify.lint import lint

CAP = 0.05

SAFE = '''
import math

class Strategy:
    def __init__(self):
        self.entered = False

    def on_bar(self, bar, ctx):
        if not self.entered:
            self.entered = True
            return Order(side="buy", weight=ctx.max_weight, stop_loss=bar.close * 0.97)
        return None
'''


def strategy_with(order: str, extra: str = "") -> str:
    return f'''
{extra}
class Strategy:
    def on_bar(self, bar, ctx):
        return {order}
'''


def rule_ids(code: str) -> set[str]:
    return {v.rule_id for v in lint(code, CAP)}


def test_safe_code_passes():
    assert lint(SAFE, CAP) == []


def test_syntax_error():
    assert rule_ids("class Strategy:\n    def on_bar(self, bar, ctx)\n        pass\n") == {"R-000"}


def test_missing_stop_loss():
    assert "R-001" in rule_ids(strategy_with('Order(side="buy", weight=ctx.max_weight)'))


def test_stop_loss_none():
    assert "R-001" in rule_ids(strategy_with('Order(side="buy", weight=ctx.max_weight, stop_loss=None)'))


@pytest.mark.parametrize("weight", ["1.0", "0.5 * 2", "ctx.max_weight * 2", "ctx.max_weight + 0.1", "min(1.0, ctx.max_weight * 3)", "w"])
def test_weight_bypass_attempts_are_blocked(weight):
    assert "R-002" in rule_ids(strategy_with(f'Order(side="buy", weight={weight}, stop_loss=bar.close * 0.97)'))


@pytest.mark.parametrize("weight", ["ctx.max_weight", "ctx.max_weight * 0.5", "0.03", "min(ctx.max_weight, 0.04)", "min(ctx.max_weight, self.x)"])
def test_allowed_weights(weight):
    assert "R-002" not in rule_ids(strategy_with(f'Order(side="buy", weight={weight}, stop_loss=bar.close * 0.97)'))


def test_sell_order_needs_no_stop():
    assert rule_ids(strategy_with('Order(side="sell")')) == set()


@pytest.mark.parametrize("stop", ["bar.close * 0.5", "bar.close * 0.999", "0.8 * bar.close", "bar.close * 1.02"])
def test_stop_distance_out_of_band(stop):
    assert "R-006" in rule_ids(strategy_with(f'Order(side="buy", weight=ctx.max_weight, stop_loss={stop})'))


@pytest.mark.parametrize("snippet", [
    "import requests",
    "import os",
    "from subprocess import run",
    "x = eval('1')",
    "y = open('a.txt')",
    "z = ().__class__.__bases__",
    "b = __builtins__",
    "f = getattr",
])
def test_forbidden(snippet):
    code = strategy_with('Order(side="buy", weight=ctx.max_weight, stop_loss=bar.close * 0.97)', snippet)
    assert "R-004" in rule_ids(code)


def test_ctx_is_read_only():
    code = '''
class Strategy:
    def on_bar(self, bar, ctx):
        ctx.max_weight = 1.0
        return None
'''
    assert "R-004" in rule_ids(code)


def test_missing_strategy_class():
    assert "R-005" in rule_ids("def on_bar(bar, ctx):\n    return None\n")


def test_wrong_method_name():
    assert "R-005" in rule_ids("class Strategy:\n    def on_tick(self, bar, ctx):\n        return None\n")


def test_positional_order_args():
    assert "R-005" in rule_ids(strategy_with('Order("buy", 0.05, 100)'))
