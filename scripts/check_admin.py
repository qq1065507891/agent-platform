from __future__ import annotations

import os

from sqlalchemy import create_engine, text


def main() -> None:
    db_url = os.getenv("DB_URL")
    if not db_url:
        raise SystemExit("DB_URL is not set")
    engine = create_engine(db_url)
    with engine.connect() as conn:
        row = conn.execute(
            text("select username,email,password_hash,status from users where username='admin'")
        ).fetchone()
    print(row)


if __name__ == "__main__":
    main()
