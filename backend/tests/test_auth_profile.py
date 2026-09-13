import unittest

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.routes import UpdateProfileRequest, update_profile
from app.database.base import Base
from app.models.user import User, UserRole


class AuthProfileTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_user_can_update_display_name(self):
        async with self.sessions() as db:
            user = User(username="member", display_name="Old Name", role=UserRole.user, is_active=True)
            db.add(user)
            await db.commit()

            result = await update_profile(UpdateProfileRequest(display_name="  New Name  "), user=user, db=db)

            self.assertEqual(result["display_name"], "New Name")
            self.assertEqual(user.display_name, "New Name")

    async def test_display_name_cannot_be_only_whitespace(self):
        async with self.sessions() as db:
            user = User(username="member", display_name="Old Name", role=UserRole.user, is_active=True)
            db.add(user)
            await db.commit()

            with self.assertRaises(HTTPException) as error:
                await update_profile(UpdateProfileRequest(display_name="   "), user=user, db=db)

            self.assertEqual(error.exception.status_code, 422)
            self.assertEqual(user.display_name, "Old Name")


if __name__ == "__main__":
    unittest.main()
