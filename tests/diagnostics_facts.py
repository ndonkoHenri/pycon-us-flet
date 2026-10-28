"""What the diagnostics tests share: the facts, the clock and the stores (INFO-04, D-72).

``test_diagnostics.py`` tests ``diagnostics_text()`` on hand-made ``Facts``;
``test_diagnostics_gather.py`` tests ``gather_facts()`` on a fake page and real stores.
Both take ``frozen_clock`` (autouse) by assignment, the second ``year`` and ``storage``
too (``docs/testing-and-quality.md`` §3.1).
"""

import dataclasses
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.config import YearData, load_year
from pycon_us.favorites import Favorites
from pycon_us.prefs import Prefs
from pycon_us.services.diagnostics import Facts, diagnostics_text, gather_facts
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from tests.fake_page import FakePage
from tests.fakes import MemoryPrefs

NOW = datetime(2026, 5, 15, 17, 30, tzinfo=UTC)
"""10:30 in Pacific Time on the first conference day."""

PACIFIC = "America/Los_Angeles"

FEED_URL = "https://staging.example.org/feed.json?token=s3cret&q=jane"
"""A Developer feed URL with a query, as a tester could set one."""

ADDRESS = "jane.doe@example.org"

NAMES = (
    "App",
    "Build",
    "Python",
    "Flet",
    "Device",
    "OS",
    "Run",
    "Year",
    "Schedule",
    "Schedule fetched",
    "Conference zone",
    "Device offset",
    "Fake clock",
    "Written",
    "Custom feed URL",
    "Reduced motion",
    "Width",
    "Capabilities",
    "Saved sessions",
)
"""Every fact the text names, in its order."""

FACTS = Facts(
    app_version="0.1.0",
    build_number="812",
    python="3.14.0",
    flet="source build",
    platform="android",
    device="Google Pixel 9, emulator",
    os="Android 15 (API 35)",
    embedded=True,
    year=2026,
    source="cache",
    feed_digest=bytes(range(32)),
    fetched_at=NOW - timedelta(hours=2),
    zone=PACIFIC,
    device_offset=timedelta(hours=1),
    fake_clock_from=None,
    now=NOW,
    written_at=NOW,
    custom_feed_url=False,
    reduced_motion=False,
    width=412,
    capabilities=(),
    saved_sessions=12,
)
"""A packaged run on an Android emulator with cached data and no Developer options."""


@pytest.fixture(autouse=True)
def frozen_clock() -> Iterator[None]:
    """Freeze ``clock.now()`` at ``NOW`` for the test, then return to real time."""
    clock.set_test_now(NOW)
    yield
    clock.set_test_now(None)


@pytest.fixture(scope="module")
def year() -> YearData:
    """The 2026 year data, loaded once for the module."""
    return load_year(2026)


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    """A 2026 ``Storage`` in ``tmp_path``, over in-memory SharedPreferences."""
    return Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)


def fields(text: str) -> dict[str, str]:
    """Return the text's lines as a mapping of each fact's name to its value."""
    lines = text.split("\n")
    pairs = dict(line.split(": ", 1) for line in lines)
    assert len(pairs) == len(lines), "a fact is named twice"
    return pairs


def text_of(**changes: object) -> dict[str, str]:
    """Return the text of ``FACTS`` with ``changes``, by fact name."""
    return fields(diagnostics_text(dataclasses.replace(FACTS, **changes)))  # pyright: ignore[reportArgumentType]


async def gathered(
    year: YearData,
    conference: Conference,
    *,
    page: FakePage | None = None,
    prefs: Prefs | None = None,
    favorites: Favorites | None = None,
) -> str:
    """Return the text of the facts ``gather_facts()`` reads from these stores and page."""
    facts = await gather_facts(
        cast(ft.Page, page or FakePage()),
        info=year.conference,
        conference=conference,
        prefs=prefs or Prefs(),
        favorites=favorites or Favorites(loaded=True),
    )
    return diagnostics_text(facts)


async def bundled(storage: Storage, year: YearData) -> Conference:
    """Return a ``Conference`` showing the bundled snapshot: no cache, no refresh yet."""
    conference = Conference()
    await conference.load_local(storage, year)
    return conference
