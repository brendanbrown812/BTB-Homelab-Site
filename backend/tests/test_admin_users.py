import unittest

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.admin.routes import UpdateUser, delete_user, list_users, update_user
from app.core.security import hash_password, verify_password
from app.database.base import Base
from app.models.user import User, UserRole


class AdminUserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_admin_can_edit_role_and_password(self):
        async with self.sessions() as db:
            admin = User(username="admin", display_name="Admin", role=UserRole.admin, is_active=True)
            member = User(username="member", display_name="Member", role=UserRole.user, password_hash=hash_password("old-password-123"), is_active=True)
            db.add_all([admin, member]); await db.commit()
            result = await update_user(member.id, UpdateUser(username="NewMember", display_name="New Name", role=UserRole.admin, new_password="new-password-456"), admin=admin, db=db)
            self.assertEqual(result["username"], "newmember")
            self.assertEqual(result["role"], UserRole.admin)
            self.assertTrue(verify_password("new-password-456", member.password_hash))

    async def test_delete_revokes_access_but_preserves_user_record(self):
        async with self.sessions() as db:
            admin = User(username="admin", display_name="Admin", role=UserRole.admin, is_active=True)
            member = User(username="member", display_name="Member", role=UserRole.user, password_hash=hash_password("old-password-123"), is_active=True)
            db.add_all([admin, member]); await db.commit()
            await delete_user(member.id, admin=admin, db=db)
            self.assertTrue(member.is_deleted)
            self.assertFalse(member.is_active)
            self.assertIsNone(member.password_hash)
            self.assertEqual([user["id"] for user in await list_users(db=db)], [admin.id])

    async def test_admin_cannot_delete_self(self):
        async with self.sessions() as db:
            admin = User(username="admin", display_name="Admin", role=UserRole.admin, is_active=True)
            db.add(admin); await db.commit()
            with self.assertRaises(HTTPException) as error:
                await delete_user(admin.id, admin=admin, db=db)
            self.assertEqual(error.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
