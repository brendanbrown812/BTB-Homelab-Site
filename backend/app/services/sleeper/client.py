import httpx
from app.core.config import get_settings


class SleeperClient:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    async def get(self, path: str) -> object:
        if self._client:
            response = await self._client.get(path)
            response.raise_for_status()
            return response.json()
        async with httpx.AsyncClient(base_url=get_settings().sleeper_base_url, timeout=15) as client:
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

    async def state(self, sport: str = "nfl") -> dict:
        return await self.get(f"/state/{sport}")  # type: ignore[return-value]
