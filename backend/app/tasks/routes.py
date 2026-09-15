from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import admin_user
from app.database.session import SessionLocal, get_db
from app.tasks.models import ScheduledTask, ScheduledTaskRun
from app.tasks.runner import run_task_now


router = APIRouter(
    prefix="/admin/tasks",
    tags=["admin tasks"],
    dependencies=[Depends(admin_user)],
)


@router.get("")
async def list_tasks(db: AsyncSession = Depends(get_db)):
    tasks = (await db.scalars(select(ScheduledTask).order_by(ScheduledTask.task_key))).all()
    return [
        {
            "key": task.task_key,
            "description": task.description,
            "schedule": task.schedule,
            "enabled": task.enabled,
            "next_run_at": task.next_run_at,
            "last_started_at": task.last_started_at,
            "last_finished_at": task.last_finished_at,
            "last_status": task.last_status.value if task.last_status else None,
            "consecutive_failures": task.consecutive_failures,
            "last_error": task.last_error,
        }
        for task in tasks
    ]


@router.get("/runs")
async def list_task_runs(limit: int = 50, db: AsyncSession = Depends(get_db)):
    limit = max(1, min(limit, 200))
    runs = (
        await db.scalars(
            select(ScheduledTaskRun).order_by(ScheduledTaskRun.started_at.desc()).limit(limit)
        )
    ).all()
    return [
        {
            "id": run.id,
            "task_key": run.task_key,
            "scheduled_for": run.scheduled_for,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "status": run.status.value,
            "result": run.result,
            "error": run.error,
        }
        for run in runs
    ]


@router.post("/{task_key}/run")
async def trigger_task(task_key: str):
    try:
        run_id = await run_task_now(SessionLocal, task_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Scheduled task not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"run_id": run_id}
