"""Tests for the semantics helpers and the scans of every app module.

The helpers are ``ui/semantics.py``'s (decisions §M, D-200). The scans hold every
``Semantics`` heading to a level (F40, F49, D-211), every merged identifier to
``named()`` (D-214), and keep a bare identifier off a button, chip, field or tile
(F50, D-230).
"""

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple, cast

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


# ------------------------------------------------------------- bare identifiers

TAKEN_IN = ("Button", "Chip", "TextField", "Tile")
"""The name endings of the controls that a bare identifier splits from (F50).

Every ``*Button`` (``PopupMenuButton`` too), every ``*Chip``, ``TextField``, and every
``*Tile``: ``ListTile``, and the folds' ``ExpansionTile`` and ``FoldTile``.
"""

ON_PURPOSE = {
    # D-214: a merge would take in the clock's picker, which would stop being a
    # button of its own; an empty node of its own until U34. (The same function
    # merges the feed URL's field, which has no picker, through named().)
    ("developer.py", "option_field", "identifier"): "developer.fake_clock",
    # D-214: the folds, around the tile and not merged, which would take in the rows
    # they hold; an empty node of their own until an identifier on the control itself.
    ("lightning_talks.py", "doubts_fold", "f'{SCREEN}.doubts'"): (
        "lightning_talks.doubts"
    ),
    ("my_schedule.py", "_fold", "identifier"): (
        "my_schedule.earlier_days, my_schedule.earlier_today"
    ),
    ("when_where.py", "OtherRooms", "f'{screen}.other_rooms'"): "session.other_rooms",
    # D-230: inside a PopupMenuItem, whose own MergeSemantics takes the identifier
    # into the item's node (Flutter's popup_menu.dart); a uiautomator dump shows it.
    ("track.py", "_menu", "f'{SCREEN}.add_all'"): "track.add_all",
}
"""The bare identifiers left so on purpose, and the identifiers they give at run time.

Keyed by module, function and identifier as written, so another bare identifier in
the same module, or under the same parameter name elsewhere, is still found.
"""


class BareIdentifier(NamedTuple):
    """A bare identifier the scan found: where it is, and the identifier as written."""

    line: int
    function: str
    identifier: str


def is_taken_in(name: str) -> bool:
    """Whether a call of ``name`` builds a control that a bare identifier splits from."""
    return name.endswith(TAKEN_IN)


def bare_identifiers(source: str) -> list[BareIdentifier]:
    """Return each bare identifier in ``source`` around a button, chip, field or tile.

    A ``Semantics`` call that passes ``identifier`` and nothing else but ``content``
    and ``disabled``, not straight inside a ``MergeSemantics``, whose ``content`` is
    a call of one of ``TAKEN_IN``, or a name its function assigns such a call to
    (screens build the control first: ``fold = FoldTile(...)``).
    """
    tree = ast.parse(source)
    parents = {
        child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
    }
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and called(node) == "Semantics"):
            continue
        keywords = {k.arg: k.value for k in node.keywords}
        if not ("identifier" in keywords and keywords.keys() <= NAMED_KEYWORDS):
            continue
        scope = scope_of(node, parents)
        content = keywords.get("content")
        if isinstance(content, ast.Call):
            splits = is_taken_in(called(content))
        elif isinstance(content, ast.Name):
            splits = content.id in taken_in_names(scope)
        else:
            splits = False
        if splits and not is_merged(node, parents):
            function = getattr(scope, "name", "")
            identifier = ast.unparse(keywords["identifier"])
            found.append(BareIdentifier(node.lineno, function, identifier))
    return found


def scope_of(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.AST:
    """Return the function around ``node``, or its module."""
    while node in parents and not isinstance(
        node, ast.FunctionDef | ast.AsyncFunctionDef
    ):
        node = parents[node]
    return node


def taken_in_names(scope: ast.AST) -> set[str]:
    """Return the names that ``scope`` assigns a button, chip, field or tile to.

    Any of its own assignments counts (a nested function's or class's does not):
    ``label: ft.Control = ft.Text(...)`` and then ``label = ft.Row(...)`` builds
    neither, one ``ft.ListTile`` among them does.
    """
    names = set()
    for node in own_nodes(scope):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if isinstance(node.value, ast.Call) and is_taken_in(called(node.value)):
            names |= {target.id for target in targets if isinstance(target, ast.Name)}
    return names


NESTED_SCOPES = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda
"""The nodes whose names are their own, not the names of the scope around them."""


def own_nodes(scope: ast.AST) -> Iterator[ast.AST]:
    """Yield the nodes of ``scope``, without those of the functions and classes in it.

    A nested helper's ``control = ft.TextButton(...)`` names its own ``control``, not
    the outer function's parameter of that name.
    """
    pending = list(ast.iter_child_nodes(scope))
    while pending:
        node = pending.pop()
        yield node
        if not isinstance(node, NESTED_SCOPES):
            pending.extend(ast.iter_child_nodes(node))


def is_merged(node: ast.Call, parents: dict[ast.AST, ast.AST]) -> bool:
    """Whether ``node`` is the content of a ``MergeSemantics``, as ``named()`` does."""
    above = parents.get(node)
    if isinstance(above, ast.keyword) and above.arg == "content":
        above = parents.get(above)
    return isinstance(above, ast.Call) and called(above) == "MergeSemantics"


def screen(*lines: str) -> str:
    """Return a module's source: ``screen(control)``, whose body is ``lines``."""
    return "def screen(control):\n" + "".join(f"    {line}\n" for line in lines)


BARE = 'ft.Semantics(identifier="x", content=ft.TextButton("Go"))'
"""The shape the scan is for: an identifier alone around a button."""

SPLIT = {
    "button": [f"return {BARE}"],
    "disabled-chip": [
        'return Semantics(identifier="x", disabled=True, content=ft.Chip("Go"))'
    ],
    "built-first": [
        "button = ft.IconButton(ft.Icons.SHARE)",
        'return ft.Semantics(identifier="x", content=button)',
    ],
    "reassigned": [
        'tile: ft.Control = ft.Text("Go")',
        "tile = ft.ListTile(title=tile)",
        'return ft.Semantics(identifier="x", content=tile)',
    ],
    "in-a-column": [
        'return ft.Column([ft.Semantics(identifier="x", content=ft.TextField())])'
    ],
}
"""Function bodies whose last line splits an identifier from its control."""

KEPT = {
    "merged": [f"return ft.MergeSemantics(content={BARE})"],
    "merged-positionally": [f"return ft.MergeSemantics({BARE})"],
    "labelled": [
        'return ft.Semantics(identifier="x", label="Go", content=ft.TextField())'
    ],
    "text": ['return ft.Semantics(identifier="x", content=ft.Text("Go"))'],
    "icon": ['return ft.Semantics(identifier="x", content=ft.Icon(ft.Icons.SHARE))'],
    "parameter": ['return ft.Semantics(identifier="x", content=control)'],
    "shadowed-in-a-helper": [
        "def helper():",
        '    control = ft.TextButton("Go")',
        "    return control",
        'return ft.Semantics(identifier="x", content=control)',
    ],
    "shadowed-in-a-class": [
        "class Helper:",
        '    control = ft.TextButton("Go")',
        'return ft.Semantics(identifier="x", content=control)',
    ],
    "no-identifier": ['return ft.Semantics(content=ft.TextButton("Go"))'],
}
"""Function bodies the scan leaves: merged, saying more, or around no such control.

A nested helper or class names its own ``control``, not the parameter it shadows.
"""


@pytest.mark.parametrize("lines", SPLIT.values(), ids=SPLIT.keys())
def test_the_bare_scan_flags_an_identifier_split_from_its_control(
    lines: list[str],
) -> None:
    """F50: a bare identifier around a button, chip, field or tile is a node apart.

    Found on its line, in its function, with the identifier as written, whether the
    control is built in the call or first, under a name.
    """
    found = bare_identifiers(screen(*lines))
    assert found == [BareIdentifier(len(lines) + 1, "screen", "'x'")]


@pytest.mark.parametrize("lines", KEPT.values(), ids=KEPT.keys())
def test_the_bare_scan_leaves_other_shapes(lines: list[str]) -> None:
    """``named()``'s merge, a ``Semantics`` with more to say, or around no such control."""
    assert bare_identifiers(screen(*lines)) == []


def site(path: Path, bare: BareIdentifier) -> tuple[str, str, str]:
    """Return a bare identifier's key in ``ON_PURPOSE``."""
    return (path.name, bare.function, bare.identifier)


def test_the_bare_scan_finds_every_identifier_left_bare_on_purpose() -> None:
    """A scan that matched nothing would pass whatever the code says.

    Each site of ``ON_PURPOSE`` is found where it is, so a stale entry fails too.
    """
    found = {
        site(path, bare)
        for path in SOURCES
        for bare in bare_identifiers(path.read_text(encoding="utf-8"))
    }
    assert ON_PURPOSE.keys() <= found


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_bare_identifier_splits_from_its_control(path: Path) -> None:
    """F50, D-214, D-230: a bare identifier around a control is a node beside it.

    Around a button TalkBack stops on an empty ``View``, then on the button; around
    one with a tooltip the identifier's node holds the name and the button is
    unnamed. ``named()`` merges the two into one node; the sites in ``ON_PURPOSE``
    cannot be merged, and say why.
    """
    unexpected = [
        f"{path.name}:{bare.line}: {bare.identifier}"
        for bare in bare_identifiers(path.read_text(encoding="utf-8"))
        if site(path, bare) not in ON_PURPOSE
    ]
    assert unexpected == []
