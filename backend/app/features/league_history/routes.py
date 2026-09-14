import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import admin_user, current_user
from app.database.session import get_db
from app.features.league_history.models import (
    CustomSeasonFact,
    ImportRun,
    Manager,
    ManagerAlias,
    ManagerAliasProvider,
    SeasonPlacement,
    SeasonPunishment,
    SeasonTeam,
    WeeklyHighlight,
    WeeklyHighlightSource,
)
from app.features.league_history.notion_importer import import_notion_game_history
from app.features.league_history.sleeper_importer import import_sleeper_season, refresh_sleeper_seasons
from app.models.season import Season, SeasonPlatform
from app.models.user import User
from app.services.notion import NotionAPIError, NotionClient, NotionConfigurationError
from app.services.sleeper import SleeperService


admin_router = APIRouter(
    prefix="/admin/league-history",
    tags=["admin league history"],
    dependencies=[Depends(admin_user)],
)
router = APIRouter(prefix="/league-history", tags=["league history"])


def get_sleeper_service() -> SleeperService:
    return SleeperService()


def get_notion_client() -> NotionClient:
    return NotionClient()


class ManagerCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    biography: str = Field(default="", max_length=10000)
    is_active: bool = True
    user_id: uuid.UUID | None = None


class ManagerUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    biography: str | None = Field(default=None, max_length=10000)
    is_active: bool | None = None
    user_id: uuid.UUID | None = None
    clear_user_link: bool = False


class BiographyUpdate(BaseModel):
    biography: str = Field(max_length=10000)


class AliasCreate(BaseModel):
    provider: ManagerAliasProvider
    external_value: str = Field(min_length=1, max_length=255)


class SeasonCreate(BaseModel):
    year: int = Field(ge=2020, le=2100)
    platform: SeasonPlatform
    sleeper_league_id: str | None = Field(default=None, max_length=80)
    is_active: bool = False


class SeasonUpdate(BaseModel):
    year: int | None = Field(default=None, ge=2020, le=2100)
    platform: SeasonPlatform | None = None
    sleeper_league_id: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None
    clear_sleeper_league_id: bool = False


class SeasonTeamCreate(BaseModel):
    manager_id: uuid.UUID
    team_name: str = Field(min_length=1, max_length=120)
    sleeper_user_id: str | None = Field(default=None, max_length=80)
    roster_id: int | None = Field(default=None, ge=1)


class SeasonTeamUpdate(BaseModel):
    manager_id: uuid.UUID | None = None
    team_name: str | None = Field(default=None, min_length=1, max_length=120)
    sleeper_user_id: str | None = Field(default=None, max_length=80)
    roster_id: int | None = Field(default=None, ge=1)
    clear_sleeper_user_id: bool = False
    clear_roster_id: bool = False


class PlacementUpdate(BaseModel):
    calculated_placement: int | None = Field(default=None, ge=1)
    override_placement: int | None = Field(default=None, ge=1)
    clear_override: bool = False


class PunishmentUpdate(BaseModel):
    manager_id: uuid.UUID
    title: str = Field(min_length=1, max_length=240)


class FactCreate(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    value: str = Field(min_length=1, max_length=10000)
    display_order: int = Field(ge=0)


class FactUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=160)
    value: str | None = Field(default=None, min_length=1, max_length=10000)
    display_order: int | None = Field(default=None, ge=0)


class HighlightCreate(BaseModel):
    week: int = Field(ge=1, le=30)
    category: str = Field(min_length=1, max_length=80)
    manager_id: uuid.UUID | None = None
    player_id: str | None = Field(default=None, max_length=80)
    player_name: str | None = Field(default=None, max_length=160)
    value: float | None = None


class HighlightUpdate(BaseModel):
    week: int | None = Field(default=None, ge=1, le=30)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    manager_id: uuid.UUID | None = None
    player_id: str | None = Field(default=None, max_length=80)
    player_name: str | None = Field(default=None, max_length=160)
    value: float | None = None
    clear_manager: bool = False
    clear_player: bool = False
    clear_value: bool = False


def _clean(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="Text fields cannot be blank")
    return cleaned


def _optional_clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


async def _commit(db: AsyncSession, conflict: str) -> None:
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail=conflict) from error


async def _require_manager(db: AsyncSession, manager_id: uuid.UUID) -> Manager:
    manager = await db.get(Manager, manager_id)
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")
    return manager


async def _require_season(db: AsyncSession, season_id: uuid.UUID) -> Season:
    season = await db.get(Season, season_id)
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")
    return season


async def _validate_user_link(db: AsyncSession, user_id: uuid.UUID | None, manager_id: uuid.UUID | None = None) -> None:
    if user_id is None:
        return
    user = await db.get(User, user_id)
    if not user or user.is_deleted:
        raise HTTPException(status_code=422, detail="Linked account was not found")
    existing = await db.scalar(select(Manager).where(Manager.user_id == user_id))
    if existing and existing.id != manager_id:
        raise HTTPException(status_code=409, detail="That account is already linked to another manager")


def _validate_season(platform: SeasonPlatform, league_id: str | None) -> str | None:
    cleaned = _optional_clean(league_id)
    if platform is SeasonPlatform.sleeper and not cleaned:
        raise HTTPException(status_code=422, detail="Sleeper seasons require a league ID")
    if platform is SeasonPlatform.espn and cleaned:
        raise HTTPException(status_code=422, detail="ESPN seasons cannot have a Sleeper league ID")
    return cleaned


async def _snapshot(db: AsyncSession) -> dict:
    users = (await db.scalars(
        select(User).where(User.is_deleted.is_(False)).order_by(User.display_name)
    )).all()
    managers = (await db.scalars(select(Manager).order_by(Manager.is_active.desc(), Manager.display_name))).all()
    aliases = (await db.scalars(select(ManagerAlias).order_by(ManagerAlias.provider, ManagerAlias.external_value))).all()
    seasons = (await db.scalars(select(Season).order_by(Season.year.desc()))).all()
    teams = (await db.scalars(select(SeasonTeam).order_by(SeasonTeam.team_name))).all()
    placements = (await db.scalars(select(SeasonPlacement))).all()
    punishments = (await db.scalars(select(SeasonPunishment))).all()
    facts = (await db.scalars(select(CustomSeasonFact).order_by(CustomSeasonFact.display_order))).all()
    highlights = (await db.scalars(
        select(WeeklyHighlight).where(WeeklyHighlight.source == WeeklyHighlightSource.manual)
        .order_by(WeeklyHighlight.week.desc(), WeeklyHighlight.category)
    )).all()
    import_runs = (await db.scalars(
        select(ImportRun).order_by(ImportRun.started_at.desc()).limit(50)
    )).all()
    aliases_by_manager: dict[uuid.UUID, list[dict]] = {}
    for alias in aliases:
        aliases_by_manager.setdefault(alias.manager_id, []).append({
            "id": alias.id, "provider": alias.provider.value, "external_value": alias.external_value,
        })
    return {
        "users": [
            {"id": user.id, "username": user.username, "display_name": user.display_name, "is_active": user.is_active}
            for user in users
        ],
        "managers": [
            {
                "id": manager.id,
                "user_id": manager.user_id,
                "display_name": manager.display_name,
                "biography": manager.biography,
                "is_active": manager.is_active,
                "aliases": aliases_by_manager.get(manager.id, []),
            }
            for manager in managers
        ],
        "import_runs": [
            {
                "id": run.id,
                "season_id": run.season_id,
                "source": run.source.value,
                "status": run.status.value,
                "counts": run.counts,
                "error_details": run.error_details,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
            }
            for run in import_runs
        ],
        "seasons": [
            {
                "id": season.id,
                "year": season.year,
                "platform": season.platform.value,
                "sleeper_league_id": season.sleeper_league_id,
                "is_active": season.is_active,
                "teams": [
                    {
                        "id": team.id,
                        "manager_id": team.manager_id,
                        "team_name": team.team_name,
                        "sleeper_user_id": team.sleeper_user_id,
                        "roster_id": team.roster_id,
                    }
                    for team in teams if team.season_id == season.id
                ],
                "placements": [
                    {
                        "id": placement.id,
                        "manager_id": placement.manager_id,
                        "calculated_placement": placement.calculated_placement,
                        "override_placement": placement.override_placement,
                    }
                    for placement in placements if placement.season_id == season.id
                ],
                "punishment": next(({
                    "id": punishment.id,
                    "manager_id": punishment.manager_id,
                    "title": punishment.title,
                } for punishment in punishments if punishment.season_id == season.id), None),
                "facts": [
                    {"id": fact.id, "label": fact.label, "value": fact.value, "display_order": fact.display_order}
                    for fact in facts if fact.season_id == season.id
                ],
                "highlights": [
                    {
                        "id": highlight.id,
                        "week": highlight.week,
                        "category": highlight.category,
                        "manager_id": highlight.manager_id,
                        "player_id": highlight.player_id,
                        "player_name": highlight.player_name,
                        "value": highlight.value,
                    }
                    for highlight in highlights if highlight.season_id == season.id
                ],
            }
            for season in seasons
        ],
    }


@admin_router.get("")
async def admin_snapshot(db: AsyncSession = Depends(get_db)):
    return await _snapshot(db)


@admin_router.post("/seasons/{season_id}/sleeper/dry-run")
async def dry_run_sleeper_import(
    season_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    sleeper: SleeperService = Depends(get_sleeper_service),
):
    await _require_season(db, season_id)
    return await import_sleeper_season(db, season_id, dry_run=True, sleeper=sleeper)


@admin_router.post("/seasons/{season_id}/sleeper/import")
async def run_sleeper_import(
    season_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    sleeper: SleeperService = Depends(get_sleeper_service),
):
    await _require_season(db, season_id)
    return await import_sleeper_season(db, season_id, sleeper=sleeper)


@admin_router.post("/sleeper/refresh")
async def refresh_all_sleeper_imports(
    db: AsyncSession = Depends(get_db),
    sleeper: SleeperService = Depends(get_sleeper_service),
):
    return {"results": await refresh_sleeper_seasons(db, sleeper=sleeper)}


@admin_router.post("/notion/dry-run")
async def dry_run_notion_import(
    db: AsyncSession = Depends(get_db),
    notion: NotionClient = Depends(get_notion_client),
):
    try:
        return await import_notion_game_history(db, dry_run=True, notion=notion)
    except NotionConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except NotionAPIError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@admin_router.post("/notion/import")
async def run_notion_import(
    db: AsyncSession = Depends(get_db),
    notion: NotionClient = Depends(get_notion_client),
):
    try:
        return await import_notion_game_history(db, dry_run=False, notion=notion)
    except NotionConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except NotionAPIError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@admin_router.post("/managers", status_code=201)
async def create_manager(body: ManagerCreate, db: AsyncSession = Depends(get_db)):
    await _validate_user_link(db, body.user_id)
    manager = Manager(
        user_id=body.user_id,
        display_name=_clean(body.display_name),
        biography=body.biography.strip(),
        is_active=body.is_active,
    )
    db.add(manager)
    await _commit(db, "That account is already linked to another manager")
    await db.refresh(manager)
    return {"id": manager.id}


@admin_router.patch("/managers/{manager_id}")
async def update_manager(manager_id: uuid.UUID, body: ManagerUpdate, db: AsyncSession = Depends(get_db)):
    manager = await _require_manager(db, manager_id)
    if body.user_id is not None:
        await _validate_user_link(db, body.user_id, manager.id)
        manager.user_id = body.user_id
    elif body.clear_user_link:
        manager.user_id = None
    if body.display_name is not None:
        manager.display_name = _clean(body.display_name)
    if body.biography is not None:
        manager.biography = body.biography.strip()
    if body.is_active is not None:
        manager.is_active = body.is_active
    await _commit(db, "Those manager details conflict with an existing manager")
    return {"id": manager.id}


@admin_router.post("/managers/{manager_id}/aliases", status_code=201)
async def create_alias(manager_id: uuid.UUID, body: AliasCreate, db: AsyncSession = Depends(get_db)):
    await _require_manager(db, manager_id)
    alias = ManagerAlias(manager_id=manager_id, provider=body.provider, external_value=_clean(body.external_value))
    db.add(alias)
    await _commit(db, "That external identity is already assigned")
    await db.refresh(alias)
    return {"id": alias.id}


@admin_router.delete("/aliases/{alias_id}", status_code=204)
async def delete_alias(alias_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    alias = await db.get(ManagerAlias, alias_id)
    if not alias:
        raise HTTPException(status_code=404, detail="Alias not found")
    await db.delete(alias)
    await db.commit()


@admin_router.post("/seasons", status_code=201)
async def create_season(body: SeasonCreate, db: AsyncSession = Depends(get_db)):
    league_id = _validate_season(body.platform, body.sleeper_league_id)
    season = Season(year=body.year, platform=body.platform, sleeper_league_id=league_id, is_active=body.is_active)
    if body.is_active:
        for active in (await db.scalars(select(Season).where(Season.is_active.is_(True)))).all():
            active.is_active = False
    db.add(season)
    await _commit(db, "That year or Sleeper league ID already exists")
    await db.refresh(season)
    return {"id": season.id}


@admin_router.patch("/seasons/{season_id}")
async def update_season(season_id: uuid.UUID, body: SeasonUpdate, db: AsyncSession = Depends(get_db)):
    season = await _require_season(db, season_id)
    platform = body.platform or season.platform
    league_id = season.sleeper_league_id
    if body.sleeper_league_id is not None:
        league_id = body.sleeper_league_id
    elif body.clear_sleeper_league_id:
        league_id = None
    league_id = _validate_season(platform, league_id)
    if body.year is not None:
        season.year = body.year
    season.platform = platform
    season.sleeper_league_id = league_id
    if body.is_active is not None:
        season.is_active = body.is_active
        if body.is_active:
            for active in (await db.scalars(select(Season).where(Season.id != season.id, Season.is_active.is_(True)))).all():
                active.is_active = False
    await _commit(db, "That year or Sleeper league ID already exists")
    return {"id": season.id}


@admin_router.post("/seasons/{season_id}/teams", status_code=201)
async def create_season_team(season_id: uuid.UUID, body: SeasonTeamCreate, db: AsyncSession = Depends(get_db)):
    await _require_season(db, season_id)
    await _require_manager(db, body.manager_id)
    team = SeasonTeam(
        season_id=season_id,
        manager_id=body.manager_id,
        team_name=_clean(body.team_name),
        sleeper_user_id=_optional_clean(body.sleeper_user_id),
        roster_id=body.roster_id,
    )
    db.add(team)
    await _commit(db, "That manager, roster, or Sleeper user is already assigned to this season")
    await db.refresh(team)
    return {"id": team.id}


@admin_router.patch("/season-teams/{team_id}")
async def update_season_team(team_id: uuid.UUID, body: SeasonTeamUpdate, db: AsyncSession = Depends(get_db)):
    team = await db.get(SeasonTeam, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Season team not found")
    if body.manager_id is not None:
        await _require_manager(db, body.manager_id)
        team.manager_id = body.manager_id
    if body.team_name is not None:
        team.team_name = _clean(body.team_name)
    if body.sleeper_user_id is not None:
        team.sleeper_user_id = _optional_clean(body.sleeper_user_id)
    elif body.clear_sleeper_user_id:
        team.sleeper_user_id = None
    if body.roster_id is not None:
        team.roster_id = body.roster_id
    elif body.clear_roster_id:
        team.roster_id = None
    await _commit(db, "That manager, roster, or Sleeper user is already assigned to this season")
    return {"id": team.id}


@admin_router.delete("/season-teams/{team_id}", status_code=204)
async def delete_season_team(team_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    team = await db.get(SeasonTeam, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Season team not found")
    await db.delete(team)
    await db.commit()


@admin_router.put("/seasons/{season_id}/placements/{manager_id}")
async def set_placement(season_id: uuid.UUID, manager_id: uuid.UUID, body: PlacementUpdate, db: AsyncSession = Depends(get_db)):
    await _require_season(db, season_id)
    await _require_manager(db, manager_id)
    placement = await db.scalar(select(SeasonPlacement).where(
        SeasonPlacement.season_id == season_id, SeasonPlacement.manager_id == manager_id,
    ))
    if not placement:
        placement = SeasonPlacement(season_id=season_id, manager_id=manager_id)
        db.add(placement)
    if body.calculated_placement is not None:
        placement.calculated_placement = body.calculated_placement
    if body.override_placement is not None:
        placement.override_placement = body.override_placement
    elif body.clear_override:
        placement.override_placement = None
    if placement.calculated_placement is None and placement.override_placement is None:
        raise HTTPException(status_code=422, detail="Provide a calculated or overridden placement")
    await _commit(db, "That manager already has a placement for this season")
    return {"id": placement.id}


@admin_router.put("/seasons/{season_id}/punishment")
async def set_punishment(season_id: uuid.UUID, body: PunishmentUpdate, db: AsyncSession = Depends(get_db)):
    await _require_season(db, season_id)
    await _require_manager(db, body.manager_id)
    punishment = await db.scalar(select(SeasonPunishment).where(SeasonPunishment.season_id == season_id))
    if not punishment:
        punishment = SeasonPunishment(season_id=season_id, manager_id=body.manager_id, title=_clean(body.title))
        db.add(punishment)
    else:
        punishment.manager_id = body.manager_id
        punishment.title = _clean(body.title)
    await db.commit()
    await db.refresh(punishment)
    return {"id": punishment.id}


@admin_router.delete("/seasons/{season_id}/punishment", status_code=204)
async def delete_punishment(season_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(delete(SeasonPunishment).where(SeasonPunishment.season_id == season_id))
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Punishment not found")
    await db.commit()


@admin_router.post("/seasons/{season_id}/facts", status_code=201)
async def create_fact(season_id: uuid.UUID, body: FactCreate, db: AsyncSession = Depends(get_db)):
    await _require_season(db, season_id)
    fact = CustomSeasonFact(
        season_id=season_id, label=_clean(body.label), value=_clean(body.value), display_order=body.display_order,
    )
    db.add(fact)
    await _commit(db, "That display order is already used in this season")
    await db.refresh(fact)
    return {"id": fact.id}


@admin_router.patch("/facts/{fact_id}")
async def update_fact(fact_id: uuid.UUID, body: FactUpdate, db: AsyncSession = Depends(get_db)):
    fact = await db.get(CustomSeasonFact, fact_id)
    if not fact:
        raise HTTPException(status_code=404, detail="Season fact not found")
    if body.label is not None:
        fact.label = _clean(body.label)
    if body.value is not None:
        fact.value = _clean(body.value)
    if body.display_order is not None:
        fact.display_order = body.display_order
    await _commit(db, "That display order is already used in this season")
    return {"id": fact.id}


@admin_router.delete("/facts/{fact_id}", status_code=204)
async def delete_fact(fact_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    fact = await db.get(CustomSeasonFact, fact_id)
    if not fact:
        raise HTTPException(status_code=404, detail="Season fact not found")
    await db.delete(fact)
    await db.commit()


@admin_router.post("/seasons/{season_id}/highlights", status_code=201)
async def create_highlight(season_id: uuid.UUID, body: HighlightCreate, db: AsyncSession = Depends(get_db)):
    await _require_season(db, season_id)
    if body.manager_id:
        await _require_manager(db, body.manager_id)
    highlight = WeeklyHighlight(
        season_id=season_id,
        week=body.week,
        category=_clean(body.category),
        source_key=f"manual:{uuid.uuid4()}",
        manager_id=body.manager_id,
        player_id=_optional_clean(body.player_id),
        player_name=_optional_clean(body.player_name),
        value=body.value,
        source=WeeklyHighlightSource.manual,
    )
    db.add(highlight)
    await db.commit()
    await db.refresh(highlight)
    return {"id": highlight.id}


@admin_router.patch("/highlights/{highlight_id}")
async def update_highlight(highlight_id: uuid.UUID, body: HighlightUpdate, db: AsyncSession = Depends(get_db)):
    highlight = await db.get(WeeklyHighlight, highlight_id)
    if not highlight or highlight.source is not WeeklyHighlightSource.manual:
        raise HTTPException(status_code=404, detail="Manual highlight not found")
    if body.week is not None:
        highlight.week = body.week
    if body.category is not None:
        highlight.category = _clean(body.category)
    if body.manager_id is not None:
        await _require_manager(db, body.manager_id)
        highlight.manager_id = body.manager_id
    elif body.clear_manager:
        highlight.manager_id = None
    if body.clear_player:
        highlight.player_id = None
        highlight.player_name = None
    else:
        if body.player_id is not None:
            highlight.player_id = _optional_clean(body.player_id)
        if body.player_name is not None:
            highlight.player_name = _optional_clean(body.player_name)
    if body.value is not None:
        highlight.value = body.value
    elif body.clear_value:
        highlight.value = None
    await db.commit()
    return {"id": highlight.id}


@admin_router.delete("/highlights/{highlight_id}", status_code=204)
async def delete_highlight(highlight_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    highlight = await db.get(WeeklyHighlight, highlight_id)
    if not highlight or highlight.source is not WeeklyHighlightSource.manual:
        raise HTTPException(status_code=404, detail="Manual highlight not found")
    await db.delete(highlight)
    await db.commit()


@router.get("/me")
async def manager_self(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    manager = await db.scalar(select(Manager).where(Manager.user_id == user.id))
    return {
        "manager": None if not manager else {
            "id": manager.id,
            "display_name": manager.display_name,
            "biography": manager.biography,
        }
    }


@router.patch("/me/biography")
async def update_own_biography(
    body: BiographyUpdate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    manager = await db.scalar(select(Manager).where(Manager.user_id == user.id))
    if not manager:
        raise HTTPException(status_code=404, detail="Your account is not linked to a manager profile")
    manager.biography = body.biography.strip()
    await db.commit()
    return {"id": manager.id, "biography": manager.biography}
