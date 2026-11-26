"""pydit application: wires the editor, execution runner, completion
popup, status bar and file modals into a single Textual App.
"""
from __future__ import annotations

import os
from typing import Optional

import jedi
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header, Input, OptionList, RichLog, TextArea

from .completion import Candidate, CompletionPopup
from .editor import CodeEditor
from .modals import ConfirmModal, PathModal
from .runner import ProcessRunner
from .status_bar import StatusBar

UNTITLED = "untitled.py"


class Pydit(App):
    """A terminal Python editor with Jedi autocompletion and live execution."""

    TITLE = "pydit"

    CSS = """
    Screen {
        layout: vertical;
        layers: base overlay;
    }
    #file_input {
        dock: top;
        display: none;
    }
    #editor {
        height: 65%;
        border: solid #333333;
    }
    #output_pane {
        height: 35%;
    }
    #output {
        height: 1fr;
        border-top: solid #00aa00;
        background: #111111;
    }
    #interactive_input {
        dock: bottom;
        height: 3;
        border: solid #00aa00;
        background: #1e1e1e;
    }
    """

    BINDINGS = [
        Binding("ctrl+r", "run_code", "Run"),
        Binding("ctrl+c", "stop_code", "Stop", priority=True),
        Binding("ctrl+s", "save_file", "Save"),
        Binding("ctrl+o", "open_prompt", "Open"),
        Binding("ctrl+shift+s", "save_as", "Save As", show=False),
        Binding("ctrl+space", "autocomplete", "Complete", show=False),
        Binding("ctrl+q", "request_quit", "Quit"),
    ]

    def __init__(self, file_path: Optional[str] = None) -> None:
        super().__init__()
        self.current_file: Optional[str] = file_path
        self.dirty: bool = False
        self.runner = ProcessRunner(
            on_stdout=self._handle_stdout,
            on_stderr=self._handle_stderr,
            on_exit=self._handle_exit,
        )

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="Path to file... (Enter to load, Esc to cancel)", id="file_input")
        with Vertical():
            yield CodeEditor.code_editor("", language="python", id="editor")
            with Vertical(id="output_pane"):
                yield RichLog(id="output", highlight=True, markup=True, wrap=True)
            yield Input(
                placeholder="Type input for the running program and press Enter...",
                id="interactive_input",
            )
        yield CompletionPopup()
        yield StatusBar()
        yield Footer()

    def on_mount(self) -> None:
        output = self.query_one("#output", RichLog)
        editor = self.query_one("#editor", CodeEditor)

        if self.current_file and os.path.exists(self.current_file):
            self._load_file(self.current_file, announce=True)
        else:
            self._update_title()
            output.write(
                "[bold green]Welcome to pydit![/bold green] "
                "Tab = Complete | Ctrl+R = Run | Ctrl+C = Stop | "
                "Ctrl+S = Save | Ctrl+O = Open | Ctrl+Q = Quit\n"
            )

        editor.focus()
        self.set_interval(0.1, self._refresh_status_bar)

    # ------------------------------------------------------------------ #
    # File I/O
    # ------------------------------------------------------------------ #
    def _load_file(self, path: str, announce: bool = False) -> None:
        editor = self.query_one("#editor", CodeEditor)
        output = self.query_one("#output", RichLog)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                editor.text = fh.read()
            self.current_file = path
            self.dirty = False
            self._update_title()
            if announce:
                output.write(f"[bold green][pydit] Loaded {path}[/bold green]\n")
        except OSError as err:
            output.write(f"[bold red][pydit] Could not load {path}: {err}[/bold red]\n")

    def _save_to(self, path: str) -> bool:
        editor = self.query_one("#editor", CodeEditor)
        output = self.query_one("#output", RichLog)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(editor.text)
            self.current_file = path
            self.dirty = False
            self._update_title()
            output.write(f"[bold green][pydit] Saved to {path}[/bold green]\n")
            return True
        except OSError as err:
            output.write(f"[bold red][pydit] Save failed: {err}[/bold red]\n")
            return False

    def _update_title(self) -> None:
        name = self.current_file or UNTITLED
        self.sub_title = f"{name}{'*' if self.dirty else ''}"

    def action_save_file(self) -> None:
        if self.current_file:
            self._save_to(self.current_file)
        else:
            self.action_save_as()

    def action_save_as(self) -> None:
        def handle(path: Optional[str]) -> None:
            if path:
                self._save_to(path)
            self.query_one("#editor", CodeEditor).focus()

        self.push_screen(PathModal("Save As", default=self.current_file or ""), handle)

    def action_open_prompt(self) -> None:
        def proceed() -> None:
            def handle(path: Optional[str]) -> None:
                if path:
                    if os.path.exists(path):
                        self._load_file(path)
                    else:
                        self.query_one("#output", RichLog).write(
                            f"[yellow][pydit] File not found: {path}[/yellow]\n"
                        )
                self.query_one("#editor", CodeEditor).focus()

            self.push_screen(PathModal("Open File", default=""), handle)

        if self.dirty:
            def on_confirm(discard: bool) -> None:
                if discard:
                    proceed()
                else:
                    self.query_one("#editor", CodeEditor).focus()

            self.push_screen(
                ConfirmModal("You have unsaved changes. Discard them and open another file?"),
                on_confirm,
            )
        else:
            proceed()

    # ------------------------------------------------------------------ #
    # Editing / dirty tracking / status bar
    # ------------------------------------------------------------------ #
    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "editor":
            self.dirty = True
            self._update_title()

    def _refresh_status_bar(self) -> None:
        editor = self.query_one("#editor", CodeEditor)
        status = self.query_one(StatusBar)
        row, col = editor.cursor_location
        status.line = row + 1
        status.column = col + 1
        status.line_count = editor.document.line_count
        status.state = "Running" if self.runner.is_running else "Idle"

    # ------------------------------------------------------------------ #
    # Autocomplete
    # ------------------------------------------------------------------ #
    def action_autocomplete(self) -> None:
        editor = self.query_one("#editor", CodeEditor)
        output = self.query_one("#output", RichLog)
        row, col = editor.cursor_location
        code = editor.text

        try:
            script = jedi.Script(code, path=self.current_file or UNTITLED)
            completions = script.complete(line=row + 1, column=col)
        except Exception as err:  # Jedi can raise on malformed source
            output.write(f"[red][pydit] Autocomplete error: {err}[/red]\n")
            return

        if not completions:
            output.write("[dim][pydit] No suggestions for the current word.[/dim]\n")
            return

        candidates = []
        for c in completions[:20]:
            try:
                doc = c.docstring()
            except Exception:
                doc = ""
            candidates.append(Candidate(name=c.name, complete=c.complete, type=c.type, docstring=doc))

        popup = self.query_one(CompletionPopup)
        anchor = editor.cursor_screen_offset()
        popup.show(candidates, anchor=anchor)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "completion_list":
            return
        popup = self.query_one(CompletionPopup)
        candidate = popup.selected
        popup.hide()
        editor = self.query_one("#editor", CodeEditor)
        editor.focus()
        if candidate and candidate.complete:
            editor.insert(candidate.complete)

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #
    def action_run_code(self) -> None:
        editor = self.query_one("#editor", CodeEditor)
        output = self.query_one("#output", RichLog)
        code = editor.text

        if not code.strip():
            output.write("[yellow][pydit] Buffer is empty. Nothing to run.[/yellow]\n")
            return

        filename = self.current_file or UNTITLED

        # Catch syntax errors up front with a friendly, precise message
        # instead of only surfacing whatever traceback the subprocess prints.
        try:
            compile(code, filename, "exec")
        except SyntaxError as err:
            output.clear()
            output.write(
                f"[bold red][pydit] Syntax error at line {err.lineno}, col {err.offset}:[/bold red]\n"
            )
            output.write(f"[red]{err.msg}[/red]\n")
            if err.text:
                output.write(f"[dim]{err.text.rstrip()}[/dim]\n")
            return
        except (ValueError, TypeError) as err:
            # e.g. null bytes or other source-encoding oddities
            output.clear()
            output.write(f"[bold red][pydit] Could not compile buffer: {err}[/bold red]\n")
            return

        output.clear()
        output.write(f"[bold cyan][pydit] Running {filename}...[/bold cyan]\n")
        self.runner.run(code, filename)

    def action_stop_code(self) -> None:
        output = self.query_one("#output", RichLog)
        if self.runner.is_running:
            self.runner.stop()
            output.write("\n[bold red][pydit] Process stopped.[/bold red]\n")
        else:
            output.write("[dim][pydit] No process is currently running.[/dim]\n")

    def _handle_stdout(self, text: str) -> None:
        self.call_from_thread(self.query_one("#output", RichLog).write, text)

    def _handle_stderr(self, text: str) -> None:
        self.call_from_thread(self.query_one("#output", RichLog).write, f"[red]{text}[/red]")

    def _handle_exit(self, code: Optional[int]) -> None:
        def announce() -> None:
            output = self.query_one("#output", RichLog)
            if code == 0:
                output.write("\n[bold green][pydit] Process finished (exit 0).[/bold green]\n")
            else:
                output.write(f"\n[bold yellow][pydit] Process exited with code {code}.[/bold yellow]\n")

        self.call_from_thread(announce)

    # ------------------------------------------------------------------ #
    # Input handling for the two dockable Input widgets
    # ------------------------------------------------------------------ #
    def on_input_submitted(self, event: Input.Submitted) -> None:
        output = self.query_one("#output", RichLog)

        if event.input.id == "file_input":
            event.input.display = False
            self.query_one("#editor", CodeEditor).focus()
            return

        if event.input.id == "interactive_input":
            text = event.value
            event.input.value = ""
            if self.runner.is_running:
                output.write(f"[italic cyan]> {text}[/italic cyan]")
                if not self.runner.send_input(text):
                    output.write("[red][pydit] Failed to send input; process may have exited.[/red]\n")
            else:
                output.write("[dim][pydit] No active process waiting for input.[/dim]\n")

    # ------------------------------------------------------------------ #
    # Quitting
    # ------------------------------------------------------------------ #
    def action_request_quit(self) -> None:
        if self.dirty:
            def on_confirm(discard: bool) -> None:
                if discard:
                    self.runner.stop()
                    self.exit()

            self.push_screen(
                ConfirmModal("You have unsaved changes. Quit without saving?"),
                on_confirm,
            )
        else:
            self.runner.stop()
            self.exit()


if __name__ == "__main__":
    Pydit().run()
