"""Tests for session detail's registration, app bar, states and changes (SESS-03).

The registration card, the star and the overflow, an unknown or dropped id, and the
change badges (NEW-04). The header and When and where are ``test_session.py``'s.

``SessionDetail`` runs in a real Flet session (``tests/session_detail.py``), as the
rows do in ``test_session_rows.py``. How the screen looks, at 200 % text and in dark
mode, is checked on devices (the PR); here, what it says and what a tap does.
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.core.change_batches import Batch
from pycon_us.core.diff import Change, ChangeKind, Listing
from pycon_us.core.models import ConferenceData
from pycon_us.screens import session as screen
from pycon_us.services import Services
from pycon_us.ui.favorite import REMOVED, UNDO
from tests import session_detail
from tests.session_detail import (
    BREAK,
    KEYNOTE,
    TALK,
    TUTORIAL,
    YEAR,
    Detail,
    Render,
    at,
    words,
)
from tests.sessions import menu_text
from tests.trees import descendants, texts

# The detail's fixture, shared by name: pytest finds fixtures among a module's names.
render = session_detail.render

# ------------------------------------------------------------------ registration


def assert_line_icon(node: ft.Control, name: ft.IconData) -> None:
    """Assert the icon topping ``node``'s TITLE_SMALL line is one line tall at any size.

    D-373: 20 dp, scaled with the text, so it stays beside the first line.
    """
    icon = next(
        n for n in descendants(node) if isinstance(n, ft.Icon) and n.icon == name
    )
    assert (icon.size, icon.apply_text_scaling) == (20, True)


async def test_a_tutorial_says_it_needs_registration_and_links_the_dashboard(
    render: Render,
) -> None:
    """A tutorial's card says to register separately; its link opens registration."""
    url = "https://example.org/2026/accounts/dashboard/"
    # 2026 as if its site still had the dashboard, which went with the live site (#824).
    conference = replace(YEAR.conference, registration_url=url)
    detail = await render(TUTORIAL, year=replace(YEAR, conference=conference))
    assert detail.text("session.registration") == [
        screen.REGISTRATION_TITLE,
        screen.REGISTRATION_TEXT,
    ]
    link = detail.node("session.registration.link")
    tile = next(n for n in descendants(link) if isinstance(n, ft.ListTile))
    await detail.click(tile)
    assert detail.launcher.launched == [(url, ft.LaunchMode.IN_APP_BROWSER_VIEW)]
    assert_line_icon(detail.node("session.registration"), ft.Icons.INFO_OUTLINE)


async def test_2026_s_registration_card_has_no_link_since_its_dashboard_is_gone(
    render: Render,
) -> None:
    """The dashboard went with the live site: the words stay, no dead link (#824)."""
    detail = await render(TUTORIAL)
    assert detail.text("session.registration") == [
        screen.REGISTRATION_TITLE,
        screen.REGISTRATION_TEXT,
    ]
    assert detail.nodes("session.registration.link") == []


async def test_a_talk_needs_no_registration_card(render: Render) -> None:
    """A talk has no registration card."""
    detail = await render(TALK)
    assert detail.nodes("session.registration") == []


# ------------------------------------------------------------------ app bar (SESS-03)


async def test_the_star_saves_and_undo_brings_it_back(render: Render) -> None:
    """The star saves the session; a second tap removes it, and Undo saves it again."""
    detail = await render(TALK)
    star = cast(ft.IconButton, detail.node("session.favorite").content)
    await detail.click(star)
    assert detail.favorites.ids == {TALK}
    star = cast(ft.IconButton, detail.node("session.favorite").content)
    assert star.icon == ft.Icons.STAR
    await detail.click(star)
    (snack,) = detail.snack_bars
    assert cast(ft.Text, snack.content).value == REMOVED
    action = cast(ft.SnackBarAction, snack.action)
    assert action.label == UNDO
    await cast(Callable[[], Any], action.on_click)()
    await detail.settle()
    assert detail.favorites.ids == {TALK}


async def test_the_overflow_opens_the_public_page(render: Render) -> None:
    """The overflow's first item is a link that opens the session's public page."""
    detail = await render(TALK)
    menu = cast(ft.PopupMenuButton, detail.node("session.overflow").content)
    assert menu.tooltip == "More options"
    item = menu.items[0]  # Add to calendar follows (tests/test_session_calendar.py)
    assert detail.node("session.open_site") is item.content
    title = cast(ft.ListTile, cast(ft.Semantics, item.content).content).title
    assert cast(ft.Semantics, title).link  # it leaves the app (ux.md §4.7)
    text = menu_text(item)  # a tile's title, which wraps at 200 % (F47, D-233)
    assert text.value == "Open on us.pycon.org"
    assert text.semantics_label == "Open on us.pycon.org\nOpens in browser"
    await detail.click(item)
    assert detail.launcher.launched == [
        (
            "https://us.pycon.org/2026/schedule/presentation/142/",
            ft.LaunchMode.IN_APP_BROWSER_VIEW,
        )
    ]


async def test_a_break_has_no_star_as_its_row_has_none(render: Render) -> None:
    """D-31: breaks and notices are not saved to My schedule."""
    detail = await render(BREAK)
    assert detail.nodes("session.favorite") == []


async def test_a_session_without_a_public_page_has_no_link_to_it(
    render: Render,
) -> None:
    """D-60: no dead controls; its overflow holds Add to calendar alone (SESS-04)."""
    detail = await render(KEYNOTE)
    assert detail.nodes("session.open_site") == []
    assert detail.nodes("session.add_to_calendar")
    assert detail.nodes("session.favorite")  # the star is always there


# ------------------------------------------------------------------ states


async def test_an_unknown_id_names_the_session_and_offers_the_schedule(
    render: Render,
) -> None:
    """An unknown id says the session isn't in the schedule and offers the Schedule."""
    detail = await render("no-such-session")
    assert detail.text("session.not_found") == [screen.NOT_FOUND]
    button = next(
        n for n in detail.session.index.values() if isinstance(n, ft.FilledTonalButton)
    )
    assert button.content == "Open schedule"
    await detail.click(button)
    assert detail.pushed == ["/schedule"]
    assert detail.nodes("session.favorite") == []


async def test_another_unknown_id_in_place_is_not_found_not_the_last_session(
    render: Render,
) -> None:
    """The same View given another id (a deep link at the same depth) forgets TALK."""
    detail = await render(TALK)
    await detail.show("no-such-session")
    assert detail.text("session.not_found") == [screen.NOT_FOUND]
    assert detail.nodes("session.removed") == []
    assert detail.nodes("session.title") == []


async def test_a_session_a_refresh_drops_keeps_its_content_under_a_note(
    render: Render,
) -> None:
    """A session a refresh drops keeps its content and star under an announced note."""
    detail = await render(TALK)
    assert detail.nodes("session.removed") == []
    data = cast(ConferenceData, detail.conference.data)
    newer = replace(
        data, sessions={k: v for k, v in data.sessions.items() if k != TALK}
    )
    detail.conference.data, detail.conference.version = newer, 2
    await detail.settle()
    note = detail.node("session.removed")
    assert note.live_region  # announced: it appears while the page is open
    assert words(note)[0] == screen.REMOVED
    assert detail.nodes("session.title")  # the content stays
    assert detail.nodes("session.favorite")  # and the star still works


# ------------------------------------------------------------------ changed (NEW-04)


async def record_changes(detail: Detail, *kinds: ChangeKind) -> None:
    """Record one batch changing TALK by ``kinds``, an hour before the frozen now.

    Its old sides: Room 102A, Friday 10:30 AM and the title "Python for People".
    """
    data = cast(ConferenceData, detail.conference.data)
    talk = data.sessions[TALK]
    new = Listing(talk.name, talk.display_start, talk.end, talk.location)
    olds = {
        ChangeKind.ROOM: replace(new, location="Room 102A"),
        ChangeKind.TIME: replace(
            new,
            start=talk.display_start - timedelta(days=1),
            end=talk.end - timedelta(days=1),
        ),
        ChangeKind.TITLE: replace(new, title="Python for People"),
    }
    now = at("2026-05-14 12:00")
    clock.set_test_now(now)
    changes = tuple(Change(TALK, kind, olds[kind], new) for kind in kinds)
    detail.change_log.batches = (Batch(now - timedelta(hours=1), changes),)
    await detail.settle()


def changed_badges(detail: Detail) -> list[tuple[str, str]]:
    """The Changed badges under the title: what each says, and what it shows."""
    found = [
        n
        for n in detail.session.index.values()
        if isinstance(n, ft.Semantics)
        and (n.identifier or "").startswith("session.changed.")
    ]
    return [(n.label or "", " ".join(words(n))) for n in found]


async def test_each_kind_of_change_shows_its_badge_with_the_old_value(
    render: Render,
) -> None:
    """Moved, retimed and renamed: a badge each, after the track's, read whole."""
    detail = await render(TALK)
    assert changed_badges(detail) == []  # unchanged: none
    await record_changes(detail, ChangeKind.TIME, ChangeKind.ROOM, ChangeKind.TITLE)
    assert changed_badges(detail) == [
        ("Was Friday, May 15, 10:30 AM", "Was Fri, May 15, 10:30\N{NO-BREAK SPACE}AM"),
        ("Moved from Room 102A", "Moved from Room 102A"),
        ("Renamed from “Python for People”", "Renamed from “Python for People”"),
    ]
    header = detail.node("session.title").parent
    assert isinstance(header, ft.Column)
    assert texts(header.controls[0])[0] == "Talk"  # the track's badge first
    assert detail.node("session.changed.room").exclude_semantics  # one phrase


async def test_a_badge_goes_on_the_tick_after_its_24_hours(
    render: Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The badges last 24 h, like the rows' Changed, and go on the open page (D-315)."""
    ticks: list[Callable[[], object]] = []

    async def run_every(self: Services, seconds: float, action: Callable[[], object]):
        ticks.append(action)

    monkeypatch.setattr(Services, "run_every", run_every)
    detail = await render(TALK)
    await record_changes(detail, ChangeKind.ROOM)
    assert detail.nodes("session.changed.room")
    clock.set_test_now(at("2026-05-15 11:00"))  # 24 h after the batch
    for tick in ticks:
        tick()
    await detail.settle()
    assert detail.nodes("session.changed.room") == []


async def test_a_removed_session_keeps_its_note_without_change_badges(
    render: Render,
) -> None:
    """D-186's note is unchanged: a dropped session no longer says what moved."""
    detail = await render(TALK)
    await record_changes(detail, ChangeKind.ROOM)
    data = cast(ConferenceData, detail.conference.data)
    newer = replace(
        data, sessions={k: v for k, v in data.sessions.items() if k != TALK}
    )
    detail.conference.data, detail.conference.version = newer, 2
    await detail.settle()
    assert_line_icon(detail.node("session.removed"), ft.Icons.EVENT_BUSY_OUTLINED)
    assert detail.nodes("session.changed.room") == []
