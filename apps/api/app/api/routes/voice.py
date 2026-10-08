"""Voice intake: the classification pipeline fed from a spoken submission.

Deliberately a thin sibling of ``routes/assistance.py``: the same org-scope
guard, the same fail-closed AI validation, the same beneficiary upsert and
repository write. Anything shared is imported, not copied, so voice and typed
submissions cannot drift apart — exactly what the Phase 7 exit gate ("voice
submissions classify at parity with typed ones") asks for.
"""

from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api.routes.assistance import (
    SUBMIT_ROLES,
    SessionDep,
    _validated_classification,
)
from app.core.deps import CurrentUser
from app.core.rbac import require_role
from app.repositories import assistance as assistance_repo
from app.repositories import audit as audit_repo
from app.schemas.assistance import AssistanceRequestOut
from app.schemas.fraud import FraudFlagOut
from app.schemas.voice import VoiceIntakeIn, VoiceIntakeOut
from app.services import fraud as fraud_service
from app.services.ai_client import ai_service_available, classify_need
from app.services.voice import TranscriptionError, get_transcription_provider
from app.workers.tasks import notify_new_critical_request

router = APIRouter()

MIN_TRANSCRIPT = 10
MAX_TRANSCRIPT = 2000


@router.post(
    "/requests",
    response_model=VoiceIntakeOut,
    status_code=201,
    dependencies=[Depends(require_role(*SUBMIT_ROLES))],
)
async def create_voice_request(
    payload: VoiceIntakeIn,
    session: SessionDep,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> VoiceIntakeOut:
    """Classify and persist a voice submission.

    Audio-only submissions need a transcription provider; with the default
    mock provider the request fails closed with 503 rather than guessing at
    words. The browser-SpeechRecognition path (``transcript`` supplied) needs
    no provider at all. Raw audio is never persisted — only the transcript
    rides the normal pipeline (PRD §22 data minimization).
    """
    if user.organization_id is not None and payload.organization_id != user.organization_id:
        raise HTTPException(
            status_code=403,
            detail="You can only submit requests to your own organization",
        )

    transcript, source = await _transcript_of(payload)
    if not MIN_TRANSCRIPT <= len(transcript) <= MAX_TRANSCRIPT:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Transcript must be {MIN_TRANSCRIPT}–{MAX_TRANSCRIPT} characters"
            ),
        )

    if not await ai_service_available():
        raise HTTPException(status_code=503, detail="AI service unavailable")
    classification = _validated_classification(await classify_need(transcript))

    beneficiary = await assistance_repo.get_or_create_beneficiary(
        session, user_id=user.id, organization_id=payload.organization_id
    )
    request = await assistance_repo.create_request(
        session,
        beneficiary_id=beneficiary.id,
        organization_id=payload.organization_id,
        description=transcript,
        category=classification["category"],
        urgency_score=classification["urgency_score"],
        priority=classification["priority"],
    )
    await audit_repo.log_action(
        session,
        action="assistance.request.voice.submitted",
        entity_type="assistance_request",
        entity_id=str(request.id),
        organization_id=request.organization_id,
        actor_id=user.id,
        note=f"transcription={source}",
    )
    # Screening runs after this submission's own audit row exists (the burst
    # rule counts audit rows) and commits atomically with the request.
    flags = await fraud_service.screen_submission(
        session,
        organization_id=request.organization_id,
        beneficiary_id=request.beneficiary_id,
        description=request.description,
        actor_id=user.id,
        request_id=request.id,
    )
    await session.commit()

    background_tasks.add_task(notify_new_critical_request, request.id)

    return VoiceIntakeOut(
        request=AssistanceRequestOut(
            id=request.id,
            organization_id=request.organization_id,
            description=request.description,
            category=request.category,
            urgency_score=request.urgency_score,
            priority=request.priority,
            status=request.status,
            created_at=request.created_at,
        ),
        transcription=source,
        fraud_flags=[FraudFlagOut.model_validate(flag) for flag in flags],
    )


async def _transcript_of(payload: VoiceIntakeIn) -> tuple[str, str]:
    """Resolve the text to classify and where it came from.

    Order matters: an explicit client transcript wins over audio, because it
    was produced by the same capture event and needs no provider at all.
    """
    if payload.transcript is not None:
        return payload.transcript.strip(), "client"

    if payload.audio_base64 is None:
        raise HTTPException(
            status_code=422,
            detail="Provide a transcript or an audio_base64 payload",
        )
    try:
        audio = base64.b64decode(payload.audio_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(
            status_code=422, detail="audio_base64 is not valid base64"
        ) from None
    if not audio:
        raise HTTPException(status_code=422, detail="audio_base64 decoded to nothing")

    try:
        transcript = await get_transcription_provider().transcribe(
            audio, mime_type=payload.mime_type or "application/octet-stream"
        )
    except TranscriptionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return transcript, "provider"
