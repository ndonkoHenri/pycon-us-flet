"""Check `docs/feature-matrix.md` against the feature catalog and its own legend (D-04, #802).

From the repo root, after editing the matrix:

    uv run python -m tools.check_matrix               # check; exit 1 and list the problems
    uv run python -m tools.check_matrix --breakdown   # also print the fuller breakdowns

It checks that every id of `docs/research/feature-catalog.json` and every `NEW-` id is
one row, exactly once; that each row's roles, disposition tags and phase use the legend's
vocabulary (`—` is the phase of `drop` rows only, `new` the tag of `NEW-` rows
only); that each row sits in its id's section and each section's "N rows" line is right;
and that the Counts tables are current. A stale Counts table is printed as it should be,
ready to paste. `tests/test_check_matrix.py` runs the check on the real matrix, so the
local checks (`tools/check.sh`) fail on a matrix edit that forgets the counts.

The breakdowns (by exact disposition, by section and phase) are printed on demand only,
so the matrix does not keep them by hand.
"""

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MATRIX = ROOT / "docs" / "feature-matrix.md"
CATALOG = ROOT / "docs" / "research" / "feature-catalog.json"

TAGS = ("keep", "improve", "redesign", "mock", "interim", "later", "drop", "new")
"""The legend's disposition tags, in the Counts table's column order."""

PHASES = ("P0", "P1", "P2", "P3", "P4", "—")
"""The legend's phases, in the Counts table's column order; `—` is dropped."""

ROLES = frozenset({"all", "attendee", "sponsor", "staff", "developer"})

NEW_PREFIX = "NEW-"
GROUPS = ("catalog", "NEW")

_CELL_SPLIT = re.compile(
    r"(?<!\\)\|"
)  # a cell may hold an escaped pipe, as in str\|int
_SECTION = re.compile(r"^### (\S+) · ")
_SECTION_ROWS = re.compile(r"^(\d+) rows? · ")
_NEW_ID = re.compile(r"^NEW-\d\d$")


@dataclass(frozen=True)
class Row:
    """One feature row of the matrix, the cells the check reads."""

    id: str
    section: str
    roles: tuple[str, ...]
    tags: tuple[str, ...]
    disposition: str
    phase: str
    line: int

    @property
    def group(self) -> str:
        """`NEW` for our additions, `catalog` for the Ionic app's features."""
        return "NEW" if self.id.startswith(NEW_PREFIX) else "catalog"


@dataclass(frozen=True)
class Matrix:
    """The parsed matrix: its rows and each section's stated row count."""

    lines: tuple[str, ...]
    rows: tuple[Row, ...]
    stated: dict[str, tuple[int, int]]
    """Each section's "N rows" count, with its 1-based line number."""


def parse(text: str) -> Matrix:
    """Read the feature rows and the sections' "N rows" lines out of the matrix's Markdown."""
    lines = tuple(text.splitlines())
    rows: list[Row] = []
    stated: dict[str, tuple[int, int]] = {}
    section = ""
    for number, line in enumerate(lines, start=1):
        if heading := _SECTION.match(line):
            section = heading.group(1)
        elif (count := _SECTION_ROWS.match(line)) and section:
            stated[section] = (int(count.group(1)), number)
        elif (
            line.startswith("| **") and section
        ):  # the Counts table's **all** row comes before any section
            cells = [cell.strip() for cell in _CELL_SPLIT.split(line)[1:-1]]
            disposition = cells[3].strip("`")
            rows.append(
                Row(
                    id=cells[0].strip("*"),
                    section=section,
                    roles=tuple(role.strip() for role in cells[2].split(",")),
                    tags=tuple(disposition.split("+")),
                    disposition=disposition,
                    phase=cells[4],
                    line=number,
                )
            )
    return Matrix(lines, tuple(rows), stated)


def row_problems(matrix: Matrix, catalog_ids: Sequence[str]) -> list[str]:
    """Each problem with the rows themselves: ids, vocabulary, sections."""
    problems: list[str] = []
    seen = Counter(row.id for row in matrix.rows)
    for id_, times in sorted(seen.items()):
        if times > 1:
            problems.append(f"{id_} appears {times} times")
    known = set(catalog_ids)
    problems += [
        f"{id_} is in the catalog but not in the matrix"
        for id_ in catalog_ids
        if id_ not in seen
    ]
    for row in matrix.rows:
        where = f"line {row.line}, {row.id}"
        if row.group == "catalog" and row.id not in known:
            problems.append(f"{where}: not a catalog id (nor NEW-NN)")
        if row.group == "NEW" and not _NEW_ID.match(row.id):
            problems.append(f"{where}: a NEW id is NEW- and two digits")
        if not row.id.startswith(f"{row.section}-"):
            problems.append(f"{where}: in section {row.section or '(none)'}")
        problems += [
            f"{where}: unknown role {role!r}" for role in row.roles if role not in ROLES
        ]
        problems += [
            f"{where}: unknown tag {tag!r}" for tag in row.tags if tag not in TAGS
        ]
        if row.phase not in PHASES:
            problems.append(f"{where}: unknown phase {row.phase!r}")
        if (row.phase == "—") != ("drop" in row.tags):
            problems.append(f"{where}: phase — goes with drop, and only with it")
        if ("new" in row.tags) != (row.group == "NEW"):
            problems.append(f"{where}: new is the tag of NEW- rows, and only theirs")
    sections = Counter(row.section for row in matrix.rows)
    for section, (count, line) in matrix.stated.items():
        if sections[section] != count:
            problems.append(
                f"line {line}: section {section} says {count} rows, has {sections[section]}"
            )
    return problems


def _line(cells: Sequence[str]) -> str:
    """A Markdown table line; an empty cell is one space, as the matrix writes it."""
    return "|" + "|".join(f" {cell} " if cell else " " for cell in cells) + "|"


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    """A Markdown table's lines, header first."""
    return [_line(header), "|" + "---|" * len(header), *(_line(row) for row in rows)]


def counts_tables(rows: Sequence[Row]) -> tuple[list[str], list[str]]:
    """The two Counts tables, by tag and by phase, as the matrix should show them."""
    by_tag = []
    by_phase = []
    for group in GROUPS:
        mine = [row for row in rows if row.group == group]
        tags = Counter(tag for row in mine for tag in row.tags)
        phases = Counter(row.phase for row in mine)
        by_tag.append([group, *(str(tags[tag]) for tag in TAGS), str(len(mine))])
        by_phase.append(
            [group, *(str(phases[phase]) for phase in PHASES), str(len(mine))]
        )
    phases = Counter(row.phase for row in rows)
    by_phase.append(
        [
            f"**{cell}**"
            for cell in ("all", *(str(phases[p]) for p in PHASES), str(len(rows)))
        ]
    )
    tag_header = ["", *(f"`{tag}`" for tag in TAGS), "rows"]
    phase_header = ["", *PHASES[:-1], "— (dropped)", "total"]
    return _table(tag_header, by_tag), _table(phase_header, by_phase)


def counts_problems(matrix: Matrix) -> list[str]:
    """A problem for each Counts table that is missing or stale, with the table it should be."""
    problems = []
    for name, expected in zip(
        ("by tag", "by phase"), counts_tables(matrix.rows), strict=True
    ):
        try:
            start = matrix.lines.index(expected[0])
        except ValueError:
            problems.append(
                f"the Counts table {name} is missing; it should be:\n"
                + "\n".join(expected)
            )
            continue
        found = list(matrix.lines[start : start + len(expected)])
        if found != expected:
            problems.append(
                f"line {start + 1}: the Counts table {name} is stale; it should be:\n"
                + "\n".join(expected)
            )
    return problems


def check(text: str, catalog_ids: Sequence[str]) -> list[str]:
    """Every problem with the matrix `text` against the catalog's ids; empty when it is right."""
    matrix = parse(text)
    return row_problems(matrix, catalog_ids) + counts_problems(matrix)


def breakdown(text: str) -> str:
    """The fuller breakdowns: rows by exact disposition, and by section and phase."""
    rows = parse(text).rows
    dispositions = Counter(row.disposition for row in rows)
    by_disposition = _table(
        ["disposition", "rows"],
        [
            [f"`{name}`", str(count)]
            for name, count in sorted(
                dispositions.items(), key=lambda kv: (-kv[1], kv[0])
            )
        ],
    )
    sections = list(dict.fromkeys(row.section for row in rows))
    cells = Counter((row.section, row.phase) for row in rows)
    by_section = _table(
        ["section", *PHASES, "rows"],
        [
            [
                section,
                *(str(cells[section, phase] or "") for phase in PHASES),
                str(sum(r.section == section for r in rows)),
            ]
            for section in sections
        ],
    )
    return "\n".join(
        [
            "By disposition:",
            "",
            *by_disposition,
            "",
            "By section and phase:",
            "",
            *by_section,
        ]
    )


def catalog_ids(path: Path = CATALOG) -> list[str]:
    """The ids of the catalog's features, in its order."""
    return [feature["id"] for feature in json.loads(path.read_text(encoding="utf-8"))]


def main(argv: Sequence[str] | None = None) -> int:
    """Check the matrix and print its problems (and the breakdowns on request); 0 when it is right."""
    parser = argparse.ArgumentParser(description="Check docs/feature-matrix.md (D-04).")
    parser.add_argument(
        "--breakdown", action="store_true", help="also print the fuller breakdowns"
    )
    args = parser.parse_args(argv)
    text = MATRIX.read_text(encoding="utf-8")
    problems = check(text, catalog_ids())
    for problem in problems:
        print(problem)
    if args.breakdown:
        print(breakdown(text))
    print(
        f"check_matrix: {len(problems)} problem(s)"
        if problems
        else "check_matrix: the matrix is consistent"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
