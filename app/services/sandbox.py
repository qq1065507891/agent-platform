from __future__ import annotations

import ast
import multiprocessing as mp
import sys
from dataclasses import dataclass
from queue import Empty
from typing import Any

from RestrictedPython import compile_restricted
from RestrictedPython.Guards import safe_builtins


FORBIDDEN_MODULES = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "pathlib",
    "shutil",
    "ctypes",
    "multiprocessing",
}

FORBIDDEN_CALLS = {
    "open",
    "eval",
    "exec",
    "compile",
    "__import__",
    "input",
}

FORBIDDEN_ATTRIBUTES = {
    "__dict__",
    "__class__",
    "__mro__",
    "__subclasses__",
    "__globals__",
}


@dataclass
class SandboxViolation:
    rule: str
    symbol: str
    line: int | None


class SandboxSecurityError(Exception):
    pass


class SandboxTimeoutError(Exception):
    pass


def scan_code_security(code: str) -> dict[str, Any]:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {
            "passed": False,
            "violations": [
                {
                    "rule": "syntax_error",
                    "symbol": str(exc.msg),
                    "line": exc.lineno,
                }
            ],
        }

    violations: list[SandboxViolation] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".")[0]
                if root_name in FORBIDDEN_MODULES:
                    violations.append(SandboxViolation("forbidden_import", root_name, getattr(node, "lineno", None)))

        if isinstance(node, ast.ImportFrom):
            module_name = (node.module or "").split(".")[0]
            if module_name in FORBIDDEN_MODULES:
                violations.append(SandboxViolation("forbidden_import", module_name, getattr(node, "lineno", None)))
            if any(alias.name == "*" for alias in node.names):
                violations.append(SandboxViolation("wildcard_import", module_name or "*", getattr(node, "lineno", None)))

        if isinstance(node, ast.Call):
            func_name = _get_callable_name(node.func)
            if func_name in FORBIDDEN_CALLS:
                violations.append(SandboxViolation("forbidden_call", func_name, getattr(node, "lineno", None)))

        if isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRIBUTES:
                violations.append(SandboxViolation("forbidden_attribute", node.attr, getattr(node, "lineno", None)))

    return {
        "passed": len(violations) == 0,
        "violations": [
            {"rule": item.rule, "symbol": item.symbol, "line": item.line}
            for item in violations
        ],
    }


def execute_skill_code_safely(code: str, params: dict[str, Any], timeout_seconds: int = 10) -> dict[str, Any]:
    scan_result = scan_code_security(code)
    if not scan_result["passed"]:
        raise SandboxSecurityError("Code failed AST security scan")

    ctx = mp.get_context("spawn")
    queue: mp.Queue = ctx.Queue(maxsize=1)
    process = ctx.Process(target=_sandbox_process_runner, args=(code, params, queue))
    process.start()
    process.join(timeout=timeout_seconds)

    if process.is_alive():
        process.terminate()
        process.join(1)
        raise SandboxTimeoutError(f"Skill execution timed out after {timeout_seconds}s")

    if process.exitcode != 0 and queue.empty():
        return {
            "ok": False,
            "result": None,
            "stdout": "",
            "error": f"Sandbox process exited with code {process.exitcode}",
        }

    try:
        payload = queue.get_nowait()
    except Empty:
        payload = {
            "ok": False,
            "result": None,
            "stdout": "",
            "error": "Sandbox returned no payload",
        }

    return payload


def _sandbox_process_runner(code: str, params: dict[str, Any], queue: mp.Queue) -> None:
    _apply_process_resource_limits()

    safe_globals: dict[str, Any] = {
        "__builtins__": {
            **safe_builtins,
            "len": len,
            "range": range,
            "min": min,
            "max": max,
            "sum": sum,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "dict": dict,
            "list": list,
        },
        "__name__": "__sandbox__",
    }

    try:
        byte_code = compile_restricted(code, filename="<external_skill>", mode="exec")
        exec(byte_code, safe_globals, None)

        run_fn = safe_globals.get("run")
        if not callable(run_fn):
            raise ValueError("Skill code must provide callable run(params) entry")

        result = run_fn(params)
        queue.put(
            {
                "ok": True,
                "result": result,
                "stdout": "",
                "error": None,
            }
        )
    except Exception as exc:
        queue.put(
            {
                "ok": False,
                "result": None,
                "stdout": "",
                "error": str(exc),
            }
        )


def _apply_process_resource_limits(memory_mb: int = 512, cpu_seconds: int = 10) -> None:
    # Best-effort resource limits (effective on Unix). Windows skips quietly.
    if sys.platform.startswith("win"):
        return

    try:
        import resource

        memory_bytes = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    except Exception:
        # Keep sandbox functional even if rlimit is unavailable.
        return


def _get_callable_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""
