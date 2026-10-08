"""Small native wheel steps to preserve overlapping message observations."""

import time
from importlib import import_module
from typing import Any

from quiz_app.errors import QuizError


def require_unlocked() -> None:
    """Require an unlocked local console; raise SESSION_LOCKED before native interaction."""
    quartz = import_module("Quartz")
    session = quartz.CGSessionCopyCurrentDictionary()
    if not session or session.get("CGSSessionScreenIsLocked") or not session.get("kCGSSessionOnConsoleKey"):
        raise QuizError("SESSION_LOCKED", "The macOS console session must be unlocked")


def ensure_foreground(reader: Any) -> None:
    """Activate WhatsApp and await live AX confirmation; reject locked or unavailable sessions."""
    require_unlocked()
    reader.running.activateWithOptions_(reader.cocoa.NSApplicationActivateIgnoringOtherApps)
    for _ in range(20):
        time.sleep(0.1)
        if reader.attr(reader.app, "AXFrontmost") is True:
            return
    require_front(reader)


def require_front(reader: Any) -> None:
    """Read the target application's live AX foreground flag before each native event."""
    if reader.attr(reader.app, "AXFrontmost") is not True:
        raise QuizError("UI_UNAVAILABLE", "WhatsApp n’est pas au premier plan ; l’action a été interrompue")


def click_control(reader: Any, node: Any) -> None:
    """Focus a verified empty composer with a guarded native click; restore the pointer."""
    quartz = import_module("Quartz")
    ensure_foreground(reader)
    point = table_center(reader, node)
    saved = quartz.CGEventGetLocation(quartz.CGEventCreate(None))
    kinds = (quartz.kCGEventMouseMoved, quartz.kCGEventLeftMouseDown, quartz.kCGEventLeftMouseUp)
    events = [quartz.CGEventCreateMouseEvent(None, kind, point, quartz.kCGMouseButtonLeft) for kind in kinds]
    restore = quartz.CGEventCreateMouseEvent(
        None, quartz.kCGEventMouseMoved, saved, quartz.kCGMouseButtonLeft
    )
    if any(event is None for event in events) or restore is None:
        raise QuizError("UI_UNAVAILABLE", "Cannot construct guarded native click events")
    try:
        for event in events:
            require_front(reader)
            quartz.CGEventSetFlags(event, 0)
            quartz.CGEventPost(quartz.kCGHIDEventTap, event)
            time.sleep(0.03)
    finally:
        quartz.CGEventPost(quartz.kCGHIDEventTap, events[-1])
        quartz.CGEventPost(quartz.kCGHIDEventTap, restore)


def scroll_pixels(reader: Any, amount: int) -> None:
    """Scroll the verified WhatsApp table in the foreground; reject unsafe UI geometry."""
    quartz = import_module("Quartz")
    ensure_foreground(reader)
    table = reader.require_group()
    point = table_center(reader, table)
    event = quartz.CGEventCreateScrollWheelEvent(None, quartz.kCGScrollEventUnitPixel, 1, amount)
    if event is None:
        raise QuizError("UI_UNAVAILABLE", "Cannot construct native scroll event")
    quartz.CGEventSetLocation(event, point)
    quartz.CGEventPost(quartz.kCGHIDEventTap, event)


def table_center(reader: Any, table: Any) -> tuple[float, float]:
    """Decode current AX table bounds, refusing missing or zero-size geometry."""
    position = reader.attr(table, "AXPosition")
    size = reader.attr(table, "AXSize")
    if position is None or size is None:
        raise QuizError("UI_UNAVAILABLE", "Conversation geometry is unavailable")
    valid, point = reader.ax.AXValueGetValue(position, reader.ax.kAXValueCGPointType, None)
    size_valid, dimensions = reader.ax.AXValueGetValue(size, reader.ax.kAXValueCGSizeType, None)
    if not valid or not size_valid or dimensions.width <= 0 or dimensions.height <= 0:
        raise QuizError("UI_UNAVAILABLE", "Conversation geometry is invalid")
    return float(point.x + dimensions.width / 2), float(point.y + dimensions.height / 2)
