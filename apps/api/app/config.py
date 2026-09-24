import os


class Settings:
    app_name: str = "FaithBridge AI API"
    environment: str = os.getenv("FAITHBRIDGE_ENV", "development")
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    ai_service_url: str = os.getenv("AI_SERVICE_URL", "http://localhost:8200")


settings = Settings()