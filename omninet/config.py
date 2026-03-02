"""
Configuration settings for Omninet application.
Uses pydantic-settings for environment variable management.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    environment: Literal["dev", "prd"] = "dev"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:root@192.168.100.250:5432/omnipet_dev"
    database_url_prd: str = "postgresql+asyncpg://postgres:root@192.168.100.250:5432/omnipet_prd"

    # Security
    secret_key: str = "your-super-secure-secret-key-change-in-production"
    access_token_expire_minutes: int = 10080  # 7 days
    algorithm: str = "HS256"

    # Email Configuration
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@omnipet.com"
    smtp_from_name: str = "Omnipet"

    # Redis
    # redis_url: str = "redis://localhost:6379/0"  # Not used - cache is in-memory

    # Root path (for reverse proxy subpath routing, e.g. "/dev")
    root_path: str = ""

    # Allowed origins for CORS
    cors_origins: str = ""  # Comma-separated, e.g. "https://omnipet.app.br,http://localhost:8000"

    # File Storage
    modules_storage_path: str = "./storage/modules"
    logs_storage_path: str = "./storage/logs"

    # Battle Configuration
    max_daily_battles: int = 10
    max_teams_per_user: int = 1

    # Verification
    verification_code_expiry_minutes: int = 5
    pairing_code_expiry_minutes: int = 5

    @property
    def cors_origin_list(self) -> list[str]:
        """Get parsed CORS origins list."""
        if self.cors_origins:
            return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return []

    @property
    def db_url(self) -> str:
        """Get the database URL based on environment."""
        return self.database_url if self.environment == "dev" else self.database_url_prd

    @property
    def is_dev(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "dev"

    @property
    def modules_path(self) -> Path:
        """Get the modules storage path as Path object."""
        path = Path(self.modules_storage_path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def logs_path(self) -> Path:
        """Get the logs storage path as Path object."""
        path = Path(self.logs_storage_path)
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
