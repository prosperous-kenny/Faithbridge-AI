"""Shared request dependencies: who is calling, and what may they reach."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import TokenError, decode_token, identity_email, subject_of
from app.db.models import User
from app.db.session import get_session
from app.repositories import users as users_repo

BEARER_SCHEME = {"WWW-Authenticate": "Bearer"}


def _unauthorized(detail: str, *, status_code: int = 401) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail, headers=BEARER_SCHEME)


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """Resolve the bearer token on this request to a local user row.

    Authority rule, and the reason this hits the database on every request:
    the token is proof of *who* the caller is, never of *what* they may do.
    Roles, active state and organisation all come from ``users``, so disabling
    an account or demoting a user takes effect on the next request instead of
    when their token expires. The ``role`` claim in a token is therefore
    informational only.

    Every failure returns a generic 401: distinguishing "no such user" from
    "bad password" or "malformed token" is exactly the oracle attackers probe.
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise _unauthorized("Not authenticated")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _unauthorized("Not authenticated")

    try:
        claims = decode_token(token)
        if settings.auth_mode == "oidc":
            email = identity_email(claims)
            user = await users_repo.get_by_email(session, email)
        else:
            user = await users_repo.get_by_id(session, subject_of(claims))
    except TokenError:
        raise _unauthorized("Could not validate credentials") from None

    if user is None:
        raise _unauthorized("Could not validate credentials")
    if not user.is_active:
        # The caller proved they hold a valid token for this account, so
        # saying it is disabled discloses nothing they did not already know.
        raise _unauthorized("Account disabled", status_code=403)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
