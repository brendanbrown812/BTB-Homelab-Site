import unittest
from datetime import datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.features.league_history.models import (
    CustomSeasonFact,
    HistorySource,
    ImportRun,
    ImportRunStatus,
    LeagueMatchup,
    LeagueTransaction,
    LeagueTransactionDraftPick,
    LeagueTransactionFaab,
    LeagueTransactionParticipant,
    LeagueTransactionPlayer,
    Manager,
    ManagerAlias,
    ManagerAliasProvider,
    SeasonPlacement,
    SeasonPunishment,
    SeasonTeam,
    TransactionMovement,
    WeeklyHighlight,
    WeeklyHighlightSource,
)
from app.models.season import Season, SeasonPlatform
from app.models.user import User, UserRole
from app.main import _ensure_local_schema_columns


class LeagueHistoryModelTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _core_records(self, db):
        user = User(username="current", display_name="Current Manager", role=UserRole.user, is_active=True)
        db.add(user)
        await db.flush()
        current = Manager(user_id=user.id, display_name="Current Manager")
        former = Manager(display_name="Former Manager", is_active=False)
        season = Season(year=2024, platform=SeasonPlatform.sleeper, sleeper_league_id="league-2024")
        db.add_all([current, former, season])
        await db.flush()
        return user, current, former, season

    async def test_all_league_history_tables_are_registered(self):
        expected = {
            "league_managers",
            "league_manager_aliases",
            "league_season_teams",
            "league_matchups",
            "league_transactions",
            "league_transaction_participants",
            "league_transaction_players",
            "league_transaction_draft_picks",
            "league_transaction_faab",
            "league_season_placements",
            "league_season_punishments",
            "league_weekly_highlights",
            "league_custom_season_facts",
            "league_import_runs",
        }
        self.assertTrue(expected.issubset(Base.metadata.tables))

    async def test_espn_season_can_omit_league_id_but_sleeper_cannot(self):
        async with self.sessions() as db:
            db.add(Season(year=2020, platform=SeasonPlatform.espn, sleeper_league_id=None))
            await db.commit()

        async with self.sessions() as db:
            db.add(Season(year=2021, platform=SeasonPlatform.sleeper, sleeper_league_id=None))
            with self.assertRaises(IntegrityError):
                await db.commit()

    async def test_manager_accounts_and_aliases_are_unique(self):
        async with self.sessions() as db:
            user, current, former, _ = await self._core_records(db)
            db.add_all([
                ManagerAlias(manager_id=current.id, provider=ManagerAliasProvider.sleeper_user_id, external_value="sleeper-1"),
                ManagerAlias(manager_id=former.id, provider=ManagerAliasProvider.notion_name, external_value="Pete"),
            ])
            await db.commit()

            db.add(Manager(user_id=user.id, display_name="Duplicate Link"))
            with self.assertRaises(IntegrityError):
                await db.commit()

        async with self.sessions() as db:
            managers = [Manager(display_name="One"), Manager(display_name="Two")]
            db.add_all(managers)
            await db.flush()
            db.add_all([
                ManagerAlias(manager_id=managers[0].id, provider=ManagerAliasProvider.notion_name, external_value="Tim"),
                ManagerAlias(manager_id=managers[1].id, provider=ManagerAliasProvider.notion_name, external_value="Tim"),
            ])
            with self.assertRaises(IntegrityError):
                await db.commit()

    async def test_season_identity_and_import_keys_prevent_duplicates(self):
        async with self.sessions() as db:
            _, current, former, season = await self._core_records(db)
            db.add_all([
                SeasonTeam(season_id=season.id, manager_id=current.id, team_name="Current Team", sleeper_user_id="s1", roster_id=1),
                SeasonTeam(season_id=season.id, manager_id=former.id, team_name="Former Team", sleeper_user_id="s2", roster_id=2),
                LeagueMatchup(
                    season_id=season.id,
                    week=1,
                    manager_a_id=current.id,
                    manager_b_id=former.id,
                    team_a_name="Current Team",
                    team_b_name="Former Team",
                    score_a=101.2,
                    score_b=99.8,
                    sleeper_matchup_id=1,
                    source=HistorySource.sleeper,
                    source_key="week-1-matchup-1",
                ),
            ])
            await db.commit()

            db.add(LeagueMatchup(
                season_id=season.id,
                week=1,
                manager_a_id=current.id,
                manager_b_id=former.id,
                team_a_name="Renamed Team",
                team_b_name="Former Team",
                source=HistorySource.sleeper,
                source_key="week-1-matchup-1",
            ))
            with self.assertRaises(IntegrityError):
                await db.commit()

    async def test_transaction_models_retain_normalized_and_raw_data(self):
        async with self.sessions() as db:
            _, current, former, season = await self._core_records(db)
            transaction = LeagueTransaction(
                season_id=season.id,
                external_id="transaction-1",
                week=4,
                transaction_type="trade",
                status="complete",
                occurred_at=datetime(2024, 10, 1, tzinfo=timezone.utc),
                raw_payload={"adds": {"player-1": 1}, "waiver_budget": [{"amount": 5}]},
            )
            db.add(transaction)
            await db.flush()
            db.add_all([
                LeagueTransactionParticipant(transaction_id=transaction.id, manager_id=current.id, roster_id=1),
                LeagueTransactionParticipant(transaction_id=transaction.id, manager_id=former.id, roster_id=2),
                LeagueTransactionPlayer(
                    transaction_id=transaction.id,
                    manager_id=current.id,
                    roster_id=1,
                    player_id="player-1",
                    movement=TransactionMovement.add,
                ),
                LeagueTransactionDraftPick(
                    transaction_id=transaction.id,
                    pick_season=2025,
                    round=2,
                    original_roster_id=2,
                    previous_owner_roster_id=2,
                    new_owner_roster_id=1,
                ),
                LeagueTransactionFaab(
                    transaction_id=transaction.id,
                    sender_roster_id=1,
                    receiver_roster_id=2,
                    amount=5,
                ),
            ])
            await db.commit()
            self.assertEqual(transaction.raw_payload["waiver_budget"][0]["amount"], 5)

            db.add(LeagueTransaction(
                season_id=season.id,
                external_id="transaction-1",
                week=4,
                transaction_type="trade",
                status="complete",
                occurred_at=datetime.now(timezone.utc),
                raw_payload={},
            ))
            with self.assertRaises(IntegrityError):
                await db.commit()

    async def test_season_annotations_have_one_stable_slot(self):
        async with self.sessions() as db:
            _, current, _, season = await self._core_records(db)
            db.add_all([
                SeasonPlacement(
                    season_id=season.id,
                    manager_id=current.id,
                    calculated_placement=None,
                    override_placement=1,
                ),
                SeasonPunishment(season_id=season.id, manager_id=current.id, title="Do the punishment"),
                WeeklyHighlight(
                    season_id=season.id,
                    week=3,
                    category="highest_team_score",
                    source_key=f"manager:{current.id}",
                    manager_id=current.id,
                    value=177.4,
                    source=WeeklyHighlightSource.calculated,
                ),
                CustomSeasonFact(season_id=season.id, label="Odd stat", value="Something happened", display_order=0),
                ImportRun(
                    season_id=season.id,
                    source=HistorySource.sleeper,
                    status=ImportRunStatus.succeeded,
                    counts={"matchups": 72, "transactions": 18},
                ),
            ])
            await db.commit()

            db.add(SeasonPlacement(season_id=season.id, manager_id=current.id, calculated_placement=3))
            with self.assertRaises(IntegrityError):
                await db.commit()
class LocalSeasonSchemaUpgradeTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_sqlite_seasons_are_rebuilt_without_losing_references(self):
        engine = create_async_engine("sqlite+aiosqlite://")
        try:
            async with engine.connect() as connection:
                await connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
                await connection.commit()
                async with connection.begin():
                    await connection.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY)"))
                    await connection.execute(text("""
                        CREATE TABLE seasons (
                            id CHAR(32) NOT NULL PRIMARY KEY,
                            year INTEGER NOT NULL UNIQUE,
                            sleeper_league_id VARCHAR(80) NOT NULL UNIQUE,
                            is_active BOOLEAN NOT NULL
                        )
                    """))
                    await connection.execute(text("""
                        CREATE TABLE season_refs (
                            id INTEGER PRIMARY KEY,
                            season_id CHAR(32) NOT NULL REFERENCES seasons(id) ON DELETE CASCADE
                        )
                    """))
                    await connection.execute(text("""
                        INSERT INTO seasons (id, year, sleeper_league_id, is_active)
                        VALUES ('season-one', 2024, 'league-2024', 1)
                    """))
                    await connection.execute(text("INSERT INTO season_refs (id, season_id) VALUES (1, 'season-one')"))
                    await connection.run_sync(_ensure_local_schema_columns)
                await connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                await connection.commit()

                columns = await connection.run_sync(lambda sync_connection: {
                    column["name"]: column for column in inspect(sync_connection).get_columns("seasons")
                })
                self.assertIn("platform", columns)
                self.assertTrue(columns["sleeper_league_id"]["nullable"])
                self.assertEqual(
                    (await connection.execute(text("SELECT platform FROM seasons WHERE year = 2024"))).scalar_one(),
                    "sleeper",
                )
                self.assertEqual(
                    (await connection.execute(text("SELECT season_id FROM season_refs WHERE id = 1"))).scalar_one(),
                    "season-one",
                )
                await connection.execute(text("""
                    INSERT INTO seasons (id, year, platform, sleeper_league_id, is_active)
                    VALUES ('season-two', 2020, 'espn', NULL, 0)
                """))
                await connection.commit()
        finally:
            await engine.dispose()


if __name__ == "__main__":
    unittest.main()
