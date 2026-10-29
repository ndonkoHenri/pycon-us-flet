"""Door check's sessions, in order, by day and searched, and the session chosen (#764).

The picker (``screens/door_session.py``) lists a door category's products as sessions
(DOOR-02): in ``product_sort_key()``'s order, by the date that starts each name (Ionic's
pattern; ``session_parts()`` splits it from the title), under a heading per day, the
undated ones last; a search keeps the sessions whose title or day and time hold every
word (D-46). The choice is a ``DoorChoice``: one session, or all of a category's, with
the label the scan screen's chip shows. ``pycon.staff_door_session`` keeps it
(``to_stored()``, ``from_stored()``), a staff key (D-414, D-433).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, TypeIs

from pycon_us.core.check_in import Catalog, Category
from pycon_us.core.queries import fold

ALL_SESSIONS = "All sessions"
"""The chip's words for a whole category: "Tutorials · All sessions"."""

SEPARATOR = " \N{MIDDLE DOT} "
"""Between a chip's two parts: "Async in depth · Wed 1:30 PM"."""

_WHEN = re.compile(
    r"^(?:(\w{3,9})\s+)?(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})"
    r"\s+(\d{1,2}):(\d{2})\s+(AM|PM)\b",
    re.IGNORECASE | re.ASCII,
)
"""Ionic's session date (``door-check.page.ts`` 92), "Wed May 13 9:00 AM", weekday
optional; ASCII ``\\w`` and ``\\d`` as in JavaScript."""

_DATE_SEPARATOR = re.compile(r"^\s*[-\u2013\u2014:]?\s*")
"""What stands between a session's date and its title, " - " in the seed."""

_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
           "dec")  # fmt: skip

_NEVER = datetime.min.replace(tzinfo=UTC)
"""The start an undated product's sort key holds, so every key compares."""


@dataclass(frozen=True)
class DoorSession:
    """A door product as the picker lists it.

    Attributes:
        id: The product's id.
        title: Its title, "All about decorators"; the whole name when it has none.
        when: Its day and time as the name gives them, "Wed 9:00 AM"; "" undated.
        day: The day it is on in the conference year, or None undated.
        time: Its start, "9:00 AM"; "" undated.
    """

    id: int
    title: str
    when: str
    day: date | None
    time: str


@dataclass(frozen=True)
class DoorChoice:
    """The session, or the sessions, Door check checks in for.

    Attributes:
        category_id: Their category's id.
        product_ids: The product ids, the door's ``fetch_products`` and inventory ids.
        label: What the chip shows, "Async in depth · Wed 1:30 PM".
        all_sessions: It is every session of the category ("All sessions").
    """

    category_id: int
    product_ids: tuple[int, ...]
    label: str
    all_sessions: bool = False


def product_sort_key(name: str, year: int) -> tuple[int, datetime, str, str]:
    """Return a key that sorts products chronologically by the date in their name (DOOR-02).

    Ionic's pattern (``door-check.page.ts`` 91-103), in ``year`` rather than its
    hard-coded 2026: a session sorts by its start; a name without a valid date (a shirt
    size, "Feb 30") sorts after every dated one. Ties go by folded name, then the name.

    Args:
        name: The product's name, such as "Wed May 13 9:00 AM - All about decorators".
        year: The conference year (``config.YEAR``).

    Returns:
        The sort key.
    """
    start = _start(name, year)
    tie = (fold(name), name)
    return (0, start, *tie) if start is not None else (1, _NEVER, *tie)


def _start(name: str, year: int) -> datetime | None:
    """Return the start a product's name gives in ``year``, or None without a valid one."""
    match = _WHEN.match(name)
    if match is None:
        return None
    _, month, day, hour, minute, half = match.groups()
    if not 1 <= int(hour) <= 12:
        return None
    hour_24 = int(hour) % 12 + (12 if half.upper() == "PM" else 0)
    month_number = _MONTHS.index(month.lower()) + 1
    try:  # A wall-clock time, made aware only to compare, as Ionic's Date.UTC.
        return datetime(year, month_number, int(day), hour_24, int(minute), tzinfo=UTC)
    except ValueError:
        return None


def session_parts(name: str) -> tuple[str, str] | None:
    """Split a session product's name into its title and its day and time.

    "Wed May 13 9:00 AM - All about decorators" is ("All about decorators",
    "Wed 9:00 AM"); without a weekday the date stays ("May 13 9:00 AM").

    Args:
        name: The product's name.

    Returns:
        The title and when it is, or None for a name without a date or a title.
    """
    match = _WHEN.match(name)
    if match is None:
        return None
    weekday, month, day, hour, minute, half = match.groups()
    title = _DATE_SEPARATOR.sub("", name[match.end() :], count=1).strip()
    if not title:
        return None
    day_part = weekday or f"{month} {day}"
    return title, f"{day_part} {hour}:{minute} {half.upper()}"


def door_sessions(
    catalog: Catalog, category: int, year: int
) -> tuple[DoorSession, ...]:
    """Return a category's sessions, chronologically (``product_sort_key()``, DOOR-02).

    Args:
        catalog: The door's catalog (``door_catalog()``).
        category: The category's id.
        year: The conference year, which a name's date is in.
    """
    products = [p for p in catalog.products if p.category == category]
    sessions = []
    for product in sorted(products, key=lambda p: product_sort_key(p.name, year)):
        dated, start, *_ = product_sort_key(product.name, year)
        if dated == 0:  # a date-only name keeps its day; its name is its title
            title, when = session_parts(product.name) or (product.name, "")
            time = f"{start.hour % 12 or 12}:{start.minute:02d} "
            time += "AM" if start.hour < 12 else "PM"
            sessions.append(DoorSession(product.id, title, when, start.date(), time))
        else:  # "Feb 30 …", or no date: listed by its whole name, last
            sessions.append(DoorSession(product.id, product.name, "", None, ""))
    return tuple(sessions)


def by_day(
    sessions: Iterable[DoorSession],
) -> tuple[tuple[date | None, tuple[DoorSession, ...]], ...]:
    """Return the sessions under their day, in their order; the undated ones under None.

    Args:
        sessions: Sessions in ``door_sessions()``' order, so a day's are together and
            the undated ones last.
    """
    groups: list[tuple[date | None, list[DoorSession]]] = []
    for session in sessions:
        if not groups or groups[-1][0] != session.day:
            groups.append((session.day, []))
        groups[-1][1].append(session)
    return tuple((day, tuple(group)) for day, group in groups)


def filter_sessions(
    sessions: tuple[DoorSession, ...], query: str
) -> tuple[DoorSession, ...]:
    """Return the sessions whose title or day and time hold every word of ``query``.

    Folded as search folds (D-46), each word anywhere, so "async" finds "Async in
    depth" and "wed" Wednesday's sessions.

    Args:
        sessions: The sessions, in their order.
        query: What the user typed.

    Returns:
        The sessions found, in their order; ``sessions`` itself without a word.
    """
    words = fold(query).split()
    if not words:
        return sessions
    return tuple(
        session
        for session in sessions
        if all(word in fold(f"{session.title} {session.when}") for word in words)
    )


def choose_session(category: int, session: DoorSession) -> DoorChoice:
    """Return the choice of one session, labelled "Async in depth · Wed 1:30 PM".

    Args:
        category: Its category's id.
        session: The session.
    """
    label = (
        f"{session.title}{SEPARATOR}{session.when}" if session.when else session.title
    )
    return DoorChoice(category, (session.id,), label)


def choose_all(category: Category, sessions: Iterable[DoorSession]) -> DoorChoice:
    """Return the choice of every session of ``category``, "Tutorials · All sessions".

    Args:
        category: The category.
        sessions: Its sessions; their ids are what the door checks in for.
    """
    ids = tuple(session.id for session in sessions)
    return DoorChoice(
        category.id, ids, f"{category.name}{SEPARATOR}{ALL_SESSIONS}", True
    )


def to_stored(choice: DoorChoice) -> dict[str, Any]:
    """Return the choice as ``pycon.staff_door_session`` keeps it.

    Args:
        choice: The choice made on the picker.

    Returns:
        ``{"category_id", "product_ids", "label", "all"}``.
    """
    return {
        "category_id": choice.category_id,
        "product_ids": list(choice.product_ids),
        "label": choice.label,
        "all": choice.all_sessions,
    }


def from_stored(value: dict[str, Any]) -> DoorChoice | None:
    """Return the choice ``pycon.staff_door_session`` holds, or None.

    Args:
        value: The stored object; ``{}`` when nothing was chosen.

    Returns:
        The choice, or None when nothing was chosen or the value is unusable (no
        category, no product, an id that isn't an integer, no label).
    """
    category, ids = value.get("category_id"), value.get("product_ids")
    label, every = value.get("label"), value.get("all")
    if not _is_id(category) or not isinstance(ids, list) or not ids:
        return None
    if not all(_is_id(i) for i in ids) or not isinstance(label, str) or not label:
        return None
    return DoorChoice(category, tuple(ids), label, every is True)


def _is_id(value: object) -> TypeIs[int]:
    """Return whether ``value`` is an id as the catalog reads them: an int, not a bool."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
