"""TypeSafe jev client: one Noul probability per player answer; acceptance is decided by the caller."""

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import httpx

API_URL = "https://api.typesafe.ai/v1/systemone"
RETRYABLE = frozenset({429, 529})
MAX_WORKERS = 8


class JevUnavailable(Exception):
    """jev returned no usable probability; callers apply the local alias fallback."""


@dataclass(frozen=True)
class NoulQuestion:
    """Question instructions and both decision criteria; the ID only keys the returned answer."""

    id: str
    instructions: str
    true: str
    false: str


def request_body(model: str, question: NoulQuestion, state: str) -> dict[str, object]:
    """Build one evaluation whose state is the player's raw answer."""
    noul = {
        "type": "noul",
        "instructions": question.instructions,
        "criteria": {"true": question.true, "false": question.false},
    }
    return {"model": model, "state": state, "questions": {question.id: noul}}


def probability(response: httpx.Response, question_id: str) -> float:
    """Extract answers[id].noul; raise JevUnavailable on an error status or malformed body."""
    if response.status_code != 200:
        raise JevUnavailable(f"HTTP {response.status_code}")
    try:
        value = response.json()["answers"][question_id]["noul"]
    except (ValueError, KeyError, TypeError) as exc:
        raise JevUnavailable("Réponse jev illisible") from exc
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise JevUnavailable("Probabilité jev hors de [0, 1]")
    return float(value)


class JevClient:
    """Synchronous, thread-safe client with bounded exponential backoff on 429/529 and network errors."""

    def __init__(
        self,
        api_key: str,
        model: str,
        http: httpx.Client | None = None,
        attempts: int = 3,
        backoff: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Bind credentials and an injectable HTTP client, retry budget and sleep."""
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.model = model
        self.http = http or httpx.Client(timeout=8.0)
        self.attempts = attempts
        self.backoff = backoff
        self.sleep = sleep

    def attempt(self, question: NoulQuestion, state: str) -> float | None:
        """Return the probability, None for a retryable failure, or raise on a definitive one."""
        try:
            response = self.http.post(
                API_URL, json=request_body(self.model, question, state), headers=self.headers
            )
        except httpx.TransportError:
            return None
        if response.status_code in RETRYABLE:
            return None
        return probability(response, question.id)

    def score(self, question: NoulQuestion, state: str) -> float:
        """Return the probability that the answer meets the true criterion; raise JevUnavailable."""
        for attempt in range(self.attempts):
            if attempt:
                self.sleep(self.backoff * 2 ** (attempt - 1))
            value = self.attempt(question, state)
            if value is not None:
                return value
        raise JevUnavailable("jev indisponible après plusieurs tentatives")

    def safe_score(self, question: NoulQuestion, state: str) -> float | None:
        """Return the probability, or None when jev is unavailable for this answer."""
        try:
            return self.score(question, state)
        except JevUnavailable:
            return None

    def score_many(self, question: NoulQuestion, states: dict[str, str]) -> dict[str, float | None]:
        """Score every player's answer in parallel, keeping keys and their order."""
        if not states:
            return {}
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(states))) as pool:
            futures = {key: pool.submit(self.safe_score, question, state) for key, state in states.items()}
            return {key: future.result() for key, future in futures.items()}
