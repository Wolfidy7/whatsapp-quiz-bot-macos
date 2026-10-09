"""Read-only provisional dashboard projections, kept separate from confirmed game results."""

from quiz_app.engine import correct_round, display_name
from quiz_app.grading import offline
from quiz_app.models import Result, Session
from quiz_app.scoring import standings


def current_results(session: Session) -> list[Result]:
    """Project first answers during an open round with local matching only; jev grades at STOP.

    Calling jev here would run on every dashboard refresh and could delay the STOP publication.
    """
    if not session.rounds:
        return []
    round_ = session.rounds[-1]
    if session.phase == "answering":
        return correct_round(round_, session.players, session.settings, offline)
    return round_.results


def live_view(session: Session) -> dict[str, object]:
    """Expose participants, response status and totals, marking open-round points as provisional."""
    current = current_results(session)
    rounds = [round_.results for round_ in session.rounds]
    if rounds:
        rounds[-1] = current
    confirmed = {
        str(row["player"]): row["points"]
        for row in standings(session.players, [r.results for r in session.rounds])
    }
    answers = {result.player: result for result in current}
    rows = []
    for row in standings(session.players, rounds):
        key = str(row["player"])
        result = answers.get(key, Result(player=key))
        rows.append(
            dict(
                row,
                name=display_name(session, key),
                confirmed_points=confirmed[key],
                round_points=result.points,
                answered=bool(result.answer),
            )
        )
    return {"ranking": rows, "provisional": session.phase == "answering"}
