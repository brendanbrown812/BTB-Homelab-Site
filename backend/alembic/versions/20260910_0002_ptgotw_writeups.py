"""Add PTGOTW writeups."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260910_0002"
down_revision = "20260910_0001"


def upgrade():
    op.create_table(
        "ptgotw_writeups",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("content_html", sa.Text(), nullable=False),
        sa.Column("author_id", postgresql.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("submitted_by_author", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("year", "week", name="uq_ptgotw_writeups_year_week"),
    )
    op.create_index("ix_ptgotw_writeups_author_id", "ptgotw_writeups", ["author_id"])


def downgrade():
    op.drop_table("ptgotw_writeups")
