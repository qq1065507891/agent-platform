from __future__ import annotations

import ast
from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import tool


@tool
def calculator(expression: str) -> str:
    """简单四则运算计算器，支持 + - * / 和括号。"""
    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            raise ValueError("不支持的运算符")
        if isinstance(node, ast.UnaryOp):
            operand = _eval(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +operand
            if isinstance(node.op, ast.USub):
                return -operand
            raise ValueError("不支持的运算符")
        if isinstance(node, ast.Num):
            return float(node.n)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError("仅支持数字与四则运算")

    if not expression or not expression.strip():
        raise ValueError("表达式不能为空")

    try:
        parsed = ast.parse(expression, mode="eval")
        result = _eval(parsed)
    except ZeroDivisionError as exc:
        raise ValueError("除数不能为 0") from exc
    except Exception as exc:
        raise ValueError("表达式格式错误") from exc

    return str(result)


@tool
def current_time(format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """获取当前时间，支持自定义格式。"""
    return datetime.now(timezone.utc).astimezone().strftime(format)


BUILTIN_TOOLS: dict[str, Any] = {
    "calculator": calculator,
    "current_time": current_time,
}
