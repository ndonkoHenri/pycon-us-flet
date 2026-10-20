"""The decision record keeps one row per id: a merge must not leave two versions of a row."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _ids(path: str, pattern: str) -> list[str]:
    """Return the ids that open a table row of ``path``, in file order."""
    return re.findall(pattern, (ROOT / path).read_text(), re.MULTILINE)


def test_every_decision_fact_and_gap_id_has_one_row() -> None:
    """Each D-, F- and U-number opens exactly one table row in the docs that record them."""
    for path, pattern in (
        ("docs/decisions.md", r"^\| (D-\d+) \|"),
        ("docs/decisions.md", r"^\| (F\d+) \|"),
        ("docs/flet-gaps-and-extensions.md", r"^\| \d+ \| \*\*(U\d+)\*\* \|"),
    ):
        ids = _ids(path, pattern)
        assert ids, f"no rows matched {pattern} in {path}"
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        assert not duplicates, f"{path}: {duplicates} appear in more than one row"
