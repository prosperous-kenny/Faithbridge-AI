from fastapi import APIRouter, HTTPException

from app.schemas.assistance import AssistanceRequestIn, AssistanceRequestOut
from app.services.ai_client import ai_service_available, classify_need

router = APIRouter()


@router.post("/requests", response_model=AssistanceRequestOut, status_code=201)
async def create_request(payload: AssistanceRequestIn) -> AssistanceRequestOut:
    if not await ai_service_available():
        raise HTTPException(status_code=503, detail="AI service unavailable")
    classification = await classify_need(payload.description)
    return AssistanceRequestOut(
        id="req-0001",
        description=payload.description,
        **classification,
        status="submitted",
    )