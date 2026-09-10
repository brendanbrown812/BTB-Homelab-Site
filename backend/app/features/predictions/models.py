import enum
import uuid
from datetime import datetime
from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


class WeekStatus(str, enum.Enum):
    open = "open"
    locked = "locked"
    final = "final"


class PickResult(str, enum.Enum):
    win = "win"
    loss = "loss"
    push = "push"


class PredictionWeek(Base):
    __tablename__ = "prediction_weeks"
    __table_args__ = (UniqueConstraint("season_id", "week_number"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), index=True)
    week_number: Mapped[int] = mapped_column(Integer)
    lock_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[WeekStatus] = mapped_column(Enum(WeekStatus), default=WeekStatus.open)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    matchups: Mapped[list["PredictionMatchup"]] = relationship(cascade="all, delete-orphan")


class PredictionMatchup(Base):
    __tablename__ = "prediction_matchups"
    __table_args__ = (UniqueConstraint("week_id", "sleeper_matchup_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    week_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prediction_weeks.id", ondelete="CASCADE"), index=True)
    sleeper_matchup_id: Mapped[int] = mapped_column(Integer)
    team_a_roster_id: Mapped[int] = mapped_column(Integer)
    team_b_roster_id: Mapped[int] = mapped_column(Integer)
    team_a_name: Mapped[str] = mapped_column(String(120))
    team_b_name: Mapped[str] = mapped_column(String(120))
    team_a_owner: Mapped[str] = mapped_column(String(120), default="")
    team_b_owner: Mapped[str] = mapped_column(String(120), default="")
    team_a_record: Mapped[str] = mapped_column(String(24), default="0–0")
    team_b_record: Mapped[str] = mapped_column(String(24), default="0–0")
    team_a_score: Mapped[float | None] = mapped_column(Float)
    team_b_score: Mapped[float | None] = mapped_column(Float)
    winner_roster_id: Mapped[int | None] = mapped_column(Integer)


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (UniqueConstraint("user_id", "matchup_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    matchup_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prediction_matchups.id", ondelete="CASCADE"), index=True)
    selected_roster_id: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[PickResult | None] = mapped_column(Enum(PickResult))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
