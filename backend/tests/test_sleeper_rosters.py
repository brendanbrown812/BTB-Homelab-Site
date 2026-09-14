import unittest

import app.services.sleeper.service as sleeper_module
from app.services.sleeper.service import SleeperService


class FakeSleeperClient:
    def __init__(self):
        self.player_calls = 0

    async def matchups(self, _league_id: str, _week: int):
        return [
            {"matchup_id": 1, "roster_id": 1, "points": 12.5, "starters": ["101", "AAA"], "players": ["303", "AAA", "101"], "players_points": {"101": 10, "AAA": 2.5, "303": 0}},
            {"matchup_id": 1, "roster_id": 2, "points": 8, "starters": ["202"], "players": ["202"], "players_points": {"202": 8}},
        ]

    async def rosters(self, _league_id: str):
        return [
            {"roster_id": 1, "owner_id": "owner1", "settings": {"wins": 2, "losses": 1}},
            {"roster_id": 2, "owner_id": "owner2", "settings": {"wins": 1, "losses": 2}},
        ]

    async def users(self, _league_id: str):
        return [
            {"user_id": "owner1", "display_name": "One", "avatar": "avatar-one", "metadata": {"team_name": "Team One"}},
            {"user_id": "owner2", "display_name": "Two", "metadata": {}},
        ]

    async def players(self):
        self.player_calls += 1
        return {
            "101": {"full_name": "Quarterback One", "position": "QB", "team": "CHI"},
            "303": {"first_name": "Runner", "last_name": "One", "position": "RB", "team": "MIN", "injury_status": "Q"},
            "202": {"full_name": "Quarterback Two", "position": "QB", "team": "GB"},
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
        self.assertIsNone(first.team_a_starters[1].image_url)
        self.assertEqual(first.team_a_starters[1].points, 2.5)
        self.assertEqual(first.team_a_starters[0].image_url, "https://sleepercdn.com/content/nfl/players/thumb/101.jpg")
        self.assertEqual([player.name for player in first.team_a_bench], ["Runner One"])
        self.assertEqual(first.team_a_bench[0].injury_status, "Q")
        self.assertEqual(first.team_a_avatar_url, "https://sleepercdn.com/avatars/thumbs/avatar-one")

    async def test_archive_uses_shared_client_for_all_history_endpoints(self):
        class ArchiveClient:
            def __init__(self):
                self.matchup_weeks = []
                self.transaction_rounds = []

            async def league(self, league_id): return {"league_id": league_id}
            async def users(self, _league_id): return [{"user_id": "u1"}]
            async def rosters(self, _league_id): return [{"roster_id": 1}]
            async def winners_bracket(self, _league_id): return [{"p": 1}]
            async def losers_bracket(self, _league_id): return [{"p": 2}]
            async def matchups(self, _league_id, week):
                self.matchup_weeks.append(week)
                return [{"week": week}]
            async def transactions(self, _league_id, round_number):
                self.transaction_rounds.append(round_number)
                return [{"round": round_number}]

        client = ArchiveClient()
        result = await SleeperService(client).league_archive("history", max_week=2)  # type: ignore[arg-type]
        self.assertEqual(result.league["league_id"], "history")
        self.assertEqual(sorted(client.matchup_weeks), [1, 2])
        self.assertEqual(sorted(client.transaction_rounds), [0, 1, 2])
        self.assertEqual(result.matchups_by_week[2][0]["week"], 2)


if __name__ == "__main__":
    unittest.main()
