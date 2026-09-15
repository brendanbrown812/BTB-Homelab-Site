import unittest
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.dependencies import current_user
from app.database.base import Base
from app.features.league_history.models import (
    CustomSeasonFact,
    HistorySource,
    LeagueMatchup,
    LeagueTransaction,
    LeagueTransactionDraftPick,
    LeagueTransactionFaab,
    LeagueTransactionParticipant,
    LeagueTransactionPlayer,
    Manager,
    SeasonPlacement,
    SeasonPunishment,
    SeasonTeam,
    WeeklyHighlight,
    WeeklyHighlightSource,
    TransactionMovement,
)
from app.features.league_history.public_routes import (
    public_manager_detail,
    public_overview,
    public_records,
    public_season_detail,
    public_seasons,
    public_teams,
    public_trades,
    public_waivers,
    router,
)
from app.models.season import Season, SeasonPlatform
from app.models.user import User  # noqa: F401 - registers the referenced table
from app.services.sleeper import SleeperPlayer


class FakeRosterService:
    def __init__(self):
        self.calls = []

    async def current_roster(self, league_id, roster_id):
        self.calls.append((league_id, roster_id))
        return (SleeperPlayer("101", "Current Player", "QB", "CHI", None, None, "image"),)

    async def player_lookup(self, player_ids):
        names = {"101": "Alpha Runner", "202": "Beta Receiver", "303": "Gamma Tight End"}
        return {
            player_id: SleeperPlayer(
                player_id, names.get(player_id, f"Player {player_id}"), "RB", "CHI", None, None,
                f"https://images.test/{player_id}.jpg",
            )
            for player_id in player_ids
        }


class LeagueHistoryPublicTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _seed(self, db):
        old = Season(year=2020, platform=SeasonPlatform.espn)
        current = Season(
            year=2025,
            platform=SeasonPlatform.sleeper,
            sleeper_league_id="league-2025",
            is_active=True,
        )
        active = Manager(display_name="Active Manager", biography="Still competing", is_active=True)
        former = Manager(display_name="Pete", biography="Original member", is_active=False)
        db.add_all([old, current, active, former])
        await db.flush()
        db.add_all([
            SeasonTeam(season_id=old.id, manager_id=active.id, team_name="Old Active"),
            SeasonTeam(season_id=old.id, manager_id=former.id, team_name="Pete Classic"),
            SeasonTeam(
                season_id=current.id,
                manager_id=active.id,
                team_name="Active Renamed",
                sleeper_user_id="active-user",
                roster_id=1,
            ),
            SeasonPlacement(season_id=old.id, manager_id=active.id, calculated_placement=2),
            SeasonPlacement(season_id=old.id, manager_id=former.id, calculated_placement=2, override_placement=1),
            SeasonPunishment(season_id=old.id, manager_id=active.id, title="Do the punishment"),
            LeagueMatchup(
                season_id=old.id,
                week=1,
                manager_a_id=active.id,
                manager_b_id=former.id,
                team_a_name="Old Active",
                team_b_name="Pete Classic",
                score_a=110,
                score_b=100,
                source=HistorySource.notion,
                source_key="old-game",
            ),
            LeagueMatchup(
                season_id=current.id,
                week=1,
                manager_a_id=active.id,
                manager_b_id=former.id,
                team_a_name="Active Renamed",
                team_b_name="Pete Classic",
                score_a=90,
                score_b=95,
                source=HistorySource.sleeper,
                source_key="new-game",
            ),
            WeeklyHighlight(
                season_id=old.id,
                week=1,
                category="Top scorer",
                source_key="manual-award",
                manager_id=active.id,
                value=110,
                source=WeeklyHighlightSource.manual,
            ),
            CustomSeasonFact(season_id=old.id, label="Closest game", value="10 points", display_order=0),
        ])
        transaction = LeagueTransaction(
            season_id=current.id,
            external_id="trade-1",
            week=1,
            transaction_type="trade",
            status="complete",
            occurred_at=datetime(2025, 9, 1, tzinfo=timezone.utc),
            raw_payload={},
        )
        db.add(transaction)
        await db.flush()
        db.add(LeagueTransactionParticipant(
            transaction_id=transaction.id,
            manager_id=active.id,
            roster_id=1,
        ))
        await db.commit()
        return old, current, active, former

    async def test_team_summaries_and_profiles_include_career_history(self):
        async with self.sessions() as db:
            _, _, active, former = await self._seed(db)
            listing = await public_teams(db=db)
            self.assertEqual([item["display_name"] for item in listing["managers"]], ["Active Manager", "Pete"])
            active_summary = listing["managers"][0]
            self.assertEqual(active_summary["career"]["wins"], 1)
            self.assertEqual(active_summary["career"]["losses"], 1)
            self.assertEqual(active_summary["career"]["points_for"], 200.0)
            self.assertEqual(active_summary["transaction_total"], 1)
            self.assertEqual(active_summary["punishment_total"], 1)
            self.assertEqual(active_summary["championships"], 0)
            self.assertEqual(active_summary["biggest_losers"], 1)
            self.assertEqual(active_summary["team_names"], ["Old Active", "Active Renamed"])
            self.assertEqual(listing["managers"][1]["championships"], 1)

            sleeper = FakeRosterService()
            detail = await public_manager_detail(active.id, db=db, sleeper=sleeper)  # type: ignore[arg-type]
            self.assertEqual(sleeper.calls, [("league-2025", 1)])
            self.assertEqual(detail["current_roster"]["players"][0]["name"], "Current Player")
            self.assertEqual(detail["transactions"], {"total": 1, "by_type": {"trade": 1}})
            self.assertEqual(detail["punishments"][0]["year"], 2020)
            self.assertEqual(detail["biggest_losers"], 1)

            former_detail = await public_manager_detail(former.id, db=db, sleeper=sleeper)  # type: ignore[arg-type]
            self.assertIsNone(former_detail["current_roster"])
            self.assertEqual(sleeper.calls, [("league-2025", 1)])
            self.assertEqual(former_detail["manager"]["biography"], "Original member")

    async def test_season_list_and_detail_expose_provenance(self):
        async with self.sessions() as db:
            old, _, active, _ = await self._seed(db)
            listing = await public_seasons(db=db)
            self.assertEqual([item["year"] for item in listing["seasons"]], [2025, 2020])
            self.assertEqual(listing["seasons"][1]["sources"], ["notion"])

            detail = await public_season_detail(old.id, db=db)
            champion = detail["placements"][0]
            self.assertEqual((champion["manager_name"], champion["placement"]), ("Pete", 1))
            self.assertEqual(champion["placement_source"], "overridden")
            self.assertEqual(detail["weekly_results"][0]["source"], "notion")
            self.assertIn("manual", {award["source"] for award in detail["awards"]})
            self.assertIn("calculated", {award["source"] for award in detail["awards"]})
            self.assertEqual(detail["facts"][0]["source"], "manual")
            self.assertEqual(detail["punishment"]["manager_id"], active.id)
            self.assertEqual(detail["standings"][1]["wins"], 1)

    async def test_records_api_shapes_ties_and_links_from_history_only(self):
        async with self.sessions() as db:
            await self._seed(db)
            payload = await public_records(db=db)
            by_key = {record["key"]: record for record in payload["records"]}
            self.assertEqual(by_key["highest_weekly_score"]["entries"][0]["year"], 2020)
            self.assertIsNotNone(by_key["highest_weekly_score"]["entries"][0]["season_id"])
            self.assertIsNotNone(by_key["career_wins"]["entries"][0]["manager_id"])
            self.assertEqual(by_key["most_trades"]["entries"][0]["detail"], "1 trades")
            self.assertEqual(payload["custom_facts"][0]["year"], 2020)

    async def test_overview_summarizes_latest_history_and_former_champion(self):
        async with self.sessions() as db:
            _, _, active, former = await self._seed(db)
            payload = await public_overview(db=db, sleeper=FakeRosterService())  # type: ignore[arg-type]
            self.assertEqual(payload["champion"]["manager_id"], former.id)
            self.assertEqual([item["placement"] for item in payload["podium"]], [1, 2])
            self.assertEqual(payload["current_managers"], [{
                "id": active.id, "display_name": "Active Manager", "team_name": "Active Renamed",
            }])
            self.assertEqual(payload["latest_trades"][0]["manager_names"], ["Active Manager"])
            self.assertEqual(payload["latest_waivers"], [])
            self.assertEqual(payload["recent_highlights"][0]["year"], 2025)
            self.assertEqual(payload["punishment"]["title"], "Do the punishment")
            self.assertTrue(payload["headline_records"])

    async def test_manual_season_highlight_replaces_calculated_category(self):
        async with self.sessions() as db:
            old, _, _, former = await self._seed(db)
            db.add(WeeklyHighlight(
                season_id=old.id,
                week=1,
                category="biggest WIN",
                source_key="manual-biggest",
                manager_id=former.id,
                value=99,
                source=WeeklyHighlightSource.manual,
            ))
            await db.commit()
            detail = await public_season_detail(old.id, db=db)
            biggest = [award for award in detail["awards"] if award["category"].casefold() == "biggest win"]
            self.assertEqual(len(biggest), 1)
            self.assertEqual(biggest[0]["manager_id"], former.id)
            self.assertEqual(biggest[0]["source"], "manual")

    async def test_every_public_route_requires_authentication(self):
        self.assertTrue(router.routes)
        for route in router.routes:
            self.assertIn(current_user, {dependency.call for dependency in route.dependant.dependencies})

    async def test_trade_payload_supports_multiple_sides_and_filters(self):
        async with self.sessions() as db:
            _, current, active, former = await self._seed(db)
            third = Manager(display_name="Third Manager", is_active=True)
            db.add(third)
            await db.flush()
            trade = LeagueTransaction(
                season_id=current.id,
                external_id="multi-trade",
                week=4,
                transaction_type="trade",
                status="complete",
                occurred_at=datetime(2025, 9, 20, tzinfo=timezone.utc),
                raw_payload={"type": "trade"},
            )
            failed_trade = LeagueTransaction(
                season_id=current.id,
                external_id="failed-trade",
                week=4,
                transaction_type="trade",
                status="failed",
                occurred_at=datetime(2025, 9, 19, tzinfo=timezone.utc),
                raw_payload={"type": "trade"},
            )
            db.add_all([trade, failed_trade])
            await db.flush()
            db.add_all([
                LeagueTransactionParticipant(transaction_id=trade.id, manager_id=active.id, roster_id=1),
                LeagueTransactionParticipant(transaction_id=trade.id, manager_id=former.id, roster_id=2),
                LeagueTransactionParticipant(transaction_id=trade.id, manager_id=third.id, roster_id=3),
                LeagueTransactionPlayer(transaction_id=trade.id, manager_id=active.id, roster_id=1, player_id="101", player_name="Old Alpha", movement=TransactionMovement.add),
                LeagueTransactionPlayer(transaction_id=trade.id, manager_id=former.id, roster_id=2, player_id="202", player_name="Beta Receiver", movement=TransactionMovement.drop),
                LeagueTransactionPlayer(transaction_id=trade.id, manager_id=third.id, roster_id=3, player_id="303", player_name="Gamma Tight End", movement=TransactionMovement.add),
                LeagueTransactionDraftPick(transaction_id=trade.id, pick_season=2026, round=2, original_roster_id=2, previous_owner_roster_id=2, new_owner_roster_id=1),
                LeagueTransactionFaab(transaction_id=trade.id, sender_roster_id=3, receiver_roster_id=1, amount=12),
                LeagueTransactionParticipant(transaction_id=failed_trade.id, manager_id=active.id, roster_id=1),
                LeagueTransactionParticipant(transaction_id=failed_trade.id, manager_id=former.id, roster_id=2),
            ])
            await db.commit()

            service = FakeRosterService()
            result = await public_trades(
                season=2025, manager_id=third.id, player="gamma", db=db, sleeper=service  # type: ignore[arg-type]
            )
            self.assertEqual(len(result["items"]), 1)
            item = result["items"][0]
            self.assertEqual(len(item["participants"]), 3)
            self.assertEqual(item["sides"][0]["draft_picks_received"][0]["round"], 2)
            self.assertEqual(item["sides"][0]["faab_received"], 12)
            gamma = next(player for player in item["adds"] if player["player_id"] == "303")
            self.assertEqual(gamma["name"], "Gamma Tight End")
            self.assertEqual(gamma["image_url"], "https://images.test/303.jpg")

            completed = await public_trades(
                season=2025, manager_id=None, player=None, status="complete", db=db, sleeper=service  # type: ignore[arg-type]
            )
            self.assertIn("multi-trade", {row["external_id"] for row in completed["items"]})
            self.assertNotIn("failed-trade", {row["external_id"] for row in completed["items"]})
            self.assertTrue(all(row["status"] == "complete" for row in completed["items"]))

            no_match = await public_trades(
                season=2020, manager_id=None, player=None, db=db, sleeper=service  # type: ignore[arg-type]
            )
            self.assertEqual(no_match["items"], [])
            self.assertIn(2020, no_match["options"]["seasons"])

    async def test_waiver_payload_and_type_status_player_filters(self):
        async with self.sessions() as db:
            _, current, active, _ = await self._seed(db)
            waiver = LeagueTransaction(
                season_id=current.id, external_id="waiver-1", week=3, transaction_type="waiver",
                status="complete", occurred_at=datetime(2025, 9, 15, tzinfo=timezone.utc), raw_payload={},
            )
            failed = LeagueTransaction(
                season_id=current.id, external_id="waiver-failed", week=3, transaction_type="waiver",
                status="failed", occurred_at=datetime(2025, 9, 14, tzinfo=timezone.utc), raw_payload={},
            )
            free_agent = LeagueTransaction(
                season_id=current.id, external_id="free-1", week=2, transaction_type="free_agent",
                status="complete", occurred_at=datetime(2025, 9, 10, tzinfo=timezone.utc), raw_payload={},
            )
            db.add_all([waiver, failed, free_agent])
            await db.flush()
            db.add_all([
                LeagueTransactionParticipant(transaction_id=waiver.id, manager_id=active.id, roster_id=1),
                LeagueTransactionPlayer(transaction_id=waiver.id, manager_id=active.id, roster_id=1, player_id="101", player_name="Alpha Runner", movement=TransactionMovement.add),
                LeagueTransactionPlayer(transaction_id=waiver.id, manager_id=active.id, roster_id=1, player_id="202", player_name="Beta Receiver", movement=TransactionMovement.drop),
                LeagueTransactionFaab(transaction_id=waiver.id, sender_roster_id=1, receiver_roster_id=0, amount=0),
                LeagueTransactionParticipant(transaction_id=failed.id, manager_id=active.id, roster_id=1),
                LeagueTransactionParticipant(transaction_id=free_agent.id, manager_id=active.id, roster_id=1),
                LeagueTransactionPlayer(transaction_id=free_agent.id, manager_id=active.id, roster_id=1, player_id="303", player_name="Gamma Tight End", movement=TransactionMovement.add),
            ])
            await db.commit()

            service = FakeRosterService()
            failed_result = await public_waivers(
                season=2025, manager_id=active.id, player=None, transaction_type="waiver", status="failed",
                db=db, sleeper=service,  # type: ignore[arg-type]
            )
            self.assertEqual([item["external_id"] for item in failed_result["items"]], ["waiver-failed"])

            free_result = await public_waivers(
                season=None, manager_id=None, player="gamma", transaction_type="free_agent", status="complete",
                db=db, sleeper=service,  # type: ignore[arg-type]
            )
            self.assertEqual(free_result["items"][0]["transaction_type"], "free_agent")

            zero_bid = await public_waivers(
                season=None, manager_id=None, player="alpha", transaction_type="waiver", status="complete",
                db=db, sleeper=service,  # type: ignore[arg-type]
            )
            self.assertEqual(zero_bid["items"][0]["bid_amount"], 0)
            self.assertEqual(zero_bid["items"][0]["drops"][0]["name"], "Beta Receiver")


if __name__ == "__main__":
    unittest.main()
