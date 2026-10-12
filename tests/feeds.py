"""Helpers for the feed tests: the recorded feeds, and copies of them with one change."""

import json
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

from pycon_us.config import load_year
from pycon_us.core.feed import process
from pycon_us.core.models import ConferenceData
from pycon_us.core.rules import FeedSettings
from tools.feed_invariants import ProcessedFeed, processed_feed

FEEDS = Path(__file__).parent / "fixtures" / "feeds"
YEARS = [2025, 2026]


@cache
def recorded(year: int) -> bytes:
    """The recorded feed of ``year``, as bytes."""
    return (FEEDS / f"conference-{year}.json").read_bytes()


def document(year: int) -> dict[str, Any]:
    """A fresh copy of the recorded feed's JSON."""
    return json.loads(recorded(year))


def settings(year: int) -> FeedSettings:
    return load_year(year).feed_settings


def processed(year: int) -> ConferenceData:
    """The recorded feed, processed. Not cached: each machine zone processes it again."""
    return process(recorded(year), settings(year))


def recorded_feed(year: int) -> ProcessedFeed:
    """The recorded feed with its JSON, model and year data, for the invariants."""
    return processed_feed(recorded(year), load_year(year))


def changed(year: int, change: Callable[[dict[str, Any]], object]) -> bytes:
    """The recorded feed with ``change`` applied to a fresh copy of its JSON."""
    doc = document(year)
    change(doc)
    return json.dumps(doc).encode()
