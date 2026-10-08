"""Payment provider interface and adapters (PRD §14 payout orchestration).

The ledger records commitments (``pledged``) and money movement; *how* money
moves is delegated to a :class:`PaymentProvider`. The default ``mock`` adapter
exercises the full contract — intent creation, capture, balance sync — with
deterministic fake identifiers, so development and CI are offline and the
reconciliation logic is real. A real Stripe adapter exists and is constructed
only when ``STRIPE_SECRET_KEY`` is set, never silently dropped.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.config import settings

CAPTURED_STATUS = "succeeded"


class PaymentProviderError(RuntimeError):
    """The provider rejected an operation (mapped to 502 by routes)."""


@dataclass(frozen=True)
class PaymentIntent:
    """The provider's view of one payment attempt."""

    reference: str
    amount: int
    currency: str
    status: str  # requires_capture | succeeded | failed


@dataclass(frozen=True)
class ProviderBalance:
    """Money the provider currently reports as captured for the platform."""

    captured_amount: int
    currency: str
    detail: str

    @property
    def variance(self) -> int:  # type: ignore[override]
        raise NotImplementedError

    def compute_variance(self, ledger_paid: int) -> int:
        """Ledger minus provider; zero means the two sides agree."""
        return ledger_paid - self.captured_amount


@runtime_checkable
class PaymentProvider(Protocol):
    """Contract every adapter must satisfy."""

    name: str

    async def create_payment_intent(self, *, amount: int, currency: str = "USD") -> PaymentIntent:
        """Reserve a payment of ``amount`` minor units on the provider."""
        ...

    async def capture_payment(self, reference: str) -> PaymentIntent:
        """Capture a reserved payment; return its final status."""
        ...

    async def sync_captured_balance(self, currency: str = "USD") -> ProviderBalance:
        """Total amount the provider currently holds captured for the platform."""
        ...


class MockPaymentProvider:
    """Deterministic in-process adapter. ``captured`` tracks money captured."""

    name = "mock"

    def __init__(self) -> None:
        self._captured = 0
        self._intents: dict[str, PaymentIntent] = {}

    async def create_payment_intent(self, *, amount: int, currency: str = "USD") -> PaymentIntent:
        reference = f"mock_pi_{secrets.token_hex(8)}"
        intent = PaymentIntent(
            reference=reference,
            amount=amount,
            currency=currency,
            status="requires_capture",
        )
        self._intents[reference] = intent
        return intent

    async def capture_payment(self, reference: str) -> PaymentIntent:
        intent = self._intents.get(reference)
        if intent is None:
            raise PaymentProviderError(f"unknown payment intent: {reference}")
        captured = PaymentIntent(
            reference=reference,
            amount=intent.amount,
            currency=intent.currency,
            status=CAPTURED_STATUS,
        )
        self._intents[reference] = captured
        self._captured += intent.amount
        return captured

    async def sync_captured_balance(self, currency: str = "USD") -> ProviderBalance:
        return ProviderBalance(
            captured_amount=self._captured,
            currency=currency,
            detail=f"{self.name} adapter: {self._captured} {currency} captured",
        )


class StripePaymentProvider:
    """Stripe adapter. Requires ``stripe`` and a secret key; raises otherwise.

    Constructing an adapter with missing configuration is a loud error so a
    maintainer notices a misspelt key instead of silently paying through the
    wrong provider.
    """

    name = "stripe"

    def __init__(self) -> None:
        if not settings.stripe_secret_key:
            raise PaymentProviderError("STRIPE_SECRET_KEY is not set")
        try:
            import stripe  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise PaymentProviderError("stripe package is not installed") from exc
        self._stripe = stripe
        self._stripe.api_key = settings.stripe_secret_key

    async def create_payment_intent(self, *, amount: int, currency: str = "USD") -> PaymentIntent:
        intent = self._stripe.PaymentIntent.create(amount=amount, currency=currency)
        return PaymentIntent(
            reference=intent["id"],
            amount=amount,
            currency=currency,
            status=intent["status"],
        )

    async def capture_payment(self, reference: str) -> PaymentIntent:
        intent = self._stripe.PaymentIntent.retrieve(reference)
        if intent["status"] == "requires_capture":
            intent = self._stripe.PaymentIntent.capture(reference)
        return PaymentIntent(
            reference=reference,
            amount=intent["amount"],
            currency=intent["currency"],
            status=intent["status"],
        )

    async def sync_captured_balance(self, currency: str = "USD") -> ProviderBalance:
        balance = self._stripe.Balance.retrieve()
        captured = sum(
            b["amount"] for b in balance["available"] if b["currency"] == currency
        )
        return ProviderBalance(
            captured_amount=captured,
            currency=currency,
            detail=f"stripe balance {captured} {currency} available",
        )


_provider: PaymentProvider | None = None


def get_payment_provider() -> PaymentProvider:
    """Cache the configured provider for the process lifetime."""
    global _provider
    if _provider is None:
        if settings.payments_provider == "stripe":
            _provider = StripePaymentProvider()
        elif settings.payments_provider == "mock":
            _provider = MockPaymentProvider()
        else:
            raise PaymentProviderError(
                f"PAYMENTS_PROVIDER={settings.payments_provider!r} is not mock or stripe"
            )
    return _provider