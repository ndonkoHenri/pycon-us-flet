"""Tests for the bottom bar's parts and the re-tap scroll (#75; D-13, D-27, D-144).

How the bar sits on a View and what a tap does are ``AppScaffold`` tests
(``test_scaffold.py``). What the bar looks like, that a re-tap scrolls a real list and
what TalkBack and VoiceOver read are checked on devices (the PR).
"""

from collections.abc import Callable
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.locations import TAB_ROOTS
from pycon_us.prefs import Prefs
from pycon_us.ui import navigation
from pycon_us.ui.navigation import (
    RETAP_SCROLL_MS,
    TABS,
    navigation_bar,
    use_scroll_to_top,
)


async def ignore(e: ft.Event[ft.NavigationBar]) -> None:
    """A tab handler for bars whose taps these tests don't make."""


def test_the_bar_has_the_five_tab_roots_in_order_with_their_labels() -> None:
    assert tuple(tab.root for tab in TABS) == TAB_ROOTS
    assert [tab.label for tab in TABS] == [
        "Now",
        "Schedule",
        "My schedule",
        "Map",
        "More",
    ]


def test_each_tab_has_an_app_nav_identifier_for_ui_tests() -> None:
    assert [tab.identifier for tab in TABS] == [
        "app.nav.now",
        "app.nav.schedule",
        "app.nav.my_schedule",
        "app.nav.map",
        "app.nav.more",
    ]


@pytest.mark.parametrize("root", TAB_ROOTS)
def test_the_bar_is_material_with_labels_always_shown_and_its_root_selected(
    root: str,
) -> None:
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
    bar = navigation_bar("/now", ignore)
    for tab, destination in zip(TABS, bar.destinations, strict=True):
        assert destination.label == tab.label  # the accessible name
        assert tagged(destination.icon) == (tab.identifier, tab.icon)
        assert tagged(destination.selected_icon) == (tab.identifier, tab.selected_icon)
    filled = {tab.selected_icon for tab in TABS} - {ft.Icons.MORE_HORIZ}
    assert not filled & {tab.icon for tab in TABS}  # outlined off, filled on (D-27)


# ------------------------------------------------------------------ use_scroll_to_top


class FakeList:
    """A mounted ``ListView``: records where it was asked to scroll."""

    def __init__(self) -> None:
        self.scrolls: list[dict[str, Any]] = []

    async def scroll_to(self, **kwargs: Any) -> None:
        self.scrolls.append(kwargs)


@pytest.fixture
def prefs(monkeypatch: pytest.MonkeyPatch) -> Prefs:
    prefs = Prefs()
    monkeypatch.setattr(navigation, "use_prefs", lambda: prefs)
    # One render, outside a renderer: use_memo just builds the value.
    monkeypatch.setattr(ft, "use_memo", lambda build, deps: build())
    return prefs


def mounted() -> tuple[FakeList, Callable[[], Any]]:
    list_ref, scroll_to_top = use_scroll_to_top()
    fake = FakeList()
    list_ref.current = cast(ft.ListView, fake)
    return fake, scroll_to_top


async def test_a_retap_scrolls_the_root_s_list_to_the_top(prefs: Prefs) -> None:
    fake, scroll_to_top = mounted()
    await scroll_to_top()
    assert fake.scrolls == [{"offset": 0, "duration": RETAP_SCROLL_MS}]


async def test_under_reduced_motion_the_retap_jumps_to_the_top(prefs: Prefs) -> None:
    prefs.reduce_motion = True
    fake, scroll_to_top = mounted()
    await scroll_to_top()
    assert fake.scrolls == [{"offset": 0, "duration": 0}]  # D-34


async def test_a_retap_before_the_list_is_built_does_nothing(prefs: Prefs) -> None:
    list_ref, scroll_to_top = use_scroll_to_top()
    assert list_ref.current is None
    await scroll_to_top()  # no error, nothing to scroll
