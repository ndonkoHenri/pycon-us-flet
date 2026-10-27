"""Tests for the bottom bar and the rail on ``AppScaffold``'s Views (#75, #387; D-144).

Which View shows the bar or the rail, what separates the bar in high contrast, and what
a tap or a re-tap on either does, built outside a renderer with the fixtures of
``tests/chrome.py`` (#264). The bar's and the rail's own parts and the re-tap scroll
are in ``test_navigation.py``.
"""

from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.locations import TAB_ROOTS
from pycon_us.theme import HC_DARK_TOKENS, HC_LIGHT_TOKENS, Tokens
from pycon_us.ui.navigation import TABS, Tab
from tests import chrome
from tests.chrome import (
    app_bar,
    back_arrow,
    body_of,
    rail_of,
    rail_stack_of,
    safe_area,
    view_at,
)
from tests.fake_page import FakePage, Hooks
from tests.test_navigation import tagged

# The harness's fixtures, under this module's names, where pytest looks them up.
year, svc, page, conference, hooks = (
    chrome.year,
    chrome.svc,
    chrome.page,
    chrome.conference,
    chrome.hooks,
)


# ------------------------------------------------------------------ the bottom bar (#75)


def bar_of(view: ft.View) -> ft.NavigationBar:
    """The ``NavigationBar`` of ``view``."""
    assert isinstance(view.navigation_bar, ft.NavigationBar)
    return view.navigation_bar


async def tap_tab(view: ft.View, root: str) -> None:
    """Tap a destination as Flutter reports it: selected first, then ``on_change``."""
    bar = bar_of(view)
    bar.selected_index = TAB_ROOTS.index(root)
    await cast(Any, bar.on_change)(SimpleNamespace(control=bar))


@pytest.mark.parametrize("root", TAB_ROOTS)
def test_every_tab_root_shows_the_bar_with_its_own_tab_selected(
    hooks: Hooks, page: FakePage, root: str
) -> None:
    """Each tab root's View has the bar with that root's tab selected."""
    bar = bar_of(view_at(hooks, page, root))
    assert TABS[bar.selected_index].root == root


@pytest.mark.parametrize(
    "tokens", [HC_LIGHT_TOKENS, HC_DARK_TOKENS], ids=["light", "dark"]
)
@pytest.mark.parametrize("root", TAB_ROOTS)
def test_in_high_contrast_a_1_dp_line_separates_the_bar_from_the_page(
    hooks: Hooks, page: FakePage, root: str, tokens: Tokens
) -> None:
    """In HC a root's body ends in a 1 dp outline line, right above the bar (THEME-06).

    HC has one surface, so the bar is the page's colour; the line draws its edge.
    """
    hooks.tokens = tokens
    view = view_at(hooks, page, root)
    assert view.navigation_bar is not None
    line = view.controls[-1]
    assert isinstance(line, ft.Divider) and line.visible is True
    assert (line.height, line.thickness, line.color) == (1, 1, ft.Colors.OUTLINE)


def test_outside_high_contrast_nothing_separates_the_bar(
    hooks: Hooks, page: FakePage
) -> None:
    """Outside HC no line sits above a root's bar: its tint is its edge."""
    view = view_at(hooks, page, "/schedule")
    line = view.controls[-1]
    assert isinstance(line, ft.Divider) and line.visible is False


def test_a_pushed_view_in_high_contrast_has_no_bar_line(
    hooks: Hooks, page: FakePage
) -> None:
    """A pushed View has no bar, so no line above one, in HC too.

    Its only line is the one under its app bar (``test_hc_boundaries.py``).
    """
    hooks.tokens = HC_LIGHT_TOKENS
    view = view_at(hooks, page, "/schedule/session/42")
    assert view.navigation_bar is None
    line = view.controls[-1]
    assert isinstance(line, ft.Divider) and line.visible is False


@pytest.mark.parametrize("tab", TABS)
def test_a_root_s_title_carries_its_screen_identifier_for_ui_tests(
    hooks: Hooks, page: FakePage, tab: Tab
) -> None:
    """A root's title is a level-1 heading with its screen id and no label."""
    title = app_bar(view_at(hooks, page, tab.root)).title
    assert isinstance(title, ft.Semantics)
    assert title.identifier == tab.title_identifier
    assert title.heading_level == 1  # the root's heading (D-211)
    assert title.label is None  # the text names the node, once (D-166)
    assert isinstance(title.content, ft.Text)
    assert title.content.value == "Title"


@pytest.mark.parametrize(
    "location",
    [
        "/now/session/42",
        "/schedule/session/42/speaker/17",
        "/more/speakers",
        "/more/tracks/python",
        "/search",
        "/search/session/42",
    ],
)
def test_pushed_views_show_the_back_arrow_and_no_bar(
    hooks: Hooks, page: FakePage, location: str
) -> None:
    """Pushed Views show a back arrow and no bottom bar."""
    view = view_at(hooks, page, location)
    assert view.navigation_bar is None  # it moved with the page (D-144)
    back_arrow(view)


@pytest.mark.parametrize("target", ["/now", "/my-schedule", "/map", "/more"])
async def test_tapping_another_tab_shows_its_root(
    hooks: Hooks, page: FakePage, target: str
) -> None:
    """Tapping another tab navigates to its root without the retap action."""
    retaps: list[str] = []

    async def retap() -> None:
        retaps.append("schedule")

    await tap_tab(view_at(hooks, page, "/schedule", on_retap=retap), target)
    assert page.navigated == [target]
    assert retaps == []


async def test_re_tapping_the_active_tab_runs_the_root_s_retap_and_stays(
    hooks: Hooks, page: FakePage
) -> None:
    """Re-tapping the active tab runs its root's retap action and stays."""
    retaps: list[str] = []

    async def retap() -> None:
        retaps.append("map")

    await tap_tab(view_at(hooks, page, "/map", on_retap=retap), "/map")
    assert retaps == ["map"]
    assert page.navigated == []


async def test_re_tapping_a_root_without_a_retap_action_does_nothing(
    hooks: Hooks, page: FakePage
) -> None:
    """A re-tap on a root without a retap action navigates nowhere and shows nothing."""
    await tap_tab(view_at(hooks, page, "/now"), "/now")
    assert page.navigated == []
    assert page.dialogs == []


async def test_a_retap_that_fails_is_reported_and_the_bar_keeps_working(
    hooks: Hooks, page: FakePage
) -> None:
    """A retap that raises shows one error dialog, and the bar still navigates."""

    async def retap() -> None:
        raise RuntimeError("the list is gone")

    view = view_at(hooks, page, "/more", on_retap=retap)
    await tap_tab(view, "/more")
    assert len(page.dialogs) == 1  # "Something went wrong" (D-163), not a crash
    await tap_tab(view, "/now")
    assert page.navigated == ["/now"]


# ------------------------------------------------------------------ the rail (#387)


async def tap_rail(view: ft.View, root: str) -> None:
    """Tap a rail destination as Flutter reports it: selected first, then ``on_change``."""
    rail = rail_of(view)
    rail.selected_index = TAB_ROOTS.index(root)
    await cast(Any, rail.on_change)(SimpleNamespace(control=rail))


@pytest.mark.parametrize("root", TAB_ROOTS)
def test_from_600_dp_a_root_shows_the_rail_and_no_bar(
    hooks: Hooks, page: FakePage, root: str
) -> None:
    """From 600 dp each root shows the rail, its own tab selected, and no bar."""
    hooks.wide = True
    view = view_at(hooks, page, root)
    assert view.navigation_bar is None
    assert rail_stack_of(view).visible is True
    rail = rail_of(view)
    assert TABS[cast(int, rail.selected_index)].root == root


@pytest.mark.parametrize("root", TAB_ROOTS)
def test_under_600_dp_a_root_keeps_the_bar_and_hides_the_rail(
    hooks: Hooks, page: FakePage, root: str
) -> None:
    """Under 600 dp each root shows the bar, and the rail beside the body is hidden."""
    view = view_at(hooks, page, root)
    bar_of(view)
    assert rail_stack_of(view).visible is False


@pytest.mark.parametrize("wide", [False, True])
def test_the_body_keeps_its_place_whichever_navigation_shows(
    hooks: Hooks, page: FakePage, wide: bool
) -> None:
    """A root's body is the row's second child, beside the rail, in both classes.

    The same place in the tree is what keeps it, and its state, across a rotation
    (D-18, D-277).
    """
    hooks.wide = wide
    view = view_at(hooks, page, "/schedule")
    row = safe_area(view).content
    assert isinstance(row, ft.Row)
    assert isinstance(row.controls[0], ft.Stack)  # the rail under its fade (D-309)
    assert row.controls[1] is body_of(view)
    assert row.spacing == 0
    assert row.vertical_alignment == ft.CrossAxisAlignment.STRETCH


@pytest.mark.parametrize(
    "location", ["/now/session/42", "/more/speakers", "/search/session/42"]
)
def test_pushed_views_show_neither_the_bar_nor_the_rail_from_600_dp(
    hooks: Hooks, page: FakePage, location: str
) -> None:
    """From 600 dp pushed Views still show the back arrow, and no bar or rail."""
    hooks.wide = True
    view = view_at(hooks, page, location)
    assert view.navigation_bar is None
    back_arrow(view)
    assert not isinstance(safe_area(view).content, ft.Row)  # the body alone, as before


@pytest.mark.parametrize("wide", [False, True])
def test_ui_tests_find_each_tab_by_identifier_or_name_in_both_layouts(
    hooks: Hooks, page: FakePage, wide: bool
) -> None:
    """Under 600 dp each tab carries ``app.nav.<tab>``; from 600 dp, its name (#163)."""
    hooks.wide = wide
    view = view_at(hooks, page, "/now")
    if wide:
        assert view.navigation_bar is None
        names = [d.label for d in rail_of(view).destinations]
        assert names == [tab.label for tab in TABS]
    else:
        ids = [tagged(d.icon)[0] for d in bar_of(view).destinations]
        assert ids == [tab.identifier for tab in TABS]


@pytest.mark.parametrize("target", ["/now", "/schedule", "/my-schedule", "/more"])
async def test_tapping_another_rail_tab_shows_its_root(
    hooks: Hooks, page: FakePage, target: str
) -> None:
    """Tapping another tab on the rail navigates to its root without the retap."""
    hooks.wide = True
    retaps: list[str] = []

    async def retap() -> None:
        retaps.append("map")

    await tap_rail(view_at(hooks, page, "/map", on_retap=retap), target)
    assert page.navigated == [target]
    assert retaps == []


async def test_re_tapping_the_active_rail_tab_runs_the_root_s_retap_and_stays(
    hooks: Hooks, page: FakePage
) -> None:
    """Re-tapping the active tab on the rail scrolls its root up and stays (D-144)."""
    hooks.wide = True
    retaps: list[str] = []

    async def retap() -> None:
        retaps.append("schedule")

    await tap_rail(view_at(hooks, page, "/schedule", on_retap=retap), "/schedule")
    assert retaps == ["schedule"]
    assert page.navigated == []


async def test_back_from_a_root_other_than_now_still_goes_to_now_from_600_dp(
    hooks: Hooks, page: FakePage
) -> None:
    """With the rail, Back on a root other than Now still goes to Now (D-17)."""
    hooks.wide = True
    view = view_at(hooks, page, "/more")
    assert view.can_pop is False
    confirmed: list[bool] = []

    async def confirm_pop(ok: bool) -> None:
        confirmed.append(ok)

    control = SimpleNamespace(confirm_pop=confirm_pop)
    await cast(Any, view.on_confirm_pop)(SimpleNamespace(control=control))
    assert page.navigated == ["/now"]
    assert confirmed == [False]
