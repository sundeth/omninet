"""Initial schema

Revision ID: 0000000000aa
Revises:
Create Date: 2026-01-19 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0000000000aa"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Pure SQL migration — avoids SQLAlchemy Enum type creation issues with asyncpg.
# PostgreSQL DDL is transactional, so a failure rolls back everything cleanly.

UPGRADE_SQL = """
-- Enum types (idempotent)
DO $$ BEGIN CREATE TYPE modulestatus  AS ENUM ('draft','published','unpublished','banned'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE seasonstatus  AS ENUM ('upcoming','active','completed');             EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE battleresult  AS ENUM ('team1_win','team2_win','draw');              EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE cosmetictype  AS ENUM ('background');                                EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE purchasetype  AS ENUM ('module','cosmetic','gameplay','item','special'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE activitytype  AS ENUM (
    'user_registered','user_verified','user_login','user_logout',
    'user_device_added','user_device_removed','user_password_reset',
    'user_coins_earned','user_coins_spent',
    'module_created','module_updated','module_published','module_unpublished',
    'module_banned','module_downloaded','module_contributor_added','module_contributor_removed',
    'team_created','team_updated','team_deleted','team_reward_claimed',
    'battle_started','battle_completed',
    'season_created','season_started','season_ended',
    'admin_user_banned','admin_module_banned','admin_config_changed'
); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- user_types
CREATE TABLE IF NOT EXISTS user_types (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          VARCHAR(50) NOT NULL UNIQUE,
    description   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- module_categories
CREATE TABLE IF NOT EXISTS module_categories (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          VARCHAR(100) NOT NULL UNIQUE,
    description   TEXT,
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- seasons
CREATE TABLE IF NOT EXISTS seasons (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name              VARCHAR(200) NOT NULL,
    description       TEXT,
    start_date        DATE NOT NULL,
    end_date          DATE NOT NULL,
    status            seasonstatus NOT NULL,
    restrictions      JSON,
    reward_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    theme_name        VARCHAR(100),
    banner_url        VARCHAR(500),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- users
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nickname      VARCHAR(100) NOT NULL UNIQUE,
    email         VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    type_id       UUID NOT NULL REFERENCES user_types(id),
    is_active     BOOLEAN NOT NULL DEFAULT FALSE,
    is_verified   BOOLEAN NOT NULL DEFAULT FALSE,
    coins         INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_users_nickname ON users (nickname);
CREATE INDEX IF NOT EXISTS ix_users_email    ON users (email);

-- user_devices
CREATE TABLE IF NOT EXISTS user_devices (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    secret_key   VARCHAR(255) NOT NULL UNIQUE,
    device_name  VARCHAR(100),
    device_type  VARCHAR(50) NOT NULL DEFAULT 'application',
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_user_devices_secret_key ON user_devices (secret_key);

-- game_modules  (without price, sell_count, is_official — added by later migrations)
CREATE TABLE IF NOT EXISTS game_modules (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name           VARCHAR(200) NOT NULL UNIQUE,
    version        VARCHAR(50) NOT NULL,
    description    TEXT,
    category_id    UUID REFERENCES module_categories(id),
    status         modulestatus NOT NULL,
    file_name      VARCHAR(255),
    file_size      INTEGER NOT NULL DEFAULT 0,
    download_count INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_game_modules_name ON game_modules (name);

-- module_contributors
CREATE TABLE IF NOT EXISTS module_contributors (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    module_id   UUID NOT NULL REFERENCES game_modules(id) ON DELETE CASCADE,
    can_publish BOOLEAN NOT NULL DEFAULT TRUE,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    added_by    UUID REFERENCES users(id),
    CONSTRAINT uq_contributor_module UNIQUE (user_id, module_id)
);

-- game_teams
CREATE TABLE IF NOT EXISTS game_teams (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    season_id      UUID REFERENCES seasons(id),
    name           VARCHAR(100),
    score          INTEGER NOT NULL DEFAULT 0,
    wins           INTEGER NOT NULL DEFAULT 0,
    losses         INTEGER NOT NULL DEFAULT 0,
    draws          INTEGER NOT NULL DEFAULT 0,
    rewarded_coins INTEGER NOT NULL DEFAULT 0,
    reward_claimed BOOLEAN NOT NULL DEFAULT FALSE,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- game_pets
CREATE TABLE IF NOT EXISTS game_pets (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team_id        UUID REFERENCES game_teams(id) ON DELETE SET NULL,
    name           VARCHAR(200) NOT NULL,
    module_name    VARCHAR(200) NOT NULL,
    module_version VARCHAR(50) NOT NULL,
    pet_version    VARCHAR(50),
    stage          INTEGER NOT NULL DEFAULT 1,
    level          INTEGER NOT NULL DEFAULT 1,
    atk_main       VARCHAR(100),
    atk_alt        VARCHAR(100),
    atk_alt2       VARCHAR(100),
    power          INTEGER NOT NULL DEFAULT 0,
    attribute      VARCHAR(50),
    hp             INTEGER NOT NULL DEFAULT 100,
    star           INTEGER NOT NULL DEFAULT 1,
    critical_turn  INTEGER NOT NULL DEFAULT 0,
    extra_data     JSON,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- game_battles
CREATE TABLE IF NOT EXISTS game_battles (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team1_id           UUID NOT NULL REFERENCES game_teams(id) ON DELETE CASCADE,
    team2_id           UUID NOT NULL REFERENCES game_teams(id) ON DELETE CASCADE,
    season_id          UUID REFERENCES seasons(id),
    winner_id          UUID REFERENCES game_teams(id),
    result             battleresult NOT NULL,
    battle_log         JSON,
    team1_score_change INTEGER NOT NULL DEFAULT 0,
    team2_score_change INTEGER NOT NULL DEFAULT 0,
    duration_seconds   INTEGER NOT NULL DEFAULT 0,
    fought_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_battle_teams_date UNIQUE (team1_id, team2_id, fought_at)
);

-- activity_logs
CREATE TABLE IF NOT EXISTS activity_logs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activity_type activitytype NOT NULL,
    user_id       UUID REFERENCES users(id) ON DELETE SET NULL,
    target_id     UUID,
    target_type   VARCHAR(50),
    description   TEXT,
    log_metadata  JSON,
    ip_address    VARCHAR(45),
    user_agent    VARCHAR(500),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_activity_logs_activity_type ON activity_logs (activity_type);
CREATE INDEX IF NOT EXISTS ix_activity_logs_user_id       ON activity_logs (user_id);
CREATE INDEX IF NOT EXISTS ix_activity_logs_target_id     ON activity_logs (target_id);
CREATE INDEX IF NOT EXISTS ix_activity_logs_created_at    ON activity_logs (created_at);

-- shop_cosmetics
CREATE TABLE IF NOT EXISTS shop_cosmetics (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cosmetic_type cosmetictype NOT NULL,
    name          VARCHAR(200) NOT NULL,
    price         INTEGER NOT NULL DEFAULT 0,
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    json_data     JSONB,
    sprite_name   VARCHAR(255),
    sell_count    INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_shop_cosmetics_cosmetic_type ON shop_cosmetics (cosmetic_type);

-- shop_gameplay
CREATE TABLE IF NOT EXISTS shop_gameplay (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(200) NOT NULL,
    description TEXT,
    price       INTEGER NOT NULL DEFAULT 0,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    json_data   JSONB,
    sell_count  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- shop_items
CREATE TABLE IF NOT EXISTS shop_items (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(200) NOT NULL,
    description TEXT,
    price       INTEGER NOT NULL DEFAULT 0,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    json_data   JSONB,
    sprite_name VARCHAR(255),
    sell_count  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- shop_specials
CREATE TABLE IF NOT EXISTS shop_specials (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(200) NOT NULL,
    description TEXT,
    price       INTEGER NOT NULL DEFAULT 0,
    enabled     BOOLEAN NOT NULL DEFAULT FALSE,
    json_data   JSONB,
    sell_count  INTEGER NOT NULL DEFAULT 0,
    start_date  TIMESTAMPTZ,
    end_date    TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- user_purchases
CREATE TABLE IF NOT EXISTS user_purchases (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id       UUID NOT NULL,
    purchase_type purchasetype NOT NULL,
    price_paid    INTEGER NOT NULL DEFAULT 0,
    purchased_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_user_purchases_user_id       ON user_purchases (user_id);
CREATE INDEX IF NOT EXISTS ix_user_purchases_item_id       ON user_purchases (item_id);
CREATE INDEX IF NOT EXISTS ix_user_purchases_purchase_type ON user_purchases (purchase_type);
"""

DOWNGRADE_SQL = """
DROP TABLE IF EXISTS user_purchases;
DROP TABLE IF EXISTS shop_specials;
DROP TABLE IF EXISTS shop_items;
DROP TABLE IF EXISTS shop_gameplay;
DROP TABLE IF EXISTS shop_cosmetics;
DROP TABLE IF EXISTS activity_logs;
DROP TABLE IF EXISTS game_battles;
DROP TABLE IF EXISTS game_pets;
DROP TABLE IF EXISTS game_teams;
DROP TABLE IF EXISTS module_contributors;
DROP TABLE IF EXISTS game_modules;
DROP TABLE IF EXISTS user_devices;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS seasons;
DROP TABLE IF EXISTS module_categories;
DROP TABLE IF EXISTS user_types;
DROP TYPE IF EXISTS purchasetype;
DROP TYPE IF EXISTS cosmetictype;
DROP TYPE IF EXISTS activitytype;
DROP TYPE IF EXISTS battleresult;
DROP TYPE IF EXISTS seasonstatus;
DROP TYPE IF EXISTS modulestatus;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
