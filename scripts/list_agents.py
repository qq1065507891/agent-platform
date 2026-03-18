from __future__ import annotations

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
        rows = conn.execute(
            text("select id, name, owner_id, status, is_public from agents order by created_at desc")
        ).fetchall()
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
