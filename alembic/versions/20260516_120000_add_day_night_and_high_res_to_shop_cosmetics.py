"""add_day_night_and_high_res_to_shop_cosmetics

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-16 12:00:00.000000+00:00

Mirrors the game's Background class on the server side so the shop can
advertise whether a background asset has separate day/night variants and
whether an HD (``*_high.png``) version is available.  Defaults match the
client's assumed-true / assumed-false for unknown rows so existing data
keeps working without an admin pass.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE shop_cosmetics
            ADD COLUMN IF NOT EXISTS day_night BOOLEAN NOT NULL DEFAULT TRUE;
    """)
    op.execute("""
        ALTER TABLE shop_cosmetics
            ADD COLUMN IF NOT EXISTS high_res BOOLEAN NOT NULL DEFAULT FALSE;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE shop_cosmetics DROP COLUMN IF EXISTS high_res;")
    op.execute("ALTER TABLE shop_cosmetics DROP COLUMN IF EXISTS day_night;")
