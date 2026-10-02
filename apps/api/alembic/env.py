import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.config import settings
from app.db import models  # noqa: F401
from app.db.session import Base

config = context.config

# Resolve the URL in priority order: an explicit sqlalchemy.url already set by
# the caller (the migration smoke test points this at a throwaway database),
# then a -x sqlalchemy.url argument, then the app settings. settings is only a
# fallback, so tests can never accidentally migrate a real database.
_url = (
    context.get_x_argument(as_dictionary=True).get("sqlalchemy.url")
    or config.get_main_option("sqlalchemy.url")
    or settings.database_url
)
if not _url:
    raise RuntimeError("No database URL configured for Alembic")
config.set_main_option("sqlalchemy.url", _url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    # Alembic's async template calls asyncio.run(), which fails when the CLI
    # is invoked from inside a running loop (the migration smoke test does
    # exactly that). Reuse the running loop when there is one.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(run_async_migrations())
    else:
        raise RuntimeError(
            "alembic migrations cannot run inside an active event loop; "
            "invoke alembic from a synchronous entrypoint"
        )


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
