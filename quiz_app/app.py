"""Loopback-only HTTP control plane with serialized game and storage mutations."""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from threading import Event, RLock
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from quiz_app.ax_reader import AXReader
from quiz_app.ax_sender import AXSender
from quiz_app.config import load_api_key, load_remote_hosts, load_settings, save_settings
from quiz_app.database_reader import DatabaseReader, DatabaseTransport
from quiz_app.engine import Engine, new_session
from quiz_app.errors import QuizError
from quiz_app.grading import Scorer, evaluate_answer, jev_scorer, local_verdict
from quiz_app.live import live_view
from quiz_app.models import Question, Settings, StrictModel
from quiz_app.repository import load_bank, load_session, save_bank
from quiz_app.storage import locked, read_json
from quiz_app.transport import Simulator, Transport

ROOT = Path(__file__).resolve().parent.parent


class StartRequest(StrictModel):
    """Explicit transport and selected question IDs; native runs need validation."""

    mode: Literal["simulation", "native"]
    question_ids: list[str] = Field(min_length=1, max_length=1000)
    settings: Settings | None = None
    rehearsal: bool = False


class Injection(StrictModel):
    """Bounded fake player input for simulations only."""

    author: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=4000)


class AnswerTest(StrictModel):
    """Question draft and candidate answer for the jev tester; unset options use saved defaults."""

    question: Question
    answer: str = Field(max_length=4000)
    ignore_accents: bool | None = None
    jev_threshold: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    jev_model: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,80}$")


class Controller:
    """Serialize all actions and hold at most one active local game."""

    def __init__(self, root: Path) -> None:
        """Bind local private files without opening WhatsApp or starting a game."""
        self.root = root
        self.lock = RLock()
        self.engine: Engine | None = None
        self.stop_requested = Event()

    def start(self, value: StartRequest) -> dict[str, object]:
        """Start one immutable game snapshot; require validation or explicit native rehearsal."""
        with self.lock:
            if self.engine and self.engine.session.phase not in ("finished", "cancelled"):
                raise QuizError("GAME_ACTIVE", "Cancel the current game before starting another")
            self.stop_requested.clear()
            try:
                return self.initialize(value)
            except QuizError as error:
                if error.code == "GAME_CANCELLED":
                    return {"phase": "cancelled", "stop_requested": True}
                raise

    def initialize(self, value: StartRequest) -> dict[str, object]:
        """Build a settings snapshot and transport, then start once under the controller owner lock."""
        settings = value.settings or load_settings(self.root / ".env")
        bank = {question.id: question for question in load_bank(self.root / "data/questions.json")}
        if (
            len(set(value.question_ids)) != len(value.question_ids)
            or not set(value.question_ids) <= bank.keys()
        ):
            raise QuizError("BANK_INVALID", "Sélectionnez des questions existantes, sans doublons")
        session = new_session(settings, [bank[id_] for id_ in value.question_ids], value.mode)
        session.rehearsal = value.rehearsal
        self.engine = Engine(
            session,
            self.transport(
                value.mode,
                settings.whatsapp_group,
                settings.max_history_pages,
                settings.whatsapp_database,
                value.rehearsal,
            ),
            self.root / f"data/sessions/{session.id}.json",
            time.time,
            self.stop_requested.is_set,
            self.scorer(settings),
        )
        try:
            self.engine.begin()
        except QuizError as exc:
            self.engine.handle_incident(exc)
        return self.state()

    def scorer(self, settings: Settings) -> Scorer:
        """Build the snapshot's jev scorer from the private key; no key means local fallback only."""
        return jev_scorer(load_api_key(self.root / ".env"), settings.jev_model)

    def transport(
        self, mode: str, group: str, max_pages: int, database: str, rehearsal: bool = False
    ) -> Transport:
        """Build the chosen transport; native use requires validation or explicit rehearsal."""
        if mode == "simulation":
            return Simulator()
        path = self.root / "data/transport-validation.json"
        if not rehearsal and (
            not path.exists() or read_json(path) != {"group": group, "validated": True, "schema": 2}
        ):
            raise QuizError(
                "TRANSPORT_UNVALIDATED", "Run the controlled native test before starting a real game"
            )
        reader = AXReader(group, max_pages, require_active=False, launch=True)
        source = DatabaseReader(Path(database), group)
        source.recent(1)
        sender = AXSender(reader, self.stop_requested.is_set)
        sender.open_group()
        return DatabaseTransport(source, sender.publish, self.root / "data/native-deliveries.json")

    def state(self) -> dict[str, object]:
        """Return a fresh JSON-safe snapshot for the dashboard."""
        with self.lock:
            if self.engine is None:
                return {}
            return dict(
                self.engine.session.model_dump(mode="json"),
                live=live_view(self.engine.session),
                stop_requested=self.stop_requested.is_set(),
            )

    def tick(self) -> None:
        """Advance a game under its single mutation lock; preserve storage incidents."""
        with self.lock:
            if self.engine and self.engine.session.phase not in ("finished", "cancelled"):
                try:
                    if self.stop_requested.is_set():
                        self.engine.cancel()
                    else:
                        self.engine.tick()
                except QuizError as exc:
                    self.engine.session.phase = "paused"
                    self.engine.session.error = f"{exc.code}: {exc}"

    def inject(self, value: Injection) -> dict[str, object]:
        """Append simulated player input and collect it immediately; reject native mode."""
        with self.lock:
            engine = self.require_engine()
            if not isinstance(engine.transport, Simulator):
                raise QuizError("MODE_INVALID", "Fake replies are available only in simulation")
            engine.transport.inject(value.author, value.body)
            engine.tick()
            return self.state()

    def require_engine(self) -> Engine:
        """Return the active controller or raise a user-facing missing-game error."""
        if self.engine is None:
            raise QuizError("NO_GAME", "No game is loaded")
        return self.engine

    def cancel(self) -> dict[str, object]:
        """Signal Stop immediately, even during native work; persist cancellation once the owner is free."""
        self.stop_requested.set()
        if not self.lock.acquire(blocking=False):
            return {"stop_requested": True}
        try:
            self.require_engine().cancel()
            return self.state()
        finally:
            self.lock.release()

    def resume(self) -> dict[str, object]:
        """Resume a paused game only after every uncertain send is found in history."""
        with self.lock:
            self.stop_requested.clear()
            self.require_engine().recover()
            return self.state()

    def recover(self, session_id: str) -> dict[str, object]:
        """Load a saved session paused; preserve evidence and require operator cancellation."""
        with self.lock:
            if len(session_id) != 32 or any(char not in "0123456789abcdef" for char in session_id):
                raise QuizError("SESSION_INVALID", "Invalid session identifier")
            session = load_session(self.root / f"data/sessions/{session_id}.json")
            if self.engine and self.engine.session.phase not in ("finished", "cancelled"):
                raise QuizError("GAME_ACTIVE", "Cancel the current game before loading an archive")
            self.stop_requested.clear()
            transport = self.transport(
                session.mode,
                session.settings.whatsapp_group,
                session.settings.max_history_pages,
                session.settings.whatsapp_database,
                session.rehearsal,
            )
            if isinstance(transport, Simulator):
                transport.messages = session.conversation.copy()
                observed = session.registration_observed + [m for r in session.rounds for m in r.observed]
                transport.sequence = max((m.sequence or 0 for m in observed + transport.messages), default=0)
            self.engine = Engine(
                session,
                transport,
                self.root / f"data/sessions/{session_id}.json",
                time.time,
                self.stop_requested.is_set,
                self.scorer(session.settings),
            )
            if session.phase != "paused":
                self.engine.pause(
                    QuizError("RECOVERY_REQUIRED", "Archive loaded paused; no messages replayed")
                )
            return self.state()


async def run_clock(controller: Controller) -> None:
    """Poll the serialized engine once per second; propagate unexpected worker failures."""
    while True:
        await asyncio.to_thread(controller.tick)
        delay = controller.engine.session.settings.poll_seconds if controller.engine else 1
        await asyncio.sleep(delay)


def make_lifespan(
    controller: Controller, background: bool
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Create an owned timer lifecycle for the injected controller."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Cancel the timer on shutdown; never replay a saved session."""
        task = asyncio.create_task(run_clock(controller)) if background else None
        try:
            with locked(controller.root / "data/service.lock"):
                yield
        finally:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    return lifespan


LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "testserver"})
Boundary = Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]


def local_boundary(remote_hosts: frozenset[str] = frozenset()) -> Boundary:
    """Reject foreign hosts and origins; remote hosts are only reachable through the HTTPS Tailscale proxy."""

    async def boundary(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        hostname = request.url.hostname
        if hostname not in LOCAL_HOSTS | remote_hosts:
            return JSONResponse({"error": "HOST_FORBIDDEN"}, status_code=403)
        host = request.headers.get("host")
        allowed = {f"{request.url.scheme}://{host}"}
        if hostname in remote_hosts:
            # tailscale serve terminates HTTPS and forwards plain HTTP to the loopback port.
            allowed.add(f"https://{host}")
        origin = request.headers.get("origin")
        if origin and origin not in allowed:
            return JSONResponse({"error": "ORIGIN_FORBIDDEN"}, status_code=403)
        if request.method in ("POST", "PUT") and len(await request.body()) > 1_000_000:
            return JSONResponse({"error": "PAYLOAD_TOO_LARGE"}, status_code=413)
        return await call_next(request)

    return boundary


def create_app(root: Path = ROOT, background: bool = True) -> FastAPI:
    """Build the local app with private root injection for isolated integration tests."""
    controller = Controller(root)

    app = FastAPI(title="WhatsApp Quiz · local", lifespan=make_lifespan(controller, background))
    app.state.controller = controller
    app.middleware("http")(local_boundary(load_remote_hosts(root / ".env")))

    @app.exception_handler(QuizError)
    async def incident(request: Request, error: QuizError) -> JSONResponse:
        """Return classified errors without leaking filesystem paths or tracebacks."""
        return JSONResponse({"error": error.code, "message": str(error)}, status_code=409)

    @app.get("/api/questions")
    def questions() -> list[Question]:
        """Read the validated question bank for editing and export."""
        return load_bank(root / "data/questions.json")

    @app.put("/api/questions")
    def update_questions(values: list[Question]) -> list[Question]:
        """Validate and atomically replace the bank without changing a running snapshot."""
        with controller.lock:
            return save_bank(root / "data/questions.json", [value.model_dump() for value in values])

    @app.post("/api/test-answer")
    def test_answer(value: AnswerTest) -> dict[str, object]:
        """Score one draft answer with jev using the form's options, falling back to saved defaults."""
        saved = load_settings(root / ".env")
        settings = saved.model_copy(
            update={
                "ignore_accents": saved.ignore_accents
                if value.ignore_accents is None
                else value.ignore_accents,
                "jev_threshold": value.jev_threshold
                if value.jev_threshold is not None
                else saved.jev_threshold,
                "jev_model": value.jev_model or saved.jev_model,
            }
        )
        score = None
        if local_verdict(value.question, value.answer, settings.ignore_accents) is None:
            score = controller.scorer(settings)(value.question, {"answer": value.answer})["answer"]
        verdict = evaluate_answer(
            value.question, value.answer, score, settings.jev_threshold, settings.ignore_accents
        )
        return {
            "accepted": verdict.accepted,
            "alias": verdict.alias,
            "reason": verdict.reason,
            "score": verdict.score,
            "source": verdict.source,
        }

    @app.get("/api/capabilities")
    def capabilities() -> dict[str, bool]:
        """Expose whether a controlled native validation receipt matches the current group."""
        path = root / "data/transport-validation.json"
        expected = {"group": load_settings(root / ".env").whatsapp_group, "validated": True, "schema": 2}
        return {"native_ready": path.exists() and read_json(path) == expected}

    @app.get("/api/settings")
    def settings() -> dict[str, object]:
        """Display operational defaults; edits belong to the single local .env file."""
        return load_settings(root / ".env").model_dump()

    @app.put("/api/settings")
    def update_settings(value: Settings) -> dict[str, object]:
        """Save validated defaults in the private .env, leaving the active game snapshot unchanged."""
        with controller.lock:
            save_settings(root / ".env", value)
            return value.model_dump()

    @app.get("/api/session")
    def session() -> dict[str, object]:
        """Read current enrollment, round evidence and results."""
        return controller.state()

    app.post("/api/start")(controller.start)
    app.post("/api/inject")(controller.inject)
    app.post("/api/cancel")(controller.cancel)
    app.post("/api/resume")(controller.resume)
    app.post("/api/recover/{session_id}")(controller.recover)
    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/")
    def index() -> FileResponse:
        """Serve the local dashboard without embedding private configuration."""
        return FileResponse(static / "index.html")

    return app
