import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.dependencies import admin_user
from app.database.session import get_db
from app.features.predictions.models import Prediction, PredictionMatchup, PredictionWeek, WeekStatus
from app.features.predictions.operations import finalize_prediction_week, refresh_prediction_week
from app.features.predictions.routes import _sync_current
from app.models.user import User

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
    count = await refresh_prediction_week(db, week)
    await db.commit()
    return {"matchups": count}


@router.post("/weeks/{week_id}/finalize")
async def finalize_week(week_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    week = await db.get(PredictionWeek, week_id)
    if not week:
        raise HTTPException(status_code=404, detail="Week not found")
    result = await finalize_prediction_week(db, week)
    await db.commit()
    return result


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
