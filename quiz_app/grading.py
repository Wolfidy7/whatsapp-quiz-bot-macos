"""Deterministic exact matching; no fuzzy matching or external service."""

import re
import unicodedata

from quiz_app.models import Question


def normalize(text: str, ignore_accents: bool = True) -> str:
    """Normalize a complete answer, preserving internal and meaningful symbols."""
    value = unicodedata.normalize("NFC", text).casefold().replace("’", "'").replace("‘", "'")
    if ignore_accents:
        value = "".join(c for c in unicodedata.normalize("NFD", value) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", value).strip().rstrip(".,!?;:").strip()


def match_answer(question: Question, answer: str, ignore_accents: bool = True) -> tuple[bool, str | None]:
    """Return acceptance and the exact declared alias that matched, or (False, None)."""
    value = normalize(answer, ignore_accents)
    aliases = [question.answer, *question.aliases]
    found = next((alias for alias in aliases if value and normalize(alias, ignore_accents) == value), None)
    return found is not None, found


def extract_answer(body: str, prefix: str) -> str | None:
    """Extract the nonempty answer after a case-insensitive command plus whitespace."""
    parts = body.strip().split(maxsplit=1)
    if len(parts) != 2 or parts[0].casefold() != prefix.casefold():
        return None
    return parts[1].strip() or None
