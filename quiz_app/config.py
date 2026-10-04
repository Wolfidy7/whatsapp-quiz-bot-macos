"""Read one private .env, without modifying the shell environment."""

import json
from pathlib import Path

from pydantic import ValidationError

from quiz_app.errors import QuizError
from quiz_app.models import Settings


def load_settings(path: Path) -> Settings:
    """Parse all settings; raise CONFIG_INVALID on missing or malformed input."""
    try:
        values = parse_env(path.read_text(encoding="utf-8"))
        settings = Settings.model_validate(values)
        if settings.min_points > settings.max_points:
            raise ValueError("MIN_POINTS must not exceed MAX_POINTS")
        if settings.join_command.casefold() == settings.answer_prefix.casefold():
            raise ValueError("JOIN_COMMAND and ANSWER_PREFIX must differ")
        return settings
    except (OSError, ValueError, ValidationError) as exc:
        raise QuizError("CONFIG_INVALID", str(exc)) from exc


def parse_env(text: str) -> dict[str, object]:
    """Parse KEY=value, JSON double quotes and booleans; reject duplicate keys."""
    values: dict[str, object] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        field = key.strip().lower()
        if not separator or field in values:
            raise ValueError("Malformed or duplicate .env key")
        value = value.strip()
        values[field] = json.loads(value) if value.startswith('"') else value
    return values
