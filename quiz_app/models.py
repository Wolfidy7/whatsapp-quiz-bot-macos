"""Validated data contracts; a session is one atomic JSON document."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quiz_app.normalization import normalize
from quiz_app.numeric import numeric_value


class StrictModel(BaseModel):
    """Reject unknown fields instead of silently accepting malformed imports."""

    model_config = ConfigDict(extra="forbid")


class Question(StrictModel):
    """A deterministic correction rule; old banks default to normalized exact equality."""

    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=500)
    aliases: list[str] = Field(default_factory=list, max_length=100)
    explanation: str = Field(default="", max_length=2000)
    grading_mode: Literal["exact", "person_name", "number"] = "exact"
    units: list[str] = Field(default_factory=list, max_length=30)
    require_unit: bool = False

    @model_validator(mode="after")
    def valid_correction(self) -> Self:
        """Reject unusable aliases, misplaced unit options and invalid numeric references."""
        if any(not normalize(alias, False) for alias in [self.answer, *self.aliases]):
            raise ValueError("Answers and aliases must contain meaningful text")
        if self.grading_mode != "number":
            if self.units or self.require_unit:
                raise ValueError("Unit options require grading_mode=number")
            return self
        self.valid_numeric_rule()
        return self

    def valid_numeric_rule(self) -> None:
        """Validate unit labels and all numeric references; raise ValueError on an invalid rule."""
        if any(not normalize(unit, False) or len(unit) > 40 for unit in self.units):
            raise ValueError("Unit labels must contain 1–40 meaningful characters")
        if self.require_unit and not self.units:
            raise ValueError("A required unit needs at least one allowed label")
        if any(
            numeric_value(alias, self.units, self.require_unit, False) is None
            for alias in [self.answer, *self.aliases]
        ):
            raise ValueError("Numeric answers and aliases must be decimal values with an allowed unit")

    @field_validator("question", "answer")
    @classmethod
    def nonblank(cls, value: str) -> str:
        """Strip surrounding spaces and reject empty content."""
        if not value.strip():
            raise ValueError("Text cannot be blank")
        return value.strip()


class Settings(StrictModel):
    """Validated defaults, snapshotted at the start of each session."""

    whatsapp_database: str = Field(min_length=1, max_length=2000)
    whatsapp_group: str = Field(min_length=1, max_length=200)
    max_players: int = Field(ge=1, le=1000)
    nb_players_expected: int = Field(default=1, ge=1, le=1000)
    max_questions: int = Field(ge=1, le=1000)
    registration_seconds: int = Field(ge=1, le=3600)
    question_seconds: int = Field(ge=1, le=3600)
    interval_seconds: int = Field(ge=0, le=3600)
    poll_seconds: float = Field(gt=0, le=30)
    join_command: str = Field(pattern=r"^![A-Za-z]+$")
    answer_prefix: str = Field(pattern=r"^![A-Za-z]+$")
    ignore_accents: bool
    max_points: int = Field(ge=1, le=100000)
    min_points: int = Field(ge=1, le=100000)
    max_history_pages: int = Field(ge=1, le=10000)
    message_chunk_size: int = Field(ge=200, le=4000)
    port: int = Field(ge=1024, le=65535)

    @model_validator(mode="after")
    def valid_player_limits(self) -> Self:
        """Validate enrollment limits, scoring bounds and distinct command prefixes."""
        if self.nb_players_expected > self.max_players:
            raise ValueError("NB_PLAYERS_EXPECTED must not exceed MAX_PLAYERS")
        if self.min_points > self.max_points:
            raise ValueError("MIN_POINTS must not exceed MAX_POINTS")
        if self.join_command.casefold() == self.answer_prefix.casefold():
            raise ValueError("JOIN_COMMAND and ANSWER_PREFIX must differ")
        return self

    @field_validator("whatsapp_group", "whatsapp_database")
    @classmethod
    def group_nonblank(cls, value: str) -> str:
        """Strip the target label and reject a blank group name during configuration load."""
        if not value.strip():
            raise ValueError("Configuration text cannot be blank")
        return value.strip()


class Message(StrictModel):
    """An ordered native observation; author is the WhatsApp display label."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    author: str
    author_id: str = ""
    body: str
    outgoing: bool = False
    fingerprint: str
    edited: bool = False
    timestamp: str = ""
    native_id: str = ""
    sequence: int | None = None


class Dispatch(StrictModel):
    """Write-ahead outgoing message, with a private unique correlation key."""

    marker: str
    text: str
    status: Literal["pending", "sent"] = "pending"


class NativeDelivery(StrictModel):
    """Private send fence and confirmed native identity, never included in public text."""

    text: str
    group_id: int = Field(ge=1)
    after: int = Field(ge=0)
    native_id: str = ""


class Result(StrictModel):
    """Per-player correction evidence for one round."""

    player: str
    answer: str = ""
    accepted: bool = False
    alias: str | None = None
    reason: str = ""
    rank: int | None = None
    points: int = 0


class Round(StrictModel):
    """Question window and immutable first observations."""

    question: Question
    start_marker: str
    stop_marker: str
    observed: list[Message] = Field(default_factory=list)
    results: list[Result] = Field(default_factory=list)


class Session(StrictModel):
    """Complete durable session snapshot with explicit recovery state."""

    version: Literal[1] = 1
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    settings: Settings
    questions: list[Question] = Field(min_length=1)
    mode: Literal["simulation", "native"]
    phase: Literal["registration", "answering", "interval", "finished", "paused", "cancelled"]
    deadline: float = Field(default=0, ge=0, allow_inf_nan=False)
    players: list[str] = Field(default_factory=list)
    player_names: dict[str, str] = Field(default_factory=dict)
    rounds: list[Round] = Field(default_factory=list)
    outbox: list[Dispatch] = Field(default_factory=list)
    error: str = ""
    resume_phase: str = ""
    registration_observed: list[Message] = Field(default_factory=list)
    conversation: list[Message] = Field(default_factory=list)
    rehearsal: bool = False
