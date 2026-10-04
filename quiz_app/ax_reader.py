"""Native read-only bridge: requires the intended WhatsApp group already visible."""

import time
from importlib import import_module
from typing import Any

from quiz_app.errors import QuizError
from quiz_app.models import Message
from quiz_app.native import clean_description, ordered_page, parse_description
from quiz_app.scrolling import scroll_pixels


class AXReader:
    """Read and scroll WhatsApp Desktop; this class has no publication operation."""

    def __init__(self, group: str, max_pages: int = 40) -> None:
        """Attach to running WhatsApp after checking permissions; never launch or send."""
        self.ax: Any = import_module("ApplicationServices")
        self.cocoa: Any = import_module("Cocoa")
        self.group = group
        self.max_pages = max_pages
        self.scroll_step = 180
        self.identities: dict[int, tuple[Any, str, float, int]] = {}
        if not self.ax.AXIsProcessTrusted():
            raise QuizError(
                "PERMISSIONS_DENIED", "Allow the terminal and real Python executable in Accessibility"
            )
        applications = [
            app
            for app in self.cocoa.NSWorkspace.sharedWorkspace().runningApplications()
            if app.bundleIdentifier() == "net.whatsapp.WhatsApp"
        ]
        if len(applications) != 1:
            raise QuizError("WHATSAPP_UNAVAILABLE", "Open WhatsApp Desktop with the intended group visible")
        self.running = applications[0]
        self.app = self.ax.AXUIElementCreateApplication(self.running.processIdentifier())
        self.ax.AXUIElementSetMessagingTimeout(self.app, 1.0)
        self.table = self.require_group()

    def attr(self, element: Any, name: str) -> Any:
        """Return an AX attribute or None if unavailable; individual calls have a timeout."""
        error, value = self.ax.AXUIElementCopyAttributeValue(element, name, None)
        return value if error == 0 else None

    def walk(self, root: Any) -> list[Any]:
        """Traverse a bounded UI tree in document order; reject a changing oversized tree."""
        stack = [(root, 0)]
        result: list[Any] = []
        deadline = time.monotonic() + 8
        while stack:
            if len(result) >= 2000 or time.monotonic() > deadline:
                raise QuizError("UI_UNAVAILABLE", "Accessibility traversal exceeded its safe limit")
            node, depth = stack.pop()
            result.append(node)
            if depth < 24:
                stack.extend((child, depth + 1) for child in reversed(self.attr(node, "AXChildren") or []))
        return result

    def require_group(self) -> Any:
        """Check the exact active header and unique conversation table before every read."""
        window = self.attr(self.app, "AXMainWindow")
        if window is None or self.attr(window, "AXModal"):
            raise QuizError("UI_UNAVAILABLE", "WhatsApp window unavailable or blocked by a dialog")
        nodes = self.walk(window)
        headers = [
            node for node in nodes if self.attr(node, "AXIdentifier") == "NavigationBar_HeaderViewButton"
        ]
        tables = [node for node in nodes if self.attr(node, "AXIdentifier") == "ChatMessagesTableView"]
        if len(headers) != 1 or len(tables) != 1:
            raise QuizError("GROUP_AMBIGUOUS", "Active conversation controls are missing or ambiguous")
        if clean_description(str(self.attr(headers[0], "AXDescription"))) != self.group:
            raise QuizError("GROUP_AMBIGUOUS", "Open the exact requested group before inspection")
        return tables[0]

    def page(self) -> list[Message]:
        """Parse visible rows and prove their AX traversal matches vertical positions."""
        table = self.require_group()
        rows: list[tuple[float, Message]] = []
        date = ""
        for node in self.attr(table, "AXChildren") or []:
            role = self.attr(node, "AXRole")
            if role == "AXHeading":
                date = clean_description(
                    str(self.attr(node, "AXDescription") or self.attr(node, "AXValue") or "")
                )
            elif self.attr(node, "AXIdentifier") == "WAMessageBubbleTableViewCell":
                row = self.parse_row(node, date)
                if row is not None:
                    rows.append(row)
        return ordered_page(rows)

    def parse_row(self, node: Any, date: str) -> tuple[float, Message] | None:
        """Read a bubble, rejecting missing physical order metadata for any text message."""
        message = parse_description(str(self.attr(node, "AXDescription") or ""), self.group, date)
        if message is None:
            return None
        position = self.attr(node, "AXPosition")
        if position is None:
            raise QuizError("HISTORY_INCOMPLETE", "Message position is unavailable")
        valid, point = self.ax.AXValueGetValue(position, self.ax.kAXValueCGPointType, None)
        if not valid:
            raise QuizError("HISTORY_INCOMPLETE", "Message position cannot be decoded")
        return float(point.y), self.identify(node, message, float(point.y))

    def identify(self, node: Any, message: Message, y: float) -> Message:
        """Track viewport continuity while distinguishing recycled native cells and duplicate texts."""
        key = hash(node)
        previous = self.identities.get(key)
        generation = 0
        if previous is not None:
            if previous[0] != node:
                raise QuizError("HISTORY_CHANGED", "Native element hash collision prevents identification")
            changed = previous[1] != message.fingerprint or abs(previous[2] - y) > self.scroll_step + 1
            generation = previous[3] + int(changed)
        self.identities[key] = (node, message.fingerprint, y, generation)
        native_id = f"{self.running.processIdentifier()}:{key}:{generation}"
        return message.model_copy(update={"native_id": native_id})

    def raw_position(self, node: Any) -> float | None:
        """Return a stable vertical signature so scrolling within long bubbles is detectable."""
        value = self.attr(node, "AXPosition")
        if value is None:
            return None
        valid, point = self.ax.AXValueGetValue(value, self.ax.kAXValueCGPointType, None)
        return round(float(point.y), 2) if valid else None

    def raw_page(self) -> list[tuple[str, float | None]]:
        """Read content and positions; restore even when message parsing fails."""
        return [
            (str(self.attr(node, "AXDescription")), self.raw_position(node))
            for node in self.attr(self.require_group(), "AXChildren") or []
            if self.attr(node, "AXIdentifier") == "WAMessageBubbleTableViewCell"
        ]

    def scroll(self, direction: str) -> bool:
        """Scroll one page, wait for rendering, and compare chronological observations."""
        before = self.raw_page()
        scroll_pixels(self, self.scroll_step if direction == "AXScrollUpByPage" else -self.scroll_step)
        time.sleep(0.35)
        return self.raw_page() != before

    def older(self) -> bool:
        """Request the preceding native page without changing any conversation content."""
        return self.scroll("AXScrollUpByPage")

    def latest(self) -> None:
        """Reach the latest viewport within a finite budget; fail rather than guess."""
        for _ in range(self.max_pages):
            if not self.scroll("AXScrollDownByPage"):
                return
        raise QuizError("HISTORY_INCOMPLETE", "Could not reach the newest page within the limit")
