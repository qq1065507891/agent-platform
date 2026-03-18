from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import os
from typing import Any

import jwt

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_EXPIRE_MIN = int(os.getenv("JWT_EXPIRE_MIN", "60"))
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def create_access_token(data: dict[str, Any], expires_minutes: int | None = None) -> str:
    expire_minutes = expires_minutes or JWT_EXPIRE_MIN
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload = {**data, "exp": expire_at}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
