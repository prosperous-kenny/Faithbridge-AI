"""Donation ledger lifecycle and allocation rules (Phase 4).

A donation moves through exactly PRD §8's lifecycle:

    pledged → paid → allocated → distributed

Each transition is one step: no skipping, no terminal-state edits, no
re-opening. Two domain rules guard where money lands:

1. **Same-organization allocation** — a donation may only be allocated to a
   beneficiary of the *same* organization the money was pledged to. Routing
   funds across organizations would break both the ledger and the impact
   attribution.
2. **No distribution without a target** — funds are distributed to a
   beneficiary, not to the void; the allocation target must be recorded
   before the ``distributed`` transition is allowed.

The lifecycle mirrors ``app/services/assistance.py`` so the two money/case
state machines read identically.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.db.models import Beneficiary, Donation

LIFE_CYCLE: dict[str, frozenset[str]] = {
    "pledged": frozenset({"paid"}),
    "paid": frozenset({"allocated"}),
    "allocated": frozenset({"distributed"}),
    "distributed": frozenset(),
}
VALID_STATUSES = frozenset(LIFE_CYCLE)


class DonationLifecycleError(ValueError):
    """Raised for illegal lifecycle transitions (mapped to 409 by the route)."""


class AllocationError(ValueError):
    """Raised when allocation rules are violated (mapped to 422 by the route).

    Separate from ``DonationLifecycleError`` so the route can tell "that was
    not an allowed step" (409, a state problem) from "that allocation cannot
    stand" (422, a payload problem).
    """


def transition_allowed(current: str, target: str) -> bool:
    return target in LIFE_CYCLE.get(current, frozenset())


def assert_transition(current: str, target: str) -> None:
    if not transition_allowed(current, target):
        raise DonationLifecycleError(
            f"Illegal donation transition: {current} -> {target}"
        )


def _now() -> datetime:
    # Stored timestamps are TIMESTAMP WITHOUT TIME ZONE; keep it naive UTC.
    return datetime.now(UTC).replace(tzinfo=None)


def assert_allocatable(donation: Donation, beneficiary: Beneficiary) -> None:
    """Enforce the allocation rules before any write.

    Must run after ``assert_transition(status, "allocated")``; it checks the
    money actually has an owner-side target that belongs to the same org.
    """
    if donation.organization_id != beneficiary.organization_id:
        raise AllocationError(
            "Allocation target must belong to the same organization as the donation"
        )


def apply_transition(
    donation: Donation, target: str, *, allocated_to_beneficiary_id: int | None = None
) -> Donation:
    """Stamp the timestamp that reaches a lifecycle step and move the status.

    Callers validate first (``assert_transition`` and, for allocation,
    ``assert_allocatable``): this function assumes the target is legal.
    """
    now = _now()
    if target == "paid":
        donation.paid_at = now
    elif target == "allocated":
        donation.allocated_at = now
        donation.allocated_to_beneficiary_id = allocated_to_beneficiary_id
    elif target == "distributed":
        donation.distributed_at = now
    donation.status = target
    return donation