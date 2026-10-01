import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.dependencies import current_user
from app.database.base import Base
from app.database.session import get_db
from app.features.ptgotw.models import PTGWriteup
from app.features.ptgotw.ranking_routes import (
    RankingOpenRequest,
    RankingOrderUpdate,
    RankingRevision,
    _calculate_results,
    _validate_future_deadline,
    admin_router,
    close_ranking_period,
    current_ranking,
    open_ranking_period,
    ranking_status,
    save_ranking,
    submit_ranking,
)
from app.features.ptgotw.routes import WriteupUpdate, delete_writeup, update_writeup
from app.models.user import User, UserRole


class PTGOTWRankingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _people(self, db):
        admin = User(username="admin", display_name="Admin", role=UserRole.admin, is_active=True)
        alice = User(username="alice", display_name="Alice", role=UserRole.user, is_active=True)
        bob = User(username="bob", display_name="Bob", role=UserRole.user, is_active=True)
        db.add_all([admin, alice, bob])
        await db.flush()
        return admin, alice, bob

    async def _writeups(self, db, admin, authors, weeks=range(1, 13)):
        rows = []
        for week in weeks:
            author = authors[(week - 1) % len(authors)]
            rows.append(PTGWriteup(
                year=2026,
                week=week,
                content_html=f"Week {week}",
                author_id=author.id,
                is_published=True,
                created_by_user_id=admin.id,
            ))
        db.add_all(rows)
        await db.commit()
        return rows

    async def _full_author_roster(self, db, alice, bob):
        others = [
            User(username=f"manager{index}", display_name=f"Manager {index}", role=UserRole.user, is_active=True)
            for index in range(3, 13)
        ]
        db.add_all(others)
        await db.flush()
        return [alice, bob, *others]

    async def test_new_writeup_is_prepended_without_losing_saved_order(self):
        async with self.sessions() as db:
            admin, alice, _ = await self._people(db)
            first = await self._writeups(db, admin, [alice], weeks=(1, 2))

            initial = await current_ranking(2026, alice, db)
            self.assertEqual([item["week"] for item in initial["writeups"]], [2, 1])
            saved = await save_ranking(
                RankingOrderUpdate(writeup_ids=[first[0].id, first[1].id], revision=0),
                2026,
                alice,
                db,
            )
            self.assertEqual(saved["revision"], 1)
            await self._writeups(db, admin, [alice], weeks=(3,))

            merged = await current_ranking(2026, alice, db)
            self.assertEqual([item["week"] for item in merged["writeups"]], [3, 1, 2])

    async def test_open_requires_all_twelve_published_writeups(self):
        async with self.sessions() as db:
            admin, alice, _ = await self._people(db)
            await self._writeups(db, admin, [alice], weeks=range(1, 12))
            with self.assertRaises(HTTPException) as error:
                await open_ranking_period(
                    2026,
                    RankingOpenRequest(closes_at=datetime.now(timezone.utc) + timedelta(days=1)),
                    admin,
                    db,
                )
            self.assertEqual(error.exception.status_code, 422)

    async def test_open_requires_twelve_distinct_writeup_authors(self):
        async with self.sessions() as db:
            admin, alice, bob = await self._people(db)
            await self._writeups(db, admin, [alice, bob])
            with self.assertRaises(HTTPException) as error:
                await open_ranking_period(
                    2026,
                    RankingOpenRequest(closes_at=datetime.now(timezone.utc) + timedelta(days=1)),
                    admin,
                    db,
                )
            self.assertEqual(error.exception.status_code, 422)
            self.assertIn("12 distinct managers", error.exception.detail)

    async def test_submit_edit_resubmit_and_deadline_lock(self):
        async with self.sessions() as db:
            admin, alice, bob = await self._people(db)
            writeups = await self._writeups(db, admin, await self._full_author_roster(db, alice, bob))
            now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
            with patch("app.features.ptgotw.ranking_routes._utc_now", return_value=now):
                await open_ranking_period(
                    2026,
                    RankingOpenRequest(closes_at=now + timedelta(days=2)),
                    admin,
                    db,
                )
                # Alice is allowed to place her own Week 1 writeup first.
                saved = await save_ranking(
                    RankingOrderUpdate(writeup_ids=[item.id for item in writeups], revision=0),
                    2026,
                    alice,
                    db,
                )
                submitted = await submit_ranking(RankingRevision(revision=saved["revision"]), 2026, alice, db)
                self.assertEqual(submitted["ballot_status"], "submitted")

                edited_order = [writeups[1].id, writeups[0].id, *[item.id for item in writeups[2:]]]
                edited = await save_ranking(
                    RankingOrderUpdate(writeup_ids=edited_order, revision=submitted["revision"]),
                    2026,
                    alice,
                    db,
                )
                self.assertEqual(edited["ballot_status"], "draft")
                self.assertIsNone(edited["submitted_at"])
                resubmitted = await submit_ranking(RankingRevision(revision=edited["revision"]), 2026, alice, db)
                self.assertEqual(resubmitted["ballot_status"], "submitted")

            with patch(
                "app.features.ptgotw.ranking_routes._utc_now",
                return_value=now + timedelta(days=3),
            ):
                closed = await current_ranking(2026, alice, db)
                self.assertEqual(closed["state"], "closed")
                self.assertFalse(closed["can_edit"])
                with self.assertRaises(HTTPException) as error:
                    await save_ranking(
                        RankingOrderUpdate(
                            writeup_ids=edited_order,
                            revision=resubmitted["revision"],
                        ),
                        2026,
                        alice,
                        db,
                    )
                self.assertEqual(error.exception.status_code, 409)

    async def test_complete_order_and_revision_are_enforced(self):
        async with self.sessions() as db:
            admin, alice, _ = await self._people(db)
            writeups = await self._writeups(db, admin, [alice], weeks=(1, 2, 3))
            with self.assertRaises(HTTPException) as duplicate:
                await save_ranking(
                    RankingOrderUpdate(
                        writeup_ids=[writeups[0].id, writeups[0].id, writeups[2].id],
                        revision=0,
                    ),
                    2026,
                    alice,
                    db,
                )
            self.assertEqual(duplicate.exception.status_code, 422)

            saved = await save_ranking(
                RankingOrderUpdate(writeup_ids=[item.id for item in writeups], revision=0),
                2026,
                alice,
                db,
            )
            with self.assertRaises(HTTPException) as stale:
                await save_ranking(
                    RankingOrderUpdate(writeup_ids=[item.id for item in reversed(writeups)], revision=0),
                    2026,
                    alice,
                    db,
                )
            self.assertEqual(stale.exception.status_code, 409)
            self.assertEqual(saved["revision"], 1)

    async def test_admin_sees_ballots_and_correct_five_to_one_scoring(self):
        async with self.sessions() as db:
            admin, alice, bob = await self._people(db)
            writeups = await self._writeups(db, admin, await self._full_author_roster(db, alice, bob))
            now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
            with patch("app.features.ptgotw.ranking_routes._utc_now", return_value=now), patch(
                "app.features.ptgotw.routes.send_writeup_published_notification",
                new=AsyncMock(),
            ) as notify:
                await open_ranking_period(
                    2026,
                    RankingOpenRequest(closes_at=now + timedelta(days=2)),
                    admin,
                    db,
                )
                alice_saved = await save_ranking(
                    RankingOrderUpdate(writeup_ids=[item.id for item in writeups], revision=0),
                    2026,
                    alice,
                    db,
                )
                await submit_ranking(RankingRevision(revision=alice_saved["revision"]), 2026, alice, db)
                await save_ranking(
                    RankingOrderUpdate(writeup_ids=[item.id for item in reversed(writeups)], revision=0),
                    2026,
                    bob,
                    db,
                )
                dashboard = await ranking_status(2026, admin, db)
                notify.assert_not_awaited()

            statuses = {row["display_name"]: row for row in dashboard["managers"]}
            self.assertEqual(statuses["Alice"]["status"], "submitted")
            self.assertEqual(statuses["Bob"]["status"], "draft")
            self.assertEqual(len(statuses["Alice"]["writeups"]), 12)

            submitted = {row["week"]: row for row in dashboard["submitted_results"]}
            self.assertEqual(submitted[1]["points"], 5)
            self.assertEqual(submitted[2]["points"], 4)
            self.assertEqual(submitted[5]["points"], 1)
            self.assertEqual(submitted[6]["points"], 0)
            self.assertEqual(submitted[12]["points"], 0)

            preview = {row["week"]: row for row in dashboard["all_saved_results"]}
            self.assertEqual(preview[1]["points"], 5)
            self.assertEqual(preview[12]["points"], 5)

    async def test_admin_can_close_period_immediately(self):
        async with self.sessions() as db:
            admin, alice, bob = await self._people(db)
            authors = await self._full_author_roster(db, alice, bob)
            await self._writeups(db, admin, authors)
            await open_ranking_period(
                2026,
                RankingOpenRequest(closes_at=datetime.now(timezone.utc) + timedelta(days=1)),
                admin,
                db,
            )
            result = await close_ranking_period(2026, admin, db)
            self.assertEqual(result["state"], "closed")

    async def test_frozen_candidate_cannot_be_deleted_or_reassigned(self):
        async with self.sessions() as db:
            admin, alice, bob = await self._people(db)
            writeups = await self._writeups(db, admin, await self._full_author_roster(db, alice, bob))
            await open_ranking_period(
                2026,
                RankingOpenRequest(closes_at=datetime.now(timezone.utc) + timedelta(days=1)),
                admin,
                db,
            )
            with self.assertRaises(HTTPException) as deleted:
                await delete_writeup(writeups[0].id, admin, db)
            self.assertEqual(deleted.exception.status_code, 409)
            with self.assertRaises(HTTPException) as reassigned:
                await update_writeup(
                    writeups[0].id,
                    WriteupUpdate(content_html="Still published", author_id=bob.id),
                    admin,
                    db,
                )
            self.assertEqual(reassigned.exception.status_code, 409)

    async def test_admin_accounts_cannot_create_manager_ballots(self):
        async with self.sessions() as db:
            admin, alice, _ = await self._people(db)
            await self._writeups(db, admin, [alice], weeks=(1,))
            with self.assertRaises(HTTPException) as error:
                await current_ranking(2026, admin, db)
            self.assertEqual(error.exception.status_code, 403)

    async def test_non_admin_cannot_access_admin_ranking_api(self):
        async with self.sessions() as db:
            _, alice, _ = await self._people(db)
            await db.commit()
            app = FastAPI()
            app.include_router(admin_router)

            async def signed_in_user():
                return alice

            async def test_db():
                yield db

            app.dependency_overrides[current_user] = signed_in_user
            app.dependency_overrides[get_db] = test_db
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/admin/ptgotw/rankings/2026")
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["detail"], "Admin access required")

    def test_deadline_without_offset_is_interpreted_as_chicago_time(self):
        now = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
        with patch("app.features.ptgotw.ranking_routes._utc_now", return_value=now):
            deadline = _validate_future_deadline(datetime(2026, 10, 2, 7, 0))
        self.assertEqual(deadline, datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc))

    def test_results_use_placement_votes_as_tiebreakers_and_preserve_exact_ties(self):
        author_ids = [uuid.uuid4() for _ in range(5)]
        writeups = [
            PTGWriteup(id=uuid.uuid4(), year=2026, week=index + 1, author_id=author_ids[index])
            for index in range(5)
        ]
        rows = [(writeup, f"Manager {index}") for index, writeup in enumerate(writeups)]
        a, b, c, d, e = [writeup.id for writeup in writeups]
        results = _calculate_results(rows, [[a, c, b, d, e], [c, d, b, e, a]])
        by_id = {row["writeup_id"]: row for row in results}
        self.assertEqual(by_id[a]["points"], by_id[b]["points"])
        self.assertLess(by_id[a]["rank"], by_id[b]["rank"])
        self.assertEqual(by_id[a]["placement_votes"][0], 1)

        exact_tie = _calculate_results(rows[:2], [[a, b], [b, a]])
        self.assertEqual(exact_tie[0]["rank"], 1)
        self.assertEqual(exact_tie[1]["rank"], 1)


if __name__ == "__main__":
    unittest.main()
