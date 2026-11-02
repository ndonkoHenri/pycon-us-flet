"""The sponsors door staff scan leads for: the reply, read; the filter; the saved choice.

``lead_sponsors`` (API-09) answers ``{"sponsors": [{id, name, booth_number?,
logo_url?}]}``. Ionic stripped one ``"`` from each end of a name (``/^"|"$/``,
``map.ts`` 59, 83, 93, 317), since some arrived JSON-quoted, and compared those names
to find the chosen sponsor (LEAD-05, LEAD-06). Here a sponsor is found by its id, kept
as a string because the capture query and the outbox's ``sponsor_id`` carry it so
(STORE-11); the name is only shown. The chosen one is kept as ``{id, name, logo_url}``
under ``pycon.staff_<year>_sponsor`` (``services/pref_keys.py``'s ``staff_sponsor()``).
"""

import re
from dataclasses import dataclass
from typing import Any

from pycon_us.core.queries import fold

_QUOTES = re.compile(r'^"|"$')
"""Ionic's quote stripping: one ``"`` at each end, no more."""


@dataclass(frozen=True)
class LeadSponsor:
    """A sponsor staff can scan leads for.

    Attributes:
        id: Its id, as a string (``sponsor_id`` is sent as one).
        name: Its name, without the surrounding quotes some replies carry.
        booth: Its booth number, or None without one.
        logo_url: Its logo's URL, or None without one.
    """

    id: str
    name: str
    booth: str | None = None
    logo_url: str | None = None


def snapshot(sponsor_id: str | None, sponsor_name: str | None) -> LeadSponsor | None:
    """Return the sponsor a lead was scanned for, from its outbox row's snapshot.

    Args:
        sponsor_id: The row's ``sponsor_id``; None for a sponsor's own lead.
        sponsor_name: The row's ``sponsor_name``.

    Returns:
        The sponsor, or None for a sponsor's own lead.
    """
    if sponsor_id is None:
        return None
    return LeadSponsor(sponsor_id, sponsor_name or sponsor_id)


def parse_sponsors(reply: object) -> tuple[LeadSponsor, ...]:
    """Read the ``lead_sponsors`` reply into sponsors sorted by name (API-09).

    An entry without a usable id or name is left out, and so is a second entry with
    an id already read: one bad row never hides the others.

    Args:
        reply: The decoded reply.

    Returns:
        The sponsors, sorted by name (case and accents folded), then by id.

    Raises:
        TypeError: The reply is not ``{"sponsors": [...]}``.
    """
    entries = reply.get("sponsors") if isinstance(reply, dict) else None
    if not isinstance(entries, list):
        raise TypeError("lead_sponsors: no sponsors list")
    sponsors: dict[str, LeadSponsor] = {}
    for entry in entries:
        sponsor = _sponsor(entry)
        if sponsor is not None and sponsor.id not in sponsors:
            sponsors[sponsor.id] = sponsor
    return tuple(sorted(sponsors.values(), key=lambda s: (fold(s.name), s.id)))


def _sponsor(entry: object) -> LeadSponsor | None:
    """Return one reply entry as a sponsor, or None when it has no id or no name."""
    if not isinstance(entry, dict):
        return None
    ident = _text(entry.get("id"))
    raw_name = entry.get("name")
    name = (
        _QUOTES.sub("", raw_name.strip()).strip() if isinstance(raw_name, str) else ""
    )
    if not ident or not name:
        return None
    return LeadSponsor(
        ident, name, _text(entry.get("booth_number")), _text(entry.get("logo_url"))
    )


def _text(value: object) -> str | None:
    """Return a string or an integer as non-empty text, else None (a bool is neither)."""
    if isinstance(value, bool) or not isinstance(value, str | int):
        return None
    return str(value).strip() or None


def filter_sponsors(
    sponsors: tuple[LeadSponsor, ...], query: str
) -> tuple[LeadSponsor, ...]:
    """Return the sponsors whose name or booth holds every word of ``query`` (LEAD-05).

    Folded as search folds (D-46), each word anywhere as a substring, so "sam" finds
    Sample Systems and "101" the sponsor at booth 101.

    Args:
        sponsors: The sponsors, in their order.
        query: What the user typed.

    Returns:
        The sponsors found, in their order; ``sponsors`` itself without a word.
    """
    words = fold(query).split()
    if not words:
        return sponsors
    return tuple(
        sponsor
        for sponsor in sponsors
        if all(word in fold(f"{sponsor.name} {sponsor.booth or ''}") for word in words)
    )


def to_stored(sponsor: LeadSponsor) -> dict[str, Any]:
    """Return the chosen sponsor as ``pycon.staff_<year>_sponsor`` keeps it (STORE-11).

    Args:
        sponsor: The sponsor chosen.

    Returns:
        ``{"id", "name", "logo_url"}``; the booth is not kept, the chip shows none.
    """
    return {"id": sponsor.id, "name": sponsor.name, "logo_url": sponsor.logo_url}


def from_stored(value: dict[str, Any]) -> LeadSponsor | None:
    """Return the chosen sponsor ``pycon.staff_<year>_sponsor`` holds, or None.

    Args:
        value: The stored object; ``{}`` when nothing was chosen.

    Returns:
        The sponsor, or None when nothing was chosen or the value is unusable.
    """
    ident, name, logo = value.get("id"), value.get("name"), value.get("logo_url")
    if not isinstance(ident, str) or not ident or not isinstance(name, str) or not name:
        return None
    return LeadSponsor(ident, name, logo_url=logo if isinstance(logo, str) else None)
