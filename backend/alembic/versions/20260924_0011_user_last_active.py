"""Track the last authenticated activity for league members."""

from alembic import op
import sqlalchemy as sa

revision = "20260924_0011"
down_revision = "20260923_0010"


def upgrade():
    op.add_column("users", sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("users", "last_active_at")
