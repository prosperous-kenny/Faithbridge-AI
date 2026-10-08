"""Voice intake parity with typed submissions (Phase 7 exit gate).

The exit gate asks that "voice submissions classify at parity with typed
ones". Parity here is pipeline parity: the same text sent through the voice
route and the typed route must come back with the same classification fields,
the same persistence, and the same guards — proved by stubbing the AI
boundary once and asserting both responses carry the identical payload.
"""

from __future__ import annotations

import base64

from app.db.session import SessionFactory
from tests import factories

API = "/api/v1"

TYPED_DESCRIPTION = "We need help with groceries this week after the factory closed"
VOICE_TRANSCRIPT = "We need help with groceries this week after the factory closed"


def _classification(text: str) -> dict:
    """Deterministic, text-dependent stub: identical text -> identical result."""
    return {
        "category": "food",
        "urgency_score": min(100, 40 + len(text) // 4),
        "priority": "high" if len(text) > 40 else "medium",
    }


def _stub_ai(monkeypatch) -> None:
    async def _available() -> bool:
        return True

    async def _classify(text: str) -> dict:
        return _classification(text)

    for route in ("app.api.routes.assistance", "app.api.routes.voice"):
        monkeypatch.setattr(f"{route}.classify_need", _classify)
        monkeypatch.setattr(f"{route}.ai_service_available", _available)


def _stub_ai_unavailable(monkeypatch) -> None:
    async def _unavailable() -> bool:
        return False

    monkeypatch.setattr(
        "app.api.routes.voice.ai_service_available", _unavailable
    )


async def _new_org() -> int:
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await session.commit()
        return org.id


async def test_voice_and_typed_submissions_classify_identically(
    client, make_user, login, monkeypatch
):
    """The Phase 7 exit gate: same text, both routes, same classification."""
    _stub_ai(monkeypatch)
    org_id = await _new_org()
    user = await make_user("community_member", organization_id=org_id)
    headers = login(user)

    typed = client.post(
        f"{API}/assistance/requests",
        json={"organization_id": org_id, "description": TYPED_DESCRIPTION},
        headers=headers,
    )
    voice = client.post(
        f"{API}/assistance/voice/requests",
        json={"organization_id": org_id, "transcript": VOICE_TRANSCRIPT},
        headers=headers,
    )

    assert typed.status_code == 201, typed.text
    assert voice.status_code == 201, voice.text

    typed_body, voice_body = typed.json(), voice.json()["request"]
    assert typed_body["category"] == voice_body["category"] == "food"
    assert typed_body["urgency_score"] == voice_body["urgency_score"]
    assert typed_body["priority"] == voice_body["priority"]
    assert typed_body["status"] == voice_body["status"] == "submitted"
    assert typed_body["description"] == voice_body["description"]
    # Both landed as real rows, not just echoed responses.
    assert typed_body["id"] != voice_body["id"]
    assert voice.json()["transcription"] == "client"


async def test_voice_submission_is_flagged_for_duplicate(
    client, make_user, login, monkeypatch
):
    """Voice submissions run through the same fraud screening as typed ones."""
    _stub_ai(monkeypatch)
    org_id = await _new_org()
    user = await make_user("community_member", organization_id=org_id)
    headers = login(user)

    first = client.post(
        f"{API}/assistance/requests",
        json={"organization_id": org_id, "description": TYPED_DESCRIPTION},
        headers=headers,
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"{API}/assistance/voice/requests",
        json={"organization_id": org_id, "transcript": VOICE_TRANSCRIPT},
        headers=headers,
    )
    assert second.status_code == 201, second.text  # flag-only, never blocked
    flags = second.json()["fraud_flags"]
    assert {flag["rule"] for flag in flags} == {"duplicate_request"}
    assert flags[0]["request_id"] == second.json()["request"]["id"]


async def test_voice_requires_transcript_or_audio(client, make_user, login):
    org_id = await _new_org()
    user = await make_user("community_member", organization_id=org_id)
    response = client.post(
        f"{API}/assistance/voice/requests",
        json={"organization_id": org_id},
        headers=login(user),
    )
    assert response.status_code == 422


async def test_audio_only_fails_closed_without_transcription_provider(
    client, make_user, login, monkeypatch
):
    """The default mock provider has no speech-to-text: 503, never a guess."""
    _stub_ai(monkeypatch)
    org_id = await _new_org()
    user = await make_user("community_member", organization_id=org_id)
    audio = base64.b64encode(b"\x00\x01fake-webm-audio-bytes").decode()
    response = client.post(
        f"{API}/assistance/voice/requests",
        json={"organization_id": org_id, "audio_base64": audio},
        headers=login(user),
    )
    assert response.status_code == 503
    assert "speech-to-text" in response.json()["detail"]


async def test_provider_transcription_path_produces_a_request(
    client, make_user, login, monkeypatch
):
    """With a provider configured, audio rides the same pipeline as text."""
    _stub_ai(monkeypatch)

    class _Provider:
        async def transcribe(self, audio: bytes, *, mime_type: str) -> str:
            assert audio == b"raw-audio"
            assert mime_type == "audio/webm"
            return "Please help us with medicine costs this week"

    monkeypatch.setattr(
        "app.api.routes.voice.get_transcription_provider", lambda: _Provider()
    )

    org_id = await _new_org()
    user = await make_user("community_member", organization_id=org_id)
    audio = base64.b64encode(b"raw-audio").decode()
    response = client.post(
        f"{API}/assistance/voice/requests",
        json={
            "organization_id": org_id,
            "audio_base64": audio,
            "mime_type": "audio/webm",
        },
        headers=login(user),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["transcription"] == "provider"
    assert body["request"]["description"] == (
        "Please help us with medicine costs this week"
    )
    assert body["fraud_flags"] == []


async def test_invalid_base64_is_rejected(client, make_user, login):
    org_id = await _new_org()
    user = await make_user("community_member", organization_id=org_id)
    response = client.post(
        f"{API}/assistance/voice/requests",
        json={"organization_id": org_id, "audio_base64": "not-base64!!"},
        headers=login(user),
    )
    assert response.status_code == 422


async def test_voice_cross_org_submission_is_403(client, make_user, login, monkeypatch):
    _stub_ai(monkeypatch)
    org_a = await _new_org()
    org_b = await _new_org()
    user = await make_user("community_member", organization_id=org_a)
    response = client.post(
        f"{API}/assistance/voice/requests",
        json={"organization_id": org_b, "transcript": VOICE_TRANSCRIPT},
        headers=login(user),
    )
    assert response.status_code == 403


async def test_voice_fails_closed_when_ai_unavailable(
    client, make_user, login, monkeypatch
):
    _stub_ai(monkeypatch)
    _stub_ai_unavailable(monkeypatch)
    org_id = await _new_org()
    user = await make_user("community_member", organization_id=org_id)
    response = client.post(
        f"{API}/assistance/voice/requests",
        json={"organization_id": org_id, "transcript": VOICE_TRANSCRIPT},
        headers=login(user),
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "AI service unavailable"
