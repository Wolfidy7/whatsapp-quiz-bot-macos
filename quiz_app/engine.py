"""Deterministic, recoverable round orchestration; no timer or UI dependencies."""

from collections.abc import Callable
from pathlib import Path
from typing import cast
from uuid import uuid4

from quiz_app.errors import QuizError
from quiz_app.grading import evaluate_answer, extract_answer
from quiz_app.history import reconcile_game
from quiz_app.messages import (
    REGISTRATION_CLOSED,
    STOP,
    cancellation,
    next_question_delay,
    question_prompt,
    registration,
    score_line,
    scoreboard,
    solution,
)
from quiz_app.models import Dispatch, Message, Question, Result, Round, Session, Settings
from quiz_app.scoring import points_for_rank, standings
from quiz_app.storage import write_json
from quiz_app.transport import Simulator, Transport


def marker(session: Session, suffix: str) -> str:
    """Return a private session-scoped correlation key for an outgoing boundary."""
    return f"[quiz:{session.id}:{suffix}]"


def player_key(message: Message) -> str:
    """Prefer the stable native sender identity, falling back to simulator display names."""
    return message.author_id or message.author


def registration_names(messages: list[Message], players: list[str], command: str) -> dict[str, str]:
    """Freeze each enrolled player's label from their first valid registration message."""
    names: dict[str, str] = {}
    for message in messages:
        key = player_key(message)
        if key in players and message.body.strip().casefold() == command.casefold():
            names.setdefault(key, message.author)
    return names


def display_name(session: Session, key: str) -> str:
    """Display frozen labels, distinguishing identical names with their enrollment numbers."""
    name = session.player_names.get(key, key)
    duplicate = list(session.player_names.values()).count(name) > 1
    return f"{name} (joueur {list(session.player_names).index(key) + 1})" if duplicate else name


def collect_players(messages: list[Message], settings: Settings) -> list[str]:
    """Extract unique first registrations in conversation order, up to the cap."""
    players: list[str] = []
    for message in messages:
        if message.outgoing or message.body.strip().casefold() != settings.join_command.casefold():
            continue
        if not player_key(message).strip():
            raise QuizError("AUTHOR_AMBIGUOUS", "A registration has no identifiable author")
        if player_key(message) not in players and len(players) < settings.max_players:
            players.append(player_key(message))
    return players


def correct_round(round_: Round, players: list[str], settings: Settings) -> list[Result]:
    """Freeze the first qualified answer per player and rank only correct replies."""
    first: dict[str, str] = {}
    for message in round_.observed:
        answer = extract_answer(message.body, settings.answer_prefix)
        if message.outgoing or answer is None:
            continue
        if not player_key(message).strip():
            raise QuizError("AUTHOR_AMBIGUOUS", "An answer has no identifiable author")
        key = player_key(message)
        if key in players and key not in first:
            first[key] = answer
    return grade_answers(first, players, round_.question, settings)


def grade_answers(
    first: dict[str, str], players: list[str], question: Question, settings: Settings
) -> list[Result]:
    """Grade first answers in their insertion order; include absent players at zero."""
    results: dict[str, Result] = {}
    rank = 0
    for player, answer in first.items():
        verdict = evaluate_answer(question, answer, settings.ignore_accents)
        accepted, alias = verdict.accepted, verdict.alias
        rank += int(accepted)
        points = (
            points_for_rank(rank, len(players), settings.max_points, settings.min_points) if accepted else 0
        )
        results[player] = Result(
            player=player,
            answer=answer,
            accepted=accepted,
            alias=alias,
            reason=verdict.reason,
            rank=rank if accepted else None,
            points=points,
        )
    return [results.get(player, Result(player=player)) for player in players]


def split_position(text: str, limit: int) -> int:
    """Prefer a complete paragraph or line within the limit; hard-cut oversized individual lines."""
    for separator in ("\n\n", "\n"):
        position = text.rfind(separator, 0, limit)
        if position > 0:
            return position + len(separator)
    return limit


def split_message(text: str, limit: int) -> list[str]:
    """Split long reports at layout boundaries where possible, preserving every character."""
    if limit < 1:
        raise ValueError("Message limit must be positive")
    chunks = []
    while len(text) > limit:
        position = split_position(text, limit)
        chunks.append(text[:position])
        text = text[position:]
    return [*chunks, text]


def player_details(player: str, rounds: list[list[Result]]) -> str:
    """Return one player's points per completed question in question order."""
    return " · ".join(
        f"Q{index}: {next(result.points for result in results if result.player == player)} pts"
        for index, results in enumerate(rounds, 1)
    )


def report(session: Session, final: bool = False) -> str:
    """Build an ordered scoreboard and optional complete per-question breakdown."""
    rounds = [round_.results for round_ in session.rounds]
    lines = []
    for row in standings(session.players, rounds):
        player = str(row["player"])
        details = player_details(player, rounds)
        lines.append(
            score_line(
                cast(int, row["rank"]),
                display_name(session, player),
                cast(int, row["points"]),
                details if final else None,
            )
        )
    return scoreboard(lines, final)


class Engine:
    """Single-owner state machine: reserve, publish, confirm, then advance."""

    def __init__(
        self,
        session: Session,
        transport: Transport,
        path: Path,
        clock: Callable[[], float],
        cancel_requested: Callable[[], bool] = lambda: False,
    ) -> None:
        """Bind a snapshot, transport, private destination and injected wall clock."""
        self.session = session
        self.transport = transport
        self.path = path
        self.clock = clock
        self.cancel_requested = cancel_requested

    def save(self) -> None:
        """Durably save all session state; storage errors stop the caller."""
        if isinstance(self.transport, Simulator):
            self.session.conversation = self.transport.messages.copy()
        write_json(self.path, self.session.model_dump(mode="json"))

    def publish(self, text: str, suffix: str) -> None:
        """Reserve each chunk before delivery; leave pending on any uncertain result."""
        limit = self.session.settings.message_chunk_size
        for index, chunk in enumerate(split_message(text, max(1, limit))):
            label = marker(self.session, f"{suffix}.{index}")
            previous = next((item for item in self.session.outbox if item.marker == label), None)
            if previous is not None:
                if previous.status == "pending":
                    raise QuizError("PUBLICATION_UNCERTAIN", "Resolve the pending message before continuing")
                continue
            item = Dispatch(marker=label, text=chunk)
            self.session.outbox.append(item)
            self.save()
            self.deliver(item.text, label)
            item.status = "sent"
            self.save()

    def deliver(self, text: str, label: str) -> None:
        """Classify unexpected transport errors as uncertain; never retry delivery."""
        try:
            if self.cancel_requested():
                raise QuizError("GAME_CANCELLED", "Arrêt demandé")
            self.transport.send(text, label)
        except QuizError:
            raise
        except Exception as exc:
            raise QuizError("PUBLICATION_UNCERTAIN", "Transport failed before confirmation") from exc

    def begin(self) -> None:
        """Announce registration and set its deadline only after confirmed publication."""
        self.publish(registration(self.session.settings), "join")
        self.session.deadline = self.clock() + self.session.settings.registration_seconds
        self.save()

    def tick(self) -> None:
        """Perform one deterministic transition; pause on any classified incident."""
        actions = {"registration": self.registration, "answering": self.answering, "interval": self.interval}
        action = actions.get(self.session.phase)
        if action is None:
            return
        if self.cancel_requested():
            self.cancel()
            return
        try:
            action()
        except QuizError as exc:
            self.handle_incident(exc)

    def handle_incident(self, error: QuizError) -> None:
        """Treat operator cancellation as terminal, keeping other incidents available for recovery."""
        if error.code == "GAME_CANCELLED":
            self.cancel()
        else:
            self.pause(error)

    def pause(self, error: QuizError) -> None:
        """Persist the interrupted phase and human-readable reason; never replay a send."""
        self.session.resume_phase = self.session.phase
        self.session.phase = "paused"
        self.session.error = f"{error.code}: {error}"
        self.save()

    def observe(self, start: str, stop: str | None, previous: list[Message]) -> list[Message]:
        """Use fast provisional prefixes during play and a complete traversal after STOP."""
        current = self.transport.segment(start, stop) if stop is not None else self.transport.preview(start)
        return (
            previous
            if current is None
            else reconcile_game(
                previous,
                current,
                self.session.settings.join_command,
                self.session.settings.answer_prefix,
            )
        )

    def registration(self) -> None:
        """Collect join messages, then freeze enrollment between two confirmed markers."""
        start = marker(self.session, "join.0")
        stop = marker(self.session, "join-stop.0") if self.clock() >= self.session.deadline else None
        if stop is not None:
            self.publish(REGISTRATION_CLOSED, "join-stop")
        self.session.registration_observed = self.observe(start, stop, self.session.registration_observed)
        self.session.players = collect_players(self.session.registration_observed, self.session.settings)
        self.session.player_names = registration_names(
            self.session.registration_observed, self.session.players, self.session.settings.join_command
        )
        self.save()
        if stop is not None:
            self.close_enrollment()

    def close_enrollment(self) -> None:
        """Start after complete enrollment, or announce and persist cancellation below the minimum."""
        count = len(self.session.players)
        minimum = self.session.settings.nb_players_expected
        if count < minimum:
            reason = cancellation(count, minimum)
            self.publish(reason, "cancel-enrollment")
            self.session.error = f"ENROLLMENT_INCOMPLETE: {reason}"
            self.cancel()
            return
        self.next_round()

    def next_round(self) -> None:
        """Prepare a round once, publish its question, then start the answer deadline."""
        index = len(self.session.rounds)
        question = self.session.questions[index]
        round_ = Round(
            question=question,
            start_marker=marker(self.session, f"q{index}.0"),
            stop_marker=marker(self.session, f"stop{index}.0"),
        )
        self.publish(
            question_prompt(question, index + 1, len(self.session.questions), self.session.settings),
            f"q{index}",
        )
        self.session.rounds.append(round_)
        self.session.phase = "answering"
        self.session.deadline = self.clock() + self.session.settings.question_seconds
        self.save()

    def answering(self) -> None:
        """Collect the full question window and close it strictly at the STOP marker."""
        round_ = self.session.rounds[-1]
        stopped = self.clock() >= self.session.deadline
        if stopped:
            self.publish(STOP, f"stop{len(self.session.rounds) - 1}")
        round_.observed = self.observe(
            round_.start_marker, round_.stop_marker if stopped else None, round_.observed
        )
        self.save()
        if stopped:
            self.finish_round(round_)

    def finish_round(self, round_: Round) -> None:
        """Correct a complete frozen window, report it, and schedule the next round."""
        round_.results = correct_round(round_, self.session.players, self.session.settings)
        self.save()
        text = solution(round_.question) + "\n\n" + report(self.session)
        if len(self.session.rounds) < len(self.session.questions):
            text += "\n\n" + next_question_delay(self.session.settings.interval_seconds)
        self.publish(text, f"result{len(self.session.rounds)}")
        self.session.phase = "interval"
        self.session.deadline = self.clock() + self.session.settings.interval_seconds
        self.save()

    def interval(self) -> None:
        """Wait between rounds or publish the final complete results exactly once."""
        if self.clock() < self.session.deadline:
            return
        if len(self.session.rounds) < len(self.session.questions):
            self.next_round()
            return
        self.publish(report(self.session, final=True), "final")
        self.session.phase = "finished"
        self.save()

    def recover(self) -> None:
        """Confirm pending markers against complete history and resume only by explicit action."""
        if self.session.phase != "paused":
            raise QuizError("RECOVERY_INVALID", "Only a paused session can resume")
        for item in self.session.outbox:
            if item.status == "pending":
                self.transport.segment(item.marker)
                item.status = "sent"
        if self.session.resume_phase not in ("registration", "answering", "interval"):
            raise QuizError("RECOVERY_INVALID", "This archive has no resumable game phase")
        restored = self.session.model_copy(update={"phase": self.session.resume_phase})
        self.session = Session.model_validate(restored.model_dump())
        self.session.error = ""
        self.save()
        if self.session.deadline == 0:
            self.begin()

    def cancel(self) -> None:
        """Stop future actions locally without issuing an unrequested WhatsApp message."""
        self.session.phase = "cancelled"
        self.save()


def new_session(settings: Settings, questions: list[Question], mode: str) -> Session:
    """Validate a fresh snapshot with a unique ID and configured question limit."""
    return Session.model_validate(
        dict(
            id=uuid4().hex,
            settings=settings,
            questions=questions[: settings.max_questions],
            mode=mode,
            phase="registration",
        )
    )
