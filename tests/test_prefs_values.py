"""Tests for the Prefs store's resolved values and Developer options (STORE-08..10).

What follows the OS (dark mode, high contrast, motion) and what ``dev`` holds for the
Developer screen, on hand-made ``Prefs``; loading and saving are ``test_prefs.py``'s.
"""

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from pycon_us import prefs as prefs_module
from pycon_us.prefs import (
    HIGH_CONTRAST_SETTINGS,
    Prefs,
    parse_feed_url,
    with_dev_options,
)
from pycon_us.reminder_settings import ReminderSettings

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
        reminders=ReminderSettings(session_lead=10, lightning=False, primer="accepted"),
        dev={"unlocked": True},
        start_screen="now",
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
    assert (prefs.reminders, prefs.dev) == (ReminderSettings(), {})  # D-198
    assert prefs.start_screen == "auto"  # Reset app is a fresh install's (D-198)
    assert prefs.os_dark and prefs.reduce_motion and prefs.screen_reader
    assert prefs.loaded is True
