"""`POST /ai/match-donors`: ranked, PII-free program matches for a donor.

The request merges saved preferences with optional inline overrides, hands the
program pool to the AI ranker, then re-attaches consent-clean open-case counts.
The response carries program and organization data only — never a beneficiary
identity (PRD §22). The same fail-closed discipline as assistance
classification applies: an AI payload that does not match the contract is a 503,
never silently passed through to a donor.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Role, require_role
from app.db.models import User
from app.db.session import get_session
from app.repositories import preferences as preferences_repo
from app.repositories import programs as programs_repo
from app.schemas.matching import MatchItem, MatchRequest, MatchResponse
from app.services.ai_client import ai_service_available
from app.services.ai_client import match_donors as call_ai_match_donors
from app.services.matching import (
    MATCHING_ENGINE,
    build_ai_payload,
    open_case_counts,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _validated_matches(ai_result: object, programs: list) -> list[dict]:
    """Fail closed on a noisy or out-of-contract AI match payload.

    ``match_donors`` lives on the trust boundary: it cannot return program ids
    from outside the pool it was given, scores outside [0, 1], or missing
    reason strings, or the API would be decorating and relaying an AI mistake.
    """
    if not isinstance(ai_result, dict) or ai_result.get("engine") != MATCHING_ENGINE:
        raise HTTPException(
            status_code=503, detail="AI service returned an invalid match payload"
        )
    matches = ai_result.get("matches")
    if not isinstance(matches, list):
        raise HTTPException(
            status_code=503, detail="AI service returned an invalid match payload"
        )
    allowed_ids = {program.id for program in programs}
    validated: list[dict] = []
    for match in matches:
        if not isinstance(match, dict):
            raise HTTPException(
                status_code=503, detail="AI service returned an invalid match payload"
            )
        program_id = match.get("program_id")
        score = match.get("match_score")
        reason = match.get("reason")
        if (
            program_id not in allowed_ids
            or not isinstance(score, (int, float))
            or not 0 <= score <= 1
            or not isinstance(reason, str)
        ):
            raise HTTPException(
                status_code=503, detail="AI service returned an invalid match payload"
            )
        validated.append(match)
    return validated


@router.post("/match-donors", response_model=MatchResponse)
async def match_donors(
    payload: MatchRequest,
    session: SessionDep,
    donor: Annotated[User, Depends(require_role(Role.DONOR))],
) -> MatchResponse:
    """Rank active programs for the donor. Saved preferences are the default;
    inline values in the request override them for this call only."""
    preference = await preferences_repo.get_for_donor(session, donor.id)
    causes = (
        list(payload.causes)
        if payload.causes is not None
        else (list(preference.causes) if preference else [])
    )
    budget = (
        payload.budget
        if payload.budget is not None
        else (preference.budget or 0 if preference else 0)
    )
    location = (
        payload.location
        if payload.location is not None
        else (preference.location if preference else None)
    )

    if not causes and (budget or 0) <= 0 and not location:
        raise HTTPException(
            status_code=400,
            detail="Save donor preferences first, or pass causes, budget or "
            "location with this request",
        )

    if not await ai_service_available():
        raise HTTPException(status_code=503, detail="AI service unavailable")

    programs = await programs_repo.list_programs(session, active_only=True)
    if not programs:
        return MatchResponse(engine=MATCHING_ENGINE, matches=[])

    ai_payload = build_ai_payload(
        causes=causes, budget=budget, location=location, programs=programs
    )
    ai_result = _validated_matches(await call_ai_match_donors(ai_payload), programs)

    counts = await open_case_counts(session, programs=programs)
    by_id = {program.id: program for program in programs}
    items = [
        MatchItem(
            program_id=match["program_id"],
            program_name=by_id[match["program_id"]].name,
            organization_name=(
                by_id[match["program_id"]].organization.name
                if by_id[match["program_id"]].organization
                else ""
            ),
            category=by_id[match["program_id"]].category,
            location=by_id[match["program_id"]].location,
            budget_needed=by_id[match["program_id"]].budget_needed,
            open_cases=counts[match["program_id"]],
            match_score=match["match_score"],
            matches_causes=match["matches_causes"],
            matches_budget=match["matches_budget"],
            matches_location=match["matches_location"],
            reason=match["reason"],
        )
        for match in ai_result
    ]
    return MatchResponse(engine=MATCHING_ENGINE, matches=items)