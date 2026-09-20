import unittest
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.features.predictions.models import PickResult, Prediction, PredictionMatchup, PredictionWeek, WeekStatus
from app.features.predictions.routes import season_weeks, week_results
from app.models.season import Season
from app.models.user import User


class PredictionResultsTests(unittest.IsolatedAsyncioTestCase):
    async def test_saved_weeks_results_and_pick_privacy(self):
        engine = create_async_engine("sqlite+aiosqlite://")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                season = Season(year=2026, sleeper_league_id="league", is_active=True)
                other_season = Season(year=2025, sleeper_league_id="old", is_active=False)
                user = User(username="one", display_name="One")
                other = User(username="two", display_name="Two")
                db.add_all([season, other_season, user, other])
                await db.flush()
                now = datetime.now(timezone.utc)
                previous = PredictionWeek(season_id=season.id, week_number=1, status=WeekStatus.final, lock_at=now - timedelta(days=7))
                current = PredictionWeek(season_id=season.id, week_number=2, status=WeekStatus.open, lock_at=now + timedelta(days=7))
                unrelated = PredictionWeek(season_id=other_season.id, week_number=3, lock_at=now)
                db.add_all([previous, current, unrelated])
                await db.flush()
                for week in [previous, current]:
                    matchup = PredictionMatchup(week_id=week.id, sleeper_matchup_id=1, team_a_roster_id=1, team_b_roster_id=2, team_a_name="A", team_b_name="B", team_a_score=110.5, team_b_score=90.0, winner_roster_id=1)
                    db.add(matchup)
                    await db.flush()
                    db.add_all([Prediction(user_id=person.id, matchup_id=matchup.id, selected_roster_id=1,
                                           result=PickResult.win if week.status == WeekStatus.final else None)
                                for person in [user, other]])
                await db.commit()

                options = await season_weeks(season.id, user, db)
                self.assertEqual([row["id"] for row in options], [current.id, previous.id])
                historical = await week_results(previous.id, user, db)
                self.assertEqual(historical["season"]["id"], season.id)
                self.assertEqual(historical["week"]["number"], 1)
                self.assertEqual(historical["week"]["status"], "final")
                self.assertEqual(historical["matchups"][0]["team_a"]["score"], 110.5)
                self.assertEqual(historical["matchups"][0]["winner_roster_id"], 1)
                self.assertEqual(len(historical["picks"]), 2)
                self.assertTrue(all(pick["result"] == "win" for pick in historical["picks"]))
                private = await week_results(current.id, user, db)
                self.assertFalse(private["week"]["picks_public"])
                self.assertEqual([pick["user_id"] for pick in private["picks"]], [user.id])
                self.assertIsNone(private["picks"][0]["result"])
                empty = await week_results(unrelated.id, user, db)
                self.assertEqual(empty["matchups"], [])
                self.assertEqual(empty["picks"], [])
                with self.assertRaises(HTTPException) as error:
                    await week_results(uuid.uuid4(), user, db)
                self.assertEqual(error.exception.status_code, 404)
        finally:
            await engine.dispose()
