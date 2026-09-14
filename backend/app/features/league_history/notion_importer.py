import hashlib
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.league_history.models import (
    HistorySource,
    ImportRun,
    ImportRunStatus,
    LeagueMatchup,
    Manager,
    ManagerAlias,
    ManagerAliasProvider,
    SeasonTeam,
)
from app.models.season import Season, SeasonPlatform
from app.services.notion import NotionClient


SUPPORTED_YEARS = (2020, 2021)


@dataclass(frozen=True)
class NotionGame:
    page_id: str
    year: int
    week: int
    week_end: int | None
    week_label: str
    team_a_name: str
    score_a: float
    team_b_name: str
    score_b: float
    winner: str
    was_ptgotw: bool


def _rich_text(value: object) -> str:
    if not isinstance(value, list):
        return ""
    pieces = []
    for item in value:
        if not isinstance(item, dict):
            continue
        plain = item.get("plain_text")
        if plain is None:
            plain = (item.get("text") or {}).get("content")
        if plain is not None:
            pieces.append(str(plain))
    return "".join(pieces).strip()


def _property(page: dict, name: str) -> object:
    prop = (page.get("properties") or {}).get(name)
    if not isinstance(prop, dict):
        return None
    prop_type = prop.get("type")
    if prop_type in ("title", "rich_text"):
        return _rich_text(prop.get(str(prop_type)))
    if prop_type in ("number", "checkbox"):
        return prop.get(str(prop_type))
    # The historical schema is fixed, but accepting the expected keys makes
    # test fixtures and older page responses easier to diagnose.
    for key in ("title", "rich_text", "number", "checkbox"):
        if key in prop:
            return _rich_text(prop[key]) if key in ("title", "rich_text") else prop[key]
    return None


def _normalize_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _parse_week(value: object) -> tuple[int, int | None] | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and float(value).is_integer():
        week = int(value)
        return week, None
    if isinstance(value, str):
        match = re.fullmatch(r"\s*(?:week\s*)?(\d{1,2})\s*", value, re.IGNORECASE)
        if match:
            return int(match.group(1)), None
        # The ESPN seasons used two-week playoff rounds. Accept both their
        # descriptive Notion titles (for example, "PR2 - W16-17 - Loser")
        # and temporary compact values such as "1617".
        match = re.search(r"\b(?:w|week)\s*(\d{1,2})\s*[-\u2013\u2014]\s*(\d{1,2})\b", value, re.IGNORECASE)
        if not match:
            match = re.fullmatch(r"\s*(\d{2})(\d{2})\s*", value)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            if 1 <= start < end <= 18:
                return start, end
    return None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0 else None


def _parse_page(page: dict) -> tuple[NotionGame | None, list[str]]:
    page_id = str(page.get("id") or "unknown")
    raw_year = _property(page, "Year")
    year = int(raw_year) if isinstance(raw_year, (int, float)) and not isinstance(raw_year, bool) and float(raw_year).is_integer() else None
    raw_week = _property(page, "Week")
    parsed_week = _parse_week(raw_week)
    week, week_end = parsed_week or (None, None)
    team_a = str(_property(page, "Team1Name") or "").strip()
    team_b = str(_property(page, "Team2Name") or "").strip()
    score_a = _number(_property(page, "Team1Score"))
    score_b = _number(_property(page, "Team2Score"))
    errors = []
    if year not in SUPPORTED_YEARS:
        errors.append("Year must be 2020 or 2021")
    if week is None or not 1 <= week <= 18:
        errors.append("Week must be 1 through 18 or a range such as W16-17")
    if not team_a or len(team_a) > 120:
        errors.append("Team1Name is missing or longer than 120 characters")
    if not team_b or len(team_b) > 120:
        errors.append("Team2Name is missing or longer than 120 characters")
    if team_a and team_b and _normalize_name(team_a) == _normalize_name(team_b):
        errors.append("A matchup must contain two different names")
    if score_a is None:
        errors.append("Team1Score must be a non-negative number")
    if score_b is None:
        errors.append("Team2Score must be a non-negative number")
    if errors:
        return None, errors
    return NotionGame(
        page_id=page_id,
        year=year,  # type: ignore[arg-type]
        week=week,  # type: ignore[arg-type]
        week_end=week_end,
        week_label=str(raw_week or "").strip(),
        team_a_name=team_a,
        score_a=score_a,  # type: ignore[arg-type]
        team_b_name=team_b,
        score_b=score_b,  # type: ignore[arg-type]
        winner=str(_property(page, "Winner") or "").strip(),
        was_ptgotw=bool(_property(page, "WasPTGOTW")),
    ), []


def _signature(game: NotionGame) -> tuple[int, int, int | None, str, str]:
    names = sorted((_normalize_name(game.team_a_name), _normalize_name(game.team_b_name)))
    return game.year, game.week, game.week_end, names[0], names[1]


def _source_key(game: NotionGame, manager_a: uuid.UUID, manager_b: uuid.UUID) -> str:
    manager_ids = sorted((str(manager_a), str(manager_b)))
    week_key = str(game.week) if game.week_end is None else f"{game.week}-{game.week_end}"
    encoded = f"{game.year}|{week_key}|{manager_ids[0]}|{manager_ids[1]}".encode("utf-8")
    return f"game:{hashlib.sha256(encoded).hexdigest()}"


async def _finish(
    db: AsyncSession,
    run_id: uuid.UUID,
    status: ImportRunStatus,
    counts: dict[str, Any],
    error: str | None = None,
) -> None:
    run = await db.get(ImportRun, run_id)
    if run:
        run.status = status
        run.counts = counts
        run.error_details = error
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()


async def import_notion_game_history(
    db: AsyncSession,
    *,
    dry_run: bool,
    notion: NotionClient | None = None,
) -> dict[str, Any]:
    run = ImportRun(
        source=HistorySource.notion,
        status=ImportRunStatus.running,
        counts={"mode": "dry_run" if dry_run else "import"},
    )
    db.add(run)
    await db.commit()
    run_id = run.id
    report: dict[str, Any] = {
        "mode": "dry_run" if dry_run else "import",
        "rows_per_season": {str(year): 0 for year in SUPPORTED_YEARS},
        "resolved_manager_aliases": [],
        "unresolved_names": [],
        "duplicate_rows": [],
        "invalid_records": [],
        "skipped_out_of_scope": [],
        "records_to_insert": {str(year): 0 for year in SUPPORTED_YEARS},
        "records_to_update": {str(year): 0 for year in SUPPORTED_YEARS},
    }
    try:
        pages = await (notion or NotionClient()).query_game_history()
        games: list[NotionGame] = []
        for page in pages:
            raw_year = _property(page, "Year")
            if (
                isinstance(raw_year, (int, float))
                and not isinstance(raw_year, bool)
                and float(raw_year).is_integer()
                and int(raw_year) not in SUPPORTED_YEARS
            ):
                report["skipped_out_of_scope"].append({
                    "page_id": str(page.get("id") or "unknown"),
                    "year": int(raw_year),
                })
                continue
            if raw_year in SUPPORTED_YEARS:
                report["rows_per_season"][str(int(raw_year))] += 1
            game, errors = _parse_page(page)
            if errors:
                report["invalid_records"].append({"page_id": str(page.get("id") or "unknown"), "errors": errors})
            elif game:
                games.append(game)

        unique_games: list[NotionGame] = []
        first_by_signature: dict[tuple[int, int, int | None, str, str], NotionGame] = {}
        for game in games:
            signature = _signature(game)
            first = first_by_signature.get(signature)
            if first:
                report["duplicate_rows"].append({
                    "year": game.year,
                    "week": game.week,
                    "week_end": game.week_end,
                    "first_page_id": first.page_id,
                    "duplicate_page_id": game.page_id,
                })
            else:
                first_by_signature[signature] = game
                unique_games.append(game)

        aliases = (await db.scalars(select(ManagerAlias).where(
            ManagerAlias.provider == ManagerAliasProvider.notion_name
        ))).all()
        managers = (await db.scalars(select(Manager))).all()
        manager_names = {manager.id: manager.display_name for manager in managers}
        manager_by_name: dict[str, uuid.UUID] = {}
        ambiguous_names: set[str] = set()
        alias_display: dict[str, str] = {}
        for alias in aliases:
            normalized = _normalize_name(alias.external_value)
            if normalized in manager_by_name and manager_by_name[normalized] != alias.manager_id:
                ambiguous_names.add(normalized)
            else:
                manager_by_name[normalized] = alias.manager_id
                alias_display[normalized] = alias.external_value

        used_names = sorted({name for game in unique_games for name in (game.team_a_name, game.team_b_name)}, key=str.casefold)
        unresolved = []
        for name in used_names:
            normalized = _normalize_name(name)
            manager_id = manager_by_name.get(normalized)
            if not manager_id or normalized in ambiguous_names:
                unresolved.append(name)
            else:
                report["resolved_manager_aliases"].append({
                    "source_name": name,
                    "alias": alias_display[normalized],
                    "manager_id": str(manager_id),
                    "manager_name": manager_names.get(manager_id, "Unknown manager"),
                })
        report["unresolved_names"] = unresolved

        seasons = (await db.scalars(select(Season).where(Season.year.in_(SUPPORTED_YEARS)))).all()
        season_by_year = {season.year: season for season in seasons}
        for year in SUPPORTED_YEARS:
            season = season_by_year.get(year)
            if not season:
                report["invalid_records"].append({"season": year, "errors": ["ESPN season is not configured"]})
            elif season.platform is not SeasonPlatform.espn:
                report["invalid_records"].append({"season": year, "errors": ["Season must use the ESPN platform"]})

        existing = (await db.scalars(select(LeagueMatchup).where(
            LeagueMatchup.source == HistorySource.notion
        ))).all()
        existing_by_key = {(item.season_id, item.source_key): item for item in existing}
        resolved_games: list[tuple[NotionGame, uuid.UUID, uuid.UUID]] = []
        first_by_managers: dict[tuple[int, int, int | None, str, str], NotionGame] = {}
        for game in unique_games:
            manager_a = manager_by_name.get(_normalize_name(game.team_a_name))
            manager_b = manager_by_name.get(_normalize_name(game.team_b_name))
            season = season_by_year.get(game.year)
            if not manager_a or not manager_b or not season or season.platform is not SeasonPlatform.espn:
                continue
            if manager_a == manager_b:
                report["invalid_records"].append({
                    "page_id": game.page_id,
                    "errors": ["Both names resolve to the same manager"],
                })
                continue
            manager_ids = sorted((str(manager_a), str(manager_b)))
            manager_signature = (game.year, game.week, game.week_end, manager_ids[0], manager_ids[1])
            first = first_by_managers.get(manager_signature)
            if first:
                report["duplicate_rows"].append({
                    "year": game.year,
                    "week": game.week,
                    "week_end": game.week_end,
                    "first_page_id": first.page_id,
                    "duplicate_page_id": game.page_id,
                })
                continue
            first_by_managers[manager_signature] = game
            resolved_games.append((game, manager_a, manager_b))
            key = _source_key(game, manager_a, manager_b)
            bucket = "records_to_update" if (season.id, key) in existing_by_key else "records_to_insert"
            report[bucket][str(game.year)] += 1

        needs_attention = bool(
            report["unresolved_names"] or report["duplicate_rows"] or report["invalid_records"]
        )
        if needs_attention:
            await _finish(db, run_id, ImportRunStatus.needs_attention, report, "Notion data requires attention")
            return {"run_id": run_id, "status": ImportRunStatus.needs_attention.value, **report}
        if dry_run:
            await _finish(db, run_id, ImportRunStatus.succeeded, report)
            return {"run_id": run_id, "status": ImportRunStatus.succeeded.value, **report}

        team_names: dict[tuple[uuid.UUID, uuid.UUID], str] = {}
        for game, manager_a, manager_b in resolved_games:
            season = season_by_year[game.year]
            team_names.setdefault((season.id, manager_a), game.team_a_name)
            team_names.setdefault((season.id, manager_b), game.team_b_name)
        existing_teams = (await db.scalars(select(SeasonTeam).where(
            SeasonTeam.season_id.in_([season.id for season in seasons])
        ))).all()
        team_by_key = {(team.season_id, team.manager_id): team for team in existing_teams}
        for (season_id, manager_id), name in team_names.items():
            team = team_by_key.get((season_id, manager_id))
            if not team:
                team = SeasonTeam(season_id=season_id, manager_id=manager_id, team_name=name)
                db.add(team)
            else:
                team.team_name = name

        for game, manager_a, manager_b in resolved_games:
            season = season_by_year[game.year]
            source_key = _source_key(game, manager_a, manager_b)
            matchup = existing_by_key.get((season.id, source_key))
            if not matchup:
                matchup = LeagueMatchup(
                    season_id=season.id,
                    source=HistorySource.notion,
                    source_key=source_key,
                )
                db.add(matchup)
            matchup.week = game.week
            matchup.manager_a_id = manager_a
            matchup.manager_b_id = manager_b
            matchup.team_a_name = game.team_a_name
            matchup.team_b_name = game.team_b_name
            matchup.score_a = game.score_a
            matchup.score_b = game.score_b
            matchup.sleeper_matchup_id = None
            matchup.source_metadata = {
                "notion_page_id": game.page_id,
                "winner": game.winner,
                "was_ptgotw": game.was_ptgotw,
                "week_end": game.week_end,
                "week_label": game.week_label,
            }

        await _finish(db, run_id, ImportRunStatus.succeeded, report)
        return {"run_id": run_id, "status": ImportRunStatus.succeeded.value, **report}
    except Exception as error:
        await db.rollback()
        report["exception_type"] = type(error).__name__
        await _finish(db, run_id, ImportRunStatus.failed, report, str(error))
        raise
