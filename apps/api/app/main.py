from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import assistance, auth, dashboard, donations, health, notifications
from app.config import settings
from app.db import models  # noqa: F401
from app.db.session import Base, check_connection, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


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