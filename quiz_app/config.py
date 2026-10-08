"""Read one private .env, without modifying the shell environment."""

import json
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from quiz_app.errors import QuizError
from quiz_app.models import Settings
from quiz_app.storage import locked


def load_settings(path: Path) -> Settings:
    """Parse all settings; raise CONFIG_INVALID on missing or malformed input."""
    try:
        values = parse_env(path.read_text(encoding="utf-8"))
        settings = Settings.model_validate(values)
        return settings
    except (OSError, ValueError, ValidationError) as exc:
        raise QuizError("CONFIG_INVALID", str(exc)) from exc


def save_settings(path: Path, settings: Settings) -> None:
    """Atomically save validated defaults to the single private .env; classify storage failures."""
    text = (
        "\n".join(
            f"{key.upper()}={json.dumps(value, ensure_ascii=False)}"
            for key, value in settings.model_dump().items()
        )
        + "\n"
    )
    try:
        with locked(path.with_suffix(".lock")):
            fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".settings-")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(text)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
                directory = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                Path(temporary).unlink(missing_ok=True)
    except OSError as error:
        raise QuizError("STORAGE_UNAVAILABLE", "Impossible d’enregistrer les paramètres") from error


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
