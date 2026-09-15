import unittest

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.features.league_history.models import (
    CustomSeasonFact,
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
    SeasonTeam,
    WeeklyHighlight,
    WeeklyHighlightSource,
)
from app.features.league_history.sleeper_importer import _placements, import_sleeper_season
from app.models.season import Season, SeasonPlatform
from app.models.user import User  # noqa: F401 - registers the referenced table
from app.services.sleeper import SleeperLeagueArchive, SleeperPlayer


def archive(*, renamed: bool = False, incomplete: bool = False) -> SleeperLeagueArchive:
    users = tuple(
        {"user_id": f"u{number}", "display_name": f"Manager {number}", "metadata": {"team_name": (
            "Renamed Franchise" if renamed and number == 1 else f"Team {number}"
        )}}
        for number in range(1, 5)
    )
    rosters = tuple({"roster_id": number, "owner_id": f"u{number}"} for number in range(1, 5))
    transactions = (
        {
            "transaction_id": "trade-1", "type": "trade", "status": "complete", "leg": 1, "created": 1700000000000,
            "roster_ids": [1, 2, 3], "adds": {"p1": 2, "p2": 3}, "drops": {"p3": 1},
            "draft_picks": [{"season": "2025", "round": 2, "roster_id": 1, "previous_owner_id": 1, "owner_id": 2}],
            "waiver_budget": [{"sender": 3, "receiver": 1, "amount": 7}],
        },
        {
            "transaction_id": "waiver-1", "type": "waiver", "status": "complete", "leg": 1, "created": 1700000001000,
            "roster_ids": [4], "adds": {"p4": 4}, "drops": {"p5": 4}, "settings": {"waiver_bid": 13},
        },
        {"transaction_id": "free-1", "type": "free_agent", "status": "complete", "leg": 1, "created": 1700000002000, "roster_ids": [1], "adds": {"p6": 1}},
        {"transaction_id": "failed-1", "type": "waiver", "status": "failed", "leg": 1, "created": 1700000003000, "roster_ids": [2], "adds": {"p7": 2}},
        {"transaction_id": "pending-1", "type": "trade", "status": "pending", "leg": 1, "created": 1700000004000, "roster_ids": [3, 4]},
    )
    winners = (
        ({"r": 2, "m": 1, "p": 1, "w": None, "l": None} if incomplete else {"r": 2, "m": 1, "p": 1, "w": 1, "l": 2}),
        {"r": 2, "m": 2, "p": 3, "w": 3, "l": 4},
    )
    return SleeperLeagueArchive(
        league={"league_id": "league-2024", "season": "2024"}, users=users, rosters=rosters,
        matchups_by_week={1: (
            {"matchup_id": 1, "roster_id": 1, "points": 111.5, "starters": ["p1"]},
            {"matchup_id": 1, "roster_id": 2, "points": 99.0, "starters": ["p2"]},
            {"matchup_id": 2, "roster_id": 3, "points": 88.0},
            {"matchup_id": 2, "roster_id": 4, "points": 87.5},
        )},
        transactions_by_round={1: transactions}, winners_bracket=winners, losers_bracket=(),
    )


class FakeSleeperService:
    def __init__(self, value: SleeperLeagueArchive):
        self.value = value

    async def league_archive(self, league_id: str):
        assert league_id == "league-2024"
        return self.value

    async def player_lookup(self, player_ids: set[str]):
        return {
            player_id: SleeperPlayer(player_id, f"Name {player_id}", "RB", None, None, None, None)
            for player_id in player_ids
        }


class SleeperImporterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _seed(self, db, *, missing_alias: bool = False):
        season = Season(year=2024, platform=SeasonPlatform.sleeper, sleeper_league_id="league-2024")
        managers = [Manager(display_name=f"Manager {number}", is_active=number != 4) for number in range(1, 5)]
        db.add_all([season, *managers])
        await db.flush()
        db.add_all([
            ManagerAlias(manager_id=manager.id, provider=ManagerAliasProvider.sleeper_user_id, external_value=f"u{number}")
            for number, manager in enumerate(managers, 1)
            if not (missing_alias and number == 4)
        ])
        await db.commit()
        return season, managers

    async def test_import_is_idempotent_updates_renamed_team_and_preserves_override(self):
        async with self.sessions() as db:
            season, managers = await self._seed(db)
            db.add_all([
                SeasonPlacement(season_id=season.id, manager_id=managers[0].id, override_placement=4),
                CustomSeasonFact(season_id=season.id, label="Manual correction", value="Keep me", display_order=0),
                WeeklyHighlight(
                    season_id=season.id, week=1, category="Commissioner award",
                    source_key="manual:keep", manager_id=managers[0].id,
                    source=WeeklyHighlightSource.manual,
                ),
            ])
            await db.commit()

            first = await import_sleeper_season(db, season.id, sleeper=FakeSleeperService(archive()))
            second = await import_sleeper_season(db, season.id, sleeper=FakeSleeperService(archive(renamed=True)))

            self.assertEqual(first["status"], "succeeded")
            self.assertEqual(second["status"], "succeeded")
            for model, expected in (
                (SeasonTeam, 4), (LeagueMatchup, 2), (LeagueTransaction, 5),
                (LeagueTransactionParticipant, 8), (LeagueTransactionPlayer, 7),
                (LeagueTransactionDraftPick, 1), (LeagueTransactionFaab, 2), (SeasonPlacement, 4),
            ):
                self.assertEqual(await db.scalar(select(func.count()).select_from(model)), expected)
            team = await db.scalar(select(SeasonTeam).where(SeasonTeam.roster_id == 1))
            self.assertEqual(team.team_name, "Renamed Franchise")
            matchup = await db.scalar(select(LeagueMatchup).where(LeagueMatchup.sleeper_matchup_id == 1))
            self.assertEqual(matchup.team_a_name, "Renamed Franchise")
            placement = await db.scalar(select(SeasonPlacement).where(SeasonPlacement.manager_id == managers[0].id))
            self.assertEqual((placement.calculated_placement, placement.override_placement), (1, 4))
            player = await db.scalar(select(LeagueTransactionPlayer).where(LeagueTransactionPlayer.player_id == "p4"))
            self.assertEqual(player.player_name, "Name p4")
            transaction = await db.scalar(select(LeagueTransaction).where(LeagueTransaction.external_id == "trade-1"))
            self.assertEqual(transaction.raw_payload["waiver_budget"][0]["amount"], 7)
            statuses = set((await db.scalars(select(LeagueTransaction.status))).all())
            self.assertEqual(statuses, {"complete", "failed", "pending"})
            former_team = await db.scalar(select(SeasonTeam).where(SeasonTeam.manager_id == managers[3].id))
            self.assertEqual(former_team.sleeper_user_id, "u4")
            self.assertEqual(await db.scalar(select(func.count()).select_from(ImportRun)), 2)
            self.assertEqual(await db.scalar(select(func.count()).select_from(Manager)), 4)
            self.assertEqual((await db.scalar(select(CustomSeasonFact))).value, "Keep me")
            self.assertEqual((await db.scalar(select(WeeklyHighlight))).source, WeeklyHighlightSource.manual)

    async def test_dry_run_records_attempt_without_writes(self):
        async with self.sessions() as db:
            season, _ = await self._seed(db)
            result = await import_sleeper_season(db, season.id, dry_run=True, sleeper=FakeSleeperService(archive()))
            self.assertEqual(result["counts"]["transactions"], 5)
            self.assertEqual(await db.scalar(select(func.count()).select_from(SeasonTeam)), 0)
            run = await db.get(ImportRun, result["run_id"])
            self.assertEqual(run.status, ImportRunStatus.succeeded)
            self.assertEqual(run.counts["mode"], "dry_run")

    async def test_unresolved_identity_marks_attention_and_aborts_season(self):
        async with self.sessions() as db:
            season, _ = await self._seed(db, missing_alias=True)
            result = await import_sleeper_season(db, season.id, sleeper=FakeSleeperService(archive()))
            self.assertEqual(result["status"], "needs_attention")
            self.assertEqual(result["counts"]["unresolved_identities"][0]["sleeper_user_id"], "u4")
            self.assertEqual(await db.scalar(select(func.count()).select_from(SeasonTeam)), 0)
            self.assertEqual(await db.scalar(select(func.count()).select_from(LeagueTransaction)), 0)

    async def test_incomplete_bracket_only_updates_completed_placement_games(self):
        async with self.sessions() as db:
            season, managers = await self._seed(db)
            await import_sleeper_season(db, season.id, sleeper=FakeSleeperService(archive(incomplete=True)))
            placements = (await db.scalars(select(SeasonPlacement))).all()
            self.assertEqual({item.manager_id: item.calculated_placement for item in placements}, {
                managers[2].id: 3, managers[3].id: 4,
            })
            run = await db.scalar(select(ImportRun))
            self.assertFalse(run.counts["placement_complete"])

    async def test_completed_season_with_no_matchups_needs_attention(self):
        async with self.sessions() as db:
            season, _ = await self._seed(db)
            value = archive()
            empty = SleeperLeagueArchive(
                league={**value.league, "status": "complete"},
                users=value.users,
                rosters=value.rosters,
                matchups_by_week={},
                transactions_by_round=value.transactions_by_round,
                winners_bracket=value.winners_bracket,
                losers_bracket=value.losers_bracket,
            )

            result = await import_sleeper_season(db, season.id, sleeper=FakeSleeperService(empty))

            self.assertEqual(result["status"], "needs_attention")
            self.assertEqual(await db.scalar(select(func.count()).select_from(SeasonTeam)), 0)
            run = await db.get(ImportRun, result["run_id"])
            self.assertIn("no paired matchups", run.error_details)

    def test_toilet_bowl_places_are_reversed_into_overall_league_places(self):
        placements = _placements(
            ({"p": 1, "w": 1, "l": 2}, {"p": 3, "w": 3, "l": 4}),
            (
                {"t1": 7, "t2": 8, "w": 7, "l": 8},
                {"t1": 9, "t2": 10, "w": 9, "l": 10},
                {"t1": 11, "t2": 12, "w": 11, "l": 12},
                {"p": 1, "w": 7, "l": 8},
                {"p": 3, "w": 9, "l": 10},
                {"p": 5, "w": 11, "l": 12},
            ),
            total_rosters=12,
        )

        self.assertEqual(placements[1], 1)
        self.assertEqual(placements[2], 2)
        self.assertEqual(placements[7], 12)
        self.assertEqual(placements[8], 11)
        self.assertEqual(placements[9], 10)
        self.assertEqual(placements[10], 9)


if __name__ == "__main__":
    unittest.main()
