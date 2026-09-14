import asyncio
from collections import defaultdict
from dataclasses import dataclass
from time import monotonic
from .client import SleeperClient


PLAYER_CACHE_SECONDS = 24 * 60 * 60
_player_cache: dict[str, dict] | None = None
_player_cache_expires_at = 0.0
_player_cache_lock = asyncio.Lock()


@dataclass(frozen=True)
class SleeperPlayer:
    player_id: str
    name: str
    position: str
    team: str | None
    injury_status: str | None
    points: float | None
    image_url: str | None


@dataclass(frozen=True)
class SleeperMatchup:
    matchup_id: int
    roster_a: int
    roster_b: int
    score_a: float | None
    score_b: float | None
    team_a_name: str
    team_b_name: str
    team_a_owner: str
    team_b_owner: str
    team_a_record: str
    team_b_record: str
    team_a_avatar_url: str | None = None
    team_b_avatar_url: str | None = None
    team_a_starters: tuple[SleeperPlayer, ...] = ()
    team_a_bench: tuple[SleeperPlayer, ...] = ()
    team_b_starters: tuple[SleeperPlayer, ...] = ()
    team_b_bench: tuple[SleeperPlayer, ...] = ()


@dataclass(frozen=True)
class SleeperLeagueArchive:
    league: dict
    users: tuple[dict, ...]
    rosters: tuple[dict, ...]
    matchups_by_week: dict[int, tuple[dict, ...]]
    transactions_by_round: dict[int, tuple[dict, ...]]
    winners_bracket: tuple[dict, ...]
    losers_bracket: tuple[dict, ...]


class SleeperService:
    """BTB-wide adapter that keeps Sleeper payloads out of feature routes."""
    def __init__(self, client: SleeperClient | None = None):
        self.client = client or SleeperClient()

    async def _players(self) -> dict[str, dict]:
        global _player_cache, _player_cache_expires_at
        now = monotonic()
        if _player_cache is not None and now < _player_cache_expires_at:
            return _player_cache
        async with _player_cache_lock:
            now = monotonic()
            if _player_cache is not None and now < _player_cache_expires_at:
                return _player_cache
            try:
                catalog = await self.client.players()
            except Exception:
                # Player names are preferable to stale data, but stale names
                # are preferable to taking the predictions page offline.
                if _player_cache is not None:
                    return _player_cache
                raise
            kept_fields = ("full_name", "first_name", "last_name", "position", "fantasy_positions", "team", "injury_status")
            _player_cache = {
                str(player_id): {field: details.get(field) for field in kept_fields}
                for player_id, details in catalog.items()
                if isinstance(details, dict)
            }
            _player_cache_expires_at = monotonic() + PLAYER_CACHE_SECONDS
            return _player_cache

    async def league_metadata(self, league_id: str) -> dict:
        return await self.client.league(league_id)

    async def league_users(self, league_id: str) -> list[dict]:
        return await self.client.users(league_id)

    async def league_rosters(self, league_id: str) -> list[dict]:
        return await self.client.rosters(league_id)

    async def league_week_matchups(self, league_id: str, week: int) -> list[dict]:
        return await self.client.matchups(league_id, week)

    async def league_winners_bracket(self, league_id: str) -> list[dict]:
        return await self.client.winners_bracket(league_id)

    async def league_losers_bracket(self, league_id: str) -> list[dict]:
        return await self.client.losers_bracket(league_id)

    async def league_transactions(self, league_id: str, round_number: int) -> list[dict]:
        return await self.client.transactions(league_id, round_number)

    async def player_lookup(self, player_ids: set[str]) -> dict[str, SleeperPlayer]:
        catalog = await self._players()
        result: dict[str, SleeperPlayer] = {}
        for player_id in player_ids:
            details = catalog.get(str(player_id)) or {}
            position = details.get("position") or next(iter(details.get("fantasy_positions") or []), None)
            first_name = details.get("first_name") or ""
            last_name = details.get("last_name") or ""
            name = details.get("full_name") or f"{first_name} {last_name}".strip() or f"Player {player_id}"
            result[str(player_id)] = SleeperPlayer(
                player_id=str(player_id), name=name, position=position or "—",
                team=details.get("team"), injury_status=details.get("injury_status"),
                points=None,
                image_url=(
                    f"https://sleepercdn.com/content/nfl/players/thumb/{player_id}.jpg"
                    if str(player_id).isdigit() else None
                ),
            )
        return result

    async def current_roster(self, league_id: str, roster_id: int) -> tuple[SleeperPlayer, ...]:
        """Return one roster and the cached catalog without loading league history."""
        rosters = await self.league_rosters(league_id)
        roster = next((row for row in rosters if int(row.get("roster_id", -1)) == roster_id), None)
        if roster is None:
            return ()
        player_ids = {str(value) for value in roster.get("players") or [] if value and str(value) != "0"}
        players = await self.player_lookup(player_ids)
        position_order = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "K": 4, "DEF": 5}
        return tuple(sorted(
            players.values(),
            key=lambda player: (position_order.get(player.position, 99), player.name),
        ))

    async def league_archive(self, league_id: str, max_week: int = 18) -> SleeperLeagueArchive:
        """Fetch one immutable view of a league through the shared Sleeper adapter."""
        league, users, rosters, winners, losers = await asyncio.gather(
            self.league_metadata(league_id),
            self.league_users(league_id),
            self.league_rosters(league_id),
            self.league_winners_bracket(league_id),
            self.league_losers_bracket(league_id),
        )
        matchup_rows, transaction_rows = await asyncio.gather(
            asyncio.gather(*(self.league_week_matchups(league_id, week) for week in range(1, max_week + 1))),
            asyncio.gather(*(self.league_transactions(league_id, round_number) for round_number in range(0, max_week + 1))),
        )
        return SleeperLeagueArchive(
            league=league,
            users=tuple(users),
            rosters=tuple(rosters),
            matchups_by_week={week: tuple(rows) for week, rows in enumerate(matchup_rows, start=1)},
            transactions_by_round={round_number: tuple(rows) for round_number, rows in enumerate(transaction_rows)},
            winners_bracket=tuple(winners),
            losers_bracket=tuple(losers),
        )

    async def weekly_matchups(self, league_id: str, week: int, include_players: bool = False) -> list[SleeperMatchup]:
        rows, rosters, users = await asyncio.gather(
            self.client.matchups(league_id, week),
            self.client.rosters(league_id),
            self.client.users(league_id),
        )
        catalog = await self._players() if include_players else {}
        user_by_id = {str(user["user_id"]): user for user in users}
        roster_by_id = {int(roster["roster_id"]): roster for roster in rosters}

        def identity(roster_id: int) -> tuple[str, str, str, str | None]:
            roster = roster_by_id.get(roster_id, {})
            owner = user_by_id.get(str(roster.get("owner_id")), {})
            metadata = owner.get("metadata") or {}
            settings = roster.get("settings") or {}
            owner_name = owner.get("display_name") or f"Roster {roster_id}"
            team_name = metadata.get("team_name") or owner_name
            record = f"{settings.get('wins', 0)}–{settings.get('losses', 0)}"
            if settings.get("ties", 0):
                record += f"–{settings['ties']}"
            avatar_id = owner.get("avatar")
            avatar_url = f"https://sleepercdn.com/avatars/thumbs/{avatar_id}" if avatar_id else None
            return team_name, owner_name, record, avatar_url

        def player(player_id: object, points: dict) -> SleeperPlayer:
            key = str(player_id)
            details = catalog.get(key) or {}
            position = details.get("position") or next(iter(details.get("fantasy_positions") or []), None)
            if not position and key.isalpha() and len(key) <= 4:
                position = "DEF"
            first_name = details.get("first_name") or ""
            last_name = details.get("last_name") or ""
            name = details.get("full_name") or f"{first_name} {last_name}".strip()
            if not name:
                name = f"{key} D/ST" if position == "DEF" else f"Player {key}"
            raw_points = points.get(key)
            return SleeperPlayer(
                player_id=key,
                name=name,
                position=position or "—",
                team=details.get("team") or (key if position == "DEF" else None),
                injury_status=details.get("injury_status"),
                points=float(raw_points) if raw_points is not None else None,
                image_url=f"https://sleepercdn.com/content/nfl/players/thumb/{key}.jpg" if key.isdigit() else None,
            )

        def lineup(row: dict) -> tuple[tuple[SleeperPlayer, ...], tuple[SleeperPlayer, ...]]:
            if not include_players:
                return (), ()
            starter_ids = [str(value) for value in row.get("starters") or [] if value and str(value) != "0"]
            starter_set = set(starter_ids)
            all_ids = [str(value) for value in row.get("players") or [] if value and str(value) != "0"]
            points = row.get("players_points") or {}
            starters = tuple(player(value, points) for value in starter_ids)
            position_order = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "K": 4, "DEF": 5}
            bench = tuple(sorted(
                (player(value, points) for value in all_ids if value not in starter_set),
                key=lambda value: (position_order.get(value.position, 99), value.name),
            ))
            return starters, bench

        groups: dict[int, list[dict]] = defaultdict(list)
        for row in rows:
            if row.get("matchup_id") is not None:
                groups[int(row["matchup_id"])].append(row)
        result = []
        for matchup_id, pair in groups.items():
            if len(pair) == 2:
                roster_a, roster_b = int(pair[0]["roster_id"]), int(pair[1]["roster_id"])
                team_a, owner_a, record_a, avatar_a = identity(roster_a)
                team_b, owner_b, record_b, avatar_b = identity(roster_b)
                starters_a, bench_a = lineup(pair[0])
                starters_b, bench_b = lineup(pair[1])
                result.append(SleeperMatchup(
                    matchup_id=matchup_id,
                    roster_a=roster_a,
                    roster_b=roster_b,
                    score_a=pair[0].get("points"),
                    score_b=pair[1].get("points"),
                    team_a_name=team_a,
                    team_b_name=team_b,
                    team_a_owner=owner_a,
                    team_b_owner=owner_b,
                    team_a_record=record_a,
                    team_b_record=record_b,
                    team_a_avatar_url=avatar_a,
                    team_b_avatar_url=avatar_b,
                    team_a_starters=starters_a,
                    team_a_bench=bench_a,
                    team_b_starters=starters_b,
                    team_b_bench=bench_b,
                ))
        return sorted(result, key=lambda item: item.matchup_id)

    async def current_week(self) -> int:
        state = await self.client.state()
        return int(state["week"])
