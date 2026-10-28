"""Door check's sessions, in order, by day and searched, and the session chosen (#764).

The picker (``screens/door_session.py``) lists a door category's products as sessions
(DOOR-02): in ``product_sort_key()``'s order, under a heading per day, the undated ones
last; a search keeps the sessions whose title or day and time hold every word (D-46).
The choice is a ``DoorChoice``: one session, or all of a category's, with the label the
scan screen's chip shows. ``pycon.staff_door_session`` keeps it (``to_stored()``,
``from_stored()``), a staff key (D-414, D-433).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any, TypeIs

from pycon_us.core.check_in import (
    Catalog,
    Category,
    product_sort_key,
    session_parts,
)
from pycon_us.core.queries import fold

ALL_SESSIONS = "All sessions"
"""The chip's words for a whole category: "Tutorials · All sessions"."""

SEPARATOR = " \N{MIDDLE DOT} "
"""Between a chip's two parts: "Async in depth · Wed 1:30 PM"."""


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
