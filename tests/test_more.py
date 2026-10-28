"""Tests for the More tab: a flat, sectioned list of pages (#77; D-15, ux.md §2.2).

``More`` runs outside a renderer: its hooks and ``AppScaffold`` are replaced, and a fake
page is bound as Flet binds a session's page. The scaffold itself (the bar, the re-tap,
Back) is tested in ``test_scaffold.py``; how the list looks and reads is checked on
devices (the PR).
"""

import inspect
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import prefs as prefs_module
from pycon_us.account import Account
from pycon_us.config import load_year
from pycon_us.dev_options import DEV_MOCK_API_URL, DEV_UNLOCKED
from pycon_us.locations import PAGES, parent_of
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import more
from pycon_us.screens.more import MORE_PAGES, More, MoreEntry
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.staff import Staff
from tests.fake_page import FakePage, bound, phone_margin
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)


@pytest.fixture
def page() -> Iterator[FakePage]:
    """A ``FakePage`` bound as Flet binds a session's page."""
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """The session's services over in-memory fakes and a 2026 ``Storage``."""
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
    """Prefs at their defaults, as on a first launch."""
    return Prefs()


@pytest.fixture
def account() -> Account:
    """A signed-out ``Account`` store, restored, as after a first launch."""
    return Account(restored=True)


@pytest.fixture
def staff() -> Staff:
    """An empty ``Staff`` store: nothing queued."""
    return Staff()


async def retap() -> None:
    """The root's re-tap action, as ``use_scroll_to_top()`` would return it."""


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch,
    svc: Services,
    prefs: Prefs,
    account: Account,
    staff: Staff,
    page: FakePage,
) -> Callable[[], dict[str, Any]]:
    """Render ``More`` once and return what it passed to ``AppScaffold``.

    The services come first: a service built while a page is bound registers with it.
    """
    monkeypatch.setattr(more, "use_scroll_to_top", lambda: (ft.Ref(), retap))
    monkeypatch.setattr(more, "use_services", lambda: svc)
    monkeypatch.setattr(more, "use_prefs", lambda: prefs)
    monkeypatch.setattr(more, "use_account", lambda: account)
    monkeypatch.setattr(more, "use_staff", lambda: staff)
    monkeypatch.setattr(more, "AppScaffold", lambda **kwargs: kwargs)
    monkeypatch.setattr(more, "use_margin", phone_margin)
    # The companion app's list, wherever pytest runs (FLET_PLATFORM may be set, F14)
    monkeypatch.setattr(prefs_module, "DEVELOPER_ALWAYS", True)

    def render() -> dict[str, Any]:
        return cast(dict[str, Any], inspect.unwrap(More)())

    return render


def rows_of(scaffold: dict[str, Any]) -> list[ft.Control]:
    """Return the rows of the scaffold's ``ListView`` body."""
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


def test_the_list_has_programme_expo_venue_and_you_under_section_headers(
    render: Callable[[], dict[str, Any]],
) -> None:
    """Programme, Expo (Sponsors, Expo hall, Job listings), the venue, About, You."""
    assert outline(rows_of(render())) == [
        "# Programme",
        "Speakers",
        "Tracks & session types",
        "Keynotes",
        "Open spaces",
        "Lightning talks",
        "Sprints",
        "# Expo & sponsors",
        "Sponsors",
        "Expo hall",
        "Job listings",
        "# At the venue",
        "Venue & hours",
        "Wi-Fi",
        "Help & safety",
        "# About",
        "About PyCon US",
        "About the PSF",
        "Social media",
        "# You",
        "Settings",
        "About this app",
        "Developer options",
    ]  # About this app says "Not an official PSF app." now (D-36)


def test_developer_is_hidden_in_packaged_builds_until_unlocked(
    monkeypatch: pytest.MonkeyPatch,
    render: Callable[[], dict[str, Any]],
    prefs: Prefs,
) -> None:
    """A packaged build lists Developer options only once Developer is unlocked."""
    monkeypatch.setattr(prefs_module, "DEVELOPER_ALWAYS", False)
    titles = outline(rows_of(render()))
    assert "About this app" in titles
    assert "Developer options" not in titles  # D-73
    prefs.dev = {DEV_UNLOCKED: True}  # 7 taps on the version (D-187)
    assert outline(rows_of(render()))[-1] == "Developer options"


def test_every_row_opens_a_page_of_the_route_table_so_none_is_dead(
    render: Callable[[], dict[str, Any]], page: FakePage
) -> None:
    """Tapping every row goes to each More page in turn, all in the route table."""
    for row in rows_of(render()):
        if (tile := tile_of(row)) is not None:
            cast(Callable[[], None], tile.on_click)()
    assert page.navigated == [entry.location for entry in MORE_PAGES]
    # Every one a page, but the hall: the drill's ``plan/expo`` on More (D-17).
    assert set(page.navigated) - PAGES == {"/more/plan/expo"}


@pytest.mark.parametrize("entry", MORE_PAGES, ids=lambda entry: entry.location)
def test_a_tap_pushes_the_row_s_page_and_back_returns_to_more(
    render: Callable[[], dict[str, Any]], page: FakePage, entry: MoreEntry
) -> None:
    """A row's tap goes to its page, whose parent is More, so Back returns there."""
    tiles = {str(t.title): t for row in rows_of(render()) if (t := tile_of(row))}
    tile = tiles[entry.title]
    assert tile.on_click is not None
    cast(Callable[[], None], tile.on_click)()
    assert page.navigated == [entry.location]
    assert parent_of(entry.location) == "/more"  # one pushed View (D-17)


def test_each_row_has_its_icon_and_a_more_identifier(
    render: Callable[[], dict[str, Any]],
) -> None:
    """Each page row is a merged node with its entry's identifier and icon."""
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
    """Each entry's identifier is ``more.`` and its page's name in snake case."""
    assert [entry.identifier for entry in MORE_PAGES] == [
        "more.speakers",
        "more.tracks",
        "more.keynotes",
        "more.open_spaces",
        "more.lightning_talks",
        "more.sprints",
        "more.sponsors",
        "more.expo",
        "more.jobs",
        "more.venue",
        "more.wifi",
        "more.help",
        "more.about",
        "more.psf",
        "more.social",
        "more.settings",
        "more.app",
        "more.developer",
    ]


def test_more_keeps_the_search_and_the_re_tap_scroll_to_top(
    render: Callable[[], dict[str, Any]],
) -> None:
    """More is titled More, scrolls to top on a re-tap, and its one action is Search."""
    scaffold = render()
    assert scaffold["title"] == "More"
    assert scaffold["on_retap"] is retap  # D-144, D-166
    [action] = scaffold["actions"]
    assert isinstance(action, ft.MergeSemantics)  # one node with its tooltip (D-234)
    search = action.content
    assert isinstance(search, ft.IconButton)
    assert search.tooltip == "Search"


def test_lightning_talks_appear_once_and_open_their_own_page(
    render: Callable[[], dict[str, Any]], page: FakePage
) -> None:
    """Lightning talks is one row of More, and it opens their one page.

    EVT-03, SHELL-10: Ionic listed them twice, under Presentations and Events, with two
    targets; here one row opens the one page, and so does the Tracks hub's row.
    """
    tiles = [t for row in rows_of(render()) if (t := tile_of(row))]
    lightning = [t for t in tiles if "lightning" in str(t.title).casefold()]
    assert [str(t.title) for t in lightning] == ["Lightning talks"]
    cast(Callable[[], None], lightning[0].on_click)()
    assert page.navigated == ["/more/lightning-talks"]


def test_a_year_without_booths_has_no_expo_hall_row(
    monkeypatch: pytest.MonkeyPatch,
    render: Callable[[], dict[str, Any]],
    svc: Services,
) -> None:
    """No booths, no hall to push: the row would be dead, so it isn't there."""
    year = replace(svc.year, map=replace(svc.year.map, booths=()))
    monkeypatch.setattr(more, "use_services", lambda: replace(svc, year=year))
    titles = outline(rows_of(render()))
    assert "Expo hall" not in titles
    assert titles[titles.index("# Expo & sponsors") + 1] == "Sponsors"


def test_with_a_mock_url_the_list_starts_with_sign_in(
    render: Callable[[], dict[str, Any]], prefs: Prefs, page: FakePage
) -> None:
    """Signed out with a mock URL set, "Sign in" is first and opens its page (D-51)."""
    prefs.dev = {DEV_MOCK_API_URL: "http://10.0.2.2:8000"}
    first = rows_of(render())[0]
    tile = tile_of(first)
    assert tile is not None and str(tile.title) == "Sign in"
    assert isinstance(first, ft.MergeSemantics)
    assert isinstance(first.content, ft.Semantics)
    assert first.content.identifier == "more.sign_in"
    cast(Callable[[], None], tile.on_click)()
    assert page.navigated == ["/more/sign-in"]
    assert parent_of("/more/sign-in") == "/more"  # Back, and the pop after success


def test_signed_in_the_first_row_is_the_account_and_opens_its_page(
    render: Callable[[], dict[str, Any]],
    page: FakePage,
    prefs: Prefs,
    account: Account,
) -> None:
    """Initials, nickname and email, one node, which opens the Account page (#688)."""
    prefs.dev = {DEV_MOCK_API_URL: "http://10.0.2.2:8000"}
    account.email, account.nickname = "all@example.com", "Robin Everything"
    account.signed_in = True
    first = rows_of(render())[0]
    assert isinstance(first, ft.MergeSemantics)
    assert isinstance(first.content, ft.Semantics)
    assert first.content.identifier == "more.account"
    tile = first.content.content
    assert isinstance(tile, ft.ListTile)
    cast(Callable[[], None], tile.on_click)()
    assert page.navigated == ["/more/account"]
    assert (tile.title, tile.subtitle) == ("Robin Everything", "all@example.com")
    avatar = cast(ft.Semantics, tile.leading)
    assert avatar.exclude_semantics  # the letters are not read before the name
    assert cast(ft.Text, cast(ft.CircleAvatar, avatar.content).content).value == "RE"


def test_an_expired_account_s_row_asks_to_sign_in_again(
    render: Callable[[], dict[str, Any]],
    prefs: Prefs,
    account: Account,
    page: FakePage,
) -> None:
    """A refused key: "Sign in again" over the email, opening Sign in (D-57, #686)."""
    prefs.dev = {DEV_MOCK_API_URL: "http://10.0.2.2:8000"}
    account.email, account.nickname = "all@example.com", "Robin Everything"
    account.signed_in = account.expired = True
    first = rows_of(render())[0]
    tile = tile_of(first)
    assert tile is not None and str(tile.title) == "Sign in again"
    assert tile.subtitle == "all@example.com"
    assert isinstance(first, ft.MergeSemantics)
    assert isinstance(first.content, ft.Semantics)
    assert first.content.identifier == "more.sign_in_again"
    cast(Callable[[], None], tile.on_click)()
    assert page.navigated == ["/more/sign-in"]


@pytest.mark.parametrize(
    ("nickname", "email", "letters"),
    [("Robin Everything", "all@example.com", "RE"), ("", "all@example.com", "A")],
)
def test_an_account_s_initials_fall_back_to_the_email(
    nickname: str, email: str, letters: str
) -> None:
    """An account without a nickname still gets a letter in its avatar."""
    assert more.account_initials(nickname, email) == letters
