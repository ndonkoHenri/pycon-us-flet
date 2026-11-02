"""The SharedPreferences key table (STORE-01; decisions §M, D-49, D-108).

Every small value the app keeps is a ``Pref`` here, prefixed ``pycon.``, with its type
and default: the app-wide keys as constants, the per-year ones built by the functions
below them (D-48, D-466). ``services/storage.py``'s ``Storage`` reads and writes them.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Pref[T]:
    """One SharedPreferences key, with the type and default of its value.

    The default's type is the value's type. A dict default means the value is
    stored as a JSON object string, since SharedPreferences cannot hold dicts.

    Attributes:
        key: The SharedPreferences key, prefixed ``pycon.``.
        default: The value used when the key is absent or unreadable.
    """

    key: str
    default: T


# ------------------------------------------------------------------ the key table (decisions §M)

PREFIX = "pycon."
"""Starts every key the app keeps in SharedPreferences, app-wide and per year."""

STAFF_PREFIX = "pycon.staff_"
"""Starts every staff key (the chosen sponsor, the scanner consent): what sign-out, an
account switch and Clear staff data remove with ``clear_prefs(STAFF_PREFIX)`` (D-414),
every year's, so a staff key added later is removed with the others."""

THEME: Pref[str] = Pref("pycon.theme", "system")
"""``system``, ``light`` or ``dark`` (THEME-01)."""

HIGH_CONTRAST: Pref[str] = Pref("pycon.high_contrast", "system")
"""``system``, ``on`` or ``off`` (THEME-01)."""

ONBOARDED: Pref[bool] = Pref("pycon.onboarded", False)
"""Whether the Welcome screen was seen (STORE-07)."""

EXCLUDED_TRACKS: Pref[list[str]] = Pref("pycon.excluded_tracks", ["Open Space"])
"""Track keys hidden from the schedule; a stored ``[]`` hides nothing (STORE-09)."""

REMINDERS: Pref[dict[str, Any]] = Pref("pycon.reminders", {})
"""Reminder settings, merged over the store's defaults (P2)."""

DEV: Pref[dict[str, Any]] = Pref("pycon.dev", {})
"""Developer options, merged over the store's defaults (D-73)."""

START_SCREEN: Pref[str] = Pref("pycon.start_screen", "auto")
"""``auto``, ``now`` or ``lead``: where a lead-retrieval account opens the app (D-16).
Not a staff key: a sign-out keeps it (#689)."""

SCANNER_CONSENT: Pref[bool] = Pref("pycon.staff_scanner_consent", False)
"""Whether this account agreed to scan only with consent (LEAD-04, STORE-06). A staff
key: a sign-out, a sign-in as another account and Clear staff data remove it, so the
Lead scanner asks again. In no store: the scanner reads it as it opens (D-423)."""

ACCOUNT: Pref[dict[str, Any]] = Pref("pycon.account", {})
"""The signed-in mock account: ``email``, ``nickname`` and ``features`` (P3, D-49).
Its key and secret are ``services/credentials.py``'s, never here."""


def favorites(year: int) -> Pref[list[str]]:
    """Return the key of a conference year's favourite session ids (D-48).

    Args:
        year: The conference year; ids are unique only within one year's feed.

    Returns:
        The ``pycon.<year>.favorites`` key, a ``list[str]`` that defaults to empty.
    """
    return Pref(f"pycon.{year}.favorites", [])


def favorites_sync(year: int) -> Pref[str]:
    """Return the key of what the account has of a year's favourites (D-55, D-406).

    Args:
        year: The conference year, as ``favorites(year)``'s.

    Returns:
        The ``pycon.<year>.favorites_sync`` key, a ``core.favorites_sync.SyncState``
        value; absent, ``merge``: the next pull takes the union. A sign-in and a
        sign-out remove it.
    """
    return Pref(f"pycon.{year}.favorites_sync", "merge")


def fetched(year: int) -> Pref[bool]:
    """Return the key that says a network feed of ``year`` was published (D-255).

    Saved by the install's first network publish for the year: from then on a refresh
    over the bundled snapshot is not diffed (``ChangeLog``). Reset app clears it.
    """
    return Pref(f"pycon.{year}.fetched", False)


def staff_sponsor(year: int) -> Pref[dict[str, Any]]:
    """Return the key of the sponsor door staff scan leads for in a year (D-466).

    ``{id, name, logo_url}`` (LEAD-05, STORE-11; ``core/lead_sponsors.py``); ``{}`` until
    one is chosen. A staff key (D-414), read as the Lead scanner opens and as it comes
    back on top, as the consent is (D-425).

    Args:
        year: The conference year; a sponsor's id means nothing in another year's data.

    Returns:
        The ``pycon.staff_<year>_sponsor`` key.
    """
    return Pref(f"{STAFF_PREFIX}{year}_sponsor", {})


def staff_door_session(year: int) -> Pref[dict[str, Any]]:
    """Return the key of the session or sessions Door check checks in for (D-466).

    ``{category_id, product_ids, label, all}`` (DOOR-02; ``core/door_sessions.py``); ``{}``
    until one is chosen. A staff key (D-414), read as Door check opens and as it comes
    back on top, as the sponsor is (D-425, D-433).

    Args:
        year: The conference year; a product's id means nothing in another year's data.

    Returns:
        The ``pycon.staff_<year>_door_session`` key.
    """
    return Pref(f"{STAFF_PREFIX}{year}_door_session", {})


def staff_swag_categories(year: int) -> Pref[list[str]]:
    """Return the key of the swag category ids Swag pickup hands out (D-466).

    As strings (SHIRT-01; #768): a SharedPreferences string list, as ``excluded_tracks``.
    A staff key (D-414), read as the screen opens, as the sponsor is (D-425); ids no
    longer in the catalog are ignored.

    Args:
        year: The conference year; a category's id means nothing in another year's data.

    Returns:
        The ``pycon.staff_<year>_swag_categories`` key.
    """
    return Pref(f"{STAFF_PREFIX}{year}_swag_categories", [])
