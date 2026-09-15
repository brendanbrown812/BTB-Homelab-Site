from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.predictions.models import (
    Prediction,
    PredictionMatchup,
    PredictionWeek,
    WeekStatus,
)
from app.features.predictions.service import score_pick
from app.models.season import Season
from app.models.user import User
from app.services.sleeper import SleeperService


async def refresh_prediction_week(
    db: AsyncSession,
    week: PredictionWeek,
    sleeper: SleeperService | None = None,
) -> int:
    """Refresh a stored prediction week without committing the transaction."""
    season = await db.get(Season, week.season_id)
    if not season or not season.sleeper_league_id:
        raise RuntimeError("Prediction week does not belong to a configured Sleeper season")

    incoming = await (sleeper or SleeperService()).weekly_matchups(
        season.sleeper_league_id,
        week.week_number,
    )
    existing = {
        matchup.sleeper_matchup_id: matchup
        for matchup in (
            await db.scalars(
                select(PredictionMatchup).where(PredictionMatchup.week_id == week.id)
            )
        ).all()
    }
    for item in incoming:
        matchup = existing.get(item.matchup_id)
        values = {
            "team_a_roster_id": item.roster_a,
            "team_b_roster_id": item.roster_b,
            "team_a_name": item.team_a_name,
            "team_b_name": item.team_b_name,
            "team_a_owner": item.team_a_owner,
            "team_b_owner": item.team_b_owner,
            "team_a_record": item.team_a_record,
            "team_b_record": item.team_b_record,
            "team_a_score": item.score_a,
            "team_b_score": item.score_b,
        }
        if matchup:
            for key, value in values.items():
                setattr(matchup, key, value)
        else:
            db.add(
                PredictionMatchup(
                    week_id=week.id,
                    sleeper_matchup_id=item.matchup_id,
                    **values,
                )
            )
    await db.flush()
    return len(incoming)


async def finalize_prediction_week(db: AsyncSession, week: PredictionWeek) -> dict:
    """Score a prediction week once, without committing the transaction."""
    if week.status is WeekStatus.final:
        return {
            "status": "final",
            "already_finalized": True,
            "users_scored": 0,
            "matchups_scored": 0,
        }

    matchups = (
        await db.scalars(
            select(PredictionMatchup).where(PredictionMatchup.week_id == week.id)
        )
    ).all()
    if not matchups:
        raise HTTPException(status_code=409, detail="No matchups are available")
    if any(matchup.team_a_score is None or matchup.team_b_score is None for matchup in matchups):
        raise HTTPException(status_code=409, detail="All matchup scores must be available")

    users = (await db.scalars(select(User).where(User.is_active.is_(True)))).all()
    for matchup in matchups:
        tied = matchup.team_a_score == matchup.team_b_score
        matchup.winner_roster_id = (
            None
            if tied
            else matchup.team_a_roster_id
            if matchup.team_a_score > matchup.team_b_score
            else matchup.team_b_roster_id
        )
        existing = {
            prediction.user_id: prediction
            for prediction in (
                await db.scalars(
                    select(Prediction).where(Prediction.matchup_id == matchup.id)
                )
            ).all()
        }
        for user in users:
            pick = existing.get(user.id)
            if not pick:
                pick = Prediction(
                    user_id=user.id,
                    matchup_id=matchup.id,
                    selected_roster_id=None,
                )
                db.add(pick)
            pick.result = score_pick(pick.selected_roster_id, matchup.winner_roster_id, tied)

    week.status = WeekStatus.final
    week.finalized_at = datetime.now(timezone.utc)
    await db.flush()
    return {
        "status": "final",
        "already_finalized": False,
        "users_scored": len(users),
        "matchups_scored": len(matchups),
    }
