"""Employment Empowerment Module: job matching over placements (PRD §14).

A placement holds a role, employer, and the skills the job-seeker had at
placement. Matching a *beneficiary* to prospective roles scores every active
(``status != graduated``) placement in their organization by token overlap
between the beneficiary's skills and the placement's role + employer + skills,
mirroring the Phase 3 donor-matching engine's approach: deterministic,
readable, and over no PII beyond the caller's own organization.
"""

from __future__ import annotations

import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Placement

_STOPWORDS = {
    "and",
    "the",
    "of",
    "for",
    "in",
    "to",
    "at",
    "junior",
    "senior",
    "assistant",
}


def _tokens(*parts: str) -> Counter[str]:
    words = re.findall(r"[a-z0-9]+", " ".join(parts).lower())
    counter: Counter[str] = Counter()
    for word in words:
        if word not in _STOPWORDS:
            counter[word] += 1
    return counter


async def match_jobs(
    session: AsyncSession,
    *,
    organization_id: int,
    skills: list[str],
    limit: int = 5,
    exclude_ids: set[int] | None = None,
) -> list[dict]:
    """Score open placements against a list of skills.

    Returns dicts with ``placement_id``, ``employer``, ``role_title``,
    ``score`` (0..100), and ``matched_skills`` — enough for a leader to explain
    any recommendation.
    """
    stmt = select(Placement).where(
        Placement.organization_id == organization_id,
        Placement.status != "graduated",
    )
    if exclude_ids:
        stmt = stmt.where(Placement.id.not_in(exclude_ids))
    placements = list((await session.execute(stmt)).scalars())

    if not skills:
        return []

    scored: list[dict] = []
    for placement in placements:
        direct = sum(1 for s in skills if s.lower() in placement.skills)
        direct_frac = direct / len(skills)
        placement_tokens = _tokens(placement.role_title, placement.employer, *placement.skills)
        overlap = sum((placement_tokens & _tokens(*skills)).values())
        token_frac = overlap / max(1, len(_tokens(*skills)))
        score = round(100 * (0.6 * direct_frac + 0.4 * token_frac))
        matched = [s for s in skills if s.lower() in placement.skills]
        scored.append(
            {
                "placement_id": placement.id,
                "employer": placement.employer,
                "role_title": placement.role_title,
                "status": placement.status,
                "score": round(score),
                "matched_skills": matched,
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]