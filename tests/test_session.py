"""Tests for session detail (SESS-01..03, -06, -07; ux.md §5.5).

The header, When and where, the star, the speakers and the description; Share, the
posters and an open space's extras are ``test_session_extras.py``'s.

``SessionDetail`` runs in a real Flet session (``tests/session_detail.py``), as the
rows do in ``test_session_rows.py``. How the screen looks, at 200 % text and in dark
mode, is checked on devices (the PR); here, what it says and what a tap does.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.core.change_batches import Batch
from pycon_us.core.diff import Change, ChangeKind, Listing
from pycon_us.core.models import ConferenceData
from pycon_us.prefs import Prefs
from pycon_us.screens import session as screen
from pycon_us.services import Services
from pycon_us.ui.favorite import REMOVED, UNDO
from tests.feeds import processed
from tests.session_detail import (
    BREAK,
    TALK,
    VIEW,
    YEAR,
    Detail,
    Render,
    at,
    headings,
    rendering,
    words,
)
from tests.sessions import menu_text
from tests.trees import descendants, texts

TUTORIAL = "19"
"""A tutorial: registration required."""

LIGHTNING = "175"
"""Lightning talks: shown in the Arena, streamed to four rooms (D-124)."""

KEYNOTE = "176"
"""A keynote: no public page in the feed; its people are year data (D-217)."""

WELCOME = "151"
"""The Friday welcome, a plenary: no speakers in the feed, no keynote data."""

JOB_FAIR = "178"
"""Sun May 17, shown from 9:30 though grouped at its 10:00 start (DATA-11)."""

PANEL = "110"
"""Beyond the Hype: six speakers, five of them without a photo in the feed."""

OPEN_SPACE = "9086"
"""pytest for system tests: its Markdown links ``[pytest](pytest.org)`` (D-140)."""


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Provide an async function that renders a session's detail at ``VIEW`` by id."""
    async with rendering(tmp_path, monkeypatch) as show:
        yield show


# ------------------------------------------------------------------ header (SESS-01)


async def test_the_title_is_the_page_s_selectable_heading(render: Render) -> None:
    """The title is a selectable level-1 headline in the body; the app bar has none."""
    detail = await render(TALK)
    title = detail.node("session.title")
    assert (title.header, title.heading_level) == (True, 1)
    text = cast(ft.Text, title.content)
    assert text.value.startswith("Python for Humans")  # pyright: ignore[reportOptionalMemberAccess]
    assert (text.theme_style, text.selectable) == (
        ft.TextThemeStyle.HEADLINE_SMALL,
        True,
    )
    assert detail.titles[-1] == ""  # the heading names the page, not the app bar


async def test_the_badges_come_before_the_title(render: Render) -> None:
    """A tutorial's badges wrap in a row above its title, in one group with it."""
    detail = await render(TUTORIAL)
    header = detail.node("session.title").parent
    assert isinstance(header, ft.Column)
    badges = header.controls[0]
    assert isinstance(badges, ft.Row) and badges.wrap
    assert texts(badges) == ["Tutorial", "Registration required"]
    assert header.spacing == 8  # one group (ux.md §3.6)


async def test_a_badge_that_repeats_the_title_is_left_out(render: Render) -> None:
    """A break's "Break" pill over its "Break" heading said nothing more."""
    detail = await render(BREAK)
    header = detail.node("session.title").parent
    assert isinstance(header, ft.Column)
    assert header.controls == [detail.node("session.title")]


async def test_the_sections_are_level_2_under_the_title(render: Render) -> None:
    """ux.md §5.5: the title is heading level 1, its sections level 2."""
    detail = await render(TALK)
    speakers = next(
        n
        for n in detail.session.index.values()
        if isinstance(n, ft.Semantics) and n.header and words(n) == ["Speakers"]
    )
    assert speakers.heading_level == 2


# ------------------------------------------------------------------ when (SESS-01)


@pytest.mark.parametrize(
    ("now", "label", "spoken"),
    [
        ("2026-05-16 10:05", "Starts in 25 min", "Starts in 25 minutes"),
        ("2026-05-16 08:25", "Starts in 2 h 5 min", "Starts in 2 hours 5 minutes"),
        ("2026-05-16 10:30", "Happening now", "Happening now"),
        ("2026-05-16 10:59", "Happening now", "Happening now"),
        ("2026-05-16 11:00", "Ended", "Ended"),  # at the end it is over (D-179)
        ("2026-05-18 09:00", "Ended", "Ended"),
    ],
)
async def test_the_time_tile_says_where_the_session_stands(
    render: Render, now: str, label: str, spoken: str
) -> None:
    """The When tile shows the countdown, "Happening now" or "Ended", spoken in full."""
    clock.set_test_now(at(now))
    detail = await render(TALK)
    status = [
        node
        for node in detail.session.index.values()
        if isinstance(node, ft.Text) and node.value == label
    ]
    assert [node.semantics_label for node in status] == [spoken]
    assert label in detail.text("session.when")


async def test_the_day_before_there_is_no_countdown(render: Render) -> None:
    """The day before: the date, then the range read with "to", and no countdown."""
    clock.set_test_now(at("2026-05-15 18:00"))
    detail = await render(TALK)
    lines = detail.text("session.when")
    # The date says when; the range has a line of its own, its "AM" kept to it.
    assert lines[:2] == ["Saturday, May 16", "10:30–11:00\u00a0AM"]
    assert not any(line.startswith("Starts") for line in lines)
    time = next(
        t
        for t in descendants(detail.node("session.when"))
        if isinstance(t, ft.Text) and t.value == lines[1]
    )
    assert time.semantics_label == "10:30 to 11:00 AM"  # "to", not a dash


@pytest.mark.parametrize(
    ("now", "label"),
    [("2026-05-17 09:20", "Starts in 10 min"), ("2026-05-17 09:45", "Happening now")],
)
async def test_the_status_follows_the_start_the_tile_shows(
    render: Render, now: str, label: str
) -> None:
    """The Job Fair opens at 9:30, though the Schedule groups it at 10:00 (DATA-11)."""
    clock.set_test_now(at(now))
    detail = await render(JOB_FAIR)
    lines = detail.text("session.when")
    assert lines[1].startswith("9:30")
    assert label in lines


async def test_with_nothing_to_add_the_time_tile_has_no_blank_line(
    render: Render,
) -> None:
    """Another day on Pacific time: no status, no note, so no subtitle's height."""
    clock.set_test_now(at("2026-05-15 18:00"))
    detail = await render(TALK)
    tile = next(
        n
        for n in descendants(detail.node("session.when"))
        if isinstance(n, ft.ListTile)
    )
    assert tile.subtitle is None


async def test_the_status_follows_the_clock_on_the_minute_tick(
    render: Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-40: the line re-renders itself as time passes, under the fake clock too."""
    clock.set_test_now(at("2026-05-16 10:29"))
    ticks: list[Callable[[], object]] = []

    async def run_every(self: Services, seconds: float, action: Callable[[], object]):
        ticks.append(action)
        action()

    monkeypatch.setattr(Services, "run_every", run_every)
    detail = await render(TALK)
    assert "Starts in 1 min" in detail.text("session.when")
    clock.set_test_now(at("2026-05-16 10:31"))
    for tick in ticks:  # the status line's, and the Changed badges' (D-315)
        tick()
    await detail.settle()
    assert "Happening now" in detail.text("session.when")


async def test_leaving_the_detail_stops_its_minute_ticks(
    render: Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F2, F39: only the effect's cleanup makes Flet cancel the loop on unmount."""
    loops: list[asyncio.Task[Any]] = []

    async def run_every(self: Services, seconds: float, action: Callable[[], object]):
        loops.append(cast(asyncio.Task[Any], asyncio.current_task()))
        await asyncio.Event().wait()  # until cancelled

    monkeypatch.setattr(Services, "run_every", run_every)
    detail = await render(TALK)
    assert loops  # the status line's, and the Changed badges' (D-315)
    assert not any(loop.done() for loop in loops)
    await detail.show(None)
    assert all(loop.cancelled() for loop in loops)


async def test_a_device_in_another_zone_gets_the_pacific_time_note(
    render: Render, machine_tz: str
) -> None:
    """D-35: say the times are conference time when the device's clock differs."""
    detail = await render(TALK)
    note = "Times are Pacific Time (PDT)"
    expected = machine_tz != "America/Los_Angeles"
    assert (note in detail.text("session.when")) is expected


# ------------------------------------------------------------------ where (SESS-02)


async def test_the_room_tile_pushes_the_room_with_the_session_highlighted(
    render: Render,
) -> None:
    """The room tile pushes room detail highlighting the session; one room, no fold."""
    detail = await render(TALK)
    room = detail.node("session.room")
    assert words(room) == ["Grand Ballroom A"]
    tile = next(n for n in descendants(room) if isinstance(n, ft.ListTile))
    await detail.click(tile)
    assert detail.pushed == [f"{VIEW}/room/grand-ballroom-a?highlight={TALK}"]
    assert detail.nodes("session.other_rooms") == []  # one room, nothing folded


async def test_a_streamed_session_folds_its_other_rooms(render: Render) -> None:
    """A streamed session shows its main room and folds the four others.

    The first folded room is a link to its room detail, highlighting the session.
    """
    detail = await render(LIGHTNING)
    assert words(detail.node("session.room")) == ["Pacific Ballroom - Arena"]
    folded = detail.node("session.other_rooms").content
    assert isinstance(folded, ft.ExpansionTile)
    assert cast(ft.Text, folded.title).value == "+4 more rooms"
    rooms = folded.controls or []
    assert [words(room) for room in rooms] == [
        ["Room 103ABC"],
        ["Room 104AB"],
        ["Grand Ballroom A"],
        ["Grand Ballroom B"],
    ]
    tile = next(n for n in descendants(rooms[0]) if isinstance(n, ft.ListTile))
    await detail.click(tile)
    assert detail.pushed == [f"{VIEW}/room/room-103abc?highlight={LIGHTNING}"]


async def test_the_folded_rooms_stay_open_once_opened(render: Render) -> None:
    """Coming back from a room's detail re-rendered the tile folded (iOS simulator)."""
    detail = await render(LIGHTNING)
    folded = cast(ft.ExpansionTile, detail.node("session.other_rooms").content)
    assert folded.expanded is False
    await detail.session.dispatch_event(folded._i, "change", True)
    await detail.settle()
    folded = cast(ft.ExpansionTile, detail.node("session.other_rooms").content)
    assert folded.expanded is True


async def test_a_break_in_many_rooms_lists_them_without_one_place(
    render: Render,
) -> None:
    """A break has no main room: "In 5 rooms" folds them.

    The first folded room's link quotes the break's id.
    """
    detail = await render(BREAK)
    assert detail.nodes("session.room") == []
    folded = cast(ft.ExpansionTile, detail.node("session.other_rooms").content)
    assert cast(ft.Text, folded.title).value == "In 5 rooms"
    first = (folded.controls or [])[0]
    await detail.click(
        next(n for n in descendants(first) if isinstance(n, ft.ListTile))
    )
    # Its id holds spaces, commas and colons: quoted, so room detail reads it whole.
    assert detail.pushed == [
        f"{VIEW}/room/room-103abc?highlight={quote(BREAK, safe='')}"
    ]


async def test_reduced_motion_opens_the_rooms_without_animation(
    render: Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With reduced motion, the folded rooms open with a 0 ms animation."""
    monkeypatch.setattr(Prefs, "motion_ms", lambda self, ms: 0)
    detail = await render(LIGHTNING)
    folded = cast(ft.ExpansionTile, detail.node("session.other_rooms").content)
    assert cast(ft.AnimationStyle, folded.animation_style).duration == 0


# ------------------------------------------------------------------ speakers (SESS-07)


def speaker_rows(detail: Detail) -> list[ft.Semantics]:
    """Return the detail's speaker rows, the nodes named ``session.speaker.<id>``."""
    return [
        node
        for node in detail.session.index.values()
        if isinstance(node, ft.Semantics)
        and (node.identifier or "").startswith("session.speaker.")
    ]


async def test_a_speaker_s_row_pushes_their_page_one_level_up(render: Render) -> None:
    """A speaker's row reads their initials and name, and pushes their page."""
    detail = await render(TALK)
    (row,) = speaker_rows(detail)
    assert row.identifier == "session.speaker.150"
    assert words(row) == ["JL", "Justin Lee"]  # the avatar's initials, then the name
    tile = next(n for n in descendants(row) if isinstance(n, ft.ListTile))
    await detail.click(tile)
    assert detail.pushed == [f"{VIEW}/speaker/150"]


async def test_the_speakers_come_in_the_feed_s_order_with_their_photos(
    render: Render,
) -> None:
    """The speakers come in the feed's order, with their photos or else initials."""
    detail = await render(PANEL)
    session = processed(2026).sessions[PANEL]
    rows = speaker_rows(detail)
    assert [words(row)[1] for row in rows] == list(session.speaker_names)
    avatars = [
        next(n for n in descendants(row) if isinstance(n, ft.CircleAvatar))
        for row in rows
    ]
    # A speaker without a photo shows their initials alone, with no empty request.
    missing = [a for a in avatars if a.foreground_image_src is None]
    assert len(missing) == 5
    assert all(isinstance(a.content, ft.Text) and a.content.value for a in missing)


async def test_a_pseudo_speaker_is_plain_text_that_nothing_taps(
    render: Render,
) -> None:
    """D-125: "Hosted by …" is no person with a page (DATA-15)."""
    detail = await render(LIGHTNING)
    assert speaker_rows(detail) == []
    # Its own node, not merged into the "Speakers" heading (seen on Android).
    node = detail.node("session.name.0")
    assert node.container
    assert words(node) == ["Hosted by Abigail, Chris, Cristián, and Lorena"]
    holder: object = node
    while isinstance(holder, ft.Control):
        assert getattr(holder, "on_click", None) is None, holder
        holder = holder.parent


async def test_names_with_no_speaker_each_get_an_identifier_in_the_authors_order(
    render: Render,
) -> None:
    """D-197: two free names must not share one node id (a UI test finds each)."""
    detail = await render(PANEL)
    data = cast(ConferenceData, detail.conference.data)
    ana = data.speakers[data.sessions[PANEL].speaker_ids[0]]
    session = replace(
        data.sessions[PANEL],
        speaker_ids=(ana.id,),
        speaker_names=("Hosted by the PSF", ana.name, "A. Guest"),
    )
    newer = replace(data, sessions={**data.sessions, PANEL: session})
    detail.conference.data, detail.conference.version = newer, 2
    await detail.settle()
    assert words(detail.node("session.name.0")) == ["Hosted by the PSF"]
    assert words(detail.node("session.name.1")) == ["A. Guest"]
    assert [row.identifier for row in speaker_rows(detail)] == [
        f"session.speaker.{ana.id}"
    ]
    # In the authors' order, read down the section: a name, the speaker, a name.
    section = detail.node("session.name.0").parent
    assert isinstance(section, ft.Column)
    order = [
        node.identifier
        for node in descendants(section)
        if isinstance(node, ft.Semantics)
        and (node.identifier or "").startswith(("session.name.", "session.speaker."))
    ]
    assert order == ["session.name.0", f"session.speaker.{ana.id}", "session.name.1"]


async def test_a_session_without_speakers_has_no_speakers_section(
    render: Render,
) -> None:
    """A session without speakers has no speaker rows and no Speakers heading."""
    detail = await render(WELCOME)
    assert speaker_rows(detail) == []
    assert all(text != "Speakers" for text, _ in headings(detail))


# ------------------------------------------------------------------ about (SESS-06)


def markdown(detail: Detail) -> ft.Markdown:
    """Return the one ``Markdown`` control in the detail's description."""
    (found,) = [
        n
        for n in descendants(detail.node("session.description"))
        if isinstance(n, ft.Markdown)
    ]
    return found


async def test_the_description_follows_the_speakers_under_its_own_heading(
    render: Render,
) -> None:
    """ux.md §5.5: speakers, then About, each a level-2 section."""
    detail = await render(TALK)
    assert [h for h in headings(detail) if h[1] == 2] == [
        ("Speakers", 2),
        ("About", 2),
    ]
    text = markdown(detail)
    assert text.value == processed(2026).sessions[TALK].description_md
    assert text.selectable


async def test_a_link_in_a_description_opens_in_the_in_app_browser(
    render: Render,
) -> None:
    """A description's link opens in the in-app browser, with ``https://`` added."""
    detail = await render(OPEN_SPACE)
    text = markdown(detail)
    assert "[pytest](pytest.org)" in text.value
    await detail.session.dispatch_event(text._i, "tap_link", "pytest.org")
    await detail.settle()
    assert detail.launcher.launched == [
        ("https://pytest.org", ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]
    assert detail.pushed == []


async def test_a_session_without_a_description_has_no_about(render: Render) -> None:
    """A session without a description has no description and no About heading."""
    detail = await render(BREAK)
    assert detail.nodes("session.description") == []
    assert all(text != "About" for text, _ in headings(detail))


# ------------------------------------------------------------------ registration


async def test_a_tutorial_says_it_needs_registration_and_links_the_dashboard(
    render: Render,
) -> None:
    """A tutorial's card says to register separately; its link opens registration."""
    detail = await render(TUTORIAL)
    assert detail.text("session.registration") == [
        screen.REGISTRATION_TITLE,
        screen.REGISTRATION_TEXT,
    ]
    link = detail.node("session.registration.link")
    tile = next(n for n in descendants(link) if isinstance(n, ft.ListTile))
    await detail.click(tile)
    assert detail.launcher.launched == [
        (YEAR.conference.registration_url, ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]


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
    assert detail.nodes("session.removed")
    assert detail.nodes("session.changed.room") == []
