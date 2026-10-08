"""Async helpers for building rows the route tests need.

Deliberately plain functions rather than fixtures: most tests want one
specific row, and a fixture per shape would be harder to read than a call.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AssistanceRequest,
    Beneficiary,
    Donation,
    DonorPreference,
    ImpactEvent,
    ImpactRollup,
    Organization,
    OrgImpactConfig,
    Placement,
    Program,
    User,
)

# Stored timestamps are TIMESTAMP WITHOUT TIME ZONE, so the value must be
# naive; UTC is used as the base to keep it independent of the host clock's
# local zone.
_NOW = datetime.now(UTC).replace(tzinfo=None)


async def create_organization(session: AsyncSession, *, name: str = "Test Church") -> Organization:
    org = Organization(name=name, org_type="church")
    session.add(org)
    await session.flush()
    return org


async def create_linked_user(
    session: AsyncSession,
    *,
    email: str,
    full_name: str = "Linked Person",
    role: str = "community_member",
) -> User:
    user = User(email=email, full_name=full_name, role=role, is_active=True)
    session.add(user)
    await session.flush()
    return user


async def create_assistance_request(
    session: AsyncSession,
    *,
    consented: bool = True,
    linked_user: bool = True,
    priority: str = "high",
    category: str = "housing",
    organization: Organization | None = None,
) -> tuple[AssistanceRequest, Beneficiary, User | None]:
    """One assistance request plus its beneficiary.

    ``consented`` controls PRD §22 consent; ``linked_user`` controls whether
    there is a person behind it to expose. Both combinations matter: PII must
    stay hidden unless consent exists *and* there is something to name.
    """
    org = organization or await create_organization(session)
    user: User | None = None
    if linked_user:
        user = await create_linked_user(
            session,
            email=f"beneficiary-{org.id}-{await _next_sequence(session)}@example.org",
        )
    beneficiary = Beneficiary(
        organization_id=org.id,
        user_id=user.id if user else None,
        household_size=4,
        consented_at=_NOW if consented else None,
        created_at=_NOW,
        updated_at=_NOW,
    )
    session.add(beneficiary)
    await session.flush()

    request = AssistanceRequest(
        beneficiary_id=beneficiary.id,
        organization_id=org.id,
        description="Rent is overdue and we need help before the end of the month.",
        category=category,
        urgency_score=70,
        priority=priority,
        status="submitted",
        created_at=_NOW,
        updated_at=_NOW,
    )
    session.add(request)
    await session.flush()
    return request, beneficiary, user


async def create_donation(
    session: AsyncSession,
    *,
    donor: User,
    amount: int = 5000,
    organization: Organization | None = None,
    program: Program | None = None,
    status: str = "pledged",
) -> Donation:
    org = organization or await create_organization(session)
    donation = Donation(
        donor_id=donor.id,
        organization_id=org.id,
        program_id=program.id if program else None,
        amount=amount,
        currency="USD",
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
    )
    session.add(donation)
    await session.flush()
    return donation


async def create_impact_event(
    session: AsyncSession,
    *,
    organization: Organization,
    metric: str = "families_supported",
    value: int = 1,
    occurred_at=None,
) -> ImpactEvent:
    event = ImpactEvent(
        organization_id=organization.id,
        metric=metric,
        value=value,
        occurred_at=occurred_at or _NOW,
        created_at=_NOW,
    )
    session.add(event)
    await session.flush()
    return event


async def create_impact_config(
    session: AsyncSession,
    *,
    organization: Organization,
    weights: dict[str, float] | None = None,
    targets: dict[str, float] | None = None,
) -> OrgImpactConfig:
    from app.services.impact import DEFAULT_TARGETS, DEFAULT_WEIGHTS

    merged_weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    merged_targets = {**DEFAULT_TARGETS, **(targets or {})}
    config = OrgImpactConfig(
        organization_id=organization.id,
        families_weight=merged_weights["families"],
        education_weight=merged_weights["education"],
        employment_weight=merged_weights["employment"],
        food_security_weight=merged_weights["food_security"],
        healthcare_weight=merged_weights["healthcare"],
        families_target=merged_targets["families"],
        education_target=merged_targets["education"],
        employment_target=merged_targets["employment"],
        food_security_target=merged_targets["food_security"],
        healthcare_target=merged_targets["healthcare"],
    )
    session.add(config)
    await session.flush()
    return config


async def create_placement(
    session: AsyncSession,
    *,
    beneficiary: Beneficiary,
    employer: str = "Acme Corp",
    role_title: str = "Junior Technician",
    organization: Organization | None = None,
) -> Placement:
    org = organization or await create_organization(session)
    placement = Placement(
        beneficiary_id=beneficiary.id,
        organization_id=org.id,
        employer=employer,
        role_title=role_title,
        placed_at=_NOW,
        created_at=_NOW,
        updated_at=_NOW,
    )
    session.add(placement)
    await session.flush()
    return placement


async def create_impact_rollup(
    session: AsyncSession,
    *,
    organization: Organization,
    metric: str,
    total: int,
    period_start=None,
    period_end=None,
) -> ImpactRollup:
    start = period_start or _NOW.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    import datetime as _dt

    start = start.replace(tzinfo=None)
    rollup = ImpactRollup(
        organization_id=organization.id,
        period_start=start,
        period_end=period_end
        or (start + _dt.timedelta(days=31)).replace(tzinfo=None),
        metric=metric,
        total=total,
        created_at=_NOW,
    )
    session.add(rollup)
    await session.flush()
    return rollup


async def create_program(
    session: AsyncSession,
    *,
    organization: Organization | None = None,
    name: str = "Shelter Support",
    category: str = "housing",
    description: str | None = None,
    location: str | None = None,
    budget_needed: int | None = None,
    is_active: bool = True,
) -> Program:
    org = organization or await create_organization(session)
    program = Program(
        organization_id=org.id,
        name=name,
        category=category,
        description=description,
        location=location,
        budget_needed=budget_needed,
        is_active=is_active,
    )
    session.add(program)
    await session.flush()
    return program


async def create_donor_preference(
    session: AsyncSession,
    *,
    donor: User,
    causes: list[str] | None = None,
    budget: float | None = None,
    location: str | None = None,
) -> DonorPreference:
    preference = DonorPreference(
        donor_id=donor.id,
        causes=causes or [],
        budget=budget,
        location=location,
    )
    session.add(preference)
    await session.flush()
    return preference


async def _next_sequence(session: AsyncSession) -> int:
    from sqlalchemy import func, select

    count = await session.execute(select(func.count()).select_from(User))
    return int(count.scalar_one()) + 1
