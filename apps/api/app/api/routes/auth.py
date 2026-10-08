"""Authentication endpoints (PRD §21 ``/auth/register``, ``/auth/login``).

In ``AUTH_MODE=local`` this API is its own identity provider: it issues
HS256 access/refresh pairs after checking a local password. In
``AUTH_MODE=oidc`` credentials are owned by Keycloak and these endpoints
answer 503 rather than pretending to handle passwords it does not have.

Privilege escalation is blocked at registration: ``faith_leader`` and ``admin``
accounts can only be created by an existing administrator, because a
self-service path to either would hand the platform to whoever signs up first.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import CurrentUser
from app.core.rbac import (
    SELF_REGISTERABLE_ROLES,
    Role,
    get_optional_admin,
)
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    subject_of,
    verify_password,
)
from app.db.models import User
from app.db.session import get_session
from app.repositories import users as users_repo
from app.schemas.auth import (
    LoginIn,
    RefreshIn,
    RegisterIn,
    TokenOut,
    UserOut,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
OptionalAdmin = Annotated[User | None, Depends(get_optional_admin)]

_INVALID_CREDENTIALS = "Invalid email or password"


async def local_auth_only() -> None:
    """Guard for endpoints that only make sense when we own the credentials."""
    if settings.auth_mode != "local":
        raise HTTPException(
            status_code=503,
            detail="Credentials are handled by the identity provider in this "
            "environment; this endpoint is unavailable.",
        )


def _issue_tokens(user: User) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id, user.role),
        expires_in=settings.jwt_access_ttl_seconds,
    )


@router.post(
    "/register",
    response_model=UserOut,
    status_code=201,
    dependencies=[Depends(local_auth_only)],
)
async def register(
    payload: RegisterIn,
    session: SessionDep,
    admin: OptionalAdmin,
) -> UserOut:
    if Role(payload.role) not in SELF_REGISTERABLE_ROLES and admin is None:
        raise HTTPException(
            status_code=403,
            detail="Only an administrator may create faith leader or "
            "administrator accounts.",
        )

    if await users_repo.email_exists(session, payload.email):
        # 409 rather than a generic failure: this is a legitimate conflict on
        # data the caller supplied, and the address is not secret to them.
        raise HTTPException(status_code=409, detail="That email is already registered.")

    user = await users_repo.create(
        session,
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
        password=payload.password,
        organization_id=payload.organization_id,
    )
    await session.commit()
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenOut, dependencies=[Depends(local_auth_only)])
async def login(payload: LoginIn, session: SessionDep) -> TokenOut:
    user = await users_repo.get_by_email(session, payload.email)

    if user is None:
        # Spend the same CPU as a real verification so response time does not
        # reveal whether this address has an account.
        verify_password(payload.password, None)
        raise HTTPException(status_code=401, detail=_INVALID_CREDENTIALS)

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail=_INVALID_CREDENTIALS)

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Account disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _issue_tokens(user)


@router.post(
    "/refresh",
    response_model=TokenOut,
    dependencies=[Depends(local_auth_only)],
)
async def refresh(payload: RefreshIn, session: SessionDep) -> TokenOut:
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
        user = await users_repo.get_by_id(session, subject_of(claims))
    except TokenError:
        raise HTTPException(status_code=401, detail=_INVALID_CREDENTIALS) from None

    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail=_INVALID_CREDENTIALS)
    # Both tokens are reissued. Rotation is currently cosmetic: refresh tokens
    # are stateless, so a stolen one stays valid until it expires. Persisting
    # and revoking them is deferred to Phase 2's payment-grade session work.
    return _issue_tokens(user)


@router.get("/me", response_model=UserOut)
async def me(current: CurrentUser) -> UserOut:
    return UserOut.model_validate(current)
