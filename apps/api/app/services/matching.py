"""Candidate preparation and PII-safe enrichment for donor matching (Phase 3).

The AI service stays stateless about our database: this module turns programs
and donor preferences into the payload it ranks, then re-attaches PII-free
context (a consent-clean open-case count per program) to the ranked results.
No beneficiary identity ever crosses this boundary (PRD §22).
"""

from __future__ import annotations

from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AssistanceRequest, Beneficiary

# The one engine the API accepts from the AI service; anything else fails
# closed, exactly like an out-of-range classification.
MATCHING_ENGINE = "tfidf-sparse-embedding"

# Cases still being handled count toward a program's open load once triaged;
# terminal states mean the need was resolved or declined.
PENDING_STATUSES = ("submitted", "triaged", "approved")


def build_ai_payload(
    *,
    causes: list[str],
    budget: float,
    location: str | None,
    programs: list,
) -> dict:
    """Serialize programs + preferences for the AI `/match-donors` endpoint."""
    return {
        "causes": list(causes),
        "budget": float(budget or 0),
        "location": location,
        "programs": [
            {
                "program_id": program.id,
                "name": program.name,
                "category": program.category,
                "description": program.description or "",
                "location": program.location,
                "budget_needed": program.budget_needed,
                "organization_name": (
                    program.organization.name if program.organization else ""
                ),
            }
            for program in programs
        ],
    }


async def open_case_counts(
    session: AsyncSession, *, programs: list
) -> dict[int, int]:
    """Consent-clean open-case counts per program, keyed by program id.

    A case counts only when it is pending *and* its beneficiary is anonymous
    (no linked account to name) or has explicitly consented. A linked person
    who has not consented is never surfaced to donor-facing endpoints, not even
    as a number, because consent gates the sharing of beneficiary information
    with donors (PRD §22). The count is deliberately aggregate: it proves live
    demand without exposing who.
    """
    if not programs:
        return {}
    pairs = {(program.organization_id, program.category) for program in programs}
    result = await session.execute(
        select(
            AssistanceRequest.organization_id,
            AssistanceRequest.category,
            func.count(),
        )
        .join(Beneficiary, Beneficiary.id == AssistanceRequest.beneficiary_id)
        .where(
            AssistanceRequest.status.in_(PENDING_STATUSES),
            or_(Beneficiary.consented_at.is_not(None), Beneficiary.user_id.is_(None)),
            tuple_(
                AssistanceRequest.organization_id, AssistanceRequest.category
            ).in_(pairs),
        )
        .group_by(AssistanceRequest.organization_id, AssistanceRequest.category)
    )
    by_pair = {(organization_id, category): count for organization_id, category, count in result.all()}
    return {
        program.id: int(by_pair.get((program.organization_id, program.category), 0))
        for program in programs
    }