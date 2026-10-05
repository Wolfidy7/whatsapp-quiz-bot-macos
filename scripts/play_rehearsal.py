"""Run an explicitly requested native quiz rehearsal with the normal game engine."""

import argparse
import time
from pathlib import Path

from pydantic import ValidationError

from quiz_app.ax_reader import AXReader
from quiz_app.ax_sender import AXSender
from quiz_app.config import load_settings
from quiz_app.database_reader import DatabaseReader, DatabaseTransport
from quiz_app.engine import Engine, collect_players, display_name, marker, new_session, report
from quiz_app.errors import QuizError
from quiz_app.models import Settings
from quiz_app.repository import load_bank
from quiz_app.storage import locked


def check_enrollment(engine: Engine, required: int) -> None:
    """Require the chosen player count at closure; raise before publishing any question if incomplete."""
    if engine.session.phase != "registration" or engine.clock() < engine.session.deadline:
        return
    messages = engine.transport.segment(marker(engine.session, "join.0"))
    count = len(collect_players(messages, engine.session.settings))
    if count != required:
        raise QuizError("ENROLLMENT_INCOMPLETE", f"Expected {required} registered players; received {count}")


def show_state(engine: Engine) -> None:
    """Print enrolled labels, phase and confirmed per-round or final standings."""
    session = engine.session
    names = [display_name(session, key) for key in session.players]
    print(f"{session.phase} · players: {names} · question {len(session.rounds)}", flush=True)
    if session.phase in ("interval", "finished"):
        print(report(session, final=session.phase == "finished"), flush=True)


def drive(engine: Engine) -> None:
    """Poll a single engine, print confirmed standings and persist incidents without replaying sends."""
    previous: tuple[str, int, int] | None = None
    try:
        engine.begin()
        while engine.session.phase not in ("finished", "paused", "cancelled"):
            check_enrollment(engine, engine.session.settings.max_players)
            engine.tick()
            state = (engine.session.phase, len(engine.session.players), len(engine.session.rounds))
            if state != previous:
                show_state(engine)
                previous = state
            if engine.session.phase not in ("finished", "paused", "cancelled"):
                time.sleep(engine.session.settings.poll_seconds)
    except QuizError as error:
        engine.pause(error)
    if engine.session.phase == "paused":
        raise QuizError("GAME_PAUSED", engine.session.error)


def play(args: argparse.Namespace, root: Path) -> None:
    """Validate temporary overrides, own the service lock and publish one explicitly selected real game."""
    defaults = load_settings(root / ".env")
    updates = {
        key: value
        for key, value in {
            "whatsapp_group": args.group,
            "max_players": args.players,
            "registration_seconds": args.join_seconds,
            "question_seconds": args.seconds,
        }.items()
        if value is not None
    }
    try:
        settings = Settings.model_validate(defaults.model_dump() | updates)
    except ValidationError as error:
        raise QuizError("CONFIG_INVALID", "Invalid rehearsal settings") from error
    bank = load_bank(args.questions or root / "data/questions.json")
    with locked(root / "data/service.lock"):
        reader = AXReader(settings.whatsapp_group)
        source = DatabaseReader(Path(settings.whatsapp_database), settings.whatsapp_group)
        source.recent(1)
        transport = DatabaseTransport(source, AXSender(reader).publish)
        session = new_session(settings, bank, "native")
        path = root / f"data/sessions/{session.id}.json"
        engine = Engine(session, transport, path, time.time)
        print(
            f"Real rehearsal: {settings.whatsapp_group} · {settings.max_players} players · "
            f"{len(session.questions)} questions. Archive: {session.id}",
            flush=True,
        )
        drive(engine)


def main() -> None:
    """Parse real-game options; print classified failures without creating a validation receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group")
    parser.add_argument("--players", type=int)
    parser.add_argument("--questions", type=Path)
    parser.add_argument("--join-seconds", type=int)
    parser.add_argument("--seconds", type=int)
    args = parser.parse_args()
    try:
        play(args, Path(__file__).resolve().parents[1])
    except QuizError as error:
        raise SystemExit(f"{error.code}: {error}") from error


if __name__ == "__main__":
    main()
