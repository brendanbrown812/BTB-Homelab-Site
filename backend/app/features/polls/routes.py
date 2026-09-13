import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import admin_user, current_user
from app.database.session import get_db
from app.features.polls.models import Poll, PollOption, PollSelectionMode, PollVote
from app.models.user import User, UserRole

router = APIRouter(prefix="/polls", tags=["polls"])


class PollCreate(BaseModel):
    question: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=10000)
    selection_mode: PollSelectionMode
    options: list[str] = Field(min_length=2)
    closes_at: datetime | None = None


class VoteUpdate(BaseModel):
    option_ids: list[uuid.UUID] = Field(min_length=1)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _is_open(poll: Poll) -> bool:
    return poll.closed_at is None and (poll.closes_at is None or _as_utc(poll.closes_at) > _utc_now())


async def _poll_payload(poll: Poll, viewer: User, db: AsyncSession) -> dict:
    options = (await db.scalars(select(PollOption).where(PollOption.poll_id == poll.id).order_by(PollOption.position))).all()
    active_users = (await db.scalars(select(User).where(User.is_active.is_(True), User.is_deleted.is_(False)).order_by(User.display_name))).all()
    active_by_id = {user.id: user for user in active_users}
    vote_rows = (await db.execute(select(PollVote.user_id, PollVote.option_id).where(PollVote.poll_id == poll.id))).all()
    votes_by_option: dict[uuid.UUID, list[dict]] = {option.id: [] for option in options}
    voted_user_ids: set[uuid.UUID] = set()
    viewer_option_ids: list[uuid.UUID] = []
    for user_id, option_id in vote_rows:
        voting_user = active_by_id.get(user_id)
        if not voting_user or option_id not in votes_by_option:
            continue
        votes_by_option[option_id].append({"id": voting_user.id, "display_name": voting_user.display_name})
        voted_user_ids.add(user_id)
        if user_id == viewer.id:
            viewer_option_ids.append(option_id)
    for voters in votes_by_option.values():
        voters.sort(key=lambda voter: voter["display_name"].casefold())
    option_positions = {option.id: option.position for option in options}
    viewer_option_ids.sort(key=lambda option_id: option_positions[option_id])
    creator_name = await db.scalar(select(User.display_name).where(User.id == poll.created_by_user_id))
    return {
        "id": poll.id,
        "question": poll.question,
        "description": poll.description,
        "selection_mode": poll.selection_mode.value,
        "closes_at": poll.closes_at,
        "closed_at": poll.closed_at,
        "created_at": poll.created_at,
        "created_by": {"id": poll.created_by_user_id, "display_name": creator_name or "Unknown user"},
        "is_open": _is_open(poll),
        "options": [
            {"id": option.id, "text": option.text, "position": option.position, "voters": votes_by_option[option.id]}
            for option in options
        ],
        "current_user_option_ids": viewer_option_ids,
        "not_voted": [
            {"id": active_user.id, "display_name": active_user.display_name}
            for active_user in active_users
            if active_user.role is UserRole.user and active_user.id not in voted_user_ids
        ],
    }


@router.get("")
async def list_polls(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    polls = (await db.scalars(select(Poll).order_by(Poll.created_at.desc()))).all()
    return {
        "is_admin": user.role is UserRole.admin,
        "polls": [await _poll_payload(poll, user, db) for poll in polls],
    }


@router.post("", status_code=201)
async def create_poll(body: PollCreate, admin: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    question = body.question.strip()
    description = body.description.strip() if body.description else None
    options = [option.strip() for option in body.options]
    if not question:
        raise HTTPException(status_code=422, detail="Poll question cannot be blank")
    if any(not option for option in options):
        raise HTTPException(status_code=422, detail="Poll options cannot be blank")
    if any(len(option) > 240 for option in options):
        raise HTTPException(status_code=422, detail="Poll options cannot exceed 240 characters")
    if len({option.casefold() for option in options}) != len(options):
        raise HTTPException(status_code=422, detail="Poll options must be unique")
    if body.closes_at is not None and _as_utc(body.closes_at) <= _utc_now():
        raise HTTPException(status_code=422, detail="Closing time must be in the future")
    poll = Poll(
        question=question,
        description=description or None,
        selection_mode=body.selection_mode,
        closes_at=body.closes_at,
        created_by_user_id=admin.id,
    )
    db.add(poll)
    await db.flush()
    db.add_all([PollOption(poll_id=poll.id, text=option, position=index) for index, option in enumerate(options)])
    await db.commit()
    await db.refresh(poll)
    return await _poll_payload(poll, admin, db)


@router.put("/{poll_id}")
async def update_and_reopen_poll(poll_id: uuid.UUID, body: PollCreate, admin: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    poll = await db.get(Poll, poll_id)
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    if _is_open(poll):
        raise HTTPException(status_code=400, detail="Only completed polls can be edited and re-opened")
    question = body.question.strip()
    description = body.description.strip() if body.description else None
    options = [option.strip() for option in body.options]
    if not question:
        raise HTTPException(status_code=422, detail="Poll question cannot be blank")
    if any(not option for option in options):
        raise HTTPException(status_code=422, detail="Poll options cannot be blank")
    if any(len(option) > 240 for option in options):
        raise HTTPException(status_code=422, detail="Poll options cannot exceed 240 characters")
    if len({option.casefold() for option in options}) != len(options):
        raise HTTPException(status_code=422, detail="Poll options must be unique")
    if body.closes_at is not None and _as_utc(body.closes_at) <= _utc_now():
        raise HTTPException(status_code=422, detail="Closing time must be in the future to re-open this poll")
    existing_options = (await db.scalars(select(PollOption).where(PollOption.poll_id == poll.id).order_by(PollOption.position))).all()
    choices_changed = body.selection_mode is not poll.selection_mode or options != [option.text for option in existing_options]
    if choices_changed:
        await db.execute(delete(PollVote).where(PollVote.poll_id == poll.id))
        await db.execute(delete(PollOption).where(PollOption.poll_id == poll.id))
        await db.flush()
        db.add_all([PollOption(poll_id=poll.id, text=option, position=index) for index, option in enumerate(options)])
    poll.question = question
    poll.description = description or None
    poll.selection_mode = body.selection_mode
    poll.closes_at = body.closes_at
    poll.closed_at = None
    await db.commit()
    await db.refresh(poll)
    return await _poll_payload(poll, admin, db)


@router.put("/{poll_id}/vote")
async def update_vote(poll_id: uuid.UUID, body: VoteUpdate, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    poll = await db.get(Poll, poll_id)
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    if not _is_open(poll):
        raise HTTPException(status_code=400, detail="This poll is closed")
    option_ids = list(dict.fromkeys(body.option_ids))
    if poll.selection_mode is PollSelectionMode.single and len(option_ids) != 1:
        raise HTTPException(status_code=422, detail="Choose exactly one option")
    valid_option_ids = set((await db.scalars(select(PollOption.id).where(PollOption.poll_id == poll.id))).all())
    if any(option_id not in valid_option_ids for option_id in option_ids):
        raise HTTPException(status_code=422, detail="One or more choices do not belong to this poll")
    await db.execute(delete(PollVote).where(PollVote.poll_id == poll.id, PollVote.user_id == user.id))
    db.add_all([PollVote(poll_id=poll.id, user_id=user.id, option_id=option_id) for option_id in option_ids])
    await db.commit()
    return await _poll_payload(poll, user, db)


@router.post("/{poll_id}/close")
async def close_poll(poll_id: uuid.UUID, admin: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    poll = await db.get(Poll, poll_id)
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    if poll.closed_at is None:
        poll.closed_at = _utc_now()
        await db.commit()
    return await _poll_payload(poll, admin, db)
