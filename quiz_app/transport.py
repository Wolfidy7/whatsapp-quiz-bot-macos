"""Transport contract plus an explicit, deterministic local simulator."""

from hashlib import sha256
from typing import Protocol

from quiz_app.history import window
from quiz_app.models import Message


class Transport(Protocol):
    """No state or UI side effects hidden in game rules."""

    def send(self, text: str, marker: str) -> None:
        """Publish and confirm a marker, or raise a classified incident."""
        ...

    def preview(self, start: str) -> list[Message] | None:
        """Return a known complete prefix quickly, or None when a viewport gap prevents it."""
        ...

    def segment(self, start: str, stop: str | None = None) -> list[Message]:
        """Return a complete ordered window or refuse an incomplete collection."""
        ...


class Simulator:
    """In-memory WhatsApp stand-in; never publishes outside this process."""

    def __init__(self) -> None:
        """Create an empty chronological conversation."""
        self.messages: list[Message] = []

    def inject(self, author: str, body: str) -> None:
        """Append a fake incoming message while keeping duplicate texts distinct."""
        fingerprint = sha256(f"{len(self.messages)}:{author}:{body}".encode()).hexdigest()
        self.messages.append(Message(author=author, body=body, fingerprint=fingerprint))

    def send(self, text: str, marker: str) -> None:
        """Append an outgoing simulated message, without any native interaction."""
        self.inject("bot", text)
        self.messages[-1] = self.messages[-1].model_copy(update={"outgoing": True})

    def preview(self, start: str) -> list[Message] | None:
        """Return the complete current simulation window without scrolling or publication."""
        return self.segment(start)

    def segment(self, start: str, stop: str | None = None) -> list[Message]:
        """Read a strictly bounded simulated conversation segment."""
        return window(self.messages, start, stop)
