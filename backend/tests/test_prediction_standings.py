import unittest
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.features.predictions.models import (
    PickResult,
    Prediction,
    PredictionMatchup,
    PredictionWeek,
    WeekStatus,
)
from app.features.predictions.routes import prediction_history, season_standings
from app.models.season import Season
from app.models.user import User, UserRole


class PredictionStandingsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_only_includes_non_admin_users_who_have_participated(self):
        async with self.sessions() as db:
            season = Season(year=2026, sleeper_league_id="league", is_active=True)
            admin = User(
                username="admin",
                display_name="Admin",
                role=UserRole.admin,
                is_active=True,
            )
            member = User(
                username="member",
                display_name="Member",
                role=UserRole.user,
                is_active=True,
            )
            nonparticipant = User(
                username="nonparticipant",
                display_name="Nonparticipant",
                role=UserRole.user,
                is_active=True,
            )
            db.add_all([season, admin, member, nonparticipant])
            await db.flush()

            week = PredictionWeek(
                season_id=season.id,
                week_number=1,
                lock_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
                status=WeekStatus.final,
            )
            db.add(week)
            await db.flush()

            matchup = PredictionMatchup(
                week_id=week.id,
                sleeper_matchup_id=1,
                team_a_roster_id=1,
                team_b_roster_id=2,
                team_a_name="A",
                team_b_name="B",
            )
            db.add(matchup)
            await db.flush()
            db.add_all(
                [
                    Prediction(
                        user_id=admin.id,
                        matchup_id=matchup.id,
                        selected_roster_id=1,
                        result=PickResult.win,
                    ),
                    Prediction(
                        user_id=member.id,
                        matchup_id=matchup.id,
                        selected_roster_id=2,
                        result=PickResult.loss,
                    ),
                    Prediction(
                        user_id=nonparticipant.id,
                        matchup_id=matchup.id,
                        selected_roster_id=None,
                        result=PickResult.loss,
                    ),
                ]
            )
            await db.commit()

            result = await season_standings(season.id, member, db)

        self.assertEqual(
            result,
            [
                {
                    "user_id": member.id,
                    "display_name": "Member",
                    "wins": 0,
                    "losses": 1,
                    "pushes": 0,
                }
            ],
        )

    async def test_participant_remains_visible_after_missing_a_later_week(self):
        async with self.sessions() as db:
            season = Season(year=2026, sleeper_league_id="league", is_active=True)
            member = User(
                username="member",
                display_name="Member",
                role=UserRole.user,
                is_active=True,
            )
            db.add_all([season, member])
            await db.flush()

            weeks = [
                PredictionWeek(
                    season_id=season.id,
                    week_number=number,
                    lock_at=datetime(2026, 9, 10 + number, tzinfo=timezone.utc),
                    status=WeekStatus.final,
                )
                for number in (1, 2)
            ]
            db.add_all(weeks)
            await db.flush()
            matchups = [
                PredictionMatchup(
                    week_id=week.id,
                    sleeper_matchup_id=1,
                    team_a_roster_id=1,
                    team_b_roster_id=2,
                    team_a_name="A",
                    team_b_name="B",
                )
                for week in weeks
            ]
            db.add_all(matchups)
            await db.flush()
            db.add_all(
                [
                    Prediction(
                        user_id=member.id,
                        matchup_id=matchups[0].id,
                        selected_roster_id=1,
                        result=PickResult.win,
                    ),
                    Prediction(
                        user_id=member.id,
                        matchup_id=matchups[1].id,
                        selected_roster_id=None,
                        result=PickResult.loss,
                    ),
                ]
            )
            await db.commit()

            result = await season_standings(season.id, member, db)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["display_name"], "Member")
        self.assertEqual((result[0]["wins"], result[0]["losses"]), (1, 1))

    async def test_history_counts_only_members_who_participated_that_week(self):
        async with self.sessions() as db:
            season = Season(year=2026, sleeper_league_id="league", is_active=True)
            admin = User(
                username="admin",
                display_name="Admin",
                role=UserRole.admin,
                is_active=True,
            )
            participant = User(
                username="participant",
                display_name="Participant",
                role=UserRole.user,
                is_active=True,
            )
            nonparticipant = User(
                username="nonparticipant",
                display_name="Nonparticipant",
                role=UserRole.user,
                is_active=True,
            )
            db.add_all([season, admin, participant, nonparticipant])
            await db.flush()

            week = PredictionWeek(
                season_id=season.id,
                week_number=1,
                lock_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
                status=WeekStatus.final,
                finalized_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
            )
            db.add(week)
            await db.flush()
            matchups = [
                PredictionMatchup(
                    week_id=week.id,
                    sleeper_matchup_id=number,
                    team_a_roster_id=number * 2 - 1,
                    team_b_roster_id=number * 2,
                    team_a_name="A",
                    team_b_name="B",
                )
                for number in (1, 2)
            ]
            db.add_all(matchups)
            await db.flush()
            for user, selections, results in (
                (admin, (1, 3), (PickResult.win, PickResult.win)),
                (participant, (1, None), (PickResult.win, PickResult.loss)),
                (nonparticipant, (None, None), (PickResult.loss, PickResult.loss)),
            ):
                db.add_all(
                    Prediction(
                        user_id=user.id,
                        matchup_id=matchup.id,
                        selected_roster_id=selection,
                        result=result,
                    )
                    for matchup, selection, result in zip(matchups, selections, results)
                )
            await db.commit()

            result = await prediction_history(season.id, participant, db)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["champions"], ["Participant"])
        self.assertEqual(
            result[0]["records"],
            [
                {
                    "name": "Participant",
                    "wins": 1,
                    "losses": 1,
                    "pushes": 0,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
