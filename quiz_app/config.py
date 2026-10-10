"""Read one private .env, without modifying the shell environment."""

import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError

from quiz_app.errors import QuizError
from quiz_app.models import Settings
from quiz_app.storage import locked

API_KEY = "jev_api_key"
# Hostnames of the private Tailscale proxy, read only from .env so the dashboard cannot widen them.
REMOTE_HOSTS = "remote_hosts"
PRIVATE_KEYS = (API_KEY, REMOTE_HOSTS)


def load_settings(path: Path) -> Settings:
    """Parse all settings; raise CONFIG_INVALID on missing or malformed input."""
    try:
        values = parse_env(path.read_text(encoding="utf-8"))
        for key in PRIVATE_KEYS:
            values.pop(key, None)
        settings = Settings.model_validate(values)
        return settings
    except (OSError, ValueError, ValidationError) as exc:
        raise QuizError("CONFIG_INVALID", str(exc)) from exc


def load_api_key(path: Path) -> str:
    """Read the private jev key, kept outside Settings; empty when the file or key is absent."""
    try:
        return str(parse_env(path.read_text(encoding="utf-8")).get(API_KEY, ""))
    except FileNotFoundError:
        return ""
    except (OSError, ValueError) as exc:
        raise QuizError("CONFIG_INVALID", str(exc)) from exc


def load_remote_hosts(path: Path) -> frozenset[str]:
    """Read the comma-separated REMOTE_HOSTS allowlist; empty when the file or key is absent."""
    try:
        raw = str(parse_env(path.read_text(encoding="utf-8")).get(REMOTE_HOSTS, ""))
    except FileNotFoundError:
        return frozenset()
    except (OSError, ValueError) as exc:
        raise QuizError("CONFIG_INVALID", str(exc)) from exc
    # Accept URLs copied from `tailscale serve` output by keeping only their hostname.
    items = (item.strip() for item in raw.split(","))
    hosts = (urlsplit(item if "//" in item else f"//{item}").hostname for item in items if item)
    return frozenset(host.rstrip(".") for host in hosts if host)


def save_settings(path: Path, settings: Settings) -> None:
    """Atomically save validated defaults to the single private .env, preserving private keys."""
    values: dict[str, object] = {**settings.model_dump(), API_KEY: load_api_key(path)}
    if hosts := load_remote_hosts(path):
        values[REMOTE_HOSTS] = ",".join(sorted(hosts))
    text = "".join(
        f"{key.upper()}={json.dumps(value, ensure_ascii=False)}\n" for key, value in values.items()
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
