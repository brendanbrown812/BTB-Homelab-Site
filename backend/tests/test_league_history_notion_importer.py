import json
import unittest

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.features.league_history.models import (
    ImportRun,
    ImportRunStatus,
    LeagueMatchup,
    Manager,
    ManagerAlias,
    ManagerAliasProvider,
    SeasonTeam,
)
from app.features.league_history.notion_importer import import_notion_game_history
from app.models.season import Season, SeasonPlatform
from app.models.user import User  # noqa: F401 - registers the referenced table
from app.services.notion import NotionClient


def _text(kind: str, value: str):
    return {"type": kind, kind: [{"plain_text": value, "text": {"content": value}}]}


def notion_page(
    page_id: str,
    *,
    year=2020,
    week="1",
    team_a="Brendan",
    score_a=101.5,
    team_b="Pete",
    score_b=99.25,
    winner="Brendan",
    ptgotw=False,
):
    return {
        "object": "page",
        "id": page_id,
        "properties": {
            "Year": {"type": "number", "number": year},
            "Week": _text("title", week),
            "Team1Name": _text("rich_text", team_a),
            "Team1Score": {"type": "number", "number": score_a},
            "Team2Name": _text("rich_text", team_b),
            "Team2Score": {"type": "number", "number": score_b},
            "Winner": _text("rich_text", winner),
            "WasPTGOTW": {"type": "checkbox", "checkbox": ptgotw},
        },
    }


class FakeNotionClient:
    def __init__(self, pages):
        self.pages = pages

    async def query_game_history(self):
        return self.pages


class NotionClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_database_container_and_paginates_data_source(self):
        requests = []

        async def handler(request: httpx.Request):
            requests.append(request)
            self.assertEqual(request.headers["authorization"], "Bearer test-token")
            self.assertEqual(request.headers["notion-version"], "2026-03-11")
            if request.method == "GET":
                return httpx.Response(200, json={"object": "database", "data_sources": [{"id": "source-1"}]})
            body = json.loads(request.content)
            if "start_cursor" not in body:
                return httpx.Response(200, json={
                    "object": "list", "results": [{"id": "page-1"}],
                    "has_more": True, "next_cursor": "opaque-cursor",
                })
            self.assertEqual(body["start_cursor"], "opaque-cursor")
            return httpx.Response(200, json={
                "object": "list", "results": [{"id": "page-2"}],
                "has_more": False, "next_cursor": None,
            })

        async with httpx.AsyncClient(
            base_url="https://api.notion.test", transport=httpx.MockTransport(handler),
        ) as http:
            client = NotionClient(token="test-token", database_id="database-1", client=http)
            pages = await client.query_game_history()

        self.assertEqual([page["id"] for page in pages], ["page-1", "page-2"])
        self.assertEqual([request.url.path for request in requests], [
            "/v1/databases/database-1",
            "/v1/data_sources/source-1/query",
            "/v1/data_sources/source-1/query",
        ])


class NotionImporterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _seed(self, db, *, include_pete=True):
        seasons = [
            Season(year=2020, platform=SeasonPlatform.espn),
            Season(year=2021, platform=SeasonPlatform.espn),
        ]
        brendan = Manager(display_name="Brendan")
        pete = Manager(display_name="Pete", is_active=False)
        db.add_all([*seasons, brendan, pete])
        await db.flush()
        aliases = [ManagerAlias(
            manager_id=brendan.id,
            provider=ManagerAliasProvider.notion_name,
            external_value="Brendan",
        )]
        if include_pete:
            aliases.append(ManagerAlias(
                manager_id=pete.id,
                provider=ManagerAliasProvider.notion_name,
                external_value="Pete",
            ))
        db.add_all(aliases)
        await db.commit()
        return seasons, brendan, pete

    async def test_dry_run_reports_aliases_and_planned_inserts_without_writes(self):
        async with self.sessions() as db:
            seasons, _, _ = await self._seed(db)
            self.assertTrue(all(season.sleeper_league_id is None for season in seasons))
            result = await import_notion_game_history(
                db,
                dry_run=True,
                notion=FakeNotionClient([
                    notion_page("page-1"),
                    notion_page("page-2", year=2021, week="Week 2", score_a=88, score_b=90, winner="Pete"),
                ]),  # type: ignore[arg-type]
            )
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["rows_per_season"], {"2020": 1, "2021": 1})
            self.assertEqual(result["records_to_insert"], {"2020": 1, "2021": 1})
            self.assertEqual({item["source_name"] for item in result["resolved_manager_aliases"]}, {"Brendan", "Pete"})
            self.assertEqual(await db.scalar(select(func.count()).select_from(LeagueMatchup)), 0)
            run = await db.get(ImportRun, result["run_id"])
            self.assertEqual(run.status, ImportRunStatus.succeeded)

    async def test_valid_years_outside_espn_import_scope_are_skipped(self):
        async with self.sessions() as db:
            await self._seed(db)
            result = await import_notion_game_history(
                db,
                dry_run=True,
                notion=FakeNotionClient([
                    notion_page("page-2020"),
                    notion_page("page-2022", year=2022),
                ]),  # type: ignore[arg-type]
            )

            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["records_to_insert"], {"2020": 1, "2021": 0})
            self.assertEqual(result["skipped_out_of_scope"], [{"page_id": "page-2022", "year": 2022}])
            self.assertEqual(result["invalid_records"], [])

    async def test_unresolved_former_manager_refuses_commit(self):
        async with self.sessions() as db:
            await self._seed(db, include_pete=False)
            result = await import_notion_game_history(
                db, dry_run=False, notion=FakeNotionClient([notion_page("page-1")]),  # type: ignore[arg-type]
            )
            self.assertEqual(result["status"], "needs_attention")
            self.assertEqual(result["unresolved_names"], ["Pete"])
            self.assertEqual(await db.scalar(select(func.count()).select_from(LeagueMatchup)), 0)
            self.assertEqual(await db.scalar(select(func.count()).select_from(SeasonTeam)), 0)

    async def test_duplicates_and_malformed_rows_are_reported_and_block_commit(self):
        async with self.sessions() as db:
            await self._seed(db)
            result = await import_notion_game_history(
                db,
                dry_run=True,
                notion=FakeNotionClient([
                    notion_page("page-1"),
                    notion_page("page-duplicate", team_a="Pete", team_b="Brendan", score_a=99.25, score_b=101.5),
                    notion_page("page-bad", week="Finale", score_a="not-a-score"),
                ]),  # type: ignore[arg-type]
            )
            self.assertEqual(result["status"], "needs_attention")
            self.assertEqual(result["duplicate_rows"][0]["duplicate_page_id"], "page-duplicate")
            errors = result["invalid_records"][0]["errors"]
            self.assertTrue(any("Week" in error for error in errors))
            self.assertTrue(any("Team1Score" in error for error in errors))

    async def test_repeated_import_updates_same_matchup_and_keeps_ptgotw_as_metadata_only(self):
        async with self.sessions() as db:
            await self._seed(db)
            first = await import_notion_game_history(
                db, dry_run=False, notion=FakeNotionClient([notion_page("page-1", ptgotw=True)]),  # type: ignore[arg-type]
            )
            second = await import_notion_game_history(
                db, dry_run=False, notion=FakeNotionClient([notion_page("page-1", score_a=123.75, ptgotw=False)]),  # type: ignore[arg-type]
            )
            self.assertEqual(first["records_to_insert"]["2020"], 1)
            self.assertEqual(second["records_to_update"]["2020"], 1)
            self.assertEqual(await db.scalar(select(func.count()).select_from(LeagueMatchup)), 1)
            self.assertEqual(await db.scalar(select(func.count()).select_from(SeasonTeam)), 2)
            matchup = await db.scalar(select(LeagueMatchup))
            self.assertEqual(matchup.score_a, 123.75)
            self.assertEqual(matchup.source_metadata, {
                "notion_page_id": "page-1", "winner": "Brendan", "was_ptgotw": False,
                "week_end": None, "week_label": "1",
            })
            self.assertEqual(await db.scalar(select(func.count()).select_from(ImportRun)), 2)

    async def test_two_week_playoff_labels_and_compact_values_import_idempotently(self):
        async with self.sessions() as db:
            await self._seed(db)
            pages = [
                notion_page("page-range", week="PR2 - W16-17 - Loser"),
                notion_page("page-compact", year=2021, week="1415"),
            ]
            first = await import_notion_game_history(
                db, dry_run=False, notion=FakeNotionClient(pages),  # type: ignore[arg-type]
            )
            second = await import_notion_game_history(
                db, dry_run=False, notion=FakeNotionClient(pages),  # type: ignore[arg-type]
            )

            self.assertEqual(first["status"], "succeeded")
            self.assertEqual(first["records_to_insert"], {"2020": 1, "2021": 1})
            self.assertEqual(second["records_to_update"], {"2020": 1, "2021": 1})
            rows = list((await db.scalars(select(LeagueMatchup).order_by(LeagueMatchup.week))).all())
            self.assertEqual([(row.week, row.source_metadata["week_end"]) for row in rows], [(14, 15), (16, 17)])
            self.assertEqual(rows[1].source_metadata["week_label"], "PR2 - W16-17 - Loser")


if __name__ == "__main__":
    unittest.main()
