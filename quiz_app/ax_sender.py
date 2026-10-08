"""Conservative native sender: verified group, empty draft, paste, send, confirm."""

import time
from collections.abc import Callable
from typing import Any

from quiz_app.ax_reader import AXReader
from quiz_app.errors import QuizError
from quiz_app.native import clean_description
from quiz_app.scrolling import click_control, ensure_foreground


def unique(nodes: list[Any], description: str) -> Any:
    """Return exactly one UI node or refuse an ambiguous control."""
    if len(nodes) != 1:
        raise QuizError("UI_UNAVAILABLE", f"{description} missing or ambiguous")
    return nodes[0]


class AXSender:
    """Send through menu actions without keyboard-layout dependent shortcuts."""

    def __init__(self, reader: AXReader, cancel_requested: Callable[[], bool] = lambda: False) -> None:
        """Use a permission-checked reader for navigation and verified native publication."""
        self.reader = reader
        self.cancel_requested = cancel_requested

    def check_cancelled(self) -> None:
        """Refuse the next native action after an operator Stop request."""
        if self.cancel_requested():
            raise QuizError("GAME_CANCELLED", "Arrêt demandé")

    def press(self, node: Any) -> None:
        """Require an enabled AX control and a successful press action."""
        if self.reader.attr(node, "AXEnabled") is False:
            raise QuizError("UI_UNAVAILABLE", "WhatsApp control is disabled")
        if self.reader.ax.AXUIElementPerformAction(node, "AXPress"):
            raise QuizError("UI_UNAVAILABLE", "WhatsApp rejected the press action")

    def menu(self, headings: tuple[str, ...], entries: tuple[str, ...]) -> None:
        """Invoke one localized menu entry and always close its menu afterward."""
        reader = self.reader
        bar = reader.attr(reader.app, "AXMenuBar")
        heading = unique(
            [
                node
                for node in reader.attr(bar, "AXChildren") or []
                if clean_description(str(reader.attr(node, "AXTitle") or "")) in headings
            ],
            "menu",
        )
        self.press(heading)
        try:
            entry = unique(
                [
                    node
                    for node in reader.walk(heading)
                    if reader.attr(node, "AXRole") == "AXMenuItem"
                    and clean_description(str(reader.attr(node, "AXTitle") or "")) in entries
                ],
                "menu entry",
            )
            self.press(entry)
        finally:
            reader.ax.AXUIElementPerformAction(bar, "AXCancel")

    def clipboard_copy(self) -> list[Any]:
        """Copy all current clipboard representations before temporary text publication."""
        cocoa = self.reader.cocoa
        board = cocoa.NSPasteboard.generalPasteboard()
        originals = []
        for item in board.pasteboardItems() or []:
            saved = cocoa.NSPasteboardItem.alloc().init()
            for kind in item.types():
                data = item.dataForType_(kind)
                if data is not None:
                    saved.setData_forType_(data, kind)
            originals.append(saved)
        return originals

    def paste(self, composer: Any, text: str, *, replace: bool = False) -> None:
        """Paste into a verified focused field; optionally replace search text and preserve clipboard."""
        reader = self.reader
        self.press(composer)
        time.sleep(0.2)
        if reader.attr(reader.app, "AXFocusedUIElement") != composer:
            click_control(reader, composer)
            time.sleep(0.2)
        if reader.attr(reader.app, "AXFocusedUIElement") != composer:
            raise QuizError("UI_UNAVAILABLE", "The targeted WhatsApp text field could not be focused")
        board = reader.cocoa.NSPasteboard.generalPasteboard()
        originals = self.clipboard_copy()
        board.clearContents()
        board.setString_forType_(text, "public.utf8-plain-text")
        version = board.changeCount()
        try:
            if replace and reader.attr(composer, "AXValue"):
                self.menu(("Edit", "Édition"), ("Select All", "Tout sélectionner", "Sélectionner tout"))
                if reader.attr(reader.app, "AXFocusedUIElement") != composer:
                    raise QuizError("UI_UNAVAILABLE", "Search field lost focus before paste")
            self.menu(("Edit", "Édition"), ("Paste", "Coller"))
            time.sleep(0.3)
            if reader.attr(composer, "AXValue") != text:
                raise QuizError("PUBLICATION_UNCERTAIN", "Pasted message did not match the reserved text")
        finally:
            if board.changeCount() == version:
                board.clearContents()
                if originals:
                    board.writeObjects_(originals)

    def window_nodes(self) -> list[Any]:
        """Read the current window controls; refuse unavailable windows and modal dialogs."""
        window = self.reader.attr(self.reader.app, "AXMainWindow")
        if window is None or self.reader.attr(window, "AXModal"):
            raise QuizError("UI_UNAVAILABLE", "WhatsApp window unavailable or blocked by a dialog")
        return self.reader.walk(window)

    def search_results(self) -> list[Any]:
        """Return only exact conversation-name matches, excluding messages and partial matches."""
        reader = self.reader
        return [
            node
            for node in self.window_nodes()
            if reader.attr(node, "AXIdentifier") == "ChatListSearchView_ChatResult"
            and clean_description(str(reader.attr(node, "AXDescription") or "")) == reader.group
        ]

    def open_group(self) -> None:
        """Search the configured group, refuse homonyms and verify its header without publishing."""
        reader = self.reader
        self.check_cancelled()
        ensure_foreground(reader)
        search = unique(
            [
                node
                for node in self.window_nodes()
                if reader.attr(node, "AXIdentifier") == "TokenizedSearchBar_TextView"
            ],
            "conversation search",
        )
        self.paste(search, reader.group, replace=True)
        time.sleep(0.8)
        for _ in range(20):
            if self.search_results():
                break
            time.sleep(0.2)
        time.sleep(0.5)
        matches = self.search_results()
        if len(matches) != 1:
            raise QuizError("GROUP_AMBIGUOUS", "Expected exactly one conversation with the configured name")
        self.press(matches[0])
        time.sleep(0.5)
        reader.table = reader.require_group()

    def publish(self, text: str, marker: str) -> None:
        """Paste the reserved text and click the native send button once; caller confirms publication."""
        reader = self.reader
        self.check_cancelled()
        ensure_foreground(reader)
        reader.require_group()
        nodes = reader.walk(reader.attr(reader.app, "AXMainWindow"))
        composer = unique(
            [node for node in nodes if reader.attr(node, "AXIdentifier") == "ChatBar_ComposerTextView"],
            "composer",
        )
        if reader.attr(composer, "AXValue"):
            raise QuizError("PUBLICATION_UNCERTAIN", "An existing draft prevents sending")
        self.check_cancelled()
        self.paste(composer, text)
        reader.require_group()
        send_button = unique(
            [
                node
                for node in reader.walk(reader.attr(reader.app, "AXMainWindow"))
                if reader.attr(node, "AXIdentifier") == "ChatBar_SendButton"
            ],
            "send button",
        )
        if reader.attr(send_button, "AXEnabled") is False:
            raise QuizError("UI_UNAVAILABLE", "WhatsApp send button is disabled")
        self.check_cancelled()
        click_control(reader, send_button)
        time.sleep(0.5)

    def send(self, text: str, marker: str) -> None:
        """Legacy diagnostic confirmation through visible rows; native database transport uses publish."""
        self.publish(text, marker)
        rows = self.reader.page()
        matches = [row for row in rows if row.outgoing and marker in row.body]
        if len(matches) != 1:
            raise QuizError("PUBLICATION_UNCERTAIN", "Outgoing marker could not be uniquely confirmed")
