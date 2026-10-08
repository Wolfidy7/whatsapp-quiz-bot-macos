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


def is_boundary(message: Message, key: str | None) -> bool:
    """Match private native metadata or a legacy visible marker on an outgoing record only."""
    return key is not None and message.outgoing and (message.native_id == key or key in message.body)


def window(messages: list[Message], start: str, stop: str | None = None) -> list[Message]:
    """Extract messages strictly between unique outgoing native identities or legacy markers."""
    begins = [i for i, m in enumerate(messages) if is_boundary(m, start)]
    ends = [i for i, m in enumerate(messages) if is_boundary(m, stop)]
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


def freeze_observation(old: Message, new: Message) -> Message:
    """Keep the first text, checking sender and native ordering metadata; reject identity changes."""
    fields = ("author_id", "outgoing", "timestamp")
    if any(getattr(old, key) != getattr(new, key) for key in fields):
        raise QuizError("HISTORY_CHANGED", "An observed message's identity metadata changed")
    if old.sequence is not None and old.sequence != new.sequence:
        raise QuizError("HISTORY_CHANGED", "An observed native sequence changed")
    return old if old.sequence is not None else old.model_copy(update={"sequence": new.sequence})


def check_observation_order(previous: list[Message], current: list[Message]) -> None:
    """Reject duplicated identities and reordered surviving messages, allowing deleted rows to disappear."""
    positions = {message.fingerprint: index for index, message in enumerate(previous)}
    ids = [message.fingerprint for message in current]
    shared = [positions[key] for key in ids if key in positions]
    if len(positions) != len(previous) or len(set(ids)) != len(ids) or shared != sorted(shared):
        raise QuizError("HISTORY_CHANGED", "Message identities are duplicated or reordered")


def chronological_observations(messages: list[Message]) -> list[Message]:
    """Sort native observations by sequence; retain legacy snapshot order when sequence is unavailable."""
    sequences = [message.sequence for message in messages]
    if None in sequences:
        return messages
    if len(set(sequences)) != len(sequences):
        raise QuizError("HISTORY_CHANGED", "Distinct observed messages share a native sequence")
    return sorted(messages, key=lambda message: message.sequence or 0)


def reconcile_game(previous: list[Message], current: list[Message], join: str, prefix: str) -> list[Message]:
    """Keep first texts across edits/deletions; skip empty records and merge replies in native order."""
    previous = [message for message in previous if message.body.strip()]
    current = [message for message in current if message.body.strip()]
    check_observation_order(previous, current)
    frozen = {message.fingerprint: message for message in previous}
    for message in current:
        old = frozen.get(message.fingerprint)
        frozen[message.fingerprint] = message if old is None else freeze_observation(old, message)
    return chronological_observations(list(frozen.values()))
