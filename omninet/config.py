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
    # Shop sprite assets — root of the per-environment asset tree used by
    # GET /shop/{kind}/{id}/sprite.  Sprites are looked up under
    # ``<shop_assets_base>/<environment>/<kind_folder>/<sprite_name>``
    # where kind_folder is "items" / "backgrounds" / "gameplay" / "specials".
    #
    # Example deployed layout (mounted from a network share):
    #   /appdata/omninet/dev/items/Protein.png
    #   /appdata/omninet/dev/backgrounds/bg_meadow_day.png
    #   /appdata/omninet/prd/items/Protein.png
    shop_assets_base: str = "/appdata/omninet"
    # Shop sprite assets (item icons, cosmetic previews, etc).  Each
    # item / cosmetic / gameplay entry references a filename via
    # ``sprite_name``; the file must live in this folder for the
    # ``GET /shop/{kind}/{id}/sprite`` endpoint to serve it.
    shop_sprites_path: str = "./storage/shop_sprites"

    # Battle Configuration
    max_daily_battles: int = 10
    max_teams_per_user: int = 1

    # Verification
    verification_code_expiry_minutes: int = 5
    pairing_code_expiry_minutes: int = 5

    # Fixed price every module costs (the DB ``price`` column is ignored
    # for modules — pricing is centralized here).  The player's very first
    # module purchase across all their linked devices is granted for free
    # regardless.
    module_fixed_price: int = 50

    # Reward coin values
    reward_coins_unlock: int = 5
    reward_coins_evolution: int = 2
    reward_coins_new_pet: int = 3
    reward_coins_adventure: int = 10

    # HMAC signing secret for reward claims (must match game client constant)
    reward_signing_secret: str = "change-me-reward-secret"

    # Arena season coin rewards
    arena_participation_coins: int = 1   # per battle (any outcome)
    arena_first_place_coins: int = 50    # season top-3
    arena_second_place_coins: int = 25
    arena_third_place_coins: int = 10

    # Game client path — absolute path to the Omnipet game client's src/
    # directory.  When set, this path is prepended to sys.path at startup
    # so the server can import the game's battle simulator directly without
    # copy-pasting code.  Leave empty to skip.
    game_client_path: str = ""

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
    def database_url_sync(self) -> str:
        """Get a sync (psycopg2) version of the active database URL.

        Alembic migrations run with a sync engine to avoid asyncpg's
        single-statement-per-execute limitation.
        """
        return self.db_url.replace("+asyncpg", "+psycopg2")

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
