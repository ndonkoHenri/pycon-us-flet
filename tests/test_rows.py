"""Tests for the shared rows: ``LinkTile`` (#77; ux.md §3.9).

The builder runs outside a renderer, with a fake page bound as Flet binds a session's
page. How tall a row is on screen and what TalkBack reads are checked on devices (the
PR): Flutter's ``ListTile`` sizes it and merges it into one node.
"""

from collections.abc import Callable, Iterator
from typing import cast

import flet as ft
import pytest

from pycon_us.ui.rows import LinkTile
from tests.fakes import FakePage, bound


@pytest.fixture
def page() -> Iterator[FakePage]:
    fake = FakePage()
    with bound(fake):
        yield fake


def tile_of(row: ft.Control) -> ft.ListTile:
    """The ``ListTile`` inside a row's semantics wrappers."""
    assert isinstance(row, ft.MergeSemantics)  # one node for screen readers
    inner = row.content
    if isinstance(inner, ft.Semantics):
        inner = inner.content
    assert isinstance(inner, ft.ListTile)
    return inner


def tap(tile: ft.ListTile) -> None:
    assert tile.on_click is not None
    cast(Callable[[], None], tile.on_click)()


def test_a_link_tile_is_one_merged_list_tile_with_a_trailing_chevron(
    page: FakePage,
) -> None:
    tile = tile_of(LinkTile("Speakers", "/more/speakers", icon=ft.Icons.PEOPLE_OUTLINE))
    assert tile.title == "Speakers"
    assert isinstance(tile.trailing, ft.Icon)
    assert tile.trailing.icon == ft.Icons.CHEVRON_RIGHT  # an in-app page (§3.7)
    assert isinstance(tile.leading, ft.Icon)
    assert tile.leading.icon == ft.Icons.PEOPLE_OUTLINE


def test_a_link_tile_without_an_icon_or_subtitle_has_neither(page: FakePage) -> None:
    tile = tile_of(LinkTile("Ana Lima", "/more/speakers/speaker/17"))
    assert tile.leading is None
    assert tile.subtitle is None


def test_a_link_tile_shows_its_subtitle(page: FakePage) -> None:
    tile = tile_of(LinkTile("Ana Lima", "/x", subtitle="Typing deep dive"))
    assert tile.subtitle == "Typing deep dive"


def test_a_tap_on_a_link_tile_pushes_its_location(page: FakePage) -> None:
    tap(tile_of(LinkTile("Keynotes", "/more/keynotes")))
    assert page.navigated == ["/more/keynotes"]


def test_a_link_tile_s_identifier_tags_the_merged_node(page: FakePage) -> None:
    row = LinkTile("Sprints", "/more/sprints", identifier="more.sprints")
    assert isinstance(row, ft.MergeSemantics)
    tagged = row.content
    assert isinstance(tagged, ft.Semantics)
    assert tagged.identifier == "more.sprints"
    assert tagged.label is None  # the row is read as its title (D-166's merge)


def test_a_link_tile_without_an_identifier_adds_no_semantics_node(
    page: FakePage,
) -> None:
    row = LinkTile("Sprints", "/more/sprints")
    assert isinstance(row, ft.MergeSemantics)
    assert isinstance(row.content, ft.ListTile)


def test_a_tap_that_fails_is_reported_not_raised(page: FakePage) -> None:
    def broken(location: str) -> None:
        raise RuntimeError("no route")

    tile = tile_of(LinkTile("Keynotes", "/more/keynotes"))
    page.navigate = broken  # type: ignore[method-assign]
    tap(tile)
    assert len(page.dialogs) == 1  # "Something went wrong" (D-163), not a crash
