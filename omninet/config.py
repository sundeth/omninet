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
    # Shop sprite assets — root of the asset tree served by
    # ``GET /shop/{kind}/{id}/sprite``.  Sprites are looked up at
    # ``<shop_assets_base>/<kind_folder>/<sprite_name>`` where kind_folder
    # is "items" / "backgrounds" / "gameplay" / "specials".
    #
    # In the deployed compose the env split lives in the volume mount
    # (``./dev:/app/storage`` for staging, ``./prd:/app/storage`` for
    # production), so both environments share the same in-container path.
    # The host-side equivalents are
    # ``/mnt/user/appdata/omninet/dev`` and ``/mnt/user/appdata/omninet/prd``.
    shop_assets_base: str = "/app/storage"
    # Shop sprite assets (item icons, cosmetic previews, etc).  Each
    # item / cosmetic / gameplay entry references a filename via
    # ``sprite_name``; the file must live in this folder for the
    # ``GET /shop/{kind}/{id}/sprite`` endpoint to serve it.
    shop_sprites_path: str = "./storage/shop_sprites"

    # Shop JSON -> database sync at startup and daily (off for a local
    # server sharing another environment's database).
    shop_sync_enabled: bool = True

    # SQL statement logging; unset = on in dev, off in prd.  Long arena
    # simulations against a dev database turn it off.
    database_echo: bool | None = None

    # Battle Configuration
    # Attacks a team may make per UTC day; a season's config can override
    # it ("attacks_per_day").  Being attacked never uses this up.
    max_daily_battles: int = 10
    max_teams_per_user: int = 1
    # Digimon per arena team.  A season's config may narrow the range or
    # force one size ("team_size": 1 makes a season of solo Digimon).
    arena_min_team_size: int = 1
    arena_max_team_size: int = 3

    # Verification
    verification_code_expiry_minutes: int = 5
    pairing_code_expiry_minutes: int = 5

    # Fixed price every module costs (the DB ``price`` column is ignored
    # for modules — pricing is centralized here).  The player's very first
    # module purchase across all their linked devices is granted for free
    # regardless.
    module_fixed_price: int = 50

    # Contribution points (a balance apart from the coins) are credited by
    # the Digimon Database, server to server: POST
    # /api/v1/internal/contribution-points/credit with this secret in the
    # X-Service-Token header. Empty = the endpoint refuses every call.
    contribution_service_token: str = ""
    # The most points one credit may carry (a contribution is 1, or 2 on an
    # entry flagged as needing data).
    contribution_max_points_per_credit: int = 10

    # Reward coin values
    reward_coins_unlock: int = 5
    reward_coins_evolution: int = 2
    reward_coins_new_pet: int = 3
    reward_coins_adventure: int = 10   # finishing a module's whole adventure
    reward_coins_area_clear: int = 1   # clearing one adventure area (boss)

    # Arena season coin rewards
    arena_participation_coins: int = 1   # per battle (any outcome)
    arena_first_place_coins: int = 50    # season top-3
    arena_second_place_coins: int = 25
    arena_third_place_coins: int = 10
    # A uploaded Digimon's full save copy is kept with the team, up to this
    # many bytes of JSON (larger copies are refused).
    arena_pet_json_max_bytes: int = 65536

    # Arena score changes per battle, for both the attacker and the defender
    # (a season's config may override them: win_score/loss_score/draw_score).
    arena_win_score: int = 25
    arena_loss_score: int = -12
    arena_draw_score: int = 5
    # Charge quality (0-3, or "random") every Digimon fights with; nobody
    # plays the charge minigame in an asynchronous battle.
    arena_default_charge: str = "2"

    # Arena runtime: the server's own copy of Omnipet's source and module
    # data, under <arena_storage_path>/runtimes/.  Updates dropped into
    # <arena_storage_path>/updates/ (Omnipet zips, and module zips queued by
    # module publishing) are applied only when a season ends.  See
    # omninet/arena/runtime.py.
    arena_storage_path: str = "./storage/arena"
    arena_runtimes_to_keep: int = 4

    # Discord relay (omninet/discord): the bot and /api/v1/discord load only
    # with a token. Set it on one environment: a token connected twice
    # answers every command twice. Links are kept under the storage path.
    discord_bot_token: str = ""
    discord_storage_path: str = "./storage/discord"
    # Python that runs the battle engine (python -m battle.arena from the
    # runtime's src/).  Empty = the interpreter running the server.
    arena_python: str = ""
    arena_engine_timeout_seconds: int = 30

    # Season schedule.  Seasons tile from the anchor in blocks of
    # arena_season_length_hours; the default anchor is a Sunday 00:00 UTC,
    # so the default 168 hours gives Sunday-to-Sunday weeks.
    arena_auto_seasons: bool = True
    arena_season_length_hours: float = 168
    arena_season_anchor: str = "2026-01-04T00:00:00+00:00"
    # JSON forced onto every automatically created season, e.g.
    # '{"allowed_stages": [3]}' and '{"charge": 3, "attacks_per_day": 20}'.
    arena_season_restrictions: str = ""
    arena_season_config: str = ""
    # How often the season clock runs (closing seasons, paying prizes,
    # applying runtime updates, opening the next season).
    arena_tick_seconds: int = 60

    # Development only: dummy players that attack on their own, and an
    # optional token the /dev/arena tools then require (X-Dev-Token).
    arena_dev_token: str = ""
    arena_dev_bots: bool = False
    arena_dev_bot_interval_seconds: int = 60
    arena_dev_bot_battles_per_tick: int = 3

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
    def arena_path(self) -> Path:
        """Root of the arena runtime store."""
        path = Path(self.arena_storage_path)
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
