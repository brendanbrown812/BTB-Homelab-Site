from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.league_history.scheduled_tasks import refresh_active_sleeper_history
from app.features.predictions.scheduled_tasks import (
    auto_finalize_prediction_weeks,
    send_prediction_deadline_reminder,
)
from app.tasks.schedules import WeeklySchedule


TaskHandler = Callable[[AsyncSession], Awaitable[dict]]


@dataclass(frozen=True)
class TaskDefinition:
    key: str
    description: str
    schedule: WeeklySchedule
    handler: TaskHandler
    run_on_registration: bool = False


TASK_DEFINITIONS = (
    TaskDefinition(
        key="league_history.refresh_active_sleeper",
        description="Import completed games for the active Sleeper season",
        schedule=WeeklySchedule(weekday=1, at=time(7, 0), timezone_name="America/Chicago"),
        handler=refresh_active_sleeper_history,
        run_on_registration=True,
    ),
    TaskDefinition(
        key="predictions.auto_finalize",
        description="Finalize prediction weeks after the NFL week ends",
        schedule=WeeklySchedule(weekday=1, at=time(7, 0), timezone_name="America/Chicago"),
        handler=auto_finalize_prediction_weeks,
    ),
    TaskDefinition(
        key="predictions.deadline_reminder",
        description="Send the Discord reminder 12 hours before predictions close",
        schedule=WeeklySchedule(weekday=3, at=time(7, 0), timezone_name="America/Chicago"),
        handler=send_prediction_deadline_reminder,
    ),
)

TASKS_BY_KEY = {definition.key: definition for definition in TASK_DEFINITIONS}
