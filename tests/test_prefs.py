"""Tests for the Prefs store: load, save, checked values and the OS facts (STORE-08..10).

SharedPreferences is the in-memory fake from ``tests/fakes.py``; Flet's own type check in
``SharedPreferences.set`` still runs.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import flet as ft
import pytest

from pycon_us import prefs as prefs_module
from pycon_us.prefs import (
    APPEARANCES,
    HIGH_CONTRAST_SETTINGS,
    Prefs,
    parse_feed_url,
    with_dev_options,
)
from pycon_us.services import storage
from pycon_us.services.storage import Storage
from tests.fakes import MemoryPrefs


@pytest.fixture
def shared() -> MemoryPrefs:
    """An empty in-memory SharedPreferences."""
    return MemoryPrefs()


@pytest.fixture
def store(shared: MemoryPrefs, tmp_path: Path) -> Storage:
    """The 2026 storage over ``shared`` and a temporary directory."""
    return Storage(prefs=shared, directory=tmp_path, year=2026)


async def loaded(store: Storage) -> Prefs:
    """A new ``Prefs`` loaded from ``store``."""
    prefs = Prefs()
    await prefs.load(store)
    return prefs


# ------------------------------------------------------------------ load


async def test_a_first_launch_reads_every_default(store: Storage) -> None:
    """On a first launch, every preference reads its default; Open Space is hidden."""
    prefs = await loaded(store)
    assert prefs.theme == "system"
    assert prefs.high_contrast == "system"
    assert prefs.onboarded is False
    assert prefs.excluded_tracks == ("Open Space",)  # hidden by default (D-20)
    assert prefs.reminders == {}
    assert prefs.dev == {}


async def test_load_reads_what_was_stored(store: Storage, shared: MemoryPrefs) -> None:
    """Loading reads back every stored preference, the JSON ones decoded."""
    shared.values.update(
        {
            "pycon.theme": "dark",
            "pycon.high_contrast": "on",
            "pycon.onboarded": True,
            "pycon.excluded_tracks": ["Talk", "Tutorial"],
            "pycon.reminders": '{"session_reminders": 10}',
            "pycon.dev": '{"feed_url": "http://127.0.0.1:8000/feed.json"}',
        }
    )
    prefs = await loaded(store)
    assert (prefs.theme, prefs.high_contrast, prefs.onboarded) == ("dark", "on", True)
    assert prefs.excluded_tracks == ("Talk", "Tutorial")
    assert prefs.reminders == {"session_reminders": 10}
    assert prefs.dev == {"feed_url": "http://127.0.0.1:8000/feed.json"}


async def test_a_stored_empty_track_list_hides_nothing(
    store: Storage, shared: MemoryPrefs
) -> None:
    """A stored empty list of hidden tracks hides nothing, not the default track."""
    shared.values["pycon.excluded_tracks"] = []
    assert (await loaded(store)).excluded_tracks == ()


@pytest.mark.parametrize(
    ("key", "field"),
    [("pycon.theme", "theme"), ("pycon.high_contrast", "high_contrast")],
)
async def test_an_unknown_setting_value_reads_as_the_default_and_is_logged(
    key: str,
    field: str,
    store: Storage,
    shared: MemoryPrefs,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unknown appearance or contrast value loads as "system", its key logged.

    The value itself is never logged (D-120).
    """
    shared.values[key] = "sepia"
    with caplog.at_level(logging.WARNING):
        prefs = await loaded(store)
    assert getattr(prefs, field) == "system"
    assert key in caplog.text
    assert "sepia" not in caplog.text  # the key is logged, never the value (D-120)


async def test_unreadable_preferences_read_as_their_defaults(
    store: Storage, shared: MemoryPrefs
) -> None:
    """When SharedPreferences fails to read, every preference loads as its default."""
    shared.error = TimeoutError()
    prefs = await loaded(store)
    assert (prefs.theme, prefs.excluded_tracks) == ("system", ("Open Space",))


async def test_load_leaves_the_boot_gate_to_its_caller(store: Storage) -> None:
    """Loading leaves ``loaded`` False: its caller opens the boot gate."""
    assert (await loaded(store)).loaded is False


def test_the_first_value_of_each_setting_is_its_storage_default() -> None:
    """The appearance and contrast choices start with "system", their stored default."""
    assert APPEARANCES == ("system", "light", "dark")
    assert APPEARANCES[0] == storage.THEME.default
    assert HIGH_CONTRAST_SETTINGS == ("system", "on", "off")
    assert HIGH_CONTRAST_SETTINGS[0] == storage.HIGH_CONTRAST.default


# ------------------------------------------------------------------ save


async def test_saved_settings_are_shown_and_survive_a_relaunch(
    store: Storage, shared: MemoryPrefs
) -> None:
    """Saved settings apply at once and load again after a relaunch.

    The hidden tracks are stored as a list, for Flutter (F12).
    """
    prefs = await loaded(store)
    saved = await prefs.save(
        store,
        theme="dark",
        high_contrast="off",
        onboarded=True,
        excluded_tracks=(),
        reminders={"session_reminders": 5},
        dev={"fake_now": "2026-05-15T09:00:00-07:00"},
    )
    assert saved is True
    assert (prefs.theme, prefs.high_contrast, prefs.excluded_tracks) == (
        "dark",
        "off",
        (),
    )
    assert shared.values["pycon.excluded_tracks"] == []  # a list for Flutter (F12)
    relaunched = await loaded(store)
    assert relaunched.theme == "dark"
    assert relaunched.high_contrast == "off"
    assert relaunched.onboarded is True
    assert relaunched.excluded_tracks == ()
    assert relaunched.reminders == {"session_reminders": 5}
    assert relaunched.dev == {"fake_now": "2026-05-15T09:00:00-07:00"}


async def test_settings_left_out_are_neither_written_nor_changed(
    store: Storage, shared: MemoryPrefs
) -> None:
    """A save writes and changes only the settings it is given."""
    prefs = await loaded(store)
    await prefs.save(store, theme="light")
    assert set(shared.values) == {"pycon.theme"}
    assert prefs.excluded_tracks == ("Open Space",)


async def test_a_change_that_cannot_be_saved_is_kept_for_the_session(
    store: Storage, shared: MemoryPrefs
) -> None:
    """A change whose write fails returns False, but holds until the app relaunches."""
    prefs = await loaded(store)
    shared.fail_writes = True
    assert await prefs.save(store, theme="dark", onboarded=True) is False
    assert (prefs.theme, prefs.onboarded) == ("dark", True)  # D-120
    assert (
        await loaded(store)
    ).theme == "system"  # lost on relaunch, hence the message


async def test_a_shared_preferences_error_on_save_is_reported_as_not_saved(
    store: Storage, shared: MemoryPrefs
) -> None:
    """A SharedPreferences error on save returns False; the change holds in memory."""
    prefs = await loaded(store)
    shared.error = RuntimeError("client error")
    assert await prefs.save(store, theme="light") is False
    assert prefs.theme == "light"


async def test_one_failed_write_still_writes_the_others(
    store: Storage, shared: MemoryPrefs
) -> None:
    """One failed write makes the save return False; the others are still written."""
    prefs = await loaded(store)

    async def fail_theme_only(key: str, value: object) -> bool:
        if key == "pycon.theme":
            return False
        shared.values[key] = value
        return True

    shared.set = fail_theme_only  # type: ignore[method-assign]
    assert await prefs.save(store, theme="dark", onboarded=True) is False
    assert shared.values == {"pycon.onboarded": True}


@pytest.mark.parametrize(
    "change", [{"theme": "sepia"}, {"high_contrast": "auto"}, {"theme": "Dark"}]
)
async def test_save_rejects_an_unknown_setting_value_and_changes_nothing(
    change: dict[str, str], store: Storage, shared: MemoryPrefs
) -> None:
    """A save with an unknown appearance or contrast raises and changes nothing."""
    prefs = await loaded(store)
    with pytest.raises(ValueError, match="must be one of"):
        await prefs.save(store, onboarded=True, **change)  # type: ignore[arg-type]
    assert shared.values == {}
    assert prefs.onboarded is False


async def test_a_save_notifies_subscribers_of_each_changed_field(
    store: Storage,
) -> None:
    """A save notifies subscribers once per changed field, in order."""
    prefs = await loaded(store)
    changes: list[str | None] = []

    def listen(_sender: object, field: str | None) -> None:
        changes.append(field)

    assert isinstance(prefs, ft.Observable)
    prefs.subscribe(listen)  # held weakly: a local function, not a lambda
    await prefs.save(store, theme="dark", excluded_tracks=("Talk",))
    assert changes == ["theme", "excluded_tracks"]


# ------------------------------------------------------------------ resolved values


@pytest.mark.parametrize(
    ("theme", "os_dark", "dark"),
    [
        ("system", False, False),
        ("system", True, True),
        ("light", True, False),
        ("dark", False, True),
    ],
)
def test_dark_follows_the_os_only_under_system(
    theme: str, os_dark: bool, dark: bool
) -> None:
    """Dark mode follows the OS only when the appearance is "system"."""
    assert Prefs(theme=theme, os_dark=os_dark).dark is dark  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("setting", "os_flag", "on"),
    [
        ("system", False, False),
        ("system", True, True),
        ("on", False, True),
        ("off", True, False),
    ],
)
def test_high_contrast_follows_the_os_flag_only_under_system(
    setting: str, os_flag: bool, on: bool
) -> None:
    """High contrast follows the OS flag only when its setting is "system"."""
    prefs = Prefs(high_contrast=setting, os_high_contrast=os_flag)  # type: ignore[arg-type]
    assert prefs.high_contrast_on is on


@pytest.mark.parametrize(
    ("switch", "os_flag", "setting"),
    [
        (False, False, "system"),
        (True, True, "system"),
        (True, False, "on"),
        (False, True, "off"),
    ],
)
def test_the_high_contrast_switch_follows_the_os_again_when_set_to_its_flag(
    switch: bool, os_flag: bool, setting: str
) -> None:
    """A switch to the OS flag stores "system", one against it "on" or "off" (D-286)."""
    for stored in HIGH_CONTRAST_SETTINGS:  # whatever the setting was before
        prefs = Prefs(high_contrast=stored, os_high_contrast=os_flag)
        assert prefs.high_contrast_setting(switch) == setting
        prefs.high_contrast = prefs.high_contrast_setting(switch)
        assert prefs.high_contrast_on is switch  # the switch shows what it was set to


@pytest.mark.parametrize(("reduce_motion", "ms"), [(False, 400), (True, 0)])
def test_an_animation_lasts_its_duration_unless_the_os_asks_for_less_motion(
    reduce_motion: bool, ms: int
) -> None:
    """An animation lasts its duration, or 0 ms when the OS asks for reduced motion."""
    assert Prefs(reduce_motion=reduce_motion).motion_ms(400) == ms  # D-34


async def test_reduced_motion_is_never_stored(
    store: Storage, shared: MemoryPrefs
) -> None:
    """A save never writes reduced motion, so a relaunch reads it as off."""
    prefs = await loaded(store)
    prefs.reduce_motion = True  # what read_accessibility() writes
    await prefs.save(store, theme="dark")
    # A device fact, read at start and on resume (F13), not a setting (D-34).
    assert not any("motion" in key for key in shared.values)
    assert not (await loaded(store)).reduce_motion


# ------------------------------------------------------------------ Developer options


def test_developer_options_are_read_from_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    """In a packaged build, Developer, the fake clock and the feed come from ``dev``."""
    monkeypatch.setattr(prefs_module, "DEVELOPER_ALWAYS", False)  # a packaged build
    prefs = Prefs()
    assert (prefs.developer, prefs.fake_now, prefs.feed_url) == (False, None, None)
    prefs.dev = {
        "unlocked": True,
        "fake_now": "2026-05-15T09:00:00-07:00",
        "feed_url": "http://127.0.0.1:8000/conference-2026.json",
    }
    assert prefs.developer and prefs.developer_unlocked
    assert prefs.fake_now == datetime(2026, 5, 15, 16, 0, tzinfo=UTC)
    assert prefs.feed_url == "http://127.0.0.1:8000/conference-2026.json"


def test_developer_is_always_available_when_not_embedded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outside a packaged build, Developer is always on, though never unlocked."""
    monkeypatch.setattr(prefs_module, "DEVELOPER_ALWAYS", True)  # the companion app
    prefs = Prefs()
    assert prefs.developer is True
    assert prefs.developer_unlocked is False  # no unlock: details come from elsewhere


@pytest.mark.parametrize(
    "dev",
    [
        {"fake_now": "2026-05-15T09:00"},  # naive: a stored start carries its offset
        {"fake_now": "next Friday"},
        {"fake_now": 1747324800},
        {"unlocked": "yes", "feed_url": ""},
    ],
)
def test_unusable_developer_values_read_as_their_defaults(dev: dict[str, Any]) -> None:
    """Naive, unreadable or mistyped Developer values read as their defaults."""
    prefs = Prefs(dev=dict(dev))
    assert prefs.fake_now is None
    assert prefs.feed_url is None
    assert prefs.developer_unlocked is False


def test_dev_options_set_and_remove_only_the_clock_and_the_feed() -> None:
    """The dev options helper sets or removes the clock and feed, keeping the rest."""
    start = datetime(2026, 5, 15, 9, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    feed = "http://127.0.0.1:8000/conference-2026.json"
    dev = with_dev_options({"unlocked": True}, fake_now=start, feed_url=feed)
    assert dev == {"unlocked": True, "fake_now": start.isoformat(), "feed_url": feed}
    assert with_dev_options(dev, fake_now=None, feed_url=None) == {"unlocked": True}


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:8000/conference-2026.json", "https://example.test/feed.json"],
)
def test_http_and_https_feed_urls_are_taken(url: str) -> None:
    """An http or https feed URL is taken, without its surrounding spaces."""
    assert parse_feed_url(f" {url} ") == url


@pytest.mark.parametrize(
    "text", ["us.pycon.org/feed.json", "ftp://example.test/f", "https://", "file:///x"]
)
def test_other_feed_urls_are_refused(text: str) -> None:
    """A feed URL without an http or https scheme and a host is refused."""
    with pytest.raises(ValueError, match="http:// or https://"):
        parse_feed_url(text)


def test_an_empty_feed_url_is_the_year_s() -> None:
    """An empty feed URL parses as None: the year's own feed."""
    assert parse_feed_url("") is None


def test_reset_returns_every_setting_to_its_default_and_keeps_the_device() -> None:
    """A reset returns every setting to its default and keeps the device's facts.

    The boot gate stays open too.
    """
    prefs = Prefs(
        theme="dark",
        high_contrast="on",
        onboarded=True,
        excluded_tracks=(),
        reminders={"minutes": 10},
        dev={"unlocked": True},
        os_dark=True,
        reduce_motion=True,
        screen_reader=True,
        loaded=True,
    )
    prefs.reset()
    assert (prefs.theme, prefs.high_contrast, prefs.onboarded) == (
        "system",
        "system",
        False,
    )
    assert prefs.excluded_tracks == ("Open Space",)  # the default filter (D-20)
    assert (prefs.reminders, prefs.dev) == ({}, {})
    assert prefs.os_dark and prefs.reduce_motion and prefs.screen_reader
    assert prefs.loaded is True
