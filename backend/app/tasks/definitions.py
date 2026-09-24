from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import time

from sqlalchemy.ext.asyncio import AsyncSession

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


TASK_DEFINITIONS = (
    TaskDefinition(
        key="predictions.auto_finalize",
        description="Finalize prediction weeks and sync current-season history after the NFL week ends",
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
