from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class FraudFlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int | None
    request_id: int | None
    rule: str
    severity: str
    detail: str | None
    status: str
    created_at: datetime


class FraudFlagUpdateIn(BaseModel):
    # "open" allows a dismissed or confirmed flag to be re-opened for review.
    status: Literal["open", "confirmed", "dismissed"]
