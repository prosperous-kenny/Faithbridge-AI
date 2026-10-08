import asyncio
import os
from pathlib import Path

import pytest
from sqlalchemy import text

os.environ.setdefault("FAITHBRIDGE_ENV", "test")

API_DIR = Path(__file__).resolve().parent.parent
TEST_DB_NAME = os.getenv("TEST_DATABASE_NAME", "faithbridge_test")


def _raw_database_url() -> str:
    """DATABASE_URL from the process environment, else from apps/api/.env."""
    url = os.environ.get("DATABASE_URL", "")
    env_file = API_DIR / ".env"
    if not url and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip()
                break
    if not url:
        pytest.exit(
            "DATABASE_URL is not set; tests need a PostgreSQL server to run "
            "against a throwaway database.",
            returncode=1,
        )
    return url


# Redirect the app at a throwaway database BEFORE app.config or app.db.session is
# imported anywhere. `create_all` on the configured database used to wipe real
# local data and desynchronise the physical schema from alembic_version; tests
# must never touch the developer's or production database.
_SERVER_URL = _raw_database_url().rsplit("/", 1)[0]
os.environ["DATABASE_URL"] = f"{_SERVER_URL}/{TEST_DB_NAME}"
_ADMIN_URL = f"{_SERVER_URL}/postgres"


async def _reset_database(url: str, database: str, create: bool) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
        if create:
            await conn.execute(text(f'CREATE DATABASE "{database}"'))
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _migrated_test_database():
    """Build the test database with Alembic, so tests run against the real schema.

    Running migrations (rather than metadata.create_all) is what makes the test
    suite meaningful: it fails if the migration chain and the ORM models ever
    disagree about foreign keys or indexes.
    """
    from alembic.config import Config

    from alembic import command

    asyncio.run(_reset_database(_ADMIN_URL, TEST_DB_NAME, create=True))

    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(cfg, "head")

    yield

    asyncio.run(_reset_database(_ADMIN_URL, TEST_DB_NAME, create=False))


@pytest.fixture
async def clean_db():
    """Empty every table between tests without dropping the schema."""
    from app.db.session import Base, engine

    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    yield


@pytest.fixture
def client():
    """TestClient with the lifespan running, so tests exercise the real app.

    The lifespan validates auth configuration and verifies the schema is at
    the Alembic head; a client built outside the context manager skips both,
    which would let a suite pass against a process that cannot actually start.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
async def make_user(clean_db):
    """Create an active, password-backed user of the requested role."""
    import secrets

    from app.db.session import SessionFactory
    from app.repositories import users as users_repo

    async def _make(
        role: str,
        *,
        email: str | None = None,
        password: str = "correct-horse-1",
        is_active: bool = True,
        organization_id: int | None = None,
    ):
        async with SessionFactory() as session:
            user = await users_repo.create(
                session,
                email=email or f"{role}-{secrets.token_hex(5)}@example.org",
                full_name=role.replace("_", " ").title(),
                role=role,
                password=password,
                is_active=is_active,
                organization_id=organization_id,
            )
            await session.commit()
            return user

    return _make


@pytest.fixture
def login(client):
    """Exchange credentials for a bearer header, failing loudly on a bad login."""

    def _login(user, password: str = "correct-horse-1") -> dict[str, str]:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": password},
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login
