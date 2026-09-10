import unittest

import app.services.sleeper.service as sleeper_module
from app.services.sleeper.service import SleeperService


class FakeSleeperClient:
    def __init__(self):
        self.player_calls = 0

    async def matchups(self, _league_id: str, _week: int):
        return [
            {"matchup_id": 1, "roster_id": 1, "points": 12.5, "starters": ["qb1", "AAA"], "players": ["rb1", "AAA", "qb1"], "players_points": {"qb1": 10, "AAA": 2.5, "rb1": 0}},
            {"matchup_id": 1, "roster_id": 2, "points": 8, "starters": ["qb2"], "players": ["qb2"], "players_points": {"qb2": 8}},
        ]

    async def rosters(self, _league_id: str):
        return [
            {"roster_id": 1, "owner_id": "owner1", "settings": {"wins": 2, "losses": 1}},
            {"roster_id": 2, "owner_id": "owner2", "settings": {"wins": 1, "losses": 2}},
        ]

    async def users(self, _league_id: str):
        return [
            {"user_id": "owner1", "display_name": "One", "metadata": {"team_name": "Team One"}},
            {"user_id": "owner2", "display_name": "Two", "metadata": {}},
        ]

    async def players(self):
        self.player_calls += 1
        return {
            "qb1": {"full_name": "Quarterback One", "position": "QB", "team": "CHI"},
            "rb1": {"first_name": "Runner", "last_name": "One", "position": "RB", "team": "MIN", "injury_status": "Q"},
            "qb2": {"full_name": "Quarterback Two", "position": "QB", "team": "GB"},
        }


class SleeperRosterTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_starters_bench_defense_and_points_with_daily_cache(self):
        sleeper_module._player_cache = None
        sleeper_module._player_cache_expires_at = 0
        client = FakeSleeperClient()
        service = SleeperService(client)  # type: ignore[arg-type]

        first = (await service.weekly_matchups("league", 1, include_players=True))[0]
        await service.weekly_matchups("league", 1, include_players=True)

        self.assertEqual(client.player_calls, 1)
        self.assertEqual([player.name for player in first.team_a_starters], ["Quarterback One", "AAA D/ST"])
        self.assertEqual(first.team_a_starters[1].position, "DEF")
        self.assertEqual(first.team_a_starters[1].points, 2.5)
        self.assertEqual([player.name for player in first.team_a_bench], ["Runner One"])
        self.assertEqual(first.team_a_bench[0].injury_status, "Q")


if __name__ == "__main__":
    unittest.main()
