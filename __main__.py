"""Entry point: `python -m pydit [file.py]` or the installed `pydit` script."""
from __future__ import annotations

import argparse

from .app import Pydit


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pydit",
        description="pydit - a terminal Python editor with Jedi autocompletion.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Python file to open (created on first save if it doesn't exist yet).",
    )
    args = parser.parse_args()

    app = Pydit(file_path=args.file)
    app.run()


if __name__ == "__main__":
    main()
