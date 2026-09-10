import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.dependencies import admin_user
from app.database.session import get_db
from app.features.predictions.models import Prediction, PredictionMatchup, PredictionWeek, WeekStatus
from app.features.predictions.routes import _sync_current
from app.features.predictions.service import score_pick
from app.models.season import Season
from app.models.user import User
from app.services.sleeper import SleeperService

router = APIRouter(prefix="/admin/predictions", tags=["admin predictions"], dependencies=[Depends(admin_user)])


@router.get("/current/submissions")
async def current_submission_status(admin: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    season, week, _ = await _sync_current(db)
    total_matchups = await db.scalar(
        select(func.count(PredictionMatchup.id)).where(PredictionMatchup.week_id == week.id)
    ) or 0
    submitted_count = (
        select(func.count(Prediction.id))
        .join(PredictionMatchup, PredictionMatchup.id == Prediction.matchup_id)
        .where(
            Prediction.user_id == User.id,
            PredictionMatchup.week_id == week.id,
            Prediction.selected_roster_id.is_not(None),
        )
        .correlate(User)
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            select(User.id, User.display_name, submitted_count.label("submitted_picks"))
            .where(User.is_active.is_(True), User.id != admin.id)
            .order_by(User.display_name)
        )
    ).all()
    return {
        "season": season.year,
        "week": week.week_number,
        "total_matchups": total_matchups,
        "users": [
            {
                "user_id": row.id,
                "display_name": row.display_name,
                "submitted_picks": row.submitted_picks,
            }
            for row in rows
        ],
    }


@router.post("/weeks/{week_id}/refresh")
async def refresh_week(week_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    week = await db.get(PredictionWeek, week_id)
    if not week:
        raise HTTPException(status_code=404, detail="Week not found")
    season = await db.get(Season, week.season_id)
    incoming = await SleeperService().weekly_matchups(season.sleeper_league_id, week.week_number)
    existing = {m.sleeper_matchup_id: m for m in (await db.scalars(select(PredictionMatchup).where(PredictionMatchup.week_id == week.id))).all()}
    for item in incoming:
        matchup = existing.get(item.matchup_id)
        if matchup:
            matchup.team_a_score, matchup.team_b_score = item.score_a, item.score_b
            matchup.team_a_name, matchup.team_b_name = item.team_a_name, item.team_b_name
            matchup.team_a_owner, matchup.team_b_owner = item.team_a_owner, item.team_b_owner
            matchup.team_a_record, matchup.team_b_record = item.team_a_record, item.team_b_record
        else:
            db.add(PredictionMatchup(week_id=week.id, sleeper_matchup_id=item.matchup_id, team_a_roster_id=item.roster_a, team_b_roster_id=item.roster_b, team_a_name=item.team_a_name, team_b_name=item.team_b_name, team_a_owner=item.team_a_owner, team_b_owner=item.team_b_owner, team_a_record=item.team_a_record, team_b_record=item.team_b_record, team_a_score=item.score_a, team_b_score=item.score_b))
    await db.commit()
    return {"matchups": len(incoming)}


@router.post("/weeks/{week_id}/finalize")
async def finalize_week(week_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    week = await db.get(PredictionWeek, week_id)
    if not week:
        raise HTTPException(status_code=404, detail="Week not found")
    matchups = (await db.scalars(select(PredictionMatchup).where(PredictionMatchup.week_id == week.id))).all()
    if any(m.team_a_score is None or m.team_b_score is None for m in matchups):
        raise HTTPException(status_code=409, detail="All matchup scores must be available")
    users = (await db.scalars(select(User).where(User.is_active.is_(True)))).all()
    for matchup in matchups:
        tied = matchup.team_a_score == matchup.team_b_score
        matchup.winner_roster_id = None if tied else matchup.team_a_roster_id if matchup.team_a_score > matchup.team_b_score else matchup.team_b_roster_id
        existing = {p.user_id: p for p in (await db.scalars(select(Prediction).where(Prediction.matchup_id == matchup.id))).all()}
        for user in users:
            pick = existing.get(user.id)
            if not pick:
                pick = Prediction(user_id=user.id, matchup_id=matchup.id, selected_roster_id=None)
                db.add(pick)
            pick.result = score_pick(pick.selected_roster_id, matchup.winner_roster_id, tied)
    week.status, week.finalized_at = WeekStatus.final, datetime.now(timezone.utc)
    await db.commit()
    return {"status": "final", "users_scored": len(users), "matchups_scored": len(matchups)}


@router.post("/weeks/{week_id}/recalculate")
async def recalculate(week_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    week = await db.get(PredictionWeek, week_id)
    if not week or week.status is not WeekStatus.final:
        raise HTTPException(status_code=409, detail="Only finalized weeks can be recalculated")
    matchups = (await db.scalars(select(PredictionMatchup).where(PredictionMatchup.week_id == week.id))).all()
    count = 0
    for matchup in matchups:
        tied = matchup.team_a_score == matchup.team_b_score
        for pick in (await db.scalars(select(Prediction).where(Prediction.matchup_id == matchup.id))).all():
            pick.result = score_pick(pick.selected_roster_id, matchup.winner_roster_id, tied)
            count += 1
    await db.commit()
    return {"recalculated": count}
