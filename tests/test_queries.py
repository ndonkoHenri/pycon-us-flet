"""Tests for the queries over the processed feed (DATA-17; architecture §7.5)."""

from datetime import date
from typing import Any

import pytest

from pycon_us.config import load_year
from pycon_us.core.feed import process
from pycon_us.core.queries import by_day, days, fold, session_view, session_views
from tests.feeds import YEARS, changed, processed, settings

pytestmark = pytest.mark.usefixtures("machine_tz")


def test_2026_days_run_from_tutorials_to_the_last_sprint_day() -> None:
    """DATA-17: the two sprint days have no sessions in the feed but get a day."""
    conference = load_year(2026).conference
    assert days(processed(2026), conference.first_day, conference.last_day) == tuple(
        date(2026, 5, d) for d in range(13, 20)
    )


@pytest.mark.parametrize("year", YEARS)
def test_every_schedule_day_is_one_of_the_days(year: int) -> None:
    conference = load_year(year).conference
    result = days(processed(year), conference.first_day, conference.last_day)
    assert {day.date for day in processed(year).days} <= set(result)
    assert list(result) == sorted(set(result))
    assert (result[0], result[-1]) == (conference.first_day, conference.last_day)


def test_a_session_outside_the_conference_dates_widens_the_days() -> None:
    def early(doc: dict[str, Any]) -> None:
        doc["schedule"][5].update(
            start="2026-05-11T09:00:00-07:00", end="2026-05-11T10:00:00-07:00"
        )

    data = process(changed(2026, early), settings(2026))
    conference = load_year(2026).conference
    result = days(data, conference.first_day, conference.last_day)
    assert result[:3] == (date(2026, 5, 11), date(2026, 5, 12), date(2026, 5, 13))


@pytest.mark.parametrize(
    ("text", "folded"),
    [
        ("Cristián", "cristian"),
        ("ÜBER Python", "uber python"),
        ("Straße", "strasse"),  # case folding, not just lower-casing
        ("ﬁle", "file"),  # NFKD splits the ligature
    ],
)
def test_fold_ignores_case_and_accents(text: str, folded: str) -> None:
    """D-46: search and the Speakers sort compare folded text."""
    assert fold(text) == folded


# ------------------------------------------------------------------ row views (SCHED-03)

ZONE_2026 = load_year(2026).conference.zone


def test_a_row_view_has_the_range_place_and_speakers_a_row_shows() -> None:
    view = session_view(processed(2026).sessions["142"], ZONE_2026, use_24h=False)
    assert view.when == "10:30–11:00 AM"
    assert view.place == "Grand Ballroom A"
    assert view.speakers == "Justin Lee"


def test_a_screen_reader_hears_to_in_place_of_the_range_s_dash() -> None:
    view = session_view(processed(2026).sessions["142"], ZONE_2026, use_24h=False)
    assert view.spoken_when == "10:30 to 11:00 AM"


def test_a_row_view_follows_the_device_s_24_hour_clock() -> None:
    view = session_view(processed(2026).sessions["142"], ZONE_2026, use_24h=True)
    assert (view.when, view.spoken_when) == ("10:30–11:00", "10:30 to 11:00")


def test_a_notice_shows_one_time_and_a_generic_break_no_place() -> None:
    sessions = processed(2026).sessions
    notice = session_view(sessions["196"], ZONE_2026, use_24h=False)
    assert notice.when == "7:30 AM"  # Registration Desk Opens: start equals end
    generic = session_view(
        sessions["break--2026-05-17T10:00:00-07:00"], ZONE_2026, use_24h=False
    )
    assert (generic.when, generic.place) == ("10:00 AM–12:00 PM", "")


def test_the_job_fair_row_shows_its_displayed_start() -> None:
    """DATA-11: grouped at 10:00, it opens at 9:30."""
    view = session_view(processed(2026).sessions["178"], ZONE_2026, use_24h=False)
    assert view.when == "9:30 AM–1:00 PM"


def test_pseudo_speakers_show_on_the_speakers_line() -> None:
    """DATA-15: the lightning talks' hosts are text, not directory speakers."""
    view = session_view(processed(2026).sessions["175"], ZONE_2026, use_24h=False)
    assert view.speakers == "Hosted by Abigail, Chris, Cristián, and Lorena"


def test_row_views_keep_the_list_s_order_and_skip_unknown_ids() -> None:
    views = session_views(
        processed(2026), ["74", "gone", "142"], ZONE_2026, use_24h=False
    )
    assert [view.session.id for view in views] == ["74", "142"]


def test_views_group_by_their_conference_local_day_in_order() -> None:
    """A speaker's rows go under a heading per day: a row says only its time."""
    sessions = processed(2026).sessions
    views = [
        session_view(sessions[i], ZONE_2026, use_24h=False) for i in ("19", "142", "76")
    ]
    grouped = [
        (day, [v.session.id for v in group]) for day, group in by_day(views, ZONE_2026)
    ]
    assert grouped == [
        (date(2026, 5, 13), ["19"]),
        (date(2026, 5, 16), ["142", "76"]),
    ]
