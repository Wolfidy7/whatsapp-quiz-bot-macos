"""Order reconstruction that refuses ambiguous page overlaps."""

from quiz_app.errors import QuizError
from quiz_app.models import Message


def merge_pages(older: list[Message], newer: list[Message]) -> list[Message]:
    """Merge older→newer pages only if one suffix/prefix overlap is possible."""
    left = [m.fingerprint for m in older]
    right = [m.fingerprint for m in newer]
    sizes = [size for size in range(1, min(len(left), len(right)) + 1) if left[-size:] == right[:size]]
    if len(sizes) != 1:
        raise QuizError("HISTORY_INCOMPLETE", "Page overlap is missing or ambiguous")
    size = sizes[0]
    same_native_row = bool(older[-1].native_id and older[-1].native_id == newer[0].native_id)
    if (size < 2 or len(set(left[-size:])) < 2) and not same_native_row:
        raise QuizError(
            "HISTORY_INCOMPLETE", "Single-row overlap requires a verified native element identity"
        )
    return older + newer[sizes[0] :]


def window(messages: list[Message], start: str, stop: str | None = None) -> list[Message]:
    """Extract messages strictly between unique outgoing boundary markers."""
    begins = [i for i, m in enumerate(messages) if m.outgoing and start in m.body]
    ends = [i for i, m in enumerate(messages) if m.outgoing and stop is not None and stop in m.body]
    if len(begins) != 1 or (stop is not None and (len(ends) != 1 or ends[0] <= begins[0])):
        raise QuizError("HISTORY_INCOMPLETE", "Question or STOP marker is missing, duplicate or out of order")
    return messages[begins[0] + 1 : ends[0] if ends else len(messages)]


def reconcile(previous: list[Message], current: list[Message]) -> list[Message]:
    """Keep first observations; reject deletion, editing or reordered history."""
    if [m.model_dump(exclude={"edited", "native_id"}) for m in current[: len(previous)]] != [
        m.model_dump(exclude={"edited", "native_id"}) for m in previous
    ]:
        raise QuizError("HISTORY_CHANGED", "Observed messages changed or disappeared; manual review required")
    return previous + current[len(previous) :]
