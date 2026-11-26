"""Asynchronous execution of the buffer's Python code in a subprocess.

The runner launches ``python3 -u -c <code>`` in a background subprocess and
streams stdout/stderr back to the UI in near-real time -- including a
partial line such as an ``input()`` prompt that has no trailing newline,
which a naive "read until newline" pump would leave stuck in the pipe.

Design notes
------------
* ``-u`` (equivalently ``PYTHONUNBUFFERED=1``) makes the *child's* stdout
  and stderr fully unbuffered at the C level, so a bare ``print("name: ",
  end="")`` is flushed to the pipe the instant it's written, not just at
  the next newline.
* A reader thread performs blocking ``read(1)`` calls and feeds characters
  into a thread-safe buffer. A second thread flushes each buffer to the UI
  callback roughly every 40ms, batching rapid output without ever holding
  back a lone, newline-less prompt for more than a tick.
* This deliberately uses plain pipes rather than a pseudo-terminal (pty).
  A pty would make ``input()`` prompts behave even more like a native
  terminal (e.g. for cursor movement or `isatty()` checks) but the ``pty``
  module is POSIX-only, so plain pipes + unbuffered I/O keep pydit
  cross-platform while still solving the interactive-input problem above.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
from typing import Callable, List, Optional

FLUSH_INTERVAL = 0.04  # seconds between UI flushes


class _StreamBuffer:
    """Thread-safe accumulator that batches characters between flushes."""

    def __init__(self, callback: Callable[[str], None]) -> None:
        self._callback = callback
        self._chars: List[str] = []
        self._lock = threading.Lock()

    def feed(self, char: str) -> None:
        with self._lock:
            self._chars.append(char)

    def flush(self) -> None:
        with self._lock:
            if not self._chars:
                return
            text = "".join(self._chars)
            self._chars.clear()
        self._callback(text)


class ProcessRunner:
    """Runs Python source in a subprocess and streams its I/O to callbacks.

    All callbacks fire from background threads. Callers running under
    Textual must marshal them back onto the UI thread themselves (e.g. via
    ``App.call_from_thread``) before touching widgets.
    """

    def __init__(
        self,
        on_stdout: Callable[[str], None],
        on_stderr: Callable[[str], None],
        on_exit: Callable[[Optional[int]], None],
    ) -> None:
        self._on_stdout = on_stdout
        self._on_stderr = on_stderr
        self._on_exit = on_exit
        self.process: Optional[subprocess.Popen] = None
        self._stop_flushing = threading.Event()
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def run(self, code: str, filename: str) -> None:
        """Terminate any prior run and start executing ``code``."""
        self.stop()
        self._stop_flushing.clear()

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        # `filename` becomes sys.argv[0] in the child, for nicer tracebacks.
        self.process = subprocess.Popen(
            ["python3", "-u", "-c", code, filename],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0,
            env=env,
        )

        out_buf = _StreamBuffer(self._on_stdout)
        err_buf = _StreamBuffer(self._on_stderr)

        threading.Thread(
            target=self._read_stream, args=(self.process.stdout, out_buf), daemon=True
        ).start()
        threading.Thread(
            target=self._read_stream, args=(self.process.stderr, err_buf), daemon=True
        ).start()
        threading.Thread(
            target=self._flush_loop, args=(out_buf, err_buf), daemon=True
        ).start()
        threading.Thread(target=self._wait, daemon=True).start()

    def _read_stream(self, pipe, buf: _StreamBuffer) -> None:
        try:
            while True:
                char = pipe.read(1)
                if not char:
                    break
                buf.feed(char)
        except (ValueError, OSError):
            pass
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    def _flush_loop(self, out_buf: _StreamBuffer, err_buf: _StreamBuffer) -> None:
        while not self._stop_flushing.is_set():
            out_buf.flush()
            err_buf.flush()
            time.sleep(FLUSH_INTERVAL)
        # Final flush so nothing written right before exit is dropped.
        out_buf.flush()
        err_buf.flush()

    def _wait(self) -> None:
        proc = self.process
        if proc is None:
            return
        return_code = proc.wait()
        self._stop_flushing.set()
        time.sleep(FLUSH_INTERVAL * 2)  # let the tail flush land first
        self._on_exit(return_code)

    def send_input(self, text: str) -> bool:
        """Write a line to the running process's stdin. Returns success."""
        if not self.is_running or self.process.stdin is None:
            return False
        try:
            self.process.stdin.write(text + "\n")
            self.process.stdin.flush()
            return True
        except (BrokenPipeError, OSError):
            return False

    def stop(self) -> None:
        """Terminate the running process, if any, escalating to kill()."""
        with self._lock:
            self._stop_flushing.set()
            proc, self.process = self.process, None
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception:
                pass
