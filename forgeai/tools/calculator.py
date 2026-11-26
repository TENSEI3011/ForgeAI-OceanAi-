"""Safe arithmetic. Parses with `ast` and evaluates a whitelist of nodes: no eval(), no names,
no attribute access, no imports. Anything else raises ValueError."""
from __future__ import annotations

import ast
import operator
import re
from typing import Any

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"round": round, "min": min, "max": max, "abs": abs, "sum": lambda *a: sum(a)}


def _eval(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and (abs(right) > 12 or abs(left) > 1e6):
            raise ValueError("exponent too large")
        return _BIN[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS
            and not node.keywords):
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError(f"unsupported expression element: {type(node).__name__}")


def calculate(expression: str) -> float:
    expr = str(expression).replace("$", "").replace("×", "*").replace("^", "**")
    expr = re.sub(r"(?<=\d),(?=\d{3}\b)", "", expr)            # 1,200 -> 1200 (keeps min(1, 2))
    expr = re.sub(r"(?<=[\d)])\s*x\s*(?=[\d(])", "*", expr)     # 3 x 4 -> 3*4
    expr = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", expr).strip()
    if len(expr) > 200:
        raise ValueError("expression too long")
    tree = ast.parse(expr, mode="eval")
    value = _eval(tree)
    if isinstance(value, float):
        value = round(value, 6)
    return value


def run(args: dict[str, Any], ctx: dict[str, Any]) -> str:
    expression = args.get("expression") or args.get("expr") or ""
    value = calculate(expression)
    return f"{expression} = {value}"
