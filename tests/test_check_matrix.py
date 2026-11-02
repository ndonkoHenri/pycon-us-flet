"""Tests for ``tools/check_matrix.py``, the feature matrix's check (D-04, #802).

The first test runs the check on the real ``docs/feature-matrix.md``, so the local checks
fail on a matrix edit that leaves the Counts tables stale; the others break a copy of it.
"""

import re

import pytest

from tools.check_matrix import MATRIX, breakdown, catalog_ids, check, main

TEXT = MATRIX.read_text(encoding="utf-8")
IDS = catalog_ids()


def edited(old: str, new: str) -> str:
    """The real matrix with its one occurrence of ``old`` replaced by ``new``."""
    assert TEXT.count(old) == 1, old
    return TEXT.replace(old, new)


def row_of(id_: str) -> str:
    """The real matrix's row line for feature ``id_``."""
    return next(line for line in TEXT.splitlines() if line.startswith(f"| **{id_}** |"))


def test_the_real_matrix_is_consistent() -> None:
    """The committed matrix has each id once, the legend's vocabulary and current Counts."""
    assert check(TEXT, IDS) == []


def test_a_phase_edit_without_the_counts_is_stale() -> None:
    """Moving a row to another phase without updating Counts reports the table as it should be."""
    row = row_of("DATA-22")
    problems = check(edited(row, row.replace("| P2 |", "| P3 |")), IDS)
    assert len(problems) == 1
    assert "the Counts table by phase is stale" in problems[0]
    assert "| catalog | 44 | 63 | 65 | 68 | 0 | 23 | 263 |" in problems[0]


def test_a_disposition_edit_without_the_counts_is_stale() -> None:
    """A combined tag counts under each of its tags, so adding one stales the table by tag."""
    row = row_of("DATA-01")
    problems = check(edited(row, row.replace("`keep`", "`keep+interim`")), IDS)
    assert len(problems) == 1
    assert "the Counts table by tag is stale" in problems[0]
    assert "| catalog | 37 | 121 | 58 | 65 | 23 | 2 | 23 | 0 | 263 |" in problems[0]


def test_a_missing_and_a_duplicated_id_are_reported() -> None:
    """A catalog id with no row and an id on two rows are each named."""
    problems = check(edited(row_of("DATA-02"), row_of("DATA-01")), IDS)
    assert "DATA-01 appears 2 times" in problems
    assert "DATA-02 is in the catalog but not in the matrix" in problems


def test_an_unknown_id_is_reported() -> None:
    """A row whose id is neither in the catalog nor a NEW id is reported."""
    row = row_of("DATA-01")
    problems = check(edited(row, row.replace("**DATA-01**", "**DATA-99**")), IDS)
    assert any("DATA-99: not a catalog id" in problem for problem in problems)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("| all |", "| everyone |", "unknown role 'everyone'"),
        ("`keep`", "`kept`", "unknown tag 'kept'"),
        ("| P0 |", "| P9 |", "unknown phase 'P9'"),
        ("| P0 |", "| — |", "phase — goes with drop"),
        ("`keep`", "`new`", "new is the tag of NEW- rows"),
    ],
)
def test_a_word_outside_the_legend_is_reported(
    old: str, new: str, message: str
) -> None:
    """Roles, tags and phases come from the legend, with — for drop and new for NEW rows only."""
    row = row_of("DATA-01")
    problems = check(edited(row, row.replace(old, new, 1)), IDS)
    assert any(f"DATA-01: {message}" in problem for problem in problems), problems


def test_a_row_in_another_section_is_reported() -> None:
    """A row under the wrong section heading is reported, with both sections' counts off."""
    row = row_of("DATA-01")
    text = edited(row + "\n", "").replace(
        row_of("STORE-01"), row_of("STORE-01") + "\n" + row
    )
    problems = check(text, IDS)
    assert any("DATA-01: in section STORE" in problem for problem in problems)
    assert any("section DATA says 35 rows, has 34" in problem for problem in problems)
    assert any("section STORE says 13 rows, has 14" in problem for problem in problems)


def test_an_escaped_pipe_stays_inside_its_cell() -> None:
    """DATA-28's approach holds an escaped pipe; its cells do not shift, so its row checks clean."""
    assert "\\|" in row_of("DATA-28")
    assert not [problem for problem in check(TEXT, IDS) if "DATA-28" in problem]


def test_breakdown_lists_dispositions_and_sections() -> None:
    """The on-demand breakdown has every exact disposition and one line per section."""
    text = breakdown(TEXT)
    assert "| `improve+mock` |" in text
    assert re.search(
        r"^\| NEW \| 1 \| 3 \| 3 \| 1 \| 1 \| \| 9 \|$", text, re.MULTILINE
    )


def test_main_exits_zero_on_the_real_matrix(capsys: pytest.CaptureFixture[str]) -> None:
    """The command exits 0 and says so when the matrix is consistent."""
    assert main([]) == 0
    assert "the matrix is consistent" in capsys.readouterr().out
