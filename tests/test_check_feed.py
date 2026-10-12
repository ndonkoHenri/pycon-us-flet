"""Tests for ``tools/check_feed.py``, the weekly live-feed check (D-77, D-84; DEV-08).

The feeds come from an ``httpx.MockTransport`` serving the recorded 2026 feed, a broken
copy of it or an error, never the network. The last tests show each invariant of
``tools/feed_invariants.py`` failing on a broken model, so none can silently always pass.
"""

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, timedelta
from typing import Any

import httpx
import pytest

from pycon_us.config import load_year
from pycon_us.core.models import ConferenceData, Session
from tests.feeds import changed, document, recorded, recorded_feed
from tools import feed_invariants
from tools.check_feed import main, new_keys
from tools.feed_invariants import ProcessedFeed

FEED_2026 = "https://us.pycon.org/2026/schedule/conference.json"
FEED_2027 = "https://us.pycon.org/2027/schedule/conference.json"
NOT_FOUND = httpx.Response(404, text="<html>Page not found</html>")

type Answer = httpx.Response | Exception


def serving(answers: dict[str, Answer]) -> httpx.MockTransport:
    """A transport that answers each URL as given and fails any other request."""

    def handle(request: httpx.Request) -> httpx.Response:
        answer = answers[str(request.url)]
        if isinstance(answer, Exception):
            raise answer
        return answer

    return httpx.MockTransport(handle)


def check(
    capsys: pytest.CaptureFixture[str],
    feed: Answer,
    next_year: Answer = NOT_FOUND,
) -> tuple[int, str]:
    """Run the check on 2026 with these answers; return its status and output."""
    status = main([], transport=serving({FEED_2026: feed, FEED_2027: next_year}))
    return status, capsys.readouterr().out


def ok(body: bytes) -> httpx.Response:
    return httpx.Response(200, content=body)


def first_talk(doc: dict[str, Any]) -> dict[str, Any]:
    return next(slot for slot in doc["schedule"] if slot["kind"] == "talk")


def test_the_recorded_feed_passes_and_a_missing_next_year_is_not_yet(
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, out = check(capsys, ok(recorded(2026)))

    assert status == 0
    assert "10 of 10 invariants hold" in out
    assert "no key the recorded feeds lack" in out
    assert f"2027: not published yet (HTTP 404 at {FEED_2027})" in out
    assert out.endswith("Feed check passed\n")


def test_a_feed_that_breaks_an_invariant_fails_and_names_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def move_a_talk_out_of_the_conference(doc: dict[str, Any]) -> None:
        talk = first_talk(doc)
        talk["start"], talk["end"] = (
            "2026-06-01T10:00:00-07:00",
            "2026-06-01T10:30:00-07:00",
        )
        talk["conf_key"] = 424242

    status, out = check(capsys, ok(changed(2026, move_a_talk_out_of_the_conference)))

    assert status == 1
    assert "FAILED: every session is on one conference day" in out
    assert "424242 is on 2026-06-01, outside the conference" in out
    assert "9 of 10 invariants hold" in out
    assert out.endswith("Feed check FAILED for 2026\n")


def test_a_record_the_parser_skips_fails_the_check(
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, out = check(
        capsys, ok(changed(2026, lambda doc: first_talk(doc).pop("name")))
    )

    assert status == 1
    assert "FAILED: no session is lost" in out
    assert "1 skipped records" in out


def test_a_feed_that_does_not_parse_fails(capsys: pytest.CaptureFixture[str]) -> None:
    status, out = check(capsys, ok(b"<html>Maintenance</html>"))

    assert status == 1
    assert "FAILED, it does not parse" in out


@pytest.mark.parametrize(
    ("answer", "reported"),
    [
        (NOT_FOUND, "FAILED, HTTP 404"),
        (httpx.ConnectError("no route to host"), "FAILED, could not fetch it"),
    ],
)
def test_a_feed_that_cannot_be_fetched_is_reported_not_raised(
    capsys: pytest.CaptureFixture[str], answer: Answer, reported: str
) -> None:
    status, out = check(capsys, answer)

    assert status == 1
    assert f"2026: {FEED_2026}\n  {reported}" in out


@pytest.mark.parametrize(
    ("answer", "reported"),
    [
        (ok(recorded(2026)), f"2027: PUBLISHED at {FEED_2027} with "),
        (
            ok(b"<html>Coming soon</html>"),
            f"2027: HTTP 200 at {FEED_2027}, but not a feed",
        ),
        (httpx.Response(503), f"2027: HTTP 503 at {FEED_2027}"),
        (httpx.ReadTimeout("timed out"), f"2027: could not fetch {FEED_2027}"),
    ],
)
def test_next_years_feed_is_reported_without_failing_the_check(
    capsys: pytest.CaptureFixture[str], answer: Answer, reported: str
) -> None:
    status, out = check(capsys, ok(recorded(2026)), next_year=answer)

    assert status == 0
    assert reported in out


def test_next_year_redirected_to_this_years_feed_is_not_published(
    capsys: pytest.CaptureFixture[str],
) -> None:
    moved = httpx.Response(302, headers={"location": FEED_2026})

    status, out = check(capsys, ok(recorded(2026)), next_year=moved)

    assert status == 0
    assert (
        f"2027: {FEED_2027} redirects to {FEED_2026} (HTTP 302); not published yet"
        in out
    )
    assert "PUBLISHED" not in out


def test_keys_the_recorded_feeds_lack_are_printed_not_failed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def grow(doc: dict[str, Any]) -> None:
        first_talk(doc)["captions_url"] = "https://example.org/captions"
        doc["badges"] = []

    status, out = check(capsys, ok(changed(2026, grow)))

    assert status == 0
    assert "keys the recorded feeds lack (ignored): (top level): badges" in out
    assert "schedule: captions_url" in out


def test_new_keys_compares_sections_and_their_records() -> None:
    grown = document(2026)
    first_talk(grown)["captions_url"] = "https://example.org/captions"
    grown["badges"] = []

    assert new_keys(document(2026), [document(2026)]) == []
    assert new_keys(grown, [document(2025), document(2026)]) == [
        "(top level): badges",
        "schedule: captions_url",
    ]


def test_each_year_given_is_checked(capsys: pytest.CaptureFixture[str]) -> None:
    status = main(["2026", "2027"], transport=serving({FEED_2026: ok(recorded(2026))}))
    out = capsys.readouterr().out

    assert status == 1
    assert "2026: " in out and "  OK\n" in out
    assert "2027: FAILED, no usable year data: 2027/conference.toml" in out
    assert "not published yet" not in out  # 2027 was asked for, so it is not probed


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
