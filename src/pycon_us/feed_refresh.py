"""The feed refresh without its store: its words, its timings and its network step (D-231).

`state.py`'s `Conference` runs refreshes and publishes what they bring; this module
holds what needs none of the store's fields. The words for the outcome: where the data
came from (`Source`), why the last refresh failed (`Problem`) and what the status
strip says (`Status`). The timings: when data turns stale (D-32, `stale()`) and when
the next automatic refresh is due (D-40, `due()`). And one attempt at the network:
`fetch()`, the `feed_digest()` that tells the published feed's bytes again (D-224),
and `log_unexpected()` for a refresh that ends in a bug (D-71).
"""

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Literal

import httpx

from pycon_us import clock
from pycon_us.config import ConferenceInfo, YearData
from pycon_us.core import feed
from pycon_us.core.models import ConferenceData
from pycon_us.core.timefmt import today
from pycon_us.services import api, feed_api

logger = logging.getLogger(__name__)

type Source = Literal["none", "bundled", "cache", "network"]
"""Where the published data came from; `none` until `load_local` publishes."""

type Problem = Literal["offline", "server"]
"""Why the last refresh failed: no answer, or an answer that could not be used."""

type Status = Literal["fresh", "stale", "refreshing", "offline", "problem"]
"""What the status strip says about the data (D-32, D-146)."""

STALE_ON_CONFERENCE_DAYS = timedelta(hours=6)
"""Data older than this is stale from the first to the last conference day (D-32)."""

STALE_OTHERWISE = timedelta(hours=24)
"""Data older than this is stale on any other day (D-32)."""

REFRESH_EVERY = timedelta(minutes=15)
"""How long after a refresh began the next automatic one is due: on resume, and on Now
and Schedule while they show (D-40)."""


def stale(age: timedelta | None, info: ConferenceInfo) -> bool:
    """Return whether data of `age` is stale by `clock.now()` (D-32).

    Stale when it is older than 6 h on a conference day (`first_day` to `last_day`
    in conference time) or 24 h on another day, or when there is no data (None).

    Args:
        age: How old the data is, `Conference.age()`.
        info: The year's facts: its dates and time zone.
    """
    if age is None:
        return True
    day = today(clock.now(), info.zone)
    conference_day = info.first_day <= day <= info.last_day
    return age > (STALE_ON_CONFERENCE_DAYS if conference_day else STALE_OTHERWISE)


def due(started_at: datetime | None) -> bool:
    """Return whether an automatic refresh is due, by when the last one started (D-40).

    Due when no refresh has started in this session (None), or the last one started
    `REFRESH_EVERY` or more ago by `clock.now()`, whatever its outcome: counted from
    the last attempt, not the data's age, so a phone offline retries every 15 min, not
    on every check. A clock set back before the last start (the fake clock) makes it
    due too.

    Args:
        started_at: When the last refresh started, `Conference._started_at`.
    """
    if started_at is None:
        return True
    return not timedelta(0) <= clock.now() - started_at < REFRESH_EVERY


def feed_digest(raw: bytes) -> bytes:
    """Return the SHA-256 of a raw feed: about 0.3 ms for 2026's 800 kB on the host."""
    return hashlib.sha256(raw).digest()


async def fetch(
    url: str,
    year: YearData,
    transport: httpx.AsyncBaseTransport | None,
    published: bytes | None,
) -> tuple[bytes, bytes, ConferenceData | None] | Problem:
    """Fetch and process the feed; return its bytes, digest and data, or why that failed.

    Args:
        url: The feed URL.
        year: The year's feed settings.
        transport: The HTTP transport; tests pass an `httpx.MockTransport`.
        published: The digest of the published feed: bytes with that digest are not
            processed, and their data is None (D-224).

    Returns:
        The bytes, their digest and the processed feed (None when it is the published
        one), or the `Problem` that stopped it (D-146).
    """
    try:
        raw = await feed_api.fetch_feed(url, transport=transport)
        digest = feed_digest(raw)
        if digest == published:
            return raw, digest, None
        return raw, digest, feed.process(raw, year.feed_settings)  # on the loop (D-109)
    except api.NetworkError as error:
        logger.info("Feed refresh: no answer (%s); keeping the current data", error)
        return "offline"
    except (api.ApiError, feed.FeedError) as error:
        logger.warning("Feed refresh failed (%s); keeping the current data", error)
        return "server"


def log_unexpected(task: asyncio.Task[None]) -> None:
    """Log a refresh that failed with an unexpected error, as soon as it ends (D-71).

    Without it, the error of a refresh nobody awaits would surface only when the finished
    task is garbage collected, which `Conference._task` delays until the next refresh.
    """
    if not task.cancelled() and (error := task.exception()) is not None:
        logger.error("Feed refresh failed unexpectedly", exc_info=error)
