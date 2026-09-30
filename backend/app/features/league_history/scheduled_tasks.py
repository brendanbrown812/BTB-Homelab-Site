from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.league_history.sleeper_importer import import_sleeper_season
from app.models.season import Season, SeasonPlatform


async def refresh_active_sleeper_history(db: AsyncSession) -> dict:
    """Import the active Sleeper season for the public league-history pages."""
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

    result = await import_sleeper_season(db, season.id)
    import_status = str(result.get("status") or "unknown")
    if import_status != "succeeded":
        raise RuntimeError(f"Current-season history sync finished with status {import_status}")

    counts = result.get("counts") or {}
    return {
        "status": "succeeded",
        "season_id": str(season.id),
        "season_year": season.year,
        "matchups": counts.get("matchups", 0),
    }
