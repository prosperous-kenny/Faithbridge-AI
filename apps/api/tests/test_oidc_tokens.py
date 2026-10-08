"""OIDC-mode token verification (PRD §22: OIDC login, RBAC).

No identity provider runs on this machine, so these tests cover the half the
API is responsible for: that a token signed by an external RS256 key is
accepted only when signature, issuer, audience, subject and expiry all hold.
The JWKS is served over loopback HTTP by the test itself, so the fetch, the
parsing, and the signature check are the same ones a Keycloak ``/certs``
response goes through, with a locally generated key standing in for the
provider's.

What this does *not* prove: that Keycloak itself issues correctly shaped
tokens, or that a realm import boots. Both need a running container and are
recorded as unverified in docs/IMPLEMENTATION_PLAN.md.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app.config import settings
from app.core import security
from app.core.security import TokenError, decode_token, identity_email, subject_of

AUDIENCE = "faithbridge-test"
KID = "test-key"
# An OIDC subject is an opaque string, not our integer primary key: this is
# why identity is resolved through the email claim in this mode.
OIDC_SUB = "3f0a1b2c-5d6e-7f80-91a2-b3c4d5e6f708"


@pytest.fixture
def oidc(monkeypatch):
    """Switch the app into OIDC mode against a locally served JWKS.

    PyJWKClient refuses non-HTTP schemes, so the key set is served over a
    throwaway HTTP server on the loopback interface. That is also closer to
    reality than a file path: the test exercises a real fetch, a real 200, and
    the same parsing a Keycloak ``/certs`` response goes through.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": KID, "alg": "RS256", "use": "sig"})
    jwks = json.dumps({"keys": [jwk]}).encode("utf-8")

    server = ThreadingHTTPServer(("127.0.0.1", 0), _jwks_handler(jwks))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    issuer = f"http://127.0.0.1:{server.server_address[1]}/realms/faithbridge"

    monkeypatch.setattr(settings, "auth_mode", "oidc")
    monkeypatch.setattr(settings, "oidc_issuer", issuer)
    monkeypatch.setattr(settings, "oidc_audience", AUDIENCE)
    # The JWKS client is cached at module level; drop it so each test fetches
    # the JWKS it just started rather than one from a previous test.
    monkeypatch.setattr(security, "_oidc_jwk_client", None)

    try:
        yield SimpleNamespace(key=key, issuer=issuer, audience=AUDIENCE)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        monkeypatch.setattr(security, "_oidc_jwk_client", None)


def _jwks_handler(body: bytes):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Keycloak serves the key set under /realms/{realm}/...; match the
            # suffix so the issuer can look like a real realm URL.
            if not self.path.endswith("/protocol/openid-connect/certs"):
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # keep pytest output clean
            pass

    return Handler


def _sign(
    private_key,
    *,
    issuer: str,
    audience: str = AUDIENCE,
    ttl: int = 300,
    kid: str = KID,
    extra: dict | None = None,
) -> str:
    now = int(time.time())
    claims = {
        "sub": OIDC_SUB,
        "email": "person@example.org",
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + ttl,
    }
    claims.update(extra or {})
    return pyjwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


# --- acceptance ------------------------------------------------------------


def test_valid_oidc_token_is_accepted(oidc):
    token = _sign(oidc.key, issuer=oidc.issuer, audience=oidc.audience)
    claims = decode_token(token, expected_type="access")
    assert claims["email"] == "person@example.org"
    assert claims["sub"] == OIDC_SUB
    assert identity_email(claims) == "person@example.org"


def test_oidc_subject_is_not_a_local_user_id(oidc):
    """Guards against ever routing an OIDC subject through the integer path."""
    token = _sign(oidc.key, issuer=oidc.issuer, audience=oidc.audience)
    with pytest.raises(TokenError):
        subject_of(decode_token(token))


def test_identity_email_rejects_tokens_without_an_email(oidc):
    token = _sign(oidc.key, issuer=oidc.issuer, extra={"email": None})
    with pytest.raises(TokenError):
        identity_email(decode_token(token))


def test_identity_email_normalises_case(oidc):
    token = _sign(
        oidc.key, issuer=oidc.issuer, extra={"email": "Mixed.Case@Example.org"}
    )
    assert identity_email(decode_token(token)) == "mixed.case@example.org"


# --- rejection -------------------------------------------------------------


def test_token_signed_by_an_unknown_key_is_rejected(oidc):
    intruder = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    forged = pyjwt.encode(
        {
            "sub": OIDC_SUB,
            "email": "attacker@example.org",
            "iss": oidc.issuer,
            "aud": oidc.audience,
            "iat": now,
            "exp": now + 300,
        },
        intruder,
        algorithm="RS256",
        headers={"kid": KID},
    )
    with pytest.raises(TokenError):
        decode_token(forged)


def test_wrong_audience_is_rejected(oidc):
    token = _sign(oidc.key, issuer=oidc.issuer, audience="someone-elses-api")
    with pytest.raises(TokenError):
        decode_token(token)


def test_wrong_issuer_is_rejected(oidc):
    token = _sign(oidc.key, issuer="https://evil.example.org")
    with pytest.raises(TokenError):
        decode_token(token)


def test_expired_token_is_rejected(oidc):
    token = _sign(oidc.key, issuer=oidc.issuer, ttl=-30)
    with pytest.raises(TokenError):
        decode_token(token)


def test_unknown_key_id_is_rejected(oidc):
    token = _sign(oidc.key, issuer=oidc.issuer, kid="not-in-jwks")
    with pytest.raises(TokenError):
        decode_token(token)


def test_tampered_payload_is_rejected(oidc):
    token = _sign(oidc.key, issuer=oidc.issuer)
    header, payload, signature = token.split(".")

    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["email"] = "promoted-to-admin@example.org"
    forged = f"{header}.{_b64url(json.dumps(claims).encode())}.{signature}"

    with pytest.raises(TokenError):
        decode_token(forged)


# --- mode contract ---------------------------------------------------------


def test_oidc_mode_refuses_to_self_issue_tokens(oidc):
    with pytest.raises(TokenError):
        security.create_access_token(1, "admin")


def test_local_secret_is_generated_when_unset(monkeypatch):
    """No JWT_SECRET must mean a random per-process key, never a hard-coded one."""
    monkeypatch.setattr(settings, "jwt_secret", "")
    monkeypatch.setattr(security, "_local_secret", None)

    first = security.ensure_local_secret()
    assert first
    assert first == security.ensure_local_secret()  # stable within the process
    assert len(first) >= 32

    # A second "process" gets a different one.
    monkeypatch.setattr(security, "_local_secret", None)
    assert security.ensure_local_secret() != first
