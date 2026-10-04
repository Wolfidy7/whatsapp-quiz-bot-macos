"""Rank-based points with a denominator fixed by registration."""

from decimal import ROUND_HALF_UP, Decimal

from quiz_app.models import Result


def points_for_rank(rank: int, players: int, maximum: int = 100, minimum: int = 20) -> int:
    """Return half-up rounded points; reject impossible ranks or invalid bounds."""
    if not 1 <= rank <= players or not 1 <= minimum <= maximum:
        raise ValueError("Invalid rank, participant count or score bounds")
    if players == 1:
        return maximum
    value = Decimal(maximum) - Decimal(maximum - minimum) * Decimal(rank - 1) / Decimal(players - 1)
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def standings(players: list[str], rounds: list[list[Result]]) -> list[dict[str, object]]:
    """Return cumulative totals with competition ranks and stable names for ties."""
    totals = {
        player: sum(r.points for rows in rounds for r in rows if r.player == player) for player in players
    }
    ordered = sorted(totals, key=lambda player: (-totals[player], player.casefold()))
    return [
        {
            "player": player,
            "points": totals[player],
            "rank": 1 + sum(score > totals[player] for score in totals.values()),
        }
        for player in ordered
    ]
