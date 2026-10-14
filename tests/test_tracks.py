"""Tests for the Tracks hub and the track pages (``screens/tracks.py``, ``track.py``; #102).

SCHED-21, SCHED-22, EVT-04, DATA-29, SHELL-10. The hub's sections and counts are plain
functions over the recorded feeds; the screens run in a real Flet session under the
store providers (``tests/sessions.py``'s ``showing()``). The slugs' loader rules are in
``tests/test_config.py``; ``track_sessions()`` itself in ``tests/test_timeline.py``.
How the pages look, wrap at 200 % and read to screen readers is checked on devices (the
PR).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.config import HUB_PAGES, load_year
from pycon_us.core.timefmt import day_heading
from pycon_us.core.timeline import track_sessions
from pycon_us.locations import PAGES, parent_of
from pycon_us.prefs import Prefs
from pycon_us.screens import track as track_screen
from pycon_us.screens import tracks as hub_screen
from pycon_us.screens.tracks import HubEntry, hub_groups, hub_phrase, track_count
from pycon_us.state import Conference
from pycon_us.ui import day_groups
from pycon_us.ui.semantics import semantics_key
from tests.feeds import YEARS, processed
from tests.sessions import Shown, showing, text_of

YEAR = load_year(2026)
INFO = YEAR.conference
DATA = processed(2026)


def track(slug: str):
    found = INFO.track_for_slug(slug)
    assert found is not None, slug
    return found


# ------------------------------------------------------------------ the hub's rows


def test_the_hub_groups_the_session_types_and_leaves_out_breaks_and_notices() -> None:
    """ux.md §5.10: Presentations, Hands-on and Community, in the registry's order."""
    groups = hub_groups(INFO, DATA)
    assert [(title, [e.track.slug for e in entries]) for title, entries in groups] == [
        (
            "Presentations",
            [
                "talks",
                "keynotes",
                "plenaries",
                "lightning-talks",
                "ai",
                "security",
                "charlas",
                "posters",
            ],
        ),
        ("Hands-on", ["tutorials", "sponsor-presentations"]),
        ("Community", ["open-spaces", "summits", "events"]),
    ]


@pytest.mark.parametrize("year", YEARS)
def test_each_count_is_what_the_tracks_page_lists(year: int) -> None:
    data = processed(year)
    info = load_year(year).conference
    for _, entries in hub_groups(info, data):
        for entry in entries:
            listed = [
                s for d in track_sessions(data, entry.track.key) for s in d.sessions
            ]
            assert entry.count == len(listed) > 0, entry.track.key


def test_posters_are_counted_one_by_one_and_open_spaces_whatever_the_filter() -> None:
    """SCHED-22: the 25 posters, not the Posters row; D-20: the filter is the Schedule's."""
    assert track_count(DATA, "Poster") == 25
    assert track_count(DATA, "Open Space") == sum(
        1 for s in DATA.sessions.values() if s.track == "Open Space"
    )
    assert "Open Space" in Prefs().excluded_tracks


def test_a_track_without_sessions_is_left_out_and_so_is_an_empty_group() -> None:
    sessions = {
        k: s
        for k, s in DATA.sessions.items()
        if s.track not in {"Open Space", "Summit", "Event"}
    }
    groups = hub_groups(INFO, replace(DATA, sessions=sessions))
    assert [title for title, _ in groups] == ["Presentations", "Hands-on"]
    assert hub_groups(INFO, replace(DATA, sessions={})) == ()


def test_a_row_reads_as_one_phrase_with_its_badge_and_count() -> None:
    """D-33: what the row shows, in its order."""
    assert hub_phrase(HubEntry(track("charlas"), 16)) == (
        "Charlas. Talks given in Spanish. Charla, 16 sessions."
    )


def test_a_new_track_says_so_after_its_badge() -> None:
    assert hub_phrase(HubEntry(track("ai"), 1)) == (
        "Future of AI with Python. A dedicated track on AI: machine learning, LLMs and "
        "more. AI, New track, 1 session."
    )


def test_a_badge_that_repeats_the_name_is_not_read_twice() -> None:
    """Lightning talks' badge says "Lightning talks", as its name does."""
    assert hub_phrase(HubEntry(track("lightning-talks"), 4)) == (
        "Lightning talks. Five-minute talks, back to back. 4 sessions."
    )


def test_a_track_page_shares_its_badge_and_the_charlas_en_espanol() -> None:
    """D-199: what every row would repeat, the intro shows once."""
    charlas = track_sessions(DATA, "Charla")
    assert track_screen.shared_badges(track("charlas"), charlas) == {
        "Charla",
        "En Español",
    }
    keynotes = track_sessions(DATA, "Keynote")  # one keynote of several is in Spanish
    assert track_screen.shared_badges(track("keynotes"), keynotes) == {"Keynote"}
    assert track_screen.shared_badges(track("charlas"), ()) == {"Charla"}


# ------------------------------------------------------------------ the screens


type Show = Callable[..., Awaitable[Shown]]


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return show(screen, conference=...): that screen rendered over the feed."""
    async with AsyncExitStack() as stack:

        async def render(
            screen: Callable[[], ft.Control], conference: Conference | None = None
        ) -> Shown:
            return await stack.enter_async_context(
                showing(
                    screen,
                    hub_screen,
                    track_screen,
                    year=YEAR,
                    conference=conference
                    or Conference(data=DATA, source="bundled", version=1),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path="/more/tracks/charlas",
                )
            )

        yield render


def page_of(slug: str) -> Callable[[], ft.Control]:
    return lambda: track_screen.TrackDetail(slug)


async def test_the_hub_has_a_row_per_track_that_pushes_its_page(show: Show) -> None:
    shown = await show(hub_screen.Tracks)
    slugs = [
        str(n.identifier).removeprefix("tracks.track.")
        for n in shown.nodes("tracks.track.")
    ]
    expected = [e.track.slug for _, entries in hub_groups(INFO, DATA) for e in entries]
    assert sorted(slugs) == sorted(expected)
    node = shown.node("tracks.track.charlas")
    assert node.button and node.exclude_semantics
    assert node.label == "Charlas. Talks given in Spanish. Charla, 16 sessions."
    await shown.click(cast(ft.Control, node.parent))
    assert shown.went == ["/more/tracks/charlas"]
    assert shown.titles[-1] == "Tracks & session types"


async def test_the_keynotes_row_counts_the_panels_its_page_lists(show: Show) -> None:
    """D-199's rule, D-217: the Keynotes page lists the four keynotes and the two
    panels, which the feed calls plenaries; the row opens it under the hub (D-207)."""
    shown = await show(hub_screen.Tracks)
    node = shown.node("tracks.track.keynotes")
    assert node.label == (
        "Keynotes. Featured talks and panels by invited speakers. Keynote, 6 sessions."
    )
    await shown.click(cast(ft.Control, node.parent))
    assert shown.went == ["/more/tracks/keynotes"]


@pytest.mark.parametrize(
    "slug", ["lightning-talks", "open-spaces", "talks", "keynotes"]
)
async def test_every_track_row_pushes_its_slug_under_the_hub(
    show: Show, slug: str
) -> None:
    """ux.md §5.10, D-207: one rule for every row; the route table opens the
    keynotes', lightning talks' and open spaces' own pages at their slugs, and Back
    from any of them returns to the hub (D-17)."""
    shown = await show(hub_screen.Tracks)
    await shown.click(cast(ft.Control, shown.node(f"tracks.track.{slug}").parent))
    assert shown.went == [f"/more/tracks/{slug}"]
    assert parent_of(f"/more/tracks/{slug}") == "/more/tracks"


def test_each_hub_page_of_a_track_is_at_that_tracks_slug() -> None:
    """The hub row of a track with a page of its own opens that page (D-207)."""
    for segment, key in HUB_PAGES.items():
        assert f"/more/tracks/{segment}" in PAGES
        assert f"/more/{segment}" in PAGES, segment  # its More entry (D-207)
        if key is not None:
            assert INFO.track(key).slug == segment, key
    assert parent_of(hub_screen.SPRINTS) == "/more/tracks"


async def test_the_sections_are_headings_of_their_own(show: Show) -> None:
    """F40: a heading needs its level to be one for screen readers."""
    shown = await show(hub_screen.Tracks)
    headings = [
        (text_of(n), n.heading_level) for n in shown.find(ft.Semantics) if n.header
    ]
    assert headings == [("Presentations", 2), ("Hands-on", 2), ("Community", 2)]


async def test_only_the_new_tracks_carry_the_new_badge(show: Show) -> None:
    shown = await show(hub_screen.Tracks)
    assert shown.texts().count("New track") == 2
    assert "AI, New track" in str(shown.node("tracks.track.ai").label)
    assert "Security, New track" in str(shown.node("tracks.track.security").label)
    assert "New track" not in str(shown.node("tracks.track.talks").label)


async def test_the_hub_without_data_loads_then_offers_to_try_again(show: Show) -> None:
    """ux.md §4.1: the skeleton until the first fetch has failed, then the way out."""
    loading = await show(hub_screen.Tracks, Conference())
    assert "Loading tracks" in [n.label for n in loading.find(ft.Semantics)]
    failed = await show(hub_screen.Tracks, Conference(problem="offline"))
    assert failed.node("tracks.no_data").live_region
    assert [b.content for b in failed.find(ft.FilledTonalButton)] == ["Try again"]


async def test_a_feed_without_sessions_says_none_are_announced(show: Show) -> None:
    data = replace(DATA, sessions={})
    shown = await show(hub_screen.Tracks, Conference(data=data, version=1))
    assert shown.node("tracks.none").live_region
    assert shown.nodes("tracks.track.") == []


async def test_the_posters_page_lists_each_poster_not_the_posters_row(
    show: Show,
) -> None:
    """SCHED-22, D-178: Ionic listed both."""
    shown = await show(page_of("posters"))
    listed = [str(n.identifier) for n in shown.nodes("track.session.")]
    posters = [s for d in track_sessions(DATA, "Poster") for s in d.sessions]
    assert len(listed) == len(posters) == 25
    assert listed == [f"track.session.{semantics_key(s.id)}" for s in posters]
    assert all(s.in_timeline is False for s in posters)


async def test_open_spaces_show_on_their_page_whatever_the_filter(show: Show) -> None:
    """D-20: the Schedule hides them by default; their own page never does."""
    shown = await show(page_of("open-spaces"))
    expected = sum(1 for s in DATA.sessions.values() if s.track == "Open Space")
    assert len(shown.nodes("track.session.")) == expected
    assert len(shown.nodes("track.favorite.")) == expected  # each with its star


async def test_sessions_are_under_a_level_2_heading_per_day(show: Show) -> None:
    shown = await show(page_of("charlas"))
    days = track_sessions(DATA, "Charla")
    headings = [
        text_of(n)
        for n in shown.find(ft.Semantics)
        if n.header and n.heading_level == 2
    ]
    assert headings == [day_heading(d.day) for d in days]


async def test_the_intro_shows_the_badge_the_new_mark_and_the_legend(
    show: Show,
) -> None:
    ai = await show(page_of("ai"))
    assert {"AI", "New track", track("ai").legend} <= set(ai.texts())
    talks = await show(page_of("talks"))
    assert "New track" not in talks.texts()


async def test_rows_leave_out_the_badges_the_intro_shows(show: Show) -> None:
    """D-199, as D-186 leaves out a badge that repeats the title: once, not per row."""
    charlas = await show(page_of("charlas"))
    rows = charlas.nodes("track.session.")
    assert len(rows) == 16
    assert charlas.texts().count("Charla") == 1  # the intro's
    assert charlas.texts().count("En Español") == 1
    for row in rows:
        label = str(row.label)
        assert not label.startswith(("Charla", "En Español")), label
    # Another track's flag stays on its rows: the tutorials need registration.
    tutorials = await show(page_of("tutorials"))
    rows = tutorials.nodes("track.session.")
    assert rows and all(
        str(row.label).startswith("Registration required. ") for row in rows
    )
    assert tutorials.texts().count("Tutorial") == 1


async def test_the_tracks_name_is_the_pages_heading_not_the_app_bars(
    show: Show,
) -> None:
    """D-186's pattern: a heading in the body wraps where an app bar title is cut."""
    shown = await show(page_of("security"))
    title = shown.node("track.title")
    assert title.header and title.heading_level == 1
    assert cast(ft.Text, title.content).value == "Trailblazing Python Security"
    assert shown.titles[-1] == ""


@pytest.mark.parametrize("slug", ["ais", "lightning-talkss", "Charlas", "python"])
async def test_an_unknown_slug_shows_not_found_with_the_way_to_all_tracks(
    show: Show, slug: str
) -> None:
    """DATA-29, D-186: on its own level under the back arrow, never a redirect."""
    shown = await show(page_of(slug))
    assert shown.node("track.not_found").live_region
    assert track_screen.NOT_FOUND in shown.texts()
    assert shown.titles[-1] == "Not found"
    assert shown.went == []
    (button,) = shown.find(ft.FilledTonalButton)
    await shown.click(button)
    assert shown.went == ["/more/tracks"]


async def test_a_track_without_sessions_in_the_feed_says_so(show: Show) -> None:
    sessions = {k: s for k, s in DATA.sessions.items() if s.track != "Charla"}
    data = replace(DATA, sessions=sessions)
    shown = await show(page_of("charlas"), Conference(data=data, version=1))
    assert shown.node("track.empty").live_region
    assert shown.nodes("track.session.") == []


async def test_a_track_page_without_data_offers_to_try_again(show: Show) -> None:
    shown = await show(page_of("charlas"), Conference(problem="server"))
    assert shown.node("track.no_data").live_region
    assert "Charla" in shown.texts()  # the intro needs no feed


async def test_a_star_tap_re_renders_one_day_and_one_row(
    show: Show, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-153: the day items and rows are memoised, so only the tapped ones run."""
    days_run: list[date] = []
    heading = day_groups.day_heading

    def counted_heading(day: date) -> str:
        days_run.append(day)
        return heading(day)

    # Each day body names its day once: counting the calls counts the bodies.
    monkeypatch.setattr(day_groups, "day_heading", counted_heading)
    shown = await show(page_of("charlas"))
    first_day = track_sessions(DATA, "Charla")[0]
    first = first_day.sessions[0]
    star = shown.node(f"track.favorite.{semantics_key(first.id)}")
    shown.rows.clear()
    days_run.clear()
    await shown.click(cast(ft.IconButton, star.content))
    assert first.id in shown.favorites.ids
    assert shown.rows == [first.id]
    assert days_run == [first_day.day]


async def test_a_row_pushes_the_session_one_level_down(show: Show) -> None:
    shown = await show(page_of("charlas"))
    first = track_sessions(DATA, "Charla")[0].sessions[0]
    node = shown.node(f"track.session.{semantics_key(first.id)}")
    await shown.click(cast(ft.Control, node.parent))
    assert shown.went == [f"/more/tracks/charlas/session/{first.id}"]
