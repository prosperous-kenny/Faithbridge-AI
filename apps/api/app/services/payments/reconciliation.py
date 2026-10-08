"""Reconciliation between the payment provider and the donation ledger.

PRD §14's exit gate is "a donation is collected, allocated, distributed, and
reconciled end to end". Collection happens through a provider adapter
(``pay``); this module closes the loop: it compares what the provider reports
as captured against what the ledger records as paid and reports the variance.
A non-zero variance is a signal for an operator, not an automatic correction —
money movement is never written without an explicit transition.
"""

from __future__ import annotations

from app.db.models import Donation
from app.services.payments.provider import get_payment_provider
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Statuses the ledger considers money actually moved (paid or beyond).
_MOVED = ("paid", "allocated", "distributed")


async def ledger_paid_total(session: AsyncSession) -> int:
    """Sum of every donation the ledger agrees is paid (or further along)."""
    result = await session.execute(
        select(func.coalesce(func.sum(Donation.amount), 0)).where(
            Donation.status.in_(_MOVED)
        )
    )
    return int(result.scalar_one())


async def ledger_pending_total(session: AsyncSession) -> int:
    """Pledged money the provider has not seen yet (expected lead item)."""
    result = await session.execute(
        select(func.coalesce(func.sum(Donation.amount), 0)).where(
            Donation.status == "pledged"
        )
    )
    return int(result.scalar_one())


async def reconcile(session: AsyncSession, currency: str = "USD") -> dict:
    """Compare provider balance with the ledger-paid total.

    Returns the provider's captured balance, the ledger's paid total, the
    variance (ledger minus provider; 0 means the systems agree), and the
    expected in-flight lead item (pledged but not yet paid). The mock provider
    tracks captures in-process, so in a quiet test process the comparison is
    exactly the donation just routed.
    """
    provider = get_payment_provider()
    balance = await provider.sync_captured_balance(currency)
    paid = await ledger_paid_total(session)
    pending = await ledger_pending_total(session)
    return {
        "provider": provider.name,
        "provider_captured_amount": balance.captured_amount,
        "ledger_paid_total": paid,
        "pending_pledged_total": pending,
        "currency": balance.currency,
        "variance": paid - balance.captured_amount,
        "detail": "variance 0 means the provider and the ledger agree",
    }