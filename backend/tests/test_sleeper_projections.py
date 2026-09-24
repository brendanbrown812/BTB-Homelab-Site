import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.features.predictions.models import WeekStatus
from app.features.predictions import routes
from app.services.sleeper import service
from app.services.sleeper.projections import projected_points, starter_projection


class ProjectionScoringTests(unittest.TestCase):
    def test_scores_available_stats_using_league_rules_not_generic_points(self):
        stats = {"pass_yd": 250, "pass_td": 2, "pass_int": 1, "rush_yd": 20, "pts_half_ppr": 99}
        self.assertEqual(projected_points(stats, {"pass_yd": .04, "pass_td": 4, "pass_int": -2, "rush_yd": .1}), 18)

    def test_excludes_bench_and_does_not_present_partial_totals(self):
        projections = {"1": {"rec": 4, "rec_yd": 60}, "2": {"rec": 0, "rec_yd": 0}, "bench": {"rec": 10, "rec_yd": 200}}
        scoring = {"rec": .5, "rec_yd": .1}
        self.assertEqual(starter_projection(["1", "2", "0"], projections, scoring), 8)
        self.assertIsNone(starter_projection(["1", "missing"], projections, scoring))
        self.assertIsNone(starter_projection([], projections, scoring))
        self.assertIsNone(starter_projection(["1"], projections, {}))

    def test_zero_negative_and_metadata_only_rows(self):
        self.assertEqual(projected_points({"pts_half_ppr": 0}, {"rec": .5}), 0)
        self.assertEqual(projected_points({"fum_lost": 1}, {"fum_lost": -2}), -2)
        self.assertIsNone(projected_points({"adp_dd_ppr": 999}, {"rec": .5}))
        self.assertIsNone(projected_points({"rec": float("nan")}, {"rec": .5}))

    def test_defense_and_kicker_components(self):
        self.assertEqual(projected_points({"sack": 3, "int": 1, "pts_allow_14_20": 1}, {"sack": 1, "int": 2, "pts_allow_14_20": 1}), 6)
        self.assertEqual(projected_points({"fgm": 2, "xpm": 3, "xpmiss": 1}, {"fgm": 3, "xpm": 1, "xpmiss": -1}), 8)


class ProjectionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        service._projection_cache.clear()

    async def test_cache_uses_season_and_week_and_rescores_for_each_league(self):
        client = SimpleNamespace(
            league=AsyncMock(return_value={"season": "2026", "season_type": "regular", "scoring_settings": {"rec": .5}}),
            projections=AsyncMock(return_value=[{"player_id": "1", "stats": {"rec": 4}, "season": "2026", "season_type": "regular", "week": 3}]),
        )
        adapter = service.SleeperService(client)
        matchups = [SimpleNamespace(roster_a=1, roster_b=2, team_a_starters=[SimpleNamespace(player_id="1")], team_b_starters=[SimpleNamespace(player_id="missing")])]
        self.assertEqual(await adapter.projected_matchup_scores("league", 3, matchups), {1: 2, 2: None})
        client.league.return_value["scoring_settings"] = {"rec": 1}
        self.assertEqual((await adapter.projected_matchup_scores("other-league", 3, matchups))[1], 4)
        self.assertEqual(client.projections.await_count, 1)
        self.assertIsNone((await adapter.projected_matchup_scores("league", 4, matchups))[1])
        self.assertEqual(client.projections.await_count, 2)
        client.league.return_value["season"] = "2027"
        self.assertIsNone((await adapter.projected_matchup_scores("league", 3, matchups))[1])
        self.assertEqual(client.projections.await_count, 3)

    async def test_projection_outage_does_not_block_current_matchups(self):
        season = SimpleNamespace(sleeper_league_id="league")
        week = SimpleNamespace(status=WeekStatus.open, week_number=3)
        with patch.object(routes, "_sync_current", AsyncMock(return_value=(season, week, []))), patch.object(routes, "_week_payload", AsyncMock(return_value={"matchups": []})) as payload, patch.object(routes, "SleeperService") as adapter:
            adapter.return_value.projected_matchup_scores = AsyncMock(side_effect=RuntimeError("Unavailable"))
            with self.assertLogs(routes.__name__, level="WARNING"):
                result = await routes.current_week(True, user=None, db=None)
            self.assertEqual(result, {"matchups": []})
            self.assertEqual(payload.call_args.args[-1], {})
