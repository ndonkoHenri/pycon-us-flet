"""The expo's booths matched to the feed's sponsors, and the job fair's tables (D-254).

``map.toml`` draws the booths (``year_map.Booth``) and the feed says who is at each one
(``Sponsor.booth``). ``expo_booths()`` joins them by number, compared as text: a booth
lists every sponsor with its number, so a shared booth keeps all its exhibitors, where
Ionic kept one name; and the sponsors whose booth has no rectangle are kept apart, so
the expo List can still show them and a test can name the gap. The answer is built
once per feed version (D-153), so the expo's memoised views get the same objects on
every render.

The job fair's tables come from the feed alone (``Sponsor.job_fair_table``):
``job_fair_tables()`` lists every sponsor with a table, tables in natural order (T2
before T10) and a shared table's sponsors by folded name, each with its open roles
(MAP-04, SPON-10). ``is_job_fair()`` finds the sessions that show the job fair's plan
card (SESS-10).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING
from weakref import WeakKeyDictionary

from pycon_us.core.jobs import listings_of
from pycon_us.core.models import ConferenceData, Session, Sponsor
from pycon_us.core.queries import fold
from pycon_us.core.slugs import room_sort_key

if TYPE_CHECKING:  # the year data's type only: core never imports the loader (D-67)
    from pycon_us.year_map import Booth


@dataclass(frozen=True)
class ExpoBooth:
    """One booth on the expo plan and the sponsors the feed puts at it.

    Attributes:
        booth: The booth's rectangle, number and label, from ``map.toml``.
        sponsors: Every sponsor whose ``booth`` is its number, in folded-name order
            (D-46); empty for a booth without an exhibitor, which its label names.
    """

    booth: Booth
    sponsors: tuple[Sponsor, ...]


@dataclass(frozen=True)
class Expo:
    """The expo: its booths with their sponsors, and the sponsors off the plan.

    Attributes:
        booths: Every booth of ``map.toml``, by number in natural order.
        unplaced: The sponsors with a booth number that no booth of ``map.toml`` has,
            by booth number in natural order, then by folded name.
    """

    booths: tuple[ExpoBooth, ...] = ()
    unplaced: tuple[Sponsor, ...] = ()


@dataclass(frozen=True)
class JobFairTable:
    """One sponsor at its job fair table: a row of the Map's Job fair pane (MAP-04).

    Attributes:
        table: The table, as the feed writes it ("T2").
        sponsor: The sponsor the feed puts at it; a shared table has an entry per
            sponsor.
        roles: The open roles of its job listings (``JobListing.roles``); 0 without a
            listing, and for a long-form listing, which lists none (D-278).
    """

    table: str
    sponsor: Sponsor
    roles: int


def expo_booths(data: ConferenceData, booths: Sequence[Booth]) -> Expo:
    """Return the year's booths with their sponsors, and the sponsors with no booth.

    A sponsor without a booth number is in neither. A year without booths has no expo,
    so its answer is empty, even when its sponsors have booth numbers.

    Args:
        data: The processed feed.
        booths: The year's booths (``MapData.booths``).

    Returns:
        The expo, the same object for the same feed and booths (D-153).
    """
    key = tuple(booths)
    results = _MEMO.setdefault(data, {})
    if key not in results:
        results[key] = _build(data, key)
    return results[key]


def job_fair_tables(data: ConferenceData) -> tuple[JobFairTable, ...]:
    """Return every sponsor with a job fair table, tables in natural order (D-254).

    A shared table's sponsors come together in folded-name order (D-46); a sponsor
    without a table is left out. Nothing else is matched: the feed is the list, which
    a refresh can correct during the conference (the printed plan cannot).

    Args:
        data: The processed feed.

    Returns:
        The rows, the same tuple for the same feed (D-153).
    """
    if data not in _TABLES:
        sponsors = [
            sponsor
            for level in data.sponsor_levels
            for sponsor in level.sponsors
            if sponsor.job_fair_table
        ]
        ordered = sorted(
            sponsors,
            key=lambda sponsor: (
                room_sort_key(sponsor.job_fair_table or ""),
                fold(sponsor.name),
            ),
        )
        _TABLES[data] = tuple(
            JobFairTable(
                sponsor.job_fair_table or "",
                sponsor,
                sum(len(listing.roles) for listing in listings_of(data, sponsor)),
            )
            for sponsor in ordered
        )
    return _TABLES[data]


def is_job_fair(session: Session) -> bool:
    """Return whether ``session`` is a Job Fair row, which shows the job fair's card.

    The feed has two (SESS-10), the event in the expo hall and the plenary that marks
    its time ("Job Fair & Community Showcase & Poster Sessions", "Job Fair & Community
    Showcase"; 2025's say "and"), with no kind or key of their own, so the name is
    matched, folded (D-46).

    Args:
        session: Any session.
    """
    return "job fair" in fold(session.name)


def _build(data: ConferenceData, booths: tuple[Booth, ...]) -> Expo:
    """Match ``booths`` to the feed's sponsors: ``expo_booths()``'s work."""
    if not booths:
        return Expo()
    by_number: dict[str, list[Sponsor]] = {}
    for level in data.sponsor_levels:
        for sponsor in level.sponsors:
            if sponsor.booth:
                by_number.setdefault(sponsor.booth, []).append(sponsor)
    placed = tuple(
        ExpoBooth(booth, _by_name(by_number.pop(booth.number, [])))
        for booth in sorted(booths, key=lambda booth: room_sort_key(booth.number))
    )
    unplaced = tuple(
        sponsor
        for number in sorted(by_number, key=room_sort_key)
        for sponsor in _by_name(by_number[number])
    )
    return Expo(placed, unplaced)


def _by_name(sponsors: list[Sponsor]) -> tuple[Sponsor, ...]:
    """Return ``sponsors`` in folded-name order (D-46)."""
    return tuple(sorted(sponsors, key=lambda sponsor: fold(sponsor.name)))


_MEMO: WeakKeyDictionary[ConferenceData, dict[tuple[Booth, ...], Expo]] = (
    WeakKeyDictionary()
)
"""``expo_booths()``'s answers, per feed. A processed feed is one object per feed version,
so it is the version in the key; weak, so a replaced feed's answers go with it."""

_TABLES: WeakKeyDictionary[ConferenceData, tuple[JobFairTable, ...]] = (
    WeakKeyDictionary()
)
"""``job_fair_tables()``'s answers, per feed, kept as ``_MEMO`` keeps the booths'."""
