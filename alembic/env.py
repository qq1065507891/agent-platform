from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from app.core.database import Base

__import__("app.models")

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_database_url() -> str:
    return os.getenv("DB_URL", config.get_main_option("sqlalchemy.url"))


def _escape_config_interpolation(value: str) -> str:
    # Alembic uses ConfigParser interpolation, '%' must be escaped as '%%'.
    return value.replace("%", "%%")


config.set_main_option("sqlalchemy.url", _escape_config_interpolation(get_database_url()))


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
