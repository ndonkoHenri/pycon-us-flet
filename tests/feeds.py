"""Helpers for the feed tests: the recorded feeds, copies of them with a change, and pairs.

A change-log case is a pair: the recorded feed and a copy with named edits applied
(``pair(2026, move(142, "Room 101B"))``), built here rather than committed as files, so it
says exactly what differs and never drifts from the recorded feed (D-255).
"""

import json
import os
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
    """The feed settings from ``year``'s year data."""
    return load_year(year).feed_settings


@cache
def _processed_in(year: int, machine_zone: str | None) -> ConferenceData:
    """Process the recorded feed once per year and machine zone, for ``processed()``."""
    return process(recorded(year), settings(year))


def processed(year: int) -> ConferenceData:
    """The recorded feed, processed once per machine zone, and shared: never change it.

    ``TZ`` is in the key because each zone of ``machine_tz`` must process the feed again
    to show that the result doesn't lean on the machine's zone. A test that needs what
    only a new load gives (an object of its own, the logs, a patched converter's calls)
    calls ``process(recorded(year), settings(year))``.
    """
    return _processed_in(year, os.environ.get("TZ"))


def recorded_feed(year: int) -> ProcessedFeed:
    """The recorded feed with its JSON, model and year data, for the invariants."""
    return processed_feed(recorded(year), load_year(year))


type Edit = Callable[[dict[str, Any]], object]
"""A change to a feed's JSON, made in place on a fresh copy."""


def changed(year: int, change: Edit) -> bytes:
    """The recorded feed with ``change`` applied to a fresh copy of its JSON."""
    doc = document(year)
    change(doc)
    return json.dumps(doc).encode()


def pair(year: int, *edits: Edit) -> tuple[bytes, bytes]:
    """A change-log case: the recorded feed, and a copy with ``edits`` applied in order."""

    def apply(doc: dict[str, Any]) -> None:
        for edit in edits:
            edit(doc)

    return recorded(year), changed(year, apply)


def slot(doc: dict[str, Any], conf_key: int) -> dict[str, Any]:
    """The schedule slot of ``doc`` whose ``conf_key`` is ``conf_key``."""
    return next(s for s in doc["schedule"] if s["conf_key"] == conf_key)


def move(conf_key: int, room: str) -> Edit:
    """An edit that moves slot ``conf_key`` to ``room``, alone."""

    def edit(doc: dict[str, Any]) -> None:
        slot(doc, conf_key).update(room=room, rooms=[room])

    return edit


def retime(conf_key: int, start: str, end: str) -> Edit:
    """An edit that gives slot ``conf_key`` new ISO 8601 times, with their offsets."""

    def edit(doc: dict[str, Any]) -> None:
        slot(doc, conf_key).update(start=start, end=end)

    return edit


def rename(conf_key: int, name: str) -> Edit:
    """An edit that renames slot ``conf_key``."""

    def edit(doc: dict[str, Any]) -> None:
        slot(doc, conf_key).update(name=name)

    return edit


def add(conf_key: int, like: int, name: str) -> Edit:
    """An edit that adds slot ``conf_key``, a copy of slot ``like`` named ``name``."""

    def edit(doc: dict[str, Any]) -> None:
        doc["schedule"].append({**slot(doc, like), "conf_key": conf_key, "name": name})

    return edit


def remove(conf_key: int) -> Edit:
    """An edit that removes slot ``conf_key`` from the schedule."""

    def edit(doc: dict[str, Any]) -> None:
        doc["schedule"].remove(slot(doc, conf_key))

    return edit
