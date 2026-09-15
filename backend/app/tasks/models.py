import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class ScheduledTaskRunStatus(str, enum.Enum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    task_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    description: Mapped[str] = mapped_column(String(255))
    schedule: Mapped[str] = mapped_column(String(160))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", index=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[ScheduledTaskRunStatus | None] = mapped_column(Enum(ScheduledTaskRunStatus))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    runs: Mapped[list["ScheduledTaskRun"]] = relationship(cascade="all, delete-orphan")


class ScheduledTaskRun(Base):
    __tablename__ = "scheduled_task_runs"
    __table_args__ = (
        Index("ix_scheduled_task_runs_task_started", "task_key", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_key: Mapped[str] = mapped_column(
        ForeignKey("scheduled_tasks.task_key", ondelete="CASCADE"), index=True
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ScheduledTaskRunStatus] = mapped_column(
        Enum(ScheduledTaskRunStatus), default=ScheduledTaskRunStatus.running, index=True
    )
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
