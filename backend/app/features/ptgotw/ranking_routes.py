import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import admin_user, current_user
from app.database.session import get_db
from app.features.ptgotw.models import (
    PTGRankingBallot,
    PTGRankingBallotStatus,
    PTGRankingCandidate,
    PTGRankingItem,
    PTGRankingPeriod,
    PTGWriteup,
)
from app.models.user import User, UserRole


router = APIRouter(prefix="/ptgotw/rankings", tags=["PTGOTW rankings"])
admin_router = APIRouter(
    prefix="/admin/ptgotw/rankings",
    tags=["admin PTGOTW rankings"],
    dependencies=[Depends(admin_user)],
)
LEAGUE_TIMEZONE = ZoneInfo("America/Chicago")
ELIGIBLE_WEEKS = set(range(1, 13))


class RankingOrderUpdate(BaseModel):
    writeup_ids: list[uuid.UUID] = Field(min_length=1, max_length=12)
    revision: int = Field(ge=0)


class RankingRevision(BaseModel):
    revision: int = Field(ge=0)


class RankingSettingsUpdate(BaseModel):
    closes_at: datetime


class RankingOpenRequest(BaseModel):
    closes_at: datetime | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _input_as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=LEAGUE_TIMEZONE)
    return value.astimezone(timezone.utc)


def _stored_as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _explicit_utc(value: datetime | None) -> datetime | None:
    return _stored_as_utc(value) if value is not None else None


def _current_year() -> int:
    return datetime.now(LEAGUE_TIMEZONE).year


def _period_state(period: PTGRankingPeriod | None, now: datetime | None = None) -> str:
    if period is None or period.opened_at is None:
        return "preparing"
    current = now or _utc_now()
    if period.is_open and period.closes_at is not None and _stored_as_utc(period.closes_at) > current:
        return "open"
    return "closed"


def _require_manager(user: User) -> None:
    if user.role is not UserRole.user:
        raise HTTPException(status_code=403, detail="Only league managers can rank writeups")


async def _period_for_year(db: AsyncSession, year: int) -> PTGRankingPeriod | None:
    return await db.scalar(select(PTGRankingPeriod).where(PTGRankingPeriod.year == year))


async def _locked_period_for_year(db: AsyncSession, year: int) -> PTGRankingPeriod | None:
    return await db.scalar(
        select(PTGRankingPeriod)
        .where(PTGRankingPeriod.year == year)
        .with_for_update()
    )


async def _get_or_create_period(db: AsyncSession, year: int) -> PTGRankingPeriod:
    period = await _period_for_year(db, year)
    if period is not None:
        return period
    period = PTGRankingPeriod(year=year)
    db.add(period)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        period = await _period_for_year(db, year)
        if period is None:
            raise
    return period


async def _eligible_rows(
    db: AsyncSession,
    year: int,
    period: PTGRankingPeriod | None,
    *,
    lock_writeups: bool = False,
) -> list[tuple[PTGWriteup, str]]:
    if period is not None and period.opened_at is not None:
        return list((await db.execute(
            select(PTGWriteup, User.display_name)
            .join(PTGRankingCandidate, PTGRankingCandidate.writeup_id == PTGWriteup.id)
            .join(User, User.id == PTGWriteup.author_id)
            .where(PTGRankingCandidate.period_id == period.id)
            .order_by(PTGRankingCandidate.position)
        )).all())
    statement = (
        select(PTGWriteup, User.display_name)
        .join(User, User.id == PTGWriteup.author_id)
        .where(
            PTGWriteup.year == year,
            PTGWriteup.week.in_(ELIGIBLE_WEEKS),
            PTGWriteup.is_published.is_(True),
        )
        .order_by(PTGWriteup.week.desc())
    )
    if lock_writeups:
        statement = statement.with_for_update(of=PTGWriteup)
    return list((await db.execute(statement)).all())


async def _ballot_for_user(
    db: AsyncSession, period: PTGRankingPeriod | None, user_id: uuid.UUID
) -> PTGRankingBallot | None:
    if period is None:
        return None
    return await db.scalar(select(PTGRankingBallot).where(
        PTGRankingBallot.period_id == period.id,
        PTGRankingBallot.user_id == user_id,
    ))


async def _saved_ids(db: AsyncSession, ballot: PTGRankingBallot | None) -> list[uuid.UUID]:
    if ballot is None:
        return []
    return list((await db.scalars(
        select(PTGRankingItem.writeup_id)
        .where(PTGRankingItem.ballot_id == ballot.id)
        .order_by(PTGRankingItem.position)
    )).all())


def _effective_ids(
    candidate_rows: list[tuple[PTGWriteup, str]], saved_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    candidate_ids = [writeup.id for writeup, _ in candidate_rows]
    valid = set(candidate_ids)
    retained = [writeup_id for writeup_id in saved_ids if writeup_id in valid]
    retained_set = set(retained)
    missing = [writeup_id for writeup_id in candidate_ids if writeup_id not in retained_set]
    return missing + retained


def _writeup_payload(writeup: PTGWriteup, author_name: str) -> dict:
    return {
        "id": writeup.id,
        "year": writeup.year,
        "week": writeup.week,
        "author": {"id": writeup.author_id, "display_name": author_name},
        "updated_at": writeup.updated_at,
    }


async def _ranking_payload(
    db: AsyncSession, year: int, period: PTGRankingPeriod | None, user: User
) -> dict:
    candidate_rows = await _eligible_rows(db, year, period)
    ballot = await _ballot_for_user(db, period, user.id)
    effective_ids = _effective_ids(candidate_rows, await _saved_ids(db, ballot))
    details = {writeup.id: _writeup_payload(writeup, name) for writeup, name in candidate_rows}
    state = _period_state(period)
    return {
        "year": year,
        "state": state,
        "closes_at": _explicit_utc(period.closes_at) if period else None,
        "can_edit": state != "closed",
        "can_submit": state == "open",
        "ballot_status": ballot.status.value if ballot else "not_started",
        "revision": ballot.revision if ballot else 0,
        "submitted_at": _explicit_utc(ballot.submitted_at) if ballot else None,
        "writeups": [details[writeup_id] for writeup_id in effective_ids],
    }


async def _validate_order(
    db: AsyncSession,
    year: int,
    period: PTGRankingPeriod,
    writeup_ids: list[uuid.UUID],
) -> None:
    if _period_state(period) == "closed":
        raise HTTPException(status_code=409, detail="Rankings are closed")
    candidate_rows = await _eligible_rows(db, year, period)
    candidate_ids = [writeup.id for writeup, _ in candidate_rows]
    if len(writeup_ids) != len(set(writeup_ids)):
        raise HTTPException(status_code=422, detail="Each writeup can appear only once")
    if len(writeup_ids) != len(candidate_ids) or set(writeup_ids) != set(candidate_ids):
        raise HTTPException(status_code=422, detail="Rank every eligible writeup exactly once")


@router.get("/current")
async def current_ranking(
    year: int | None = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_manager(user)
    selected_year = year or _current_year()
    return await _ranking_payload(db, selected_year, await _period_for_year(db, selected_year), user)


@router.put("/current")
async def save_ranking(
    body: RankingOrderUpdate,
    year: int | None = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_manager(user)
    selected_year = year or _current_year()
    period = await _get_or_create_period(db, selected_year)
    period = await _locked_period_for_year(db, selected_year) or period
    await _validate_order(db, selected_year, period, body.writeup_ids)
    ballot = await _ballot_for_user(db, period, user.id)
    now = _utc_now()
    if ballot is None:
        if body.revision != 0:
            raise HTTPException(status_code=409, detail="This ranking changed on another device; reload and try again")
        ballot = PTGRankingBallot(
            period_id=period.id,
            user_id=user.id,
            status=PTGRankingBallotStatus.draft,
            revision=1,
            updated_at=now,
        )
        db.add(ballot)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status_code=409, detail="This ranking changed on another device; reload and try again") from None
    else:
        result = await db.execute(
            update(PTGRankingBallot)
            .where(PTGRankingBallot.id == ballot.id, PTGRankingBallot.revision == body.revision)
            .values(
                revision=body.revision + 1,
                status=PTGRankingBallotStatus.draft,
                submitted_at=None,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            await db.rollback()
            raise HTTPException(status_code=409, detail="This ranking changed on another device; reload and try again")
        await db.execute(delete(PTGRankingItem).where(PTGRankingItem.ballot_id == ballot.id))
    db.add_all([
        PTGRankingItem(ballot_id=ballot.id, writeup_id=writeup_id, position=index)
        for index, writeup_id in enumerate(body.writeup_ids, start=1)
    ])
    await db.commit()
    await db.refresh(ballot)
    return await _ranking_payload(db, selected_year, period, user)


@router.post("/current/submit")
async def submit_ranking(
    body: RankingRevision,
    year: int | None = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_manager(user)
    selected_year = year or _current_year()
    period = await _locked_period_for_year(db, selected_year)
    if period is None or _period_state(period) != "open":
        raise HTTPException(status_code=409, detail="Ranking submissions are not open")
    ballot = await _ballot_for_user(db, period, user.id)
    if ballot is None:
        raise HTTPException(status_code=422, detail="Save a complete ranking before submitting")
    saved_ids = await _saved_ids(db, ballot)
    await _validate_order(db, selected_year, period, saved_ids)
    now = _utc_now()
    result = await db.execute(
        update(PTGRankingBallot)
        .where(PTGRankingBallot.id == ballot.id, PTGRankingBallot.revision == body.revision)
        .values(
            revision=body.revision + 1,
            status=PTGRankingBallotStatus.submitted,
            submitted_at=now,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        await db.rollback()
        raise HTTPException(status_code=409, detail="This ranking changed on another device; reload and try again")
    await db.commit()
    return await _ranking_payload(db, selected_year, period, user)


def _validate_future_deadline(value: datetime) -> datetime:
    deadline = _input_as_utc(value)
    if deadline <= _utc_now():
        raise HTTPException(status_code=422, detail="Ranking deadline must be in the future")
    return deadline


@admin_router.put("/{year}/settings")
async def update_ranking_settings(
    year: int,
    body: RankingSettingsUpdate,
    admin: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db),
):
    period = await _get_or_create_period(db, year)
    period = await _locked_period_for_year(db, year) or period
    period.closes_at = _validate_future_deadline(body.closes_at)
    period.updated_by_user_id = admin.id
    await db.commit()
    return await _admin_payload(db, year, period)


@admin_router.post("/{year}/open")
async def open_ranking_period(
    year: int,
    body: RankingOpenRequest,
    admin: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db),
):
    period = await _get_or_create_period(db, year)
    period = await _locked_period_for_year(db, year) or period
    deadline_value = body.closes_at or period.closes_at
    if deadline_value is None:
        raise HTTPException(status_code=422, detail="Set a ranking deadline before opening submissions")
    deadline = _validate_future_deadline(deadline_value)
    if period.opened_at is None:
        rows = await _eligible_rows(db, year, None, lock_writeups=True)
        weeks = {writeup.week for writeup, _ in rows}
        authors = {writeup.author_id for writeup, _ in rows}
        if len(rows) != 12 or weeks != ELIGIBLE_WEEKS or len(authors) != 12:
            raise HTTPException(
                status_code=422,
                detail="Publish one Week 1 through 12 writeup for each of 12 distinct managers before opening rankings",
            )
        db.add_all([
            PTGRankingCandidate(period_id=period.id, writeup_id=writeup.id, position=index)
            for index, (writeup, _) in enumerate(rows, start=1)
        ])
        period.opened_at = _utc_now()
    period.closes_at = deadline
    period.is_open = True
    period.closed_at = None
    period.updated_by_user_id = admin.id
    await db.commit()
    return await _admin_payload(db, year, period)


@admin_router.post("/{year}/close")
async def close_ranking_period(
    year: int,
    admin: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db),
):
    period = await _locked_period_for_year(db, year)
    if period is None or period.opened_at is None:
        raise HTTPException(status_code=404, detail="Ranking period not found")
    period.is_open = False
    period.closed_at = _utc_now()
    period.updated_by_user_id = admin.id
    await db.commit()
    return await _admin_payload(db, year, period)


@admin_router.post("/{year}/reopen")
async def reopen_ranking_period(
    year: int,
    body: RankingSettingsUpdate,
    admin: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db),
):
    period = await _locked_period_for_year(db, year)
    if period is None or period.opened_at is None:
        raise HTTPException(status_code=404, detail="Ranking period not found")
    period.closes_at = _validate_future_deadline(body.closes_at)
    period.is_open = True
    period.closed_at = None
    period.updated_by_user_id = admin.id
    await db.commit()
    return await _admin_payload(db, year, period)


def _calculate_results(
    candidate_rows: list[tuple[PTGWriteup, str]],
    ballot_orders: list[list[uuid.UUID]],
) -> list[dict]:
    details = {writeup.id: (writeup, author_name) for writeup, author_name in candidate_rows}
    totals = {
        writeup.id: {
            "writeup_id": writeup.id,
            "week": writeup.week,
            "author": {"id": writeup.author_id, "display_name": author_name},
            "points": 0,
            "placement_votes": [0, 0, 0, 0, 0],
            "rank_total": 0,
            "ballot_count": 0,
        }
        for writeup, author_name in candidate_rows
    }
    for order in ballot_orders:
        for position, writeup_id in enumerate(order, start=1):
            if writeup_id not in details:
                continue
            row = totals[writeup_id]
            row["rank_total"] += position
            row["ballot_count"] += 1
            if position <= 5:
                row["points"] += 6 - position
                row["placement_votes"][position - 1] += 1
    ordered = sorted(
        totals.values(),
        key=lambda row: (
            -row["points"],
            *(-count for count in row["placement_votes"]),
            row["week"],
        ),
    )
    previous_signature = None
    previous_rank = 0
    for index, row in enumerate(ordered, start=1):
        signature = (row["points"], *row["placement_votes"])
        if signature != previous_signature:
            previous_rank = index
            previous_signature = signature
        row["rank"] = previous_rank
        row["top_five_appearances"] = sum(row["placement_votes"])
        row["average_rank"] = (
            round(row["rank_total"] / row["ballot_count"], 2) if row["ballot_count"] else None
        )
        del row["rank_total"]
    return ordered


async def _admin_payload(db: AsyncSession, year: int, period: PTGRankingPeriod | None) -> dict:
    candidate_rows = await _eligible_rows(db, year, period)
    candidate_details = {
        writeup.id: _writeup_payload(writeup, author_name)
        for writeup, author_name in candidate_rows
    }
    ballots = list((await db.scalars(
        select(PTGRankingBallot).where(
            PTGRankingBallot.period_id == period.id if period else False
        )
    )).all()) if period else []
    ballot_by_user = {ballot.user_id: ballot for ballot in ballots}
    effective_orders: dict[uuid.UUID, list[uuid.UUID]] = {}
    for ballot in ballots:
        effective_orders[ballot.id] = _effective_ids(candidate_rows, await _saved_ids(db, ballot))
    managers = list((await db.scalars(
        select(User)
        .where(
            User.role == UserRole.user,
            User.is_active.is_(True),
            User.is_deleted.is_(False),
        )
        .order_by(User.display_name)
    )).all())
    writeup_years = set((await db.scalars(select(PTGWriteup.year).distinct())).all())
    period_years = set((await db.scalars(select(PTGRankingPeriod.year).distinct())).all())
    manager_rows = []
    for manager in managers:
        ballot = ballot_by_user.get(manager.id)
        order = effective_orders.get(ballot.id, []) if ballot else []
        manager_rows.append({
            "user_id": manager.id,
            "display_name": manager.display_name,
            "last_active_at": _explicit_utc(manager.last_active_at),
            "status": ballot.status.value if ballot else "not_started",
            "revision": ballot.revision if ballot else 0,
            "updated_at": _explicit_utc(ballot.updated_at) if ballot else None,
            "submitted_at": _explicit_utc(ballot.submitted_at) if ballot else None,
            "writeups": [candidate_details[writeup_id] for writeup_id in order],
        })
    submitted_orders = [
        effective_orders[ballot.id]
        for ballot in ballots
        if ballot.status == PTGRankingBallotStatus.submitted
    ]
    all_orders = [effective_orders[ballot.id] for ballot in ballots]
    return {
        "year": year,
        "state": _period_state(period),
        "accepting_submissions": _period_state(period) == "open",
        "closes_at": _explicit_utc(period.closes_at) if period else None,
        "opened_at": _explicit_utc(period.opened_at) if period else None,
        "closed_at": _explicit_utc(period.closed_at) if period else None,
        "available_years": sorted(writeup_years | period_years | {year}, reverse=True),
        "candidate_count": len(candidate_rows),
        "managers": manager_rows,
        "submitted_results": _calculate_results(candidate_rows, submitted_orders),
        "all_saved_results": _calculate_results(candidate_rows, all_orders),
    }


@admin_router.get("/{year}")
async def ranking_status(
    year: int,
    _: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await _admin_payload(db, year, await _period_for_year(db, year))
