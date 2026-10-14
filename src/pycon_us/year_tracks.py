"""The track registry, the Tracks hub's own pages, and the registry's checks (D-228).

``conference.toml``'s ``[[tracks]]`` build into ``Track`` below, through
``year_schema.build()``, as ``config.ConferenceInfo.tracks`` (DATA-14, DATA-28, DATA-29).
``check_tracks()`` then checks the registry's rules. ``HUB_PAGES`` and ``KEYNOTE_TRACKS``
name tracks by key, so they live here with the registry (D-207, D-217), free of Flet.
Split from ``config.py`` at D-66's ~400 lines, as ``year_pages`` and ``year_keynotes``
were.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from pycon_us.year_schema import YearDataError

_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
"""A track slug: lower-case words joined by single hyphens (DATA-29)."""

TRACK_GROUPS = ("talks", "hands-on", "community", "logistics")
"""The filter-sheet groups a track can belong to, in display order (DATA-14)."""

type TrackFormat = Literal["short", "plural", "long"]


@dataclass(frozen=True)
class Track:
    """One entry of the track registry (DATA-14, DATA-28).

    Attributes:
        key: The track as feed processing names it: the feed's kind with its first letter
            upper-cased (``Ai``, ``Lightning-talks``, ``Open Space``).
        short: The name on badges and rows (``AI``).
        plural: The title of a list of its sessions (``Future of AI with Python``).
        long: The full name, for session detail (``The Future of AI with Python``).
        icon: The name of an outlined ``ft.Icons`` member (D-27).
        group: Its group in the filter sheet, one of ``TRACK_GROUPS``.
        slug: Its page's segment in ``/more/tracks/<slug>`` (DATA-29): written out,
            never derived, so a key's spelling (``Ai``, ``Lightning-talks``) never
            leaks into a route; lower case, words joined by ``-``.
        legend: One line on what its sessions are, for the Tracks hub and the track's
            page (EVT-04): "Talks given in Spanish".
        new: Whether the track is new this year: the hub and its page show a "New
            track" badge (SCHED-21).
    """

    key: str
    short: str
    plural: str
    long: str
    icon: str
    group: str
    slug: str
    legend: str
    new: bool = False


HUB_PAGES: dict[str, str | None] = {
    "sprints": None,
    "lightning-talks": "Lightning-talks",
    "open-spaces": "Open Space",
    "keynotes": "Keynote",
}
"""The Tracks hub's pages of their own, by segment under ``/more/tracks``, with the key of
the track each is the page of (the feed's kinds, DATA-14; the sprints are no track, D-126).

More's pages, also the hub's children, so Back returns to the hub (D-207). The routes
list them before ``:slug``, so the loader refuses a track slug that names another's page.
Here, with the registry, the loader stays free of Flet.
"""

KEYNOTE_TRACKS = ("Keynote", "Plenary")
"""The tracks a ``[[keynotes]]`` entry's session can be of: the keynotes' own
(``HUB_PAGES["keynotes"]``), and the plenaries', since the feed files the panels there.
The loader and the snapshot tool refuse an entry on any other track (D-217)."""


def check_tracks(tracks: Iterable[Track], file: str) -> None:
    """Check the registry's rules: unique keys and slugs, hub pages, legends and groups.

    Args:
        tracks: ``conference.toml``'s ``[[tracks]]``, in file order.
        file: The file as errors name it, ``2026/conference.toml``.

    Raises:
        YearDataError: An entry breaks a rule; the message names the entry and the field.
    """
    seen: set[str] = set()
    slugs: set[str] = set()
    for index, track in enumerate(tracks):
        if track.key in seen:
            raise YearDataError(
                f"{file}: tracks[{index}].key: duplicate track {track.key!r}"
            )
        seen.add(track.key)
        if not _SLUG.fullmatch(track.slug):
            raise YearDataError(
                f"{file}: tracks[{index}].slug: {track.slug!r} is not lower-case "
                "words joined by '-'"
            )
        if track.slug in slugs:
            raise YearDataError(
                f"{file}: tracks[{index}].slug: duplicate slug {track.slug!r}"
            )
        slugs.add(track.slug)
        _check_hub_page(track, file, index)
        if not track.legend.strip():
            raise YearDataError(f"{file}: tracks[{index}].legend: is empty")
        if track.group not in TRACK_GROUPS:
            raise YearDataError(
                f"{file}: tracks[{index}].group: {track.group!r} is not one of {TRACK_GROUPS}"
            )


def _check_hub_page(track: Track, file: str, index: int) -> None:
    """Refuse a track slug that names a page of the hub's other than the track's own.

    The hub's pages (``HUB_PAGES``) come before ``:slug`` under ``/more/tracks``
    (D-207), so a track at ``sprints`` would have no page. A track with a page of its
    own keeps the page's segment as its slug: its hub row pushes
    ``/more/tracks/<slug>``, which must be that page.
    """
    own = next((seg for seg, key in HUB_PAGES.items() if key == track.key), None)
    if own is not None and track.slug != own:
        raise YearDataError(
            f"{file}: tracks[{index}].slug: expected {own!r}, the segment of "
            f"the track's own page, /more/tracks/{own}"
        )
    if own is None and track.slug in HUB_PAGES:
        raise YearDataError(
            f"{file}: tracks[{index}].slug: {track.slug!r} is the segment of "
            f"another page, /more/tracks/{track.slug}"
        )
