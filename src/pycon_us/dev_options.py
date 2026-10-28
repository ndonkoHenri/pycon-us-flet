"""Developer options: the keys of ``Prefs.dev`` and the helpers that edit them (D-73, D-187).

``Prefs`` reads these keys (``developer_unlocked``, ``fake_now``, ``feed_url``,
``mock_api_url``); the Developer and About this app screens write them through
``Prefs.save(dev=...)``. Split from ``prefs.py`` at D-66's ~400 lines (#737).
"""

from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

DEV_UNLOCKED = "unlocked"
"""``Prefs.dev`` key: True once 7 taps on About this app's version unlocked Developer."""

DEV_FAKE_NOW = "fake_now"
"""``Prefs.dev`` key: the fake clock's start, an ISO 8601 instant with its offset."""

DEV_FEED_URL = "feed_url"
"""``Prefs.dev`` key: the feed URL that refreshes use instead of the year's."""

DEV_MOCK_API_URL = "mock_api_url"
"""``Prefs.dev`` key: the mock API's base URL; set, the private-API features show (D-51)."""


def with_dev_options(
    dev: dict[str, Any], *, fake_now: datetime | None, feed_url: str | None
) -> dict[str, Any]:
    """Return ``dev`` with the fake clock and the feed URL set; None removes one (D-187).

    The other keys, the unlock among them, are kept. Pass the result to ``Prefs.save``.

    Args:
        dev: The current ``Prefs.dev``.
        fake_now: The fake clock's start (aware), or None for real time.
        feed_url: The feed URL, or None for the year's.
    """
    options = {k: v for k, v in dev.items() if k not in (DEV_FAKE_NOW, DEV_FEED_URL)}
    if fake_now is not None:
        options[DEV_FAKE_NOW] = fake_now.isoformat()
    if feed_url is not None:
        options[DEV_FEED_URL] = feed_url
    return options


def parse_feed_url(text: str) -> str | None:
    """Return the feed URL the field names, or None when it is empty (the year's feed).

    Args:
        text: An ``http://`` or ``https://`` URL; plain HTTP for a test server on the
            laptop (testing-and-quality.md §5.2).

    Raises:
        ValueError: The text is not such a URL; its message is the field's error.
    """
    text = text.strip()
    if not text:
        return None
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Use an http:// or https:// address")
    return text
