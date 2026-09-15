from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.predictions.models import PredictionWeek, WeekStatus
from app.features.predictions.operations import finalize_prediction_week, refresh_prediction_week
from app.models.season import Season, SeasonPlatform


async def auto_finalize_prediction_weeks(db: AsyncSession) -> dict:
    """Refresh and finalize every due, unfinished week in the active Sleeper season."""
    now = datetime.now(timezone.utc)
    weeks = (
        await db.scalars(
            select(PredictionWeek)
            .join(Season, Season.id == PredictionWeek.season_id)
            .where(
                Season.is_active.is_(True),
                Season.platform == SeasonPlatform.sleeper,
                Season.sleeper_league_id.is_not(None),
                PredictionWeek.status != WeekStatus.final,
                PredictionWeek.lock_at <= now,
            )
            .order_by(PredictionWeek.week_number)
        )
    ).all()
    if not weeks:
        return {"status": "skipped", "reason": "No unfinished prediction weeks are due"}

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

    return {
        "status": "succeeded",
        "weeks_finalized": finalized,
        "matchups_refreshed": refreshed_matchups,
    }
