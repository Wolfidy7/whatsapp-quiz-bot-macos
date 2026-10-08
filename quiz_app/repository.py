"""Validated question-bank and session document boundaries."""

from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from quiz_app.errors import QuizError
from quiz_app.models import Question, Session
from quiz_app.storage import read_json, write_json


def validate_questions(value: object) -> list[Question]:
    """Validate a nonempty bank with unique stable IDs; reject malformed imports."""
    try:
        questions = TypeAdapter(list[Question]).validate_python(value)
        ids = [question.id for question in questions]
        if not ids or len(ids) > 1000 or len(ids) != len(set(ids)):
            raise ValueError("Question IDs must be unique; bank cannot be empty")
        return questions
    except (ValidationError, ValueError) as exc:
        raise QuizError("BANK_INVALID", str(exc)) from exc


def load_bank(path: Path) -> list[Question]:
    """Read and validate a JSON question bank without repairing corrupt content."""
    return validate_questions(read_json(path))


def save_bank(path: Path, questions: object) -> list[Question]:
    """Validate before atomic replacement; return the canonical saved bank."""
    validated = validate_questions(questions)
    write_json(path, [question.model_dump() for question in validated])
    return validated


def load_session(path: Path) -> Session:
    """Validate a durable snapshot; callers must explicitly recover interrupted games."""
    try:
        session = Session.model_validate(read_json(path))
        validate_snapshot(session)
        return session
    except ValidationError as exc:
        raise QuizError("SESSION_INVALID", "Invalid saved session schema") from exc


def validate_snapshot(session: Session) -> None:
    """Reject contradictory enrollment, question counts or duplicate outgoing reservations."""
    if (
        len(set(session.players)) != len(session.players)
        or len(session.players) > session.settings.max_players
    ):
        raise QuizError("SESSION_INVALID", "Invalid enrolled-player snapshot")
    ids = [question.id for question in session.questions]
    if len(set(ids)) != len(ids) or len(ids) > session.settings.max_questions:
        raise QuizError("SESSION_INVALID", "Invalid question snapshot")
    markers = [item.marker for item in session.outbox]
    if len(set(markers)) != len(markers):
        raise QuizError("SESSION_INVALID", "Duplicate outgoing reservations")
    validate_rounds(session)


def validate_rounds(session: Session) -> None:
    """Require round questions and corrected rosters to agree with the frozen snapshot."""
    if len(session.rounds) > len(session.questions) or (session.phase == "answering" and not session.rounds):
        raise QuizError("SESSION_INVALID", "Invalid round count")
    for index, round_ in enumerate(session.rounds):
        if round_.question != session.questions[index]:
            raise QuizError("SESSION_INVALID", "Round question differs from frozen bank")
        if round_.results and [row.player for row in round_.results] != session.players:
            raise QuizError("SESSION_INVALID", "Round results differ from frozen roster")
