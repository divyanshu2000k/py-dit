"""Custom TextArea with Python-aware editing conveniences."""
from __future__ import annotations

from typing import Optional

from textual import events
from textual.geometry import Offset
from textual.widgets import TextArea


class CodeEditor(TextArea):
    """A TextArea that auto-pairs brackets/quotes, auto-indents after a
    trailing ``:`` on Enter, and hands Tab / Ctrl+Space off to the app for
    Jedi-powered autocompletion.
    """

    AUTO_PAIRS = {
        "(": ")",
        "[": "]",
        "{": "}",
        '"': '"',
        "'": "'",
    }
    CLOSERS = set(AUTO_PAIRS.values())

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "tab":
            event.prevent_default()
            event.stop()
            if self._is_mid_identifier():
                self.app.action_autocomplete()
            else:
                self.insert("    ")
            return

        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self._insert_newline_with_indent()
            return

        if event.character and event.character in self.AUTO_PAIRS:
            event.prevent_default()
            event.stop()
            opener = event.character
            closer = self.AUTO_PAIRS[opener]
            self.insert(opener + closer)
            row, col = self.cursor_location
            self.move_cursor((row, col - 1))
            return

        # Typing a closing character that's already right under the cursor
        # just steps over it instead of inserting a duplicate -- standard
        # editor behaviour for auto-paired brackets/quotes.
        if event.character and event.character in self.CLOSERS:
            row, col = self.cursor_location
            line = self._current_line_text()
            if col < len(line) and line[col] == event.character:
                event.prevent_default()
                event.stop()
                self.move_cursor((row, col + 1))
                return

        await super()._on_key(event)

    def _is_mid_identifier(self) -> bool:
        """True if the char left of the cursor looks like part of a name,
        i.e. Tab should trigger completion rather than indent.
        """
        row, col = self.cursor_location
        line = self._current_line_text()
        if col == 0 or col > len(line):
            return False
        prev_char = line[col - 1]
        return prev_char.isalnum() or prev_char in ("_", ".")

    def _current_line_text(self) -> str:
        try:
            return self.document.get_line(self.cursor_location[0])
        except Exception:
            lines = self.text.split("\n")
            row = self.cursor_location[0]
            return lines[row] if row < len(lines) else ""

    def _insert_newline_with_indent(self) -> None:
        row, col = self.cursor_location
        line = self._current_line_text()
        current_indent = line[: len(line) - len(line.lstrip(" "))]
        stripped_before_cursor = line[:col].rstrip()
        extra = "    " if stripped_before_cursor.endswith(":") else ""
        self.insert("\n" + current_indent + extra)

    def cursor_screen_offset(self) -> Optional[Offset]:
        """Best-effort screen position just below/right of the cursor.

        Used only to anchor the completion popup. Textual's built-in
        TextArea doesn't expose an exact public API for pixel/cell-precise
        cursor coordinates, so this is a heuristic based on the widget's
        own screen region, scroll offset, and gutter (line-number) width.
        It's good enough to put the popup in the right neighbourhood; if
        anything looks off it falls back to ``None`` and the caller can
        just show the popup in its default spot.
        """
        try:
            region = self.region
        except Exception:
            return None
        row, col = self.cursor_location
        scroll_x, scroll_y = self.scroll_offset
        gutter = 0
        if getattr(self, "show_line_numbers", False):
            gutter = len(str(max(self.document.line_count, 1))) + 2
        x = region.x + gutter + (col - scroll_x)
        y = region.y + (row - scroll_y) + 1
        return Offset(max(region.x, x), max(region.y, y))
