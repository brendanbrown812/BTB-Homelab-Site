import unittest
import uuid

from app.features.league_history.statistics import (
    HighlightCandidate,
    HistoryMatchup,
    HistoryPlacement,
    HistoryTransaction,
    calculate_records,
    calculate_weekly_highlights,
    career_totals,
    margin_record,
    merge_weekly_highlights,
    placement_leader,
    season_points_record,
    season_record_extreme,
    streak_record,
    transaction_leader,
    weekly_team_score_record,
)


class LeagueHistoryStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.season = uuid.uuid4()
        self.a, self.b, self.c, self.d = (uuid.uuid4() for _ in range(4))
        self.names = {self.a: "Alpha", self.b: "Beta", self.c: "Gamma", self.d: "Delta"}

    def matchup(self, week, a, b, score_a, score_b, *, metadata=None, year=2025):
        return HistoryMatchup(
            self.season, year, week, a, self.names[a], f"{self.names[a]} Team", score_a,
            b, self.names[b], f"{self.names[b]} Team", score_b, metadata,
        )

    def test_weekly_score_and_margin_records_keep_zeroes_ties_and_skip_incomplete_weeks(self):
        rows = [
            self.matchup(1, self.a, self.b, 0, 0),
            self.matchup(1, self.c, self.d, 10, 5),
            self.matchup(2, self.a, self.c, 999, None),
            self.matchup(2, self.b, self.d, 4, 3),
            self.matchup(3, self.a, self.b, 10, 4),
            self.matchup(3, self.c, self.d, 10, 4),
            self.matchup(4, self.a, self.b, 0, 0, metadata={"is_complete": False}),
        ]
        highest = weekly_team_score_record(rows, highest=True)
        lowest = weekly_team_score_record(rows, highest=False)
        biggest = margin_record(rows, biggest=True)
        closest = margin_record(rows, biggest=False)
        self.assertEqual(highest.entries[0].value, 10)
        self.assertEqual(len(highest.entries), 3)
        self.assertEqual(lowest.entries[0].value, 0)
        self.assertEqual(len(lowest.entries), 2)
        self.assertEqual(biggest.entries[0].value, 6)
        self.assertEqual(len(biggest.entries), 2)
        self.assertEqual(closest.entries[0].value, 0)
        self.assertNotIn(999, [entry.value for entry in highest.entries])

    def test_points_records_and_career_totals_include_stored_playoff_games(self):
        rows = [
            self.matchup(14, self.a, self.b, 100, 90),
            self.matchup(15, self.a, self.c, 110, 80),
        ]
        season_points = season_points_record(rows)
        totals = career_totals(rows)
        self.assertEqual(season_points.entries[0].manager_id, self.a)
        self.assertEqual(season_points.entries[0].value, 210)
        self.assertEqual(totals[self.a]["wins"], 2)
        self.assertEqual(totals[self.a]["points_against"], 170)

    def test_best_worst_records_and_streaks_support_ties_and_losses(self):
        rows = [
            self.matchup(1, self.a, self.b, 20, 10),
            self.matchup(2, self.a, self.b, 30, 20),
            self.matchup(3, self.a, self.c, 10, 40),
            self.matchup(4, self.a, self.c, 5, 15),
        ]
        best = season_record_extreme(rows, best=True)
        worst = season_record_extreme(rows, best=False)
        winning = streak_record(rows, winning=True)
        losing = streak_record(rows, winning=False)
        self.assertEqual(best.entries[0].detail, "2-0")
        self.assertEqual(worst.entries[0].detail, "0-2")
        self.assertEqual({entry.manager_id for entry in winning.entries}, {self.a, self.c})
        self.assertEqual(winning.entries[0].value, 2)
        self.assertEqual({entry.manager_id for entry in losing.entries}, {self.a, self.b})

    def test_transaction_leaders_count_trade_participation_and_successful_acquisitions(self):
        transactions = [
            HistoryTransaction(self.season, 2025, "trade", "complete", (self.a, self.b)),
            HistoryTransaction(self.season, 2025, "trade", "complete", (self.a, self.c)),
            HistoryTransaction(self.season, 2025, "waiver", "complete", (self.b,), (self.b, self.b)),
            HistoryTransaction(self.season, 2025, "free_agent", "complete", (self.c,), (self.c,)),
            HistoryTransaction(self.season, 2025, "waiver", "failed", (self.a,), (self.a,)),
        ]
        trades = transaction_leader(transactions, self.names, acquisitions=False)
        acquisitions = transaction_leader(transactions, self.names, acquisitions=True)
        self.assertEqual((trades.entries[0].manager_id, trades.entries[0].value), (self.a, 2))
        self.assertEqual((acquisitions.entries[0].manager_id, acquisitions.entries[0].value), (self.b, 2))

    def test_placement_leaders_apply_effective_bottom_three_per_season(self):
        rows = [
            HistoryPlacement(self.season, 2025, self.a, "Alpha", 1, 10),
            HistoryPlacement(self.season, 2025, self.b, "Beta", 2, 10),
            HistoryPlacement(self.season, 2025, self.c, "Gamma", 8, 10),
            HistoryPlacement(self.season, 2025, self.d, "Delta", 10, 10),
        ]
        self.assertEqual(placement_leader(rows, kind="championships").entries[0].manager_id, self.a)
        self.assertEqual(len(placement_leader(rows, kind="podiums").entries), 2)
        self.assertEqual({entry.manager_id for entry in placement_leader(rows, kind="bottom_finishes").entries}, {self.c, self.d})

    def test_missing_espn_details_omit_player_and_lineup_highlights(self):
        rows = [self.matchup(1, self.a, self.b, 100, 90)]
        highlights = calculate_weekly_highlights(rows)
        categories = {item.category for item in highlights}
        self.assertIn("Highest-scoring fantasy team", categories)
        self.assertIn("Biggest win", categories)
        self.assertIn("Closest game", categories)
        self.assertNotIn("Highest-scoring starter", categories)
        self.assertNotIn("Lineup efficiency", categories)

    def test_multi_week_playoff_totals_do_not_become_weekly_records_or_highlights(self):
        regular = self.matchup(14, self.a, self.b, 100, 90)
        series = self.matchup(16, self.c, self.d, 250, 200, metadata={"week_end": 17})

        self.assertEqual(weekly_team_score_record([regular, series], highest=True).entries[0].value, 100)
        self.assertEqual(margin_record([regular, series], biggest=True).entries[0].value, 10)
        self.assertFalse(any(item.week == 16 for item in calculate_weekly_highlights([regular, series])))
        self.assertEqual(career_totals([regular, series])[self.c]["points_for"], 250)

    def test_complete_sleeper_player_points_generate_tied_starter_highlights(self):
        metadata = {
            "team_a": {"starters": ["11", "12"], "players_points": {"11": 20, "12": 4}},
            "team_b": {"starters": ["21"], "players_points": {"21": 20}},
        }
        highlights = calculate_weekly_highlights([self.matchup(1, self.a, self.b, 100, 90, metadata=metadata)])
        starters = [item for item in highlights if item.category == "Highest-scoring starter"]
        self.assertEqual({item.player_id for item in starters}, {"11", "21"})
        self.assertTrue(all(item.value == 20 for item in starters))

    def test_incomplete_player_points_omit_starter_highlight(self):
        metadata = {
            "team_a": {"starters": ["11"], "players_points": {}},
            "team_b": {"starters": ["21"], "players_points": {"21": 50}},
        }
        highlights = calculate_weekly_highlights([self.matchup(1, self.a, self.b, 100, 90, metadata=metadata)])
        self.assertNotIn("Highest-scoring starter", {item.category for item in highlights})

    def test_manual_highlight_overrides_calculated_category_but_keeps_custom_awards(self):
        calculated = [
            HighlightCandidate(self.season, 1, "Biggest win", self.a, "Alpha", value=20, source_key="calculated"),
            HighlightCandidate(self.season, 1, "Closest game", value=1, source_key="closest"),
        ]
        manual = [
            HighlightCandidate(self.season, 1, "biggest WIN", self.b, "Beta", value=99, source="manual", source_key="manual"),
            HighlightCandidate(self.season, 1, "Best mascot", self.c, "Gamma", source="manual", source_key="mascot"),
        ]
        merged = merge_weekly_highlights(calculated, manual)
        biggest = [item for item in merged if item.category.casefold() == "biggest win"]
        self.assertEqual(len(biggest), 1)
        self.assertEqual(biggest[0].manager_id, self.b)
        self.assertEqual({item.category for item in merged}, {"biggest WIN", "Closest game", "Best mascot"})

    def test_registry_omits_unavailable_records_instead_of_fabricating_values(self):
        records = calculate_records([], [], [], self.names)
        self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
