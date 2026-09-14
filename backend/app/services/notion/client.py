import httpx

from app.core.config import get_settings


class NotionConfigurationError(RuntimeError):
    pass


class NotionAPIError(RuntimeError):
    pass


class NotionClient:
    """Small read-only adapter for Notion's data-source API."""

    def __init__(
        self,
        *,
        token: str | None = None,
        data_source_id: str | None = None,
        database_id: str | None = None,
        client: httpx.AsyncClient | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        timeout: float | None = None,
    ):
        settings = get_settings()
        configured_token = settings.notion_api_token.get_secret_value()
        self._token = token if token is not None else configured_token
        self._data_source_id = data_source_id if data_source_id is not None else settings.notion_game_history_data_source_id
        self._database_id = database_id if database_id is not None else settings.notion_game_history_database_id
        self._client = client
        self._base_url = base_url or settings.notion_base_url
        self._api_version = api_version or settings.notion_api_version
        self._timeout = timeout if timeout is not None else settings.notion_timeout_seconds

    @property
    def headers(self) -> dict[str, str]:
        token = self._token.strip()
        if not token:
            raise NotionConfigurationError("NOTION_API_TOKEN is not configured")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": self._api_version,
        }

    async def _request(self, method: str, path: str, *, json: dict | None = None) -> dict:
        try:
            if self._client:
                response = await self._client.request(
                    method, path, json=json, headers=self.headers, timeout=self._timeout,
                )
            else:
                async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                    response = await client.request(method, path, json=json, headers=self.headers)
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError as error:
                raise NotionAPIError("Notion returned a non-JSON response") from error
            if not isinstance(payload, dict):
                raise NotionAPIError("Notion returned an unexpected response shape")
            return payload
        except httpx.TimeoutException as error:
            raise NotionAPIError("Notion request timed out") from error
        except httpx.HTTPStatusError as error:
            message = ""
            try:
                body = error.response.json()
                message = str(body.get("message") or body.get("code") or "")
            except (ValueError, AttributeError):
                pass
            detail = f": {message[:300]}" if message else ""
            raise NotionAPIError(f"Notion returned HTTP {error.response.status_code}{detail}") from error
        except httpx.RequestError as error:
            raise NotionAPIError("Could not connect to Notion") from error

    async def resolve_data_source_id(self) -> str:
        direct_id = self._data_source_id.strip()
        if direct_id:
            return direct_id
        database_id = self._database_id.strip()
        if not database_id:
            raise NotionConfigurationError(
                "Set NOTION_GAME_HISTORY_DATA_SOURCE_ID or NOTION_GAME_HISTORY_DATABASE_ID"
            )
        database = await self._request("GET", f"/v1/databases/{database_id}")
        sources = database.get("data_sources") or []
        if len(sources) != 1 or not sources[0].get("id"):
            raise NotionConfigurationError(
                "The configured Notion database must contain exactly one data source; "
                "otherwise set NOTION_GAME_HISTORY_DATA_SOURCE_ID explicitly"
            )
        return str(sources[0]["id"])

    async def query_game_history(self) -> list[dict]:
        data_source_id = await self.resolve_data_source_id()
        results: list[dict] = []
        cursor: str | None = None
        while True:
            body: dict[str, object] = {
                "page_size": 100,
                "sorts": [
                    {"property": "Year", "direction": "ascending"},
                    {"property": "Week", "direction": "ascending"},
                ],
            }
            if cursor:
                body["start_cursor"] = cursor
            page = await self._request("POST", f"/v1/data_sources/{data_source_id}/query", json=body)
            rows = page.get("results")
            if not isinstance(rows, list):
                raise NotionAPIError("Notion query response did not contain a results list")
            results.extend(row for row in rows if isinstance(row, dict))
            if not page.get("has_more"):
                return results
            next_cursor = page.get("next_cursor")
            if not next_cursor:
                raise NotionAPIError("Notion indicated another page without returning a cursor")
            cursor = str(next_cursor)
