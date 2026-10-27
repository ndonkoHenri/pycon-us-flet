"""Tests for the Now tab's header words (#95; SCHED-25, SCHED-26; D-14, D-179).

What is on and what is next is ``core.agenda`` (``test_agenda.py``); here, what Now says
of it at fixed times of the 2026 feed: the header's words in every season. The words are
pure (``season()``, ``header_copy()``, ``up_next_when()``) and run on their own. The
screen is ``test_now_screen.py``'s and ``test_now_card.py``'s, over
``tests/now_view.py``'s harness. How Now looks, wraps at 200 % and reads to TalkBack and
VoiceOver is checked on devices (the PR).
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import flet as ft
import pytest

from pycon_us.core.agenda import Phase, now_next
from pycon_us.core.models import ConferenceData
from pycon_us.screens.now_header import (
    GOLD,
    HeaderCopy,
    Season,
    StatusHeader,
    header_copy,
    header_phrase,
    season,
    spoken,
    up_next_when,
)
from tests import now_view
from tests.now_view import INFO, PACIFIC, _walk, may
from tests.test_theme import contrast_ratio

data = now_view.data


# ------------------------------------------------------------------ the words


def copy_at(data: ConferenceData, now: datetime, **kwargs: Any) -> tuple[str, ...]:
    """The header's season, title and subtitle at ``now``, on a Pacific device."""
    copy = header_copy(
        now_next(data, now),
        now,
        data,
        INFO,
        use_24h=kwargs.get("use_24h", False),
        device_offset=now.astimezone(PACIFIC).utcoffset(),
    )
    assert copy.note is None  # the device shows conference time
    return copy.season, copy.title, copy.subtitle


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (
            datetime(2026, 4, 20, 9, tzinfo=PACIFIC),
            (Season.COUNTDOWN, "Starts in 23 days", "May 13–19 · Long Beach, CA"),
        ),
        (
            may(12, 23, 59),
            (Season.COUNTDOWN, "Starts tomorrow", "May 13–19 · Long Beach, CA"),
        ),
        # The first morning, before its first start: already the conference.
        (
            may(13, 7),
            (
                Season.CONFERENCE,
                "Day 1 of 5 · Wednesday",
                "First up today at 7:30 AM",
            ),
        ),
        (
            may(15, 6),
            (Season.CONFERENCE, "Day 3 of 5 · Friday", "First up today at 7:30 AM"),
        ),
        # While the day runs, when its next slot starts (D-366).
        (
            may(15, 11, 10),
            (Season.CONFERENCE, "Day 3 of 5 · Friday", "Up next at 11:30 AM"),
        ),
        # The day's last slot: nothing more starts today, so the venue.
        (
            may(14, 18, 30),
            (
                Season.CONFERENCE,
                "Day 2 of 5 · Thursday",
                "Long Beach Convention Center",
            ),
        ),
        (
            may(15, 21),
            (Season.CONFERENCE, "Day 3 of 5 · Friday", "That's a wrap for today"),
        ),
        # After the last end, the last evening is still the last day.
        (
            may(17, 21),
            (Season.CONFERENCE, "Day 5 of 5 · Sunday", "That's a wrap for today"),
        ),
        (
            may(18, 10),
            (
                Season.SPRINTS,
                "Sprints · Monday",
                "The sprints run until Tuesday, May 19",
            ),
        ),
        (
            may(19, 10),
            (Season.SPRINTS, "Sprints · Tuesday", "The last day of the sprints"),
        ),
        (
            may(25, 10),
            (Season.OVER, "See you next year", "Thanks for coming."),
        ),
    ],
)
def test_the_header_says_where_the_conference_stands(
    data: ConferenceData, now: datetime, expected: tuple[str, ...], machine_tz: str
) -> None:
    """The header's season, title and subtitle, from the countdown to the end."""
    assert copy_at(data, now) == expected


def test_the_seasons_follow_the_phases_and_the_year_s_dates(
    data: ConferenceData,
) -> None:
    """The season follows the phase and the year's conference and sprint dates.

    The conference starts on its first morning and lasts until the last evening; the
    sprints follow, then it is over.
    """
    assert season(Phase.BEFORE, may(12, 12).date(), data, INFO) is Season.COUNTDOWN
    assert season(Phase.BEFORE, may(13, 7).date(), data, INFO) is Season.CONFERENCE
    for phase in (Phase.BEFORE_DAY, Phase.DAY, Phase.AFTER_DAY):
        assert season(phase, may(15, 12).date(), data, INFO) is Season.CONFERENCE
    assert season(Phase.AFTER, may(17, 23).date(), data, INFO) is Season.CONFERENCE
    assert season(Phase.AFTER, may(18, 0).date(), data, INFO) is Season.SPRINTS
    assert season(Phase.AFTER, may(19, 23).date(), data, INFO) is Season.SPRINTS
    assert season(Phase.AFTER, may(20, 0).date(), data, INFO) is Season.OVER


def test_the_first_start_follows_the_device_s_clock_format(
    data: ConferenceData,
) -> None:
    """On a 24-hour device, the first start reads ``07:30``, and the next ``11:30``."""
    _, _, subtitle = copy_at(data, may(15, 6), use_24h=True)
    assert subtitle == "First up today at 07:30"
    _, _, subtitle = copy_at(data, may(15, 11, 10), use_24h=True)
    assert subtitle == "Up next at 11:30"


def test_the_header_names_pacific_time_on_a_device_elsewhere(
    data: ConferenceData,
) -> None:
    """On a device in another zone, the header notes that times are Pacific Time."""
    now = may(15, 11, 10)
    kiritimati = now.astimezone(ZoneInfo("Pacific/Kiritimati")).utcoffset()
    copy = header_copy(
        now_next(data, now), now, data, INFO, use_24h=False, device_offset=kiritimati
    )
    assert copy.note == "Times are Pacific Time (PDT)"


@pytest.mark.parametrize(
    "now",
    [datetime(2026, 4, 20, 9, tzinfo=PACIFIC), may(18, 10), may(25, 10)],
    ids=["countdown", "sprints", "over"],
)
def test_the_zone_note_shows_only_in_the_season_with_times(
    data: ConferenceData, now: datetime
) -> None:
    """The countdown, the sprints and the end show dates only: no zone to name."""
    kiritimati = now.astimezone(ZoneInfo("Pacific/Kiritimati")).utcoffset()
    copy = header_copy(
        now_next(data, now), now, data, INFO, use_24h=False, device_offset=kiritimati
    )
    assert copy.season is not Season.CONFERENCE
    assert copy.note is None


def test_a_screen_reader_hears_pauses_and_ranges_in_words() -> None:
    """Spoken, a middle dot is a comma pause and a dash between dates is "to"."""
    assert spoken("Up next · 11:30 AM") == "Up next, 11:30 AM"
    assert spoken("Join a project · May 18–19") == "Join a project, May 18 to 19"
    assert spoken("Wed, May 13 – Sun, May 17") == "Wed, May 13 to Sun, May 17"


def test_the_header_reads_as_one_phrase(data: ConferenceData) -> None:
    """The header reads as one phrase: name, title and subtitle, each a sentence."""
    now = datetime(2026, 4, 20, 9, tzinfo=PACIFIC)
    copy = header_copy(
        now_next(data, now),
        now,
        data,
        INFO,
        use_24h=False,
        device_offset=now.utcoffset(),
    )
    assert header_phrase(INFO.name, copy) == (
        "PyCon US 2026. Starts in 23 days. May 13 to 19, Long Beach, CA."
    )


def test_up_next_names_its_day_when_it_is_not_today(data: ConferenceData) -> None:
    """Up next's time says "tomorrow", or the date, when it is not today."""

    def when(now: datetime) -> str:
        slot = now_next(data, now).up_next
        assert slot is not None
        return up_next_when(slot, now, INFO, use_24h=False)

    assert when(may(15, 11, 10)) == "11:30 AM"
    assert when(may(15, 21)) == "tomorrow at 7:00 AM"
    assert when(may(12, 12)) == "tomorrow at 7:30 AM"
    assert when(datetime(2026, 5, 1, 12, tzinfo=PACIFIC)) == "Wed, May 13 at 7:30 AM"


def test_gold_reads_on_the_header_s_indigo() -> None:
    """Gold is for icons on the indigo only: 6.2:1, as ux.md §3.1 computes it."""
    assert contrast_ratio(GOLD, "#3B3EA9") >= 6.0


@pytest.mark.parametrize(
    ("dark", "fill", "ink"),
    [
        (False, ft.Colors.PRIMARY, ft.Colors.ON_PRIMARY),
        # The dark primary is a pale indigo; its container is the brand's (D-190).
        (True, ft.Colors.PRIMARY_CONTAINER, ft.Colors.ON_PRIMARY_CONTAINER),
    ],
)
def test_the_header_is_the_brand_indigo_in_both_schemes(
    dark: bool, fill: ft.Colors, ink: ft.Colors
) -> None:
    """The header is the brand indigo with its ink in each scheme, its icon gold."""
    copy = HeaderCopy(Season.CONFERENCE, "Day 3 of 5 · Friday", "Long Beach")
    header = StatusHeader("PyCon US 2026", copy, dark=dark)
    assert isinstance(header, ft.Semantics)
    card = header.content
    assert isinstance(card, ft.Container)
    assert card.bgcolor == fill
    texts = [c for c in _walk(card) if isinstance(c, ft.Text)]
    assert texts and all(text.color == ink for text in texts)
    (icon,) = [c for c in _walk(card) if isinstance(c, ft.Icon)]
    assert icon.color == GOLD
