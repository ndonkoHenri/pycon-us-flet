"""Tests for the bottom bar, the rail and the re-tap scroll (#75, #387; D-144, D-277).

The bar's and the rail's own parts and the re-tap scroll, built outside a renderer
with the fixtures of ``tests/chrome.py`` (#264); how they sit on ``AppScaffold``'s
Views and what a tap does are in ``test_navigation_views.py``. What they look like, that a re-tap scrolls a real list and what TalkBack and
VoiceOver read are checked on devices (the PR).
"""

import inspect
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.locations import TAB_ROOTS
from pycon_us.prefs import Prefs
from pycon_us.ui import navigation
from pycon_us.ui.navigation import (
    RAIL_FADE,
    RAIL_FIT_DP,
    RAIL_WIDTH,
    RETAP_SCROLL_MS,
    TABS,
    Rail,
    navigation_bar,
    navigation_rail,
    use_scroll_to_top,
)
from tests import chrome
from tests.chrome import inner_rail
from tests.fakes import Hooks

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
    rail = inner_rail(navigation_rail("/now", ignore, visible=True))
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
    rail = inner_rail(navigation_rail(root, ignore, visible=True))
    assert rail.label_type == ft.NavigationRailLabelType.ALL
    assert rail.group_alignment == -1  # the destinations at the top (ux.md §8)
    assert rail.min_width == RAIL_WIDTH == 80
    assert rail.extended is False
    assert rail.scrollable is True  # phone landscape at 200 % text (D-277)
    assert rail.selected_index == TAB_ROOTS.index(root)


@pytest.mark.parametrize("visible", [True, False])
def test_the_rail_shows_only_when_asked(visible: bool) -> None:
    """``visible`` decides whether the rail shows; hidden, it keeps its destinations."""
    stack = navigation_rail("/map", ignore, visible=visible)
    assert stack.visible is visible  # the rail and its fade show or hide together
    assert len(inner_rail(stack).destinations) == len(TABS)


def test_a_short_rail_fades_its_bottom_edge_to_show_that_it_scrolls() -> None:
    """A short rail's bottom edge fades into its colour, and ignores taps (D-309).

    The empty space under the last destination is as tall, so at the end of a scroll
    More sits clear of the fade.
    """
    stack = navigation_rail("/now", ignore, visible=True, short=True)
    rail, fade = stack.controls
    assert fade.visible is True
    assert isinstance(fade, ft.Container)
    assert (fade.left, fade.right, fade.bottom, fade.height) == (0, 0, 0, RAIL_FADE)
    assert fade.top is None  # pinned to the bottom edge only
    assert isinstance(fade.gradient, ft.LinearGradient)
    assert fade.gradient.colors == [
        ft.Colors.with_opacity(0, ft.Colors.SURFACE),
        ft.Colors.SURFACE,  # the rail's own Material colour, in every theme
    ]
    assert fade.ignore_interactions is True  # a tap reaches the destination under it
    assert fade.content is None  # nothing for a screen reader
    assert isinstance(rail, ft.NavigationRail)
    assert isinstance(rail.trailing, ft.Container)
    assert rail.trailing.height == RAIL_FADE
    assert rail.pin_trailing_to_bottom is False  # it scrolls with the destinations


def test_a_rail_that_fits_has_no_fade_and_no_space_under_more() -> None:
    """Where the destinations fit, the last label is not faded and nothing scrolls."""
    stack = navigation_rail("/now", ignore, visible=True)
    rail, fade = stack.controls
    assert fade.visible is False
    assert isinstance(rail, ft.NavigationRail)
    assert rail.trailing is None


@pytest.mark.parametrize(
    ("height", "short"),
    [(303, True), (RAIL_FIT_DP - 0.5, True), (RAIL_FIT_DP, False), (325, False)],
)
def test_the_rail_fades_only_when_shorter_than_its_destinations(
    hooks: Hooks, monkeypatch: pytest.MonkeyPatch, height: float, short: bool
) -> None:
    """``Rail`` measures itself and fades under ``RAIL_FIT_DP``, 320 dp (D-309).

    About 303 dp on an Android phone in landscape; an iPhone 17's (about 325 dp) or a
    tablet's shows all five.
    """
    assert RAIL_FIT_DP == 320
    monkeypatch.setattr(ft, "use_state", hooks.use_state)
    render = inspect.unwrap(Rail)
    stack = render("/now", ignore, True)
    assert stack.controls[1].visible is False  # before the first measurement
    stack.on_size_change(SimpleNamespace(width=80, height=height))
    assert hooks.state is short
    stack = render("/now", ignore, True)
    assert stack.controls[1].visible is short
    assert stack.visible is True


async def test_a_tap_on_the_bar_or_the_rail_hands_its_index_on() -> None:
    """The bar and the rail each hand the tapped destination's index to ``on_select``."""
    picked: list[int] = []

    async def select(index: int) -> None:
        picked.append(index)

    bar = navigation_bar("/now", select)
    bar.selected_index = 3
    await cast(Any, bar.on_change)(SimpleNamespace(control=bar))
    rail = inner_rail(navigation_rail("/now", select, visible=True))
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
