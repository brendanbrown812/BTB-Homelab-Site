import asyncio
from collections import defaultdict
from dataclasses import dataclass
from .client import SleeperClient


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


class SleeperService:
    """BTB-wide adapter that keeps Sleeper payloads out of feature routes."""
    def __init__(self, client: SleeperClient | None = None):
        self.client = client or SleeperClient()

    async def weekly_matchups(self, league_id: str, week: int) -> list[SleeperMatchup]:
        rows, rosters, users = await asyncio.gather(
            self.client.matchups(league_id, week),
            self.client.rosters(league_id),
            self.client.users(league_id),
        )
        user_by_id = {str(user["user_id"]): user for user in users}
        roster_by_id = {int(roster["roster_id"]): roster for roster in rosters}

        def identity(roster_id: int) -> tuple[str, str, str]:
            roster = roster_by_id.get(roster_id, {})
            owner = user_by_id.get(str(roster.get("owner_id")), {})
            metadata = owner.get("metadata") or {}
            settings = roster.get("settings") or {}
            owner_name = owner.get("display_name") or f"Roster {roster_id}"
            team_name = metadata.get("team_name") or owner_name
            record = f"{settings.get('wins', 0)}–{settings.get('losses', 0)}"
            if settings.get("ties", 0):
                record += f"–{settings['ties']}"
            return team_name, owner_name, record

        groups: dict[int, list[dict]] = defaultdict(list)
        for row in rows:
            if row.get("matchup_id") is not None:
                groups[int(row["matchup_id"])].append(row)
        result = []
        for matchup_id, pair in groups.items():
            if len(pair) == 2:
                roster_a, roster_b = int(pair[0]["roster_id"]), int(pair[1]["roster_id"])
                team_a, owner_a, record_a = identity(roster_a)
                team_b, owner_b, record_b = identity(roster_b)
                result.append(SleeperMatchup(matchup_id, roster_a, roster_b, pair[0].get("points"), pair[1].get("points"), team_a, team_b, owner_a, owner_b, record_a, record_b))
        return sorted(result, key=lambda item: item.matchup_id)

    async def current_week(self) -> int:
        state = await self.client.state()
        return int(state["week"])
