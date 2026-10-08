"""Voice intake: audio-to-text behind a provider interface (PRD §14).

The intake route accepts either a transcript the client produced itself
(browser SpeechRecognition) or a base64 audio blob to transcribe here. As
with payments and WhatsApp, development and CI run the "mock" provider,
which has no speech-to-text backend: an audio-only submission then fails
closed at the route with 503 rather than inventing words. Raw audio is
decoded, transcribed, and dropped — it is never persisted (PRD §22 data
minimization); only the transcript rides the normal classification pipeline.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx

from app.config import settings

_TIMEOUT = 15.0


class TranscriptionError(RuntimeError):
    """No usable transcript could be produced for the supplied audio."""


@runtime_checkable
class TranscriptionProvider(Protocol):
    async def transcribe(self, audio: bytes, *, mime_type: str) -> str: ...


class MockTranscriptionProvider:
    """Stand-in with no speech-to-text backend.

    Failing loudly is the point: silently returning an empty or guessed
    transcript would send fabricated text into the classification pipeline.
    """

    async def transcribe(self, audio: bytes, *, mime_type: str) -> str:
        raise TranscriptionError(
            "no speech-to-text provider configured (VOICE_PROVIDER=mock)"
        )


class HttpTranscriptionProvider:
    """POSTs the audio blob to VOICE_TRANSCRIPTION_URL; expects {"text": ...}.

    Generic on purpose: any self-hosted Whisper wrapper or cloud STT gateway
    works by returning that one JSON field.
    """

    def __init__(self, url: str, api_key: str) -> None:
        if not url:
            raise TranscriptionError(
                "VOICE_PROVIDER=http requires VOICE_TRANSCRIPTION_URL to be set"
            )
        self._url = url
        self._api_key = api_key

    async def transcribe(self, audio: bytes, *, mime_type: str) -> str:
        headers = {"Content-Type": mime_type or "application/octet-stream"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(self._url, content=audio, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TranscriptionError(f"transcription request failed: {exc}") from exc
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str):
            raise TranscriptionError(
                "transcription provider response had no 'text' field"
            )
        return text.strip()


def get_transcription_provider() -> TranscriptionProvider:
    if settings.voice_provider == "mock":
        return MockTranscriptionProvider()
    if settings.voice_provider == "http":
        return HttpTranscriptionProvider(
            settings.voice_transcription_url,
            settings.voice_transcription_api_key,
        )
    raise RuntimeError(
        f"VOICE_PROVIDER={settings.voice_provider!r} is not mock or http"
    )
