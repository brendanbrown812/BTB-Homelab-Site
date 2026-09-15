import unittest
from datetime import datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.dependencies import admin_user
from app.database.base import Base
from app.features.predictions.models import PredictionMatchup, PredictionWeek, WeekStatus
from app.features.predictions.scheduled_tasks import auto_finalize_prediction_weeks
from app.models.season import Season
from app.models.user import User, UserRole
from app.tasks.models import ScheduledTask, ScheduledTaskRun, ScheduledTaskRunStatus
from app.tasks.runner import claim_next_due_task, run_due_tasks_once, sync_task_definitions
from app.tasks.routes import router as task_router
from app.tasks.schedules import WeeklySchedule


class WeeklyScheduleTests(unittest.TestCase):
    def setUp(self):
        self.schedule = WeeklySchedule(weekday=1, at=time(7), timezone_name="America/Chicago")

    def test_next_run_is_tuesday_at_seven_central_during_daylight_time(self):
        after = datetime(2026, 9, 14, 18, tzinfo=timezone.utc)
        self.assertEqual(
            self.schedule.next_after(after),
            datetime(2026, 9, 15, 12, tzinfo=timezone.utc),
        )

    def test_next_run_uses_standard_time_after_dst_transition(self):
        after = datetime(2026, 11, 1, 18, tzinfo=timezone.utc)
        self.assertEqual(
            self.schedule.next_after(after),
            datetime(2026, 11, 3, 13, tzinfo=timezone.utc),
        )

    def test_exact_fire_time_advances_to_the_following_week(self):
        fire_time = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
        self.assertEqual(
            self.schedule.next_after(fire_time),
            datetime(2026, 9, 22, 12, tzinfo=timezone.utc),
        )


class ScheduledTaskRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_definitions_are_registered_without_overwriting_enabled_state(self):
        now = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
        async with self.sessions() as db:
            await sync_task_definitions(db, now)
            task = await db.get(ScheduledTask, "predictions.auto_finalize")
            self.assertEqual(task.schedule, "Tuesday 07:00 America/Chicago")
            self.assertEqual(task.next_run_at, datetime(2026, 9, 15, 12))
            task.enabled = False
            task.description = "old description"
            await db.commit()
            await sync_task_definitions(db, now)
            self.assertFalse(task.enabled)
            self.assertNotEqual(task.description, "old description")

    async def test_task_observability_routes_require_admin_access(self):
        self.assertTrue(task_router.routes)
        for route in task_router.routes:
            dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
            self.assertIn(admin_user, dependency_calls, route.path)

    async def test_claim_uses_a_lease_and_creates_a_run(self):
        due = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
        async with self.sessions() as db:
            await sync_task_definitions(db, due - timedelta(days=1))
            claim = await claim_next_due_task(db, now=due, lease_seconds=60)
            self.assertIsNotNone(claim)
            second = await claim_next_due_task(db, now=due, lease_seconds=60)
            self.assertIsNone(second)
            runs = (await db.scalars(select(ScheduledTaskRun))).all()
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].status, ScheduledTaskRunStatus.running)

    async def test_success_is_audited_and_advances_the_schedule(self):
        due = datetime.now(timezone.utc) - timedelta(minutes=1)
        async with self.sessions() as db:
            await sync_task_definitions(db, due - timedelta(days=1))
            task = await db.get(ScheduledTask, "predictions.auto_finalize")
            task.next_run_at = due
            await db.commit()

        with patch("app.tasks.runner.TASKS_BY_KEY") as registry:
            definition = registry.get.return_value
            definition.key = "predictions.auto_finalize"
            definition.schedule = WeeklySchedule(1, time(7), "America/Chicago")
            definition.handler = AsyncMock(return_value={"status": "skipped", "reason": "nothing due"})
            processed = await run_due_tasks_once(self.sessions)

        self.assertEqual(processed, 1)
        async with self.sessions() as db:
            run = await db.scalar(select(ScheduledTaskRun))
            task = await db.get(ScheduledTask, "predictions.auto_finalize")
            self.assertEqual(run.status, ScheduledTaskRunStatus.skipped)
            self.assertEqual(task.last_status, ScheduledTaskRunStatus.skipped)
            self.assertIsNone(task.locked_until)
            self.assertGreater(task.next_run_at.replace(tzinfo=timezone.utc), due)

    async def test_failure_is_audited_and_scheduled_for_retry(self):
        due = datetime.now(timezone.utc) - timedelta(minutes=1)
        async with self.sessions() as db:
            await sync_task_definitions(db, due - timedelta(days=1))
            task = await db.get(ScheduledTask, "predictions.auto_finalize")
            task.next_run_at = due
            await db.commit()

        with patch("app.tasks.runner.TASKS_BY_KEY") as registry:
            definition = registry.get.return_value
            definition.key = "predictions.auto_finalize"
            definition.schedule = WeeklySchedule(1, time(7), "America/Chicago")
            definition.handler = AsyncMock(side_effect=RuntimeError("Sleeper unavailable"))
            processed = await run_due_tasks_once(self.sessions, retry_minutes=10)

        self.assertEqual(processed, 1)
        async with self.sessions() as db:
            run = await db.scalar(select(ScheduledTaskRun))
            task = await db.get(ScheduledTask, "predictions.auto_finalize")
            self.assertEqual(run.status, ScheduledTaskRunStatus.failed)
            self.assertIn("Sleeper unavailable", run.error)
            self.assertEqual(task.consecutive_failures, 1)
            self.assertIsNone(task.locked_until)
            self.assertGreater(task.next_run_at.replace(tzinfo=timezone.utc), datetime.now(timezone.utc))


class PredictionAutoFinalizeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_due_week_is_refreshed_and_finalized_once(self):
        async with self.sessions() as db:
            season = Season(year=2026, sleeper_league_id="league", is_active=True)
            user = User(username="member", display_name="Member", role=UserRole.user, is_active=True)
            db.add_all([season, user])
            await db.flush()
            week = PredictionWeek(
                season_id=season.id,
                week_number=1,
                lock_at=datetime.now(timezone.utc) - timedelta(days=4),
                status=WeekStatus.open,
            )
            db.add(week)
            await db.flush()
            db.add(
                PredictionMatchup(
                    week_id=week.id,
                    sleeper_matchup_id=1,
                    team_a_roster_id=1,
                    team_b_roster_id=2,
                    team_a_name="A",
                    team_b_name="B",
                    team_a_score=100,
                    team_b_score=90,
                )
            )
            await db.commit()

            with patch(
                "app.features.predictions.scheduled_tasks.refresh_prediction_week",
                new=AsyncMock(return_value=1),
            ) as refresh:
                first = await auto_finalize_prediction_weeks(db)
                await db.commit()
                second = await auto_finalize_prediction_weeks(db)

            self.assertEqual(first["weeks_finalized"], [1])
            self.assertEqual(second["status"], "skipped")
            self.assertEqual(refresh.await_count, 1)
            self.assertEqual(week.status, WeekStatus.final)

    async def test_future_and_inactive_season_weeks_are_not_finalized(self):
        async with self.sessions() as db:
            active = Season(year=2026, sleeper_league_id="active", is_active=True)
            inactive = Season(year=2025, sleeper_league_id="inactive", is_active=False)
            db.add_all([active, inactive])
            await db.flush()
            future = PredictionWeek(
                season_id=active.id,
                week_number=2,
                lock_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
            old = PredictionWeek(
                season_id=inactive.id,
                week_number=1,
                lock_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
            db.add_all([future, old])
            await db.commit()

            result = await auto_finalize_prediction_weeks(db)

            self.assertEqual(result["status"], "skipped")
            self.assertEqual(future.status, WeekStatus.open)
            self.assertEqual(old.status, WeekStatus.open)

    async def test_empty_sleeper_response_does_not_finalize_a_due_week(self):
        async with self.sessions() as db:
            season = Season(year=2026, sleeper_league_id="league", is_active=True)
            db.add(season)
            await db.flush()
            week = PredictionWeek(
                season_id=season.id,
                week_number=1,
                lock_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
            db.add(week)
            await db.commit()

            with patch(
                "app.features.predictions.scheduled_tasks.refresh_prediction_week",
                new=AsyncMock(return_value=0),
            ):
                with self.assertRaisesRegex(RuntimeError, "returned no matchups"):
                    await auto_finalize_prediction_weeks(db)

            self.assertEqual(week.status, WeekStatus.open)


if __name__ == "__main__":
    unittest.main()
