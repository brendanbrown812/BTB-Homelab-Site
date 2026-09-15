"""Add database-backed scheduled task state and run history."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260914_0009"
down_revision = "20260913_0008"


def upgrade():
    run_status = postgresql.ENUM(
        "running", "succeeded", "failed", "skipped",
        name="scheduledtaskrunstatus",
        create_type=False,
    )
    run_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "scheduled_tasks",
        sa.Column("task_key", sa.String(120), primary_key=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("schedule", sa.String(160), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", run_status, nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_scheduled_tasks_enabled", "scheduled_tasks", ["enabled"])
    op.create_index("ix_scheduled_tasks_next_run_at", "scheduled_tasks", ["next_run_at"])
    op.create_index("ix_scheduled_tasks_locked_until", "scheduled_tasks", ["locked_until"])

    op.create_table(
        "scheduled_task_runs",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column(
            "task_key",
            sa.String(120),
            sa.ForeignKey("scheduled_tasks.task_key", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", run_status, nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_scheduled_task_runs_task_key", "scheduled_task_runs", ["task_key"])
    op.create_index("ix_scheduled_task_runs_scheduled_for", "scheduled_task_runs", ["scheduled_for"])
    op.create_index("ix_scheduled_task_runs_status", "scheduled_task_runs", ["status"])
    op.create_index(
        "ix_scheduled_task_runs_task_started",
        "scheduled_task_runs",
        ["task_key", "started_at"],
    )


def downgrade():
    op.drop_table("scheduled_task_runs")
    op.drop_table("scheduled_tasks")
    postgresql.ENUM(name="scheduledtaskrunstatus").drop(op.get_bind(), checkfirst=True)
