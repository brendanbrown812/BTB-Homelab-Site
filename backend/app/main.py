from contextlib import asynccontextmanager
from sqlalchemy import inspect, select, text
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.auth.routes import router as auth_router
from app.admin.routes import router as admin_router
from app.core.config import get_settings
from app.database.base import Base
from app.database.session import SessionLocal, engine
from app.features.predictions.routes import router as predictions_router
from app.features.predictions.admin_routes import router as admin_predictions_router
from app.features.ptgotw.routes import router as ptgotw_router
from app.features.polls.routes import router as polls_router
from app.models.season import Season
from app.models.user import User, UserRole
from app.core.security import hash_password, verify_password

settings = get_settings()


def _ensure_local_schema_columns(connection):
    inspector = inspect(connection)
    users_columns = {column["name"] for column in inspector.get_columns("users")}
    if "is_deleted" not in users_columns:
        connection.execute(text("ALTER TABLE users ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0"))
    if "ptgotw_writeups" in inspector.get_table_names():
        writeup_columns = {column["name"] for column in inspector.get_columns("ptgotw_writeups")}
        if "is_published" not in writeup_columns:
            connection.execute(text("ALTER TABLE ptgotw_writeups ADD COLUMN is_published BOOLEAN NOT NULL DEFAULT 1"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.local_create_schema:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.run_sync(_ensure_local_schema_columns)
    if settings.sleeper_league_id and settings.sleeper_league_id != "put-your-sleeper-league-id-here":
        async with SessionLocal() as db:
            season = await db.scalar(select(Season).where(Season.year == settings.season_year))
            if season:
                season.sleeper_league_id = settings.sleeper_league_id
                season.is_active = True
            else:
                db.add(Season(year=settings.season_year, sleeper_league_id=settings.sleeper_league_id, is_active=True))
            await db.commit()
    bootstrap_password = settings.bootstrap_admin_password
    if bootstrap_password == "replace-with-a-temporary-admin-password":
        bootstrap_password = ""
    if bootstrap_password and len(bootstrap_password) < 12:
        raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must be at least 12 characters")
    async with SessionLocal() as db:
        bootstrap = await db.scalar(select(User).where(User.is_bootstrap.is_(True)))
        if bootstrap_password:
            if not bootstrap:
                bootstrap = User(
                    username=settings.bootstrap_admin_username.lower(),
                    display_name=settings.bootstrap_admin_display_name,
                    role=UserRole.admin,
                    password_hash=hash_password(bootstrap_password),
                    is_active=True,
                    is_bootstrap=True,
                )
                db.add(bootstrap)
            else:
                bootstrap.username = settings.bootstrap_admin_username.lower()
                bootstrap.display_name = settings.bootstrap_admin_display_name
                bootstrap.role = UserRole.admin
                bootstrap.is_active = True
                if not bootstrap.password_hash or not verify_password(bootstrap_password, bootstrap.password_hash):
                    bootstrap.password_hash = hash_password(bootstrap_password)
        elif bootstrap:
            bootstrap.is_active = False
        await db.commit()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()
    ],
    # Local dev servers may choose another free port, and the browser may use
    # either loopback hostname. Docker explicitly disables LOCAL_CREATE_SCHEMA,
    # so deployed environments still rely only on CORS_ORIGINS above.
    allow_origin_regex=(
        r"^https?://(?:localhost|127\.0\.0\.1)(?::\d+)?$"
        if settings.local_create_schema
        else None
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(predictions_router, prefix="/api")
app.include_router(admin_predictions_router, prefix="/api")
app.include_router(ptgotw_router, prefix="/api")
app.include_router(polls_router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
