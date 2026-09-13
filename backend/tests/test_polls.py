import unittest

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.features.polls.models import PollSelectionMode
from app.features.polls.routes import PollCreate, VoteUpdate, close_poll, create_poll, update_and_reopen_poll, update_vote
from app.models.user import User, UserRole


class PollTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_multiple_choice_vote_returns_named_live_results(self):
        async with self.sessions() as db:
            admin = User(username="admin", display_name="Commissioner", role=UserRole.admin, is_active=True)
            member = User(username="member", display_name="League Member", role=UserRole.user, is_active=True)
            inactive = User(username="inactive", display_name="Inactive Member", role=UserRole.user, is_active=False)
            db.add_all([admin, member, inactive])
            await db.commit()
            poll = await create_poll(PollCreate(question="Pick snacks", description=None, selection_mode=PollSelectionMode.multiple, options=["Wings", "Pizza", "Chips"]), admin=admin, db=db)

            result = await update_vote(poll["id"], VoteUpdate(option_ids=[poll["options"][0]["id"], poll["options"][1]["id"]]), user=member, db=db)

            self.assertEqual(result["current_user_option_ids"], [poll["options"][0]["id"], poll["options"][1]["id"]])
            self.assertEqual(result["options"][0]["voters"][0]["display_name"], "League Member")
            self.assertEqual(result["not_voted"], [])

    async def test_single_choice_poll_rejects_multiple_options(self):
        async with self.sessions() as db:
            admin = User(username="admin", display_name="Commissioner", role=UserRole.admin, is_active=True)
            member = User(username="member", display_name="League Member", role=UserRole.user, is_active=True)
            db.add_all([admin, member])
            await db.commit()
            poll = await create_poll(PollCreate(question="Choose one", description=None, selection_mode=PollSelectionMode.single, options=["A", "B"]), admin=admin, db=db)

            with self.assertRaises(HTTPException) as error:
                await update_vote(poll["id"], VoteUpdate(option_ids=[option["id"] for option in poll["options"]]), user=member, db=db)

            self.assertEqual(error.exception.status_code, 422)

    async def test_user_can_replace_an_existing_vote(self):
        async with self.sessions() as db:
            admin = User(username="admin", display_name="Commissioner", role=UserRole.admin, is_active=True)
            member = User(username="member", display_name="League Member", role=UserRole.user, is_active=True)
            db.add_all([admin, member])
            await db.commit()
            poll = await create_poll(PollCreate(question="Choose one", description=None, selection_mode=PollSelectionMode.single, options=["A", "B"]), admin=admin, db=db)
            await update_vote(poll["id"], VoteUpdate(option_ids=[poll["options"][0]["id"]]), user=member, db=db)

            result = await update_vote(poll["id"], VoteUpdate(option_ids=[poll["options"][1]["id"]]), user=member, db=db)

            self.assertEqual(result["options"][0]["voters"], [])
            self.assertEqual([voter["display_name"] for voter in result["options"][1]["voters"]], ["League Member"])

    async def test_admin_can_edit_and_reopen_a_closed_poll(self):
        async with self.sessions() as db:
            admin = User(username="admin", display_name="Commissioner", role=UserRole.admin, is_active=True)
            member = User(username="member", display_name="League Member", role=UserRole.user, is_active=True)
            db.add_all([admin, member])
            await db.commit()
            poll = await create_poll(PollCreate(question="Old question", description=None, selection_mode=PollSelectionMode.single, options=["A", "B"]), admin=admin, db=db)
            await update_vote(poll["id"], VoteUpdate(option_ids=[poll["options"][0]["id"]]), user=member, db=db)
            await close_poll(poll["id"], admin=admin, db=db)

            result = await update_and_reopen_poll(poll["id"], PollCreate(question="New question", description="More context", selection_mode=PollSelectionMode.multiple, options=["A", "B", "C"]), admin=admin, db=db)

            self.assertTrue(result["is_open"])
            self.assertEqual(result["question"], "New question")
            self.assertEqual([option["text"] for option in result["options"]], ["A", "B", "C"])
            self.assertTrue(all(option["voters"] == [] for option in result["options"]))


if __name__ == "__main__":
    unittest.main()
