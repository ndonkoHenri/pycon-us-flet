"""The Code of Conduct tool's data: the directory, the name search, the count words.

`coc_attendees` (API-08) answers the attendee directory the name search runs over
(MASK-01); `coc_capture` answers the attendee an incident was recorded for. Ionic
matched raw lower-case substrings and coloured its list and its result card by two
different thresholds; here every word of a query must appear, folded as the app's
search folds (D-46), and one `count_level` serves the list and the result alike
(MASK-02). Nothing here is stored or logged: the directory lives in memory only
(D-56), and names, codes and emails never reach a log (D-72).
"""

from dataclasses import dataclass, field
from enum import Enum

from pycon_us.core.queries import fold

LIMIT = 25
"""The most rows a search returns; past it the screen asks for a narrower query."""


class Level(Enum):
    """How many incidents an attendee has on record, as the screens mark it.

    A screen maps a level to a colour **and** an icon, never a colour alone.
    """

    NONE = "none"
    NOTICE = "notice"
    HIGH = "high"


@dataclass(frozen=True)
class Attendee:
    """One attendee of the CoC directory.

    Attributes:
        code: The badge's access code, what a record is sent with.
        full_name: The full name, or `""`.
        nickname: The nickname, or `""`.
        badge_name: The name printed on the badge, or `""`.
        incidents: The incidents on record.
        folded: The three names folded and joined by spaces, what `search`
            matches; computed once, so a keystroke over thousands stays fast.
    """

    code: str
    full_name: str = ""
    nickname: str = ""
    badge_name: str = ""
    incidents: int = 0
    folded: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Fold the names once for `search`."""
        names = f"{self.full_name} {self.nickname} {self.badge_name}"
        object.__setattr__(self, "folded", fold(names))


@dataclass(frozen=True)
class Matches:
    """What a name search found.

    Attributes:
        rows: The attendees found, in the directory's order, at most the limit.
        more: Whether more matched than `rows` holds ("Refine your search").
    """

    rows: tuple[Attendee, ...]
    more: bool


@dataclass(frozen=True)
class Recorded:
    """The attendee an incident was just recorded for, from `coc_capture`'s reply.

    Attributes:
        name: The full name, else the nickname, else the badge name, else `""`.
        badge_name: The name printed on the badge, or `""`.
        email: The email, or None without one; the result card hides it until
            revealed (MASK-05).
        incidents: The incidents now on record, or None when the reply has no count:
            the incident is recorded all the same, so it is never an error.
    """

    name: str
    badge_name: str
    email: str | None
    incidents: int | None


def parse_directory(data: object) -> tuple[Attendee, ...]:
    """Read `coc_attendees`' `data` into the directory, sorted as Ionic sorted it.

    An entry without an access code is left out, a repeated code is kept once (the
    first read), and a missing or non-integer `violations` reads as 0: one bad row
    never hides the others.

    Args:
        data: The reply's `data` (the client unwraps the envelope).

    Returns:
        The attendees, sorted by their folded display name, then by code.

    Raises:
        TypeError: `data` is not a list.
    """
    if not isinstance(data, list):
        raise TypeError("coc_attendees: no attendee list")
    found: dict[str, Attendee] = {}
    for entry in data:
        attendee = _attendee(entry)
        if attendee is not None and attendee.code not in found:
            found[attendee.code] = attendee
    return tuple(sorted(found.values(), key=lambda a: (fold(display_name(a)), a.code)))


def _attendee(entry: object) -> Attendee | None:
    """Return one directory entry as an attendee, or None without an access code."""
    if not isinstance(entry, dict):
        return None
    code = _text(entry.get("access_code"))
    if not code:
        return None
    return Attendee(
        code,
        _text(entry.get("full_name")),
        _text(entry.get("nickname")),
        _text(entry.get("badge_name")),
        _count(entry.get("violations")) or 0,
    )


def _text(value: object) -> str:
    """Return a string stripped, anything else as `""`."""
    return value.strip() if isinstance(value, str) else ""


def _count(value: object) -> int | None:
    """Return a non-negative integer count, else None (a bool is no count)."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def display_name(attendee: Attendee) -> str:
    """Return the name a row shows: the full name, else nickname, badge name or code.

    Args:
        attendee: The attendee.
    """
    return (
        attendee.full_name or attendee.nickname or attendee.badge_name or attendee.code
    )


def search(attendees: tuple[Attendee, ...], query: str, limit: int = LIMIT) -> Matches:
    """Find the attendees whose names hold every word of `query` (MASK-02, D-46).

    Each folded word must appear, anywhere and as a substring, in the full name,
    nickname or badge name, so "ada ex" finds Ada Example and "jose" finds José.

    Args:
        attendees: The directory, in its order.
        query: What the user typed.
        limit: The most rows to return.

    Returns:
        The first `limit` attendees found, in the directory's order, and whether
        more matched; nothing for a query without a word.
    """
    words = fold(query).split()
    if not words:
        return Matches((), False)
    rows: list[Attendee] = []
    for attendee in attendees:
        if all(word in attendee.folded for word in words):
            if len(rows) == limit:
                return Matches(tuple(rows), True)
            rows.append(attendee)
    return Matches(tuple(rows), False)


def count_words(incidents: int) -> str:
    """Return the incident count in words, the same on every screen (MASK-02).

    Args:
        incidents: The incidents on record.

    Returns:
        "No incidents on record", "1 incident on record" or "3 incidents on record".
    """
    if incidents <= 0:
        return "No incidents on record"
    noun = "incident" if incidents == 1 else "incidents"
    return f"{incidents} {noun} on record"


def count_level(incidents: int) -> Level:
    """Return the level of an incident count, one threshold set for list and result.

    Ionic's list used these thresholds (>0 a warning, >2 danger); its result card
    used another (>1). One set keeps a row and its result the same (MASK-02).

    Args:
        incidents: The incidents on record.

    Returns:
        `NONE` for 0, `NOTICE` for 1 or 2, `HIGH` for 3 or more.
    """
    if incidents <= 0:
        return Level.NONE
    return Level.NOTICE if incidents <= 2 else Level.HIGH


def parse_capture(data: object) -> Recorded:
    """Read `coc_capture`'s `data` into the attendee the incident went to.

    Args:
        data: The reply's `data`: `{nickname, full_name, badge_name, email,
            violations}`.

    Returns:
        The attendee's names, email and new count.

    Raises:
        TypeError: `data` is not an object.
    """
    if not isinstance(data, dict):
        raise TypeError("coc_capture: no attendee in the reply")
    full_name, nickname = _text(data.get("full_name")), _text(data.get("nickname"))
    badge_name = _text(data.get("badge_name"))
    return Recorded(
        full_name or nickname or badge_name,
        badge_name,
        _text(data.get("email")) or None,
        _count(data.get("violations")),
    )
