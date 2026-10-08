"""Append-only impact feed and the Community Impact Score (PRD §8, §15).

The impact ledger is the measurement backbone for Donations Distributed and
the Community Impact Score. Domain actions record events (a fulfilled case,
a distributed donation, a placement); the score normalises each dimension
against a per-organisation target and weights them per-organisation, defaulting
to the PRD §15 baseline:

    Impact Score = 0.25*Families + 0.20*Education + 0.20*Employment
                 + 0.20*Food Security + 0.15*Healthcare

The score is *reproducible from config alone*: a caller can recompute it by
hand from the config row (or its absence) plus the event feed, which is what
the exit-gate test asserts.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import impact as impact_repo

DIMENSIONS = ("families", "education", "employment", "food_security", "healthcare")

# Canonical event metrics -> score dimension. Aliases (domain wrappers for the
# same outcome) collapse into one dimension so the feed can use the term an
# organisation already reports with.
METRIC_DIMENSION: dict[str, str] = {
    "families_supported": "families",
    "education_outcomes": "education",
    "school_fees_sponsored": "education",
    "employment_success": "employment",
    "employment_placements": "employment",
    "food_security": "food_security",
    "meals_provided": "food_security",
    "healthcare_support": "healthcare",
    "medical_cases_supported": "healthcare",
}

# Reporting-only metrics that never feed the score (they belong to ledgers the
# score does not own, e.g. money distributed).
REPORT_ONLY_METRICS: dict[str, str] = {
    "donations_distributed": "value of donations distributed in the period",
}

VALID_METRICS = frozenset({*METRIC_DIMENSION, *REPORT_ONLY_METRICS})

DEFAULT_WEIGHTS: dict[str, float] = {
    "families": 0.25,
    "education": 0.20,
    "employment": 0.20,
    "food_security": 0.20,
    "healthcare": 0.15,
}
DEFAULT_TARGETS: dict[str, float] = {dimension: 100.0 for dimension in DIMENSIONS}


async def record_event(
    session: AsyncSession,
    *,
    organization_id: int,
    metric: str,
    value: int,
    occurred_at: datetime | None = None,
):
    """Append one impact event. Domain actions call this; there is no update
    or delete path (append-only, PRD §8 impact feed)."""
    if metric not in VALID_METRICS:
        raise ValueError(
            f"Unknown impact metric {metric!r}; expected one of "
            + ", ".join(sorted(VALID_METRICS))
        )
    if value < 0:
        raise ValueError("Impact event value cannot be negative")
    return await impact_repo.create_event(
        session,
        organization_id=organization_id,
        metric=metric,
        value=value,
        occurred_at=occurred_at,
    )


def dimension_values(events: list) -> dict[str, int]:
    """Collapse the event feed into per-dimension raw totals."""
    totals: dict[str, int] = {}
    for event in events:
        dimension = METRIC_DIMENSION.get(event.metric)
        if dimension is None:
            continue
        totals[dimension] = totals.get(dimension, 0) + event.value
    return totals


async def community_impact_score(
    session: AsyncSession,
    *,
    organization_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict:
    """Compute the 0-100 Community Impact Score for one organization.

    Uses the organisation's config row when present, the PRD baseline
    otherwise. Returns the score plus its component breakdown so a report can
    show *why* a score is what it is.
    """
    config = await impact_repo.get_config(session, organization_id)
    if config is None:
        weights: dict[str, float] = dict(DEFAULT_WEIGHTS)
        targets: dict[str, float] = dict(DEFAULT_TARGETS)
    else:
        weights = {
            "families": config.families_weight,
            "education": config.education_weight,
            "employment": config.employment_weight,
            "food_security": config.food_security_weight,
            "healthcare": config.healthcare_weight,
        }
        targets = {
            "families": config.families_target,
            "education": config.education_target,
            "employment": config.employment_target,
            "food_security": config.food_security_target,
            "healthcare": config.healthcare_target,
        }
    events = await impact_repo.events_in_period(
        session, organization_id=organization_id, start=start, end=end
    )
    raw = dimension_values(events)
    components: dict[str, float] = {}
    for dimension in DIMENSIONS:
        cap = max(0.0, targets[dimension])
        if cap == 0:
            components[dimension] = 0.0
            continue
        components[dimension] = min(100.0, round(100.0 * raw.get(dimension, 0) / cap))
    score = round(sum(weights[d] * components[d] for d in DIMENSIONS))
    return {
        "score": score,
        "components": components,
        "weights": weights,
        "targets": targets,
        "start": start,
        "end": end,
    }