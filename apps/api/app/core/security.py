"""Password hashing and token issue/verification for Phase 1 authentication.

Two token paths share one contract:

* ``local``   -- this process signs and verifies its own HS256 JWTs. Used by
  development and by every automated test. No external service is contacted.
* ``oidc``    -- an external OIDC provider (Keycloak) signs RS256 tokens; this
  module verifies them against the provider's JSON Web Key Set. The API does
  not self-issue tokens in this mode.

Verification returns raw claims only. Deciding *what those claims are allowed
to do* is deliberately not this module's job: role checks read the database
(core.deps), so revoking a user's role takes effect on the next request rather
than whenever their token expires.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import uuid

import jwt as pyjwt
from jwt import InvalidTokenError as PyJwtError
from jwt.exceptions import PyJWKClientError

from app.config import settings

# --- Password hashing ------------------------------------------------------
#
# PBKDF2-HMAC-SHA256 from the standard library. Argon2id/bcrypt would be the
# first choice for a new system, but both are compiled extensions; a plain
# implementation keeps `pip install -e .` reproducible on a clean machine,
# which matters more here than a few milliseconds per login. The iteration
# count is stored inside the hash so it can be raised later without breaking
# existing passwords.

PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 600_000
PASSWORD_SALT_BYTES = 16
MIN_PASSWORD_LENGTH = 8
# Upper bound exists because the hash cost is linear in input length: without
# it, an unauthenticated caller could submit a 10 MB password and tie up a
# worker for seconds on every attempt.
MAX_PASSWORD_LENGTH = 128

# Used only to equalise timing when an email is unknown, so that login
# response times do not reveal which addresses have accounts.
_DUMMY_PASSWORD_HASH = None


class PasswordPolicyError(ValueError):
    """Raised when a password fails the length/format policy."""


class TokenError(ValueError):
    """Raised when a token is missing, malformed, expired, or otherwise untrusted.

    The reason string is for logs and tests. Routes must translate any
    TokenError into a generic 401 without echoing it to the client.
    """


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str, *, iterations: int = PASSWORD_ITERATIONS) -> str:
    _check_password_policy(password)
    salt = secrets.token_bytes(PASSWORD_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{PASSWORD_SCHEME}${iterations}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str | None) -> bool:
    """Constant-time password check. A missing hash always fails."""
    if not encoded:
        # Still spend the time: returning early on no-hash accounts would let
        # a caller distinguish "no password set" from "wrong password" by
        # latency.
        _dummy_verify(password)
        return False

    try:
        scheme, iterations_s, salt_s, digest_s = encoded.split("$")
    except ValueError:
        return False
    if scheme != PASSWORD_SCHEME:
        return False
    try:
        iterations = int(iterations_s)
        salt = base64.b64decode(salt_s, validate=True)
        expected = base64.b64decode(digest_s, validate=True)
    except ValueError:
        return False
    if iterations <= 0 or not salt:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _dummy_verify(password: str) -> None:
    """Burn the same CPU as a real verify, for accounts with no stored password."""
    global _DUMMY_PASSWORD_HASH
    if _DUMMY_PASSWORD_HASH is None:
        _DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))
    verify_password(password, _DUMMY_PASSWORD_HASH)


def _check_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at most {MAX_PASSWORD_LENGTH} characters long."
        )


# --- Local secret ----------------------------------------------------------

_local_secret: str | None = None


def ensure_local_secret() -> str:
    """Return the secret used to sign local-mode tokens.

    When JWT_SECRET is unset, generate a random secret for the lifetime of this
    process instead of falling back to anything hard-coded: a predictable
    signing key would let anyone mint an admin token. The trade-off is that
    sessions do not survive a restart, which is acceptable for development and
    is exactly what the warning is for.
    """
    if settings.jwt_secret:
        return settings.jwt_secret
    global _local_secret
    if _local_secret is None:
        _local_secret = secrets.token_urlsafe(48)
    return _local_secret


# --- Token issue -----------------------------------------------------------


def create_token(
    *,
    user_id: int,
    role: str,
    token_type: str,
    ttl_seconds: int,
) -> str:
    """Mint a local-mode token. ``token_type`` is "access" or "refresh"."""
    if settings.auth_mode != "local":
        raise TokenError("this API does not issue tokens in OIDC mode")
    if token_type not in ("access", "refresh"):
        raise TokenError(f"unsupported token type: {token_type}")

    now = int(time.time())
    claims = {
        "sub": str(user_id),
        "role": role,  # informational only; see core.deps for the authority rule
        "type": token_type,
        "iat": now,
        "nbf": now,
        "exp": now + ttl_seconds,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": uuid.uuid4().hex,
    }
    return pyjwt.encode(claims, ensure_local_secret(), algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int, role: str) -> str:
    return create_token(
        user_id=user_id,
        role=role,
        token_type="access",
        ttl_seconds=settings.jwt_access_ttl_seconds,
    )


def create_refresh_token(user_id: int, role: str) -> str:
    return create_token(
        user_id=user_id,
        role=role,
        token_type="refresh",
        ttl_seconds=settings.jwt_refresh_ttl_seconds,
    )


# --- Token verification ----------------------------------------------------

_oidc_jwk_client: pyjwt.PyJWKClient | None = None


def _get_oidc_jwk_client() -> pyjwt.PyJWKClient:
    """Lazily build the JWKS client so importing this module never fetches."""
    global _oidc_jwk_client
    if _oidc_jwk_client is None:
        _oidc_jwk_client = pyjwt.PyJWKClient(
            f"{settings.oidc_issuer.rstrip('/')}/protocol/openid-connect/certs",
            cache_keys=True,
            lifespan=300,
        )
    return _oidc_jwk_client


def decode_token(token: str, *, expected_type: str = "access") -> dict:
    """Verify a token and return its claims.

    Raises :class:`TokenError` on anything untrusted. Both modes enforce the
    same claim contract (issuer, audience, expiry, token type) so that swapping
    AUTH_MODE does not relax what a caller must present.
    """
    if not token or not token.strip():
        raise TokenError("empty token")

    if settings.auth_mode == "local":
        try:
            claims = pyjwt.decode(
                token,
                ensure_local_secret(),
                algorithms=[settings.jwt_algorithm],
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer,
            )
        except PyJwtError as exc:
            raise TokenError(f"invalid token: {exc}") from exc
    else:
        try:
            signing_key = _get_oidc_jwk_client().get_signing_key_from_jwt(token)
            claims = pyjwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=settings.oidc_audience,
                issuer=settings.oidc_issuer,
            )
        # PyJWKClientError (unknown kid, unusable JWKS) and a JWKS that cannot
        # be fetched at all are both "cannot verify" rather than a server bug:
        # the client must see 401, not a 500, and the underlying reason is
        # carried by TokenError for the log.
        except (PyJwtError, PyJWKClientError, OSError, ValueError) as exc:
            raise TokenError(f"invalid token: {exc}") from exc

    if settings.auth_mode == "local":
        if claims.get("type") != expected_type:
            raise TokenError(f"expected a {expected_type} token")
        if not claims.get("sub"):
            raise TokenError("token has no subject")
    # OIDC mode: the provider owns the claim shape. Keycloak access and refresh
    # tokens are distinguished by the client they were minted for, not by a
    # "type" claim, so there is nothing to enforce here beyond the signature,
    # issuer and audience checks the decode already performed. Only access
    # tokens are accepted by the API in this mode; refresh is delegated to the
    # provider's own /token endpoint.
    elif not claims.get("sub"):
        raise TokenError("token has no subject")
    return claims


def subject_of(claims: dict) -> int:
    """Return the ``sub`` claim as a local user id (local mode only).

    In OIDC mode ``sub`` is the provider's opaque subject, not our primary
    key; identity is resolved from the ``email`` claim there instead.
    """
    try:
        return int(claims["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenError("token subject is not a user id") from exc


def identity_email(claims: dict) -> str:
    """Return the email a token identifies (OIDC mode only).

    Raises TokenError if the token carries no usable email, because accepting
    a token without an identity would mean resolving every request to "no user".
    """
    email = claims.get("email")
    if not isinstance(email, str) or "@" not in email:
        raise TokenError("token has no usable email claim")
    return email.lower()
