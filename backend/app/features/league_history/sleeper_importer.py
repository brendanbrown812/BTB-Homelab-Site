import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.league_history.models import (
    HistorySource,
    ImportRun,
    ImportRunStatus,
    LeagueMatchup,
    LeagueTransaction,
    LeagueTransactionDraftPick,
    LeagueTransactionFaab,
    LeagueTransactionParticipant,
    LeagueTransactionPlayer,
    ManagerAlias,
    ManagerAliasProvider,
    SeasonPlacement,
    SeasonTeam,
    TransactionMovement,
)
from app.models.season import Season, SeasonPlatform
from app.services.sleeper import SleeperLeagueArchive, SleeperService


class SleeperImportError(Exception):
    pass


def _team_name(user: dict, roster_id: int) -> str:
    metadata = user.get("metadata") or {}
    return str(metadata.get("team_name") or user.get("display_name") or f"Roster {roster_id}")


def _roster_references(payload: dict) -> set[int]:
    result = {int(value) for value in payload.get("roster_ids") or [] if value not in (None, 0)}
    for key in ("adds", "drops"):
        result.update(int(value) for value in (payload.get(key) or {}).values() if value is not None)
    for pick in payload.get("draft_picks") or []:
        for key in ("roster_id", "owner_id", "previous_owner_id"):
            if pick.get(key) is not None:
                result.add(int(pick[key]))
    for transfer in payload.get("waiver_budget") or []:
        for key in ("sender", "receiver"):
            if transfer.get(key) not in (None, 0):
                result.add(int(transfer[key]))
    return result


def _placements(
    winners_bracket: tuple[dict, ...],
    losers_bracket: tuple[dict, ...],
    *,
    total_rosters: int,
    playoff_type: int,
) -> dict[int, int]:
    """Convert winner and consolation/toilet bracket results to overall places."""
    result: dict[int, int] = {}

    def completed_games(bracket: tuple[dict, ...]) -> list[dict]:
        return [
            game for game in bracket
            if game.get("p") is not None and game.get("w") is not None and game.get("l") is not None
        ]

    for game in completed_games(winners_bracket):
        place = int(game["p"])
        result[int(game["w"])] = place
        result[int(game["l"])] = place + 1

    loser_games = completed_games(losers_bracket)
    loser_rosters = {
        int(value)
        for game in losers_bracket
        for key in ("t1", "t2", "w", "l")
        for value in (game.get(key),)
        if isinstance(value, int) and value > 0
    }
    loser_team_count = len(loser_rosters)
    relative_places = bool(loser_games) and loser_team_count > 0 and max(int(game["p"]) for game in loser_games) <= loser_team_count

    for game in loser_games:
        bracket_place = int(game["p"])
        winner_place, loser_place = bracket_place, bracket_place + 1
        if relative_places and playoff_type == 2:
            # In a toilet bowl, first in the loser bracket is last overall.
            winner_place = total_rosters - bracket_place + 1
            loser_place = total_rosters - bracket_place
        elif relative_places:
            # In a consolation bracket, first is the best non-playoff finish.
            first_consolation_place = total_rosters - loser_team_count + 1
            winner_place = first_consolation_place + bracket_place - 1
            loser_place = first_consolation_place + bracket_place
        result[int(game["w"])] = winner_place
        result[int(game["l"])] = loser_place
    return result


async def _finish_run(
    db: AsyncSession,
    run_id: uuid.UUID,
    status: ImportRunStatus,
    counts: dict[str, Any],
    error: str | None = None,
) -> None:
    run = await db.get(ImportRun, run_id)
    if not run:
        return
    run.status = status
    run.counts = counts
    run.error_details = error
    run.finished_at = datetime.now(timezone.utc)
    await db.commit()


async def import_sleeper_season(
    db: AsyncSession,
    season_id: uuid.UUID,
    *,
    dry_run: bool = False,
    sleeper: SleeperService | None = None,
) -> dict[str, Any]:
    """Import a season atomically. The audit row is committed independently."""
    season = await db.get(Season, season_id)
    if not season:
        raise SleeperImportError("Season not found")
    run = ImportRun(
        season_id=season_id,
        source=HistorySource.sleeper,
        status=ImportRunStatus.running,
        counts={"mode": "dry_run" if dry_run else "import"},
    )
    db.add(run)
    await db.commit()
    run_id = run.id
    counts: dict[str, Any] = {"mode": "dry_run" if dry_run else "import"}

    try:
        if season.platform is not SeasonPlatform.sleeper or not season.sleeper_league_id:
            raise SleeperImportError("Only configured Sleeper seasons can be imported")

        adapter = sleeper or SleeperService()
        archive = await adapter.league_archive(season.sleeper_league_id)
        aliases = (await db.scalars(select(ManagerAlias).where(
            ManagerAlias.provider == ManagerAliasProvider.sleeper_user_id
        ))).all()
        manager_by_user = {alias.external_value: alias.manager_id for alias in aliases}
        user_by_id = {str(user["user_id"]): user for user in archive.users if user.get("user_id") is not None}

        roster_rows: dict[int, tuple[uuid.UUID, str, str]] = {}
        unresolved: list[dict[str, Any]] = []
        for roster in archive.rosters:
            roster_id = int(roster["roster_id"])
            owner_id = str(roster.get("owner_id") or "")
            manager_id = manager_by_user.get(owner_id)
            if not owner_id or not manager_id:
                unresolved.append({
                    "roster_id": roster_id,
                    "sleeper_user_id": owner_id or None,
                    "display_name": (user_by_id.get(owner_id) or {}).get("display_name"),
                })
                continue
            roster_rows[roster_id] = (
                manager_id,
                owner_id,
                _team_name(user_by_id.get(owner_id) or {}, roster_id),
            )

        referenced_rosters: set[int] = set()
        for rows in archive.matchups_by_week.values():
            referenced_rosters.update(int(row["roster_id"]) for row in rows if row.get("roster_id") is not None)
        for rows in archive.transactions_by_round.values():
            for payload in rows:
                referenced_rosters.update(_roster_references(payload))
        known_roster_ids = {int(roster["roster_id"]) for roster in archive.rosters}
        missing_rosters = sorted(referenced_rosters - known_roster_ids)
        unresolved.extend({"roster_id": value, "reason": "referenced roster has no resolved manager"} for value in missing_rosters)
        counts["unresolved_identities"] = unresolved
        counts["season_teams"] = len(roster_rows)
        if unresolved:
            await _finish_run(db, run_id, ImportRunStatus.needs_attention, counts, "Unresolved Sleeper identities")
            return {"run_id": run_id, "status": ImportRunStatus.needs_attention.value, "counts": counts}

        matchup_pairs: list[tuple[int, int, dict, dict]] = []
        for week, rows in archive.matchups_by_week.items():
            grouped: dict[int, list[dict]] = {}
            for row in rows:
                if row.get("matchup_id") is not None:
                    grouped.setdefault(int(row["matchup_id"]), []).append(row)
            for matchup_id, pair in grouped.items():
                if len(pair) == 2:
                    matchup_pairs.append((week, matchup_id, *sorted(pair, key=lambda row: int(row["roster_id"]))))

        transactions = {
            str(payload.get("transaction_id")): (round_number, payload)
            for round_number, rows in archive.transactions_by_round.items()
            for payload in rows
            if payload.get("transaction_id") is not None
        }
        player_ids = {
            str(player_id)
            for _, payload in transactions.values()
            for field in ("adds", "drops")
            for player_id in (payload.get(field) or {}).keys()
        }
        player_names = {}
        if player_ids:
            try:
                player_names = await adapter.player_lookup(player_ids)
            except Exception:
                # IDs and raw payloads remain fully usable if the large catalog
                # endpoint is temporarily unavailable.
                counts["player_lookup_failed"] = True
        league_settings = archive.league.get("settings") or {}
        calculated = _placements(
            archive.winners_bracket,
            archive.losers_bracket,
            total_rosters=int(archive.league.get("total_rosters") or len(roster_rows)),
            playoff_type=int(league_settings.get("playoff_type") or 0),
        )
        league_status = str(archive.league.get("status") or "").lower()
        counts.update({
            "matchups": len(matchup_pairs),
            "transactions": len(transactions),
            "players": len(player_ids),
            "calculated_placements": len(calculated),
            "placement_complete": len(calculated) == len(roster_rows),
        })

        if not roster_rows:
            await _finish_run(
                db, run_id, ImportRunStatus.needs_attention, counts,
                "Sleeper returned no rosters for this league ID",
            )
            return {"run_id": run_id, "status": ImportRunStatus.needs_attention.value, "counts": counts}
        if league_status in {"complete", "completed"} and not matchup_pairs:
            await _finish_run(
                db, run_id, ImportRunStatus.needs_attention, counts,
                "Sleeper returned no paired matchups for this completed season",
            )
            return {"run_id": run_id, "status": ImportRunStatus.needs_attention.value, "counts": counts}

        if dry_run:
            await _finish_run(db, run_id, ImportRunStatus.succeeded, counts)
            return {"run_id": run_id, "status": ImportRunStatus.succeeded.value, "counts": counts}

        existing_teams = (await db.scalars(select(SeasonTeam).where(SeasonTeam.season_id == season.id))).all()
        team_by_manager = {team.manager_id: team for team in existing_teams}
        for roster_id, (manager_id, owner_id, name) in roster_rows.items():
            team = team_by_manager.get(manager_id)
            if not team:
                team = SeasonTeam(season_id=season.id, manager_id=manager_id, team_name=name)
                db.add(team)
                team_by_manager[manager_id] = team
            team.team_name = name
            team.sleeper_user_id = owner_id
            team.roster_id = roster_id

        existing_matchups = (await db.scalars(select(LeagueMatchup).where(
            LeagueMatchup.season_id == season.id, LeagueMatchup.source == HistorySource.sleeper
        ))).all()
        matchup_by_key = {item.source_key: item for item in existing_matchups}
        current_leg_value = (archive.league.get("settings") or {}).get("leg")
        current_leg = int(current_leg_value) if current_leg_value is not None else None
        for week, matchup_id, row_a, row_b in matchup_pairs:
            roster_a, roster_b = int(row_a["roster_id"]), int(row_b["roster_id"])
            manager_a, _, name_a = roster_rows[roster_a]
            manager_b, _, name_b = roster_rows[roster_b]
            source_key = f"week:{week}:matchup:{matchup_id}"
            item = matchup_by_key.get(source_key)
            if not item:
                item = LeagueMatchup(season_id=season.id, source=HistorySource.sleeper, source_key=source_key)
                db.add(item)
            item.week = week
            item.manager_a_id, item.manager_b_id = manager_a, manager_b
            item.team_a_name, item.team_b_name = name_a, name_b
            item.score_a = float(row_a["points"]) if row_a.get("points") is not None else None
            item.score_b = float(row_b["points"]) if row_b.get("points") is not None else None
            item.sleeper_matchup_id = matchup_id
            source_metadata = {"team_a": row_a, "team_b": row_b}
            if league_status in {"complete", "completed"}:
                source_metadata["is_complete"] = True
            elif current_leg is not None:
                source_metadata["is_complete"] = week < current_leg
            item.source_metadata = source_metadata

        existing_transactions = (await db.scalars(select(LeagueTransaction).where(
            LeagueTransaction.season_id == season.id
        ))).all()
        transaction_by_external = {item.external_id: item for item in existing_transactions}
        for external_id, (round_number, payload) in transactions.items():
            transaction = transaction_by_external.get(external_id)
            if not transaction:
                transaction = LeagueTransaction(
                    season_id=season.id,
                    external_id=external_id,
                    week=int(payload.get("leg") or round_number),
                    transaction_type=str(payload.get("type") or "unknown"),
                    status=str(payload.get("status") or "unknown"),
                    occurred_at=datetime.fromtimestamp(
                        int(payload.get("created") or payload.get("status_updated") or 0) / 1000,
                        tz=timezone.utc,
                    ),
                    raw_payload=payload,
                )
                db.add(transaction)
                await db.flush()
            transaction.week = int(payload.get("leg") or round_number)
            transaction.transaction_type = str(payload.get("type") or "unknown")
            transaction.status = str(payload.get("status") or "unknown")
            created = int(payload.get("created") or payload.get("status_updated") or 0)
            transaction.occurred_at = datetime.fromtimestamp(created / 1000, tz=timezone.utc)
            transaction.raw_payload = payload

            for model in (LeagueTransactionParticipant, LeagueTransactionPlayer, LeagueTransactionDraftPick, LeagueTransactionFaab):
                await db.execute(delete(model).where(model.transaction_id == transaction.id))

            participant_ids = _roster_references(payload)
            for roster_id in sorted(participant_ids):
                db.add(LeagueTransactionParticipant(
                    transaction_id=transaction.id, manager_id=roster_rows[roster_id][0], roster_id=roster_id,
                ))
            for movement, field in ((TransactionMovement.add, "adds"), (TransactionMovement.drop, "drops")):
                for player_id, roster_value in (payload.get(field) or {}).items():
                    roster_id = int(roster_value)
                    player = player_names.get(str(player_id))
                    db.add(LeagueTransactionPlayer(
                        transaction_id=transaction.id,
                        manager_id=roster_rows[roster_id][0],
                        roster_id=roster_id,
                        player_id=str(player_id),
                        player_name=player.name if player else None,
                        movement=movement,
                    ))
            for pick in payload.get("draft_picks") or []:
                db.add(LeagueTransactionDraftPick(
                    transaction_id=transaction.id,
                    pick_season=int(pick["season"]),
                    round=int(pick["round"]),
                    original_roster_id=int(pick["roster_id"]),
                    previous_owner_roster_id=int(pick["previous_owner_id"]),
                    new_owner_roster_id=int(pick["owner_id"]),
                ))
            for transfer in payload.get("waiver_budget") or []:
                db.add(LeagueTransactionFaab(
                    transaction_id=transaction.id,
                    sender_roster_id=int(transfer["sender"]),
                    receiver_roster_id=int(transfer["receiver"]),
                    amount=int(transfer["amount"]),
                ))
            waiver_bid = (payload.get("settings") or {}).get("waiver_bid")
            roster_ids = payload.get("roster_ids") or []
            if waiver_bid is not None and roster_ids:
                db.add(LeagueTransactionFaab(
                    transaction_id=transaction.id,
                    sender_roster_id=int(roster_ids[0]),
                    receiver_roster_id=0,
                    amount=int(waiver_bid),
                ))

        placements = (await db.scalars(select(SeasonPlacement).where(SeasonPlacement.season_id == season.id))).all()
        placement_by_manager = {item.manager_id: item for item in placements}
        for item in placements:
            item.calculated_placement = None
        for roster_id, place in calculated.items():
            if roster_id not in roster_rows:
                continue
            manager_id = roster_rows[roster_id][0]
            item = placement_by_manager.get(manager_id)
            if not item:
                item = SeasonPlacement(season_id=season.id, manager_id=manager_id)
                db.add(item)
                placement_by_manager[manager_id] = item
            item.calculated_placement = place

        await db.commit()
        await _finish_run(db, run_id, ImportRunStatus.succeeded, counts)
        return {"run_id": run_id, "status": ImportRunStatus.succeeded.value, "counts": counts}
    except Exception as error:
        await db.rollback()
        counts["exception_type"] = type(error).__name__
        await _finish_run(db, run_id, ImportRunStatus.failed, counts, str(error))
        if isinstance(error, SleeperImportError):
            return {"run_id": run_id, "status": ImportRunStatus.failed.value, "counts": counts, "error": str(error)}
        raise


async def refresh_sleeper_seasons(db: AsyncSession, sleeper: SleeperService | None = None) -> list[dict[str, Any]]:
    seasons = (await db.scalars(select(Season).where(
        Season.platform == SeasonPlatform.sleeper,
        Season.sleeper_league_id.is_not(None),
    ).order_by(Season.year))).all()
    results = []
    for season in seasons:
        results.append(await import_sleeper_season(db, season.id, sleeper=sleeper))
    return results
