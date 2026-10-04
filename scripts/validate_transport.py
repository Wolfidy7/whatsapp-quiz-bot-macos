"""Explicit manual validation in Test; requires known replies from another account."""

import argparse
import time
from pathlib import Path
from uuid import uuid4

from quiz_app.ax_reader import AXReader
from quiz_app.ax_sender import AXSender
from quiz_app.config import load_settings
from quiz_app.database_reader import DatabaseReader, DatabaseTransport
from quiz_app.errors import QuizError
from quiz_app.storage import locked, read_json, write_json


def validate(expected_path: Path, seconds: int, root: Path) -> None:
    """Send boundaries in Test only, verify known ordered incoming replies, save a receipt."""
    with locked(root / "data/service.lock"):
        run_validation(expected_path, seconds, root)


def run_validation(expected_path: Path, seconds: int, root: Path) -> None:
    """Validate a fixture under the service lock; propagate source and publication incidents."""
    expected = read_json(expected_path)
    if not valid_fixture(expected) or not 10 <= seconds <= 60:
        raise QuizError("VALIDATION_INVALID", "Provide at least three known replies as author/body objects")
    (root / "data/transport-validation.json").unlink(missing_ok=True)
    reader = AXReader("Test")
    source = DatabaseReader(Path(load_settings(root / ".env").whatsapp_database), "Test")
    source.recent(1)
    transport = DatabaseTransport(source, AXSender(reader).publish)
    id_ = uuid4().hex
    start, stop = f"[validation:{id_}:question]", f"[validation:{id_}:stop]"
    path = root / f"data/diagnostics/validation-{id_}.json"
    dispatches: list[dict[str, str]] = []
    publish_reserved(
        transport,
        f"Transport validation: reply in the agreed order within {seconds}s.\n{start}",
        start,
        path,
        dispatches,
    )
    print("Question sent in Test. Waiting for the known replies…", flush=True)
    time.sleep(seconds)
    publish_reserved(transport, f"STOP\n{stop}", stop, path, dispatches)
    messages = transport.segment(start, stop)
    incoming = [
        {"author": message.author, "body": message.body} for message in messages if not message.outgoing
    ]
    if incoming != expected or any(message.edited for message in messages):
        raise QuizError(
            "VALIDATION_FAILED", "Incoming authors, replies or order differ from the agreed fixture"
        )
    write_json(root / "data/transport-validation.json", {"group": "Test", "validated": True, "schema": 2})
    print("Complete controlled native window validated for Test.")


def valid_fixture(value: object) -> bool:
    """Accept only at least three nonblank exact author/body objects; never publish on malformed input."""
    if not isinstance(value, list) or len(value) < 3:
        return False
    return all(
        isinstance(item, dict)
        and set(item) == {"author", "body"}
        and all(isinstance(field, str) and field.strip() for field in item.values())
        for item in value
    )


def publish_reserved(
    transport: DatabaseTransport,
    text: str,
    marker: str,
    path: Path,
    dispatches: list[dict[str, str]],
) -> None:
    """Write a pending reservation before one send; leave evidence pending if sending raises."""
    item = {"marker": marker, "text": text, "status": "pending"}
    dispatches.append(item)
    write_json(path, dispatches)
    transport.send(text, marker)
    item["status"] = "sent"
    write_json(path, dispatches)


def main() -> None:
    """Require an explicit expected fixture and bounded observation delay before any send."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--seconds", type=int, choices=range(10, 61), default=30)
    args = parser.parse_args()
    validate(args.expected, args.seconds, Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    main()
