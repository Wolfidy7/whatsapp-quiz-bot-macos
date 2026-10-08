"""Deterministic, explicit correction modes; no fuzzy matching or external service."""

from collections import Counter
from dataclasses import dataclass

from quiz_app.models import Question
from quiz_app.normalization import normalize as normalize
from quiz_app.numeric import numeric_value


@dataclass(frozen=True)
class Verdict:
    """Original reference and readable reason, shared by live scoring and the editor."""

    accepted: bool
    alias: str | None
    reason: str


def alias_reason(question: Question, value: str, alias: str, ignore_accents: bool) -> str:
    """Explain a complete match against one reference, or return empty text for a mismatch."""
    expected = normalize(alias, ignore_accents)
    if question.grading_mode == "number":
        candidate = numeric_value(value, question.units, question.require_unit, ignore_accents)
        reference = numeric_value(expected, question.units, question.require_unit, ignore_accents)
        return (
            "Valeur numérique équivalente et unité conforme."
            if candidate is not None and candidate == reference
            else ""
        )
    if value == expected:
        return "Correspondance exacte après normalisation."
    if question.grading_mode == "person_name" and Counter(value.split()) == Counter(expected.split()):
        return "Nom complet reconnu : ordre des mots différent."
    return ""


def evaluate_answer(question: Question, answer: str, ignore_accents: bool = True) -> Verdict:
    """Compare a full answer with declared references and return acceptance evidence; no effects."""
    value = normalize(answer, ignore_accents)
    if value:
        for alias in [question.answer, *question.aliases]:
            reason = alias_reason(question, value, alias, ignore_accents)
            if reason:
                return Verdict(True, alias, reason)
    return Verdict(False, None, "Aucune réponse officielle ou alias ne correspond selon le mode choisi.")


def match_answer(question: Question, answer: str, ignore_accents: bool = True) -> tuple[bool, str | None]:
    """Return acceptance and the original matching reference, preserving the tuple API."""
    verdict = evaluate_answer(question, answer, ignore_accents)
    return verdict.accepted, verdict.alias


def extract_answer(body: str, prefix: str) -> str | None:
    """Extract the nonempty answer after a case-insensitive command plus whitespace."""
    parts = body.strip().split(maxsplit=1)
    if len(parts) != 2 or parts[0].casefold() != prefix.casefold():
        return None
    return parts[1].strip() or None
