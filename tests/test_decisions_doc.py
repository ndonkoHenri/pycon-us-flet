"""The decision record stays whole: one row per id, every citation resolves, every amendment is marked."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = "docs/decisions.md"
GAPS = "docs/flet-gaps-and-extensions.md"
DECISION_ROW = r"^\| (D-\d+) \|"
FACT_ROW = r"^\| (F\d+) \|"
TOP_LEVEL_DOCS = [*ROOT.glob("*.md"), *(ROOT / "docs").glob("*.md")]

# Ruff's rule names, which a noqa or a testing doc cites and which look like fact ids.
RUFF_RULES = {"F401", "F811"}
# Not after a word, a dash, a backslash (Python's \U escapes) or a # (a hex colour).
NOT_INSIDE = r"(?<![\w\\#-])"
# Fenced code first, then a code span of any number of backticks.
FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
CODE_SPAN = re.compile(r"(`+)(?!`).*?(?<!`)\1(?!`)")
# A link without a scheme.
LINK = re.compile(r"\]\((?!\w+:)([^)\s]+)\)")
# From "amends" to the end of what it amends: "amends D-x and keeps D-y" amends only D-x.
AMENDS = re.compile(r"\bamend(?:s|ing)\b(.*?)(?=keeps|;|\)|\. |<br>|$)", re.IGNORECASE)


def _ids(path: str, pattern: str) -> list[str]:
    """Return the ids that open a table row of ``path``, in file order."""
    return re.findall(pattern, (ROOT / path).read_text(), re.MULTILINE)


def _anchors(path: Path) -> set[str]:
    """Return GitHub's anchor for each heading of a Markdown file."""
    headings = re.findall(
        r"^#{1,6} +(.+)$", FENCE.sub("", path.read_text()), re.MULTILINE
    )
    return {re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-") for h in headings}


def _broken_link(doc: Path, target: str) -> bool:
    """Say whether a relative link leads to no file, or to no heading of that file."""
    path, _, anchor = target.partition("#")
    dest = doc.parent / path if path else doc
    return not dest.exists() or bool(
        anchor and dest.suffix == ".md" and anchor not in _anchors(dest)
    )


def test_every_decision_fact_and_gap_id_has_one_row() -> None:
    """Each D-, F- and U-number opens exactly one table row in the docs that record them."""
    for path, pattern in (
        (DECISIONS, DECISION_ROW),
        (DECISIONS, FACT_ROW),
        (GAPS, r"^\| \d+ \| \*\*(U\d+)\*\* \|"),
    ):
        ids = _ids(path, pattern)
        assert ids, f"no rows matched {pattern} in {path}"
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        assert not duplicates, f"{path}: {duplicates} appear in more than one row"


def test_every_cited_id_resolves() -> None:
    """A D- or F-number cited in the docs, src or tests has its row, and a U-number is in the gaps doc.

    ``docs/research`` is left out: it is the raw analysis, in the v1 numbers. So is "v1 D-nn", the v1 record's form.
    """
    known = {
        rf"(?<!v1 ){NOT_INSIDE}D-\d+\b": set(_ids(DECISIONS, DECISION_ROW)),
        rf"{NOT_INSIDE}F\d+\b": set(_ids(DECISIONS, FACT_ROW)) | RUFF_RULES,
        rf"{NOT_INSIDE}U\d+\b": set(re.findall(r"\bU\d+\b", (ROOT / GAPS).read_text())),
    }
    research = ROOT / "docs" / "research"
    citing = [
        *ROOT.glob("*.md"),
        *(p for p in (ROOT / "docs").rglob("*.md") if not p.is_relative_to(research)),
        *(ROOT / "src").rglob("*.py"),
        *(ROOT / "tests").rglob("*.py"),
    ]
    unresolved = {
        f"{path.relative_to(ROOT)}: {cited}"
        for path in citing
        for pattern, ids in known.items()
        for cited in re.findall(pattern, path.read_text())
        if cited not in ids
    }
    assert not unresolved, sorted(unresolved)


def test_relative_links_and_anchors_in_the_top_level_docs_resolve() -> None:
    """Each relative link in the root's and ``docs/``'s Markdown leads to a file and, if it names one, a heading."""
    broken = [
        f"{doc.relative_to(ROOT)}: {target}"
        for doc in TOP_LEVEL_DOCS
        for target in LINK.findall(CODE_SPAN.sub("", FENCE.sub("", doc.read_text())))
        if _broken_link(doc, target)
    ]
    assert not broken, broken


def test_a_row_that_amends_another_is_named_in_it() -> None:
    """A row saying "amends D-x" is named in D-x's row, so a reader of D-x learns its words have changed."""
    text = (ROOT / DECISIONS).read_text()
    rows = {m[1]: m[0] for m in re.finditer(rf"{DECISION_ROW}.*$", text, re.MULTILINE)}
    named = {row_id: set(re.findall(r"D-\d+", row)) for row_id, row in rows.items()}
    unmarked = sorted(
        f"{amended} doesn't name {row_id}"
        for row_id, row in rows.items()
        for clause in AMENDS.findall(row)
        for amended in re.findall(r"D-\d+", clause)
        if row_id not in named.get(amended, ())
    )
    assert not unmarked, unmarked
