"""Add league polls."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260912_0004"
down_revision = "20260910_0003"


def upgrade():
    selection_mode = postgresql.ENUM("single", "multiple", name="pollselectionmode", create_type=False)
    selection_mode.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "polls",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("question", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("selection_mode", selection_mode, nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_polls_created_by_user_id", "polls", ["created_by_user_id"])
    op.create_table(
        "poll_options",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("poll_id", postgresql.UUID(), sa.ForeignKey("polls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.String(240), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("poll_id", "position", name="uq_poll_options_poll_position"),
    )
    op.create_index("ix_poll_options_poll_id", "poll_options", ["poll_id"])
    op.create_table(
        "poll_votes",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("poll_id", postgresql.UUID(), sa.ForeignKey("polls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("option_id", postgresql.UUID(), sa.ForeignKey("poll_options.id", ondelete="CASCADE"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("poll_id", "user_id", "option_id", name="uq_poll_votes_poll_user_option"),
    )
    op.create_index("ix_poll_votes_poll_id", "poll_votes", ["poll_id"])
    op.create_index("ix_poll_votes_user_id", "poll_votes", ["user_id"])
    op.create_index("ix_poll_votes_option_id", "poll_votes", ["option_id"])


def downgrade():
    op.drop_table("poll_votes")
    op.drop_table("poll_options")
    op.drop_table("polls")
    postgresql.ENUM(name="pollselectionmode").drop(op.get_bind(), checkfirst=True)
