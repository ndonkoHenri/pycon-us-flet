"""Tests for `tools/check_backticks.py`, the guard against reST double backticks (D-479, #1028).

The last test runs the check on the repo's own Python files, so the local checks fail on a
span that slips back in; the others pin what is flagged and what is deliberately left alone.
"""

import tokenize
from pathlib import Path

import pytest

from tools.check_backticks import find_spans, main, tracked_python_files

TICKS = "`" * 2


def _read(path: Path) -> str:
    """Return a Python file's text, decoded as its encoding line says."""
    with tokenize.open(path) as file:
        return file.read()


def test_a_span_in_a_docstring_is_flagged_with_its_line() -> None:
    """A double-backtick span in a docstring is reported on the line it starts on."""
    source = f'def f():\n    """Return it.\n\n    Uses {TICKS}x{TICKS} here.\n    """\n'
    assert find_spans(source) == [(4, f"{TICKS}x{TICKS}")]


def test_a_span_in_a_comment_is_flagged() -> None:
    """A comment is read too."""
    assert find_spans(f"x = 1  # keep {TICKS}y{TICKS}\n") == [(1, f"{TICKS}y{TICKS}")]


def test_a_span_that_wraps_a_line_is_reported_where_it_starts() -> None:
    """A docstring span over a line break is reported on its first line; the next one on its own."""
    source = f'"""Both {TICKS}a\nb{TICKS} and {TICKS}c{TICKS}."""\n'
    assert [line for line, _ in find_spans(source)] == [1, 2]


def test_single_backticks_pass() -> None:
    """Markdown's single backtick, the house style, is not flagged."""
    assert find_spans('"""Return `x` (and `y`)."""\n# keep `z`\n') == []


def test_a_span_that_holds_a_backtick_is_allowed() -> None:
    """Markdown needs the double delimiter around text that contains a backtick."""
    assert find_spans(f'"""See {TICKS}a`b{TICKS} here."""\n') == []


def test_an_unpaired_run_is_not_a_span() -> None:
    """A docstring that quotes a lone double-backtick run is not a span."""
    assert find_spans(f'"""Quoted: "`a{TICKS}b`"."""\n') == []


def test_a_string_that_is_data_is_left_alone() -> None:
    """A string literal that is not a bare statement, such as a fixture or an expected value, is data."""
    assert (
        find_spans(
            f'EXPECTED = "{TICKS}x{TICKS}"\nassert f("a") == "{TICKS}y{TICKS}"\n'
        )
        == []
    )


def test_a_longer_run_is_not_a_span() -> None:
    """A Markdown fence of three backticks is not a double-backtick span."""
    assert find_spans('"""\n```bash\nls\n```\n"""\n') == []


def test_main_reports_and_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main` prints `path:line: text` for a file with a span and exits 1; a clean file exits 0."""
    bad = tmp_path / "bad.py"
    bad.write_text(f'"""A {TICKS}span{TICKS}."""\n', encoding="utf-8")
    good = tmp_path / "good.py"
    good.write_text('"""A `span`."""\n', encoding="utf-8")
    assert main([str(good)]) == 0
    assert main([str(bad)]) == 1
    assert (
        f"{bad}:1: {TICKS}span{TICKS}: use single backticks" in capsys.readouterr().out
    )


def test_the_repo_has_no_double_backtick_span() -> None:
    """No tracked Python file has a double-backtick span in a comment or docstring."""
    root = Path(__file__).resolve().parent.parent
    found = [
        f"{name}:{line}"
        for name in tracked_python_files()
        for line, _ in find_spans(_read(root / name))
    ]
    assert found == []


def test_a_data_string_beside_a_docstring_is_left_alone() -> None:
    """A string assigned on the docstring's own line, or a byte string, is data and is not read."""
    source = f'"""Doc."""; value = "{TICKS}data{TICKS}"; raw = b"{TICKS}b{TICKS}"\n'
    assert find_spans(source) == []


def test_two_allowed_spans_do_not_make_a_false_one() -> None:
    """Delimiters are paired as Markdown pairs them, so the text between two allowed spans is not a span."""
    assert find_spans(f'"""See {TICKS}a`b{TICKS} and {TICKS}c`d{TICKS}."""\n') == []


def test_a_span_built_by_implicit_concatenation_is_flagged() -> None:
    """Adjacent literals in one docstring read as one string, so a span split across them is found."""
    assert find_spans(f'"Uses {TICKS}" "x{TICKS}."\n') == [(1, f"{TICKS}x{TICKS}")]


def test_a_file_in_another_encoding_is_read(tmp_path: Path) -> None:
    """A Latin-1 file with an encoding line is decoded, not rejected as UTF-8."""
    path = tmp_path / "latin.py"
    path.write_bytes(
        f'# -*- coding: latin-1 -*-\n"""Caf\xe9 {TICKS}x{TICKS}."""\n'.encode("latin-1")
    )
    assert main([str(path)]) == 1


def test_a_file_that_is_not_python_fails_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A syntax error is reported as a problem on its line, not as a traceback."""
    path = tmp_path / "broken.py"
    path.write_text("def (:\n", encoding="utf-8")
    assert main([str(path)]) == 1
    assert "cannot read it as Python" in capsys.readouterr().out
