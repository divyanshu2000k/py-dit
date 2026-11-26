"""Modal dialogs: file-path prompts and yes/no confirmations.

Both screens are typed ``ModalScreen[...]`` so callers get a proper result
back through ``push_screen(screen, callback)`` -- a ``str | None`` path, or
a ``bool`` for confirmations -- instead of reaching back into global state.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


class PathModal(ModalScreen[str]):
    """Asks the user for a file path (used for both Open and Save As)."""

    DEFAULT_CSS = """
    PathModal {
        align: center middle;
    }
    PathModal > #dialog {
        width: 60;
        height: auto;
        border: round #00aa00;
        background: #1e1e1e;
        padding: 1 2;
    }
    PathModal > #dialog > Input {
        margin-top: 1;
    }
    PathModal > #dialog > Horizontal {
        margin-top: 1;
        height: 3;
        align: right middle;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, title: str, default: str = "") -> None:
        super().__init__()
        self._title = title
        self._default = default

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._title)
            yield Input(value=self._default, placeholder="path/to/file.py", id="path_input")
            with Horizontal():
                yield Button("Cancel", id="cancel", variant="default")
                yield Button("Confirm", id="confirm", variant="success")

    def on_mount(self) -> None:
        self.query_one("#path_input", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._confirm()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            self._confirm()
        else:
            self.dismiss(None)

    def _confirm(self) -> None:
        value = self.query_one("#path_input", Input).value.strip()
        self.dismiss(value or None)


class ConfirmModal(ModalScreen[bool]):
    """A yes/no confirmation dialog, e.g. for unsaved-changes warnings."""

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
    }
    ConfirmModal > #dialog {
        width: 54;
        height: auto;
        border: round #cc6600;
        background: #1e1e1e;
        padding: 1 2;
    }
    ConfirmModal > #dialog > Horizontal {
        margin-top: 1;
        height: 3;
        align: right middle;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, message: str, confirm_label: str = "Yes", cancel_label: str = "No") -> None:
        super().__init__()
        self._message = message
        self._confirm_label = confirm_label
        self._cancel_label = cancel_label

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._message)
            with Horizontal():
                yield Button(self._cancel_label, id="no", variant="default")
                yield Button(self._confirm_label, id="yes", variant="error")

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")
