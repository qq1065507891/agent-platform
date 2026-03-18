from __future__ import annotations

from datetime import datetime, timezone
import os
import sys

from sqlalchemy import inspect, text

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.database import engine


def add_column_if_missing(table: str, column: str, ddl: str) -> None:
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns(table)}
    if column in columns:
        print(f"{table}.{column} already exists")
        return
    with engine.begin() as connection:
        connection.execute(text(ddl))
    print(f"Added {table}.{column}")


def backfill_timestamp(table: str, column: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                f"UPDATE {table} SET {column} = :now WHERE {column} IS NULL"
            ),
            {"now": datetime.now(timezone.utc)},
        )
    print(f"Backfilled {table}.{column}")


def main() -> None:
    add_column_if_missing(
        "skills",
        "created_at",
        "ALTER TABLE skills ADD COLUMN created_at TIMESTAMP",
    )
    add_column_if_missing(
        "skills",
        "updated_at",
        "ALTER TABLE skills ADD COLUMN updated_at TIMESTAMP",
    )
    backfill_timestamp("skills", "created_at")
    backfill_timestamp("skills", "updated_at")


if __name__ == "__main__":
    main()
