"""The decision record stays whole: one row per id, every citation resolves, every amendment is marked."""

import os
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = "docs/decisions.md"
GAPS = "docs/flet-gaps-and-extensions.md"
DECISION_ROW = r"^\| (D-\d+) \|"
FACT_ROW = r"^\| (F\d+) \|"
TOP_LEVEL_DOCS = [*ROOT.glob("*.md"), *(ROOT / "docs").glob("*.md")]
# Folders that hold no Markdown of ours: the Ionic checkout, build output and installed packages. So are the hidden
# ones (git's own, virtual environments, caches, the Flet checkout), except `.github`.
NOT_OURS = {"excluded", "build", "node_modules"}

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
    """Return the ids that open a table row of `path`, in file order."""
    return re.findall(pattern, (ROOT / path).read_text(), re.MULTILINE)


def _amended(row: str) -> list[str]:
    """Return the ids a decision row says it amends, reading its prose without the code spans."""
    # A `)` in a code span, as in `build_tile()`, isn't the end of the clause.
    clauses = AMENDS.findall(CODE_SPAN.sub("", row))
    return [amended for clause in clauses for amended in re.findall(r"D-\d+", clause)]


def _all_docs() -> list[Path]:
    """Return every Markdown file of the repository, the README of a tool or a spike and a GitHub template included."""
    docs = []
    for folder, subfolders, files in os.walk(ROOT):
        # Pruned while walking, so an optional Flet clone (`.flet-src`) is never entered.
        subfolders[:] = [
            name
            for name in subfolders
            if name not in NOT_OURS and (name == ".github" or not name.startswith("."))
        ]
        docs += [Path(folder, name) for name in files if name.endswith(".md")]
    return docs


def _anchors(path: Path) -> set[str]:
    """Return GitHub's anchor for each heading of a Markdown file."""
    headings = re.findall(
        r"^#{1,6} +(.+)$", FENCE.sub("", path.read_text()), re.MULTILINE
    )
    anchors = set()
    seen = Counter()
    for heading in headings:
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        # GitHub numbers the repeats of a heading: slug, slug-1, slug-2.
        anchors.add(f"{slug}-{seen[slug]}" if seen[slug] else slug)
        seen[slug] += 1
    return anchors


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

    `docs/research` is left out: it is the raw analysis, in the v1 numbers. So is "v1 D-nn", the v1 record's form.
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


def test_relative_links_and_anchors_in_every_doc_resolve() -> None:
    """Each relative link in the repository's Markdown leads to a file and, if it names one, a heading."""
    broken = [
        f"{doc.relative_to(ROOT)}: {target}"
        for doc in _all_docs()
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
        for amended in _amended(row)
        if row_id not in named.get(amended, ())
    )
    assert not unmarked, unmarked


def test_a_code_span_does_not_end_an_amends_clause() -> None:
    """An id amended after a code span holding a `)` is read, and "keeps" still ends the clause."""
    row = "(amends D-50's `build_tile()` and D-62's signature, keeps D-70)"
    assert _amended(row) == ["D-50", "D-62"]


def test_a_repeated_heading_gets_githubs_numbered_anchor(tmp_path: Path) -> None:
    """The n-th repeat of a heading is linked as `slug-n`, as GitHub numbers it; past the last repeat is broken."""
    doc = tmp_path / "doc.md"
    doc.write_text("# Other issues\n\n## Other issues\n\n## Other issues\n")
    assert not _broken_link(doc, "#other-issues")
    assert not _broken_link(doc, "#other-issues-1")
    assert not _broken_link(doc, "#other-issues-2")
    assert _broken_link(doc, "#other-issues-3")
