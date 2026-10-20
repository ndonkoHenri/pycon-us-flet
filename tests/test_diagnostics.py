"""Tests for the plain diagnostics text a bug report carries (INFO-04, D-72, D-271).

``diagnostics_text()`` is tested on hand-made ``Facts``; ``gather_facts()`` on a fake
page and real stores: the bundled snapshot, a refresh through an ``httpx.MockTransport``,
and Developer options set in ``Prefs``. Time comes from ``clock.set_test_now()``.
"""

import dataclasses
import logging
import platform
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import flet as ft
import httpx
import pytest

import pycon_us
from pycon_us import capabilities, clock
from pycon_us.config import YearData, load_year
from pycon_us.favorites import Favorites
from pycon_us.prefs import DEV_FAKE_NOW, DEV_FEED_URL, Prefs
from pycon_us.services import diagnostics
from pycon_us.services.diagnostics import Facts, diagnostics_text, gather_facts
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from tests.fakes import FakePage, MemoryPrefs, android_device, ios_device
from tests.feeds import changed

NOW = datetime(2026, 5, 15, 17, 30, tzinfo=UTC)
"""10:30 in Pacific Time on the first conference day."""

PACIFIC = "America/Los_Angeles"

FEED_URL = "https://staging.example.org/feed.json?token=s3cret&q=jane"
"""A Developer feed URL with a query, as a tester could set one."""

ADDRESS = "jane.doe@example.org"

NAMES = (
    "App",
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


# ------------------------------------------------------------------ the text


def test_each_line_names_one_fact_in_a_fixed_order() -> None:
    """The text is 18 ``Name: value`` lines, under the issue's 20, one per fact."""
    text = diagnostics_text(FACTS)
    assert tuple(fields(text)) == NAMES
    assert len(text.splitlines()) == len(NAMES) <= 20


def test_the_whole_text_of_a_packaged_run() -> None:
    """A packaged run's text, line by line: versions, device, data, clock and settings."""
    assert diagnostics_text(FACTS).split("\n") == (
        [
            "App: 0.1.0",
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


# ------------------------------------------------------------------ gathering


@pytest.mark.parametrize("embedded", [True, False])
async def test_gathering_says_whether_the_run_is_packaged(
    monkeypatch: pytest.MonkeyPatch,
    storage: Storage,
    year: YearData,
    embedded: bool,
) -> None:
    """A packaged build and the companion app (``is_embedded()``) each say what they are."""
    monkeypatch.setattr(diagnostics, "is_embedded", lambda: embedded)
    lines = fields(await gathered(year, await bundled(storage, year)))
    expected = "packaged app" if embedded else diagnostics.NOT_EMBEDDED
    assert lines["Run"] == expected


async def test_gathering_reads_the_build_and_the_year(
    storage: Storage, year: YearData
) -> None:
    """The app, Python and Flet versions, the year, its zone and the capabilities."""
    lines = fields(await gathered(year, await bundled(storage, year)))
    assert lines["App"] == pycon_us.__version__
    assert lines["Python"] == platform.python_version()
    assert lines["Flet"] == pycon_us.FLET_VERSION
    assert lines["Year"] == "2026"
    assert lines["Conference zone"] == PACIFIC
    # Under pytest nothing is embedded, so no capability is on (D-63).
    assert lines["Capabilities"] == "none"


async def test_gathering_lists_only_the_capabilities_that_are_on(
    monkeypatch: pytest.MonkeyPatch, storage: Storage, year: YearData
) -> None:
    """``gather_facts()`` names the capabilities that are on, in order, and skips the rest."""
    monkeypatch.setattr(
        capabilities,
        "ALL",
        (("Secure storage", False), ("Reminders", True), ("Badge scanner", True)),
    )
    lines = fields(await gathered(year, await bundled(storage, year)))
    assert lines["Capabilities"] == "Reminders, Badge scanner"


async def test_bundled_data_names_the_snapshot_and_its_capture(
    storage: Storage, year: YearData
) -> None:
    """With no cache and no refresh, the schedule is the snapshot, dated by its capture."""
    conference = await bundled(storage, year)
    lines = fields(await gathered(year, conference))
    assert conference.digest is not None
    assert lines["Schedule"] == f"bundled, feed {conference.digest.hex()[:12]}"
    captured = year.conference.snapshot_captured_at
    assert captured is not None
    assert lines["Schedule fetched"].startswith(
        captured.astimezone(year.conference.zone).isoformat(timespec="seconds")
    )


async def test_feed_data_names_the_network_and_the_feed_it_brought(
    storage: Storage, year: YearData
) -> None:
    """After a refresh brings a new feed, the schedule is from the network, just now."""

    def rename(document: dict[str, object]) -> None:
        """Rename the conference's first slot, so the feed differs from the snapshot."""
        slots = document["schedule"]
        assert isinstance(slots, list)
        slots[0]["name"] = "Renamed on the server"

    served = changed(2026, rename)
    conference = await bundled(storage, year)
    snapshot = conference.digest
    await conference.refresh(
        storage,
        year,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=served)),
    )
    lines = fields(await gathered(year, conference))
    assert conference.source == "network"
    assert conference.digest not in (None, snapshot)
    assert lines["Schedule"] == f"network, feed {conference.digest.hex()[:12]}"  # pyright: ignore[reportOptionalMemberAccess]
    assert lines["Schedule fetched"] == "2026-05-15T10:30:00-07:00 (just now)"


@pytest.mark.parametrize(
    ("dev", "fake_clock", "custom"),
    [
        ({}, "off", "no"),
        (
            {DEV_FAKE_NOW: "2026-05-16T09:00:00-07:00"},
            "from 2026-05-16T09:00:00-07:00, now 2026-05-15T10:30:00-07:00",
            "no",
        ),
        ({DEV_FEED_URL: FEED_URL}, "off", "yes"),
        (
            {DEV_FAKE_NOW: "2026-05-16T09:00:00-07:00", DEV_FEED_URL: FEED_URL},
            "from 2026-05-16T09:00:00-07:00, now 2026-05-15T10:30:00-07:00",
            "yes",
        ),
    ],
)
async def test_gathering_reads_the_developer_options(
    storage: Storage,
    year: YearData,
    dev: dict[str, str],
    fake_clock: str,
    custom: str,
) -> None:
    """With and without a fake clock or a custom feed URL, in every combination.

    The fake clock's start is the stored one and "now" is ``clock.now()``, which a test
    freezes here; in the app the clock runs forward from the start.
    """
    text = await gathered(year, await bundled(storage, year), prefs=Prefs(dev=dev))
    lines = fields(text)
    assert lines["Fake clock"] == fake_clock
    assert lines["Custom feed URL"] == custom


async def test_the_text_never_holds_the_url_ids_titles_or_an_email(
    storage: Storage, year: YearData
) -> None:
    """Even with all of them in the stores, the gathered text names none (D-72).

    The feed URL (with a token and a query) is in effect, sessions are saved, and the
    device's maker quotes an email address. A search query is left out by construction:
    ``gather_facts()`` never reads ``ViewMemory``, and the field-set test pins that.
    """
    conference = await bundled(storage, year)
    data = conference.data
    assert data is not None
    # Three-digit ids, so that one cannot match a version's digit by chance.
    saved = [ident for ident in sorted(data.sessions) if len(ident) == 3][:3]
    titles = [data.sessions[ident].name for ident in saved]
    page = FakePage()
    page.platform = ft.PagePlatform.ANDROID
    page.device = android_device(35, manufacturer=ADDRESS, model="Pixel", release="15")
    text = await gathered(
        year,
        conference,
        page=page,
        prefs=Prefs(dev={DEV_FEED_URL: FEED_URL}),
        favorites=Favorites(ids=frozenset(saved), loaded=True),
    )
    lines = fields(text)
    assert lines["Saved sessions"] == "3"
    assert lines["Custom feed URL"] == "yes"
    forbidden = [FEED_URL, "staging.example.org", "s3cret", "token", ADDRESS]
    forbidden += titles
    for value in forbidden:
        assert value not in text
    for ident in saved:
        assert not re.search(rf"\b{re.escape(ident)}\b", text)


async def test_an_android_device_names_its_make_model_and_api_level(
    storage: Storage, year: YearData
) -> None:
    """An emulator says so; the OS line gives the release and the API level."""
    page = FakePage()
    page.platform = ft.PagePlatform.ANDROID
    page.device = android_device(
        35, manufacturer="Google", model="sdk_gphone64_arm64", release="15"
    )
    lines = fields(await gathered(year, await bundled(storage, year), page=page))
    assert lines["Device"] == "Google sdk_gphone64_arm64, emulator"
    assert lines["OS"] == "Android 15 (API 35)"


@pytest.mark.parametrize(
    ("physical", "device"), [(False, "iPhone 17, simulator"), (True, "iPhone 17")]
)
async def test_an_ios_device_names_its_model_never_its_name(
    storage: Storage, year: YearData, physical: bool, device: str
) -> None:
    """The model's commercial name and the iOS version, not the user-given device name."""
    page = FakePage()
    page.device = dataclasses.replace(
        ios_device("iPhone 17", "26.5", physical=physical), name="Jane's iPhone"
    )
    text = await gathered(year, await bundled(storage, year), page=page)
    lines = fields(text)
    assert lines["Device"] == device
    assert lines["OS"] == "iOS 26.5"
    assert "Jane" not in text


async def test_a_failed_device_read_leaves_the_rest_and_logs_the_class(
    storage: Storage, year: YearData, caplog: pytest.LogCaptureFixture
) -> None:
    """The device is "unknown" and the OS the platform; the log names the error's class."""
    page = FakePage()
    page.device_error = RuntimeError(f"failed for {ADDRESS}")
    with caplog.at_level(logging.WARNING):
        lines = fields(await gathered(year, await bundled(storage, year), page=page))
    assert lines["Device"] == "unknown"
    assert lines["OS"] == "ios"
    assert "Could not read the device info: RuntimeError" in caplog.text
    assert ADDRESS not in caplog.text


async def test_gathering_reads_the_width_motion_and_saved_count(
    storage: Storage, year: YearData
) -> None:
    """The page's width, the OS's motion setting and the favourites' count, or unknown."""
    page = FakePage()
    page.width = 820
    prefs = Prefs(reduce_motion=True)
    text = await gathered(
        year,
        await bundled(storage, year),
        page=page,
        prefs=prefs,
        favorites=Favorites(ids=frozenset({"1", "2"}), loaded=False),
    )
    lines = fields(text)
    assert lines["Width"] == "820 dp, medium"
    assert lines["Reduced motion"] == "on"
    assert lines["Saved sessions"] == "unknown (the saved list could not be read)"
