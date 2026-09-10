"""Initial BTB core and predictions schema."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260910_0001"
down_revision = None


def upgrade():
    role = postgresql.ENUM("user", "admin", name="userrole", create_type=False)
    status = postgresql.ENUM("open", "locked", "final", name="weekstatus", create_type=False)
    result = postgresql.ENUM("win", "loss", "push", name="pickresult", create_type=False)
    role.create(op.get_bind(), checkfirst=True); status.create(op.get_bind(), checkfirst=True); result.create(op.get_bind(), checkfirst=True)
    op.create_table("users", sa.Column("id", postgresql.UUID(), primary_key=True), sa.Column("username", sa.String(80), nullable=False, unique=True), sa.Column("display_name", sa.String(120), nullable=False), sa.Column("role", role, nullable=False), sa.Column("password_hash", sa.String(255)), sa.Column("setup_token_hash", sa.String(64)), sa.Column("setup_token_expires_at", sa.DateTime(timezone=True)), sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("is_bootstrap", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("seasons", sa.Column("id", postgresql.UUID(), primary_key=True), sa.Column("year", sa.Integer(), nullable=False, unique=True), sa.Column("sleeper_league_id", sa.String(80), nullable=False, unique=True), sa.Column("is_active", sa.Boolean(), nullable=False))
    op.create_table("prediction_weeks", sa.Column("id", postgresql.UUID(), primary_key=True), sa.Column("season_id", postgresql.UUID(), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False), sa.Column("week_number", sa.Integer(), nullable=False), sa.Column("lock_at", sa.DateTime(timezone=True), nullable=False), sa.Column("status", status, nullable=False), sa.Column("finalized_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("season_id", "week_number"))
    op.create_table("prediction_matchups", sa.Column("id", postgresql.UUID(), primary_key=True), sa.Column("week_id", postgresql.UUID(), sa.ForeignKey("prediction_weeks.id", ondelete="CASCADE"), nullable=False), sa.Column("sleeper_matchup_id", sa.Integer(), nullable=False), sa.Column("team_a_roster_id", sa.Integer(), nullable=False), sa.Column("team_b_roster_id", sa.Integer(), nullable=False), sa.Column("team_a_name", sa.String(120), nullable=False), sa.Column("team_b_name", sa.String(120), nullable=False), sa.Column("team_a_owner", sa.String(120), nullable=False, server_default=""), sa.Column("team_b_owner", sa.String(120), nullable=False, server_default=""), sa.Column("team_a_record", sa.String(24), nullable=False, server_default="0–0"), sa.Column("team_b_record", sa.String(24), nullable=False, server_default="0–0"), sa.Column("team_a_score", sa.Float()), sa.Column("team_b_score", sa.Float()), sa.Column("winner_roster_id", sa.Integer()), sa.UniqueConstraint("week_id", "sleeper_matchup_id"))
    op.create_table("predictions", sa.Column("id", postgresql.UUID(), primary_key=True), sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("matchup_id", postgresql.UUID(), sa.ForeignKey("prediction_matchups.id", ondelete="CASCADE"), nullable=False), sa.Column("selected_roster_id", sa.Integer()), sa.Column("result", result), sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("user_id", "matchup_id"))
    for table, column in [("users", "username"), ("prediction_weeks", "season_id"), ("prediction_matchups", "week_id"), ("predictions", "user_id"), ("predictions", "matchup_id")]: op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    for table in ("predictions", "prediction_matchups", "prediction_weeks", "seasons", "users"): op.drop_table(table)
    for enum in ("pickresult", "weekstatus", "userrole"): postgresql.ENUM(name=enum).drop(op.get_bind(), checkfirst=True)
