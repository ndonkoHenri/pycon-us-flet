"""Tests for the facts ``gather_facts()`` reads for a bug report (INFO-04, D-72, D-271).

``gather_facts()`` runs on a fake page and real stores: the bundled snapshot, a refresh
through an ``httpx.MockTransport``, and Developer options set in ``Prefs``. Time comes
from ``clock.set_test_now()``; the text itself is ``tests/test_diagnostics.py``'s.
"""

import dataclasses
import logging
import platform
import re

import flet as ft
import httpx
import pytest

import pycon_us
from pycon_us import capabilities
from pycon_us.config import YearData
from pycon_us.favorites import Favorites
from pycon_us.prefs import DEV_FAKE_NOW, DEV_FEED_URL, Prefs
from pycon_us.services import diagnostics
from pycon_us.services.storage import Storage
from tests import diagnostics_facts
from tests.diagnostics_facts import (
    ADDRESS,
    FEED_URL,
    PACIFIC,
    bundled,
    fields,
    gathered,
)
from tests.fake_page import FakePage, android_device, ios_device
from tests.feeds import changed

frozen_clock = diagnostics_facts.frozen_clock  # the fixtures, under this module's names
year = diagnostics_facts.year
storage = diagnostics_facts.storage


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
