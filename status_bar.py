"""Status bar summarizing cursor position, document size, and run state."""
from __future__ import annotations

import platform

from textual.reactive import reactive
from textual.widgets import Static


class StatusBar(Static):
    """A single-line status readout docked at the bottom of the screen."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: #202020;
        color: #00cc66;
        padding: 0 1;
    }
    """

    line: reactive[int] = reactive(1)
    column: reactive[int] = reactive(1)
    line_count: reactive[int] = reactive(1)
    state: reactive[str] = reactive("Idle")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._py_version = platform.python_version()

    def render(self) -> str:
        state_color = "green" if self.state == "Idle" else "yellow"
        return (
            f"Line: {self.line}, Col: {self.column}    "
            f"Lines: {self.line_count}    "
            f"Python: {self._py_version}    "
            f"[{state_color}]\u25cf {self.state}[/{state_color}]"
        )

    def watch_line(self, _value: int) -> None:
        self.refresh()

    def watch_column(self, _value: int) -> None:
        self.refresh()

    def watch_line_count(self, _value: int) -> None:
        self.refresh()

    def watch_state(self, _value: str) -> None:
        self.refresh()
