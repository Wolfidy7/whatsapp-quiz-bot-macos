"""Private JSON documents, atomic replacement, backups and process locking."""

import fcntl
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from quiz_app.errors import QuizError


@contextmanager
def locked(path: Path) -> Iterator[None]:
    """Acquire a nonblocking file lock; raise STORAGE_BUSY instead of racing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise QuizError("STORAGE_BUSY", "Another process holds the storage lock") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def read_json(path: Path) -> Any:
    """Load a JSON file; never silently replace a corrupt document."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QuizError("STORAGE_INVALID", f"Cannot read {path.name}") from exc


def write_json(path: Path, value: object) -> None:
    """Atomically commit private JSON after retaining the previous good version."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with locked(path.with_suffix(".lock")):
            if path.exists():
                old = read_json(path)
                atomic_write(path.with_suffix(".backup.json"), old)
            atomic_write(path, value)
    except OSError as exc:
        raise QuizError("STORAGE_UNAVAILABLE", "Unable to commit private JSON") from exc


def atomic_write(path: Path, value: object) -> None:
    """Flush a temporary file and replace its destination; propagate write errors."""
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".quiz-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
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
