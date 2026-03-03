"""Initial schema

Revision ID: 0000000000aa
Revises:
Create Date: 2026-01-19 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0000000000aa"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Enum types ---
    op.execute(
        "CREATE TYPE modulestatus AS ENUM ('draft', 'published', 'unpublished', 'banned')"
    )
    op.execute(
        "CREATE TYPE seasonstatus AS ENUM ('upcoming', 'active', 'completed')"
    )
    op.execute(
        "CREATE TYPE battleresult AS ENUM ('team1_win', 'team2_win', 'draw')"
    )
    op.execute(
        "CREATE TYPE activitytype AS ENUM ("
        "'user_registered', 'user_verified', 'user_login', 'user_logout',"
        "'user_device_added', 'user_device_removed', 'user_password_reset',"
        "'user_coins_earned', 'user_coins_spent',"
        "'module_created', 'module_updated', 'module_published', 'module_unpublished',"
        "'module_banned', 'module_downloaded', 'module_contributor_added', 'module_contributor_removed',"
        "'team_created', 'team_updated', 'team_deleted', 'team_reward_claimed',"
        "'battle_started', 'battle_completed',"
        "'season_created', 'season_started', 'season_ended',"
        "'admin_user_banned', 'admin_module_banned', 'admin_config_changed'"
        ")"
    )
    op.execute(
        "CREATE TYPE cosmetictype AS ENUM ('background')"
    )
    op.execute(
        "CREATE TYPE purchasetype AS ENUM ('module', 'cosmetic', 'gameplay', 'item', 'special')"
    )

    # --- user_types ---
    op.create_table(
        "user_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # --- module_categories ---
    op.create_table(
        "module_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # --- seasons ---
    op.create_table(
        "seasons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "upcoming", "active", "completed",
                name="seasonstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("restrictions", sa.JSON(), nullable=True),
        sa.Column("reward_multiplier", sa.Float(), nullable=False),
        sa.Column("theme_name", sa.String(100), nullable=True),
        sa.Column("banner_url", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nickname", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("coins", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["type_id"], ["user_types.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nickname"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_nickname"), "users", ["nickname"])
    op.create_index(op.f("ix_users_email"), "users", ["email"])

    # --- user_devices ---
    op.create_table(
        "user_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("secret_key", sa.String(255), nullable=False),
        sa.Column("device_name", sa.String(100), nullable=True),
        sa.Column("device_type", sa.String(50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("secret_key"),
    )
    op.create_index(op.f("ix_user_devices_secret_key"), "user_devices", ["secret_key"])

    # --- game_modules ---
    op.create_table(
        "game_modules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "published", "unpublished", "banned",
                name="modulestatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("download_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["category_id"], ["module_categories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_game_modules_name"), "game_modules", ["name"])

    # --- module_contributors ---
    op.create_table(
        "module_contributors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("can_publish", sa.Boolean(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("added_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["module_id"], ["game_modules.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["added_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "module_id", name="uq_contributor_module"),
    )

    # --- game_teams ---
    op.create_table(
        "game_teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("season_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(100), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False),
        sa.Column("losses", sa.Integer(), nullable=False),
        sa.Column("draws", sa.Integer(), nullable=False),
        sa.Column("rewarded_coins", sa.Integer(), nullable=False),
        sa.Column("reward_claimed", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- game_pets ---
    op.create_table(
        "game_pets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("module_name", sa.String(200), nullable=False),
        sa.Column("module_version", sa.String(50), nullable=False),
        sa.Column("pet_version", sa.String(50), nullable=True),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("atk_main", sa.String(100), nullable=True),
        sa.Column("atk_alt", sa.String(100), nullable=True),
        sa.Column("atk_alt2", sa.String(100), nullable=True),
        sa.Column("power", sa.Integer(), nullable=False),
        sa.Column("attribute", sa.String(50), nullable=True),
        sa.Column("hp", sa.Integer(), nullable=False),
        sa.Column("star", sa.Integer(), nullable=False),
        sa.Column("critical_turn", sa.Integer(), nullable=False),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["game_teams.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- game_battles ---
    op.create_table(
        "game_battles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team1_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team2_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("season_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("winner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "result",
            sa.Enum(
                "team1_win", "team2_win", "draw",
                name="battleresult",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("battle_log", sa.JSON(), nullable=True),
        sa.Column("team1_score_change", sa.Integer(), nullable=False),
        sa.Column("team2_score_change", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column(
            "fought_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["team1_id"], ["game_teams.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["team2_id"], ["game_teams.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.ForeignKeyConstraint(["winner_id"], ["game_teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "team1_id", "team2_id", "fought_at", name="uq_battle_teams_date"
        ),
    )

    # --- activity_logs ---
    op.create_table(
        "activity_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "activity_type",
            sa.Enum(
                "user_registered", "user_verified", "user_login", "user_logout",
                "user_device_added", "user_device_removed", "user_password_reset",
                "user_coins_earned", "user_coins_spent",
                "module_created", "module_updated", "module_published", "module_unpublished",
                "module_banned", "module_downloaded", "module_contributor_added",
                "module_contributor_removed",
                "team_created", "team_updated", "team_deleted", "team_reward_claimed",
                "battle_started", "battle_completed",
                "season_created", "season_started", "season_ended",
                "admin_user_banned", "admin_module_banned", "admin_config_changed",
                name="activitytype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("log_metadata", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_activity_logs_activity_type"), "activity_logs", ["activity_type"]
    )
    op.create_index(op.f("ix_activity_logs_user_id"), "activity_logs", ["user_id"])
    op.create_index(op.f("ix_activity_logs_target_id"), "activity_logs", ["target_id"])
    op.create_index(op.f("ix_activity_logs_created_at"), "activity_logs", ["created_at"])

    # --- shop_cosmetics ---
    op.create_table(
        "shop_cosmetics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "cosmetic_type",
            sa.Enum("background", name="cosmetictype", create_type=False),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("json_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sprite_name", sa.String(255), nullable=True),
        sa.Column("sell_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_shop_cosmetics_cosmetic_type"), "shop_cosmetics", ["cosmetic_type"]
    )

    # --- shop_gameplay ---
    op.create_table(
        "shop_gameplay",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("json_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sell_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- shop_items ---
    op.create_table(
        "shop_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("json_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sprite_name", sa.String(255), nullable=True),
        sa.Column("sell_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- shop_specials ---
    op.create_table(
        "shop_specials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("json_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sell_count", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- user_purchases ---
    op.create_table(
        "user_purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "purchase_type",
            sa.Enum(
                "module", "cosmetic", "gameplay", "item", "special",
                name="purchasetype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("price_paid", sa.Integer(), nullable=False),
        sa.Column(
            "purchased_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_purchases_user_id"), "user_purchases", ["user_id"])
    op.create_index(op.f("ix_user_purchases_item_id"), "user_purchases", ["item_id"])
    op.create_index(
        op.f("ix_user_purchases_purchase_type"), "user_purchases", ["purchase_type"]
    )


def downgrade() -> None:
    op.drop_table("user_purchases")
    op.drop_table("shop_specials")
    op.drop_table("shop_items")
    op.drop_table("shop_gameplay")
    op.drop_table("shop_cosmetics")
    op.drop_table("activity_logs")
    op.drop_table("game_battles")
    op.drop_table("game_pets")
    op.drop_table("game_teams")
    op.drop_table("module_contributors")
    op.drop_table("game_modules")
    op.drop_table("user_devices")
    op.drop_table("users")
    op.drop_table("seasons")
    op.drop_table("module_categories")
    op.drop_table("user_types")
    op.execute("DROP TYPE IF EXISTS purchasetype")
    op.execute("DROP TYPE IF EXISTS cosmetictype")
    op.execute("DROP TYPE IF EXISTS activitytype")
    op.execute("DROP TYPE IF EXISTS battleresult")
    op.execute("DROP TYPE IF EXISTS seasonstatus")
    op.execute("DROP TYPE IF EXISTS modulestatus")
