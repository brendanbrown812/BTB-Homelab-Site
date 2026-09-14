"""Pure league-history calculations. Prediction data must never enter this module."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable


@dataclass(frozen=True)
class HistoryMatchup:
    season_id: uuid.UUID
    year: int
    week: int
    manager_a_id: uuid.UUID
    manager_a_name: str
    team_a_name: str
    score_a: float | None
    manager_b_id: uuid.UUID
    manager_b_name: str
    team_b_name: str
    score_b: float | None
    source_metadata: dict | None = None


@dataclass(frozen=True)
class HistoryTransaction:
    season_id: uuid.UUID
    year: int
    transaction_type: str
    status: str
    participant_ids: tuple[uuid.UUID, ...]
    acquisition_manager_ids: tuple[uuid.UUID, ...] = ()


@dataclass(frozen=True)
class HistoryPlacement:
    season_id: uuid.UUID
    year: int
    manager_id: uuid.UUID
    manager_name: str
    placement: int
    team_count: int


@dataclass(frozen=True)
class RecordEntry:
    manager_id: uuid.UUID
    manager_name: str
    value: float
    detail: str
    season_id: uuid.UUID | None = None
    year: int | None = None
    week: int | None = None


@dataclass(frozen=True)
class RecordStatistic:
    key: str
    label: str
    category: str
    entries: tuple[RecordEntry, ...]


@dataclass(frozen=True)
class HighlightCandidate:
    season_id: uuid.UUID
    week: int
    category: str
    manager_id: uuid.UUID | None = None
    manager_name: str | None = None
    player_id: str | None = None
    player_name: str | None = None
    value: float | None = None
    detail: str | None = None
    source: str = "calculated"
    source_key: str = ""


def _complete_weeks(matchups: Iterable[HistoryMatchup]) -> list[HistoryMatchup]:
    grouped: dict[tuple[uuid.UUID, int], list[HistoryMatchup]] = defaultdict(list)
    for matchup in matchups:
        grouped[(matchup.season_id, matchup.week)].append(matchup)
    return [
        matchup
        for rows in grouped.values()
        if rows and all(
            row.score_a is not None
            and row.score_b is not None
            and (row.source_metadata or {}).get("is_complete") is not False
            for row in rows
        )
        for matchup in rows
    ]


def _single_week_matchups(matchups: Iterable[HistoryMatchup]) -> list[HistoryMatchup]:
    """Exclude aggregate multi-week playoff series from weekly comparisons."""
    return [
        matchup for matchup in matchups
        if (matchup.source_metadata or {}).get("week_end") is None
    ]


def _teams(matchup: HistoryMatchup):
    return (
        (matchup.manager_a_id, matchup.manager_a_name, matchup.team_a_name, matchup.score_a, matchup.score_b),
        (matchup.manager_b_id, matchup.manager_b_name, matchup.team_b_name, matchup.score_b, matchup.score_a),
    )


def _extreme(key: str, label: str, category: str, entries: list[RecordEntry], highest: bool = True) -> RecordStatistic | None:
    if not entries:
        return None
    target = (max if highest else min)(entry.value for entry in entries)
    tied = tuple(entry for entry in entries if entry.value == target)
    return RecordStatistic(key, label, category, tied)


def weekly_team_score_record(matchups: Iterable[HistoryMatchup], *, highest: bool) -> RecordStatistic | None:
    entries = []
    for matchup in _complete_weeks(_single_week_matchups(matchups)):
        for manager_id, manager_name, team_name, score, _ in _teams(matchup):
            assert score is not None
            entries.append(RecordEntry(
                manager_id, manager_name, score, f"{team_name} scored {score:.2f}",
                matchup.season_id, matchup.year, matchup.week,
            ))
    return _extreme(
        "highest_weekly_score" if highest else "lowest_weekly_score",
        "Highest weekly team score" if highest else "Lowest weekly team score",
        "Scoring",
        entries,
        highest,
    )


def margin_record(matchups: Iterable[HistoryMatchup], *, biggest: bool) -> RecordStatistic | None:
    entries = []
    for matchup in _complete_weeks(_single_week_matchups(matchups)):
        assert matchup.score_a is not None and matchup.score_b is not None
        margin = abs(matchup.score_a - matchup.score_b)
        if matchup.score_a >= matchup.score_b:
            manager_id, manager_name = matchup.manager_a_id, matchup.manager_a_name
        else:
            manager_id, manager_name = matchup.manager_b_id, matchup.manager_b_name
        detail = f"{matchup.team_a_name} {matchup.score_a:.2f} – {matchup.team_b_name} {matchup.score_b:.2f}"
        entries.append(RecordEntry(
            manager_id, manager_name, margin, detail, matchup.season_id, matchup.year, matchup.week
        ))
    return _extreme(
        "biggest_blowout" if biggest else "closest_matchup",
        "Biggest blowout" if biggest else "Closest matchup",
        "Matchups",
        entries,
        biggest,
    )


def season_points_record(matchups: Iterable[HistoryMatchup]) -> RecordStatistic | None:
    totals: dict[tuple[uuid.UUID, int, uuid.UUID, str], float] = defaultdict(float)
    for matchup in _complete_weeks(matchups):
        for manager_id, manager_name, _, score, _ in _teams(matchup):
            assert score is not None
            totals[(matchup.season_id, matchup.year, manager_id, manager_name)] += score
    entries = [
        RecordEntry(manager_id, name, round(value, 2), f"{value:.2f} points", season_id, year)
        for (season_id, year, manager_id, name), value in totals.items()
    ]
    return _extreme("highest_season_points", "Highest season points", "Scoring", entries)


def career_totals(matchups: Iterable[HistoryMatchup]) -> dict[uuid.UUID, dict[str, float | int | str]]:
    totals: dict[uuid.UUID, dict[str, float | int | str]] = {}
    for matchup in _complete_weeks(matchups):
        assert matchup.score_a is not None and matchup.score_b is not None
        for manager_id, name, _, score_for, score_against in _teams(matchup):
            row = totals.setdefault(manager_id, {
                "manager_name": name, "wins": 0, "losses": 0, "ties": 0,
                "points_for": 0.0, "points_against": 0.0,
            })
            assert score_for is not None and score_against is not None
            row["points_for"] = float(row["points_for"]) + score_for
            row["points_against"] = float(row["points_against"]) + score_against
            if score_for > score_against:
                row["wins"] = int(row["wins"]) + 1
            elif score_for < score_against:
                row["losses"] = int(row["losses"]) + 1
            else:
                row["ties"] = int(row["ties"]) + 1
    for row in totals.values():
        row["points_for"] = round(float(row["points_for"]), 2)
        row["points_against"] = round(float(row["points_against"]), 2)
    return totals


def career_leader_records(matchups: Iterable[HistoryMatchup]) -> list[RecordStatistic]:
    totals = career_totals(matchups)
    definitions = (
        ("career_wins", "Career wins", "wins", "Career"),
        ("career_losses", "Career losses", "losses", "Career"),
        ("career_points_for", "Career points for", "points_for", "Career"),
        ("career_points_against", "Career points against", "points_against", "Career"),
    )
    records = []
    for key, label, field_name, category in definitions:
        entries = [RecordEntry(
            manager_id, str(row["manager_name"]), float(row[field_name]),
            f"{float(row[field_name]):.2f}" if "points" in field_name else str(int(row[field_name])),
        ) for manager_id, row in totals.items()]
        result = _extreme(key, label, category, entries)
        if result:
            records.append(result)
    return records


def season_record_extreme(matchups: Iterable[HistoryMatchup], *, best: bool) -> RecordStatistic | None:
    totals: dict[tuple[uuid.UUID, int, uuid.UUID, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    for matchup in _complete_weeks(matchups):
        assert matchup.score_a is not None and matchup.score_b is not None
        for manager_id, name, _, score_for, score_against in _teams(matchup):
            row = totals[(matchup.season_id, matchup.year, manager_id, name)]
            assert score_for is not None and score_against is not None
            if score_for > score_against:
                row[0] += 1
            elif score_for < score_against:
                row[1] += 1
            else:
                row[2] += 1
    if not totals:
        return None
    ratios = {
        key: Fraction(values[0] * 2 + values[2], max(1, sum(values)) * 2)
        for key, values in totals.items()
    }
    target = (max if best else min)(ratios.values())
    entries = []
    for (season_id, year, manager_id, name), ratio in ratios.items():
        if ratio == target:
            wins, losses, ties = totals[(season_id, year, manager_id, name)]
            detail = f"{wins}-{losses}" + (f"-{ties}" if ties else "")
            entries.append(RecordEntry(manager_id, name, float(ratio), detail, season_id, year))
    return RecordStatistic(
        "best_season_record" if best else "worst_season_record",
        "Best season record" if best else "Worst season record",
        "Records",
        tuple(entries),
    )


def streak_record(matchups: Iterable[HistoryMatchup], *, winning: bool) -> RecordStatistic | None:
    games: dict[uuid.UUID, list[tuple[int, int, bool, HistoryMatchup, str]]] = defaultdict(list)
    for matchup in _complete_weeks(matchups):
        assert matchup.score_a is not None and matchup.score_b is not None
        for manager_id, name, _, score_for, score_against in _teams(matchup):
            assert score_for is not None and score_against is not None
            outcome = score_for > score_against if winning else score_for < score_against
            games[manager_id].append((matchup.year, matchup.week, outcome, matchup, name))
    entries: list[RecordEntry] = []
    for manager_id, rows in games.items():
        current = 0
        best_length = 0
        best_end: HistoryMatchup | None = None
        name = rows[0][4]
        for _, _, outcome, matchup, _ in sorted(rows, key=lambda row: (row[0], row[1])):
            current = current + 1 if outcome else 0
            if current > best_length:
                best_length, best_end = current, matchup
        if best_length and best_end:
            entries.append(RecordEntry(
                manager_id, name, float(best_length), f"{best_length} games",
                best_end.season_id, best_end.year, best_end.week,
            ))
    return _extreme(
        "longest_winning_streak" if winning else "longest_losing_streak",
        "Longest winning streak" if winning else "Longest losing streak",
        "Streaks",
        entries,
    )


def transaction_leader(
    transactions: Iterable[HistoryTransaction], manager_names: dict[uuid.UUID, str], *, acquisitions: bool
) -> RecordStatistic | None:
    counts: dict[uuid.UUID, int] = defaultdict(int)
    if acquisitions:
        for transaction in transactions:
            if transaction.transaction_type in {"waiver", "free_agent"} and transaction.status.lower() in {"complete", "completed", "successful"}:
                for manager_id in transaction.acquisition_manager_ids:
                    counts[manager_id] += 1
    else:
        for transaction in transactions:
            if transaction.transaction_type == "trade" and transaction.status.lower() in {"complete", "completed", "successful"}:
                for manager_id in set(transaction.participant_ids):
                    counts[manager_id] += 1
    entries = [RecordEntry(
        manager_id, manager_names.get(manager_id, "Unknown manager"), float(value),
        f"{value} acquisitions" if acquisitions else f"{value} trades",
    ) for manager_id, value in counts.items()]
    return _extreme(
        "most_acquisitions" if acquisitions else "most_trades",
        "Most waiver/free-agent acquisitions" if acquisitions else "Most trades",
        "Transactions",
        entries,
    )


def placement_leader(placements: Iterable[HistoryPlacement], *, kind: str) -> RecordStatistic | None:
    counts: dict[tuple[uuid.UUID, str], int] = defaultdict(int)
    for placement in placements:
        qualifies = (
            placement.placement == 1 if kind == "championships"
            else placement.placement <= 3 if kind == "podiums"
            else placement.placement >= max(1, placement.team_count - 2)
        )
        if qualifies:
            counts[(placement.manager_id, placement.manager_name)] += 1
    labels = {
        "championships": "Championships",
        "podiums": "Podium finishes",
        "bottom_finishes": "Bottom-three finishes",
    }
    entries = [RecordEntry(manager_id, name, float(value), f"{value} finishes") for (manager_id, name), value in counts.items()]
    return _extreme(f"most_{kind}", labels[kind], "Finishes", entries)


def calculate_records(
    matchups: Iterable[HistoryMatchup],
    transactions: Iterable[HistoryTransaction],
    placements: Iterable[HistoryPlacement],
    manager_names: dict[uuid.UUID, str],
) -> list[RecordStatistic]:
    matchup_rows = list(matchups)
    transaction_rows = list(transactions)
    placement_rows = list(placements)
    candidates = [
        weekly_team_score_record(matchup_rows, highest=True),
        weekly_team_score_record(matchup_rows, highest=False),
        margin_record(matchup_rows, biggest=True),
        margin_record(matchup_rows, biggest=False),
        season_points_record(matchup_rows),
        season_record_extreme(matchup_rows, best=True),
        season_record_extreme(matchup_rows, best=False),
        streak_record(matchup_rows, winning=True),
        streak_record(matchup_rows, winning=False),
        transaction_leader(transaction_rows, manager_names, acquisitions=False),
        transaction_leader(transaction_rows, manager_names, acquisitions=True),
        *career_leader_records(matchup_rows),
        placement_leader(placement_rows, kind="championships"),
        placement_leader(placement_rows, kind="podiums"),
        placement_leader(placement_rows, kind="bottom_finishes"),
    ]
    return [candidate for candidate in candidates if candidate is not None]


def calculate_weekly_highlights(matchups: Iterable[HistoryMatchup]) -> list[HighlightCandidate]:
    complete = _complete_weeks(_single_week_matchups(matchups))
    grouped: dict[tuple[uuid.UUID, int], list[HistoryMatchup]] = defaultdict(list)
    for matchup in complete:
        grouped[(matchup.season_id, matchup.week)].append(matchup)
    highlights: list[HighlightCandidate] = []
    for (season_id, week), rows in grouped.items():
        team_scores = [
            (manager_id, manager_name, team_name, score)
            for matchup in rows
            for manager_id, manager_name, team_name, score, _ in _teams(matchup)
        ]
        high_score = max(float(row[3]) for row in team_scores if row[3] is not None)
        for manager_id, manager_name, team_name, score in team_scores:
            if score == high_score:
                highlights.append(HighlightCandidate(
                    season_id, week, "Highest-scoring fantasy team", manager_id, manager_name,
                    value=high_score, detail=team_name, source_key=f"highest-team:{manager_id}",
                ))

        wins = []
        margins = []
        for matchup in rows:
            assert matchup.score_a is not None and matchup.score_b is not None
            margin = abs(matchup.score_a - matchup.score_b)
            margins.append((margin, matchup))
            if matchup.score_a > matchup.score_b:
                wins.append((margin, matchup.manager_a_id, matchup.manager_a_name, matchup))
            elif matchup.score_b > matchup.score_a:
                wins.append((margin, matchup.manager_b_id, matchup.manager_b_name, matchup))
        if wins:
            biggest = max(row[0] for row in wins)
            for margin, manager_id, manager_name, matchup in wins:
                if margin == biggest:
                    highlights.append(HighlightCandidate(
                        season_id, week, "Biggest win", manager_id, manager_name, value=margin,
                        detail=f"{matchup.team_a_name} vs {matchup.team_b_name}",
                        source_key=f"biggest-win:{manager_id}",
                    ))
        closest = min(row[0] for row in margins)
        for margin, matchup in margins:
            if margin == closest:
                highlights.append(HighlightCandidate(
                    season_id, week, "Closest game", value=margin,
                    detail=f"{matchup.team_a_name} vs {matchup.team_b_name}",
                    source_key=f"closest:{matchup.manager_a_id}:{matchup.manager_b_id}",
                ))

        starter_rows: list[tuple[str, float, uuid.UUID, str]] = []
        player_data_complete = True
        for matchup in rows:
            for side, manager_id, manager_name in (
                ("team_a", matchup.manager_a_id, matchup.manager_a_name),
                ("team_b", matchup.manager_b_id, matchup.manager_b_name),
            ):
                metadata = (matchup.source_metadata or {}).get(side)
                starters = metadata.get("starters") if isinstance(metadata, dict) else None
                points = metadata.get("players_points") if isinstance(metadata, dict) else None
                active_starters = [str(value) for value in starters or [] if str(value) != "0"]
                if (
                    not isinstance(starters, list)
                    or not isinstance(points, dict)
                    or any(player_id not in points or not isinstance(points[player_id], (int, float)) for player_id in active_starters)
                ):
                    player_data_complete = False
                    continue
                starter_rows.extend((player_id, float(points[player_id]), manager_id, manager_name) for player_id in active_starters)
        if player_data_complete and starter_rows:
            high_player = max(row[1] for row in starter_rows)
            for player_id, value, manager_id, manager_name in starter_rows:
                if value == high_player:
                    highlights.append(HighlightCandidate(
                        season_id, week, "Highest-scoring starter", manager_id, manager_name,
                        player_id=player_id, value=value, source_key=f"highest-starter:{player_id}",
                    ))
        # Lineup efficiency intentionally remains absent: stored matchup rows do
        # not retain the league's slot eligibility rules needed for a valid optimum.
    return highlights


def merge_weekly_highlights(
    calculated: Iterable[HighlightCandidate], manual: Iterable[HighlightCandidate]
) -> list[HighlightCandidate]:
    manual_rows = list(manual)
    overridden = {(row.week, row.category.strip().casefold()) for row in manual_rows}
    rows = [
        row for row in calculated
        if (row.week, row.category.strip().casefold()) not in overridden
    ] + manual_rows
    return sorted(rows, key=lambda row: (row.week, row.category.casefold(), row.source != "manual", row.source_key))
