from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import dataclass

import requests


@dataclass
class VerifyResult:
    name: str
    ok: bool
    detail: str


def _print_result(result: VerifyResult) -> None:
    status = "PASS" if result.ok else "FAIL"
    print(f"[{status}] {result.name}: {result.detail}")


def _extract_trace_headers(resp: requests.Response) -> tuple[str | None, str | None]:
    return resp.headers.get("X-Trace-Id"), resp.headers.get("X-Request-Id")


def verify_health(base_url: str, request_id: str) -> VerifyResult:
    url = f"{base_url.rstrip('/')}/"
    resp = requests.get(url, headers={"X-Request-Id": request_id, "X-Trace-Id": request_id}, timeout=10)
    trace_id, echoed_request_id = _extract_trace_headers(resp)
    ok = resp.ok and resp.json().get("status") == "ok" and (echoed_request_id == request_id)
    return VerifyResult(
        name="health endpoint",
        ok=ok,
        detail=f"status={resp.status_code}, trace_id={trace_id}, request_id={echoed_request_id}",
    )


def verify_login(base_url: str, username: str, password: str, request_id: str) -> tuple[VerifyResult, str | None]:
    url = f"{base_url.rstrip('/')}/api/v1/auth/login"
    payload = {"username": username, "password": password}
    resp = requests.post(
        url,
        json=payload,
        headers={"X-Request-Id": request_id, "X-Trace-Id": request_id},
        timeout=15,
    )
    trace_id, echoed_request_id = _extract_trace_headers(resp)
    token = None
    try:
        body = resp.json()
        token = body.get("data", {}).get("access_token")
    except Exception:
        body = {"raw": resp.text[:300]}

    ok = resp.ok and bool(token) and echoed_request_id == request_id
    return (
        VerifyResult(
            name="auth login",
            ok=ok,
            detail=f"status={resp.status_code}, trace_id={trace_id}, request_id={echoed_request_id}, body={json.dumps(body, ensure_ascii=False)[:280]}",
        ),
        token,
    )


def verify_stream(
    base_url: str,
    token: str,
    conversation_id: str,
    request_id: str,
) -> VerifyResult:
    url = f"{base_url.rstrip('/')}/api/v1/conversations/{conversation_id}/messages/stream"
    payload = {"content": "日志链路验证消息", "attachments": []}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Request-Id": request_id,
        "X-Trace-Id": request_id,
    }
    with requests.post(url, json=payload, headers=headers, timeout=40, stream=True) as resp:
        trace_id, echoed_request_id = _extract_trace_headers(resp)
        got_delta = False
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            raw = line[6:]
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if data.get("type") == "delta":
                got_delta = True
                break

    ok = resp.ok and echoed_request_id == request_id and got_delta
    return VerifyResult(
        name="conversation stream",
        ok=ok,
        detail=f"status={resp.status_code}, trace_id={trace_id}, request_id={echoed_request_id}, got_delta={got_delta}",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify request_id/trace_id logging chain")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--username", help="Login username")
    parser.add_argument("--password", help="Login password")
    parser.add_argument("--conversation-id", help="Optional conversation id for stream verification")
    args = parser.parse_args()

    health_request_id = uuid.uuid4().hex
    _print_result(verify_health(args.base_url, health_request_id))

    if not args.username or not args.password:
        print("\nSkip login/stream checks: provide --username and --password to verify authenticated chain.")
        return

    login_request_id = uuid.uuid4().hex
    login_result, token = verify_login(args.base_url, args.username, args.password, login_request_id)
    _print_result(login_result)

    if not token:
        print("\nLogin failed; cannot continue stream verification.")
        return

    if not args.conversation_id:
        print("\nSkip stream check: provide --conversation-id to verify SSE chain.")
        return

    stream_request_id = uuid.uuid4().hex
    _print_result(verify_stream(args.base_url, token, args.conversation_id, stream_request_id))

    print("\nNext step: grep your service logs with request_id values shown above and confirm API/Celery events share the same IDs.")


if __name__ == "__main__":
    main()
