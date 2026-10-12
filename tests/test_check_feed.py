"""Tests for ``tools/check_feed.py``, the weekly live-feed check (D-77, D-84; DEV-08).

The feeds come from an ``httpx.MockTransport`` serving the recorded 2026 feed, a broken
copy of it or an error, never the network.
"""

import dataclasses
import json
from typing import Any

import httpx
import pytest

from pycon_us.config import load_year
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
    """The invariants guard the fixtures only if they can fail: two of them, broken."""
    feed = recorded_feed(2026)
    # The JSON has a slot the model never saw.
    more = json.loads(json.dumps(feed.document))
    more["schedule"].append(dict(first_talk(more), conf_key=777777))
    assert feed_invariants.no_session_is_lost(
        dataclasses.replace(feed, document=more)
    ) == ["slots neither a session nor dropped: 777777"]
    # Without its override, the Job Fair's earlier displayed start is unexpected.
    year = load_year(2026)
    bare = dataclasses.replace(
        year, content=dataclasses.replace(year.content, display_time_overrides=())
    )
    problems = feed_invariants.only_overridden_sessions_show_another_start(
        ProcessedFeed(feed.raw, feed.document, feed.data, bare)
    )
    assert problems == ["178 is shown at another time than expected"]
