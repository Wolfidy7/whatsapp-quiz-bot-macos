"""Dashboard-triggered question generation through the local Claude Code generate-questions skill."""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from importlib import import_module
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator

from quiz_app.batches import check, merge
from quiz_app.errors import QuizError
from quiz_app.models import Question, StrictModel
from quiz_app.repository import validate_questions

BATCH = "data/generated-questions.json"
SKILL = "generate-questions"
CHECK_COMMAND = f"PYTHONPATH=. .venv/bin/python scripts/check_questions.py {BATCH}"
TOOLS = ["Skill", "Read", "Write", "Edit", "Bash", "WebSearch", "WebFetch", "TodoWrite"]
# Everything the skill needs to read; .env (jev key), sessions and the bank stay out of reach.
READABLE = ("docs/", f".claude/skills/{SKILL}/", "scripts/", "quiz_app/", BATCH)
MAX_TURNS = 150
MAX_EVENTS = 200
DASHBOARD_RULES = f"""Tu es lancé depuis le tableau de bord du quiz, sans opérateur pour te répondre.
- Tous les paramètres sont fournis : ne pose aucune question.
- Arrête-toi après l'étape 5 du skill : n'exécute ni --merge ni --replace. L'application remplacera
  la banque elle-même, après validation du lot par l'utilisateur.
- Termine par le compte rendu de l'étape 7, en précisant que le lot attend cette validation.
- Seuls ces outils sont autorisés : le skill {SKILL} ; la lecture de docs/, du skill, de scripts/
  et de quiz_app/ ; l'écriture de {BATCH} ; la commande exacte `{CHECK_COMMAND}` ; la recherche web."""


class GenerationRequest(StrictModel):
    """Themes, size and difficulty of one batch, as typed in the dashboard."""

    themes: str = Field(min_length=1, max_length=300)
    count: int = Field(ge=1, le=200)
    difficulty: Literal["facile", "moyenne", "difficile"] = "moyenne"

    @field_validator("themes")
    @classmethod
    def single_line(cls, value: str) -> str:
        """Keep themes to one printable line so they cannot reshape the agent prompt."""
        value = value.strip()
        if not value or any(not char.isprintable() for char in value):
            raise ValueError("Les thèmes tiennent sur une ligne, sans caractère de contrôle")
        return value


def tool_decision(name: str, tool_input: dict[str, Any], root: Path) -> str | None:
    """Return None to allow one agent tool call, or the reason it is refused."""
    if name in ("WebSearch", "WebFetch", "TodoWrite"):
        return None
    if name == "Skill":
        return None if tool_input.get("skill") == SKILL else f"Seul le skill {SKILL} est autorisé"
    if name == "Bash":
        return bash_decision(str(tool_input.get("command", "")), root)
    if name in ("Read", "Write", "Edit"):
        return file_decision(name, project_path(str(tool_input.get("file_path", "")), root))
    return f"Outil {name} non autorisé pour la génération depuis le tableau de bord"


def file_decision(name: str, relative: str | None) -> str | None:
    """Allow reads of the skill's sources and writes of the generated batch only."""
    readable = name == "Read" and relative is not None and relative.startswith(READABLE)
    if readable or relative == BATCH:
        return None
    return f"Accès refusé : seuls {BATCH} (écriture) et {', '.join(READABLE[:-1])} (lecture) sont permis"


def bash_decision(command: str, root: Path) -> str | None:
    """Allow only the checker on the generated batch, optionally after a cd into the project."""
    normalized = " ".join(command.split())
    for prefix in (f"cd {root} && ", f'cd "{root}" && '):
        normalized = normalized.removeprefix(prefix)
    return None if normalized == CHECK_COMMAND else f"Seule la commande « {CHECK_COMMAND} » est autorisée"


def project_path(path: str, root: Path) -> str | None:
    """Resolve a tool path to a project-relative POSIX path, or None outside the project."""
    if not path:
        return None
    resolved = (root / path).resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def describe_tool(name: str, tool_input: dict[str, Any], root: Path) -> str | None:
    """Summarize one allowed tool call as a progress line for the dashboard."""
    if name == "Skill":
        return f"Chargement du skill {SKILL}"
    if name == "Read":
        return f"Lecture de {project_path(str(tool_input.get('file_path', '')), root)}"
    if name in ("Write", "Edit"):
        return "Écriture du lot"
    if name == "Bash":
        return "Contrôle du lot (check_questions.py)"
    if name == "WebSearch":
        return f"Recherche web : {tool_input.get('query', '')}"
    if name == "WebFetch":
        return f"Consultation : {tool_input.get('url', '')}"
    return None


Progress = Callable[[str], None]
Runner = Callable[[GenerationRequest, Path, Progress], Awaitable[tuple[str, float | None]]]


def make_guard(root: Path, progress: Progress) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Build the PreToolUse hook that allows or refuses every agent tool call and reports it."""

    async def guard(data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
        name, tool_input = data["tool_name"], data.get("tool_input") or {}
        reason = tool_decision(name, tool_input, root)
        target = str(tool_input.get("command") or tool_input.get("file_path") or "")[:120]
        refused = f"Refusé · {name} {target}".rstrip() + f" : {reason}"
        line = refused if reason else describe_tool(name, tool_input, root)
        if line:
            progress(line)
        decision = {"permissionDecision": "allow"}
        if reason:
            decision = {"permissionDecision": "deny", "permissionDecisionReason": reason}
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", **decision}}

    return guard


def report_text(message: Any, progress: Progress) -> None:
    """Forward the first line of each assistant text block as progress."""
    for block in getattr(message, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            progress(text.strip().splitlines()[0][:200])


def outcome(result: Any) -> tuple[str, float | None]:
    """Return the final report and cost, or raise when the agent did not finish cleanly."""
    if result is None or result.is_error:
        detail = getattr(result, "result", None) or getattr(result, "subtype", "aucun résultat")
        raise QuizError("GENERATION_FAILED", f"Claude n’a pas terminé la génération : {detail}")
    return result.result or "", result.total_cost_usd


async def claude_runner(
    request: GenerationRequest, root: Path, progress: Progress
) -> tuple[str, float | None]:
    """Run the project skill with the Claude Agent SDK; every tool call passes the PreToolUse guard."""
    sdk = import_module("claude_agent_sdk")
    options = sdk.ClaudeAgentOptions(
        cwd=str(root),
        tools=TOOLS,
        skills=[SKILL],
        setting_sources=["project"],
        system_prompt={"type": "preset", "preset": "claude_code", "append": DASHBOARD_RULES},
        hooks={"PreToolUse": [sdk.HookMatcher(matcher=None, hooks=[make_guard(root, progress)])]},
        max_turns=MAX_TURNS,
    )
    prompt = f"/{SKILL} {request.themes} {request.count} {request.difficulty}"
    result = None
    async for message in sdk.query(prompt=prompt, options=options):
        if hasattr(message, "is_error"):
            result = message
        report_text(message, progress)
    return outcome(result)


class Generator:
    """Own at most one background generation and the review of its batch."""

    def __init__(self, root: Path, runner: Runner = claude_runner) -> None:
        """Bind the project directory and the agent runner; nothing runs until start."""
        self.root = root
        self.runner = runner
        self.task: asyncio.Task[None] | None = None
        self.reset()

    def reset(self) -> None:
        """Forget the previous run before a new one."""
        self.status: Literal["idle", "running", "done", "failed", "cancelled"] = "idle"
        self.request: GenerationRequest | None = None
        self.events: list[str] = []
        self.report = ""
        self.error = ""
        self.cost: float | None = None
        self.started: float | None = None
        self.finished: float | None = None
        self.applied: str | None = None

    def start(self, request: GenerationRequest) -> dict[str, object]:
        """Start one generation on the running event loop; refuse a second concurrent run."""
        if self.status == "running":
            raise QuizError("GENERATION_ACTIVE", "Une génération est déjà en cours")
        (self.root / BATCH).unlink(missing_ok=True)
        self.reset()
        self.status, self.request, self.started = "running", request, time.time()
        self.task = asyncio.get_running_loop().create_task(self.run(request))
        return self.state()

    async def run(self, request: GenerationRequest) -> None:
        """Record the outcome; failures and cancellation never escape the background task."""
        try:
            self.report, self.cost = await self.runner(request, self.root, self.progress)
            self.status = "done"
        except asyncio.CancelledError:
            self.status = "cancelled"
        except Exception as exc:
            self.status, self.error = "failed", str(exc) or type(exc).__name__
        self.finished = time.time()

    def progress(self, line: str) -> None:
        """Keep the latest progress lines for polling."""
        self.events = [*self.events, line][-MAX_EVENTS:]

    async def cancel(self) -> dict[str, object]:
        """Stop a running generation and wait until its task has settled."""
        if self.task is not None and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        return self.state()

    def batch(self) -> tuple[list[Question], list[str], list[str]]:
        """Read and check the generated batch against the authoring rules, as a replacement bank."""
        try:
            questions = validate_questions(json.loads((self.root / BATCH).read_text(encoding="utf-8")))
        except FileNotFoundError:
            return [], ["Le lot n’a pas été écrit"], []
        except (OSError, ValueError, QuizError) as exc:
            return [], [f"Lot illisible : {exc}"], []
        errors, warnings = check(questions, [])
        return questions, errors, warnings

    def apply(self, bank_path: Path) -> dict[str, object]:
        """Replace the bank with a finished, error-free batch after a timestamped backup."""
        if self.status != "done" or self.applied:
            raise QuizError("GENERATION_NOT_READY", "Aucun lot terminé à appliquer")
        questions, errors, _ = self.batch()
        if errors:
            raise QuizError("BATCH_INVALID", "Le lot contient des erreurs : la banque n’a pas été modifiée")
        backup = merge(questions, [], bank_path)
        self.applied = backup.name if backup else "aucune"
        return self.state()

    def state(self) -> dict[str, object]:
        """Return a JSON-safe snapshot; the batch is checked once the run has finished."""
        review = None
        if self.status == "done":
            questions, errors, warnings = self.batch()
            review = {
                "questions": [
                    {"id": q.id, "question": q.question, "answer": q.criteria.true} for q in questions
                ],
                "errors": errors,
                "warnings": warnings,
            }
        return {
            "status": self.status,
            "request": self.request.model_dump() if self.request else None,
            "events": self.events,
            "report": self.report,
            "error": self.error,
            "cost_usd": self.cost,
            "started": self.started,
            "finished": self.finished,
            "batch": review,
            "applied": self.applied,
        }
