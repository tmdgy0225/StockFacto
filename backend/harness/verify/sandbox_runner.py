"""Sandbox runner: 하네스와 분리된 별도 인터프리터(`python -I` 또는 Docker 컨테이너)에서 전략을 백테스트한다.

harness 패키지를 import 하지 않는 자기완결 스크립트여야 한다.
stdin 으로 JSON 요청을 받고 stdout 으로 JSON 결과를 돌려준다.

런타임 검증(R-001/R-002/R-005/R-006)은 여기서도 한 번 더 집행한다(Defense in depth).
enforce=True 이면 위반 주문은 체결하지 않는다(fail-closed).
enforce=False(대조군 측정용)이면 위반을 기록만 하고 그대로 체결해 실제 위험을 계측한다.
"""
import builtins
import io
import json
import sys
import traceback

SAFE_BUILTINS = [
    "abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "isinstance", "len", "list",
    "max", "min", "range", "reversed", "round", "set", "sorted", "str", "sum", "tuple", "zip",
    "object", "super", "property", "staticmethod", "classmethod",
    "Exception", "ValueError", "TypeError", "KeyError", "IndexError", "ZeroDivisionError", "ArithmeticError",
    "__build_class__",
]


class Order:
    __slots__ = ("side", "weight", "stop_loss", "reason")

    def __init__(self, side, weight=0.0, stop_loss=None, reason=""):
        self.side = side
        self.weight = weight
        self.stop_loss = stop_loss
        self.reason = reason


class Bar:
    __slots__ = ("_d",)

    def __init__(self, d):
        object.__setattr__(self, "_d", d)

    t = property(lambda self: self._d["t"])
    open = property(lambda self: self._d["open"])
    high = property(lambda self: self._d["high"])
    low = property(lambda self: self._d["low"])
    close = property(lambda self: self._d["close"])


class Context:
    """전략에 노출되는 읽기 전용 컨텍스트. 비중 상한 집행은 이 객체가 아니라 러너의 cap 으로 한다."""

    def __init__(self, symbol, max_weight):
        self._symbol = symbol
        self._max_weight = max_weight
        self._state = {"position": 0.0, "entry_price": None, "bar_index": 0, "closes": ()}

    symbol = property(lambda self: self._symbol)
    max_weight = property(lambda self: self._max_weight)
    position = property(lambda self: self._state["position"])
    entry_price = property(lambda self: self._state["entry_price"])
    bar_index = property(lambda self: self._state["bar_index"])
    closes = property(lambda self: self._state["closes"])


def _restricted_import(allowed):
    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if level or name.split(".")[0] not in allowed:
            raise ImportError(f"import blocked by sandbox: {name}")
        return builtins.__import__(name, globals, locals, fromlist, level)
    return _import


def _strategy_line(tb):
    line = None
    for frame in traceback.extract_tb(tb):
        if frame.filename == "strategy.py":
            line = frame.lineno
    return line


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def run(req):
    cap = float(req["max_weight"])
    enforce = bool(req.get("enforce", True))
    stop_min, stop_max = req["stop_min"], req["stop_max"]
    bars = req["bars"]

    violations = {}

    def flag(rule_id, message, bar_index):
        v = violations.setdefault(rule_id, {"rule_id": rule_id, "message": message, "first_bar": bar_index, "count": 0})
        v["count"] += 1

    safe = {name: getattr(builtins, name) for name in SAFE_BUILTINS}
    safe["__import__"] = _restricted_import(set(req["allowed_imports"]))
    namespace = {"__builtins__": safe, "__name__": "strategy", "Order": Order}

    m = {"bars": len(bars), "trades": 0, "stop_hits": 0, "rejected_orders": 0,
         "max_weight_used": 0.0, "mdd": 0.0, "total_return": 0.0}
    curve = []
    error = None
    captured = io.StringIO()
    real_stdout = sys.stdout
    sys.stdout = captured
    try:
        try:
            exec(compile(req["code"], "strategy.py", "exec"), namespace)
            strategy = namespace["Strategy"]()
        except Exception as e:
            error = {"type": type(e).__name__, "message": str(e), "line": _strategy_line(e.__traceback__), "bar": None}
            return _result(False, error, violations, m, curve, captured)

        ctx = Context(req.get("symbol", ""), cap)
        cash, shares, stop = 1.0, 0.0, None
        peak = 1.0
        closes = []
        for i, raw in enumerate(bars):
            bar = Bar(raw)
            if shares > 0 and stop is not None and bar.low <= stop:
                cash += shares * min(bar.open, stop)
                shares, stop = 0.0, None
                ctx._state["entry_price"] = None
                m["stop_hits"] += 1

            closes.append(bar.close)
            equity_now = cash + shares * bar.close
            ctx._state.update(position=(shares * bar.close / equity_now) if equity_now > 0 else 0.0,
                              bar_index=i, closes=tuple(closes))
            try:
                order = strategy.on_bar(bar, ctx)
            except Exception as e:
                error = {"type": type(e).__name__, "message": str(e), "line": _strategy_line(e.__traceback__), "bar": i}
                break

            if order is not None:
                if not isinstance(order, Order):
                    flag("R-005", "on_bar 가 Order 또는 None 이 아닌 값을 반환했습니다.", i)
                elif order.side == "buy" and shares == 0:
                    problems = []
                    w, sl = order.weight, order.stop_loss
                    if not _is_number(w) or w <= 0 or w > cap + 1e-9:
                        problems.append(("R-002", f"런타임 비중 {w!r} 가 상한 {cap:.0%} 를 벗어났습니다."))
                    if sl is None or not _is_number(sl):
                        problems.append(("R-001", "런타임 매수 주문에 유효한 stop_loss 가 없습니다."))
                    elif sl >= bar.close:
                        problems.append(("R-006", f"stop_loss({sl:.2f}) 가 진입가({bar.close:.2f}) 이상입니다."))
                    else:
                        dist = (bar.close - sl) / bar.close
                        if not (stop_min <= dist <= stop_max):
                            problems.append(("R-006", f"런타임 손절 거리 {dist:.1%} 가 허용 범위를 벗어났습니다."))
                    for rule_id, msg in problems:
                        flag(rule_id, msg, i)
                    if problems and enforce:
                        m["rejected_orders"] += 1
                    elif _is_number(w) and w > 0:
                        w = min(float(w), 1.0)  # 레버리지 없음
                        equity = cash
                        shares = equity * w / bar.close
                        cash -= shares * bar.close
                        stop = sl if _is_number(sl) else None
                        ctx._state["entry_price"] = bar.close
                        m["trades"] += 1
                        m["max_weight_used"] = max(m["max_weight_used"], w)
                elif order.side == "sell":
                    if shares > 0:
                        cash += shares * bar.close
                        shares, stop = 0.0, None
                        ctx._state["entry_price"] = None
                elif order.side != "buy":
                    flag("R-005", f"알 수 없는 side: {order.side!r}", i)

            equity = cash + shares * bar.close
            peak = max(peak, equity)
            m["mdd"] = max(m["mdd"], (peak - equity) / peak if peak > 0 else 0.0)
            curve.append(round(equity, 6))

        m["total_return"] = (curve[-1] - 1.0) if curve else 0.0
        return _result(error is None, error, violations, m, curve, captured)
    finally:
        sys.stdout = real_stdout


def _result(ok, error, violations, metrics, curve, captured):
    metrics = {k: (round(v, 6) if isinstance(v, float) else v) for k, v in metrics.items()}
    return {"ok": ok, "error": error, "violations": list(violations.values()), "metrics": metrics,
            "equity_curve": curve, "stdout": captured.getvalue()[:2000]}


def main():
    req = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    result = run(req)
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()
