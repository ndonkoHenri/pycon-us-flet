"""Tests for the bottom bar, the rail and the re-tap scroll (#75, #387; D-144, D-277).

The bar's and the rail's own parts, then how they sit on ``AppScaffold``'s Views and
what a tap does, built outside a renderer with the fixtures of ``tests/chrome.py``
(#264). What they look like, that a re-tap scrolls a real list and what TalkBack and
VoiceOver read are checked on devices (the PR).
"""

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.locations import TAB_ROOTS
from pycon_us.prefs import Prefs
from pycon_us.theme import HC_DARK_TOKENS, HC_LIGHT_TOKENS, Tokens
from pycon_us.ui import navigation
from pycon_us.ui.navigation import (
    RAIL_WIDTH,
    RETAP_SCROLL_MS,
    TABS,
    Tab,
    navigation_bar,
    navigation_rail,
    use_scroll_to_top,
)
from tests import chrome
from tests.chrome import app_bar, back_arrow, body_of, rail_of, safe_area, view_at
from tests.fakes import FakePage, Hooks

# The harness's fixtures, under this module's names, where pytest looks them up.
year, svc, page, conference, hooks = (
    chrome.year,
    chrome.svc,
    chrome.page,
    chrome.conference,
    chrome.hooks,
)


async def ignore(index: int) -> None:
    """A tab handler for bars and rails whose taps these tests don't make."""


def test_the_bar_has_the_five_tab_roots_in_order_with_their_labels() -> None:
    """The bar's tabs are the five tab roots, in order, with their labels."""
    assert tuple(tab.root for tab in TABS) == TAB_ROOTS
    assert [tab.label for tab in TABS] == [
        "Now",
        "Schedule",
        "My schedule",
        "Map",
        "More",
    ]


def test_each_tab_has_an_app_nav_identifier_for_ui_tests() -> None:
    """Each tab carries an ``app.nav.<tab>`` identifier."""
    assert [tab.identifier for tab in TABS] == [
        "app.nav.now",
        "app.nav.schedule",
        "app.nav.my_schedule",
        "app.nav.map",
        "app.nav.more",
    ]


def test_each_tab_root_s_title_has_a_screen_identifier_for_ui_tests() -> None:
    """Each tab names its root title's identifier, ``<screen>.title``."""
    assert [tab.title_identifier for tab in TABS] == [
        "now.title",
        "schedule.title",
        "my_schedule.title",
        "map.title",
        "more.title",
    ]


@pytest.mark.parametrize("root", TAB_ROOTS)
def test_the_bar_is_material_with_labels_always_shown_and_its_root_selected(
    root: str,
) -> None:
    """On each root the bar is Material, shows every label and selects that root."""
    bar = navigation_bar(root, ignore)
    assert bar.label_behavior == ft.NavigationBarLabelBehavior.ALWAYS_SHOW
    assert bar.adaptive is not True  # never Cupertino (D-10)
    assert bar.selected_index == TAB_ROOTS.index(root)


def tagged(icon: ft.IconDataOrControl | None) -> tuple[str | None, ft.IconData]:
    """The identifier and the icon of a destination's tagged icon."""
    assert isinstance(icon, ft.Semantics)
    assert isinstance(icon.content, ft.Icon)
    assert icon.label is None  # no name of its own: the destination's label is it
    return icon.identifier, cast(ft.IconData, icon.content.icon)


def test_each_destination_is_labelled_and_outlined_until_selected() -> None:
    """Each destination has its tab's label and id, outlined until selected."""
    bar = navigation_bar("/now", ignore)
    for tab, destination in zip(TABS, bar.destinations, strict=True):
        assert destination.label == tab.label  # the accessible name
        assert tagged(destination.icon) == (tab.identifier, tab.icon)
        assert tagged(destination.selected_icon) == (tab.identifier, tab.selected_icon)
    filled = {tab.selected_icon for tab in TABS} - {ft.Icons.MORE_HORIZ}
    assert not filled & {tab.icon for tab in TABS}  # outlined off, filled on (D-27)


def test_the_rail_has_the_bar_s_labels_and_icons_and_no_identifier_node() -> None:
    """The rail's destinations are the bar's, with plain icons (#163, F95).

    An identifier ``Semantics`` there would be a second, empty TalkBack stop in each
    destination: flows find a rail destination by its name until Flet can tag it.
    """
    rail = navigation_rail("/now", ignore, visible=True)
    for tab, destination in zip(TABS, rail.destinations, strict=True):
        assert destination.label == tab.label  # the accessible name
        assert (destination.icon, destination.selected_icon) == (
            tab.icon,
            tab.selected_icon,
        )


@pytest.mark.parametrize("root", TAB_ROOTS)
def test_the_rail_shows_every_label_at_the_top_with_its_root_selected(
    root: str,
) -> None:
    """On each root the rail shows every label at the top, its root selected.

    It is M3's width and scrolls, so each destination stays reachable at large text.
    """
    rail = navigation_rail(root, ignore, visible=True)
    assert rail.label_type == ft.NavigationRailLabelType.ALL
    assert rail.group_alignment == -1  # the destinations at the top (ux.md §8)
    assert rail.min_width == RAIL_WIDTH == 80
    assert rail.extended is False
    assert rail.scrollable is True  # phone landscape at 200 % text (D-277)
    assert rail.selected_index == TAB_ROOTS.index(root)


@pytest.mark.parametrize("visible", [True, False])
def test_the_rail_shows_only_when_asked(visible: bool) -> None:
    """``visible`` decides whether the rail shows; hidden, it keeps its destinations."""
    rail = navigation_rail("/map", ignore, visible=visible)
    assert rail.visible is visible
    assert len(rail.destinations) == len(TABS)


async def test_a_tap_on_the_bar_or_the_rail_hands_its_index_on() -> None:
    """The bar and the rail each hand the tapped destination's index to ``on_select``."""
    picked: list[int] = []

    async def select(index: int) -> None:
        picked.append(index)

    bar = navigation_bar("/now", select)
    bar.selected_index = 3
    await cast(Any, bar.on_change)(SimpleNamespace(control=bar))
    rail = navigation_rail("/now", select, visible=True)
    rail.selected_index = 1
    await cast(Any, rail.on_change)(SimpleNamespace(control=rail))
    assert picked == [3, 1]


# ------------------------------------------------------------------ use_scroll_to_top


class FakeList:
    """A mounted ``ListView``: records where it was asked to scroll."""

    def __init__(self) -> None:
        """Start with no scroll asked for."""
        self.scrolls: list[dict[str, Any]] = []

    async def scroll_to(self, **kwargs: Any) -> None:
        """Record the arguments of a scroll request."""
        self.scrolls.append(kwargs)


@pytest.fixture
def prefs(monkeypatch: pytest.MonkeyPatch) -> Prefs:
    """Default ``Prefs`` for ``navigation``, with ``use_memo`` building at once."""
    prefs = Prefs()
    monkeypatch.setattr(navigation, "use_prefs", lambda: prefs)
    # One render, outside a renderer: use_memo just builds the value.
    monkeypatch.setattr(ft, "use_memo", lambda build, deps: build())
    return prefs


def mounted() -> tuple[FakeList, Callable[[], Any]]:
    """Call ``use_scroll_to_top()`` and mount a ``FakeList`` on its ref."""
    list_ref, scroll_to_top = use_scroll_to_top()
    fake = FakeList()
    list_ref.current = cast(ft.ListView, fake)
    return fake, scroll_to_top


async def test_a_retap_scrolls_the_root_s_list_to_the_top(prefs: Prefs) -> None:
    """A re-tap scrolls the mounted list to offset 0 over ``RETAP_SCROLL_MS``."""
    fake, scroll_to_top = mounted()
    await scroll_to_top()
    assert fake.scrolls == [{"offset": 0, "duration": RETAP_SCROLL_MS}]


async def test_under_reduced_motion_the_retap_jumps_to_the_top(prefs: Prefs) -> None:
    """Under reduced motion the re-tap scrolls to the top with no duration."""
    prefs.reduce_motion = True
    fake, scroll_to_top = mounted()
    await scroll_to_top()
    assert fake.scrolls == [{"offset": 0, "duration": 0}]  # D-34


async def test_a_retap_before_the_list_is_built_does_nothing(prefs: Prefs) -> None:
    """A re-tap before the list is mounted returns without an error."""
    list_ref, scroll_to_top = use_scroll_to_top()
    assert list_ref.current is None
    await scroll_to_top()  # no error, nothing to scroll


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
    rail = rail_of(view)
    assert rail.visible is True
    assert TABS[cast(int, rail.selected_index)].root == root


@pytest.mark.parametrize("root", TAB_ROOTS)
def test_under_600_dp_a_root_keeps_the_bar_and_hides_the_rail(
    hooks: Hooks, page: FakePage, root: str
) -> None:
    """Under 600 dp each root shows the bar, and the rail beside the body is hidden."""
    view = view_at(hooks, page, root)
    bar_of(view)
    assert rail_of(view).visible is False


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
    assert isinstance(row.controls[0], ft.NavigationRail)
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
