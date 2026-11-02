"""A feed or API reply nested too deep is one more unusable answer, on any stack (#891).

``RecursionError`` is not a ``ValueError``, so it would go past every guard made for a
corrupt payload. These tests pin that it never does, on ``tests/small_stack.py``'s small
stack: the feed's and the private API's readers, and the tools that read what the network
or the app sends. The other places that parse JSON read what the app itself wrote.
"""

import asyncio
import contextlib
import json
import logging
from functools import partial
from typing import Any

import httpx
import pytest

from pycon_us.config import YearData, load_year
from pycon_us.core.feed import FeedError, process
from pycon_us.feed_refresh import fetch
from pycon_us.services.api import MAX_NESTING, ApiError, unwrap
from pycon_us.services.storage import Storage
from tests import feed_store
from tests.feed_store import TOO_DEEP_FEED, loaded, serving
from tests.feeds import document, settings
from tests.small_stack import (
    DEPTHS,
    TOO_DEEP_TO_PARSE,
    nested_lists,
    nested_objects,
    on_a_small_stack,
)
from tools.check_feed import next_year_status
from tools.mock_api.handlers import handle
from tools.mock_api.state import MockState

frozen_clock, year, storage = (
    feed_store.frozen_clock,
    feed_store.year,
    feed_store.storage,
)

TOO_DEEP = [nested_lists(TOO_DEEP_TO_PARSE), nested_objects(TOO_DEEP_TO_PARSE)]
"""Bodies that overflow the parser on a small stack, arrays and objects alike."""

TOO_DEEP_IDS = ["arrays", "objects"]

HOLE = "the nesting goes here"
"""Stands for the nesting in a feed's document, as what parses may be too deep to dump."""


def first_talk(doc: dict[str, Any]) -> dict[str, Any]:
    """The first talk of a feed document, which reads as a good slot."""
    return next(slot for slot in doc["schedule"] if slot["kind"] == "talk")


TALK = first_talk(document(2026))

PLACES: dict[str, dict[str, Any]] = {
    "a slot's name": {"schedule": [{**TALK, "name": HOLE}]},
    "a content block": {"schedule": [TALK], "conference": {"content": {"wifi": HOLE}}},
    "the sponsors": {"schedule": [TALK], "conference": {"sponsors": HOLE}},
    "a sponsor level": {"schedule": [TALK], "conference": {"sponsors": {"Gold": HOLE}}},
    "the id of a slot with nested sessions": {
        "schedule": [TALK, {"sessions": [1], "conf_key": HOLE}]
    },
}
"""Where a nesting the parser takes gets printed, in a skipped record or a log."""


# ------------------------------------------------------------------ the feed


@pytest.mark.parametrize("raw", TOO_DEEP, ids=TOO_DEEP_IDS)
def test_a_feed_too_deep_to_parse_raises_feed_error(raw: bytes) -> None:
    """Bytes that overflow the stack in the parser raise ``FeedError``, like any bad feed."""
    feed_settings = settings(2026)
    with pytest.raises(FeedError, match="nested too deep"):
        on_a_small_stack(partial(process, raw, feed_settings))


@pytest.mark.parametrize("place", PLACES.values(), ids=PLACES)
def test_no_depth_of_nesting_in_a_feed_gets_past_feed_error(
    place: dict[str, Any],
) -> None:
    """At every depth, the feed is read with that record skipped or raises ``FeedError``.

    Printing a value takes more stack than parsing it, so between the depth that printing
    overflows at and the one parsing does, a skipped record's reason used to raise.
    """
    template = json.dumps(place).encode()
    hole = json.dumps(HOLE).encode()
    feed_settings = settings(2026)

    def sweep() -> None:
        """Process the feed at each depth; any error but ``FeedError`` fails the test."""
        for depth in DEPTHS:
            with contextlib.suppress(FeedError):
                process(template.replace(hole, nested_objects(depth)), feed_settings)

    on_a_small_stack(sweep)


def test_html_nested_past_the_recursion_limit_raises_feed_error() -> None:
    """A description whose HTML nests too deep to walk raises ``FeedError``, on any stack."""
    with pytest.raises(FeedError, match="nested too deep"):
        process(TOO_DEEP_FEED, settings(2026))


@pytest.mark.parametrize("raw", TOO_DEEP, ids=TOO_DEEP_IDS)
def test_a_refresh_that_fetches_too_deep_a_feed_is_the_server_problem(
    raw: bytes,
) -> None:
    """The refresh's network step says "server", so the store keeps its data (D-146)."""
    current = load_year(2026)
    outcome = on_a_small_stack(
        lambda: asyncio.run(
            fetch(current.conference.feed_url, current, serving(raw), None)
        )
    )
    assert outcome == "server"


async def test_a_cache_nested_too_deep_is_deleted_and_the_snapshot_published(
    storage: Storage, year: YearData, caplog: pytest.LogCaptureFixture
) -> None:
    """A cache that overflows the stack is deleted with a warning, like a corrupt one."""
    assert await storage.write_feed(TOO_DEEP_FEED)

    with caplog.at_level(logging.WARNING):
        conference = await loaded(storage, year)

    assert conference.source == "bundled"
    assert conference.data is not None
    assert not storage.feed_path.exists()
    assert "it does not parse: nested too deep" in caplog.text


# ------------------------------------------------------------------ the private API


@pytest.mark.parametrize("raw", TOO_DEEP, ids=TOO_DEEP_IDS)
def test_a_reply_too_deep_to_parse_is_not_json(raw: bytes) -> None:
    """A success that overflows the parser is unreadable: it may have been applied."""
    response = httpx.Response(200, content=raw)
    with pytest.raises(ApiError) as caught:
        on_a_small_stack(partial(unwrap, response, False))
    assert caught.value.unreadable
    assert caught.value.message == "The reply is not JSON."


def test_an_error_status_too_deep_to_parse_stays_a_refusal() -> None:
    """An error status with such a body keeps its status and reason, not its body."""
    response = httpx.Response(502, content=nested_lists(TOO_DEEP_TO_PARSE))
    with pytest.raises(ApiError) as caught:
        on_a_small_stack(partial(unwrap, response, False))
    assert (caught.value.status, caught.value.message) == (502, "Bad Gateway")


@pytest.mark.parametrize(
    "shape",
    [
        lambda nesting: nesting,
        lambda nesting: b'{"code": 200, "data": %b}' % nesting,
        lambda nesting: b'{"code": 200, "data": {"a": 1, "b": [[], {"c": %b}]}}' % nesting,
    ],
    ids=["the whole reply", "its data", "behind shallow siblings"],
)  # fmt: skip
def test_no_depth_of_nesting_past_the_limit_reaches_the_caller(shape: Any) -> None:
    """At every depth past the limit, ``unwrap()`` raises ``ApiError`` and nothing else.

    A reply the parser took could still overflow when something printed it, or when the
    outbox dumped it into a row after a send that had worked, so none gets that far.
    """

    def sweep() -> None:
        """Unwrap each depth past the limit, an array and an object nesting of each."""
        for depth in (depth for depth in DEPTHS if depth > MAX_NESTING):
            for nesting in (nested_lists(depth), nested_objects(depth)):
                response = httpx.Response(200, content=shape(nesting))
                with pytest.raises(ApiError) as caught:
                    unwrap(response, True)
                assert caught.value.unreadable

    on_a_small_stack(sweep)


def test_a_reply_at_the_limit_is_read() -> None:
    """The deepest reply allowed reads as itself; one level more is not JSON."""
    deepest = nested_lists(MAX_NESTING)
    assert unwrap(httpx.Response(200, content=deepest), False) == json.loads(deepest)
    with pytest.raises(ApiError, match="not JSON"):
        unwrap(httpx.Response(200, content=nested_lists(MAX_NESTING + 1)), False)


def test_the_limit_is_far_below_what_a_small_stack_overflows_at() -> None:
    """A reply at the limit can be printed and dumped, as the outbox does, on a small stack."""
    deepest = unwrap(
        httpx.Response(200, content=nested_objects(MAX_NESTING - 1)), False
    )
    assert on_a_small_stack(partial(repr, deepest))
    assert on_a_small_stack(partial(json.dumps, deepest))


# ------------------------------------------------------------------ the tools


@pytest.mark.parametrize("raw", TOO_DEEP, ids=TOO_DEEP_IDS)
def test_the_mock_refuses_a_request_body_too_deep_to_parse(raw: bytes) -> None:
    """A body that overflows the mock's parser is a 400, like any body that isn't JSON."""
    answer = partial(
        handle, MockState.from_seed(), "POST", "/2026/api/v1/authenticate/", {}, raw
    )
    status, _, reply = on_a_small_stack(answer)
    assert (status, json.loads(reply)) == (
        400,
        {"code": 400, "error": "The body must be a JSON object."},
    )


def test_the_next_year_check_reports_a_feed_too_deep_to_parse() -> None:
    """The weekly check never fails on next year's URL: such a body is "not a feed"."""
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, content=nested_lists(TOO_DEEP_TO_PARSE))
    )
    status = on_a_small_stack(partial(next_year_status, 2026, transport=transport))
    assert "but not a feed" in status
