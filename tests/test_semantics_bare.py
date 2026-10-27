"""Tests for the scan that keeps a bare identifier off a button, chip, field or tile.

F50, D-230: a ``Semantics`` identifier set beside such a control, not merged into it,
splits from the control's node. The scan reads every app module's source
(``tests/test_semantics.py``'s ``SOURCES``); the helpers and the other scans are
``tests/test_semantics.py``'s (#623).
"""

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

import pytest

from tests.test_semantics import NAMED_KEYWORDS, SOURCES, called

TAKEN_IN = ("Button", "Chip", "TextField", "Tile")
"""The name endings of the controls that a bare identifier splits from (F50).

Every ``*Button`` (``PopupMenuButton`` too), every ``*Chip``, ``TextField``, and every
``*Tile``: ``ListTile``, ``ExpansionTile`` and the app's fold, ``FoldTile``, whose
identifier goes on its header (D-354).
"""


ON_PURPOSE = {
    # D-214: a merge would take in the clock's picker, which would stop being a
    # button of its own; an empty node of its own until U34. (The same function
    # merges the feed URL's field, which has no picker, through named().)
    ("developer_ui.py", "option_field", "identifier"): "developer.fake_clock",
    # D-230, D-233: inside a PopupMenuItem, whose own MergeSemantics takes the
    # identifier into the item's node (Flutter's popup_menu.dart); a uiautomator
    # dump shows it. Every overflow item is built there.
    ("menus.py", "menu_item", "identifier"): (
        "session.open_site, session.add_to_calendar, my_schedule.export,"
        " sprints.info, sprints.submit, track.add_all"
    ),
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
    # D-354: a fold's identifier goes on its header, through FoldTile(identifier=).
    "fold": [
        'fold = FoldTile(ft.Text("Earlier days"), [], expanded=False)',
        'return ft.Semantics(identifier="x", content=fold)',
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
