from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.assistance import AssistanceRequestOut
from app.schemas.fraud import FraudFlagOut


class VoiceIntakeIn(BaseModel):
    """A voice submission: a transcript, an audio blob, or both.

    At least one of the two must be present (enforced in the route: Pydantic
    cannot express "one of these" cleanly on optional fields). When both are
    given, the client transcript wins — it came from the same capture that
    produced the audio — and the audio is discarded after screening.
    """

    organization_id: int
    transcript: str | None = Field(default=None, min_length=10, max_length=2000)
    audio_base64: str | None = Field(default=None, max_length=4_000_000)
    mime_type: str | None = Field(default=None, max_length=100)


class VoiceIntakeOut(BaseModel):
    request: AssistanceRequestOut
    # Which side produced the text: the browser ("client") or the
    # configured transcription provider ("provider").
    transcription: Literal["client", "provider"]
    fraud_flags: list[FraudFlagOut] = Field(default_factory=list)
