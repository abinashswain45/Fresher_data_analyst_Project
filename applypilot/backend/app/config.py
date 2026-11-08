"""Application configuration loaded from environment variables (see .env.example)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ApplyPilot AI"
    environment: str = "development"  # development | production | test

    # Database: PostgreSQL in production, SQLite fallback for local development/tests.
    database_url: str = "sqlite:///./applypilot.db"

    # Auth
    jwt_secret: str = "change-me-in-production-please-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 12

    # Field-level + file encryption (Fernet key, urlsafe base64, 32 bytes).
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    encryption_key: str = ""

    # CORS: comma separated list of allowed frontend origins.
    cors_origins: str = "http://localhost:3000"

    # Storage
    storage_dir: Path = Path("./storage")
    max_upload_mb: int = 10

    # AI (Anthropic Claude). If unset, the platform runs in heuristic mode.
    anthropic_api_key: str = ""
    ai_model: str = "claude-opus-5-5"
    ai_effort: str = "medium"
    ai_enable_fallbacks: bool = True

    # Browser automation
    automation_headless: bool = True
    playwright_chromium_executable: str = ""  # optional explicit Chromium path
    automation_timeout_ms: int = 20000
    automation_max_pages: int = 12
    automation_max_sessions: int = 3

    # Job fetching
    http_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 ApplyPilot/1.0"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.storage_dir.mkdir(parents=True, exist_ok=True)
    return s
