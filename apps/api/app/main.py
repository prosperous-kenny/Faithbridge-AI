from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import assistance, auth, dashboard, donations, health
from app.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.1.0")
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
    return app


app = create_app()