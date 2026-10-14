"""Tests that every button's spoken tooltip is in the button's own node (F55, D-234).

Flet wraps a control in its ``tooltip`` from outside, so a button's tooltip is a node of
its own over the button, which is left unnamed ("Button" in TalkBack), unless a merge
makes them one: ``named()``, ``merged()``, ``links.external()`` or a ``MergeSemantics``.
An ``ast`` scan of every app module finds a ``*Button`` call whose tooltip is said and
that reaches no merge; the helpers' own behaviour is checked first.
"""

import ast
from pathlib import Path
from typing import cast

import flet as ft
import pytest

import pycon_us
from pycon_us.screens.schedule_days import JUMP_TOOLTIP, now_button
from pycon_us.ui.semantics import merged
from tests.test_semantics import SOURCES, called, own_nodes, scope_of

MERGES = {"MergeSemantics", "named", "merged", "external"}
"""The calls that merge their control into one node with its tooltip."""


def test_merged_puts_the_button_alone_in_one_merged_node() -> None:
    """F55: the merge goes straight around the button, so the tooltip names it."""
    button = ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Back")
    node = merged(button)
    assert isinstance(node, ft.MergeSemantics)
    assert node.content is button


def test_the_now_button_says_what_it_does_from_inside() -> None:
    """D-234: a View takes only a FAB: said from its label, its tooltip left unsaid."""

    async def jump() -> None:
        """Nothing: the button is only built."""

    fab = now_button(on_today=True, on_click=jump)
    tooltip = fab.tooltip
    assert isinstance(tooltip, ft.Tooltip)
    assert (tooltip.message, tooltip.exclude_from_semantics) == (JUMP_TOOLTIP, True)
    node = cast(ft.Semantics, fab.content)
    assert node.identifier == "schedule.jump_now"
    assert cast(ft.Text, node.content).semantics_label == f"Now\n{JUMP_TOOLTIP}"


def says_its_tooltip(call: ast.Call) -> bool:
    """Whether ``call`` passes a tooltip that screen readers get: not ``None``, and not
    a ``Tooltip(..., exclude_from_semantics=True)``."""
    tooltip = next((k.value for k in call.keywords if k.arg == "tooltip"), None)
    if tooltip is None or (isinstance(tooltip, ast.Constant) and tooltip.value is None):
        return False
    if isinstance(tooltip, ast.Call) and called(tooltip) == "Tooltip":
        return not any(
            k.arg == "exclude_from_semantics"
            and isinstance(k.value, ast.Constant)
            and k.value.value is True
            for k in tooltip.keywords
        )
    return True


class Modules:
    """The parsed modules a scan reads, and each node's parent in them."""

    def __init__(self, sources: dict[str, str]) -> None:
        """Parse ``sources``, module names to their source."""
        self.trees = {name: ast.parse(source) for name, source in sources.items()}
        self.parents = {
            child: node
            for tree in self.trees.values()
            for node in ast.walk(tree)
            for child in ast.iter_child_nodes(node)
        }

    def calls_of(self, function: str) -> list[ast.Call]:
        """Return every call of ``function`` by name, in every module."""
        return [
            node
            for tree in self.trees.values()
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and called(node) == function
        ]

    def reaches_merge(
        self, node: ast.AST, seen: frozenset[ast.AST] = frozenset()
    ) -> bool:
        """Whether the control that ``node`` builds ends up inside a merge.

        Straight, or through a ``Semantics`` around it, a conditional, a name its
        function assigns it to, or a function that returns it, whose every call must
        then reach one.
        """
        if node in seen:
            return False
        seen |= {node}
        above = self.parents.get(node)
        if isinstance(above, ast.keyword):
            above = self.parents.get(above) if above.arg == "content" else None
        if isinstance(above, ast.Call):
            if called(above) in MERGES:
                return True
            return called(above) == "Semantics" and self.reaches_merge(above, seen)
        if isinstance(above, ast.IfExp) and node is not above.test:
            return self.reaches_merge(above, seen)
        if isinstance(above, ast.Assign | ast.AnnAssign):
            targets = above.targets if isinstance(above, ast.Assign) else [above.target]
            names = {t.id for t in targets if isinstance(t, ast.Name)}
            uses = [
                use
                for use in own_nodes(scope_of(above, self.parents))
                if isinstance(use, ast.Name)
                and use.id in names
                and isinstance(use.ctx, ast.Load)
            ]
            return any(self.reaches_merge(use, seen) for use in uses)
        if isinstance(above, ast.Return):
            function = scope_of(above, self.parents)
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                return False
            calls = self.calls_of(function.name)
            return bool(calls) and all(self.reaches_merge(c, seen) for c in calls)
        return False


def unmerged_tooltips(sources: dict[str, str]) -> list[str]:
    """Return ``module:line`` for each button whose spoken tooltip reaches no merge."""
    modules = Modules(sources)
    return [
        f"{name}:{node.lineno}"
        for name, tree in modules.trees.items()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and called(node).endswith("Button")
        and says_its_tooltip(node)
        and not modules.reaches_merge(node)
    ]


def screen(*lines: str) -> dict[str, str]:
    """Return one module, ``m``: ``def screen(control):`` with ``lines`` as its body."""
    return {"m": "def screen(control):\n" + "".join(f"    {x}\n" for x in lines)}


BACK = 'ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Back")'
"""The shape the scan is for: an icon button named by its tooltip."""

SPLIT = {
    "bare": [f"return {BACK}"],
    "in-a-list": [f"return ft.Row([{BACK}])"],
    "built-first": [f"button = {BACK}", "return ft.Row([button])"],
    "identifier-only": [f'return ft.Semantics(identifier="x", content={BACK})'],
    "a-fab": ['return ft.FloatingActionButton(content="Now", tooltip="Jump")'],
    "a-text-button": ['return ft.TextButton("Reset", tooltip="Reset the filter")'],
    "a-said-tooltip-object": [
        'return ft.IconButton(ft.Icons.ADD, tooltip=ft.Tooltip("Add"))'
    ],
}
"""Function bodies whose button is said as an unnamed button under its tooltip."""

KEPT = {
    "merged": [f"return merged({BACK})"],
    "named": [f'return named("x", {BACK})'],
    "merge-semantics": [f"return ft.MergeSemantics(content={BACK})"],
    "merged-positionally": [f"return ft.MergeSemantics({BACK})"],
    "external": [f'return external("x", ft.Semantics(label="Go", content={BACK}))'],
    "built-first": [f"button = {BACK}", 'return named("x", button)'],
    "either-way": [
        f"button = {BACK}",
        'return named("x", button) if control else merged(button)',
    ],
    "unsaid": [
        (
            "return ft.IconButton(ft.Icons.ADD, "
            'tooltip=ft.Tooltip("Add", exclude_from_semantics=True))'
        )
    ],
    "no-tooltip": ["return ft.IconButton(ft.Icons.ADD)"],
    "a-label": ['return ft.Semantics(label="Back", content=ft.Text("Back"))'],
}
"""Function bodies whose button is one node with its name, or has no said tooltip."""


@pytest.mark.parametrize("lines", SPLIT.values(), ids=SPLIT.keys())
def test_the_scan_flags_a_tooltip_outside_its_button(lines: list[str]) -> None:
    """F55: a said tooltip that reaches no merge leaves its button unnamed."""
    assert unmerged_tooltips(screen(*lines)) != []


@pytest.mark.parametrize("lines", KEPT.values(), ids=KEPT.keys())
def test_the_scan_keeps_a_merged_or_unsaid_tooltip(lines: list[str]) -> None:
    """D-234: merged, the tooltip names the button; unsaid, nothing is split."""
    assert unmerged_tooltips(screen(*lines)) == []


def test_the_scan_follows_a_returned_button_to_its_callers() -> None:
    """A builder that returns the button (the fake clock's picker) is checked where
    it is called: each call must merge it, or the button is unnamed there."""
    builder = f"def picker():\n    return {BACK}\n"
    both = builder + 'def a():\n    return named("x", picker())\n'
    assert unmerged_tooltips({"m": both}) == []
    one_bare = both + "def b():\n    return ft.Row([picker()])\n"
    assert unmerged_tooltips({"m": one_bare}) == ["m:2"]
    assert unmerged_tooltips({"m": builder}) == ["m:2"]  # called nowhere: no merge


def app_sources() -> dict[str, str]:
    """Return every app module's source, keyed by its path in the package."""
    root = Path(pycon_us.__file__).parent
    return {str(p.relative_to(root)): p.read_text(encoding="utf-8") for p in SOURCES}


def test_the_scan_finds_the_app_s_buttons_with_tooltips() -> None:
    """A scan that matched nothing would pass whatever the code says: the app has
    a dozen buttons with a said tooltip (Back, Search, Share, Clear, the menus)."""
    modules = Modules(app_sources())
    said = [
        node
        for tree in modules.trees.values()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and called(node).endswith("Button")
        and says_its_tooltip(node)
    ]
    assert len(said) >= 8


def test_every_said_tooltip_is_merged_into_its_button() -> None:
    """F55, D-234, ux.md §9: every button with a said tooltip is one named node."""
    assert unmerged_tooltips(app_sources()) == []
