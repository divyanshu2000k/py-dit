"""Floating completion popup powered by Jedi.

Shown near the cursor (see ``CodeEditor.cursor_screen_offset``), it lists
candidate names with their Jedi-reported type (module / function / class /
statement / ...) and a docstring preview for whichever entry is
highlighted. Navigation (Up/Down/Enter) is handled by the underlying
``OptionList``; Escape dismisses it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from textual.containers import Vertical
from textual.geometry import Offset
from textual.reactive import reactive
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option


@dataclass
class Candidate:
    """A single completion candidate, decoupled from Jedi's own object so
    the popup doesn't need to keep a live Jedi session around."""

    name: str
    complete: str  # text to insert at the cursor
    type: str
    docstring: str


class CompletionPopup(Vertical):
    """A small overlay listing Jedi completions, with a docstring preview."""

    DEFAULT_CSS = """
    CompletionPopup {
        layer: overlay;
        width: 46;
        height: auto;
        max-height: 14;
        border: round #00aa00;
        background: #1e1e1e;
        display: none;
    }
    CompletionPopup > OptionList {
        height: auto;
        max-height: 8;
        background: #1e1e1e;
    }
    CompletionPopup > #doc_preview {
        height: auto;
        max-height: 6;
        padding: 0 1;
        color: #999999;
        border-top: solid #333333;
    }
    """

    BINDINGS = [("escape", "dismiss", "Cancel")]

    visible: reactive[bool] = reactive(False)

    def __init__(self) -> None:
        super().__init__(id="completion_popup")
        self._candidates: List[Candidate] = []

    def compose(self):
        yield OptionList(id="completion_list")
        yield Static("", id="doc_preview")

    def show(self, candidates: List[Candidate], anchor: Optional[Offset] = None) -> None:
        self._candidates = candidates
        option_list = self.query_one("#completion_list", OptionList)
        option_list.clear_options()
        for candidate in candidates:
            label = f"[b]{candidate.name}[/b]  [dim]{candidate.type}[/dim]"
            option_list.add_option(Option(label, id=candidate.name))

        if anchor is not None:
            self.styles.offset = anchor

        self.display = True
        self.visible = True

        if candidates:
            option_list.highlighted = 0
            self._update_preview(0)
        option_list.focus()

    def hide(self) -> None:
        self.display = False
        self.visible = False
        self._candidates = []

    def action_dismiss(self) -> None:
        self.hide()
        try:
            self.app.query_one("#editor").focus()
        except Exception:
            pass

    def _update_preview(self, index: int) -> None:
        preview = self.query_one("#doc_preview", Static)
        if 0 <= index < len(self._candidates):
            doc = (self._candidates[index].docstring or "").strip()
            preview.update(doc[:400] if doc else "[dim]No documentation available.[/dim]")
        else:
            preview.update("")

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._update_preview(event.option_index)

    @property
    def selected(self) -> Optional[Candidate]:
        option_list = self.query_one("#completion_list", OptionList)
        idx = option_list.highlighted
        if idx is None or not (0 <= idx < len(self._candidates)):
            return None
        return self._candidates[idx]
