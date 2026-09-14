"""Add cached display names to league transaction players."""

from alembic import op
import sqlalchemy as sa


revision = "20260913_0008"
down_revision = "20260913_0007"


def upgrade():
    op.add_column("league_transaction_players", sa.Column("player_name", sa.String(160), nullable=True))


def downgrade():
    op.drop_column("league_transaction_players", "player_name")
