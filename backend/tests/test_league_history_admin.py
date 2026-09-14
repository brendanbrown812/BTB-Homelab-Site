import unittest

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.dependencies import admin_user
from app.database.base import Base
from app.features.league_history.models import Manager
from app.features.league_history.routes import (
    AliasCreate,
    BiographyUpdate,
    FactCreate,
    FactUpdate,
    HighlightCreate,
    HighlightUpdate,
    ManagerCreate,
    ManagerUpdate,
    PlacementUpdate,
    PunishmentUpdate,
    SeasonCreate,
    SeasonTeamCreate,
    SeasonTeamUpdate,
    SeasonUpdate,
    admin_router,
    router as league_history_router,
    admin_snapshot,
    create_alias,
    create_fact,
    create_highlight,
    create_manager,
    create_season,
    create_season_team,
    delete_alias,
    delete_fact,
    delete_highlight,
    delete_punishment,
    delete_season_team,
    manager_self,
    set_placement,
    set_punishment,
    update_fact,
    update_highlight,
    update_manager,
    update_own_biography,
    update_season,
    update_season_team,
)
from app.features.league_history.models import ManagerAliasProvider
from app.models.season import SeasonPlatform
from app.models.user import User, UserRole


class LeagueHistoryAdminTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _users(self, db):
        admin = User(username="admin", display_name="Commissioner", role=UserRole.admin, is_active=True)
        member = User(username="member", display_name="League Member", role=UserRole.user, is_active=True)
        db.add_all([admin, member])
        await db.commit()
        return admin, member

    async def test_admin_can_manage_complete_manual_history(self):
        async with self.sessions() as db:
            _, member = await self._users(db)
            manager_id = (await create_manager(ManagerCreate(
                display_name="Pete", biography="Original member", is_active=False,
            ), db=db))["id"]
            current_id = (await create_manager(ManagerCreate(
                display_name="League Member", user_id=member.id,
            ), db=db))["id"]
            alias_id = (await create_alias(manager_id, AliasCreate(
                provider=ManagerAliasProvider.notion_name, external_value="  Pete  ",
            ), db=db))["id"]
            season_id = (await create_season(SeasonCreate(
                year=2020, platform=SeasonPlatform.espn,
            ), db=db))["id"]
            team_id = (await create_season_team(season_id, SeasonTeamCreate(
                manager_id=manager_id, team_name="Pete's Team",
            ), db=db))["id"]
            await set_placement(season_id, manager_id, PlacementUpdate(override_placement=12), db=db)
            await set_punishment(season_id, PunishmentUpdate(
                manager_id=manager_id, title="  Run the beer mile  ",
            ), db=db)
            fact_id = (await create_fact(season_id, FactCreate(
                label="Highest score", value="181.2 by Pete", display_order=0,
            ), db=db))["id"]
            highlight_id = (await create_highlight(season_id, HighlightCreate(
                week=1, category="Top scorer", manager_id=manager_id, value=181.2,
            ), db=db))["id"]

            snapshot = await admin_snapshot(db=db)
            self.assertEqual(snapshot["managers"][1]["aliases"][0]["external_value"], "Pete")
            self.assertEqual(snapshot["seasons"][0]["platform"], "espn")
            self.assertIsNone(snapshot["seasons"][0]["sleeper_league_id"])
            self.assertEqual(snapshot["seasons"][0]["placements"][0]["override_placement"], 12)
            self.assertEqual(snapshot["seasons"][0]["punishment"]["title"], "Run the beer mile")

            await update_manager(manager_id, ManagerUpdate(display_name="Peter", is_active=True), db=db)
            await update_season_team(team_id, SeasonTeamUpdate(team_name="New Team Name"), db=db)
            await update_fact(fact_id, FactUpdate(value="Updated fact"), db=db)
            await update_highlight(highlight_id, HighlightUpdate(category="Weekly MVP"), db=db)
            await delete_alias(alias_id, db=db)
            await delete_fact(fact_id, db=db)
            await delete_highlight(highlight_id, db=db)
            await delete_punishment(season_id, db=db)
            await delete_season_team(team_id, db=db)

            snapshot = await admin_snapshot(db=db)
            self.assertEqual(next(item for item in snapshot["managers"] if item["id"] == manager_id)["display_name"], "Peter")
            self.assertEqual(snapshot["seasons"][0]["teams"], [])
            self.assertEqual(snapshot["seasons"][0]["facts"], [])
            self.assertEqual(snapshot["seasons"][0]["highlights"], [])
            self.assertIsNone(snapshot["seasons"][0]["punishment"])
            self.assertEqual(next(item for item in snapshot["managers"] if item["id"] == current_id)["user_id"], member.id)

    async def test_sleeper_seasons_require_an_id_and_ids_are_unique(self):
        async with self.sessions() as db:
            await self._users(db)
            with self.assertRaises(HTTPException) as error:
                await create_season(SeasonCreate(year=2022, platform=SeasonPlatform.sleeper), db=db)
            self.assertEqual(error.exception.status_code, 422)

            first = await create_season(SeasonCreate(
                year=2022, platform=SeasonPlatform.sleeper, sleeper_league_id="league-one", is_active=True,
            ), db=db)
            second = await create_season(SeasonCreate(
                year=2023, platform=SeasonPlatform.sleeper, sleeper_league_id="league-two", is_active=True,
            ), db=db)
            snapshot = await admin_snapshot(db=db)
            active = [season for season in snapshot["seasons"] if season["is_active"]]
            self.assertEqual([season["id"] for season in active], [second["id"]])

            with self.assertRaises(HTTPException) as error:
                await update_season(first["id"], SeasonUpdate(sleeper_league_id="league-two"), db=db)
            self.assertEqual(error.exception.status_code, 409)

    async def test_member_can_only_update_linked_biography(self):
        async with self.sessions() as db:
            _, member = await self._users(db)
            manager_id = (await create_manager(ManagerCreate(
                display_name="Member", user_id=member.id,
            ), db=db))["id"]

            result = await update_own_biography(
                BiographyUpdate(biography="  Longtime league member.  "), user=member, db=db,
            )
            self.assertEqual(result["biography"], "Longtime league member.")
            self.assertEqual((await manager_self(user=member, db=db))["manager"]["id"], manager_id)
            self.assertEqual((await db.get(Manager, manager_id)).display_name, "Member")

        async with self.sessions() as db:
            unlinked = User(username="unlinked", display_name="Unlinked", role=UserRole.user, is_active=True)
            db.add(unlinked)
            await db.commit()
            with self.assertRaises(HTTPException) as error:
                await update_own_biography(BiographyUpdate(biography="No profile"), user=unlinked, db=db)
            self.assertEqual(error.exception.status_code, 404)

    async def test_admin_routes_require_admin_dependency(self):
        self.assertTrue(admin_router.routes)
        for route in admin_router.routes:
            dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
            self.assertIn(admin_user, dependency_calls, route.path)

        member = User(username="member", display_name="Member", role=UserRole.user, is_active=True)
        with self.assertRaises(HTTPException) as error:
            await admin_user(member)
        self.assertEqual(error.exception.status_code, 403)

        route_keys = [(method, route.path) for route in [*admin_router.routes, *league_history_router.routes] for method in route.methods]
        self.assertEqual(len(route_keys), len(set(route_keys)))


if __name__ == "__main__":
    unittest.main()
