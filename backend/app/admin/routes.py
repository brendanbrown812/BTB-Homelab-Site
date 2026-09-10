from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.dependencies import admin_user
from app.core.security import generate_password, hash_password
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
    generated_password = generate_password()
    user = User(
        username=username,
        display_name=body.display_name,
        role=body.role,
        password_hash=hash_password(generated_password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"id": user.id, "generated_password": generated_password}
