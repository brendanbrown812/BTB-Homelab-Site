from datetime import datetime, timezone
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import create_access_token, hash_password, hash_setup_token, verify_password
from app.database.session import get_db
from app.models.user import User
from app.auth.dependencies import current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class SetupRequest(BaseModel):
    token: str
    password: str = Field(min_length=12, max_length=128)


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    username = body.username.strip().lower()
    user = await db.scalar(select(User).where(User.username == username))
    if not user or not user.is_active or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"access_token": create_access_token(str(user.id), user.role.value), "token_type": "bearer"}


@router.post("/setup-account")
async def setup_account(body: SetupRequest, db: AsyncSession = Depends(get_db)):
    digest = hash_setup_token(body.token)
    user = await db.scalar(select(User).where(User.setup_token_hash == digest))
    expires = user.setup_token_expires_at if user and user.setup_token_expires_at else None
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if not user or not expires or expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Setup credential is invalid or expired")
    user.password_hash = hash_password(body.password)
    user.setup_token_hash = None
    user.setup_token_expires_at = None
    await db.commit()
    return {"message": "Account setup complete"}


@router.get("/me")
async def me(user: User = Depends(current_user)):
    return {"id": user.id, "username": user.username, "display_name": user.display_name, "role": user.role.value}
