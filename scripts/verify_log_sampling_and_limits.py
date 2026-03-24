from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _print_result(result: CheckResult) -> None:
    status = "PASS" if result.ok else "FAIL"
    print(f"[{status}] {result.name}: {result.detail}")


def _emit_logs(info_count: int, long_len: int, list_len: int) -> None:
    from app.core.logging import get_logger, setup_logging

    setup_logging()
    logger = get_logger("log-verifier")

    for i in range(info_count):
        logger.info("sampling_probe", seq=i)

    logger.warning(
        "limit_probe",
        payload="x" * long_len,
        items=list(range(list_len)),
        token="sk-abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    )


def _parse_json_lines(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _run_subprocess(
    info_count: int,
    long_len: int,
    list_len: int,
    sample_rate: float,
    max_field_length: int,
    max_collection_items: int,
    app_env: str,
) -> tuple[str, str, int]:
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": app_env,
            "LOG_INFO_SAMPLE_RATE": str(sample_rate),
            "LOG_MAX_FIELD_LENGTH": str(max_field_length),
            "LOG_MAX_COLLECTION_ITEMS": str(max_collection_items),
            "LOG_LEVEL": "INFO",
            "LOG_LEVEL_DEV": "INFO",
            "LOG_LEVEL_STAGING": "INFO",
            "LOG_LEVEL_PROD": "INFO",
        }
    )
    cmd = [
        sys.executable,
        __file__,
        "--emit-only",
        "--info-count",
        str(info_count),
        "--long-len",
        str(long_len),
        "--list-len",
        str(list_len),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return proc.stdout, proc.stderr, proc.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify log sampling and field truncation")
    parser.add_argument("--emit-only", action="store_true", help="Internal mode: only emit logs")
    parser.add_argument("--info-count", type=int, default=200)
    parser.add_argument("--long-len", type=int, default=5000)
    parser.add_argument("--list-len", type=int, default=120)
    parser.add_argument("--sample-rate", type=float, default=0.2)
    parser.add_argument("--max-field-length", type=int, default=256)
    parser.add_argument("--max-collection-items", type=int, default=20)
    parser.add_argument("--app-env", default="prod")
    args = parser.parse_args()

    if args.emit_only:
        _emit_logs(args.info_count, args.long_len, args.list_len)
        return

    stdout, stderr, returncode = _run_subprocess(
        info_count=args.info_count,
        long_len=args.long_len,
        list_len=args.list_len,
        sample_rate=args.sample_rate,
        max_field_length=args.max_field_length,
        max_collection_items=args.max_collection_items,
        app_env=args.app_env,
    )

    if returncode != 0:
        print("Child process failed")
        print(stderr)
        sys.exit(returncode)

    logs = _parse_json_lines(stdout + "\n" + stderr)

    info_rows = [r for r in logs if r.get("event") == "sampling_probe"]
    limit_rows = [r for r in logs if r.get("event") == "limit_probe"]

    observed_rate = (len(info_rows) / args.info_count) if args.info_count > 0 else 0.0
    # give tolerance because sampling is random
    tolerance = 0.1
    sample_ok = abs(observed_rate - args.sample_rate) <= tolerance

    _print_result(
        CheckResult(
            name="info log sampling",
            ok=sample_ok,
            detail=f"expected≈{args.sample_rate:.2f}, observed={observed_rate:.2f}, emitted={len(info_rows)}/{args.info_count}",
        )
    )

    if not limit_rows:
        _print_result(CheckResult(name="field limits", ok=False, detail="no limit_probe log found"))
        return

    row = limit_rows[-1]
    payload = str(row.get("payload", ""))
    items = row.get("items", [])
    token = str(row.get("token", ""))

    trunc_ok = payload.endswith("...[truncated]") and len(payload) <= args.max_field_length + len("...[truncated]")
    list_ok = isinstance(items, list) and len(items) == args.max_collection_items + 1 and str(items[-1]).startswith("...[")
    redact_ok = "***" in token

    _print_result(
        CheckResult(
            name="long field truncation",
            ok=trunc_ok,
            detail=f"payload_len={len(payload)}, max={args.max_field_length}",
        )
    )
    _print_result(
        CheckResult(
            name="collection truncation",
            ok=list_ok,
            detail=f"items_len={len(items) if isinstance(items, list) else 'n/a'}, max_items={args.max_collection_items}",
        )
    )
    _print_result(
        CheckResult(
            name="sensitive redaction",
            ok=redact_ok,
            detail=f"token={token}",
        )
    )

    print("\nIf any check FAILs, inspect your env vars and logging config, then rerun.")


if __name__ == "__main__":
    main()
