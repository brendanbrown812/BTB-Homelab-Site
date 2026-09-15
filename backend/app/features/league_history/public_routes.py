import uuid
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.database.session import get_db
from app.features.league_history.models import (
    CustomSeasonFact,
    LeagueMatchup,
    LeagueTransaction,
    LeagueTransactionDraftPick,
    LeagueTransactionFaab,
    LeagueTransactionParticipant,
    LeagueTransactionPlayer,
    Manager,
    SeasonPlacement,
    SeasonPunishment,
    SeasonTeam,
    WeeklyHighlight,
)
from app.features.league_history.statistics import (
    HighlightCandidate,
    HistoryMatchup,
    HistoryPlacement,
    HistoryTransaction,
    calculate_records,
    calculate_weekly_highlights,
    merge_weekly_highlights,
)
from app.models.season import Season, SeasonPlatform
from app.models.user import User
from app.services.sleeper import SleeperPlayer, SleeperService


router = APIRouter(
    prefix="/league-history",
    tags=["league history"],
    dependencies=[Depends(current_user)],
)


def get_public_sleeper_service() -> SleeperService:
    return SleeperService()


def _effective_placement(placement: SeasonPlacement | None) -> tuple[int | None, str]:
    if placement and placement.override_placement is not None:
        return placement.override_placement, "overridden"
    if placement and placement.calculated_placement is not None:
        return placement.calculated_placement, "calculated"
    return None, "unavailable"


def _stat_matchups(
    matchups: list[LeagueMatchup], seasons: dict[uuid.UUID, Season], managers: dict[uuid.UUID, Manager]
) -> list[HistoryMatchup]:
    rows = []
    for matchup in matchups:
        season = seasons.get(matchup.season_id)
        manager_a = managers.get(matchup.manager_a_id)
        manager_b = managers.get(matchup.manager_b_id)
        if not season or not manager_a or not manager_b:
            continue
        rows.append(HistoryMatchup(
            matchup.season_id, season.year, matchup.week,
            matchup.manager_a_id, manager_a.display_name, matchup.team_a_name, matchup.score_a,
            matchup.manager_b_id, manager_b.display_name, matchup.team_b_name, matchup.score_b,
            matchup.source_metadata,
        ))
    return rows


def _records(matchups: list[LeagueMatchup], manager_ids: set[uuid.UUID]) -> dict[uuid.UUID, dict]:
    result = {
        manager_id: {"wins": 0, "losses": 0, "ties": 0, "points_for": 0.0, "points_against": 0.0}
        for manager_id in manager_ids
    }
    for matchup in matchups:
        if matchup.score_a is None or matchup.score_b is None:
            continue
        for manager_id in (matchup.manager_a_id, matchup.manager_b_id):
            result.setdefault(manager_id, {"wins": 0, "losses": 0, "ties": 0, "points_for": 0.0, "points_against": 0.0})
        a = result[matchup.manager_a_id]
        b = result[matchup.manager_b_id]
        a["points_for"] += matchup.score_a
        a["points_against"] += matchup.score_b
        b["points_for"] += matchup.score_b
        b["points_against"] += matchup.score_a
        if matchup.score_a > matchup.score_b:
            a["wins"] += 1
            b["losses"] += 1
        elif matchup.score_b > matchup.score_a:
            b["wins"] += 1
            a["losses"] += 1
        else:
            a["ties"] += 1
            b["ties"] += 1
    for record in result.values():
        record["points_for"] = round(record["points_for"], 2)
        record["points_against"] = round(record["points_against"], 2)
    return result


async def _history_rows(db: AsyncSession):
    managers = (await db.scalars(select(Manager).order_by(Manager.is_active.desc(), Manager.display_name))).all()
    seasons = (await db.scalars(select(Season).where(Season.year >= 2020).order_by(Season.year))).all()
    teams = (await db.scalars(select(SeasonTeam))).all()
    placements = (await db.scalars(select(SeasonPlacement))).all()
    matchups = (await db.scalars(select(LeagueMatchup))).all()
    punishments = (await db.scalars(select(SeasonPunishment))).all()
    participants = (await db.scalars(select(LeagueTransactionParticipant))).all()
    transactions = (await db.scalars(select(LeagueTransaction))).all()
    return managers, seasons, teams, placements, matchups, punishments, participants, transactions


@router.get("/teams")
async def public_teams(db: AsyncSession = Depends(get_db)):
    managers, seasons, teams, placements, matchups, punishments, participants, transactions = await _history_rows(db)
    season_by_id = {season.id: season for season in seasons}
    placement_by_key = {(item.season_id, item.manager_id): item for item in placements}
    team_counts = Counter(team.season_id for team in teams)
    records = _records(list(matchups), {manager.id for manager in managers})
    transaction_by_id = {item.id: item for item in transactions}
    transaction_ids_by_manager: dict[uuid.UUID, set[uuid.UUID]] = {}
    for participant in participants:
        transaction_ids_by_manager.setdefault(participant.manager_id, set()).add(participant.transaction_id)
    punishment_counts = Counter(item.manager_id for item in punishments)
    items = []
    for manager in managers:
        manager_teams = sorted(
            (team for team in teams if team.manager_id == manager.id and team.season_id in season_by_id),
            key=lambda team: season_by_id[team.season_id].year,
        )
        championships = sum(
            _effective_placement(placement_by_key.get((team.season_id, manager.id)))[0] == 1
            for team in manager_teams
        )
        biggest_losers = sum(
            _effective_placement(placement_by_key.get((team.season_id, manager.id)))[0] == team_counts[team.season_id]
            for team in manager_teams
        )
        transaction_ids = transaction_ids_by_manager.get(manager.id, set())
        items.append({
            "id": manager.id,
            "display_name": manager.display_name,
            "biography": manager.biography,
            "is_active": manager.is_active,
            "seasons_played": len(manager_teams),
            "championships": championships,
            "biggest_losers": biggest_losers,
            "team_names": list(dict.fromkeys(team.team_name for team in manager_teams)),
            "latest_team_name": manager_teams[-1].team_name if manager_teams else None,
            "career": records[manager.id],
            "transaction_total": sum(1 for value in transaction_ids if value in transaction_by_id),
            "punishment_total": punishment_counts[manager.id],
        })
    return {"managers": items}


@router.get("/head-to-head")
async def public_head_to_head(
    manager_a_id: uuid.UUID | None = None,
    manager_b_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    managers = list((await db.scalars(
        select(Manager).order_by(Manager.is_active.desc(), Manager.display_name)
    )).all())
    manager_options = [{
        "id": manager.id,
        "display_name": manager.display_name,
        "is_active": manager.is_active,
    } for manager in managers]
    if manager_a_id is None and manager_b_id is None:
        return {"managers": manager_options, "comparison": None}
    if manager_a_id is None or manager_b_id is None:
        raise HTTPException(status_code=422, detail="Select two managers")
    if manager_a_id == manager_b_id:
        raise HTTPException(status_code=422, detail="Select two different managers")

    manager_by_id = {manager.id: manager for manager in managers}
    manager_a = manager_by_id.get(manager_a_id)
    manager_b = manager_by_id.get(manager_b_id)
    if not manager_a or not manager_b:
        raise HTTPException(status_code=404, detail="Manager not found")

    matchups = list((await db.scalars(select(LeagueMatchup).where(or_(
        and_(LeagueMatchup.manager_a_id == manager_a_id, LeagueMatchup.manager_b_id == manager_b_id),
        and_(LeagueMatchup.manager_a_id == manager_b_id, LeagueMatchup.manager_b_id == manager_a_id),
    )))).all())
    seasons = list((await db.scalars(select(Season).where(
        Season.id.in_({matchup.season_id for matchup in matchups})
    ))).all()) if matchups else []
    season_by_id = {season.id: season for season in seasons}

    games = []
    wins_a = wins_b = ties = 0
    points_a = points_b = 0.0
    for matchup in matchups:
        metadata = matchup.source_metadata or {}
        if matchup.score_a is None or matchup.score_b is None or metadata.get("is_complete") is False:
            continue
        season = season_by_id.get(matchup.season_id)
        if not season:
            continue
        selected_a_is_stored_a = matchup.manager_a_id == manager_a_id
        score_a = matchup.score_a if selected_a_is_stored_a else matchup.score_b
        score_b = matchup.score_b if selected_a_is_stored_a else matchup.score_a
        team_a_name = matchup.team_a_name if selected_a_is_stored_a else matchup.team_b_name
        team_b_name = matchup.team_b_name if selected_a_is_stored_a else matchup.team_a_name
        points_a += score_a
        points_b += score_b
        winner_id = None
        if score_a > score_b:
            wins_a += 1
            winner_id = manager_a_id
        elif score_b > score_a:
            wins_b += 1
            winner_id = manager_b_id
        else:
            ties += 1
        games.append({
            "id": matchup.id,
            "season_id": season.id,
            "year": season.year,
            "week": matchup.week,
            "week_end": metadata.get("week_end"),
            "team_a_name": team_a_name,
            "team_b_name": team_b_name,
            "score_a": round(score_a, 2),
            "score_b": round(score_b, 2),
            "winner_id": winner_id,
            "margin": round(abs(score_a - score_b), 2),
            "source": matchup.source.value,
        })
    games.sort(key=lambda game: (game["year"], game["week"], game["id"]), reverse=True)
    game_count = len(games)
    return {
        "managers": manager_options,
        "comparison": {
            "manager_a": {
                "id": manager_a.id,
                "display_name": manager_a.display_name,
                "wins": wins_a,
                "points_for": round(points_a, 2),
                "average_score": round(points_a / game_count, 2) if game_count else 0,
            },
            "manager_b": {
                "id": manager_b.id,
                "display_name": manager_b.display_name,
                "wins": wins_b,
                "points_for": round(points_b, 2),
                "average_score": round(points_b / game_count, 2) if game_count else 0,
            },
            "ties": ties,
            "total_matchups": game_count,
            "games": games,
        },
    }


def _player(player: SleeperPlayer) -> dict:
    return {
        "player_id": player.player_id,
        "name": player.name,
        "position": player.position,
        "team": player.team,
        "injury_status": player.injury_status,
        "points": player.points,
        "image_url": player.image_url,
    }


def _transaction_player(player: LeagueTransactionPlayer, catalog: dict[str, SleeperPlayer]) -> dict:
    details = catalog.get(player.player_id)
    return {
        "player_id": player.player_id,
        "name": details.name if details else player.player_name or f"Player {player.player_id}",
        "position": details.position if details else None,
        "team": details.team if details else None,
        "image_url": details.image_url if details else None,
    }


async def _transaction_rows(
    db: AsyncSession,
    sleeper: SleeperService,
    *,
    transaction_types: set[str],
    season: int | None,
    manager_id: uuid.UUID | None,
    player: str | None,
    status: str | None = None,
    transaction_type: str | None = None,
) -> dict:
    """Shape imported transactions without loading a historical Sleeper archive."""
    seasons = (await db.scalars(select(Season).where(Season.year >= 2020).order_by(Season.year.desc()))).all()
    season_by_id = {item.id: item for item in seasons}
    managers = (await db.scalars(select(Manager).order_by(Manager.display_name))).all()
    manager_by_id = {item.id: item for item in managers}
    transactions = list((await db.scalars(select(LeagueTransaction).order_by(
        LeagueTransaction.occurred_at.desc(), LeagueTransaction.external_id
    ))).all())
    eligible = [
        item for item in transactions
        if item.season_id in season_by_id and item.transaction_type in transaction_types
    ]
    eligible_ids = {item.id for item in eligible}
    participants = list((await db.scalars(select(LeagueTransactionParticipant).where(
        LeagueTransactionParticipant.transaction_id.in_(eligible_ids)
    ))).all()) if eligible_ids else []
    players = list((await db.scalars(select(LeagueTransactionPlayer).where(
        LeagueTransactionPlayer.transaction_id.in_(eligible_ids)
    ))).all()) if eligible_ids else []
    picks = list((await db.scalars(select(LeagueTransactionDraftPick).where(
        LeagueTransactionDraftPick.transaction_id.in_(eligible_ids)
    ))).all()) if eligible_ids else []
    faab = list((await db.scalars(select(LeagueTransactionFaab).where(
        LeagueTransactionFaab.transaction_id.in_(eligible_ids)
    ))).all()) if eligible_ids else []

    player_ids = {item.player_id for item in players}
    catalog: dict[str, SleeperPlayer] = {}
    if player_ids:
        try:
            catalog = await sleeper.player_lookup(player_ids)
        except Exception:
            # Imports persist names, so a catalog outage should not take history offline.
            catalog = {}

    participants_by_transaction: dict[uuid.UUID, list[LeagueTransactionParticipant]] = {}
    players_by_transaction: dict[uuid.UUID, list[LeagueTransactionPlayer]] = {}
    picks_by_transaction: dict[uuid.UUID, list[LeagueTransactionDraftPick]] = {}
    faab_by_transaction: dict[uuid.UUID, list[LeagueTransactionFaab]] = {}
    for item in participants:
        participants_by_transaction.setdefault(item.transaction_id, []).append(item)
    for item in players:
        players_by_transaction.setdefault(item.transaction_id, []).append(item)
    for item in picks:
        picks_by_transaction.setdefault(item.transaction_id, []).append(item)
    for item in faab:
        faab_by_transaction.setdefault(item.transaction_id, []).append(item)

    def involved_participants(transaction: LeagueTransaction) -> list[LeagueTransactionParticipant]:
        """Exclude a draft pick's original franchise unless it actually moved an asset."""
        all_rows = participants_by_transaction.get(transaction.id, [])
        roster_ids = {
            int(value) for value in ((transaction.raw_payload or {}).get("roster_ids") or [])
            if value not in (None, 0)
        }
        roster_ids.update(row.roster_id for row in players_by_transaction.get(transaction.id, []))
        for pick in picks_by_transaction.get(transaction.id, []):
            roster_ids.update((pick.previous_owner_roster_id, pick.new_owner_roster_id))
        for transfer in faab_by_transaction.get(transaction.id, []):
            roster_ids.update(value for value in (transfer.sender_roster_id, transfer.receiver_roster_id) if value != 0)
        selected = [row for row in all_rows if row.roster_id in roster_ids]
        return selected or all_rows

    player_query = player.strip().casefold() if player else None
    filtered = []
    for item in eligible:
        item_participants = involved_participants(item)
        item_players = players_by_transaction.get(item.id, [])
        if season is not None and season_by_id[item.season_id].year != season:
            continue
        if manager_id is not None and all(row.manager_id != manager_id for row in item_participants):
            continue
        if transaction_type is not None and item.transaction_type != transaction_type:
            continue
        if status is not None and item.status != status:
            continue
        if player_query and not any(
            player_query in _transaction_player(row, catalog)["name"].casefold()
            or player_query in row.player_id.casefold()
            for row in item_players
        ):
            continue
        filtered.append(item)

    def manager_for_roster(rows: list[LeagueTransactionParticipant], roster_id: int) -> Manager | None:
        participant = next((row for row in rows if row.roster_id == roster_id), None)
        return manager_by_id.get(participant.manager_id) if participant else None

    def manager_name_for_roster(rows: list[LeagueTransactionParticipant], roster_id: int) -> str:
        manager = manager_for_roster(rows, roster_id)
        return manager.display_name if manager else f"Roster {roster_id}"

    items = []
    for item in filtered:
        item_participants = sorted(
            involved_participants(item),
            key=lambda row: manager_by_id.get(row.manager_id).display_name if manager_by_id.get(row.manager_id) else "",
        )
        item_players = players_by_transaction.get(item.id, [])
        item_picks = picks_by_transaction.get(item.id, [])
        item_faab = faab_by_transaction.get(item.id, [])
        sides = []
        for participant in item_participants:
            manager = manager_by_id.get(participant.manager_id)
            received_picks = [pick for pick in item_picks if pick.new_owner_roster_id == participant.roster_id]
            sent_picks = [pick for pick in item_picks if pick.previous_owner_roster_id == participant.roster_id]
            sides.append({
                "manager_id": participant.manager_id,
                "manager_name": manager.display_name if manager else "Unknown manager",
                "roster_id": participant.roster_id,
                "adds": [_transaction_player(row, catalog) for row in item_players if row.roster_id == participant.roster_id and row.movement.value == "add"],
                "drops": [_transaction_player(row, catalog) for row in item_players if row.roster_id == participant.roster_id and row.movement.value == "drop"],
                "draft_picks_received": [{
                    "season": pick.pick_season,
                    "round": pick.round,
                    "original_roster_id": pick.original_roster_id,
                    "original_manager_name": manager_name_for_roster(
                        participants_by_transaction.get(item.id, []), pick.original_roster_id
                    ),
                } for pick in received_picks],
                "draft_picks_sent": [{"season": pick.pick_season, "round": pick.round} for pick in sent_picks],
                "faab_received": sum(row.amount for row in item_faab if row.receiver_roster_id == participant.roster_id),
                "faab_sent": sum(row.amount for row in item_faab if row.sender_roster_id == participant.roster_id),
            })
        items.append({
            "id": item.id,
            "external_id": item.external_id,
            "season": season_by_id[item.season_id].year,
            "week": item.week,
            "transaction_type": item.transaction_type,
            "status": item.status,
            "occurred_at": item.occurred_at,
            "participants": [{
                "manager_id": row.manager_id,
                "manager_name": manager_by_id[row.manager_id].display_name if row.manager_id in manager_by_id else "Unknown manager",
                "roster_id": row.roster_id,
            } for row in item_participants],
            "sides": sides,
            "adds": [_transaction_player(row, catalog) for row in item_players if row.movement.value == "add"],
            "drops": [_transaction_player(row, catalog) for row in item_players if row.movement.value == "drop"],
            "bid_amount": (
                sum(row.amount for row in item_faab if row.receiver_roster_id == 0)
                if any(row.receiver_roster_id == 0 for row in item_faab)
                else None
            ),
        })
    return {
        "items": items,
        "options": {
            "seasons": [item.year for item in seasons],
            "managers": [{"id": item.id, "display_name": item.display_name} for item in managers],
            "transaction_types": sorted({item.transaction_type for item in eligible}),
            "statuses": sorted({item.status for item in eligible}),
        },
    }


@router.get("/trades")
async def public_trades(
    season: int | None = Query(default=None, ge=2020),
    manager_id: uuid.UUID | None = None,
    player: str | None = Query(default=None, max_length=160),
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    sleeper: SleeperService = Depends(get_public_sleeper_service),
):
    return await _transaction_rows(
        db, sleeper, transaction_types={"trade"}, season=season, manager_id=manager_id, player=player,
        status=status,
    )


@router.get("/waivers")
async def public_waivers(
    season: int | None = Query(default=None, ge=2020),
    manager_id: uuid.UUID | None = None,
    player: str | None = Query(default=None, max_length=160),
    transaction_type: str | None = Query(default=None, max_length=40),
    status: str | None = Query(default=None, max_length=40),
    db: AsyncSession = Depends(get_db),
    sleeper: SleeperService = Depends(get_public_sleeper_service),
):
    return await _transaction_rows(
        db,
        sleeper,
        transaction_types={"waiver", "free_agent"},
        season=season,
        manager_id=manager_id,
        player=player,
        status=status,
        transaction_type=transaction_type,
    )


@router.get("/records")
async def public_records(db: AsyncSession = Depends(get_db)):
    seasons = (await db.scalars(select(Season).where(Season.year >= 2020))).all()
    managers = (await db.scalars(select(Manager))).all()
    season_by_id = {item.id: item for item in seasons}
    manager_by_id = {item.id: item for item in managers}
    matchups = list((await db.scalars(select(LeagueMatchup))).all())
    transactions = list((await db.scalars(select(LeagueTransaction))).all())
    transaction_ids = {item.id for item in transactions}
    participants = list((await db.scalars(select(LeagueTransactionParticipant).where(
        LeagueTransactionParticipant.transaction_id.in_(transaction_ids)
    ))).all()) if transaction_ids else []
    transaction_players = list((await db.scalars(select(LeagueTransactionPlayer).where(
        LeagueTransactionPlayer.transaction_id.in_(transaction_ids)
    ))).all()) if transaction_ids else []
    picks = list((await db.scalars(select(LeagueTransactionDraftPick).where(
        LeagueTransactionDraftPick.transaction_id.in_(transaction_ids)
    ))).all()) if transaction_ids else []
    faab = list((await db.scalars(select(LeagueTransactionFaab).where(
        LeagueTransactionFaab.transaction_id.in_(transaction_ids)
    ))).all()) if transaction_ids else []
    placements = list((await db.scalars(select(SeasonPlacement))).all())
    teams = list((await db.scalars(select(SeasonTeam))).all())
    custom_facts = list((await db.scalars(select(CustomSeasonFact).order_by(
        CustomSeasonFact.season_id, CustomSeasonFact.display_order
    ))).all())

    participants_by_transaction: dict[uuid.UUID, list[LeagueTransactionParticipant]] = {}
    players_by_transaction: dict[uuid.UUID, list[LeagueTransactionPlayer]] = {}
    picks_by_transaction: dict[uuid.UUID, list[LeagueTransactionDraftPick]] = {}
    faab_by_transaction: dict[uuid.UUID, list[LeagueTransactionFaab]] = {}
    for item in participants:
        participants_by_transaction.setdefault(item.transaction_id, []).append(item)
    for item in transaction_players:
        players_by_transaction.setdefault(item.transaction_id, []).append(item)
    for item in picks:
        picks_by_transaction.setdefault(item.transaction_id, []).append(item)
    for item in faab:
        faab_by_transaction.setdefault(item.transaction_id, []).append(item)

    transaction_rows = []
    for transaction in transactions:
        season = season_by_id.get(transaction.season_id)
        if not season:
            continue
        participant_rows = participants_by_transaction.get(transaction.id, [])
        roster_ids = {
            int(value) for value in ((transaction.raw_payload or {}).get("roster_ids") or [])
            if value not in (None, 0)
        }
        roster_ids.update(row.roster_id for row in players_by_transaction.get(transaction.id, []))
        for pick in picks_by_transaction.get(transaction.id, []):
            roster_ids.update((pick.previous_owner_roster_id, pick.new_owner_roster_id))
        for transfer in faab_by_transaction.get(transaction.id, []):
            roster_ids.update(value for value in (transfer.sender_roster_id, transfer.receiver_roster_id) if value)
        involved = [row.manager_id for row in participant_rows if not roster_ids or row.roster_id in roster_ids]
        acquisitions = [
            row.manager_id for row in players_by_transaction.get(transaction.id, [])
            if row.movement.value == "add"
        ]
        transaction_rows.append(HistoryTransaction(
            transaction.season_id, season.year, transaction.transaction_type, transaction.status,
            tuple(dict.fromkeys(involved)), tuple(acquisitions),
        ))

    team_count_by_season = Counter(team.season_id for team in teams)
    placement_rows = []
    for placement in placements:
        season = season_by_id.get(placement.season_id)
        manager = manager_by_id.get(placement.manager_id)
        effective, _ = _effective_placement(placement)
        if season and manager and effective is not None and team_count_by_season[season.id]:
            placement_rows.append(HistoryPlacement(
                season.id, season.year, manager.id, manager.display_name,
                effective, team_count_by_season[season.id],
            ))
    records = calculate_records(
        _stat_matchups(matchups, season_by_id, manager_by_id),
        transaction_rows,
        placement_rows,
        {manager.id: manager.display_name for manager in managers},
    )
    return {"records": [{
        "key": record.key,
        "label": record.label,
        "category": record.category,
        "tied": len(record.entries) > 1,
        "entries": [{
            "manager_id": entry.manager_id,
            "manager_name": entry.manager_name,
            "value": entry.value,
            "detail": entry.detail,
            "season_id": entry.season_id,
            "year": entry.year,
            "week": entry.week,
        } for entry in record.entries],
    } for record in records], "custom_facts": [{
        "id": fact.id,
        "season_id": fact.season_id,
        "year": season_by_id[fact.season_id].year,
        "label": fact.label,
        "value": fact.value,
    } for fact in custom_facts if fact.season_id in season_by_id]}


@router.get("/overview")
async def public_overview(
    db: AsyncSession = Depends(get_db),
    sleeper: SleeperService = Depends(get_public_sleeper_service),
):
    seasons = list((await db.scalars(select(Season).where(Season.year >= 2020).order_by(Season.year.desc()))).all())
    managers = list((await db.scalars(select(Manager).order_by(Manager.display_name))).all())
    teams = list((await db.scalars(select(SeasonTeam))).all())
    placements = list((await db.scalars(select(SeasonPlacement))).all())
    punishments = list((await db.scalars(select(SeasonPunishment))).all())
    matchups = list((await db.scalars(select(LeagueMatchup))).all())
    highlights = list((await db.scalars(select(WeeklyHighlight))).all())
    season_by_id = {item.id: item for item in seasons}
    manager_by_id = {item.id: item for item in managers}

    placement_rows = []
    for placement in placements:
        effective, source = _effective_placement(placement)
        season = season_by_id.get(placement.season_id)
        manager = manager_by_id.get(placement.manager_id)
        if season and manager and effective is not None:
            placement_rows.append({
                "season_id": season.id,
                "year": season.year,
                "manager_id": manager.id,
                "manager_name": manager.display_name,
                "placement": effective,
                "source": source,
            })
    podium_year = max((row["year"] for row in placement_rows if row["placement"] <= 3), default=None)
    podium = sorted(
        (row for row in placement_rows if row["year"] == podium_year and row["placement"] <= 3),
        key=lambda row: row["placement"],
    )
    champion = max(
        (row for row in placement_rows if row["placement"] == 1),
        key=lambda row: row["year"],
        default=None,
    )

    latest_team_by_manager: dict[uuid.UUID, SeasonTeam] = {}
    for team in teams:
        season = season_by_id.get(team.season_id)
        current = latest_team_by_manager.get(team.manager_id)
        current_season = season_by_id.get(current.season_id) if current else None
        if season and (current_season is None or season.year > current_season.year):
            latest_team_by_manager[team.manager_id] = team
    current_managers = [{
        "id": manager.id,
        "display_name": manager.display_name,
        "team_name": latest_team_by_manager[manager.id].team_name if manager.id in latest_team_by_manager else None,
    } for manager in managers if manager.is_active]

    latest_trades = list((await db.scalars(select(LeagueTransaction).where(
        LeagueTransaction.transaction_type == "trade"
    ).order_by(LeagueTransaction.occurred_at.desc(), LeagueTransaction.external_id).limit(3))).all())
    latest_waivers = list((await db.scalars(select(LeagueTransaction).where(
        LeagueTransaction.transaction_type.in_(("waiver", "free_agent"))
    ).order_by(LeagueTransaction.occurred_at.desc(), LeagueTransaction.external_id).limit(3))).all())
    transactions = list({item.id: item for item in [*latest_trades, *latest_waivers]}.values())
    transaction_ids = {item.id for item in transactions}
    participants = list((await db.scalars(select(LeagueTransactionParticipant).where(
        LeagueTransactionParticipant.transaction_id.in_(transaction_ids)
    ))).all()) if transaction_ids else []
    overview_players = list((await db.scalars(select(LeagueTransactionPlayer).where(
        LeagueTransactionPlayer.transaction_id.in_(transaction_ids)
    ))).all()) if transaction_ids else []
    overview_picks = list((await db.scalars(select(LeagueTransactionDraftPick).where(
        LeagueTransactionDraftPick.transaction_id.in_(transaction_ids)
    ))).all()) if transaction_ids else []
    overview_faab = list((await db.scalars(select(LeagueTransactionFaab).where(
        LeagueTransactionFaab.transaction_id.in_(transaction_ids)
    ))).all()) if transaction_ids else []
    involved_rosters: dict[uuid.UUID, set[int]] = {}
    for item in transactions:
        involved_rosters[item.id] = {
            int(value) for value in ((item.raw_payload or {}).get("roster_ids") or []) if value not in (None, 0)
        }
    for item in overview_players:
        involved_rosters.setdefault(item.transaction_id, set()).add(item.roster_id)
    for item in overview_picks:
        involved_rosters.setdefault(item.transaction_id, set()).update((item.previous_owner_roster_id, item.new_owner_roster_id))
    for item in overview_faab:
        involved_rosters.setdefault(item.transaction_id, set()).update(
            value for value in (item.sender_roster_id, item.receiver_roster_id) if value
        )
    participants_by_transaction: dict[uuid.UUID, list[str]] = {}
    for participant in participants:
        selected_rosters = involved_rosters.get(participant.transaction_id, set())
        if selected_rosters and participant.roster_id not in selected_rosters:
            continue
        manager = manager_by_id.get(participant.manager_id)
        if manager and manager.display_name not in participants_by_transaction.setdefault(participant.transaction_id, []):
            participants_by_transaction[participant.transaction_id].append(manager.display_name)

    def transaction_summary(item: LeagueTransaction) -> dict:
        season = season_by_id.get(item.season_id)
        return {
            "id": item.id,
            "season": season.year if season else None,
            "week": item.week,
            "transaction_type": item.transaction_type,
            "status": item.status,
            "occurred_at": item.occurred_at,
            "manager_names": participants_by_transaction.get(item.id, []),
        }

    record_payload = await public_records(db=db)
    headline_keys = {"highest_weekly_score", "biggest_blowout", "career_wins", "most_championships"}
    headline_records = [record for record in record_payload["records"] if record["key"] in headline_keys]

    activity_season_ids = {item.season_id for item in matchups} | {item.season_id for item in highlights}
    recent_highlights = []
    for highlight_season in (season for season in seasons if season.id in activity_season_ids):
        season_detail = await public_season_detail(highlight_season.id, db=db, sleeper=sleeper)
        candidate_highlights = sorted(
            season_detail["awards"], key=lambda item: (item["week"], item["category"]), reverse=True
        )[:6]
        if not candidate_highlights:
            continue
        for item in candidate_highlights:
            item["season_id"] = highlight_season.id
            item["year"] = highlight_season.year
        recent_highlights = candidate_highlights
        break

    latest_punishment = max(
        (item for item in punishments if item.season_id in season_by_id),
        key=lambda item: season_by_id[item.season_id].year,
        default=None,
    )
    return {
        "champion": champion,
        "podium": podium,
        "current_managers": current_managers,
        "latest_trades": [transaction_summary(item) for item in latest_trades],
        "latest_waivers": [transaction_summary(item) for item in latest_waivers],
        "headline_records": headline_records,
        "recent_highlights": recent_highlights,
        "punishment": None if not latest_punishment else {
            "season_id": latest_punishment.season_id,
            "year": season_by_id[latest_punishment.season_id].year,
            "manager_id": latest_punishment.manager_id,
            "manager_name": manager_by_id[latest_punishment.manager_id].display_name if latest_punishment.manager_id in manager_by_id else "Unknown manager",
            "title": latest_punishment.title,
        },
    }


@router.get("/teams/{manager_id}")
async def public_manager_detail(
    manager_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    sleeper: SleeperService = Depends(get_public_sleeper_service),
):
    manager = await db.get(Manager, manager_id)
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")
    managers, seasons, teams, placements, matchups, punishments, participants, transactions = await _history_rows(db)
    season_by_id = {season.id: season for season in seasons}
    manager_teams = sorted(
        (team for team in teams if team.manager_id == manager.id and team.season_id in season_by_id),
        key=lambda team: season_by_id[team.season_id].year,
    )
    placement_by_key = {(item.season_id, item.manager_id): item for item in placements}
    season_history = []
    for team in manager_teams:
        placement, source = _effective_placement(placement_by_key.get((team.season_id, manager.id)))
        season = season_by_id[team.season_id]
        season_history.append({
            "season_id": season.id,
            "year": season.year,
            "platform": season.platform.value,
            "team_name": team.team_name,
            "placement": placement,
            "placement_source": source,
        })

    transaction_by_id = {item.id: item for item in transactions}
    transaction_ids = {
        participant.transaction_id for participant in participants if participant.manager_id == manager.id
    }
    transaction_types = Counter(
        transaction_by_id[item_id].transaction_type
        for item_id in transaction_ids
        if item_id in transaction_by_id
    )
    punishment_history = sorted((
        {
            "season_id": punishment.season_id,
            "year": season_by_id[punishment.season_id].year,
            "title": punishment.title,
        }
        for punishment in punishments
        if punishment.manager_id == manager.id and punishment.season_id in season_by_id
    ), key=lambda item: item["year"], reverse=True)

    current_roster = None
    if manager.is_active:
        active_season = next((season for season in seasons if season.is_active and season.platform is SeasonPlatform.sleeper), None)
        active_team = next((team for team in manager_teams if active_season and team.season_id == active_season.id), None)
        if active_season and active_team and active_season.sleeper_league_id and active_team.roster_id:
            try:
                players = await sleeper.current_roster(active_season.sleeper_league_id, active_team.roster_id)
                current_roster = {
                    "season_year": active_season.year,
                    "team_name": active_team.team_name,
                    "players": [_player(player) for player in players],
                    "error": None,
                }
            except Exception:
                current_roster = {
                    "season_year": active_season.year,
                    "team_name": active_team.team_name,
                    "players": [],
                    "error": "Current roster is temporarily unavailable.",
                }

    team_counts = Counter(team.season_id for team in teams)
    return {
        "manager": {
            "id": manager.id,
            "display_name": manager.display_name,
            "biography": manager.biography,
            "is_active": manager.is_active,
        },
        "seasons": season_history,
        "championships": sum(item["placement"] == 1 for item in season_history),
        "biggest_losers": sum(
            item["placement"] == team_counts[item["season_id"]] for item in season_history
        ),
        "career": _records(list(matchups), {manager.id})[manager.id],
        "transactions": {"total": len(transaction_ids), "by_type": dict(sorted(transaction_types.items()))},
        "punishments": punishment_history,
        "current_roster": current_roster,
    }


@router.get("/seasons")
async def public_seasons(db: AsyncSession = Depends(get_db)):
    seasons = (await db.scalars(select(Season).where(Season.year >= 2020).order_by(Season.year.desc()))).all()
    teams = (await db.scalars(select(SeasonTeam))).all()
    matchups = (await db.scalars(select(LeagueMatchup))).all()
    placements = (await db.scalars(select(SeasonPlacement))).all()
    return {"seasons": [{
        "id": season.id,
        "year": season.year,
        "platform": season.platform.value,
        "is_active": season.is_active,
        "manager_count": sum(team.season_id == season.id for team in teams),
        "matchup_count": sum(matchup.season_id == season.id for matchup in matchups),
        "placement_count": sum(placement.season_id == season.id for placement in placements),
        "sources": sorted({matchup.source.value for matchup in matchups if matchup.season_id == season.id}),
    } for season in seasons]}



@router.get("/seasons/{season_id}")
async def public_season_detail(
    season_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    sleeper: SleeperService = Depends(get_public_sleeper_service),
):
    season = await db.get(Season, season_id)
    if not season or season.year < 2020:
        raise HTTPException(status_code=404, detail="Season not found")
    managers = (await db.scalars(select(Manager))).all()
    manager_by_id = {manager.id: manager for manager in managers}
    teams = (await db.scalars(select(SeasonTeam).where(SeasonTeam.season_id == season.id))).all()
    matchups = list((await db.scalars(select(LeagueMatchup).where(
        LeagueMatchup.season_id == season.id
    ).order_by(LeagueMatchup.week, LeagueMatchup.source_key))).all())
    placements = (await db.scalars(select(SeasonPlacement).where(SeasonPlacement.season_id == season.id))).all()
    placement_by_manager = {item.manager_id: item for item in placements}
    records = _records(matchups, {team.manager_id for team in teams})

    standings = []
    placement_rows = []
    for team in teams:
        manager = manager_by_id.get(team.manager_id)
        placement, source = _effective_placement(placement_by_manager.get(team.manager_id))
        common = {
            "manager_id": team.manager_id,
            "manager_name": manager.display_name if manager else "Unknown manager",
            "team_name": team.team_name,
            "placement": placement,
            "placement_source": source,
        }
        placement_rows.append(common)
        standings.append({**common, **records[team.manager_id]})
    placement_rows.sort(key=lambda item: (item["placement"] is None, item["placement"] or 999, item["manager_name"]))
    standings.sort(key=lambda item: (
        item["placement"] is None,
        item["placement"] or 999,
        -item["wins"],
        -item["points_for"],
    ))

    highlights = (await db.scalars(select(WeeklyHighlight).where(
        WeeklyHighlight.season_id == season.id
    ).order_by(WeeklyHighlight.week, WeeklyHighlight.category))).all()
    calculated_highlights = calculate_weekly_highlights(_stat_matchups(matchups, {season.id: season}, manager_by_id))
    manual_highlights = [HighlightCandidate(
        season.id,
        item.week,
        item.category,
        item.manager_id,
        manager_by_id[item.manager_id].display_name if item.manager_id in manager_by_id else None,
        item.player_id,
        item.player_name,
        item.value,
        source="manual",
        source_key=item.source_key,
    ) for item in highlights if item.source.value == "manual"]
    merged_highlights = merge_weekly_highlights(calculated_highlights, manual_highlights)
    highlight_player_ids = {item.player_id for item in merged_highlights if item.player_id}
    highlight_players: dict[str, SleeperPlayer] = {}
    if highlight_player_ids:
        try:
            highlight_players = await sleeper.player_lookup(highlight_player_ids)
        except Exception:
            highlight_players = {}
    facts = (await db.scalars(select(CustomSeasonFact).where(
        CustomSeasonFact.season_id == season.id
    ).order_by(CustomSeasonFact.display_order))).all()
    punishment = await db.scalar(select(SeasonPunishment).where(SeasonPunishment.season_id == season.id))
    return {
        "season": {
            "id": season.id,
            "year": season.year,
            "platform": season.platform.value,
            "is_active": season.is_active,
            "sources": sorted({matchup.source.value for matchup in matchups}),
        },
        "placements": placement_rows,
        "standings": standings,
        "weekly_results": [{
            "id": matchup.id,
            "week": matchup.week,
            "week_end": (matchup.source_metadata or {}).get("week_end"),
            "week_label": (matchup.source_metadata or {}).get("week_label"),
            "manager_a_id": matchup.manager_a_id,
            "manager_b_id": matchup.manager_b_id,
            "team_a_name": matchup.team_a_name,
            "team_b_name": matchup.team_b_name,
            "score_a": matchup.score_a,
            "score_b": matchup.score_b,
            "source": matchup.source.value,
        } for matchup in matchups],
        "awards": [{
            "id": item.source_key or f"{item.week}:{item.category}:{item.manager_id or item.player_id or 'game'}",
            "week": item.week,
            "category": item.category,
            "manager_id": item.manager_id,
            "manager_name": item.manager_name,
            "player_id": item.player_id,
            "player_name": (
                highlight_players[item.player_id].name
                if item.player_id in highlight_players
                else item.player_name or (f"Player {item.player_id}" if item.player_id else None)
            ),
            "player_image_url": highlight_players[item.player_id].image_url if item.player_id in highlight_players else None,
            "value": item.value,
            "detail": item.detail,
            "source": item.source,
        } for item in merged_highlights],
        "facts": [{"id": item.id, "label": item.label, "value": item.value, "source": "manual"} for item in facts],
        "punishment": None if not punishment else {
            "manager_id": punishment.manager_id,
            "manager_name": manager_by_id[punishment.manager_id].display_name if punishment.manager_id in manager_by_id else "Unknown manager",
            "title": punishment.title,
            "source": "manual",
        },
    }
