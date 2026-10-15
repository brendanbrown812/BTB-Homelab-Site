"""Add reactions to PTGOTW comments."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261015_0013"
down_revision = "20260930_0012"


def upgrade():
    reaction_type = postgresql.ENUM(
        "thumbs_up",
        "thumbs_down",
        "heart",
        "laughing",
        name="ptgcommentreactiontype",
        create_type=False,
    )
    reaction_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "ptgotw_comment_reactions",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column(
            "comment_id",
            postgresql.UUID(),
            sa.ForeignKey("ptgotw_comments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reaction_type", reaction_type, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "comment_id",
            "user_id",
            "reaction_type",
            name="uq_ptgotw_comment_reaction_user_type",
        ),
    )
    op.create_index(
        "ix_ptgotw_comment_reactions_comment_id",
        "ptgotw_comment_reactions",
        ["comment_id"],
    )
    op.create_index(
        "ix_ptgotw_comment_reactions_user_id",
        "ptgotw_comment_reactions",
        ["user_id"],
    )


def downgrade():
    op.drop_table("ptgotw_comment_reactions")
    postgresql.ENUM(name="ptgcommentreactiontype").drop(op.get_bind(), checkfirst=True)
