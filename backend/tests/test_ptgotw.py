import unittest

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.features.ptgotw.models import PTGWriteup
from app.features.ptgotw.routes import WriteupCreate, WriteupUpdate, _clean_content, create_writeup, delete_writeup, list_writeups, update_writeup
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
            created = await create_writeup(WriteupCreate(year=2026, week=2, author_id=author.id, submitted_by_author=True), admin=admin, db=db)
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
            created = await create_writeup(WriteupCreate(year=2026, week=4, author_id=author.id, submitted_by_author=True), admin=admin, db=db)
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
            created = await create_writeup(WriteupCreate(year=2026, week=3, author_id=author.id, submitted_by_author=True), admin=admin, db=db)
            with self.assertRaises(HTTPException) as error:
                await update_writeup(created["id"], WriteupUpdate(content_html="Nope"), user=other, db=db)
            self.assertEqual(error.exception.status_code, 403)

    async def test_admin_can_delete_a_writeup(self):
        async with self.sessions() as db:
            admin = User(username="admin", display_name="Admin", role=UserRole.admin, is_active=True)
            author = User(username="writer", display_name="Writer", role=UserRole.user, is_active=True)
            db.add_all([admin, author]); await db.commit()
            created = await create_writeup(WriteupCreate(year=2026, week=5, author_id=author.id, submitted_by_author=True), admin=admin, db=db)
            await delete_writeup(created["id"], _=admin, db=db)
            self.assertIsNone(await db.get(PTGWriteup, created["id"]))

    def test_writeup_character_limit_is_thirty_thousand(self):
        self.assertEqual(_clean_content("x" * 30000), "x" * 30000)
        with self.assertRaises(HTTPException) as error:
            _clean_content("x" * 30001)
        self.assertEqual(error.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
