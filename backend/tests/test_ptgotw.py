import unittest
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.features.ptgotw.models import PTGWriteup
from app.features.ptgotw.routes import CommentCreate, CommentUpdate, WriteupCreate, WriteupUpdate, _author_edit_window_open, _author_publish_window_open, _clean_content, create_comment, create_writeup, delete_comment, delete_writeup, editable_writeups, get_writeup, list_comments, list_writeups, upcoming_writeup, update_comment, update_writeup
from app.models.user import User, UserRole


class PTGOTWTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_assignment_is_hidden_until_it_has_content(self):
        async with self.sessions() as db:
            admin = User(username="admin", display_name="Admin", role=UserRole.admin, is_active=True)
            author = User(username="writer", display_name="The Writer", role=UserRole.user, is_active=True)
            db.add_all([admin, author]); await db.commit()
            created = await create_writeup(WriteupCreate(year=2026, week=2, author_id=author.id, submitted_by_author=True, due_date=date.today()), admin=admin, db=db)
            listing = await list_writeups(year=2026, user=author, db=db)
            self.assertEqual(listing["writeups"], [])

            await update_writeup(created["id"], WriteupUpdate(content_html="<script>bad()</script><p><strong>Game time</strong></p>", is_published=True), user=author, db=db)
            listing = await list_writeups(year=2026, user=author, db=db)
            self.assertEqual(len(listing["writeups"]), 1)
            writeup = await db.get(PTGWriteup, created["id"])
            self.assertNotIn("<script>", writeup.content_html)
            self.assertIn("<strong>Game time</strong>", writeup.content_html)

    async def test_author_can_save_content_as_a_private_draft(self):
        async with self.sessions() as db:
            admin = User(username="admin", display_name="Admin", role=UserRole.admin, is_active=True)
            author = User(username="writer", display_name="The Writer", role=UserRole.user, is_active=True)
            db.add_all([admin, author]); await db.commit()
            created = await create_writeup(WriteupCreate(year=2026, week=4, author_id=author.id, submitted_by_author=True, due_date=date.today()), admin=admin, db=db)
            saved = await update_writeup(created["id"], WriteupUpdate(content_html="<p>Work in progress</p>", is_published=False), user=author, db=db)
            listing = await list_writeups(year=2026, user=author, db=db)
            admin_listing = await list_writeups(year=2026, user=admin, db=db)
            self.assertFalse(saved["is_published"])
            self.assertEqual(listing["writeups"], [])
            self.assertTrue(admin_listing["is_admin_view"])
            self.assertEqual(len(admin_listing["writeups"]), 1)
            self.assertFalse(admin_listing["writeups"][0]["is_published"])
            self.assertTrue(admin_listing["writeups"][0]["has_content"])

    async def test_unassigned_user_cannot_edit(self):
        async with self.sessions() as db:
            admin = User(username="admin", display_name="Admin", role=UserRole.admin, is_active=True)
            author = User(username="writer", display_name="Writer", role=UserRole.user, is_active=True)
            other = User(username="other", display_name="Other", role=UserRole.user, is_active=True)
            db.add_all([admin, author, other]); await db.commit()
            created = await create_writeup(WriteupCreate(year=2026, week=3, author_id=author.id, submitted_by_author=True, due_date=date.today()), admin=admin, db=db)
            with self.assertRaises(HTTPException) as error:
                await update_writeup(created["id"], WriteupUpdate(content_html="Nope"), user=other, db=db)
            self.assertEqual(error.exception.status_code, 403)

    async def test_admin_can_delete_a_writeup(self):
        async with self.sessions() as db:
            admin = User(username="admin", display_name="Admin", role=UserRole.admin, is_active=True)
            author = User(username="writer", display_name="Writer", role=UserRole.user, is_active=True)
            db.add_all([admin, author]); await db.commit()
            created = await create_writeup(WriteupCreate(year=2026, week=5, author_id=author.id, submitted_by_author=True, due_date=date.today()), admin=admin, db=db)
            await delete_writeup(created["id"], _=admin, db=db)
            self.assertIsNone(await db.get(PTGWriteup, created["id"]))

    async def test_threaded_comments_show_admin_badge_and_support_owner_edits(self):
        async with self.sessions() as db:
            admin = User(username="admin", display_name="Commissioner", role=UserRole.admin, is_active=True)
            author = User(username="writer", display_name="Writer", role=UserRole.user, is_active=True)
            commenter = User(username="reader", display_name="Reader", role=UserRole.user, is_active=True)
            db.add_all([admin, author, commenter]); await db.commit()
            writeup = await create_writeup(WriteupCreate(year=2026, week=6, author_id=author.id, content_html="<p>Published</p>", is_published=True), admin=admin, db=db)

            admin_thread = await create_comment(writeup["id"], CommentCreate(content="Official note"), user=admin, db=db)
            parent_id = admin_thread["comments"][0]["id"]
            await create_comment(writeup["id"], CommentCreate(content="Good point", parent_id=parent_id), user=commenter, db=db)
            updated = await update_comment(writeup["id"], (await list_comments(writeup["id"], user=commenter, db=db))["comments"][1]["id"], CommentUpdate(content="Really good point"), user=commenter, db=db)

            self.assertTrue(updated["comments"][0]["author"]["is_admin"])
            self.assertEqual(updated["comments"][1]["parent_id"], parent_id)
            self.assertEqual(updated["comments"][1]["content"], "Really good point")
            self.assertIsNotNone(updated["comments"][1]["edited_at"])

    async def test_admin_deletion_keeps_replies_as_a_tombstone(self):
        async with self.sessions() as db:
            admin = User(username="admin", display_name="Admin", role=UserRole.admin, is_active=True)
            author = User(username="writer", display_name="Writer", role=UserRole.user, is_active=True)
            commenter = User(username="reader", display_name="Reader", role=UserRole.user, is_active=True)
            db.add_all([admin, author, commenter]); await db.commit()
            writeup = await create_writeup(WriteupCreate(year=2026, week=7, author_id=author.id, content_html="Published", is_published=True), admin=admin, db=db)
            thread = await create_comment(writeup["id"], CommentCreate(content="Parent"), user=commenter, db=db)
            parent_id = thread["comments"][0]["id"]
            await create_comment(writeup["id"], CommentCreate(content="Reply", parent_id=parent_id), user=author, db=db)

            deleted = await delete_comment(writeup["id"], parent_id, admin=admin, db=db)
            deleted_parent = next(comment for comment in deleted["comments"] if comment["id"] == parent_id)
            reply = next(comment for comment in deleted["comments"] if comment["id"] != parent_id)
            self.assertEqual(len(deleted["comments"]), 2)
            self.assertTrue(deleted_parent["is_deleted"])
            self.assertIsNone(deleted_parent["content"])
            self.assertIsNone(deleted_parent["author"])
            self.assertEqual(reply["parent_id"], parent_id)

    async def test_comments_are_hidden_on_drafts_and_return_after_republishing(self):
        async with self.sessions() as db:
            admin = User(username="admin", display_name="Admin", role=UserRole.admin, is_active=True)
            author = User(username="writer", display_name="Writer", role=UserRole.user, is_active=True)
            db.add_all([admin, author]); await db.commit()
            writeup = await create_writeup(WriteupCreate(year=2026, week=8, author_id=author.id, content_html="Published", is_published=True), admin=admin, db=db)
            await create_comment(writeup["id"], CommentCreate(content="Keep me"), user=author, db=db)
            await update_writeup(writeup["id"], WriteupUpdate(content_html="Draft", is_published=False), user=admin, db=db)
            with self.assertRaises(HTTPException) as error:
                await list_comments(writeup["id"], user=admin, db=db)
            self.assertEqual(error.exception.status_code, 404)
            await update_writeup(writeup["id"], WriteupUpdate(content_html="Published again", is_published=True), user=admin, db=db)
            restored = await list_comments(writeup["id"], user=author, db=db)
            self.assertEqual(restored["comments"][0]["content"], "Keep me")

    async def test_author_can_edit_future_assignment_but_cannot_publish_it_early(self):
        async with self.sessions() as db:
            admin = User(username="admin", display_name="Admin", role=UserRole.admin, is_active=True)
            author = User(username="writer", display_name="Writer", role=UserRole.user, is_active=True)
            db.add_all([admin, author]); await db.commit()
            today = date.today()
            nearer = await create_writeup(WriteupCreate(year=2026, week=9, author_id=author.id, submitted_by_author=True, due_date=today + timedelta(days=14)), admin=admin, db=db)
            future = await create_writeup(WriteupCreate(year=2026, week=10, author_id=author.id, submitted_by_author=True, due_date=today + timedelta(days=15)), admin=admin, db=db)
            expired = await create_writeup(WriteupCreate(year=2026, week=11, author_id=author.id, submitted_by_author=True, due_date=today - timedelta(days=8)), admin=admin, db=db)

            assignments = await editable_writeups(user=author, db=db)
            self.assertEqual({item["id"] for item in assignments}, {nearer["id"], future["id"]})
            self.assertEqual((await get_writeup(future["id"], user=author, db=db))["id"], future["id"])
            self.assertTrue(_author_edit_window_open(await db.get(PTGWriteup, future["id"]), today))
            self.assertFalse(_author_publish_window_open(await db.get(PTGWriteup, future["id"]), today))
            self.assertFalse(_author_edit_window_open(await db.get(PTGWriteup, expired["id"]), today))

            saved = await update_writeup(future["id"], WriteupUpdate(content_html="Early draft", is_published=False), user=author, db=db)
            self.assertFalse(saved["is_published"])
            with self.assertRaises(HTTPException) as error:
                await update_writeup(future["id"], WriteupUpdate(content_html="Too early", is_published=True), user=author, db=db)
            self.assertEqual(error.exception.status_code, 403)

            with self.assertRaises(HTTPException) as error:
                await update_writeup(expired["id"], WriteupUpdate(content_html="Too late", is_published=True), user=author, db=db)
            self.assertEqual(error.exception.status_code, 403)

            reminder = await upcoming_writeup(user=author, db=db)
            self.assertEqual(reminder["id"], nearer["id"])
            self.assertEqual(reminder["days_remaining"], 14)
            await update_writeup(nearer["id"], WriteupUpdate(content_html="Published by admin", is_published=True), user=admin, db=db)
            self.assertIsNone(await upcoming_writeup(user=author, db=db))
            ready = await create_writeup(WriteupCreate(year=2026, week=12, author_id=author.id, submitted_by_author=True, due_date=today + timedelta(days=7)), admin=admin, db=db)
            await update_writeup(ready["id"], WriteupUpdate(content_html="Published", is_published=True), user=author, db=db)
            edited = await update_writeup(ready["id"], WriteupUpdate(content_html="Edited after publishing", is_published=True), user=author, db=db)
            self.assertEqual(edited["content_html"], "Edited after publishing")

    def test_author_can_edit_through_seven_days_after_due_date(self):
        writeup = PTGWriteup(due_date=date(2026, 10, 10), is_published=True)
        self.assertTrue(_author_edit_window_open(writeup, date(2026, 10, 17)))
        self.assertFalse(_author_edit_window_open(writeup, date(2026, 10, 18)))
        self.assertFalse(_author_publish_window_open(writeup, date(2026, 10, 2)))
        self.assertTrue(_author_publish_window_open(writeup, date(2026, 10, 3)))
        self.assertTrue(_author_publish_window_open(writeup, date(2026, 10, 17)))
        self.assertFalse(_author_publish_window_open(writeup, date(2026, 10, 18)))

    def test_writeup_character_limit_is_thirty_thousand(self):
        self.assertEqual(_clean_content("x" * 30000), "x" * 30000)
        with self.assertRaises(HTTPException) as error:
            _clean_content("x" * 30001)
        self.assertEqual(error.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
