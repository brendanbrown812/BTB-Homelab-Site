"""Add threaded comments to PTGOTW writeups."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260913_0005"
down_revision = "20260912_0004"


def upgrade():
    op.create_table(
        "ptgotw_comments",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("writeup_id", postgresql.UUID(), sa.ForeignKey("ptgotw_writeups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("parent_id", postgresql.UUID(), sa.ForeignKey("ptgotw_comments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ptgotw_comments_writeup_id", "ptgotw_comments", ["writeup_id"])
    op.create_index("ix_ptgotw_comments_user_id", "ptgotw_comments", ["user_id"])
    op.create_index("ix_ptgotw_comments_parent_id", "ptgotw_comments", ["parent_id"])


def downgrade():
    op.drop_table("ptgotw_comments")
