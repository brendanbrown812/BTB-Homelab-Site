import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.features.predictions.admin_routes import current_submission_status
from app.features.predictions.models import Prediction, PredictionMatchup, PredictionWeek
from app.models.season import Season
from app.models.user import User, UserRole


class SubmissionStatusTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_returns_only_current_week_counts_for_other_active_users(self):
        async with self.session_factory() as db:
            season = Season(year=2026, sleeper_league_id="league", is_active=True)
            admin = User(username="admin", display_name="Admin", role=UserRole.admin, is_active=True)
            alice = User(username="alice", display_name="Alice", role=UserRole.user, is_active=True)
            bob = User(username="bob", display_name="Bob", role=UserRole.user, is_active=True)
            inactive = User(username="inactive", display_name="Inactive", role=UserRole.user, is_active=False)
            db.add_all([season, admin, alice, bob, inactive])
            await db.flush()

            week = PredictionWeek(season_id=season.id, week_number=3, lock_at=datetime(2026, 9, 17, tzinfo=timezone.utc))
            db.add(week)
            await db.flush()
            matchups = [
                PredictionMatchup(week_id=week.id, sleeper_matchup_id=index, team_a_roster_id=index * 2 - 1, team_b_roster_id=index * 2, team_a_name="A", team_b_name="B")
                for index in (1, 2)
            ]
            db.add_all(matchups)
            await db.flush()
            db.add_all([
                Prediction(user_id=alice.id, matchup_id=matchups[0].id, selected_roster_id=1),
                Prediction(user_id=alice.id, matchup_id=matchups[1].id, selected_roster_id=None),
                Prediction(user_id=bob.id, matchup_id=matchups[0].id, selected_roster_id=1),
                Prediction(user_id=bob.id, matchup_id=matchups[1].id, selected_roster_id=4),
            ])
            await db.commit()

            with patch(
                "app.features.predictions.admin_routes._sync_current",
                new=AsyncMock(return_value=(season, week, [])),
            ):
                result = await current_submission_status(admin=admin, db=db)

        self.assertEqual(result["total_matchups"], 2)
        self.assertEqual(
            [(user["display_name"], user["submitted_picks"]) for user in result["users"]],
            [("Alice", 1), ("Bob", 2)],
        )
        self.assertEqual(set(result["users"][0]), {"user_id", "display_name", "submitted_picks"})


if __name__ == "__main__":
    unittest.main()
