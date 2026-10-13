"""Tests for the More tab: a flat, sectioned list of pages (#77; D-15, ux.md §2.2).

``More`` runs outside a renderer: its hooks and ``AppScaffold`` are replaced, and a fake
page is bound as Flet binds a session's page. The scaffold itself (the bar, the re-tap,
Back) is tested in ``test_scaffold.py``; how the list looks and reads is checked on
devices (the PR).
"""

import inspect
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import prefs as prefs_module
from pycon_us.config import load_year
from pycon_us.locations import PAGES, parent_of
from pycon_us.prefs import DEV_UNLOCKED, Prefs
from pycon_us.screens import more
from pycon_us.screens.more import MORE_PAGES, More, MoreEntry
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.state import ViewMemory
from tests.fakes import (
    FakePage,
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    bound,
)


@pytest.fixture
def page() -> Iterator[FakePage]:
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    return Services(
        year=load_year(2026),
        storage=storage,
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )


@pytest.fixture
def prefs() -> Prefs:
    return Prefs()


async def retap() -> None:
    """The root's re-tap action, as ``use_scroll_to_top()`` would return it."""


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch, svc: Services, prefs: Prefs, page: FakePage
) -> Callable[[], dict[str, Any]]:
    """Render ``More`` once and return what it passed to ``AppScaffold``.

    The services come first: a service built while a page is bound registers with it.
    """
    monkeypatch.setattr(more, "use_scroll_to_top", lambda: (ft.Ref(), retap))
    monkeypatch.setattr(more, "use_services", lambda: svc)
    monkeypatch.setattr(more, "use_prefs", lambda: prefs)
    monkeypatch.setattr(more, "AppScaffold", lambda **kwargs: kwargs)
    # The companion app's list, wherever pytest runs (FLET_PLATFORM may be set, F14)
    monkeypatch.setattr(prefs_module, "DEVELOPER_ALWAYS", True)

    def render() -> dict[str, Any]:
        return cast(dict[str, Any], inspect.unwrap(More)())

    return render


def rows_of(scaffold: dict[str, Any]) -> list[ft.Control]:
    body = scaffold["body"]
    assert isinstance(body, ft.ListView)
    return list(body.controls)


def header_text(control: ft.Control) -> str | None:
    """A ``SectionHeader``'s text, or None for any other row."""
    if isinstance(control, ft.Semantics) and control.header:
        assert isinstance(control.content, ft.Container)
        assert isinstance(control.content.content, ft.Text)
        return control.content.content.value
    return None


def tile_of(row: ft.Control) -> ft.ListTile | None:
    """A ``LinkTile``'s ``ListTile``, or None for any other row."""
    if isinstance(row, ft.MergeSemantics) and isinstance(row.content, ft.Semantics):
        tile = row.content.content
        return tile if isinstance(tile, ft.ListTile) else None
    return None


def outline(rows: list[ft.Control]) -> list[str]:
    """The list as headers (``# ``), page titles and the other rows' kinds."""
    result = []
    for row in rows:
        if (text := header_text(row)) is not None:
            result.append(f"# {text}")
        elif (tile := tile_of(row)) is not None:
            result.append(str(tile.title))
        elif isinstance(row, ft.Semantics):
            result.append(str(row.identifier))
        else:
            result.append(type(row).__name__)
    return result


def test_the_list_has_programme_then_you_under_section_headers(
    render: Callable[[], dict[str, Any]],
) -> None:
    assert outline(rows_of(render())) == [
        "# Programme",
        "Speakers",
        "Tracks & session types",
        "Keynotes",
        "Open spaces",
        "Lightning talks",
        "Sprints",
        "# You",
        "more.appearance",
        "About this app",
        "Developer options",
    ]  # About this app says "Not an official PSF app." now (D-36)


def test_developer_is_hidden_in_packaged_builds_until_unlocked(
    monkeypatch: pytest.MonkeyPatch,
    render: Callable[[], dict[str, Any]],
    prefs: Prefs,
) -> None:
    monkeypatch.setattr(prefs_module, "DEVELOPER_ALWAYS", False)
    titles = outline(rows_of(render()))
    assert "About this app" in titles
    assert "Developer options" not in titles  # D-73
    prefs.dev = {DEV_UNLOCKED: True}  # 7 taps on the version (D-187)
    assert outline(rows_of(render()))[-1] == "Developer options"


def test_every_row_opens_a_page_of_the_route_table_so_none_is_dead(
    render: Callable[[], dict[str, Any]], page: FakePage
) -> None:
    for row in rows_of(render()):
        if (tile := tile_of(row)) is not None:
            cast(Callable[[], None], tile.on_click)()
    assert page.navigated == [entry.location for entry in MORE_PAGES]
    assert set(page.navigated) <= PAGES


@pytest.mark.parametrize("entry", MORE_PAGES, ids=lambda entry: entry.location)
def test_a_tap_pushes_the_row_s_page_and_back_returns_to_more(
    render: Callable[[], dict[str, Any]], page: FakePage, entry: MoreEntry
) -> None:
    tiles = {str(t.title): t for row in rows_of(render()) if (t := tile_of(row))}
    tile = tiles[entry.title]
    assert tile.on_click is not None
    cast(Callable[[], None], tile.on_click)()
    assert page.navigated == [entry.location]
    assert parent_of(entry.location) == "/more"  # one pushed View (D-17)


def test_each_row_has_its_icon_and_a_more_identifier(
    render: Callable[[], dict[str, Any]],
) -> None:
    rows = [row for row in rows_of(render()) if tile_of(row) is not None]
    by_id = {}
    for row in rows:
        assert isinstance(row, ft.MergeSemantics)
        assert isinstance(row.content, ft.Semantics)
        tile = tile_of(row)
        assert tile is not None and isinstance(tile.leading, ft.Icon)
        by_id[row.content.identifier] = tile.leading.icon
    assert by_id == {entry.identifier: entry.icon for entry in MORE_PAGES}


def test_identifiers_name_the_page_in_snake_case() -> None:
    assert [entry.identifier for entry in MORE_PAGES] == [
        "more.speakers",
        "more.tracks",
        "more.keynotes",
        "more.open_spaces",
        "more.lightning_talks",
        "more.sprints",
        "more.app",
        "more.developer",
    ]


def test_more_keeps_the_search_and_the_re_tap_scroll_to_top(
    render: Callable[[], dict[str, Any]],
) -> None:
    scaffold = render()
    assert scaffold["title"] == "More"
    assert scaffold["on_retap"] is retap  # D-144, D-166
    [search] = scaffold["actions"]
    assert isinstance(search, ft.IconButton)
    assert search.tooltip == "Search"


def appearance_column(scaffold: dict[str, Any]) -> ft.Column:
    """The Appearance group's column: its label, then its ``RadioGroup``."""
    [group] = [
        row
        for row in rows_of(scaffold)
        if isinstance(row, ft.Semantics) and row.identifier == "more.appearance"
    ]
    column = group.content
    assert isinstance(column, ft.Column)
    return column


def appearance_of(scaffold: dict[str, Any]) -> ft.RadioGroup:
    choice = appearance_column(scaffold).controls[-1]
    assert isinstance(choice, ft.RadioGroup)
    return choice


def options_of(choice: ft.RadioGroup) -> list[tuple[str | None, str, ft.ListTile]]:
    """Each option row as (identifier, its radio's value, its tile)."""
    column = choice.content
    assert isinstance(column, ft.Column)
    options = []
    for row in column.controls:
        assert isinstance(row, ft.MergeSemantics)  # one node per option
        assert isinstance(row.content, ft.Semantics)
        tile = row.content.content
        assert isinstance(tile, ft.ListTile) and isinstance(tile.leading, ft.Radio)
        options.append((row.content.identifier, str(tile.leading.value), tile))
    return options


async def choose(choice: ft.RadioGroup, value: str) -> None:
    """Pick an option as Flutter reports it: the value first, then ``on_change``."""
    choice.value = value
    await cast(Any, choice.on_change)(SimpleNamespace(control=choice))


def test_appearance_shows_the_stored_choice(
    render: Callable[[], dict[str, Any]], prefs: Prefs
) -> None:
    prefs.theme = "dark"
    choice = appearance_of(render())
    assert choice.value == "dark"  # controlled (D-157)


def test_appearance_offers_three_radio_rows_whose_whole_row_selects(
    render: Callable[[], dict[str, Any]],
) -> None:
    options = options_of(appearance_of(render()))
    assert [(ident, value, tile.title) for ident, value, tile in options] == [
        ("more.appearance.system", "system", "System"),
        ("more.appearance.light", "light", "Light"),
        ("more.appearance.dark", "dark", "Dark"),
    ]
    assert all(tile.toggle_inputs for _, _, tile in options)


def test_the_appearance_label_is_a_heading_for_screen_readers(
    render: Callable[[], dict[str, Any]],
) -> None:
    merged = appearance_column(render()).controls[0]
    # One node: the tile's own node is the heading, not an unlabelled one around it.
    assert isinstance(merged, ft.MergeSemantics)
    label = merged.content
    assert isinstance(label, ft.Semantics) and label.header  # D-33
    assert label.heading_level == 3  # a group inside "You" (D-211)
    assert isinstance(label.content, ft.ListTile)
    assert label.content.title == "Appearance"
    assert label.content.on_click is None  # a label, not a link


async def test_choosing_an_appearance_saves_it(
    render: Callable[[], dict[str, Any]], prefs: Prefs, page: FakePage
) -> None:
    await choose(appearance_of(render()), "light")
    assert prefs.theme == "light"
    assert page.dialogs == []


async def test_an_appearance_that_cannot_be_saved_says_so(
    render: Callable[[], dict[str, Any]],
    prefs: Prefs,
    page: FakePage,
    svc: Services,
) -> None:
    cast(MemoryPrefs, svc.storage.prefs).fail_writes = True
    await choose(appearance_of(render()), "dark")
    assert prefs.theme == "dark"  # applied for this session (D-120)
    [snack] = page.dialogs
    assert isinstance(snack, ft.SnackBar)
    assert isinstance(snack.content, ft.Text)
    assert snack.content.value == "Couldn't save your change"


def test_lightning_talks_appear_once_and_open_their_own_page(
    render: Callable[[], dict[str, Any]], page: FakePage
) -> None:
    """EVT-03, SHELL-10: Ionic listed them twice, under Presentations and Events, with
    two targets; here one row opens the one page, and so does the Tracks hub's row."""
    tiles = [t for row in rows_of(render()) if (t := tile_of(row))]
    lightning = [t for t in tiles if "lightning" in str(t.title).casefold()]
    assert [str(t.title) for t in lightning] == ["Lightning talks"]
    cast(Callable[[], None], lightning[0].on_click)()
    assert page.navigated == ["/more/lightning-talks"]
