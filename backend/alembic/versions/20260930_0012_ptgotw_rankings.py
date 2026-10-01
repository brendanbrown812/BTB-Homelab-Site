"""Add annual PTGOTW ranking periods and ballots."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260930_0012"
down_revision = "20260924_0011"


def upgrade():
    ballot_status = postgresql.ENUM(
        "draft", "submitted", name="ptgrankingballotstatus", create_type=False
    )
    ballot_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "ptgotw_ranking_periods",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_by_user_id",
            postgresql.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ptgotw_ranking_periods_year", "ptgotw_ranking_periods", ["year"], unique=True)
    op.create_index(
        "ix_ptgotw_ranking_periods_updated_by_user_id",
        "ptgotw_ranking_periods",
        ["updated_by_user_id"],
    )

    op.create_table(
        "ptgotw_ranking_candidates",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column(
            "period_id",
            postgresql.UUID(),
            sa.ForeignKey("ptgotw_ranking_periods.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "writeup_id",
            postgresql.UUID(),
            sa.ForeignKey("ptgotw_writeups.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("period_id", "writeup_id", name="uq_ptgotw_ranking_candidate_writeup"),
        sa.UniqueConstraint("period_id", "position", name="uq_ptgotw_ranking_candidate_position"),
    )
    op.create_index("ix_ptgotw_ranking_candidates_period_id", "ptgotw_ranking_candidates", ["period_id"])
    op.create_index("ix_ptgotw_ranking_candidates_writeup_id", "ptgotw_ranking_candidates", ["writeup_id"])

    op.create_table(
        "ptgotw_ranking_ballots",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column(
            "period_id",
            postgresql.UUID(),
            sa.ForeignKey("ptgotw_ranking_periods.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", ballot_status, nullable=False, server_default="draft"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("period_id", "user_id", name="uq_ptgotw_ranking_ballot_user"),
    )
    op.create_index("ix_ptgotw_ranking_ballots_period_id", "ptgotw_ranking_ballots", ["period_id"])
    op.create_index("ix_ptgotw_ranking_ballots_user_id", "ptgotw_ranking_ballots", ["user_id"])

    op.create_table(
        "ptgotw_ranking_items",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column(
            "ballot_id",
            postgresql.UUID(),
            sa.ForeignKey("ptgotw_ranking_ballots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "writeup_id",
            postgresql.UUID(),
            sa.ForeignKey("ptgotw_writeups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("ballot_id", "writeup_id", name="uq_ptgotw_ranking_item_writeup"),
        sa.UniqueConstraint("ballot_id", "position", name="uq_ptgotw_ranking_item_position"),
    )
    op.create_index("ix_ptgotw_ranking_items_ballot_id", "ptgotw_ranking_items", ["ballot_id"])
    op.create_index("ix_ptgotw_ranking_items_writeup_id", "ptgotw_ranking_items", ["writeup_id"])


def downgrade():
    op.drop_table("ptgotw_ranking_items")
    op.drop_table("ptgotw_ranking_ballots")
    op.drop_table("ptgotw_ranking_candidates")
    op.drop_table("ptgotw_ranking_periods")
    postgresql.ENUM(name="ptgrankingballotstatus").drop(op.get_bind(), checkfirst=True)
