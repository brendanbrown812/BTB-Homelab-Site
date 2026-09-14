import httpx
from app.core.config import get_settings


class SleeperClient:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    async def get(self, path: str, timeout: float = 15) -> object:
        if self._client:
            response = await self._client.get(path, timeout=timeout)
            response.raise_for_status()
            return response.json()
        async with httpx.AsyncClient(base_url=get_settings().sleeper_base_url, timeout=timeout) as client:
            response = await client.get(path)
            response.raise_for_status()
            return response.json()

    async def league(self, league_id: str) -> dict:
        return await self.get(f"/league/{league_id}")  # type: ignore[return-value]

    async def rosters(self, league_id: str) -> list[dict]:
        return await self.get(f"/league/{league_id}/rosters")  # type: ignore[return-value]

    async def users(self, league_id: str) -> list[dict]:
        return await self.get(f"/league/{league_id}/users")  # type: ignore[return-value]

    async def matchups(self, league_id: str, week: int) -> list[dict]:
        return await self.get(f"/league/{league_id}/matchups/{week}")  # type: ignore[return-value]

    async def winners_bracket(self, league_id: str) -> list[dict]:
        return await self.get(f"/league/{league_id}/winners_bracket")  # type: ignore[return-value]

    async def losers_bracket(self, league_id: str) -> list[dict]:
        return await self.get(f"/league/{league_id}/losers_bracket")  # type: ignore[return-value]

    async def transactions(self, league_id: str, round_number: int) -> list[dict]:
        return await self.get(f"/league/{league_id}/transactions/{round_number}")  # type: ignore[return-value]

    async def players(self, sport: str = "nfl") -> dict[str, dict]:
        # Sleeper's player catalog is about 5 MB, so allow more time than the
        # smaller league endpoints. SleeperService caches it for 24 hours.
        return await self.get(f"/players/{sport}", timeout=60)  # type: ignore[return-value]

    async def state(self, sport: str = "nfl") -> dict:
        return await self.get(f"/state/{sport}")  # type: ignore[return-value]
