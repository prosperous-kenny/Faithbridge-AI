import httpx

from app.config import settings

_TIMEOUT = 5.0


async def ai_service_available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(f"{settings.ai_service_url}/health")
            return response.status_code == 200
    except httpx.HTTPError:
        return False


async def classify_need(text: str) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(
            f"{settings.ai_service_url}/classify",
            json={"text": text},
        )
        response.raise_for_status()
        payload = response.json()
        return {
            "category": payload["category"],
            "urgency_score": payload["urgency_score"],
            "priority": payload["priority"],
        }


async def match_donors(payload: dict) -> dict:
    """Ask the AI service to rank a program pool against the donor's
    preferences. The payload carries no beneficiary data, so the response is
    PII-free by construction (PRD §22)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(
            f"{settings.ai_service_url}/match-donors",
            json=payload,
        )
        response.raise_for_status()
        return response.json()