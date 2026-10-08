"""Background work for the assistance pipeline.

Phase 2 executes re-scoring and notifications in-process via FastAPI
``BackgroundTasks`` so the lifecycle works today, without depending on a
broker that this machine cannot run. A deployed environment swaps the dispatch
mechanism for Celery (see ``celery_app.py``); the task functions stay the same,
so moving between them never changes behavior, only where they run.
"""

from __future__ import annotations

import logging

from app.db.session import SessionFactory
from app.repositories import assistance as assistance_repo
from app.repositories import users as users_repo
from app.services.ai_client import classify_need
from app.services.email import notify_critical_request

logger = logging.getLogger(__name__)


async def notify_new_critical_request(request_id: int) -> None:
    """Email an organization's active case handlers that a critical request
    entered their queue, so triage happens before expiry rather than on the
    next dashboard visit. No handlers and no critical priority are both
    silent no-ops."""
    async with SessionFactory() as session:
        request = await assistance_repo.get_request(session, request_id)
        if request is None or request.priority != "critical":
            return
        handlers = await users_repo.list_handlers(
            session, organization_id=request.organization_id
        )
        description = request.description

    for handler in handlers:
        try:
            result = await notify_critical_request(
                handler.email, str(request_id), description
            )
        except Exception:
            logger.exception(
                "critical request %s: notification to %s raised",
                request_id,
                handler.email,
            )
            continue
        if not result.sent:
            logger.warning(
                "critical request %s: notification to %s not sent: %s",
                request_id,
                handler.email,
                result.detail,
            )


async def rescore_request(request_id: int) -> None:
    """Re-run classification on a request and persist fresh scores on its way
    through triage. Best-effort: a failed re-classification keeps the previous
    scores rather than corrupting or dropping the case."""
    async with SessionFactory() as session:
        request = await assistance_repo.get_request(session, request_id)
        if request is None:
            return
        try:
            classification = await classify_need(request.description)
        except Exception:
            logger.exception("rescore %s failed; keeping previous scores", request_id)
            return
        request.category = classification["category"]
        request.urgency_score = classification["urgency_score"]
        request.priority = classification["priority"]
        await session.commit()

    if classification["priority"] == "critical":
        await notify_new_critical_request(request_id)