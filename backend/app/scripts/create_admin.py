import asyncio
import getpass
import sys
from sqlalchemy import select
from app.core.security import hash_password
from app.database.session import SessionLocal
from app.database.session import engine
from app.database.base import Base
from app.models.user import User, UserRole


async def create_admin(username: str, display_name: str) -> None:
    password = getpass.getpass("Admin password (12+ characters): ")
    if len(password) < 12:
        raise SystemExit("Password must be at least 12 characters.")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        if await db.scalar(select(User).where(User.username == username.lower())):
            raise SystemExit("That username already exists.")
        db.add(User(username=username.lower(), display_name=display_name, role=UserRole.admin, password_hash=hash_password(password)))
        await db.commit()
    print(f"Created BTB admin: {username.lower()}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python -m app.scripts.create_admin USERNAME 'Display Name'")
    asyncio.run(create_admin(sys.argv[1], sys.argv[2]))
