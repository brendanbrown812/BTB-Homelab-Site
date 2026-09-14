import enum
import uuid
from sqlalchemy import Boolean, CheckConstraint, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class SeasonPlatform(str, enum.Enum):
    espn = "espn"
    sleeper = "sleeper"


class Season(Base):
    __tablename__ = "seasons"
    __table_args__ = (
        CheckConstraint(
            "platform <> 'sleeper' OR sleeper_league_id IS NOT NULL",
            name="ck_seasons_sleeper_requires_league_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    year: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    platform: Mapped[SeasonPlatform] = mapped_column(Enum(SeasonPlatform), default=SeasonPlatform.sleeper)
    sleeper_league_id: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
