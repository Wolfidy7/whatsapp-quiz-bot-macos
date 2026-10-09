"""jev threshold decisions, with exact alias matching as the explicit offline fallback."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from quiz_app.jev import JevClient, NoulQuestion
from quiz_app.models import Question
from quiz_app.normalization import normalize as normalize

Scorer = Callable[[Question, dict[str, str]], dict[str, float | None]]
FALLBACK = "Repli local (jev indisponible) : "


@dataclass(frozen=True)
class Verdict:
    """Acceptance evidence shared by live scoring and the editor: jev score or matched alias."""

    accepted: bool
    alias: str | None
    reason: str
    score: float | None = None
    source: Literal["jev", "fallback"] = "fallback"


def offline(question: Question, answers: dict[str, str]) -> dict[str, float | None]:
    """Score nothing, so every answer uses the local fallback; never touches the network."""
    return dict.fromkeys(answers)


def noul_question(question: Question) -> NoulQuestion:
    """Map a bank question to jev: the question is the instructions; aliases are never sent."""
    return NoulQuestion(question.id, question.question, question.criteria.true, question.criteria.false)


def jev_scorer(api_key: str, model: str) -> Scorer:
    """Score round answers with jev in parallel; without a key, every answer falls back locally."""
    if not api_key:
        return offline
    client = JevClient(api_key, model)
    return lambda question, answers: client.score_many(noul_question(question), answers)


def fallback_verdict(question: Question, answer: str, ignore_accents: bool = True) -> Verdict:
    """Accept only a complete normalized match with the true criterion or a declared alias."""
    value = normalize(answer, ignore_accents)
    if value:
        for alias in [question.criteria.true, *question.aliases]:
            if value == normalize(alias, ignore_accents):
                return Verdict(True, alias, FALLBACK + "correspondance exacte après normalisation.")
    return Verdict(False, None, FALLBACK + "aucune référence ni alias ne correspond.")


def evaluate_answer(
    question: Question, answer: str, score: float | None, threshold: float, ignore_accents: bool = True
) -> Verdict:
    """Accept when the jev probability reaches the threshold; fall back locally without a score."""
    if score is None:
        return fallback_verdict(question, answer, ignore_accents)
    accepted = score >= threshold
    comparison = "≥" if accepted else "<"
    return Verdict(accepted, None, f"Score jev {score:.3f} {comparison} seuil {threshold:.3f}.", score, "jev")


def extract_answer(body: str, prefix: str) -> str | None:
    """Extract the nonempty answer after a case-insensitive command plus whitespace."""
    parts = body.strip().split(maxsplit=1)
    if len(parts) != 2 or parts[0].casefold() != prefix.casefold():
        return None
    return parts[1].strip() or None
