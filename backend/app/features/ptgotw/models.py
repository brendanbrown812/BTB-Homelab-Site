import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, JSON, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class PTGWriteup(Base):
    __tablename__ = "ptgotw_writeups"
    __table_args__ = (UniqueConstraint("year", "week", name="uq_ptgotw_writeups_year_week"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    year: Mapped[int] = mapped_column(Integer)
    week: Mapped[int] = mapped_column(Integer)
    content_html: Mapped[str] = mapped_column(Text, default="")
    draft: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    submitted_by_author: Mapped[bool] = mapped_column(Boolean, default=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PTGWriteupComment(Base):
    __tablename__ = "ptgotw_comments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    writeup_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ptgotw_writeups.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ptgotw_comments.id", ondelete="CASCADE"), nullable=True, index=True)
    content: Mapped[str] = mapped_column(Text)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now().astimezone(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PTGRankingBallotStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"


class PTGRankingPeriod(Base):
    __tablename__ = "ptgotw_ranking_periods"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    year: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=False)
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PTGRankingCandidate(Base):
    __tablename__ = "ptgotw_ranking_candidates"
    __table_args__ = (
        UniqueConstraint("period_id", "writeup_id", name="uq_ptgotw_ranking_candidate_writeup"),
        UniqueConstraint("period_id", "position", name="uq_ptgotw_ranking_candidate_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ptgotw_ranking_periods.id", ondelete="CASCADE"), index=True
    )
    writeup_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ptgotw_writeups.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)


class PTGRankingBallot(Base):
    __tablename__ = "ptgotw_ranking_ballots"
    __table_args__ = (
        UniqueConstraint("period_id", "user_id", name="uq_ptgotw_ranking_ballot_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ptgotw_ranking_periods.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[PTGRankingBallotStatus] = mapped_column(
        Enum(PTGRankingBallotStatus), default=PTGRankingBallotStatus.draft
    )
    revision: Mapped[int] = mapped_column(Integer, default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PTGRankingItem(Base):
    __tablename__ = "ptgotw_ranking_items"
    __table_args__ = (
        UniqueConstraint("ballot_id", "writeup_id", name="uq_ptgotw_ranking_item_writeup"),
        UniqueConstraint("ballot_id", "position", name="uq_ptgotw_ranking_item_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ballot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ptgotw_ranking_ballots.id", ondelete="CASCADE"), index=True
    )
    writeup_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ptgotw_writeups.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
