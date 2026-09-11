"""Add PTGOTW drafts and soft user deletion."""

from alembic import op
import sqlalchemy as sa

revision = "20260910_0003"
down_revision = "20260910_0002"


def upgrade():
    op.add_column("ptgotw_writeups", sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("users", sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("users", "is_deleted")
    op.drop_column("ptgotw_writeups", "is_published")
