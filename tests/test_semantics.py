"""Tests for the semantics helpers (``ui/semantics.py``; decisions §M, D-200)."""

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
    """F42: Flutter's ``enabled`` comes from the ``Semantics``' own ``disabled``."""
    button = ft.IconButton(ft.Icons.SHARE_OUTLINED, disabled=True)
    merged = named("session.share", button, disabled=True)
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


# ------------------------------------------------------------------ headings

SOURCES = sorted(Path(pycon_us.__file__).parent.rglob("*.py"))
"""Every module of the app, where a ``Semantics`` may mark a heading."""


def heading_calls(path: Path) -> list[tuple[int, dict[str, ast.expr]]]:
    """Return each ``Semantics(...)`` call in ``path`` that sets a heading keyword.

    Its line and its keywords, for every call that passes ``header`` or
    ``heading_level``, whether it is spelled ``ft.Semantics`` or ``Semantics``.
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
    return calls


def is_unset(value: ast.expr | None) -> bool:
    """Whether a keyword's value is missing, ``None`` or ``False``."""
    return value is None or (
        isinstance(value, ast.Constant) and value.value in (None, False)
    )


def test_the_scan_finds_the_headings_it_checks() -> None:
    """A scan that matched nothing would pass whatever the code says."""
    found = {path.name for path in SOURCES if heading_calls(path)}
    assert {"scaffold.py", "states.py", "time_gutter.py", "more.py"} <= found


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_every_heading_has_both_the_flag_and_a_level(path: Path) -> None:
    """F40, F46, D-208: a heading is ``header=True`` with a level from 1 to 6.

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
