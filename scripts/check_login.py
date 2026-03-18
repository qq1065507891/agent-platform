from __future__ import annotations

import hashlib
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def main() -> None:
    load_dotenv()
    db_url = os.getenv("DB_URL")
    if not db_url:
        raise SystemExit("DB_URL is not set")
    engine = create_engine(db_url)
    with engine.connect() as conn:
        row = conn.execute(
            text("select username,password_hash,status from users where username='admin'")
        ).fetchone()
    print("row=", row)
    if not row:
        return
    password = "Passw0rd!"
    expected = hashlib.sha256(password.encode("utf-8")).hexdigest()
    print("expected=", expected)
    print("verify=", row.password_hash == expected)


if __name__ == "__main__":
    main()
