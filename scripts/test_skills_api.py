from __future__ import annotations

import argparse
import json
import os
from typing import Any

import requests


DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"


def _request(
    method: str,
    url: str,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = requests.request(
        method=method,
        url=url,
        headers=headers,
        json=payload,
        params=params,
        timeout=30,
    )
    try:
        data = resp.json()
    except ValueError:
        data = {"raw": resp.text}

    return {
        "status_code": resp.status_code,
        "ok": resp.ok,
        "data": data,
    }


def login(base_url: str, username: str, password: str) -> str:
    url = f"{base_url}/auth/login"
    payload = {
        "username": username,
        "password": password,
        "login_type": "password",
    }
    result = _request("POST", url, payload=payload)
    if not result["ok"]:
        raise RuntimeError(f"login failed: {json.dumps(result, ensure_ascii=False)}")

    token = (result["data"].get("data") or {}).get("access_token")
    if not token:
        raise RuntimeError(f"login response missing access_token: {json.dumps(result, ensure_ascii=False)}")
    return token


def list_skills(base_url: str, token: str, page: int, page_size: int) -> dict[str, Any]:
    url = f"{base_url}/skills"
    return _request(
        "GET",
        url,
        token=token,
        params={"page": page, "page_size": page_size},
    )


def load_skill(
    base_url: str,
    token: str,
    source_type: str,
    source_url: str,
    source_version: str | None,
    expected_hash: str | None,
) -> dict[str, Any]:
    url = f"{base_url}/skills/load"
    payload: dict[str, Any] = {
        "source_type": source_type,
        "source_url": source_url,
    }
    if source_version:
        payload["source_version"] = source_version
    if expected_hash:
        payload["expected_hash"] = expected_hash

    return _request("POST", url, token=token, payload=payload)


def disable_skill(base_url: str, token: str, skill_id: str, reason: str | None = None) -> dict[str, Any]:
    url = f"{base_url}/skills/{skill_id}/disable"
    payload = {"reason": reason or "manual disable by test script"}
    return _request("POST", url, token=token, payload=payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Test skills APIs: list/load/disable")
    parser.add_argument("--base-url", default=os.getenv("API_BASE_URL", DEFAULT_BASE_URL))

    parser.add_argument("--token", default=os.getenv("API_TOKEN"), help="Direct Bearer token")
    parser.add_argument("--username", default=os.getenv("API_USERNAME"), help="If token not provided, login username")
    parser.add_argument("--password", default=os.getenv("API_PASSWORD"), help="If token not provided, login password")

    parser.add_argument("--list", action="store_true", help="Call GET /skills")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=20)

    parser.add_argument("--load", action="store_true", help="Call POST /skills/load")
    parser.add_argument(
        "--source-type",
        default="http",
        choices=["github", "npm", "http", "local", "private_registry"],
    )
    parser.add_argument("--source-url", default=None, help="External python script URL")
    parser.add_argument("--source-version", default="1.0.0")
    parser.add_argument("--expected-hash", default=None)

    parser.add_argument("--disable-skill-id", default=None, help="If set, will call disable API")
    parser.add_argument("--disable-reason", default="security test disable")

    args = parser.parse_args()

    if not args.list and not args.load and not args.disable_skill_id:
        parser.error("At least one action is required: --list or --load or --disable-skill-id")

    if args.load and not args.source_url:
        parser.error("--source-url is required when using --load")

    token = args.token
    if not token:
        if not args.username or not args.password:
            raise RuntimeError("Either --token or both --username/--password are required")
        token = login(args.base_url, args.username, args.password)
        print("[OK] login success")

    if args.list:
        list_result = list_skills(
            base_url=args.base_url,
            token=token,
            page=args.page,
            page_size=args.page_size,
        )
        print("\n=== GET /skills result ===")
        print(json.dumps(list_result, ensure_ascii=False, indent=2))

    if args.load:
        load_result = load_skill(
            base_url=args.base_url,
            token=token,
            source_type=args.source_type,
            source_url=args.source_url,
            source_version=args.source_version,
            expected_hash=args.expected_hash,
        )
        print("\n=== POST /skills/load result ===")
        print(json.dumps(load_result, ensure_ascii=False, indent=2))

    if args.disable_skill_id:
        disable_result = disable_skill(
            base_url=args.base_url,
            token=token,
            skill_id=args.disable_skill_id,
            reason=args.disable_reason,
        )
        print("\n=== POST /skills/{id}/disable result ===")
        print(json.dumps(disable_result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
