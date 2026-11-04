"""Tests for `tools/check_feed.py`, the weekly live-feed check (D-77, D-84; DEV-08).

The feeds come from an `httpx.MockTransport` serving the active year's recorded feed, a
broken copy of it or an error, never the network. Each invariant of `tools/feed_invariants.py`
failing on a broken model, so none can silently always pass, is
`test_check_feed_breaks.py`'s.
"""

from typing import Any

import httpx
import pytest

from pycon_us.config import YEAR, load_year
from tests.feeds import changed, document, recorded
from tools.check_feed import main, new_keys

NEXT_YEAR = YEAR + 1
FEED = load_year().conference.feed_url
NEXT_FEED = FEED.replace(f"/{YEAR}/", f"/{NEXT_YEAR}/")
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
    """Run the check on the active year with these answers; return its status and output."""
    status = main([], transport=serving({FEED: feed, NEXT_FEED: next_year}))
    return status, capsys.readouterr().out


def ok(body: bytes) -> httpx.Response:
    """A 200 response carrying `body`."""
    return httpx.Response(200, content=body)


def first_talk(doc: dict[str, Any]) -> dict[str, Any]:
    """The first slot of kind `talk` in a feed document."""
    return next(slot for slot in doc["schedule"] if slot["kind"] == "talk")


def test_the_recorded_feed_passes_and_a_missing_next_year_is_not_yet(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The recorded feed passes, and a 404 for next year reads as not published yet."""
    status, out = check(capsys, ok(recorded(YEAR)))

    assert status == 0
    assert "13 of 13 invariants hold" in out
    assert "no key the recorded feeds lack" in out
    assert f"{NEXT_YEAR}: not published yet (HTTP 404 at {NEXT_FEED})" in out
    assert out.endswith("Feed check passed\n")


def test_a_feed_that_breaks_an_invariant_fails_and_names_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A talk moved off the conference days fails the check, naming the invariant."""

    def move_a_talk_out_of_the_conference(doc: dict[str, Any]) -> None:
        talk = first_talk(doc)
        talk["start"], talk["end"] = (
            f"{YEAR}-06-01T10:00:00-07:00",
            f"{YEAR}-06-01T10:30:00-07:00",
        )
        talk["conf_key"] = 424242

    status, out = check(capsys, ok(changed(YEAR, move_a_talk_out_of_the_conference)))

    assert status == 1
    assert "FAILED: every session is on one conference day" in out
    assert f"424242 is on {YEAR}-06-01, outside the conference" in out
    assert "12 of 13 invariants hold" in out
    assert out.endswith(f"Feed check FAILED for {YEAR}\n")


def test_a_record_the_parser_skips_fails_the_check(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A talk without a name is skipped, which fails `no session is lost`."""
    status, out = check(
        capsys, ok(changed(YEAR, lambda doc: first_talk(doc).pop("name")))
    )

    assert status == 1
    assert "FAILED: no session is lost" in out
    assert "1 skipped records" in out


def test_a_feed_that_does_not_parse_fails(capsys: pytest.CaptureFixture[str]) -> None:
    """An HTML page served as the feed fails the check as one that won't parse."""
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
    """A 404 or a connection error fails the check with a report, not a raise."""
    status, out = check(capsys, answer)

    assert status == 1
    assert f"{YEAR}: {FEED}\n  {reported}" in out


@pytest.mark.parametrize(
    ("answer", "reported"),
    [
        (ok(recorded(YEAR)), f"{NEXT_YEAR}: PUBLISHED at {NEXT_FEED} with "),
        (
            ok(b"<html>Coming soon</html>"),
            f"{NEXT_YEAR}: HTTP 200 at {NEXT_FEED}, but not a feed",
        ),
        (httpx.Response(503), f"{NEXT_YEAR}: HTTP 503 at {NEXT_FEED}"),
        (httpx.ReadTimeout("timed out"), f"{NEXT_YEAR}: could not fetch {NEXT_FEED}"),
    ],
)
def test_next_years_feed_is_reported_without_failing_the_check(
    capsys: pytest.CaptureFixture[str], answer: Answer, reported: str
) -> None:
    """Whatever next year's URL answers is reported, and the check passes."""
    status, out = check(capsys, ok(recorded(YEAR)), next_year=answer)

    assert status == 0
    assert reported in out


def test_next_year_redirected_to_this_years_feed_is_not_published(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Next year's URL redirecting to this year's feed is not published yet."""
    moved = httpx.Response(302, headers={"location": FEED})

    status, out = check(capsys, ok(recorded(YEAR)), next_year=moved)

    assert status == 0
    assert (
        f"{NEXT_YEAR}: {NEXT_FEED} redirects to {FEED} (HTTP 302); not published yet"
        in out
    )
    assert "PUBLISHED" not in out


def test_keys_the_recorded_feeds_lack_are_printed_not_failed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """New keys, top level or in a slot, are printed as ignored and pass."""

    def grow(doc: dict[str, Any]) -> None:
        first_talk(doc)["captions_url"] = "https://example.org/captions"
        doc["badges"] = []

    status, out = check(capsys, ok(changed(YEAR, grow)))

    assert status == 0
    assert "keys the recorded feeds lack (ignored): (top level): badges" in out
    assert "schedule: captions_url" in out


def test_new_keys_compares_sections_and_their_records() -> None:
    """`new_keys` lists the keys no recorded feed has, top level and per section."""
    grown = document(2026)
    first_talk(grown)["captions_url"] = "https://example.org/captions"
    grown["badges"] = []

    assert new_keys(document(2026), [document(2026)]) == []
    assert new_keys(grown, [document(2025), document(2026)]) == [
        "(top level): badges",
        "schedule: captions_url",
    ]


def test_each_year_given_is_checked(capsys: pytest.CaptureFixture[str]) -> None:
    """Each year named is checked, next year failing without data, and not probed."""
    status = main(
        [str(YEAR), str(NEXT_YEAR)], transport=serving({FEED: ok(recorded(YEAR))})
    )
    out = capsys.readouterr().out

    assert status == 1
    assert f"{YEAR}: " in out and "  OK\n" in out
    assert (
        f"{NEXT_YEAR}: FAILED, no usable year data: {NEXT_YEAR}/conference.toml" in out
    )
    assert "not published yet" not in out  # it was asked for, so it is not probed
