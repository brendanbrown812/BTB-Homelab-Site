from app.features.predictions.models import PickResult


def score_pick(selected_roster_id: int | None, winner_roster_id: int | None, tied: bool) -> PickResult:
    """A blank is a loss; actual matchup ties are pushes for everyone."""
    if tied:
        return PickResult.push
    if selected_roster_id is None:
        return PickResult.loss
    return PickResult.win if selected_roster_id == winner_roster_id else PickResult.loss


def record(results: list[PickResult]) -> dict[str, int]:
    return {kind.value: results.count(kind) for kind in PickResult}
