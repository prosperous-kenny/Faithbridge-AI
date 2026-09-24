from fastapi import APIRouter

from app.schemas.auth import RegisterOut

router = APIRouter()


@router.post("/register", response_model=RegisterOut, status_code=201)
async def register() -> RegisterOut:
    return RegisterOut(message="registration not implemented in v0")


@router.post("/login")
async def login() -> dict:
    return {"message": "login not implemented in v0"}