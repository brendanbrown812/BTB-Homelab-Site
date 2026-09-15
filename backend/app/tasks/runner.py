import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.tasks.definitions import TASK_DEFINITIONS, TASKS_BY_KEY, TaskDefinition
from app.tasks.models import ScheduledTask, ScheduledTaskRun, ScheduledTaskRunStatus
from app.tasks.schedules import as_utc


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClaimedTask:
    definition: TaskDefinition
    run_id: uuid.UUID
    scheduled_for: datetime
    advance_schedule: bool = True


async def sync_task_definitions(db: AsyncSession, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    existing = {
        task.task_key: task
        for task in (await db.scalars(select(ScheduledTask))).all()
    }
    for definition in TASK_DEFINITIONS:
        task = existing.get(definition.key)
        if task:
            task.description = definition.description
            task.schedule = definition.schedule.label
        else:
            db.add(
                ScheduledTask(
                    task_key=definition.key,
                    description=definition.description,
                    schedule=definition.schedule.label,
                    next_run_at=definition.schedule.next_after(now),
                )
            )
    await db.commit()


async def claim_next_due_task(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    lease_seconds: int = 15 * 60,
) -> ClaimedTask | None:
    now = now or datetime.now(timezone.utc)
    task = await db.scalar(
        select(ScheduledTask)
        .where(
            ScheduledTask.enabled.is_(True),
            ScheduledTask.next_run_at <= now,
            or_(ScheduledTask.locked_until.is_(None), ScheduledTask.locked_until <= now),
        )
        .order_by(ScheduledTask.next_run_at, ScheduledTask.task_key)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if not task:
        return None

    definition = TASKS_BY_KEY.get(task.task_key)
    if not definition:
        task.enabled = False
        task.last_error = "No registered handler exists for this task"
        await db.commit()
        return None

    stale_runs = (
        await db.scalars(
            select(ScheduledTaskRun).where(
                ScheduledTaskRun.task_key == task.task_key,
                ScheduledTaskRun.status == ScheduledTaskRunStatus.running,
            )
        )
    ).all()
    for stale in stale_runs:
        stale.status = ScheduledTaskRunStatus.failed
        stale.finished_at = now
        stale.error = "The scheduler lease expired before this run completed"

    run = ScheduledTaskRun(
        task_key=task.task_key,
        scheduled_for=task.next_run_at,
        started_at=now,
        status=ScheduledTaskRunStatus.running,
    )
    db.add(run)
    task.locked_until = now + timedelta(seconds=lease_seconds)
    task.last_started_at = now
    task.last_status = ScheduledTaskRunStatus.running
    await db.commit()
    return ClaimedTask(definition=definition, run_id=run.id, scheduled_for=run.scheduled_for)


async def _record_success(
    db: AsyncSession,
    claim: ClaimedTask,
    result: dict,
    now: datetime,
) -> None:
    run = await db.get(ScheduledTaskRun, claim.run_id)
    task = await db.get(ScheduledTask, claim.definition.key)
    if not run or not task:
        raise RuntimeError("Scheduled task state disappeared while the task was running")
    outcome = result.get("status")
    status = (
        ScheduledTaskRunStatus.skipped
        if outcome == ScheduledTaskRunStatus.skipped.value
        else ScheduledTaskRunStatus.succeeded
    )
    run.status = status
    run.result = result
    run.finished_at = now
    task.last_status = status
    task.last_finished_at = now
    task.last_error = None
    task.consecutive_failures = 0
    task.locked_until = None
    if claim.advance_schedule:
        task.next_run_at = claim.definition.schedule.next_after(now)
    await db.commit()


async def _record_failure(
    session_factory: async_sessionmaker[AsyncSession],
    claim: ClaimedTask,
    error: Exception,
    *,
    now: datetime,
    retry_minutes: int,
) -> None:
    message = f"{type(error).__name__}: {error}"[:4000]
    async with session_factory() as db:
        run = await db.get(ScheduledTaskRun, claim.run_id)
        task = await db.get(ScheduledTask, claim.definition.key)
        if run:
            run.status = ScheduledTaskRunStatus.failed
            run.error = message
            run.finished_at = now
        if task:
            task.last_status = ScheduledTaskRunStatus.failed
            task.last_finished_at = now
            task.last_error = message
            task.consecutive_failures += 1
            task.locked_until = None
            if claim.advance_schedule:
                task.next_run_at = now + timedelta(minutes=retry_minutes)
        await db.commit()


async def execute_claimed_task(
    session_factory: async_sessionmaker[AsyncSession],
    claim: ClaimedTask,
    *,
    retry_minutes: int = 15,
) -> ScheduledTaskRunStatus:
    try:
        async with session_factory() as db:
            result = await claim.definition.handler(db)
            now = datetime.now(timezone.utc)
            await _record_success(db, claim, result, now)
            status = (
                ScheduledTaskRunStatus.skipped
                if result.get("status") == "skipped"
                else ScheduledTaskRunStatus.succeeded
            )
            logger.info("Scheduled task %s finished with status %s", claim.definition.key, status.value)
            return status
    except Exception as exc:
        now = datetime.now(timezone.utc)
        await _record_failure(
            session_factory,
            claim,
            exc,
            now=now,
            retry_minutes=retry_minutes,
        )
        logger.exception("Scheduled task %s failed", claim.definition.key)
        return ScheduledTaskRunStatus.failed


async def run_due_tasks_once(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    now: datetime | None = None,
    lease_seconds: int = 15 * 60,
    retry_minutes: int = 15,
) -> int:
    async with session_factory() as db:
        claim = await claim_next_due_task(db, now=now, lease_seconds=lease_seconds)
    if not claim:
        return 0
    await execute_claimed_task(session_factory, claim, retry_minutes=retry_minutes)
    return 1


async def run_task_now(
    session_factory: async_sessionmaker[AsyncSession],
    task_key: str,
) -> uuid.UUID:
    definition = TASKS_BY_KEY.get(task_key)
    if not definition:
        raise KeyError(task_key)
    now = datetime.now(timezone.utc)
    async with session_factory() as db:
        task = await db.scalar(
            select(ScheduledTask).where(ScheduledTask.task_key == task_key).with_for_update()
        )
        if not task:
            await sync_task_definitions(db, now)
            task = await db.get(ScheduledTask, task_key)
        if task.locked_until and as_utc(task.locked_until) > now:
            raise RuntimeError("Scheduled task is already running")
        advance_schedule = as_utc(task.next_run_at) <= now
        run = ScheduledTaskRun(
            task_key=task_key,
            scheduled_for=now,
            started_at=now,
            status=ScheduledTaskRunStatus.running,
        )
        db.add(run)
        task.locked_until = now + timedelta(minutes=15)
        task.last_started_at = now
        task.last_status = ScheduledTaskRunStatus.running
        await db.commit()
        claim = ClaimedTask(
            definition=definition,
            run_id=run.id,
            scheduled_for=now,
            advance_schedule=advance_schedule,
        )
    await execute_claimed_task(session_factory, claim)
    return claim.run_id
