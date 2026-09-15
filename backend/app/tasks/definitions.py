from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.predictions.scheduled_tasks import auto_finalize_prediction_weeks
from app.tasks.schedules import WeeklySchedule


TaskHandler = Callable[[AsyncSession], Awaitable[dict]]


@dataclass(frozen=True)
class TaskDefinition:
    key: str
    description: str
    schedule: WeeklySchedule
    handler: TaskHandler


TASK_DEFINITIONS = (
    TaskDefinition(
        key="predictions.auto_finalize",
        description="Refresh and finalize prediction weeks after the NFL week ends",
        schedule=WeeklySchedule(weekday=1, at=time(7, 0), timezone_name="America/Chicago"),
        handler=auto_finalize_prediction_weeks,
    ),
)

TASKS_BY_KEY = {definition.key: definition for definition in TASK_DEFINITIONS}
