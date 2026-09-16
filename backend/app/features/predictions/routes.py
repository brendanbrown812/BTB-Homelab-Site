import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.dependencies import current_user
from app.database.session import get_db
from app.features.predictions.models import Prediction, PredictionMatchup, PredictionWeek, WeekStatus
from app.models.user import User, UserRole
from app.models.season import Season
from app.services.sleeper import SleeperMatchup, SleeperPlayer, SleeperService

router = APIRouter(prefix="/predictions", tags=["predictions"])
CENTRAL_TIME = ZoneInfo("America/Chicago")


class PickInput(BaseModel):
    matchup_id: uuid.UUID
    selected_roster_id: int | None


class PickCard(BaseModel):
    picks: list[PickInput]


def _default_lock_at(now: datetime | None = None) -> datetime:
    now = now.astimezone(CENTRAL_TIME) if now else datetime.now(CENTRAL_TIME)
    days = (3 - now.weekday()) % 7
    candidate = datetime.combine((now + timedelta(days=days)).date(), time(19, 0), tzinfo=now.tzinfo)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate.astimezone(timezone.utc)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _migrate_friday_lock_to_thursday(week: PredictionWeek) -> bool:
    local_lock = _utc(week.lock_at).astimezone(CENTRAL_TIME)
    if week.status is not WeekStatus.open or local_lock.weekday() != 4:
        return False
    thursday = datetime.combine(local_lock.date() - timedelta(days=1), time(19, 0), tzinfo=CENTRAL_TIME)
    week.lock_at = thursday.astimezone(timezone.utc)
    return True


async def _sync_current(db: AsyncSession, include_rosters: bool = False) -> tuple[Season, PredictionWeek, list[SleeperMatchup]]:
    season = await db.scalar(select(Season).where(Season.is_active.is_(True)))
    if not season:
        raise HTTPException(status_code=503, detail="No active BTB season is configured. Set SLEEPER_LEAGUE_ID and restart the backend.")
    sleeper = SleeperService()
    week_number = await sleeper.current_week()
    week = await db.scalar(select(PredictionWeek).where(PredictionWeek.season_id == season.id, PredictionWeek.week_number == week_number))
    if not week:
        week = PredictionWeek(season_id=season.id, week_number=week_number, lock_at=_default_lock_at(), status=WeekStatus.open)
        db.add(week)
        await db.flush()
    else:
        _migrate_friday_lock_to_thursday(week)
    incoming = await sleeper.weekly_matchups(season.sleeper_league_id, week_number, include_players=include_rosters)
    if week.status is not WeekStatus.final:
        existing = {m.sleeper_matchup_id: m for m in (await db.scalars(select(PredictionMatchup).where(PredictionMatchup.week_id == week.id))).all()}
        for item in incoming:
            matchup = existing.get(item.matchup_id)
            values = dict(team_a_roster_id=item.roster_a, team_b_roster_id=item.roster_b, team_a_name=item.team_a_name, team_b_name=item.team_b_name, team_a_owner=item.team_a_owner, team_b_owner=item.team_b_owner, team_a_record=item.team_a_record, team_b_record=item.team_b_record, team_a_score=item.score_a, team_b_score=item.score_b)
            if matchup:
                for key, value in values.items():
                    setattr(matchup, key, value)
            else:
                db.add(PredictionMatchup(week_id=week.id, sleeper_matchup_id=item.matchup_id, **values))
        await db.commit()
    return season, week, incoming


@router.get("/current")
async def current_week(include_rosters: bool = False, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    season, week, live_matchups = await _sync_current(db, include_rosters)
    matchups = (await db.scalars(select(PredictionMatchup).where(PredictionMatchup.week_id == week.id).order_by(PredictionMatchup.sleeper_matchup_id))).all()
    picks_query = select(Prediction).where(Prediction.matchup_id.in_([m.id for m in matchups]))
    public = datetime.now(timezone.utc) >= _utc(week.lock_at)
    if not public:
        picks_query = picks_query.where(Prediction.user_id == user.id)
    picks = (await db.scalars(picks_query)).all()
    live_by_matchup = {item.matchup_id: item for item in live_matchups}

    def players_payload(players: tuple[SleeperPlayer, ...]) -> list[dict]:
        return [{
            "player_id": player.player_id,
            "name": player.name,
            "position": player.position,
            "team": player.team,
            "injury_status": player.injury_status,
            "points": player.points,
            "image_url": player.image_url,
        } for player in players]

    def team_payload(matchup: PredictionMatchup, side: str) -> dict:
        live = live_by_matchup.get(matchup.sleeper_matchup_id)
        roster_id = getattr(matchup, f"team_{side}_roster_id")
        live_side = "a" if live and live.roster_a == roster_id else "b"
        result = {
            "roster_id": roster_id,
            "name": getattr(matchup, f"team_{side}_name"),
            "owner": getattr(matchup, f"team_{side}_owner"),
            "record": getattr(matchup, f"team_{side}_record"),
            "score": getattr(matchup, f"team_{side}_score"),
            "avatar_url": getattr(live, f"team_{live_side}_avatar_url") if live else None,
        }
        if include_rosters and live:
            result["starters"] = players_payload(getattr(live, f"team_{live_side}_starters"))
            result["bench"] = players_payload(getattr(live, f"team_{live_side}_bench"))
        return result

    return {
        "season": {"id": season.id, "year": season.year},
        "week": {"id": week.id, "number": week.week_number, "status": week.status.value, "lock_at": week.lock_at, "picks_public": public},
        "matchups": [{"id": m.id, "sleeper_matchup_id": m.sleeper_matchup_id, "team_a": team_payload(m, "a"), "team_b": team_payload(m, "b"), "winner_roster_id": m.winner_roster_id} for m in matchups],
        "picks": [{"user_id": p.user_id, "matchup_id": p.matchup_id, "selected_roster_id": p.selected_roster_id, "result": p.result.value if p.result else None} for p in picks],
    }


@router.get("/weeks/{week_id}")
async def get_week(week_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    week = await db.get(PredictionWeek, week_id)
    if not week:
        raise HTTPException(status_code=404, detail="Week not found")
    matchups = (await db.scalars(select(PredictionMatchup).where(PredictionMatchup.week_id == week_id))).all()
    picks_query = select(Prediction).join(PredictionMatchup).where(PredictionMatchup.week_id == week_id)
    if datetime.now(timezone.utc) < _utc(week.lock_at):
        picks_query = picks_query.where(Prediction.user_id == user.id)
    picks = (await db.scalars(picks_query)).all()
    return {"week": week, "matchups": matchups, "picks": picks, "picks_public": datetime.now(timezone.utc) >= _utc(week.lock_at)}


@router.put("/weeks/{week_id}/picks")
async def save_picks(week_id: uuid.UUID, body: PickCard, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    week = await db.get(PredictionWeek, week_id)
    if not week or week.status is not WeekStatus.open or datetime.now(timezone.utc) >= _utc(week.lock_at):
        raise HTTPException(status_code=409, detail="Picks are locked")
    allowed = set((await db.scalars(select(PredictionMatchup.id).where(PredictionMatchup.week_id == week_id))).all())
    if any(p.matchup_id not in allowed for p in body.picks):
        raise HTTPException(status_code=400, detail="Pick does not belong to this week")
    for item in body.picks:
        pick = await db.scalar(select(Prediction).where(Prediction.user_id == user.id, Prediction.matchup_id == item.matchup_id))
        if pick:
            pick.selected_roster_id = item.selected_roster_id
        else:
            db.add(Prediction(user_id=user.id, matchup_id=item.matchup_id, selected_roster_id=item.selected_roster_id))
    await db.commit()
    return {"saved": len(body.picks)}


@router.get("/seasons/{season_id}/standings")
async def season_standings(season_id: uuid.UUID, _: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    participating_users = (
        select(Prediction.user_id)
        .join(PredictionMatchup, PredictionMatchup.id == Prediction.matchup_id)
        .join(PredictionWeek, PredictionWeek.id == PredictionMatchup.week_id)
        .where(
            PredictionWeek.season_id == season_id,
            Prediction.selected_roster_id.is_not(None),
        )
        .distinct()
    )
    query = (select(User.id, User.display_name,
        func.count(case((Prediction.result == "win", 1))).label("wins"),
        func.count(case((Prediction.result == "loss", 1))).label("losses"),
        func.count(case((Prediction.result == "push", 1))).label("pushes"))
        .join(Prediction, Prediction.user_id == User.id)
        .join(PredictionMatchup, PredictionMatchup.id == Prediction.matchup_id)
        .join(PredictionWeek, PredictionWeek.id == PredictionMatchup.week_id)
        .where(
            PredictionWeek.season_id == season_id,
            PredictionWeek.status == WeekStatus.final,
            User.role == UserRole.user,
            User.id.in_(participating_users),
        )
        .group_by(User.id).order_by(func.count(case((Prediction.result == "win", 1))).desc()))
    rows = (await db.execute(query)).all()
    return [{"user_id": r.id, "display_name": r.display_name, "wins": r.wins, "losses": r.losses, "pushes": r.pushes} for r in rows]


@router.get("/seasons/{season_id}/history")
async def prediction_history(season_id: uuid.UUID, _: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    weeks = (await db.scalars(select(PredictionWeek).where(PredictionWeek.season_id == season_id, PredictionWeek.status == WeekStatus.final).order_by(PredictionWeek.week_number.desc()))).all()
    history = []
    for week in weeks:
        participating_users = (
            select(Prediction.user_id)
            .join(PredictionMatchup, PredictionMatchup.id == Prediction.matchup_id)
            .where(
                PredictionMatchup.week_id == week.id,
                Prediction.selected_roster_id.is_not(None),
            )
            .distinct()
        )
        query = (select(User.display_name, func.count(case((Prediction.result == "win", 1))).label("wins"), func.count(case((Prediction.result == "loss", 1))).label("losses"), func.count(case((Prediction.result == "push", 1))).label("pushes"))
            .join(Prediction, Prediction.user_id == User.id).join(PredictionMatchup, PredictionMatchup.id == Prediction.matchup_id)
            .where(
                PredictionMatchup.week_id == week.id,
                User.role == UserRole.user,
                User.id.in_(participating_users),
            ).group_by(User.id).order_by(func.count(case((Prediction.result == "win", 1))).desc()))
        records = (await db.execute(query)).all()
        high = records[0].wins if records else 0
        history.append({"week": week.week_number, "finalized_at": week.finalized_at, "champions": [r.display_name for r in records if r.wins == high], "records": [{"name": r.display_name, "wins": r.wins, "losses": r.losses, "pushes": r.pushes} for r in records]})
    return history
