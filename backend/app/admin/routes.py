import uuid

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


class UpdateUser(BaseModel):
    username: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_.-]{3,80}$")
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: UserRole | None = None
    new_password: str | None = Field(default=None, min_length=12, max_length=128)


@router.get("")
async def list_users(db: AsyncSession = Depends(get_db)):
    users = (await db.scalars(select(User).where(User.is_deleted.is_(False)).order_by(User.display_name))).all()
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


@router.patch("/{user_id}")
async def update_user(user_id: uuid.UUID, body: UpdateUser, admin: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user or user.is_deleted:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_bootstrap and any(value is not None for value in (body.username, body.display_name, body.role)):
        raise HTTPException(status_code=400, detail="Bootstrap account details are controlled by the environment")
    if body.role is not None and user.id == admin.id and body.role is not UserRole.admin:
        raise HTTPException(status_code=400, detail="You cannot remove your own admin role")
    if body.username is not None:
        username = body.username.lower()
        existing = await db.scalar(select(User).where(User.username == username, User.id != user.id))
        if existing:
            raise HTTPException(status_code=409, detail="That username already exists")
        user.username = username
    if body.display_name is not None:
        user.display_name = body.display_name.strip()
    if body.role is not None:
        user.role = body.role
    if body.new_password:
        user.password_hash = hash_password(body.new_password)
        user.setup_token_hash = None
        user.setup_token_expires_at = None
    await db.commit()
    return {"id": user.id, "username": user.username, "display_name": user.display_name, "role": user.role, "is_active": user.is_active, "is_bootstrap": user.is_bootstrap, "setup_pending": user.password_hash is None}


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: uuid.UUID, admin: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user or user.is_deleted:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    if user.is_bootstrap:
        raise HTTPException(status_code=400, detail="The environment bootstrap account cannot be deleted")
    user.is_deleted = True
    user.is_active = False
    user.password_hash = None
    user.setup_token_hash = None
    user.setup_token_expires_at = None
    user.username = f"deleted-{user.id}"
    await db.commit()
