"""Volunteer matching over skills and availability (PRD §14, Phase 3).

Same philosophy as the Phase 6 job matcher: deterministic, readable scoring
over nothing but the caller's own organization. Two components are blended —
direct skill coverage and availability-slot coverage — so a leader can see
exactly why a volunteer ranked where they did. The response carries the
volunteer's display name and user id only: no email, no phone, no address
(PRD §22 data minimization).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Volunteer

# The closed set of availability slots accepted by the API (schemas validate
# against it): two dimensions, three slots each, keeps matching comparable.
AVAILABILITY_SLOTS = frozenset(
    {
        "weekday_morning",
        "weekday_afternoon",
        "weekday_evening",
        "weekend_morning",
        "weekend_afternoon",
        "weekend_evening",
    }
)

SKILL_WEIGHT = 0.6
AVAILABILITY_WEIGHT = 0.4


async def match_volunteers(
    session: AsyncSession,
    *,
    organization_id: int,
    skills: list[str],
    availability: list[str] | None = None,
    limit: int = 5,
    exclude_ids: set[int] | None = None,
) -> list[dict]:
    """Rank active volunteers in one organization.

    With no requirements at all there is nothing to score, so an empty list
    is returned (same contract as ``match_jobs``). When only one dimension is
    supplied, it is scored alone: asking for weekend help should not rank a
    volunteer with zero relevant skills above one who has them.
    """
    required_slots = [slot for slot in (availability or []) if slot in AVAILABILITY_SLOTS]
    if not skills and not required_slots:
        return []

    stmt = (
        select(Volunteer)
        .where(
            Volunteer.organization_id == organization_id,
            Volunteer.is_active.is_(True),
        )
        .options(selectinload(Volunteer.user))
    )
    if exclude_ids:
        stmt = stmt.where(Volunteer.id.not_in(exclude_ids))
    volunteers = list((await session.execute(stmt)).scalars())

    wanted = [skill.lower() for skill in skills]
    scored: list[dict] = []
    for volunteer in volunteers:
        have = {skill.lower() for skill in volunteer.skills}
        matched_skills = [skill for skill in skills if skill.lower() in have]
        matched_slots = [
            slot for slot in required_slots if slot in volunteer.availability
        ]

        if wanted:
            skill_frac = len(matched_skills) / len(wanted)
        else:
            skill_frac = None
        if required_slots:
            availability_frac = len(matched_slots) / len(required_slots)
        else:
            availability_frac = 0.0

        # Blend only the dimensions that were actually asked for, so a
        # skills-only match reads as a percentage of skills covered.
        if skill_frac is not None and required_slots:
            raw = SKILL_WEIGHT * skill_frac + AVAILABILITY_WEIGHT * availability_frac
        elif skill_frac is not None:
            raw = skill_frac
        else:
            raw = availability_frac
        score = round(100 * raw)

        scored.append(
            {
                "volunteer_id": volunteer.id,
                "user_id": volunteer.user_id,
                "user_name": volunteer.user.full_name,
                "skills": volunteer.skills,
                "availability": volunteer.availability,
                "score": score,
                "matched_skills": matched_skills,
                "matched_availability": matched_slots,
            }
        )

    scored.sort(key=lambda item: (-item["score"], item["volunteer_id"]))
    return scored[:limit]
