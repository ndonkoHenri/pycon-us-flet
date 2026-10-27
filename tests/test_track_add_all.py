"""Tests for "Add all to My schedule" on a track page (``screens/track.py``; #103).

SCHED-24, D-209, ux.md §5.10: the overflow item saves every session the page lists,
on every day, with ``Favorites.add_many()`` (D-172), then one SnackBar with Undo, and
no dialog (D-29). The page runs in a real Flet session over the recorded 2026 feed
(``tests/sessions.py``); the store's own rules are in ``tests/test_favorites.py``.
On devices the SnackBar showed on the pushed track page itself (#255; #197).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.timeline import track_sessions
from pycon_us.favorites import Change
from pycon_us.screens import open_spaces
from pycon_us.screens import track as screen
from pycon_us.state import Conference
from pycon_us.ui.favorite import ALREADY_SAVED, NOT_SAVED, UNDO, added_feedback
from tests.fakes import MemoryHaptics, MemoryPrefs
from tests.feeds import processed
from tests.harness import Shown, showing
from tests.sessions import menu_text, settle, text_of

YEAR = load_year(2026)
DATA = processed(2026)
FAVORITES = "pycon.2026.favorites"
CHARLAS = [s.id for day in track_sessions(DATA, "Charla") for s in day.sessions]
"""The 16 charlas, on more than one day."""

TALK = "142"
"""Python for Humans, a talk: saved before, outside the charlas."""

type Show = Callable[..., Awaitable[Shown]]


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return a function that shows a track page over the feed.

    It takes the track's slug, the sessions ``saved`` before the page opened, and a
    ``conference`` (the recorded feed by default).
    """
    async with AsyncExitStack() as stack:

        async def render(
            slug: str,
            *,
            saved: tuple[str, ...] = (),
            conference: Conference | None = None,
        ) -> Shown:
            page = await stack.enter_async_context(
                showing(
                    lambda: screen.TrackDetail(slug),
                    screen,
                    year=YEAR,
                    conference=conference
                    or Conference(data=DATA, source="bundled", version=1),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=f"/more/tracks/{slug}",
                )
            )
            if saved:  # saved before the page opened, and written
                await page.favorites.add_many(page.services.storage, saved)
                await settle()
            return page

        yield render


def prefs(page: Shown) -> MemoryPrefs:
    """Return the page's ``MemoryPrefs``, where the favourites are written."""
    return cast(MemoryPrefs, page.services.storage.prefs)


def stored(page: Shown) -> list[str] | None:
    """The favourites as written to SharedPreferences."""
    return prefs(page).values.get(FAVORITES)


def effects(page: Shown) -> list[str]:
    """Return the haptic effects the page asked for, in order."""
    return cast(MemoryHaptics, page.services.haptics).effects


def said(page: Shown) -> list[tuple[str, str | None]]:
    """Each SnackBar's message and its action's label, in order."""
    return [
        (text_of(snack.content), label_of(snack.action)) for snack in page.snack_bars
    ]


def label_of(action: str | ft.SnackBarAction | None) -> str | None:
    """Return a SnackBar action's label, or the action as given when it is not one."""
    return action.label if isinstance(action, ft.SnackBarAction) else action


async def add_all(page: Shown) -> None:
    """Tap the overflow menu's one item, Add all to My schedule."""
    (item,) = page.find(ft.PopupMenuItem)
    assert menu_text(item).value == screen.ADD_ALL
    await page.click(item)


async def undo(page: Shown) -> None:
    """Tap Undo on the last SnackBar, then let the session settle."""
    action = cast(ft.SnackBarAction, page.snack_bars[-1].action)
    assert action.label == UNDO
    await cast(Callable[[], Any], action.on_click)()
    await settle()


# ------------------------------------------------------------------ the add


async def test_it_saves_every_session_of_the_track_on_every_day(show: Show) -> None:
    """Not only what is on screen: the charlas run over more than one day."""
    page = await show("charlas")
    assert len(CHARLAS) == 16 and len(track_sessions(DATA, "Charla")) > 1
    await add_all(page)
    assert page.favorites.ids == set(CHARLAS)
    assert stored(page) == sorted(CHARLAS)
    assert said(page) == [("Added 16 sessions", UNDO)]
    assert effects(page) == ["selection_click"]  # as a star's add (ux.md §4.5)
    stars = page.nodes("track.favorite.")
    assert len(stars) == 16 and all(star.toggled for star in stars)


async def test_the_posters_page_adds_each_poster_not_the_posters_row(
    show: Show,
) -> None:
    """SCHED-22: the page lists the 25 posters, so the add saves those."""
    page = await show("posters")
    posters = {s.id for day in track_sessions(DATA, "Poster") for s in day.sessions}
    rows = {s.id for s in DATA.sessions.values() if s.track == "Poster"} - posters
    await add_all(page)
    assert page.favorites.ids == posters and len(posters) == 25
    assert rows and not rows & page.favorites.ids  # the Posters row stays unsaved
    assert said(page) == [("Added 25 sessions", UNDO)]


async def test_it_counts_only_new_sessions_and_undo_restores_the_list_exactly(
    show: Show,
) -> None:
    """D-172: sessions saved before, in the track or not, survive the Undo."""
    before = (CHARLAS[0], CHARLAS[5], TALK)
    page = await show("charlas", saved=before)
    await add_all(page)
    assert said(page) == [("Added 14 sessions", UNDO)]
    assert page.favorites.ids == {*CHARLAS, TALK}
    await undo(page)
    assert page.favorites.ids == set(before)
    assert stored(page) == sorted(before)
    assert len(page.snack_bars) == 1  # an Undo says nothing more, as a star's


async def test_undo_closes_the_added_snack_bar(show: Show) -> None:
    """D-251: with a screen reader it would stay, saying what Undo took back."""
    page = await show("charlas")
    page.prefs.screen_reader = True
    await add_all(page)
    (snack,) = page.snack_bars
    assert snack.open and snack.persist
    await undo(page)
    assert not snack.open
    assert page.snack_bars == [snack]


async def test_one_new_session_is_said_in_the_singular(show: Show) -> None:
    """One new session is said as "Added 1 session", and Undo takes only it back."""
    page = await show("charlas", saved=tuple(CHARLAS[1:]))
    await add_all(page)
    assert said(page) == [("Added 1 session", UNDO)]
    await undo(page)
    assert page.favorites.ids == set(CHARLAS[1:])


async def test_a_track_saved_already_says_so_without_undo_or_a_write(
    show: Show,
) -> None:
    """A track saved already says so, with no Undo, no write and no haptic."""
    page = await show("charlas", saved=tuple(CHARLAS))
    prefs(page).values[FAVORITES] = ["untouched"]  # any write would replace it
    effects(page).clear()
    await add_all(page)
    assert said(page) == [(ALREADY_SAVED, None)]
    assert stored(page) == ["untouched"]
    assert effects(page) == []
    assert page.favorites.ids == set(CHARLAS)


async def test_a_failed_write_says_so_and_keeps_undo(show: Show) -> None:
    """ux.md §4.4: the add shows for the session; Undo still takes it back."""
    page = await show("charlas", saved=(TALK,))
    prefs(page).fail_writes = True
    await add_all(page)
    assert said(page) == [(NOT_SAVED, UNDO)]
    assert page.favorites.ids == {*CHARLAS, TALK}
    await undo(page)
    assert page.favorites.ids == {TALK}


async def test_an_undo_that_cannot_be_saved_says_so_without_another_undo(
    show: Show,
) -> None:
    """An Undo whose write fails takes the add back and says so, with no Undo."""
    page = await show("charlas")
    await add_all(page)
    prefs(page).fail_writes = True
    await undo(page)
    assert page.favorites.ids == set()
    assert said(page)[-1] == (NOT_SAVED, None)


# ------------------------------------------------------------------ where it is offered


@pytest.mark.parametrize("slug", ["talks", "charlas", "posters", "tutorials", "ai"])
async def test_a_track_page_offers_it_in_the_app_bars_overflow(
    show: Show, slug: str
) -> None:
    """A track page's More options menu holds the item, with its identifiers."""
    page = await show(slug)
    (menu,) = page.find(ft.PopupMenuButton)
    assert menu.icon == ft.Icons.MORE_VERT and menu.tooltip == "More options"
    assert page.node("track.menu").content is menu
    (item,) = menu.items
    assert menu_text(item).value == screen.ADD_ALL
    assert cast(ft.Semantics, item.content).identifier == "track.add_all"
    assert page.snack_bars == []  # straight to the SnackBar: no dialog (D-29)


async def test_the_items_label_wraps_beside_its_icon_at_large_text(show: Show) -> None:
    """F47: the item is ``menu_item()``'s, whose label is a tile's title (D-233)."""
    page = await show("charlas")
    (item,) = page.find(ft.PopupMenuItem)
    assert item.icon is None
    tile = cast(ft.ListTile, cast(ft.Semantics, item.content).content)
    assert cast(ft.Icon, tile.leading).icon == ft.Icons.PLAYLIST_ADD
    assert tile.title is menu_text(item)  # no link: it stays in the app


@pytest.mark.parametrize("slug", ["notices", "breaks"])
async def test_it_is_not_offered_on_tracks_without_stars(show: Show, slug: str) -> None:
    """The notices and breaks have no star to fill (D-31)."""
    page = await show(slug)
    assert page.find(ft.PopupMenuButton) == []
    assert page.nodes("track.menu") == []


async def test_it_is_not_offered_without_sessions_to_add(show: Show) -> None:
    """No dead control (ux.md §1): an empty track, or no feed yet."""
    sessions = {k: s for k, s in DATA.sessions.items() if s.track != "Charla"}
    empty = Conference(data=replace(DATA, sessions=sessions), version=1)
    assert (await show("charlas", conference=empty)).find(ft.PopupMenuButton) == []
    loading = await show("charlas", conference=Conference(problem="server"))
    assert loading.find(ft.PopupMenuButton) == []


async def test_the_open_spaces_page_does_not_offer_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The open spaces page, under the Tracks hub, has no overflow and no add.

    ux.md §5.10: the open spaces' slug is this page's route (D-205), never a track
    page's, and the page has no overflow.
    """
    conference = Conference(data=DATA, source="bundled", version=1)
    async with showing(
        open_spaces.OpenSpaces,
        open_spaces,
        year=YEAR,
        conference=conference,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        view_path="/more/tracks/open-spaces",
    ) as page:
        assert page.nodes("open_spaces.session.")  # it shows its sessions
        assert screen.ADD_ALL not in page.texts()
        assert page.find(ft.PopupMenuButton) == []


# ------------------------------------------------------------------ the message


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (Change(added=frozenset(map(str, range(16)))), "Added 16 sessions"),
        (Change(added=frozenset({"1"})), "Added 1 session"),
        (Change(), ALREADY_SAVED),
        (Change(added=frozenset({"1", "2"}), saved=False), NOT_SAVED),
    ],
)
def test_the_message_counts_what_the_add_saved(change: Change, message: str) -> None:
    """The message counts the new sessions, or says none was new, or none was saved."""
    assert added_feedback(change) == message
