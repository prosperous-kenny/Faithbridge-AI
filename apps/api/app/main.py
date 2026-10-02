from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import assistance, auth, dashboard, donations, health, notifications
from app.config import settings
from app.db import models  # noqa: F401
from app.db.session import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Schema is owned by Alembic (Phase 0). create_all is no longer called at
    # startup: it silently diverges from the migration history and hides drift.
    # Run `alembic upgrade head` before starting the API.
    if not settings.auto_create_schema:
        async with engine.connect() as conn:
            applied = await conn.run_sync(_schema_is_current)
        if not applied:
            raise RuntimeError(
                "Database schema is not at the current Alembic revision. "
                "Run `alembic upgrade head` in apps/api before starting the API."
            )
    else:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


def _schema_is_current(connection) -> bool:
    """True when alembic_version matches the latest migration head."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()

    row = connection.execute(
        text("SELECT version_num FROM alembic_version")
    ).scalar()
    return row == head


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    prefix = settings.api_v1_prefix
    app.include_router(health.router, tags=["system"])
    app.include_router(auth.router, prefix=f"{prefix}/auth", tags=["auth"])
    app.include_router(assistance.router, prefix=f"{prefix}/assistance", tags=["assistance"])
    app.include_router(donations.router, prefix=f"{prefix}/donations", tags=["donations"])
    app.include_router(dashboard.router, prefix=f"{prefix}/dashboard", tags=["dashboard"])
    app.include_router(
        notifications.router, prefix=f"{prefix}/notifications", tags=["notifications"]
    )
    return app


app = create_app()