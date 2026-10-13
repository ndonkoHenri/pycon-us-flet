"""Tests for the semantics helpers and the heading scan of every app module.

The helpers are ``ui/semantics.py``'s (decisions §M, D-200); the scan holds every
``Semantics`` heading to a level (F40, F49, D-211).
"""

import ast
from pathlib import Path
from typing import cast

import flet as ft
import pytest

import pycon_us
from pycon_us.ui.semantics import named, semantics_key

TALK = "142"
"""A talk: a numeric id."""

COFFEE = "break-Expo Hall AB-2026-05-15T08:00:00-07:00"
"""A synthetic break id, with spaces and colons (D-42)."""


def test_a_semantics_key_is_safe_in_a_selector() -> None:
    """Decisions §M: a break's id has spaces and colons; its key has neither."""
    assert semantics_key(COFFEE) == "break-expo-hall-ab-2026-05-15t08-00-00-07-00"
    assert semantics_key("poster-detail-60") == "poster-detail-60"
    assert semantics_key(TALK) == TALK


def test_a_named_disabled_button_s_node_says_it_is_disabled() -> None:
    """F42: Flutter's ``enabled`` comes from the ``Semantics``' own ``disabled``.

    ``named()`` reads it from the control, so a caller cannot forget it (D-214).
    """
    button = ft.IconButton(ft.Icons.SHARE_OUTLINED, disabled=True)
    merged = named("session.share", button)
    assert isinstance(merged, ft.MergeSemantics)
    node = merged.content
    assert isinstance(node, ft.Semantics)
    assert (node.identifier, node.disabled, node.content) == (
        "session.share",
        True,
        button,
    )
    enabled = named("session.share", ft.IconButton(ft.Icons.SHARE_OUTLINED))
    assert not cast(ft.Semantics, cast(ft.MergeSemantics, enabled).content).disabled


def test_a_named_row_follows_its_tile_s_state() -> None:
    """#239: a disabled Developer row read as enabled; its node now follows the tile."""
    for disabled in (True, False):
        tile = ft.ListTile(title="Clear cached feed", disabled=disabled)
        node = cast(ft.MergeSemantics, named("developer.clear_cache", tile)).content
        assert cast(ft.Semantics, node).disabled is disabled


def test_a_semantics_passed_for_the_button_needs_the_button_s_disabled() -> None:
    """F42: ``named()`` reads only the control it gets, not the button inside it.

    The open spaces' Propose and a sprint's More pass a ``Semantics`` (a label,
    ``expanded``) in the button's place: its ``disabled`` is its own, ``False``
    unless it is given the button's, as ``named()``'s docstring says.
    """
    button = ft.TextButton("More", disabled=True)
    bare = cast(
        ft.MergeSemantics, named("sprints.more.x", ft.Semantics(content=button))
    )
    assert not cast(ft.Semantics, bare.content).disabled
    wrapped = ft.Semantics(expanded=False, disabled=button.disabled, content=button)
    told = cast(ft.MergeSemantics, named("sprints.more.x", wrapped))
    assert cast(ft.Semantics, told.content).disabled


# ------------------------------------------------------------------ headings

SOURCES = sorted(Path(pycon_us.__file__).parent.rglob("*.py"))
"""Every module of the app, where a ``Semantics`` may mark a heading."""


def heading_calls(path: Path) -> list[tuple[int, dict[str, ast.expr]]]:
    """Return each heading call in ``path``: a ``Semantics(...)`` or a ``SectionHeader``.

    Its line and its keywords, for every ``Semantics`` call that passes ``header``
    or ``heading_level``, whether it is spelled ``ft.Semantics`` or ``Semantics``,
    or a ``SectionHeader(level=...)`` call, whose ``level`` is its heading's
    ``heading_level``.
    """
    calls = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        keywords = {k.arg: k.value for k in node.keywords if k.arg}
        if name == "Semantics" and {"header", "heading_level"} & keywords.keys():
            calls.append((node.lineno, keywords))
        elif name == "SectionHeader" and "level" in keywords:
            # SectionHeader forwards its level as a name, which the scan of its own
            # Semantics can't range-check: check the callers' levels instead.
            heading = {"header": ast.Constant(True), "heading_level": keywords["level"]}
            calls.append((node.lineno, heading))
    return calls


def is_unset(value: ast.expr | None) -> bool:
    """Whether a keyword's value is missing, ``None`` or ``False``."""
    return value is None or (
        isinstance(value, ast.Constant) and value.value in (None, False)
    )


def test_the_scan_finds_the_headings_it_checks() -> None:
    """A scan that matched nothing would pass whatever the code says.

    The modules named here define a heading with its own ``Semantics``, rather than
    tune a ``SectionHeader``'s level, so they match whatever level a screen picks.
    """
    found = {path.name for path in SOURCES if heading_calls(path)}
    defining = {
        "scaffold.py",
        "states.py",
        "time_gutter.py",
        "now_header.py",
        "session.py",
    }
    assert defining <= found
    assert len(found) >= 10


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_every_heading_has_both_the_flag_and_a_level(path: Path) -> None:
    """F40, F49, D-211: a heading is ``header=True`` with a level from 1 to 6.

    Both of Flutter's bridges make a heading only of a level above 0, so the flag
    alone is none for TalkBack or VoiceOver; the flag goes with it, as Flutter and
    Flet call a heading a header. Flutter takes levels 1 to 6.
    """
    wrong = []
    for line, keywords in heading_calls(path):
        level = keywords.get("heading_level")
        if is_unset(keywords.get("header")) or is_unset(level):
            wrong.append(f"{path.name}:{line}")
        elif isinstance(level, ast.Constant) and level.value not in range(1, 7):
            wrong.append(f"{path.name}:{line}: level {level.value!r}")
    assert wrong == []


# ------------------------------------------------------------ merged identifiers


def called(node: ast.Call) -> str:
    """Return the name a call calls: ``Semantics`` for ``ft.Semantics(...)``."""
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


NAMED_KEYWORDS = {"identifier", "content", "disabled"}
"""The keywords of the ``Semantics`` that ``named()`` merges."""


def hand_merges(path: Path) -> list[int]:
    """Return the lines of ``path`` that build ``named()``'s shape by hand.

    A ``MergeSemantics`` straight around a ``Semantics`` that passes ``identifier``
    and nothing else but ``content`` and ``disabled``: what ``named()`` returns.
    """
    lines = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not (isinstance(node, ast.Call) and called(node) == "MergeSemantics"):
            continue
        inner = [*node.args, *(k.value for k in node.keywords if k.arg == "content")]
        if not (inner and isinstance(inner[0], ast.Call)):
            continue
        keywords = {k.arg for k in inner[0].keywords}
        only_named_s = "identifier" in keywords and keywords <= NAMED_KEYWORDS
        if called(inner[0]) == "Semantics" and only_named_s:
            lines.append(node.lineno)
    return lines


def test_the_merge_scan_finds_named_s_own_shape() -> None:
    """A scan that matched nothing would pass whatever the code says."""
    assert hand_merges(Path(pycon_us.__file__).parent / "ui" / "semantics.py")


@pytest.mark.parametrize(
    "path", [p for p in SOURCES if p.name != "semantics.py"], ids=lambda p: p.name
)
def test_identifiers_are_merged_through_named(path: Path) -> None:
    """D-214, ux.md §9: ``named()`` is the one way to merge an identifier.

    A copy by hand has to pass the control's ``disabled`` itself, which the
    Developer rows' didn't (F42). A merge with more keywords (a label, the link
    flag) is another shape, and stays.
    """
    assert hand_merges(path) == []
