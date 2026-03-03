"""add_is_official_to_game_modules

Revision ID: a1b2c3d4e5f6
Revises: f0eebeab7aea
Create Date: 2026-01-20 14:00:00.000000+00:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f0eebeab7aea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE game_modules
            ADD COLUMN IF NOT EXISTS is_official BOOLEAN NOT NULL DEFAULT FALSE;
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_game_modules_is_official ON game_modules (is_official);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_game_modules_is_official;")
    op.execute("ALTER TABLE game_modules DROP COLUMN IF EXISTS is_official;")
