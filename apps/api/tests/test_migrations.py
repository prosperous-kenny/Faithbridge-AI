"""Verify Alembic migrations apply and roll back cleanly.

The Phase 0 exit gate requires `alembic upgrade head` then `downgrade base`
to both succeed. This runs both against a throwaway database so the
developer's working data is never touched.

Run with:  python -m tests.test_migrations
"""

import asyncio
import os
import re
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

TEST_DB = "faithbridge_alembic_test"


def _base_url() -> str:
    env_file = API_DIR / ".env"
    url = os.getenv("DATABASE_URL", "")
    if not url and env_file.exists():
        match = re.search(
            r"^DATABASE_URL=(.+)$", env_file.read_text(encoding="utf-8"), re.MULTILINE
        )
        if match:
            url = match.group(1).strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


async def _reset(url: str) -> None:
    admin_url = url.rsplit("/", 1)[0] + "/postgres"
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}"'))
        await conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    await engine.dispose()


def _run_in_thread(fn):
    """Run fn on a worker thread and re-raise anything it threw."""
    import threading

    box: dict[str, BaseException] = {}

    def _target() -> None:
        try:
            fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller
            box["exc"] = exc

    thread = threading.Thread(target=_target)
    thread.start()
    thread.join()
    return box.get("exc")


def _alembic(url: str, action: str, revision: str) -> None:
    """Run an Alembic command on a worker thread.

    Alembic's env.py calls asyncio.run(), which cannot be nested inside the
    event loop this script is already running on, so the command is pushed to
    a thread where no loop is active.
    """
    from alembic.config import Config

    from alembic import command

    def _invoke() -> None:
        cfg = Config(str(API_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(API_DIR / "alembic"))
        # env.py prefers an explicitly configured URL over settings.database_url,
        # so this points the migration at the throwaway database.
        cfg.set_main_option("sqlalchemy.url", url)
        getattr(command, action)(cfg, revision)

    err = _run_in_thread(_invoke)
    if err is not None:
        raise err


async def main() -> int:
    base_url = _base_url()
    test_url = base_url.rsplit("/", 1)[0] + f"/{TEST_DB}"

    await _reset(base_url)

    print(f"  reset {TEST_DB}")

    _alembic(test_url, "upgrade", "head")
    print("  upgrade head OK")

    engine = create_async_engine(test_url)
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "select table_name from information_schema.tables "
                "where table_schema = 'public' order by table_name"
            )
        )
        tables = [r[0] for r in rows]
    await engine.dispose()
    print(f"  {len(tables)} tables: {', '.join(tables)}")

    _alembic(test_url, "downgrade", "base")
    print("  downgrade base OK")

    engine = create_async_engine(test_url)
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "select table_name from information_schema.tables "
                "where table_schema = 'public' and table_name <> 'alembic_version' "
                "order by table_name"
            )
        )
        leftover = [r[0] for r in rows]
    await engine.dispose()

    # alembic_version is Alembic's own bookkeeping table and is expected to
    # survive; every application table must be gone.
    if leftover:
        print(f"  FAIL: {len(leftover)} app table(s) survived: {', '.join(leftover)}")
        return 1

    print("  all application tables dropped (alembic_version retained by design)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
