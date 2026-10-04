"""Read-only native prototype and conservative paginated history reconciliation."""

import re
import unicodedata
from collections.abc import Callable
from hashlib import sha256
from typing import Protocol

from quiz_app.errors import QuizError
from quiz_app.history import merge_pages, window
from quiz_app.models import Message


class HistoryView(Protocol):
    """Injectable AX page boundary; scrolling must wait for a stable snapshot."""

    def page(self) -> list[Message]:
        """Read rows in verified top-to-bottom order."""
        ...

    def older(self) -> bool:
        """Scroll up once; return whether the displayed page changed."""
        ...

    def latest(self) -> None:
        """Restore the conversation to its latest page."""
        ...


def clean_description(value: str) -> str:
    """Strip directional formatting only, preserving accents and emoji sequences."""
    marks = dict.fromkeys(map(ord, "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"))
    return unicodedata.normalize("NFC", value.translate(marks))


def parse_description(description: str, group: str, date_label: str) -> Message | None:
    """Parse English AX message metadata; reject unreadable author or message rows."""
    text = clean_description(description)
    if text.startswith("Reply to "):
        text = text.partition("\n")[2]
    text = text.partition(".\nQuoted message.\n")[0]
    outgoing = text.startswith("Your message, ")
    timestamp = r"((?:\d{1,2}[A-Za-z]+(?:\d{4})?at)?\d{1,2}:\d{2})"
    if outgoing:
        expression = (
            rf"Your message, (.*), {timestamp}, Sent to {re.escape(group)}, "
            r"(?:Sent|Delivered|Read)(, Edited)?"
        )
    elif text.startswith("Message from "):
        expression = rf"Message from ([^,]+), (.*), {timestamp}, Received in {re.escape(group)}(, Edited)?"
    else:
        return None
    matched = re.fullmatch(expression, text, re.S)
    if matched is None:
        raise QuizError("AUTHOR_AMBIGUOUS", "Unsupported message metadata; collection stopped")
    fields = matched.groups()
    author, body, time = ("bot", fields[0], fields[1]) if outgoing else fields[:3]
    signature = sha256(f"{author}\n{body}\n{time}\n{outgoing}".encode()).hexdigest()
    return Message(
        author=author,
        body=body,
        outgoing=outgoing,
        fingerprint=signature,
        edited=bool(fields[-1]),
        timestamp=time,
    )


def ordered_page(rows: list[tuple[float, Message]]) -> list[Message]:
    """Verify tree traversal order equals physical vertical order; reject contradictions."""
    positions = [position for position, _ in rows]
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        raise QuizError("HISTORY_INCOMPLETE", "Accessibility row order is ambiguous")
    return [message for _, message in rows]


def collect_history(view: HistoryView, start: str, stop: str | None, max_pages: int) -> list[Message]:
    """Recover a bounded window across overlapping pages, always restoring the viewport."""
    try:
        view.latest()
        messages = view.page()
        for _ in range(max_pages):
            if any(message.outgoing and start in message.body for message in messages):
                return window(messages, start, stop)
            if not view.older():
                break
            messages = merge_pages(view.page(), messages)
        raise QuizError("HISTORY_INCOMPLETE", "Start marker not found in complete recoverable history")
    finally:
        view.latest()


def collect_recent(view: HistoryView, count: int, max_pages: int) -> list[Message]:
    """Recover requested recent messages across screens, or fail on any missing continuity."""
    if count < 1 or max_pages < 1:
        raise ValueError("Count and scroll budget must be positive")
    try:
        view.latest()
        messages = view.page()
        for _ in range(max_pages):
            if len(messages) >= count:
                return messages[-count:]
            if not view.older():
                return messages
            messages = merge_pages(view.page(), messages)
        raise QuizError(
            "HISTORY_INCOMPLETE", "Scroll budget exhausted before the requested count was recovered"
        )
    finally:
        view.latest()


class NativeTransport:
    """Serialized native history with an injected, confirmed sender."""

    def __init__(self, view: HistoryView, sender: Callable[[str, str], None], max_pages: int) -> None:
        """Bind a current conversation view, safe sender and finite scroll limit."""
        self.view = view
        self.sender = sender
        self.max_pages = max_pages
        self.cache: dict[str, list[Message]] = {}

    def preview(self, start: str) -> list[Message] | None:
        """Collect the visible page without blocking STOP on a full history traversal."""
        page = self.view.page()
        if any(message.outgoing and start in message.body for message in page):
            self.cache[start] = page
        elif start in self.cache:
            try:
                self.cache[start] = merge_pages(self.cache[start], page)
            except QuizError:
                return None
        else:
            return None
        return window(self.cache[start], start)

    def segment(self, start: str, stop: str | None = None) -> list[Message]:
        """Return a complete native window or a classified collection failure."""
        return collect_history(self.view, start, stop, self.max_pages)

    def send(self, text: str, marker: str) -> None:
        """Delegate delivery; sender must verify the marker before returning."""
        self.sender(text, marker)
        self.cache[marker] = self.view.page()
