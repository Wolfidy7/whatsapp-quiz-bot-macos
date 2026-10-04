"""Controlled native round with automatic enrollment; sends only to the explicit group."""

import argparse
import time
from pathlib import Path
from uuid import uuid4

from quiz_app.ax_reader import AXReader
from quiz_app.ax_sender import AXSender
from quiz_app.config import load_settings
from quiz_app.database_reader import DatabaseReader, DatabaseTransport
from quiz_app.engine import correct_round
from quiz_app.errors import QuizError
from quiz_app.history import reconcile
from quiz_app.models import Message, Question, Round, Settings
from quiz_app.storage import locked, write_json
from quiz_app.transport import Transport
from scripts.validate_transport import publish_reserved


def first_join(messages: list[Message], command: str) -> Message | None:
    """Return the first incoming exact join; reject a qualified sender without native identity."""
    for message in messages:
        if message.outgoing or message.body.strip().casefold() != command.casefold():
            continue
        if not message.author_id or not message.author:
            raise QuizError("AUTHOR_AMBIGUOUS", "The joining account has no native sender identity")
        return message
    return None


def wait_for_join(transport: Transport, marker: str, command: str, seconds: int) -> Message:
    """Poll a complete enrollment prefix until a native player joins or the bounded deadline expires."""
    deadline = time.monotonic() + seconds
    observed: list[Message] = []
    while time.monotonic() < deadline:
        current = transport.preview(marker)
        if current is not None:
            observed = reconcile(observed, current)
        player = first_join(observed, command)
        if player is not None:
            return player
        time.sleep(0.5)
    raise QuizError("NO_PLAYERS", "No other account joined before the validation deadline")


def observe_window(transport: Transport, marker: str, seconds: int) -> list[Message]:
    """Freeze observations during the answer window; fail on changed or missing earlier messages."""
    deadline = time.monotonic() + seconds
    observed: list[Message] = []
    while time.monotonic() < deadline:
        current = transport.preview(marker)
        if current is not None:
            observed = reconcile(observed, current)
        time.sleep(0.5)
    return observed


def verify_round(messages: list[Message], player: Message, settings: Settings) -> int:
    """Require three known replies from the enrolled identity in order; verify first-answer scoring."""
    incoming = [message for message in messages if not message.outgoing and message.body]
    expected = [
        f"{settings.answer_prefix} Paris",
        f"{settings.answer_prefix} Londres",
        f"{settings.answer_prefix} Paris",
    ]
    if [message.body for message in incoming] != expected:
        raise QuizError("VALIDATION_FAILED", "Replies differ from the three agreed messages or their order")
    if any(message.author_id != player.author_id or message.edited for message in incoming):
        raise QuizError("VALIDATION_FAILED", "Reply authors differ from the enrolled native identity")
    question = Question(
        id="native-validation", question="Quelle est la capitale de la France ?", answer="Paris"
    )
    round_ = Round(question=question, start_marker="verified", stop_marker="verified-stop", observed=messages)
    result = correct_round(round_, [player.author_id], settings)[0]
    if result.answer != "Paris" or result.points != settings.max_points:
        raise QuizError("VALIDATION_FAILED", "The first correct answer did not receive the expected score")
    return result.points


def validate(group: str, join_seconds: int, seconds: int, root: Path) -> None:
    """Own the service lock and run one explicitly targeted native test; never replay interrupted sends."""
    if not group.strip() or not 10 <= seconds <= 180 or not 30 <= join_seconds <= 600:
        raise QuizError("VALIDATION_INVALID", "Provide a group and bounded enrollment/answer durations")
    with locked(root / "data/service.lock"):
        settings = load_settings(root / ".env")
        reader = AXReader(group)
        source = DatabaseReader(Path(settings.whatsapp_database), group)
        source.recent(1)
        transport = DatabaseTransport(source, AXSender(reader).publish)
        (root / "data/transport-validation.json").unlink(missing_ok=True)
        run_round(transport, group, settings, join_seconds, seconds, root)


def run_round(
    transport: DatabaseTransport,
    group: str,
    settings: Settings,
    join_seconds: int,
    seconds: int,
    root: Path,
) -> None:
    """Publish enrollment/question/STOP once, persist full evidence, then announce verified scoring."""
    label = f"[validation:{uuid4().hex}"
    join = f"{label}:join]"
    path = root / f"data/diagnostics/auto-{label[12:]}.json"
    dispatches: list[dict[str, str]] = []
    publish_reserved(
        transport,
        f"Test du quiz : un autre membre peut envoyer {settings.join_command} "
        f"dans les {join_seconds} secondes pour participer. Un seul joueur pour ce test.\n{join}",
        join,
        path,
        dispatches,
    )
    print(f"Enrollment posted in {group}. Waiting for another account's {settings.join_command}…", flush=True)
    continue_round(transport, group, settings, join_seconds, seconds, root, label, dispatches)


def continue_round(
    transport: DatabaseTransport,
    group: str,
    settings: Settings,
    join_seconds: int,
    seconds: int,
    root: Path,
    label: str,
    dispatches: list[dict[str, str]],
) -> None:
    """Continue a confirmed enrollment publication; verify identities, order and score before receipt."""
    join, closed, start = [f"{label}:{name}]" for name in ("join", "closed", "question")]
    path = root / f"data/diagnostics/auto-{label[12:]}.json"
    player = wait_for_join(transport, join, settings.join_command, join_seconds)
    publish_reserved(transport, f"Inscription du test fermée.\n{closed}", closed, path, dispatches)
    enrollment = transport.segment(join, closed)
    if first_join(enrollment, settings.join_command) != player:
        raise QuizError("HISTORY_CHANGED", "Enrollment changed before its closing marker")
    print(f"Enrolled automatically: {player.author}. Posting the question.", flush=True)
    replies = " → ".join(f"{settings.answer_prefix} {answer}" for answer in ("Paris", "Londres", "Paris"))
    publish_reserved(
        transport,
        f"Question de test : quelle est la capitale de la France ?\n"
        f"Le joueur inscrit doit envoyer trois messages séparés, dans cet ordre :\n{replies}\n"
        f"Délai : {seconds} secondes. Seule la première réponse compte pour le score.\n{start}",
        start,
        path,
        dispatches,
    )
    print(f"Question posted. Send the three replies within {seconds}s.", flush=True)
    complete_answers(transport, group, settings, seconds, root, label, dispatches, player)


def complete_answers(
    transport: DatabaseTransport,
    group: str,
    settings: Settings,
    seconds: int,
    root: Path,
    label: str,
    dispatches: list[dict[str, str]],
    player: Message,
) -> None:
    """Collect a confirmed question window, publish STOP and verify the complete immutable transcript."""
    start, stop, result = [f"{label}:{name}]" for name in ("question", "stop", "result")]
    path = root / f"data/diagnostics/auto-{label[12:]}.json"
    observed = observe_window(transport, start, seconds)
    publish_reserved(transport, f"STOP\n{stop}", stop, path, dispatches)
    messages = reconcile(observed, transport.segment(start, stop))
    evidence = root / f"data/diagnostics/auto-{label[12:]}-evidence.json"
    write_json(
        evidence,
        {
            "group": group,
            "player": player.model_dump(),
            "messages": [message.model_dump() for message in messages],
            "validated": False,
        },
    )
    points = verify_round(messages, player, settings)
    write_json(
        evidence,
        {
            "group": group,
            "player": player.model_dump(),
            "messages": [message.model_dump() for message in messages],
            "validated": True,
            "points": points,
        },
    )
    publish_reserved(
        transport,
        f"Réponse : Paris.\nTest validé : 3 messages lus dans l’ordre, "
        f"auteur identifié automatiquement. Première réponse retenue : Paris.\n"
        f"Score du joueur inscrit : {points} points.\n{result}",
        result,
        path,
        dispatches,
    )
    write_json(root / "data/transport-validation.json", {"group": group, "validated": True, "schema": 2})
    print(f"Controlled native round validated. Evidence: {evidence.name}", flush=True)


def main() -> None:
    """Run only with an explicit target group; constrain native waiting periods through CLI choices."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", required=True)
    parser.add_argument("--join-seconds", type=int, choices=range(30, 601), default=180)
    parser.add_argument("--seconds", type=int, choices=range(10, 181), default=60)
    args = parser.parse_args()
    validate(args.group, args.join_seconds, args.seconds, Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    main()
