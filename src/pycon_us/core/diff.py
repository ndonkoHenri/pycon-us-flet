"""What changed between two processed feeds: the change log's diff (D-47, NEW-04).

`diff(old, new)` compares the sessions of two feeds by id (D-42) and says what an
attendee would notice: a session added or removed, or one whose time, room or title
changed. It reads only what each side's model holds, so it is pure, and both sides are
always parsed by the current code from raw bytes (the cache keeps them, D-47): a change of
the parser can never show up as a change of the schedule.

Sessions of the collapsed kinds (`rules.COLLAPSED_KINDS`) are left out. A collapsed
break or poster row's id holds its start (`<kind>-<room>-<start>`, D-123), so a moved
break would read as one removed and one added. Poster details copy their Posters row's
time and place and have no row of their own (DATA-07), so a moved Posters row would read
as all of them changed at once, and a missing one as all of them removed.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.rules import COLLAPSED_KINDS
from pycon_us.core.timefmt import instant


class ChangeKind(StrEnum):
    """What changed about a session; the order is the order of one session's changes.

    Attributes:
        ADDED: The new feed lists a session the old one did not.
        REMOVED: The new feed no longer lists it ("Removed from the latest schedule",
            never "cancelled", D-47).
        TIME: Its shown start or its end moved.
        ROOM: Its location changed.
        TITLE: Its cleaned name changed.
    """

    ADDED = "added"
    REMOVED = "removed"
    TIME = "time"
    ROOM = "room"
    TITLE = "title"


_KIND_ORDER = {kind: index for index, kind in enumerate(ChangeKind)}


@dataclass(frozen=True)
class Listing:
    """A session as one feed lists it: the values the diff compares.

    They are what a row shows, so the change log can say a session's old and new values,
    and still show a removed session's last title, time and room once the feed has
    dropped it (D-255).

    Attributes:
        title: The cleaned name (`Session.name`).
        start: The start a row shows (`Session.display_start`). It moves with
            `Session.start`; the Job Fair's is 30 minutes earlier (DATA-11).
        end: The end.
        location: The room text; several rooms are joined by ", " (`Session.location`).
    """

    title: str
    start: datetime
    end: datetime
    location: str


@dataclass(frozen=True)
class Change:
    """One change to one session; a session whose time and room changed has two.

    Attributes:
        id: The session's id (D-42).
        kind: What changed.
        old: The session in the old feed; None when it was added.
        new: The session in the new feed; None when it was removed.
    """

    id: str
    kind: ChangeKind
    old: Listing | None
    new: Listing | None

    @property
    def latest(self) -> Listing:
        """The newest listing of the session: the new one, or the last one if removed."""
        listing = self.new or self.old
        assert listing is not None, "a change has at least one side"
        return listing

    @property
    def title(self) -> str:
        """The session's newest title, the one the change is listed under."""
        return self.latest.title


def _listing(session: Session) -> Listing:
    """Return what the diff compares of `session`.

    Args:
        session: A session of either feed.
    """
    return Listing(
        title=session.name,
        start=session.display_start,
        end=session.end,
        location=session.location,
    )


def diff(old: ConferenceData, new: ConferenceData) -> list[Change]:
    """Return what changed from `old` to `new`, session by session.

    Sessions are matched by id. A session only in `new` is added, one only in `old`
    removed; one in both gives a change for each of its time (shown start or end),
    location and title that differ. Breaks, Posters rows and posters are left out (see
    the module's docstring). The changes are ordered by the session's new start (the old
    one for a removal), then id, then kind (`ChangeKind`'s order), so the same two feeds
    always give the same list. Ids compare as text, not numbers: "1142" comes before
    "142", and "142" before "51". The same feed on both sides gives an empty list.

    Args:
        old: The feed the user saw.
        new: The feed that replaces it.
    """
    before = _compared(old)
    after = _compared(new)
    changes = [
        Change(key, ChangeKind.REMOVED, _listing(session), None)
        for key, session in before.items()
        if key not in after
    ]
    for key, session in after.items():
        previous = before.get(key)
        if previous is None:
            changes.append(Change(key, ChangeKind.ADDED, None, _listing(session)))
        else:
            changes.extend(_changes(key, _listing(previous), _listing(session)))
    changes.sort(key=_order)
    return changes


def _compared(data: ConferenceData) -> dict[str, Session]:
    return {
        key: session
        for key, session in data.sessions.items()
        if session.kind not in COLLAPSED_KINDS
    }


def _changes(key: str, old: Listing, new: Listing) -> Iterator[Change]:
    # As instants: one zone's times compare by wall clock, so a move from 1:30 PDT to
    # 1:30 PST on the night summer time ends would go unseen (#535).
    if (instant(old.start), instant(old.end)) != (instant(new.start), instant(new.end)):
        yield Change(key, ChangeKind.TIME, old, new)
    if old.location != new.location:
        yield Change(key, ChangeKind.ROOM, old, new)
    if old.title != new.title:
        yield Change(key, ChangeKind.TITLE, old, new)


def _order(change: Change) -> tuple[datetime, str, int]:
    return instant(change.latest.start), change.id, _KIND_ORDER[change.kind]
