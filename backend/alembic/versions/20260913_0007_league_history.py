"""Add league history and statistics foundation."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260913_0007"
down_revision = "20260913_0006"


def upgrade():
    season_platform = postgresql.ENUM("espn", "sleeper", name="seasonplatform", create_type=False)
    alias_provider = postgresql.ENUM("notion_name", "sleeper_user_id", name="manageraliasprovider", create_type=False)
    history_source = postgresql.ENUM("notion", "sleeper", "manual", name="historysource", create_type=False)
    movement = postgresql.ENUM("add", "drop", name="transactionmovement", create_type=False)
    highlight_source = postgresql.ENUM("calculated", "manual", name="weeklyhighlightsource", create_type=False)
    import_status = postgresql.ENUM(
        "running", "succeeded", "failed", "needs_attention",
        name="importrunstatus", create_type=False,
    )
    for enum_type in (season_platform, alias_provider, history_source, movement, highlight_source, import_status):
        enum_type.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "seasons",
        sa.Column("platform", season_platform, nullable=False, server_default="sleeper"),
    )
    op.alter_column("seasons", "sleeper_league_id", existing_type=sa.String(80), nullable=True)
    op.create_check_constraint(
        "ck_seasons_sleeper_requires_league_id",
        "seasons",
        "platform <> 'sleeper' OR sleeper_league_id IS NOT NULL",
    )

    op.create_table(
        "league_managers",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, unique=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("biography", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_league_managers_user_id", "league_managers", ["user_id"])
    op.create_index("ix_league_managers_display_name", "league_managers", ["display_name"])
    op.create_index("ix_league_managers_is_active", "league_managers", ["is_active"])

    op.create_table(
        "league_manager_aliases",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("manager_id", postgresql.UUID(), sa.ForeignKey("league_managers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", alias_provider, nullable=False),
        sa.Column("external_value", sa.String(255), nullable=False),
        sa.UniqueConstraint("provider", "external_value", name="uq_league_manager_alias_provider_value"),
    )
    op.create_index("ix_league_manager_aliases_manager_id", "league_manager_aliases", ["manager_id"])

    op.create_table(
        "league_season_teams",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("season_id", postgresql.UUID(), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manager_id", postgresql.UUID(), sa.ForeignKey("league_managers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("team_name", sa.String(120), nullable=False),
        sa.Column("sleeper_user_id", sa.String(80), nullable=True),
        sa.Column("roster_id", sa.Integer(), nullable=True),
        sa.UniqueConstraint("season_id", "manager_id", name="uq_league_season_teams_season_manager"),
        sa.UniqueConstraint("season_id", "roster_id", name="uq_league_season_teams_season_roster"),
        sa.UniqueConstraint("season_id", "sleeper_user_id", name="uq_league_season_teams_season_sleeper_user"),
    )
    op.create_index("ix_league_season_teams_season_id", "league_season_teams", ["season_id"])
    op.create_index("ix_league_season_teams_manager_id", "league_season_teams", ["manager_id"])

    op.create_table(
        "league_matchups",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("season_id", postgresql.UUID(), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("manager_a_id", postgresql.UUID(), sa.ForeignKey("league_managers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("manager_b_id", postgresql.UUID(), sa.ForeignKey("league_managers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("team_a_name", sa.String(120), nullable=False),
        sa.Column("team_b_name", sa.String(120), nullable=False),
        sa.Column("score_a", sa.Float(), nullable=True),
        sa.Column("score_b", sa.Float(), nullable=True),
        sa.Column("sleeper_matchup_id", sa.Integer(), nullable=True),
        sa.Column("source", history_source, nullable=False),
        sa.Column("source_key", sa.String(255), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=True),
        sa.UniqueConstraint("season_id", "source", "source_key", name="uq_league_matchups_source_key"),
        sa.CheckConstraint("manager_a_id <> manager_b_id", name="ck_league_matchups_distinct_managers"),
    )
    for column in ("season_id", "week", "manager_a_id", "manager_b_id"):
        op.create_index(f"ix_league_matchups_{column}", "league_matchups", [column])

    op.create_table(
        "league_transactions",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("season_id", postgresql.UUID(), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(120), nullable=False),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("transaction_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("season_id", "external_id", name="uq_league_transactions_season_external"),
    )
    for column in ("season_id", "week", "transaction_type", "status", "occurred_at"):
        op.create_index(f"ix_league_transactions_{column}", "league_transactions", [column])

    op.create_table(
        "league_transaction_participants",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("transaction_id", postgresql.UUID(), sa.ForeignKey("league_transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manager_id", postgresql.UUID(), sa.ForeignKey("league_managers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("roster_id", sa.Integer(), nullable=False),
        sa.UniqueConstraint("transaction_id", "roster_id", name="uq_league_transaction_participant_roster"),
    )
    op.create_index("ix_league_transaction_participants_transaction_id", "league_transaction_participants", ["transaction_id"])
    op.create_index("ix_league_transaction_participants_manager_id", "league_transaction_participants", ["manager_id"])

    op.create_table(
        "league_transaction_players",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("transaction_id", postgresql.UUID(), sa.ForeignKey("league_transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manager_id", postgresql.UUID(), sa.ForeignKey("league_managers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("roster_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.String(80), nullable=False),
        sa.Column("movement", movement, nullable=False),
        sa.UniqueConstraint("transaction_id", "player_id", "movement", "roster_id", name="uq_league_transaction_player_movement"),
    )
    for column in ("transaction_id", "manager_id", "player_id"):
        op.create_index(f"ix_league_transaction_players_{column}", "league_transaction_players", [column])

    op.create_table(
        "league_transaction_draft_picks",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("transaction_id", postgresql.UUID(), sa.ForeignKey("league_transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pick_season", sa.Integer(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("original_roster_id", sa.Integer(), nullable=False),
        sa.Column("previous_owner_roster_id", sa.Integer(), nullable=False),
        sa.Column("new_owner_roster_id", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "transaction_id", "pick_season", "round", "original_roster_id",
            "previous_owner_roster_id", "new_owner_roster_id",
            name="uq_league_transaction_draft_pick",
        ),
    )
    op.create_index("ix_league_transaction_draft_picks_transaction_id", "league_transaction_draft_picks", ["transaction_id"])

    op.create_table(
        "league_transaction_faab",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("transaction_id", postgresql.UUID(), sa.ForeignKey("league_transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_roster_id", sa.Integer(), nullable=False),
        sa.Column("receiver_roster_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.UniqueConstraint("transaction_id", "sender_roster_id", "receiver_roster_id", name="uq_league_transaction_faab_transfer"),
    )
    op.create_index("ix_league_transaction_faab_transaction_id", "league_transaction_faab", ["transaction_id"])

    op.create_table(
        "league_season_placements",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("season_id", postgresql.UUID(), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manager_id", postgresql.UUID(), sa.ForeignKey("league_managers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("calculated_placement", sa.Integer(), nullable=True),
        sa.Column("override_placement", sa.Integer(), nullable=True),
        sa.UniqueConstraint("season_id", "manager_id", name="uq_league_season_placements_season_manager"),
        sa.CheckConstraint("calculated_placement IS NULL OR calculated_placement > 0", name="ck_league_placements_calculated_positive"),
        sa.CheckConstraint("override_placement IS NULL OR override_placement > 0", name="ck_league_placements_override_positive"),
    )
    op.create_index("ix_league_season_placements_season_id", "league_season_placements", ["season_id"])
    op.create_index("ix_league_season_placements_manager_id", "league_season_placements", ["manager_id"])

    op.create_table(
        "league_season_punishments",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("season_id", postgresql.UUID(), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manager_id", postgresql.UUID(), sa.ForeignKey("league_managers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.UniqueConstraint("season_id", name="uq_league_season_punishments_season"),
    )
    op.create_index("ix_league_season_punishments_season_id", "league_season_punishments", ["season_id"])
    op.create_index("ix_league_season_punishments_manager_id", "league_season_punishments", ["manager_id"])

    op.create_table(
        "league_weekly_highlights",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("season_id", postgresql.UUID(), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("source_key", sa.String(255), nullable=False),
        sa.Column("manager_id", postgresql.UUID(), sa.ForeignKey("league_managers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("player_id", sa.String(80), nullable=True),
        sa.Column("player_name", sa.String(160), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("source", highlight_source, nullable=False),
        sa.UniqueConstraint("season_id", "week", "category", "source_key", name="uq_league_weekly_highlights_source_key"),
        sa.CheckConstraint("week > 0", name="ck_league_weekly_highlights_week_positive"),
    )
    for column in ("season_id", "week", "manager_id"):
        op.create_index(f"ix_league_weekly_highlights_{column}", "league_weekly_highlights", [column])

    op.create_table(
        "league_custom_season_facts",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("season_id", postgresql.UUID(), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint("season_id", "display_order", name="uq_league_custom_season_facts_order"),
    )
    op.create_index("ix_league_custom_season_facts_season_id", "league_custom_season_facts", ["season_id"])

    op.create_table(
        "league_import_runs",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("season_id", postgresql.UUID(), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source", history_source, nullable=False),
        sa.Column("status", import_status, nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("error_details", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_league_import_runs_season_id", "league_import_runs", ["season_id"])
    op.create_index("ix_league_import_runs_source", "league_import_runs", ["source"])
    op.create_index("ix_league_import_runs_status", "league_import_runs", ["status"])


def downgrade():
    op.drop_table("league_import_runs")
    op.drop_table("league_custom_season_facts")
    op.drop_table("league_weekly_highlights")
    op.drop_table("league_season_punishments")
    op.drop_table("league_season_placements")
    op.drop_table("league_transaction_faab")
    op.drop_table("league_transaction_draft_picks")
    op.drop_table("league_transaction_players")
    op.drop_table("league_transaction_participants")
    op.drop_table("league_transactions")
    op.drop_table("league_matchups")
    op.drop_table("league_season_teams")
    op.drop_table("league_manager_aliases")
    op.drop_table("league_managers")

    op.drop_constraint("ck_seasons_sleeper_requires_league_id", "seasons", type_="check")
    op.execute("UPDATE seasons SET sleeper_league_id = 'legacy-espn-' || CAST(year AS VARCHAR) WHERE sleeper_league_id IS NULL")
    op.alter_column("seasons", "sleeper_league_id", existing_type=sa.String(80), nullable=False)
    op.drop_column("seasons", "platform")

    for enum_name in (
        "importrunstatus", "weeklyhighlightsource", "transactionmovement",
        "historysource", "manageraliasprovider", "seasonplatform",
    ):
        postgresql.ENUM(name=enum_name).drop(op.get_bind(), checkfirst=True)
