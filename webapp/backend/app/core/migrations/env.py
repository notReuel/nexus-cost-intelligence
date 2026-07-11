from logging.config import fileConfig
import sys
from pathlib import Path

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Make `app` importable regardless of cwd Alembic is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # backend/

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so their tables register on SQLModel.metadata, then
# point Alembic's autogenerate at that single source of truth — the same
# metadata `db.py::init_db()` uses for create_all(). This is what makes
# `alembic revision --autogenerate` actually see our schema.
from app.core import models  # noqa: F401
from app.core.db import DATABASE_URL
from sqlmodel import SQLModel
target_metadata = SQLModel.metadata

# Let DATABASE_URL (env var) override whatever is in alembic.ini, so the
# same migrations run against SQLite locally and Postgres in production
# without editing the ini file.
config.set_main_option("sqlalchemy.url", DATABASE_URL)


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
        context.configure(
            connection=connection, target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",  # needed for SQLite ALTERs
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
