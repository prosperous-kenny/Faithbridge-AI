from pydantic import BaseModel, Field


class PayDonationIn(BaseModel):
    """Confirmation that a donor wants the pledge captured now.

    Empty by design: the provider creates the intent and immediately captures,
    which is the mock (and Stripe's payment-intent + capture) flow. The field
    exists so the contract does not depend on an undocumented empty body.
    """

    provider_token: str | None = Field(default=None, max_length=200)


class PaymentResultOut(BaseModel):
    donation_id: int
    status: str
    provider: str
    provider_reference: str
    amount: int
    currency: str


class ReconcileOut(BaseModel):
    provider: str
    provider_captured_amount: int
    ledger_paid_total: int
    pending_pledged_total: int
    currency: str
    variance: int
    detail: str