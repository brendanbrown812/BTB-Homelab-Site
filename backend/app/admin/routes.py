from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.dependencies import admin_user
from app.core.security import create_setup_token
from app.database.session import get_db
from app.models.user import User, UserRole

router = APIRouter(prefix="/admin/users", tags=["admin users"], dependencies=[Depends(admin_user)])


class CreateUser(BaseModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9_.-]{3,80}$")
    display_name: str = Field(min_length=1, max_length=120)
    role: UserRole = UserRole.user


@router.get("")
async def list_users(db: AsyncSession = Depends(get_db)):
    users = (await db.scalars(select(User).order_by(User.display_name))).all()
    return [{"id": user.id, "username": user.username, "display_name": user.display_name, "role": user.role, "is_active": user.is_active, "is_bootstrap": user.is_bootstrap, "setup_pending": user.password_hash is None} for user in users]


@router.post("", status_code=201)
async def create_user(body: CreateUser, db: AsyncSession = Depends(get_db)):
    username = body.username.lower()
    if await db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=409, detail="That username already exists")
    raw, digest = create_setup_token()
    user = User(username=username, display_name=body.display_name, role=body.role, setup_token_hash=digest, setup_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=48))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"id": user.id, "setup_token": raw, "expires_in_hours": 48}
