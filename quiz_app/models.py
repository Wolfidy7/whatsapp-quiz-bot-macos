"""Validated data contracts; a session is one atomic JSON document."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quiz_app.normalization import normalize


class StrictModel(BaseModel):
    """Reject unknown fields instead of silently accepting malformed imports."""

    model_config = ConfigDict(extra="forbid")


class Criteria(StrictModel):
    """jev decision criteria: what a correct (true) and an incorrect (false) answer mean."""

    true: str = Field(min_length=1, max_length=500)
    false: str = Field(min_length=1, max_length=500)

    @field_validator("true", "false")
    @classmethod
    def nonblank(cls, value: str) -> str:
        """Strip surrounding spaces and reject empty criteria."""
        if not value.strip():
            raise ValueError("Criteria cannot be blank")
        return value.strip()


class Question(StrictModel):
    """A jev-graded question; aliases are only the offline fallback and are never sent to jev."""

    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    question: str = Field(min_length=1, max_length=2000)
    criteria: Criteria
    aliases: list[str] = Field(default_factory=list, max_length=100)
    explanation: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def valid_fallback(self) -> Self:
        """Require meaningful fallback references: the true criterion and every alias."""
        if any(not normalize(alias, False) for alias in [self.criteria.true, *self.aliases]):
            raise ValueError("Criteria and aliases must contain meaningful text")
        return self

    @field_validator("question")
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
    jev_threshold: float = Field(default=0.8, ge=0, le=1, allow_inf_nan=False)
    jev_model: str = Field(default="jev-latest", pattern=r"^[A-Za-z0-9._-]{1,80}$")

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
    score: float | None = Field(default=None, ge=0, le=1)
    source: Literal["jev", "fallback", "local", ""] = ""
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
