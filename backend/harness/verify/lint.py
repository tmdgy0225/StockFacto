"""① Static Linter (Non-AI): Python AST 기반 정적 검사.

실행 전에 잡을 수 있는 위반은 모두 여기서 잡는다(Shift Feedback Left).
Lint 를 통과하지 못하면 비싼 샌드박스 백테스트는 실행하지 않는다.
"""
from __future__ import annotations

import ast

from ..config import load_rules
from ..violations import Violation, violation

STAGE = "lint"
_ALLOWED_DUNDERS = {"__init__"}


def lint(code: str, max_weight: float, ctx_max_weight: float | None = None) -> list[Violation]:
    """max_weight: 위반 판정 기준 비중 상한.
    ctx_max_weight: 코드 안의 `ctx.max_weight` 가 실제로 가질 값 (기본: max_weight).
    대조군은 하네스가 상한을 주입하지 않으므로 1.0 으로 계산해 '실제로 얼마를 사려 했는지' 를 본다.
    """
    try:
        tree = ast.parse(code, filename="strategy.py")
    except SyntaxError as e:
        return [violation("R-000", STAGE, f"SyntaxError: {e.msg}", e.lineno)]

    cfg = load_rules()
    found: list[Violation] = []
    found += _check_contract(tree)
    found += _check_forbidden(tree, set(cfg["sandbox"]["allowed_imports"]), set(cfg["sandbox"]["forbidden_names"]))
    ctx_value = max_weight if ctx_max_weight is None else ctx_max_weight
    found += _check_orders(tree, max_weight, ctx_value, cfg["risk"]["stop_loss"])
    return _dedupe(found)


# ---------------------------------------------------------------- R-005 계약

def _check_contract(tree: ast.Module) -> list[Violation]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Strategy":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "on_bar":
                    params = [a.arg for a in item.args.args]
                    if params[:3] == ["self", "bar", "ctx"]:
                        return []
                    return [violation("R-005", STAGE, f"on_bar 시그니처는 (self, bar, ctx) 여야 합니다: {params}", item.lineno)]
            return [violation("R-005", STAGE, "Strategy 클래스에 on_bar 메서드가 없습니다.", node.lineno)]
    return [violation("R-005", STAGE, "모듈 최상위에 class Strategy 가 없습니다.")]


# ---------------------------------------------------------------- R-004 금지 요소

def _check_forbidden(tree: ast.Module, allowed_imports: set[str], forbidden: set[str]) -> list[Violation]:
    out: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in allowed_imports:
                    out.append(violation("R-004", STAGE, f"허용되지 않은 import: {alias.name}", node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level or module.split(".")[0] not in allowed_imports:
                out.append(violation("R-004", STAGE, f"허용되지 않은 import: from {'.' * node.level}{module}", node.lineno))
        elif isinstance(node, ast.Name):
            if node.id in forbidden:
                out.append(violation("R-004", STAGE, f"금지된 이름 사용: {node.id}", node.lineno))
            elif node.id.startswith("__"):
                out.append(violation("R-004", STAGE, f"내부(dunder) 이름 접근 금지: {node.id}", node.lineno))
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr not in _ALLOWED_DUNDERS:
                out.append(violation("R-004", STAGE, f"내부(dunder) 속성 접근 금지: .{node.attr}", node.lineno))
        elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)):
            targets = node.targets if isinstance(node, (ast.Assign, ast.Delete)) else [node.target]
            for target in targets:
                for sub in ast.walk(target):
                    if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) and sub.value.id == "ctx":
                        out.append(violation("R-004", STAGE, f"ctx 는 읽기 전용입니다: ctx.{sub.attr} 변경 시도", node.lineno))
    return out


# ---------------------------------------------------------------- R-001/R-002/R-006 주문

def _check_orders(tree: ast.Module, max_weight: float, ctx_value: float, stop_cfg: dict) -> list[Violation]:
    out: list[Violation] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Order"):
            continue
        line = node.lineno
        if node.args or any(k.arg is None for k in node.keywords):
            out.append(violation("R-005", STAGE, "Order 는 키워드 인자만 사용해야 합니다.", line))
        kw = {k.arg: k.value for k in node.keywords if k.arg}

        side = kw.get("side")
        side_val = side.value if isinstance(side, ast.Constant) else None
        if side is None:
            out.append(violation("R-005", STAGE, "Order 에 side 가 없습니다.", line))
        elif isinstance(side, ast.Constant) and side_val not in ("buy", "sell"):
            out.append(violation("R-005", STAGE, f"side 는 'buy' 또는 'sell' 이어야 합니다: {side_val!r}", line))
        if side_val == "sell":
            continue  # 매도(청산) 주문은 비중/손절 검사 대상이 아니다. side 가 동적이면 매수로 간주(보수적).

        stop = kw.get("stop_loss")
        if stop is None or (isinstance(stop, ast.Constant) and stop.value is None):
            out.append(violation("R-001", STAGE, "매수 주문에 stop_loss 가 없습니다.", line))
        else:
            ratio = _close_multiplier(stop)
            if ratio is not None:
                dist = 1 - ratio
                if not (stop_cfg["min_distance"] <= dist <= stop_cfg["max_distance"]):
                    out.append(violation(
                        "R-006", STAGE,
                        f"손절 거리 {dist:.1%} 가 허용 범위({stop_cfg['min_distance']:.1%}~{stop_cfg['max_distance']:.0%})를 벗어났습니다.",
                        line,
                    ))

        weight = kw.get("weight")
        if weight is None:
            out.append(violation("R-002", STAGE, "매수 주문에 weight 가 없습니다.", line))
            continue
        bound = _upper_bound(weight, ctx_value)
        if bound is not None:
            if bound > max_weight + 1e-9:
                out.append(violation("R-002", STAGE, f"비중 {bound:.0%} 가 상한 {max_weight:.0%} 를 초과합니다.", line))
            elif bound <= 0:
                out.append(violation("R-002", STAGE, "비중은 0보다 커야 합니다.", line))
        elif not _refs_max_weight(weight):
            out.append(violation("R-002", STAGE, "weight 는 ctx.max_weight 에서 파생되거나 상수여야 합니다.", line))
    return out


def _is_max_weight(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "max_weight" and isinstance(node.value, ast.Name) and node.value.id == "ctx"


def _refs_max_weight(node: ast.AST) -> bool:
    return any(_is_max_weight(n) for n in ast.walk(node))


def _upper_bound(node: ast.AST, cap: float) -> float | None:
    """weight 식의 상한을 정적으로 계산한다. ctx.max_weight 는 cap 으로 치환. 계산 불가면 None."""
    if _is_max_weight(node):
        return cap
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _upper_bound(node.operand, cap)
        return None if v is None else (v if isinstance(node.op, ast.UAdd) else -v)
    if isinstance(node, ast.BinOp):
        left, right = _upper_bound(node.left, cap), _upper_bound(node.right, cap)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div) and right != 0:
            return left / right
        return None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("min", "max") and node.args:
        values = [_upper_bound(a, cap) for a in node.args]
        known = [v for v in values if v is not None]
        if node.func.id == "min":
            return min(known) if known else None  # min 의 상한은 계산 가능한 인자 중 최솟값
        return max(known) if len(known) == len(values) else None
    return None


def _close_multiplier(node: ast.AST) -> float | None:
    """stop_loss 가 `bar.close * k` (또는 `k * bar.close`) 형태면 k 를 반환."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        for price, k in ((node.left, node.right), (node.right, node.left)):
            if (
                isinstance(price, ast.Attribute) and price.attr == "close"
                and isinstance(price.value, ast.Name) and price.value.id == "bar"
            ):
                bound = _upper_bound(k, 0.0)
                if bound is not None and not _refs_max_weight(k):
                    return bound
    return None


def _dedupe(items: list[Violation]) -> list[Violation]:
    seen, out = set(), []
    for v in items:
        key = (v.rule_id, v.line, v.message)
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out
