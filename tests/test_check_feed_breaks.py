"""Tests that each invariant of the weekly feed check fails on a broken model (D-77, D-84).

An empty list proves nothing about an invariant that cannot fail, so each one is shown
reporting a 2026 model broken for it (``BREAKS``), and two more read the JSON or the
year's data. The check itself is ``test_check_feed.py``'s.
"""

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, timedelta
from typing import Any

import pytest

from pycon_us.config import load_year
from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.sponsors import sponsor_by_slug
from tests.feeds import recorded_feed
from tests.test_check_feed import first_talk
from tools import feed_invariants
from tools.feed_invariants import ProcessedFeed


def test_the_invariants_report_what_they_find() -> None:
    """Two invariants that also read the JSON or the year's data, broken there."""
    feed = recorded_feed(2026)
    # The JSON has a slot the model never saw.
    more = json.loads(json.dumps(feed.document))
    more["schedule"].append(dict(first_talk(more), conf_key=777777))
    assert feed_invariants.no_session_is_lost(replace(feed, document=more)) == [
        "slots neither a session nor dropped: 777777"
    ]
    # Without its override, the Job Fair's earlier displayed start is unexpected.
    year = load_year(2026)
    bare = replace(year, content=replace(year.content, display_time_overrides=()))
    problems = feed_invariants.only_overridden_sessions_show_another_start(
        ProcessedFeed(feed.raw, feed.document, feed.data, bare)
    )
    assert problems == ["178 is shown at another time than expected"]


def with_session(data: ConferenceData, session: Session) -> ConferenceData:
    """``data`` with ``session`` filed under its id, replacing any session there."""
    return replace(data, sessions={**data.sessions, session.id: session})


def with_talk_19(data: ConferenceData, **changes: Any) -> ConferenceData:
    """``data`` with the 09:00 tutorial "All about decorators" changed, still at 19."""
    talk = replace(data.sessions["19"], **changes)
    return replace(data, sessions={**data.sessions, "19": talk})


def with_first_day(data: ConferenceData, **changes: Any) -> ConferenceData:
    """``data`` with its first day, 2026-05-13, changed."""
    return replace(data, days=(replace(data.days[0], **changes), *data.days[1:]))


def without_sessions(data: ConferenceData, ids: set[str]) -> ConferenceData:
    """``data`` without the sessions whose ids are in ``ids``."""
    return replace(
        data, sessions={k: s for k, s in data.sessions.items() if k not in ids}
    )


def without_rows(data: ConferenceData, name: str) -> ConferenceData:
    """``data`` without its collapsed rows called ``name``."""
    rows = feed_invariants.collapsed_rows(data)
    return without_sessions(data, {row.id for row in rows if row.name == name})


def break_called_lunch(data: ConferenceData) -> ConferenceData:
    """``data`` with the Break row of 2026-05-13, a day without lunch, called Lunch."""
    row = data.sessions["break--2026-05-13T12:30:00-07:00"]
    return with_session(data, replace(row, name="Lunch"))


def reversed_9am_rows(data: ConferenceData) -> ConferenceData:
    """``data`` with the five 09:00 rows of 2026-05-13 in reverse order."""
    first, nine, *rest = data.days[0].groups
    nine = replace(nine, session_ids=tuple(reversed(nine.session_ids)))
    return with_first_day(data, groups=(first, nine, *rest))


def reversed_room(data: ConferenceData, slug: str) -> ConferenceData:
    """``data`` with the sessions of room ``slug`` in reverse order."""
    room = data.rooms[slug]
    room = replace(room, session_ids=tuple(reversed(room.session_ids)))
    return replace(data, rooms={**data.rooms, slug: room})


def in_utc(data: ConferenceData) -> ConferenceData:
    """``data`` with the three times of session 19 in UTC: the same moments."""
    talk = data.sessions["19"]
    return with_talk_19(
        data,
        start=talk.start.astimezone(UTC),
        display_start=talk.display_start.astimezone(UTC),
        end=talk.end.astimezone(UTC),
    )


def with_bloomberg_twice(data: ConferenceData) -> ConferenceData:
    """``data`` with a second Bloomberg, as ``BLOOMBERG``, at the end of the last level."""
    bloomberg = sponsor_by_slug(data, "bloomberg")
    assert bloomberg is not None
    *levels, last = data.sponsor_levels
    twin = replace(bloomberg, name="BLOOMBERG", level=last.name)
    last = replace(last, sponsors=(*last.sponsors, twin))
    return replace(data, sponsor_levels=(*levels, last))


def with_empty_top_level(data: ConferenceData) -> ConferenceData:
    """``data`` with its top sponsor level, Visionary, emptied."""
    top, *rest = data.sponsor_levels
    return replace(data, sponsor_levels=(replace(top, sponsors=()), *rest))


def with_mixed_top_level(data: ConferenceData) -> ConferenceData:
    """``data`` with the top level's last sponsor given the next level's order."""
    top, *rest = data.sponsor_levels
    *first, last = top.sponsors
    odd = replace(last, level_order=top.order + 1)
    return replace(data, sponsor_levels=(replace(top, sponsors=(*first, odd)), *rest))


type Invariant = Callable[[ProcessedFeed], list[str]]

BREAKS: list[tuple[Callable[[ConferenceData], ConferenceData], Invariant, str]] = [
    (
        lambda d: without_sessions(d, {"19"}),
        feed_invariants.no_session_is_lost,
        "slots neither a session nor dropped: 19",
    ),
    (
        lambda d: with_talk_19(d, id="1919"),
        feed_invariants.ids_are_unique_stable_strings_in_ionics_forms,
        "session '19' has the id '1919'",
    ),
    (
        lambda d: with_talk_19(d, id="1919"),
        feed_invariants.ids_are_unique_stable_strings_in_ionics_forms,
        "processing the same bytes again gives another outline",
    ),
    (
        lambda d: with_session(d, replace(d.sessions["19"], id="talk-19")),
        feed_invariants.ids_are_unique_stable_strings_in_ionics_forms,
        "id 'talk-19' is in none of Ionic's forms",
    ),
    (
        lambda d: replace(d, days=tuple(reversed(d.days))),
        feed_invariants.every_session_is_on_one_conference_day,
        "the days are not sorted, or repeat a date",
    ),
    (
        lambda d: with_talk_19(d, end=d.sessions["19"].start - timedelta(minutes=1)),
        feed_invariants.times_are_aware_in_the_years_zone_and_ordered,
        "19 ends before it starts",
    ),
    (
        in_utc,
        feed_invariants.times_are_aware_in_the_years_zone_and_ordered,
        "19 has a time outside the conference zone",
    ),
    (
        lambda d: with_first_day(d, groups=tuple(reversed(d.days[0].groups))),
        feed_invariants.every_group_has_a_start_and_ordered_rows,
        "2026-05-13: the groups are not sorted, or repeat a start",
    ),
    (
        reversed_9am_rows,
        feed_invariants.every_group_has_a_start_and_ordered_rows,
        "2026-05-13 09:00: rows not ordered by location, then name",
    ),
    (
        lambda d: with_session(d, replace(d.sessions["19"], id="130")),
        feed_invariants.no_dropped_category_survives,
        "slot 130 (sponsor-workshop) is a session",
    ),
    (
        lambda d: without_rows(d, "Posters"),
        feed_invariants.no_dropped_category_survives,
        "Posters rows missing on 2026-05-17",
    ),
    (
        lambda d: without_rows(d, "Lunch"),
        feed_invariants.one_lunch_row_per_day_with_lunch,
        "Lunch rows missing on 2026-05-14, 2026-05-15, 2026-05-16, 2026-05-17",
    ),
    (
        break_called_lunch,
        feed_invariants.one_lunch_row_per_day_with_lunch,
        "Lunch rows without a Lunch slot on 2026-05-13",
    ),
    (
        lambda d: with_talk_19(
            d, display_start=d.sessions["19"].start + timedelta(minutes=7)
        ),
        feed_invariants.only_overridden_sessions_show_another_start,
        "19 is shown at another time than expected",
    ),
    (
        lambda d: replace(
            d, speakers={k: s for k, s in d.speakers.items() if k != "19"}
        ),
        feed_invariants.speakers_and_sessions_link_both_ways,
        "linked, not in the directory: 19",
    ),
    (
        lambda d: reversed_room(d, "elsewhere"),
        feed_invariants.rooms_and_sessions_agree,
        "room elsewhere's sessions are not by start, then name",
    ),
    (
        with_bloomberg_twice,
        feed_invariants.sponsor_slugs_are_unique,
        "2 sponsors share the slug 'bloomberg'",
    ),
    (
        lambda d: replace(d, sponsor_levels=tuple(reversed(d.sponsor_levels))),
        feed_invariants.sponsor_levels_are_sorted_and_not_empty,
        "the sponsor levels are not sorted by their order",
    ),
    (
        with_empty_top_level,
        feed_invariants.sponsor_levels_are_sorted_and_not_empty,
        "sponsor level 'Visionary' has no sponsor",
    ),
    (
        with_mixed_top_level,
        feed_invariants.sponsor_levels_are_sorted_and_not_empty,
        "sponsor level 'Visionary' also has orders 1",
    ),
    (
        lambda d: replace(
            d,
            job_listings=(
                replace(d.job_listings[0], sponsor_name="Bloomberg L.P."),
                *d.job_listings[1:],
            ),
        ),
        feed_invariants.job_listings_name_a_sponsor,
        "job listing 6 names no sponsor: 'Bloomberg L.P.'",
    ),
]
"""Ways to break the 2026 model, the invariant each breaks, and a problem it reports."""


@pytest.mark.parametrize(
    ("breaking", "invariant", "expected"),
    BREAKS,
    ids=[expected for *_, expected in BREAKS],
)
def test_each_invariant_reports_a_model_that_breaks_it(
    breaking: Callable[[ConferenceData], ConferenceData],
    invariant: Invariant,
    expected: str,
) -> None:
    """An invariant that always returned [] would pass every fixture test."""
    feed = recorded_feed(2026)

    assert expected in invariant(replace(feed, data=breaking(feed.data)))


def test_every_invariant_has_a_way_to_break_it() -> None:
    """Each invariant the weekly check runs is shown failing in ``BREAKS``."""
    broken = {invariant.__name__ for _, invariant, _ in BREAKS}
    assert broken == {invariant.__name__ for invariant in feed_invariants.INVARIANTS}
