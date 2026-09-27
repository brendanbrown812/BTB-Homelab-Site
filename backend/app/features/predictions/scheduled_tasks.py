from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.league_history.sleeper_importer import import_sleeper_season
from app.features.predictions.models import PredictionWeek, WeekStatus
from app.features.predictions.notifications import send_prediction_deadline_notification
from app.features.predictions.operations import finalize_prediction_week, refresh_prediction_week
from app.features.predictions.routes import _sync_current
from app.models.season import Season, SeasonPlatform


async def auto_finalize_prediction_weeks(db: AsyncSession) -> dict:
    """Finalize due prediction weeks and refresh the active season's league history."""
    now = datetime.now(timezone.utc)
    season = await db.scalar(
        select(Season)
        .where(
            Season.is_active.is_(True),
            Season.platform == SeasonPlatform.sleeper,
            Season.sleeper_league_id.is_not(None),
        )
        .order_by(Season.year.desc())
    )
    if not season:
        return {"status": "skipped", "reason": "No active Sleeper season is configured"}

    weeks = (
        await db.scalars(
            select(PredictionWeek)
            .where(
                PredictionWeek.season_id == season.id,
                PredictionWeek.status != WeekStatus.final,
                PredictionWeek.lock_at <= now,
            )
            .order_by(PredictionWeek.week_number)
        )
    ).all()

    finalized: list[int] = []
    refreshed_matchups = 0
    for week in weeks:
        refreshed = await refresh_prediction_week(db, week)
        if refreshed == 0:
            raise RuntimeError(
                f"Sleeper returned no matchups for Week {week.week_number}; finalization was not attempted"
            )
        refreshed_matchups += refreshed
        try:
            await finalize_prediction_week(db, week)
        except HTTPException as exc:
            raise RuntimeError(f"Week {week.week_number} could not be finalized: {exc.detail}") from exc
        finalized.append(week.week_number)

    history_result = await import_sleeper_season(db, season.id)
    history_status = str(history_result.get("status") or "unknown")
    if history_status != "succeeded":
        raise RuntimeError(f"Current-season history sync finished with status {history_status}")

    return {
        "status": "succeeded",
        "weeks_finalized": finalized,
        "matchups_refreshed": refreshed_matchups,
        "history_sync": history_status,
        "history_matchups": history_result.get("counts", {}).get("matchups", 0),
    }


async def send_prediction_deadline_reminder(
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict:
    """Notify Discord when the current prediction card is about 12 hours from locking."""
    settings = get_settings()
    if getattr(settings, "disable_outbound_notifications", False):
        return {"status": "skipped", "reason": "Outbound notifications are disabled"}
    if not settings.discord_predictions_webhook_url.strip():
        return {"status": "skipped", "reason": "Discord predictions webhook is not configured"}

    _, week, _ = await _sync_current(db)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    lock_at = week.lock_at if week.lock_at.tzinfo else week.lock_at.replace(tzinfo=timezone.utc)
    time_remaining = lock_at.astimezone(timezone.utc) - now.astimezone(timezone.utc)
    if week.status is not WeekStatus.open:
        return {"status": "skipped", "reason": "The current prediction week is not open"}
    if not timedelta(hours=11) <= time_remaining <= timedelta(hours=13):
        return {
            "status": "skipped",
            "reason": "The current prediction week is not about 12 hours from closing",
        }

    delivery_status = await send_prediction_deadline_notification()
    if delivery_status != "sent":
        raise RuntimeError(f"Discord predictions reminder finished with status {delivery_status}")
    return {
        "status": "succeeded",
        "week": week.week_number,
        "lock_at": lock_at.isoformat(),
        "notification": "sent",
    }
