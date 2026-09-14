import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ManagerAliasProvider(str, enum.Enum):
    notion_name = "notion_name"
    sleeper_user_id = "sleeper_user_id"


class HistorySource(str, enum.Enum):
    notion = "notion"
    sleeper = "sleeper"
    manual = "manual"


class TransactionMovement(str, enum.Enum):
    add = "add"
    drop = "drop"


class WeeklyHighlightSource(str, enum.Enum):
    calculated = "calculated"
    manual = "manual"


class ImportRunStatus(str, enum.Enum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    needs_attention = "needs_attention"


class Manager(Base):
    __tablename__ = "league_managers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True, index=True, nullable=True
    )
    display_name: Mapped[str] = mapped_column(String(120), index=True)
    biography: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ManagerAlias(Base):
    __tablename__ = "league_manager_aliases"
    __table_args__ = (
        UniqueConstraint("provider", "external_value", name="uq_league_manager_alias_provider_value"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    manager_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("league_managers.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[ManagerAliasProvider] = mapped_column(Enum(ManagerAliasProvider))
    external_value: Mapped[str] = mapped_column(String(255))


class SeasonTeam(Base):
    __tablename__ = "league_season_teams"
    __table_args__ = (
        UniqueConstraint("season_id", "manager_id", name="uq_league_season_teams_season_manager"),
        UniqueConstraint("season_id", "roster_id", name="uq_league_season_teams_season_roster"),
        UniqueConstraint("season_id", "sleeper_user_id", name="uq_league_season_teams_season_sleeper_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), index=True)
    manager_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("league_managers.id", ondelete="RESTRICT"), index=True)
    team_name: Mapped[str] = mapped_column(String(120))
    sleeper_user_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    roster_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class LeagueMatchup(Base):
    __tablename__ = "league_matchups"
    __table_args__ = (
        UniqueConstraint("season_id", "source", "source_key", name="uq_league_matchups_source_key"),
        CheckConstraint("manager_a_id <> manager_b_id", name="ck_league_matchups_distinct_managers"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), index=True)
    week: Mapped[int] = mapped_column(Integer, index=True)
    manager_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("league_managers.id", ondelete="RESTRICT"), index=True)
    manager_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("league_managers.id", ondelete="RESTRICT"), index=True)
    team_a_name: Mapped[str] = mapped_column(String(120))
    team_b_name: Mapped[str] = mapped_column(String(120))
    score_a: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_b: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleeper_matchup_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[HistorySource] = mapped_column(Enum(HistorySource))
    source_key: Mapped[str] = mapped_column(String(255))
    source_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)


class LeagueTransaction(Base):
    __tablename__ = "league_transactions"
    __table_args__ = (
        UniqueConstraint("season_id", "external_id", name="uq_league_transactions_season_external"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(120))
    week: Mapped[int] = mapped_column(Integer, index=True)
    transaction_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSON)


class LeagueTransactionParticipant(Base):
    __tablename__ = "league_transaction_participants"
    __table_args__ = (
        UniqueConstraint("transaction_id", "roster_id", name="uq_league_transaction_participant_roster"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("league_transactions.id", ondelete="CASCADE"), index=True
    )
    manager_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("league_managers.id", ondelete="RESTRICT"), index=True)
    roster_id: Mapped[int] = mapped_column(Integer)


class LeagueTransactionPlayer(Base):
    __tablename__ = "league_transaction_players"
    __table_args__ = (
        UniqueConstraint(
            "transaction_id", "player_id", "movement", "roster_id",
            name="uq_league_transaction_player_movement",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("league_transactions.id", ondelete="CASCADE"), index=True
    )
    manager_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("league_managers.id", ondelete="RESTRICT"), index=True)
    roster_id: Mapped[int] = mapped_column(Integer)
    player_id: Mapped[str] = mapped_column(String(80), index=True)
    player_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    movement: Mapped[TransactionMovement] = mapped_column(Enum(TransactionMovement))


class LeagueTransactionDraftPick(Base):
    __tablename__ = "league_transaction_draft_picks"
    __table_args__ = (
        UniqueConstraint(
            "transaction_id", "pick_season", "round", "original_roster_id",
            "previous_owner_roster_id", "new_owner_roster_id",
            name="uq_league_transaction_draft_pick",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("league_transactions.id", ondelete="CASCADE"), index=True
    )
    pick_season: Mapped[int] = mapped_column(Integer)
    round: Mapped[int] = mapped_column(Integer)
    original_roster_id: Mapped[int] = mapped_column(Integer)
    previous_owner_roster_id: Mapped[int] = mapped_column(Integer)
    new_owner_roster_id: Mapped[int] = mapped_column(Integer)


class LeagueTransactionFaab(Base):
    __tablename__ = "league_transaction_faab"
    __table_args__ = (
        UniqueConstraint(
            "transaction_id", "sender_roster_id", "receiver_roster_id",
            name="uq_league_transaction_faab_transfer",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("league_transactions.id", ondelete="CASCADE"), index=True
    )
    sender_roster_id: Mapped[int] = mapped_column(Integer)
    receiver_roster_id: Mapped[int] = mapped_column(Integer)
    amount: Mapped[int] = mapped_column(Integer)


class SeasonPlacement(Base):
    __tablename__ = "league_season_placements"
    __table_args__ = (
        UniqueConstraint("season_id", "manager_id", name="uq_league_season_placements_season_manager"),
        CheckConstraint(
            "calculated_placement IS NULL OR calculated_placement > 0",
            name="ck_league_placements_calculated_positive",
        ),
        CheckConstraint("override_placement IS NULL OR override_placement > 0", name="ck_league_placements_override_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), index=True)
    manager_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("league_managers.id", ondelete="RESTRICT"), index=True)
    calculated_placement: Mapped[int | None] = mapped_column(Integer, nullable=True)
    override_placement: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SeasonPunishment(Base):
    __tablename__ = "league_season_punishments"
    __table_args__ = (UniqueConstraint("season_id", name="uq_league_season_punishments_season"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), index=True)
    manager_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("league_managers.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(String(240))


class WeeklyHighlight(Base):
    __tablename__ = "league_weekly_highlights"
    __table_args__ = (
        UniqueConstraint(
            "season_id", "week", "category", "source_key",
            name="uq_league_weekly_highlights_source_key",
        ),
        CheckConstraint("week > 0", name="ck_league_weekly_highlights_week_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), index=True)
    week: Mapped[int] = mapped_column(Integer, index=True)
    category: Mapped[str] = mapped_column(String(80))
    source_key: Mapped[str] = mapped_column(String(255))
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("league_managers.id", ondelete="SET NULL"), index=True, nullable=True
    )
    player_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    player_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[WeeklyHighlightSource] = mapped_column(Enum(WeeklyHighlightSource))


class CustomSeasonFact(Base):
    __tablename__ = "league_custom_season_facts"
    __table_args__ = (
        UniqueConstraint("season_id", "display_order", name="uq_league_custom_season_facts_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(160))
    value: Mapped[str] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer)


class ImportRun(Base):
    __tablename__ = "league_import_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    season_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("seasons.id", ondelete="CASCADE"), index=True, nullable=True
    )
    source: Mapped[HistorySource] = mapped_column(Enum(HistorySource), index=True)
    status: Mapped[ImportRunStatus] = mapped_column(Enum(ImportRunStatus), index=True)
    counts: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
