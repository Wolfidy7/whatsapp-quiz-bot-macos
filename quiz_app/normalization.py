"""Shared text normalization without semantic guesses or spelling corrections."""

import re
import unicodedata


def normalize(text: str, ignore_accents: bool = True) -> str:
    """Normalize a complete string, retaining internal punctuation and meaningful symbols."""
    value = unicodedata.normalize("NFC", text).casefold().replace("’", "'").replace("‘", "'")
    if ignore_accents:
        value = "".join(c for c in unicodedata.normalize("NFD", value) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", value).strip().rstrip(".,!?;:").strip()
