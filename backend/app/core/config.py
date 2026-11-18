"""
Application configuration.

All settings are read from environment variables (or a `.env` file) using
pydantic-settings, so no secret ever has to be written in the source code.
See `.env.example` in the project root for every available option.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> project root is three levels up from `app`
BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_ROOT / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General -----------------------------------------------------------
    APP_NAME: str = "RetailIQ"
    ENVIRONMENT: str = "development"  # development | production | test
    LOG_LEVEL: str = "INFO"

    # --- Database ----------------------------------------------------------
    # PostgreSQL is the production database. When DATABASE_URL is empty or not set
    # we fall back to a local SQLite file so the project runs with zero setup.
    DATABASE_URL: str = ""

    # --- Security ----------------------------------------------------------
    SECRET_KEY: str = "dev-only-change-me-this-is-not-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30
    # In development there is no email server, so the reset link is returned
    # in the API response. NEVER enable this in production.
    EXPOSE_RESET_TOKEN: bool = True
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"
    ALLOW_PUBLIC_SIGNUP: bool = True
    # Public demo deployments: the published demo accounts cannot be deleted,
    # deactivated, demoted or have their passwords changed by visitors.
    PROTECT_DEMO_ACCOUNTS: bool = False

    # --- Rate limiting (requests per minute per client IP) ------------------
    RATE_LIMIT_AUTH_PER_MIN: int = 20
    RATE_LIMIT_ASSISTANT_PER_MIN: int = 30

    # --- Files -------------------------------------------------------------
    MAX_UPLOAD_MB: int = 25
    UPLOAD_DIR: Path = PROJECT_ROOT / "data" / "uploads"
    PROCESSED_DIR: Path = PROJECT_ROOT / "data" / "processed"
    SAMPLE_DIR: Path = PROJECT_ROOT / "data" / "sample"
    MODEL_DIR: Path = PROJECT_ROOT / "models"
    REPORT_DIR: Path = PROJECT_ROOT / "reports"

    # --- Optional LLM for the assistant ------------------------------------
    # If neither key is present the assistant runs in rule-based mode.
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-sonnet-4-5"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"

    # --- Serving the built frontend (production / Docker single container) --
    FRONTEND_DIST: Path | None = None

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalise_db_url(cls, v: str) -> str:
        if not v or not v.strip():  # empty -> zero-setup SQLite file
            return f"sqlite:///{(PROJECT_ROOT / 'data' / 'retailiq.db').as_posix()}"
        v = v.strip()
        # Heroku/Render style "postgres://" URLs -> SQLAlchemy psycopg3 driver
        if v.startswith("postgres://"):
            v = "postgresql+psycopg://" + v[len("postgres://"):]
        elif v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    DEMO_EMAILS: tuple[str, ...] = ("admin@retailiq.dev", "analyst@retailiq.dev")

    def is_protected_demo(self, email: str) -> bool:
        return self.PROTECT_DEMO_ACCOUNTS and email.lower() in self.DEMO_EMAILS

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def llm_provider(self) -> str | None:
        if self.ANTHROPIC_API_KEY:
            return "anthropic"
        if self.OPENAI_API_KEY:
            return "openai"
        return None

    def ensure_dirs(self) -> None:
        for d in (self.UPLOAD_DIR, self.PROCESSED_DIR, self.SAMPLE_DIR, self.MODEL_DIR, self.REPORT_DIR):
            Path(d).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


settings = get_settings()
