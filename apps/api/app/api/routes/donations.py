from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_donations() -> dict:
    return {"items": []}