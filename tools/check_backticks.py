"""Reject reST double-backtick spans in Python comments and docstrings (D-480, #1028).

The house style is Markdown's single backtick, so a span written as two backticks, a
word and two backticks is a slip from reST. From the repo root:

    uv run python -m tools.check_backticks              # every tracked Python file
    uv run python -m tools.check_backticks FILE...      # just these (what pre-commit passes)

It exits 1 and prints one `path:line: text` per span. Only comments (`tokenize`) and bare
string statements (`ast`: docstrings, attribute docstrings) are read, so a string that is
data, such as a test fixture or the Markdown a converter must produce, is never flagged.
A span whose text holds a backtick is allowed: Markdown needs the double delimiter there. `tests/test_check_backticks.py` pins this and runs the check on the repo.
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

RUN = re.compile(r"`+")
"""A run of backticks: Markdown pairs a run with the next run of the same length."""


def _double_spans(text: str) -> list[tuple[int, str]]:
    """Return the offset and text of each two-backtick span in `text` that holds no backtick.

    Runs are paired as CommonMark pairs them: an opening run closes at the next run of the
    same length, and one that has no such partner is plain text. A span of two backticks
    around text with a backtick in it is what Markdown needs there, so it is not returned.
    """
    runs = list(RUN.finditer(text))
    found = []
    i = 0
    while i < len(runs):
        opening = runs[i]
        width = opening.end() - opening.start()
        closing = next(
            (
                j
                for j in range(i + 1, len(runs))
                if runs[j].end() - runs[j].start() == width
            ),
            None,
        )
        if closing is None:
            i += 1
            continue
        body = text[opening.end() : runs[closing].start()]
        if width == 2 and "`" not in body:
            found.append((opening.start(), text[opening.start() : runs[closing].end()]))
        i = closing + 1
    return found


def find_spans(source: str) -> list[tuple[int, str]]:
    """Return the line and text of every double-backtick span in `source`'s comments and docstrings.

    A docstring is any bare string statement, as the AST sees it: the string's value, so
    that adjacent literals joined by implicit concatenation read as one, and a string that
    is data (an assignment, an argument, an f-string, bytes) is never read.

    Args:
        source: The text of one Python file.

    Returns:
        `(line, span)` pairs, comments first, then docstrings; the line is the one the span
        starts on (a docstring's lines are counted from the value, so an escaped newline
        shifts them).

    Raises:
        SyntaxError: When `source` is not Python.
    """
    tree = ast.parse(
        source
    )  # first: a file that is not Python fails here, as SyntaxError
    found: list[tuple[int, str]] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            found.extend(
                (token.start[0], span) for _, span in _double_spans(token.string)
            )
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            text = node.value.value
            found.extend(
                (node.lineno + text.count("\n", 0, offset), span)
                for offset, span in _double_spans(text)
            )
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
        try:
            with tokenize.open(path) as file:  # honours a file's encoding line
                spans = find_spans(file.read())
        except SyntaxError as error:
            print(f"{name}:{error.lineno or 1}: cannot read it as Python: {error.msg}")
            problems += 1
            continue
        for line, span in spans:
            flat = " ".join(span.split())
            print(f"{name}:{line}: {flat}: use single backticks")
            problems += 1
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
