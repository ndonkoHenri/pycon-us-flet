"""Tests for what a row says and what Share sends (`core/row_views.py`).

The phrases a screen reader hears for a row (D-200) and the text session detail's Share
sends (NEW-06), both built from a row's view.

The views themselves are tested in `test_row_views.py`, whose conference zone these
tests share.
"""

from dataclasses import replace

import pytest

from pycon_us.config import load_year
from pycon_us.core.row_views import (
    SessionView,
    elapsed_phrase,
    notice_phrase,
    session_view,
    share_text,
    spoken_phrase,
)
from tests.feeds import processed
from tests.test_row_views import ZONE_2026

pytestmark = pytest.mark.usefixtures("machine_tz")


# ------------------------------------------------------------------ spoken phrases

TALK = "142"
"""A talk with one speaker: "Python for Humans - …", 10:30-11:00 AM, Grand Ballroom A."""

TUTORIAL = "19"
"""A tutorial that needs registration."""

NOTICE = "196"
"""Registration Desk Opens, 7:30 AM: a notice with a description."""

COFFEE = "break-Expo Hall AB-2026-05-15T08:00:00-07:00"
"""A collapsed break with nothing to read."""


def view_of(session_id: str) -> SessionView:
    """The 2026 session's row view, on a 12-hour clock."""
    return session_view(processed(2026).sessions[session_id], ZONE_2026, use_24h=False)


def test_the_phrase_names_every_badge_and_skips_what_is_missing() -> None:
    """The phrase says the badges, title, time, place and speakers, skipping blanks."""
    view = view_of(TUTORIAL)
    phrase = spoken_phrase(["Tutorial", "Registration required"], view)
    assert phrase == (
        "Tutorial, Registration required. All about decorators. "
        "9:00 AM to 12:30 PM, Room 101B. Reuven M. Lerner."
    )
    no_speakers = spoken_phrase(["Break"], view_of(COFFEE))
    assert no_speakers == "Break. Coffee. 8:00 to 9:00 AM, Expo Hall AB."


def test_a_phrase_without_its_time_keeps_its_place() -> None:
    """The Posters detail says the time above its rows (D-206); a place would stay."""
    view = view_of(TUTORIAL)
    phrase = spoken_phrase(["Tutorial"], view, show_time=False)
    assert phrase == "Tutorial. All about decorators. Room 101B. Reuven M. Lerner."
    no_place = spoken_phrase([], replace(view, place=""), show_time=False)
    assert no_place == "All about decorators. Reuven M. Lerner."


def test_a_notice_reads_as_its_kind_name_and_time() -> None:
    """ux.md §3.9: "Notice. Registration opens, 7:00 AM"."""
    phrase = notice_phrase("Notice", view_of(NOTICE))
    assert phrase == "Notice. Registration Desk Opens, 7:30 AM."


def test_a_row_that_is_on_says_how_much_has_passed_last() -> None:
    """Now's elapsed bar is said in the row's phrase, as a sentence of its own (#95)."""
    assert elapsed_phrase(60) == "60 percent elapsed."
    assert elapsed_phrase(0) == "0 percent elapsed."


def test_a_title_that_ends_a_sentence_gets_no_second_full_stop() -> None:
    """A title ending in a question mark gets no full stop after it."""
    view = view_of(TALK)
    asked = replace(
        view, session=replace(view.session, name="Is Python fast?"), place=""
    )
    assert spoken_phrase([], asked) == "Is Python fast? 10:30 to 11:00 AM. Justin Lee."


# ------------------------------------------------------------------ Share (NEW-06)

CONFERENCE = load_year(2026).conference.name


def shared(session_id: str, *, use_24h: bool = False) -> list[str]:
    """The lines Share sends for a 2026 session."""
    session = processed(2026).sessions[session_id]
    return share_text(session, CONFERENCE, ZONE_2026, use_24h=use_24h).split("\n")


def test_a_talk_shares_its_title_when_and_where_and_its_public_page() -> None:
    """A talk shares its title, its day, time and room, and its page's URL."""
    assert shared(TALK) == [
        "Python for Humans - Designing Python Code Like a User Interface",
        "PyCon US 2026 · Saturday, May 16, 10:30–11:00 AM PDT · Grand Ballroom A",
        "https://us.pycon.org/2026/schedule/presentation/142/",
    ]


def test_the_shared_time_follows_the_device_s_24_hour_clock() -> None:
    """The shared time is on the 24-hour clock when the device's is."""
    assert shared(TALK, use_24h=True)[1] == (
        "PyCon US 2026 · Saturday, May 16, 10:30–11:00 PDT · Grand Ballroom A"
    )


@pytest.mark.parametrize(
    "session_id",
    [
        COFFEE,  # a collapsed break: <kind>-<room>-<start>
        "poster-Expo Hall AB-2026-05-17T09:30:00-07:00",  # the Posters row
        "poster-detail-60",  # a poster
    ],
)
def test_a_synthetic_id_shares_text_without_a_url(session_id: str) -> None:
    """NEW-06: only the site's own sessions have a page to link."""
    lines = shared(session_id)
    assert len(lines) == 2
    assert not any("://" in line for line in lines)


def test_a_session_the_site_has_no_page_for_shares_no_url() -> None:
    """A keynote has a numeric id but no page: a URL built from the id would be dead."""
    assert shared("176") == [
        "amanda casari",
        "PyCon US 2026 · Sunday, May 17, 9:00–9:45 AM PDT · Pacific Ballroom - Arena",
    ]


def test_the_shared_page_is_the_feed_s_own_link_not_one_built_from_the_id() -> None:
    """The lightning talks' id is 175 and their page presentation/177."""
    assert shared("175")[2] == "https://us.pycon.org/2026/schedule/presentation/177/"


def test_an_open_space_shares_its_entry_on_the_open_spaces_page() -> None:
    """An open space shares the anchor of its entry on the site's open spaces page."""
    assert shared("9119")[2] == (
        "https://us.pycon.org/2026/schedule/open-spaces/#OpenSpace-119"
    )


def test_the_shared_time_starts_where_the_detail_s_does() -> None:
    """DATA-11: the Job Fair is grouped at 10:00 and opens at 9:30."""
    assert shared("178")[1] == (
        "PyCon US 2026 · Sunday, May 17, 9:30 AM–1:00 PM PDT · Expo Hall AB"
    )


def test_a_generic_break_and_a_notice_share_no_place() -> None:
    """A break in no room and a notice share their day and time, no place."""
    assert shared("break--2026-05-17T10:00:00-07:00")[1] == (
        "PyCon US 2026 · Sunday, May 17, 10:00 AM–12:00 PM PDT"
    )
    assert shared(NOTICE)[1] == "PyCon US 2026 · Wednesday, May 13, 7:30 AM PDT"
