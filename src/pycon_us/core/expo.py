"""The expo's booths matched to the feed's sponsors, and the job fair's tables (D-254).

``map.toml`` draws the booths (``year_map.Booth``) and the feed says who is at each one
(``Sponsor.booth``). ``expo_booths()`` joins them by number, compared as text: a booth
lists every sponsor with its number, so a shared booth keeps all its exhibitors, where
Ionic kept one name; and the sponsors whose booth has no rectangle are kept apart, so
the expo List can still show them and a test can name the gap. The answer is built
once per feed version (D-153), so the expo's memoised views get the same objects on
every render.

The expo List (#404) has one row per exhibitor (D-254): ``list_rows()`` makes them,
by booth number in natural order with a shared booth's exhibitors together by name, or
by name (``by_name()``), and a booth without an exhibitor is a row by its label.
``filter_rows()`` and ``filter_sponsors()`` keep those whose name or booth number holds
every word of the List's filter, folded as search folds (D-46). ``booth_entries()``
gives search's Places the same exhibitors, each at its booth, the ones off the plan
among them (EXPO-04, #406).

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
class ExpoRow:
    """One row of the expo List: an exhibitor at its booth, or a booth without one.

    Attributes:
        item: The booth and all its exhibitors, which a tap selects on the plan.
        sponsor: The row's exhibitor; None for a booth without one, or before the feed.
        search_text: The booth's number and the row's name, folded (D-46).
    """

    item: ExpoBooth
    sponsor: Sponsor | None = None
    search_text: str = ""

    @property
    def number(self) -> str:
        """The booth's number, as ``map.toml`` writes it."""
        return self.item.booth.number

    @property
    def name(self) -> str:
        """The exhibitor's name, else the booth's label; "" for neither."""
        return self.sponsor.name if self.sponsor else self.item.booth.label

    @property
    def key(self) -> str:
        """The row's key, unique in the List: "726.pybeach", or "407" alone."""
        return f"{self.number}.{self.sponsor.slug}" if self.sponsor else self.number


@dataclass(frozen=True)
class BoothEntry:
    """One exhibitor at its booth, or a booth without one, as search finds it (#406).

    Attributes:
        number: The booth's number, as the feed and ``map.toml`` write it.
        name: The exhibitor's name, else the booth's label; "" for neither.
        slug: The exhibitor's slug; "" for a booth without one.
        placed: Whether the expo plan draws the booth; False for a sponsor's booth
            that ``map.toml`` does not have, which opens the List's line instead.
    """

    number: str
    name: str
    slug: str = ""
    placed: bool = True

    @property
    def key(self) -> str:
        """The entry's key, unique in the year: "726.pybeach", or "407" alone."""
        return f"{self.number}.{self.slug}" if self.slug else self.number


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


def list_rows(booths: Sequence[ExpoBooth]) -> tuple[ExpoRow, ...]:
    """Return the List's rows in booth order: one per exhibitor, or one for the booth.

    A shared booth's rows follow its exhibitors' folded-name order (``expo_booths()``),
    so they stay together under its number (D-254).

    Args:
        booths: The booths with their exhibitors, in natural number order.
    """
    return tuple(
        _row(item, sponsor) for item in booths for sponsor in (item.sponsors or (None,))
    )


def booth_entries(expo: Expo) -> tuple[BoothEntry, ...]:
    """Return every exhibitor at its booth, the booths off the plan among them (#406).

    One entry per List row (``list_rows()``, D-254), and one per sponsor of
    ``Expo.unplaced``, all by booth number in natural order, a shared booth's
    exhibitors in folded-name order.

    Args:
        expo: The year's expo (``expo_booths()``).
    """
    placed = [
        BoothEntry(
            row.number, row.name, row.sponsor.slug if row.sponsor else "", placed=True
        )
        for row in list_rows(expo.booths)
    ]
    unplaced = [
        BoothEntry(sponsor.booth or "", sponsor.name, sponsor.slug, placed=False)
        for sponsor in expo.unplaced
    ]
    # A stable sort: each part is in booth order already, its exhibitors by name.
    return tuple(
        sorted(placed + unplaced, key=lambda entry: room_sort_key(entry.number))
    )


def by_name(rows: Sequence[ExpoRow]) -> tuple[ExpoRow, ...]:
    """Return ``rows`` by folded name (D-46), then booth number; nameless rows last.

    Args:
        rows: The List's rows (``list_rows()``).
    """
    return tuple(
        sorted(
            rows,
            key=lambda row: (not row.name, fold(row.name), room_sort_key(row.number)),
        )
    )


def filter_rows(rows: tuple[ExpoRow, ...], query: str) -> tuple[ExpoRow, ...]:
    """Return the rows whose number or name holds every word of ``query`` (D-46).

    A query with no word to match returns ``rows`` itself, as ``filter_projects()``
    does: "socal" finds 726's SoCal Python, "613" booth 613.

    Args:
        rows: The List's rows, in the order shown.
        query: What the user typed in the List's filter.
    """
    words = fold(query).split()
    if not words:
        return rows
    return tuple(row for row in rows if all(word in row.search_text for word in words))


def filter_sponsors(sponsors: tuple[Sponsor, ...], query: str) -> tuple[Sponsor, ...]:
    """Return the unplaced sponsors whose booth number or name holds every word.

    Args:
        sponsors: ``Expo.unplaced``.
        query: What the user typed in the List's filter.
    """
    words = fold(query).split()
    if not words:
        return sponsors
    return tuple(
        sponsor
        for sponsor in sponsors
        if all(word in fold(f"{sponsor.booth} {sponsor.name}") for word in words)
    )


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


def _row(item: ExpoBooth, sponsor: Sponsor | None) -> ExpoRow:
    """One List row, with the folded text its filter matches."""
    name = sponsor.name if sponsor else item.booth.label
    return ExpoRow(item, sponsor, fold(f"{item.booth.number} {name}"))


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
