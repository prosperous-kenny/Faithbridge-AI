import os
from pathlib import Path

from dotenv import load_dotenv

VALID_AUTH_MODES = ("local", "oidc")

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Settings:
    app_name: str = "FaithBridge AI API"
    environment: str = os.getenv("FAITHBRIDGE_ENV", "development")
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    ai_service_url: str = os.getenv("AI_SERVICE_URL", "http://localhost:8200")
    database_url: str = os.getenv("DATABASE_URL", "")
    db_echo: bool = os.getenv("DB_ECHO", "false").lower() == "true"
    # Escape hatch for local dev only: create tables with create_all instead of
    # requiring `alembic upgrade head`. Never enable in a deployed environment.
    auto_create_schema: bool = os.getenv("AUTO_CREATE_SCHEMA", "false").lower() == "true"
    resend_api_key: str = os.getenv("RESEND_API_KEY", "")
    email_from: str = os.getenv(
        "EMAIL_FROM", "FaithBridge AI <notifications@example.com>"
    )

    # --- Authentication (Phase 1) -------------------------------------------
    # Two modes, selected at process start:
    #
    #   local  This API issues and verifies its own HS256 JWTs. Used for
    #          development and for the whole automated test suite. No external
    #          identity provider is contacted.
    #   oidc   Tokens are issued by an external OIDC provider (Keycloak in
    #          development) and verified here against its JSON Web Key Set.
    #          The API stops self-issuing tokens: register/login/refresh are
    #          unavailable and are expected to be fronted by the provider.
    auth_mode: str = os.getenv("AUTH_MODE", "local").strip().lower()
    # Sign secret for local-mode tokens. Empty means "generate a random secret
    # for this process" (see security.ensure_local_secret): never a hard-coded
    # fallback, because a predictable JWT secret would let anyone mint an
    # admin token.
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_algorithm: str = "HS256"
    # 15 minutes: short enough that a leaked access token expires quickly.
    jwt_access_ttl_seconds: int = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "900"))
    # 14 days: long enough for a usable session, short enough to bound risk.
    jwt_refresh_ttl_seconds: int = int(
        os.getenv("JWT_REFRESH_TTL_SECONDS", str(60 * 60 * 24 * 14))
    )
    jwt_issuer: str = os.getenv("JWT_ISSUER", "faithbridge-api")
    jwt_audience: str = os.getenv("JWT_AUDIENCE", "faithbridge")
    # OIDC mode only: issuer URL and audience the provider's tokens are signed
    # for, e.g. https://localhost:8443/realms/faithbridge
    oidc_issuer: str = os.getenv("OIDC_ISSUER", "")
    oidc_audience: str = os.getenv("OIDC_AUDIENCE", "")

    # --- Observability (Phase 5) ---------------------------------------------
    # Sentry error tracking is a pure opt-in: no DSN, no SDK ever loaded.
    sentry_dsn: str = os.getenv("SENTRY_DSN", "")

    # --- Phase 2 integrations (Phase 6) --------------------------------------
    # Every external adapter sits behind a provider interface so development and
    # CI run fully offline. "mock" (the default) exercises the real code path —
    # intent creation, capture, reconciliation, message send — with a fake
    # backend; the named provider is only constructed when its credentials are
    # actually present, so an unset key is a configuration error the caller
    # will notice, never a silent fallback.
    payments_provider: str = os.getenv("PAYMENTS_PROVIDER", "mock").strip().lower()
    stripe_secret_key: str = os.getenv("STRIPE_SECRET_KEY", "")
    whatsapp_provider: str = os.getenv("WHATSAPP_PROVIDER", "mock").strip().lower()
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_whatsapp_from: str = os.getenv(
        "TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886"
    )

    def validate_auth_config(self) -> None:
        """Fail fast on auth settings that would be unsafe or unusable.

        Called from the application lifespan, so a misconfigured process dies
        at startup rather than serving 500s or, worse, accepting weak tokens.
        """
        if self.auth_mode not in VALID_AUTH_MODES:
            raise RuntimeError(
                f"AUTH_MODE={self.auth_mode!r} is not one of {VALID_AUTH_MODES}."
            )
        if self.auth_mode == "oidc":
            missing = [
                name
                for name, value in (
                    ("OIDC_ISSUER", self.oidc_issuer),
                    ("OIDC_AUDIENCE", self.oidc_audience),
                )
                if not value
            ]
            if missing:
                raise RuntimeError(
                    "AUTH_MODE=oidc requires " + ", ".join(missing) + " to be set."
                )
        if self.environment == "production":
            if self.auth_mode != "oidc":
                raise RuntimeError(
                    "AUTH_MODE must be 'oidc' in production; the local provider "
                    "is for development only."
                )
            if not self.jwt_secret:
                raise RuntimeError("JWT_SECRET must be set in production.")


settings = Settings()