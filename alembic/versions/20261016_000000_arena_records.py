"""arena records: per-Digimon identity and record, season winners

Revision ID: 20261016arena
Revises: 20261005arena
Create Date: 2026-10-16 00:00:00.000000

Changes:
- game_pets: pet_uid (VARCHAR(64), indexed) -- the game's identity for a
  Digimon, kept through evolution, so one species form fights one season;
  battles / wins / losses / draws (INTEGER, default 0) -- the record of the
  server copy, which the game adds to the real pet when the season ends.
- season_winners: the podium of every finished season (rank, account,
  nickname, record, prize, the team's Digimon), kept for player profiles.

Additive only: a server still running the previous code keeps working
against the upgraded database.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "20261016arena"
down_revision: str | None = "20261005arena"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE game_pets ADD COLUMN IF NOT EXISTS pet_uid VARCHAR(64);
        ALTER TABLE game_pets ADD COLUMN IF NOT EXISTS battles INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE game_pets ADD COLUMN IF NOT EXISTS wins INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE game_pets ADD COLUMN IF NOT EXISTS losses INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE game_pets ADD COLUMN IF NOT EXISTS draws INTEGER NOT NULL DEFAULT 0;
        CREATE INDEX IF NOT EXISTS ix_game_pets_pet_uid ON game_pets (pet_uid);
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS season_winners (
            id UUID PRIMARY KEY,
            season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
            rank INTEGER NOT NULL,
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            team_id UUID REFERENCES game_teams(id) ON DELETE SET NULL,
            nickname VARCHAR(100),
            season_name VARCHAR(200) NOT NULL,
            score INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            draws INTEGER NOT NULL DEFAULT 0,
            prize_coins INTEGER NOT NULL DEFAULT 0,
            pets JSON,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_season_winner_rank UNIQUE (season_id, rank)
        );
        CREATE INDEX IF NOT EXISTS ix_season_winners_season_id ON season_winners (season_id);
        CREATE INDEX IF NOT EXISTS ix_season_winners_user_id ON season_winners (user_id);
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS season_winners;
        DROP INDEX IF EXISTS ix_game_pets_pet_uid;
        ALTER TABLE game_pets DROP COLUMN IF EXISTS draws;
        ALTER TABLE game_pets DROP COLUMN IF EXISTS losses;
        ALTER TABLE game_pets DROP COLUMN IF EXISTS wins;
        ALTER TABLE game_pets DROP COLUMN IF EXISTS battles;
        ALTER TABLE game_pets DROP COLUMN IF EXISTS pet_uid;
    """)
