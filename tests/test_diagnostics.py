"""Tests for the plain diagnostics text a bug report carries (INFO-04, D-72, D-271).

``diagnostics_text()`` is tested on hand-made ``Facts``; ``gather_facts()`` on a fake
page and real stores is ``tests/test_diagnostics_gather.py``'s. Both share
``tests/diagnostics_facts.py``. Time comes from ``clock.set_test_now()``.
"""

import dataclasses
import re
from datetime import UTC, datetime, timedelta

import pytest

from pycon_us.services import diagnostics
from pycon_us.services.diagnostics import Facts, diagnostics_text
from tests import diagnostics_facts
from tests.diagnostics_facts import (
    ADDRESS,
    FACTS,
    FEED_URL,
    NAMES,
    fields,
    text_of,
)

frozen_clock = diagnostics_facts.frozen_clock  # the fixture, under this module's name


# ------------------------------------------------------------------ the text


def test_each_line_names_one_fact_in_a_fixed_order() -> None:
    """The text is 19 ``Name: value`` lines, under the issue's 20, one per fact."""
    text = diagnostics_text(FACTS)
    assert tuple(fields(text)) == NAMES
    assert len(text.splitlines()) == len(NAMES) <= 20


def test_the_whole_text_of_a_packaged_run() -> None:
    """A packaged run's text, line by line: versions, device, data, clock and settings."""
    assert diagnostics_text(FACTS).split("\n") == (
        [
            "App: 0.1.0",
            "Build: 812",
            "Python: 3.14.0",
            "Flet: source build",
            "Device: Google Pixel 9, emulator",
            "OS: Android 15 (API 35)",
            "Run: packaged app",
            "Year: 2026",
            "Schedule: cache, feed 000102030405",
            "Schedule fetched: 2026-05-15T08:30:00-07:00 (2 hours ago)",
            "Conference zone: America/Los_Angeles",
            "Device offset: UTC+01:00",
            "Fake clock: off",
            "Written: 2026-05-15T10:30:00-07:00",
            "Custom feed URL: no",
            "Reduced motion: off",
            "Width: 412 dp, compact",
            "Capabilities: none",
            "Saved sessions: 12",
        ]
    )


def test_times_are_iso_8601_in_conference_time_with_their_offset() -> None:
    """The fetch, the fake clock and the writing time are ISO 8601 with a UTC offset."""
    start = datetime(2026, 5, 15, 16, 0, tzinfo=UTC)
    lines = text_of(fake_clock_from=start)
    iso = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d"
    assert re.fullmatch(rf"{iso} \(2 hours ago\)", lines["Schedule fetched"])
    assert re.fullmatch(rf"from {iso}, now {iso}", lines["Fake clock"])
    assert re.fullmatch(iso, lines["Written"])
    assert lines["Fake clock"] == (
        "from 2026-05-15T09:00:00-07:00, now 2026-05-15T10:30:00-07:00"
    )


@pytest.mark.parametrize(
    ("offset", "line"),
    [
        (timedelta(hours=-7), "UTC-07:00"),
        (timedelta(0), "UTC+00:00"),
        (timedelta(hours=5, minutes=30), "UTC+05:30"),
    ],
)
def test_the_device_offset_is_iso_8601_with_an_ascii_sign(
    offset: timedelta, line: str
) -> None:
    """West of UTC is "-", never the typographic minus, so "-07:00" finds it in a report."""
    text = diagnostics_text(dataclasses.replace(FACTS, device_offset=offset))
    assert fields(text)["Device offset"] == line
    assert "\u2212" not in text


def test_a_companion_run_says_it_is_not_embedded() -> None:
    """``flet run`` and the companion app are not embedded, and the text says so (F14)."""
    assert text_of(embedded=False)["Run"] == diagnostics.NOT_EMBEDDED


def test_before_any_data_the_schedule_says_none_yet() -> None:
    """Before ``load_local`` publishes, there is no source, feed or fetch time."""
    lines = text_of(source="none", feed_digest=None, fetched_at=None)
    assert lines["Schedule"] == "none yet"
    assert lines["Schedule fetched"] == "never"


def test_an_unknown_device_falls_back_to_the_platform() -> None:
    """Without device info, the device is "unknown" and the OS is the page's platform."""
    lines = text_of(device=None, os=None, platform="ios")
    assert lines["Device"] == "unknown"
    assert lines["OS"] == "ios"


@pytest.mark.parametrize(
    ("width", "line"),
    [
        (None, "unknown"),
        (412, "412 dp, compact"),
        (599.6, "600 dp, compact"),
        (600, "600 dp, medium"),
        (839, "839 dp, medium"),
        (840, "840 dp, expanded"),
        (1366, "1366 dp, expanded"),
    ],
)
def test_the_width_names_its_material_window_size_class(
    width: float | None, line: str
) -> None:
    """Compact under 600 dp, medium under 840 dp, expanded from there (D-09)."""
    assert text_of(width=width)["Width"] == line


def test_the_capabilities_list_those_the_build_has() -> None:
    """The names of the capabilities in the build, joined, or "none"."""
    assert text_of(capabilities=("Reminders", "Badge scanner"))["Capabilities"] == (
        "Reminders, Badge scanner"
    )


def test_an_unread_saved_list_is_not_counted_as_empty() -> None:
    """When the favourites could not be read, the count is unknown, not 0 (D-172)."""
    assert text_of(saved_sessions=None)["Saved sessions"] == (
        "unknown (the saved list could not be read)"
    )


def test_facts_has_exactly_the_reviewed_fields() -> None:
    """``Facts`` holds only the reviewed fields, none of them personal (D-72, D-271).

    Adding a field means first deciding it carries nothing personal (no query, title,
    id, URL or name), then listing it here. The search query has no field by design.
    """
    assert [field.name for field in dataclasses.fields(Facts)] == [
        "app_version",
        "build_number",
        "python",
        "flet",
        "platform",
        "device",
        "os",
        "embedded",
        "year",
        "source",
        "feed_digest",
        "fetched_at",
        "zone",
        "device_offset",
        "fake_clock_from",
        "now",
        "written_at",
        "custom_feed_url",
        "reduced_motion",
        "width",
        "capabilities",
        "saved_sessions",
    ]


def test_values_cannot_add_a_line_or_carry_an_address_or_a_url() -> None:
    """A value with a line break, an email or a URL and its query stays one clean line."""
    text = diagnostics_text(
        dataclasses.replace(
            FACTS,
            device=f"Pixel\nInjected: {ADDRESS}",
            os=f"Android {FEED_URL} mailto%40{ADDRESS}",
            flet=f"x {'y' * 200}",
        )
    )
    lines = fields(text)
    assert tuple(lines) == NAMES
    assert lines["Device"] == "Pixel Injected: <email>"
    assert lines["OS"].startswith("Android <url>")
    for secret in (ADDRESS, "example.org", "token", "s3cret", "q=jane", "https"):
        assert secret not in text
    assert len(lines["Flet"]) == diagnostics.MAX_VALUE
    assert lines["Flet"].endswith("…")
