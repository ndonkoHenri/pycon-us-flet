"""Reject reST double-backtick spans in Python comments and docstrings (D-479, #1028).

The house style is Markdown's single backtick, so a span written as two backticks, a
word and two backticks is a slip from reST. From the repo root:

    uv run python -m tools.check_backticks              # every tracked Python file
    uv run python -m tools.check_backticks FILE...      # just these (what pre-commit passes)

It exits 1 and prints one `path:line: text` per span. Only comments and bare string
statements (docstrings, attribute docstrings) are read, found with `tokenize` and `ast`, so
a string that is data, such as a test fixture or the Markdown a converter must produce,
is never flagged. A span whose text holds a backtick is allowed: Markdown needs the double
delimiter there. `tests/test_check_backticks.py` pins this and runs the check on the repo.
"""

import argparse
import ast
import io
import re
import subprocess
import sys
import tokenize
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_TICKS = "`" * 2
SPAN = re.compile(rf"(?<!`){_TICKS}(?!`)([^`]+?)(?<!`){_TICKS}(?!`)", re.DOTALL)
"""Two backticks, text with no backtick in it, two backticks; not part of a longer run."""


def _docstring_lines(tree: ast.AST) -> list[tuple[int, int]]:
    """Return the first and last line of every bare string statement in `tree`."""
    return [
        (node.lineno, node.end_lineno or node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]


def find_spans(source: str) -> list[tuple[int, str]]:
    """Return the line and text of every double-backtick span in `source`'s comments and docstrings.

    Args:
        source: The text of one Python file.

    Returns:
        `(line, span)` pairs in file order; the line is the one the span starts on.
    """
    docs = _docstring_lines(ast.parse(source))
    found: list[tuple[int, str]] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            wanted = True
        else:
            wanted = token.type == tokenize.STRING and any(
                first <= token.start[0] and token.end[0] <= last for first, last in docs
            )
        if not wanted:
            continue
        for match in SPAN.finditer(token.string):
            line = token.start[0] + token.string.count("\n", 0, match.start())
            found.append((line, match.group(0)))
    return found


def tracked_python_files() -> list[str]:
    """Return the Python files git tracks, from the repo root."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "*.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [name for name in out.split("\0") if name]


def main(argv: Sequence[str] | None = None) -> int:
    """Check the files named, or every tracked Python file; return the exit status."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "files", nargs="*", help="Python files (default: every tracked one)"
    )
    args = parser.parse_args(argv)
    problems = 0
    for name in args.files or tracked_python_files():
        path = Path(name) if Path(name).is_absolute() else ROOT / name
        for line, span in find_spans(path.read_text(encoding="utf-8")):
            flat = " ".join(span.split())
            print(f"{name}:{line}: {flat}: use single backticks")
            problems += 1
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
