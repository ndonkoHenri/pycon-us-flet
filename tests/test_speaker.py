"""Tests for speaker detail (``screens/speaker.py``; #99, SPKR-03, SESS-12).

The screen runs in a real Flet session under the store providers
(``tests/sessions.py``'s ``showing()``). The rows' co-speaker line is
``session_view(of_speaker=...)``'s, tested in ``tests/test_row_views.py``; the
query, ``speaker_sessions()``, in ``tests/test_speakers.py``. How the page looks, wraps
at 200 % and reads to screen readers, and the Back chain on both platforms, are checked
on devices (the PR).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.speakers import speaker_sessions
from pycon_us.core.timefmt import day_heading
from pycon_us.locations import drill_href, parent_of
from pycon_us.screens import speaker as screen
from pycon_us.state import Conference
from pycon_us.ui import day_groups
from pycon_us.ui.semantics import semantics_key
from tests.feeds import processed
from tests.sessions import Shown, showing, text_of

YEAR = load_year(2026)
DATA = processed(2026)

CATHERINE = "112"
"""Catherine Nelson: a Thursday tutorial with Robert Masson, then Friday's six-person panel."""

JUSTIN = "150"
"""Justin Lee: one talk, given alone."""

VIEW_PATH = f"/now/session/110/speaker/{CATHERINE}"
"""The speaker's View, pushed from the panel she is on, pushed from Now."""


type Show = Callable[..., Awaitable[Shown]]


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return show(speaker_id, conference=...): that speaker's page over the feed."""
    async with AsyncExitStack() as stack:

        async def render(
            speaker_id: str, conference: Conference | None = None
        ) -> Shown:
            return await stack.enter_async_context(
                showing(
                    lambda: screen.SpeakerDetail(speaker_id),
                    screen,
                    year=YEAR,
                    conference=conference
                    or Conference(data=DATA, source="bundled", version=1),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW_PATH,
                )
            )

        yield render


def headings(shown: Shown) -> list[tuple[str, int | None]]:
    return [(text_of(n), n.heading_level) for n in shown.find(ft.Semantics) if n.header]


# ------------------------------------------------------------------ the page


async def test_the_name_is_the_page_s_heading_not_the_app_bar_s(show: Show) -> None:
    """D-186's pattern: a heading in the body wraps where an app bar title is cut."""
    shown = await show(CATHERINE)
    title = shown.node("speaker.title")
    assert title.header and title.heading_level == 1
    assert cast(ft.Text, title.content).value == "Catherine Nelson"
    assert shown.titles[-1] == ""


async def test_the_photo_is_decorative_beside_the_name(show: Show) -> None:
    shown = await show(CATHERINE)
    (avatar,) = shown.find(ft.CircleAvatar)
    assert avatar.radius == screen.PHOTO_RADIUS
    assert avatar.foreground_image_src == DATA.speakers[CATHERINE].photo_url
    assert cast(ft.Semantics, avatar.parent).exclude_semantics


async def test_sessions_come_by_day_before_the_bio_each_a_level_2_heading(
    show: Show,
) -> None:
    """ux.md §5.7: "when do they speak" before the bio; F40: headings need levels."""
    shown = await show(CATHERINE)
    days = speaker_sessions(DATA, CATHERINE)
    assert headings(shown) == [
        ("Catherine Nelson", 1),
        *[(day_heading(day.day), 2) for day in days],
        ("About", 2),
    ]


async def test_each_session_is_a_row_with_its_star(show: Show) -> None:
    shown = await show(CATHERINE)
    keys = [semantics_key(i) for i in ("106", "110")]
    assert [str(n.identifier) for n in shown.nodes("speaker.session.")] == [
        f"speaker.session.{key}" for key in keys
    ]
    assert [str(n.identifier) for n in shown.nodes("speaker.favorite.")] == [
        f"speaker.favorite.{key}" for key in keys
    ]


async def test_rows_name_only_the_co_speakers_shown_and_said(show: Show) -> None:
    """#99's comment: the page names its speaker; a row says who else speaks."""
    shown = await show(CATHERINE)
    talk = str(shown.node("speaker.session.106").label)
    assert talk.endswith(" With Robert Masson.")
    assert "With Robert Masson" in shown.texts()
    for row in shown.nodes("speaker.session."):
        assert "Catherine Nelson" not in str(row.label)
    assert shown.texts().count("Catherine Nelson") == 1  # the heading's


async def test_a_speaker_alone_gets_rows_without_a_speakers_line(show: Show) -> None:
    shown = await show(JUSTIN)
    (row,) = shown.nodes("speaker.session.")
    assert str(row.label).endswith("10:30 to 11:00 AM, Grand Ballroom A.")
    assert shown.texts().count("Justin Lee") == 1
    assert not [t for t in shown.texts() if t.startswith("With ")]


async def test_the_bio_is_the_feed_s_markdown_last(show: Show) -> None:
    """D-116, D-197: one builder for every feed text, its links by the link rule."""
    shown = await show(CATHERINE)
    bio = shown.node("speaker.bio")
    (markdown,) = shown.find(ft.Markdown)
    assert markdown.value == DATA.speakers[CATHERINE].bio_md
    assert markdown.selectable and markdown.on_tap_link is not None
    assert bio.container


async def test_a_speaker_without_a_bio_has_no_about_section(show: Show) -> None:
    speakers = dict(DATA.speakers)
    speakers[JUSTIN] = replace(speakers[JUSTIN], bio="", bio_md="")
    data = replace(DATA, speakers=speakers)
    shown = await show(JUSTIN, Conference(data=data, version=1))
    assert ("About", 2) not in headings(shown)
    assert shown.find(ft.Markdown) == []


async def test_a_placeholder_bio_has_no_about_section(show: Show) -> None:
    """Jelle Zijlstra's 2026 bio is the feed's lone "-"."""
    shown = await show("184")
    assert ("About", 2) not in headings(shown)
    assert shown.find(ft.Markdown) == []


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
    shown = await show(CATHERINE)
    star = shown.node("speaker.favorite.110")
    shown.rows.clear()
    days_run.clear()
    await shown.click(cast(ft.IconButton, star.content))
    assert "110" in shown.favorites.ids
    assert shown.rows == ["110"]
    assert days_run == [DATA.sessions["110"].day]


# ------------------------------------------------------------------ states


async def test_a_speaker_without_sessions_says_so_above_the_bio(show: Show) -> None:
    """ux.md §4.6: a speaker whose sessions all left the feed, as a track page's."""
    ids = {s.id for day in speaker_sessions(DATA, JUSTIN) for s in day.sessions}
    sessions = {k: v for k, v in DATA.sessions.items() if k not in ids}
    shown = await show(JUSTIN, Conference(data=replace(DATA, sessions=sessions)))
    assert shown.node("speaker.empty").live_region
    assert screen.NO_SESSIONS in shown.texts()
    assert shown.nodes("speaker.session.") == []
    assert headings(shown)[0] == ("Justin Lee", 1)
    assert headings(shown)[-1] == ("About", 2)


@pytest.mark.parametrize("speaker_id", ["nobody", "", "112 "])
async def test_an_unknown_id_shows_not_found_with_the_way_to_all_speakers(
    show: Show, speaker_id: str
) -> None:
    """D-186: on its own level under the back arrow, never a redirect."""
    shown = await show(speaker_id)
    assert shown.node("speaker.not_found").live_region
    assert screen.NOT_FOUND in shown.texts()
    assert shown.titles[-1] == "Not found"
    assert shown.went == []
    (button,) = shown.find(ft.FilledTonalButton)
    await shown.click(button)
    assert shown.went == ["/more/speakers"]


async def test_without_data_the_page_loads_then_offers_to_try_again(
    show: Show,
) -> None:
    """ux.md §4.1: the skeleton until the first fetch has failed, then the way out."""
    loading = await show(CATHERINE, Conference())
    assert "Loading schedule" in [n.label for n in loading.find(ft.Semantics)]
    failed = await show(CATHERINE, Conference(problem="offline"))
    assert failed.node("speaker.no_data").live_region
    # No name in the page to head it: the bar's title is its level-1 heading (D-211).
    assert loading.titles[-1] == failed.titles[-1] == "Speaker"
    assert [b.content for b in failed.find(ft.FilledTonalButton)] == ["Try again"]
    assert failed.nodes("speaker.not_found") == []


# ------------------------------------------------------------------ Back (SESS-12)


async def test_a_row_pushes_its_session_one_level_down(show: Show) -> None:
    shown = await show(CATHERINE)
    node = shown.node("speaker.session.106")
    await shown.click(cast(ft.Control, node.parent))
    assert shown.went == [f"{VIEW_PATH}/session/106"]


@pytest.mark.parametrize("root", ["/now", "/schedule", "/my-schedule", "/search"])
def test_session_speaker_session_room_pops_one_step_at_a_time(root: str) -> None:
    """D-17: every cross-link pushes one View, so Back undoes one push at a time."""
    stack = [root]
    for kind, ident in [
        ("session", "110"),
        ("speaker", CATHERINE),
        ("session", "106"),
        ("room", "room-101a"),
    ]:
        stack.append(drill_href(stack[-1], kind, ident))
    location = stack.pop()
    while stack:
        location = parent_of(location, search_base="/schedule")
        assert location == stack.pop()
