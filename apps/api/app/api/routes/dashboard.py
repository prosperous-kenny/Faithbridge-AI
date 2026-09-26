from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AssistanceRequest,
    Beneficiary,
    Donation,
    Organization,
    Placement,
    Program,
    User,
)
from app.db.session import get_session

router = APIRouter()


@router.get("/stats")
async def stats(session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    async def count(model: type) -> int:
        result = await session.execute(select(func.count()).select_from(model))
        return int(result.scalar_one())

    return {
        "organizations": await count(Organization),
        "users": await count(User),
        "programs": await count(Program),
        "beneficiaries": await count(Beneficiary),
        "assistance_requests": await count(AssistanceRequest),
        "donations": await count(Donation),
        "placements": await count(Placement),
    }
