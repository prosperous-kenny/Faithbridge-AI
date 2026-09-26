import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Settings:
    app_name: str = "FaithBridge AI API"
    environment: str = os.getenv("FAITHBRIDGE_ENV", "development")
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    ai_service_url: str = os.getenv("AI_SERVICE_URL", "http://localhost:8200")
    database_url: str = os.getenv("DATABASE_URL", "")
    db_echo: bool = os.getenv("DB_ECHO", "false").lower() == "true"


settings = Settings()