import unittest
import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.features.ptgotw.models import PTGWriteup
from app.features.ptgotw.routes import (
    WriteupCreate, WriteupUpdate, _league_today, autosave_writeup_draft,
    create_writeup, editable_writeups, get_writeup, list_writeups, update_writeup,
)
from app.main import _ensure_local_schema_columns
from app.models.user import User, UserRole


class WriteupDraftTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def seed(self, db, published=True):
        admin = User(username="admin", display_name="Admin", role=UserRole.admin)
        author = User(username="writer", display_name="Writer", role=UserRole.user)
        reader = User(username="reader", display_name="Reader", role=UserRole.user)
        db.add_all([admin, author, reader])
        await db.commit()
        entry = await create_writeup(WriteupCreate(year=2026, week=3, author_id=author.id, submitted_by_author=True, due_date=_league_today(), content_html="<p>Live version</p>", is_published=published), admin, db)
        return admin, author, reader, entry["id"]

    async def test_autosave_never_changes_public_content_or_metadata(self):
        async with self.sessions() as db:
            admin, author, reader, entry_id = await self.seed(db)
            draft = await autosave_writeup_draft(entry_id, WriteupUpdate(content_html='<p onclick="bad()">Draft</p>', week=4, is_published=False), admin, db)
            self.assertTrue(draft["is_published"])
            self.assertEqual(draft["draft"]["content_html"], "<p>Draft</p>")
            self.assertEqual(draft["draft"]["week"], 4)
            public = await get_writeup(entry_id, reader, db)
            self.assertEqual(public["content_html"], "<p>Live version</p>")
            self.assertEqual(public["week"], 3)
            self.assertNotIn("draft", public)
            self.assertNotIn("draft", (await list_writeups(2026, reader, db))["writeups"][0])
            editor = await editable_writeups(author, db)
            self.assertEqual(editor[0]["draft"]["content_html"], "<p>Draft</p>")
            published = await update_writeup(entry_id, WriteupUpdate(content_html="<p>Final</p>", is_published=True, week=4), admin, db)
            self.assertEqual(published["content_html"], "<p>Final</p>")
            self.assertIsNone((await db.get(PTGWriteup, entry_id)).draft)

    async def test_draft_permissions_and_publish_window_remain_enforced(self):
        async with self.sessions() as db:
            admin, author, reader, entry_id = await self.seed(db, published=False)
            entry = await db.get(PTGWriteup, entry_id)
            entry.due_date = _league_today() + timedelta(days=20)
            await db.commit()
            saved = await autosave_writeup_draft(entry_id, WriteupUpdate(content_html="Early draft", is_published=True, author_id=reader.id, week=10), author, db)
            self.assertFalse(saved["is_published"])
            self.assertEqual(saved["draft"], {"content_html": "Early draft"})
            self.assertEqual((await list_writeups(2026, reader, db))["writeups"], [])
            with self.assertRaises(HTTPException) as error:
                await update_writeup(entry_id, WriteupUpdate(content_html="Early draft", is_published=True), author, db)
            self.assertEqual(error.exception.status_code, 403)
            with self.assertRaises(HTTPException):
                await autosave_writeup_draft(entry_id, WriteupUpdate(content_html="Other user"), reader, db)
            entry.due_date = _league_today() - timedelta(days=8)
            await db.commit()
            with self.assertRaises(HTTPException):
                await autosave_writeup_draft(entry_id, WriteupUpdate(content_html="Too late"), author, db)

    async def test_create_retries_use_stable_id_without_duplicate_entries(self):
        async with self.sessions() as db:
            admin, author, _, _ = await self.seed(db)
            body = WriteupCreate(id=uuid.uuid4(), year=2026, week=4, author_id=author.id)
            first = await create_writeup(body, admin, db)
            retry = await create_writeup(body, admin, db)
            self.assertEqual(first["id"], retry["id"])
            self.assertEqual(await db.scalar(select(func.count()).select_from(PTGWriteup)), 2)

    async def test_blank_draft_is_preserved_and_limits_are_checked(self):
        async with self.sessions() as db:
            _, author, reader, entry_id = await self.seed(db)
            await autosave_writeup_draft(entry_id, WriteupUpdate(content_html=""), author, db)
            self.assertEqual((await editable_writeups(author, db))[0]["draft"]["content_html"], "")
            self.assertEqual((await get_writeup(entry_id, reader, db))["content_html"], "<p>Live version</p>")
            with self.assertRaises(HTTPException) as error:
                await autosave_writeup_draft(entry_id, WriteupUpdate(content_html="x" * 30001), author, db)
            self.assertEqual(error.exception.status_code, 422)

    async def test_existing_local_database_gets_nullable_draft_column(self):
        async with self.engine.begin() as connection:
            await connection.execute(text("ALTER TABLE ptgotw_writeups DROP COLUMN draft"))
            await connection.run_sync(_ensure_local_schema_columns)
            await connection.run_sync(_ensure_local_schema_columns)
            await connection.execute(text("SELECT draft FROM ptgotw_writeups"))
