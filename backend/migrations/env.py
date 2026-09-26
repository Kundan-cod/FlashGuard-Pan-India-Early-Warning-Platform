"""
Alembic migration environment (Track B, pending local run).

Pulls the database URL from app settings (env/.env) so no credentials are
committed, and enables PostGIS-aware autogenerate against the ORM metadata.
Run:  alembic -c alembic.ini upgrade head
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject the runtime DB URL (env-driven) rather than hard-coding it.
from app.config.settings import get_settings  # noqa: E402
config.set_main_option("sqlalchemy.url", get_settings().database_url)

# ORM metadata for autogenerate.
from app.database.models_orm import Base  # noqa: E402
target_metadata = Base.metadata if Base is not None else None


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"),
                       target_metadata=target_metadata, literal_binds=True,
                       dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import engine_from_config, pool
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        # IMPORTANT (SQLAlchemy 2.0): do NOT run any statement on `connection`
        # before context.configure()/begin_transaction(). Under 2.0 autobegin,
        # a pre-migration statement (e.g. CREATE EXTENSION) opens an implicit
        # transaction that Alembic's begin_transaction() then does NOT own — so
        # the migration DDL never gets committed and is rolled back at connection
        # close, with alembic still exiting 0. The migration body itself runs
        # `CREATE EXTENSION IF NOT EXISTS postgis;` as its first statement inside
        # Alembic's managed transaction, which is the correct place for it.
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
