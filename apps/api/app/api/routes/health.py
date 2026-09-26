from fastapi import APIRouter

from app.db.session import check_connection

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "faithbridge-api"}


@router.get("/health/ready")
async def readiness() -> dict:
    db_ok = await check_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "faithbridge-api",
        "database": "up" if db_ok else "down",
    }