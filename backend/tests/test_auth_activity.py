import unittest
from datetime import datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.dependencies import current_user
from app.core.security import create_access_token
from app.database.base import Base
from app.main import _ensure_local_schema_columns
from app.models.user import User, UserRole


class AuthActivityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_authenticated_request_updates_last_active_time(self):
        async with self.sessions() as db:
            user = User(username="member", display_name="Member", role=UserRole.user, is_active=True)
            db.add(user)
            await db.commit()

            before_request = datetime.now(timezone.utc)
            authenticated_user = await current_user(
                token=create_access_token(str(user.id), user.role.value),
                db=db,
            )

            self.assertIsNotNone(authenticated_user.last_active_at)
            self.assertGreaterEqual(authenticated_user.last_active_at, before_request)

    async def test_existing_local_database_gets_last_active_column(self):
        async with self.engine.begin() as connection:
            await connection.execute(text("ALTER TABLE users DROP COLUMN last_active_at"))
            await connection.run_sync(_ensure_local_schema_columns)
            await connection.run_sync(_ensure_local_schema_columns)
            columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"] for column in inspect(sync_connection).get_columns("users")
                }
            )

        self.assertIn("last_active_at", columns)


if __name__ == "__main__":
    unittest.main()
