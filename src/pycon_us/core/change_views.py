"""The change log's words: each change as an old-to-new line and a sentence (NEW-04).

Pure functions of the log's batches, like ``row_views`` for the rows (D-184): Schedule
changes, the Changed badge, the Review SnackBar and Now's card all say a change the same
way. ``change_view()`` formats one change once: its old and new values for the line
"old → new" and the sentence a screen reader says; ``item_phrase()`` adds "In My
schedule." for a saved session. ``sections()`` puts the batches under "Affects My
schedule" and "All changes", grouped by detection time ("Today, 10:42 AM").
``changed_phrase()`` is the badge's spoken part, ``detail_badge()`` session detail's badge
of one kind with its old value, ``snackbar_text()`` and ``now_card_text()`` the counts.

Times are conference time, whatever the device's zone (D-35, D-43), in 24-hour form when
the device asks for it (F23). A session gone from the feed is "Removed from the latest
schedule", never cancelled: the feed's flag is always false (D-47).
"""

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo

from pycon_us.core.change_batches import Batch
from pycon_us.core.diff import Change, ChangeKind, Listing
from pycon_us.core.timefmt import (
    day_heading,
    day_label,
    local_date,
    on_screen,
    time_label,
    time_range_label,
)

REMOVED_NOTE = "Removed from the latest schedule"
"""What a removed session's item says inline (D-47, D-255)."""

AFFECTS_MY_SCHEDULE = "Affects My schedule"
"""The first section's title: the changes to saved sessions."""

ALL_CHANGES = "All changes"
"""The second section's title: every other change, or every change when none is saved."""

NO_ROOM = "No room"
"""A room change's side whose location is empty."""

RECENT = timedelta(hours=24)
"""How long a change counts on Now's card and keeps its Changed badge (D-255)."""

_REMOVED_SAID = "removed from the latest schedule"
"""``REMOVED_NOTE`` inside a sentence, after the session's title."""

_DASH = "–"
"""The en dash of ``timefmt`` ranges, said "to" (as ``row_views`` says it)."""

_SEPARATOR = " · "
"""Between a listing's time and its room on screen."""

_BADGE_WORDS = {
    ChangeKind.TIME: "time",
    ChangeKind.ROOM: "room",
    ChangeKind.TITLE: "title",
}
"""What the Changed badge says of each kind it marks; additions and removals get none."""


@dataclass(frozen=True, eq=False)
class ChangeView:
    """One change as Schedule changes shows and says it, formatted once (D-153).

    Frozen with identity equality (D-70 rule 6), so a memoised item compares it by
    identity.

    Attributes:
        change: The change.
        old: The old value, struck through on screen: "Room 102A", "10:30–11:00 AM",
            the old title, or a removed session's last "Sat, May 16, 10:30–11:00 AM ·
            Room 104A". Empty for an addition.
        new: The new value: "Room 103ABC", "11:30 AM–12:00 PM", the new title, or an
            added session's time and room. Empty for a removal, whose item says
            ``REMOVED_NOTE`` instead.
        sentence: The change as one sentence for a screen reader, starting with the
            session's newest title: "Building X: room changed from Room 102A to Room
            103ABC." It never relies on the strikethrough.
    """

    change: Change
    old: str
    new: str
    sentence: str

    @property
    def title(self) -> str:
        """The session's newest title, the item's title."""
        return self.change.title


def change_view(change: Change, zone: tzinfo, *, use_24h: bool) -> ChangeView:
    """Return how one change is shown and said.

    A time change on the same conference-local day shows the two ranges alone,
    "10:30–11:00 AM" → "11:30 AM–12:00 PM"; one that moves to another day puts the day
    before each, "Fri, May 15, 10:30–11:00 AM" → "Sat, May 16, 9:00–9:30 AM". An
    addition and a removal show their day, time and room, since nothing else on the
    list says when they are.

    Args:
        change: The change.
        zone: The conference's zone; every time shows in it (D-35, D-43).
        use_24h: Whether the device uses the 24-hour clock
            (``page.media.always_use_24_hour_format``).
    """
    title = change.title
    if change.kind is ChangeKind.ADDED:
        added = change.latest
        line = _where_and_when(added, zone, use_24h=use_24h)
        said = _spoken_listing(added, zone, use_24h=use_24h)
        return ChangeView(change, "", line, f"{title}: added, {said}.")
    if change.kind is ChangeKind.REMOVED:
        removed = change.latest
        line = _where_and_when(removed, zone, use_24h=use_24h)
        said = _spoken_listing(removed, zone, use_24h=use_24h)
        return ChangeView(change, line, "", f"{title}: {_REMOVED_SAID}. Was {said}.")
    assert change.old is not None and change.new is not None, "a change of a listing"
    old, new = change.old, change.new
    if change.kind is ChangeKind.TIME:
        with_day = local_date(old.start, zone) != local_date(new.start, zone)
        shown = [_when(side, zone, use_24h, with_day=with_day) for side in (old, new)]
        said = [
            _said_when(side, zone, use_24h, with_day=with_day) for side in (old, new)
        ]
        sentence = f"{title}: time changed. Was {said[0]}, now {said[1]}."
        return ChangeView(change, shown[0], shown[1], sentence)
    if change.kind is ChangeKind.ROOM:
        was, now = old.location or NO_ROOM, new.location or NO_ROOM
        return ChangeView(
            change, was, now, f"{title}: room changed from {was} to {now}."
        )
    return ChangeView(
        change, old.title, new.title, f"{title}: renamed from “{old.title}”."
    )


def item_phrase(view: ChangeView, *, saved: bool) -> str:
    """Return what a screen reader says for an item: its sentence, then whether it is saved.

    "Building X: room changed from Room 102A to Room 103ABC. In My schedule." (ux.md
    §6.4). The star's state changes without the change, so it is added here, not kept
    in the view.

    Args:
        view: The item's view.
        saved: Whether the session is in My schedule.
    """
    return f"{view.sentence} In My schedule." if saved else view.sentence


def changed_phrase(kinds: Iterable[ChangeKind]) -> str:
    """Return the Changed badge's spoken part for a session's recent changes (ux.md §3.4).

    "Room changed", "Time and room changed", "Time, room and title changed", in
    ``ChangeKind``'s order, each kind once. Additions and removals have no badge, so
    they are left out, and with nothing else the phrase is empty.

    Args:
        kinds: The kinds of the session's changes in the last 24 hours.
    """
    marked = set(kinds)
    words = [word for kind, word in _BADGE_WORDS.items() if kind in marked]
    if not words:
        return ""
    return f"{_joined(words).capitalize()} changed"


def detail_badge(change: Change, zone: tzinfo, *, use_24h: bool) -> tuple[str, str]:
    """Return session detail's badge for one recent change: its text, and as said.

    "Moved from Room 102A"; "Was Fri, May 15, 10:30 AM", said "Was Friday, May 15,
    10:30 AM"; "Renamed from “Old title”" (ux.md §5.5). The old value is the one before
    the last 24 h's changes (``ChangeLog.recent_of()``). Times are conference time.

    Args:
        change: A time, room or title change with both sides.
        zone: The conference's zone (D-35, D-43).
        use_24h: Whether the device uses the 24-hour clock.
    """
    old = change.old
    assert old is not None, "a badged change has an old side"
    if change.kind is ChangeKind.TIME:
        day = local_date(old.start, zone)
        time = time_label(old.start, zone, use_24h=use_24h)
        return (
            f"Was {day_label(day)}, {on_screen(time)}",
            f"Was {day_heading(day)}, {time}",
        )
    if change.kind is ChangeKind.ROOM:
        text = f"Moved from {old.location or NO_ROOM.lower()}"
        return text, text
    text = f"Renamed from “{old.title}”"
    return text, text


@dataclass(frozen=True, eq=False)
class ChangeGroup:
    """The items of one batch: the changes one refresh brought.

    Attributes:
        batch: The batch, whose ``seen`` mark the list reads and sets (ux.md §6.4).
        heading: When it was detected, in conference time: "Today, 10:42 AM",
            "Yesterday, 4:15 PM" or "Fri, May 15, 10:42 AM".
        views: Its changes in the section, in the diff's order.
    """

    batch: Batch
    heading: str
    views: tuple[ChangeView, ...]


@dataclass(frozen=True, eq=False)
class ChangeSection:
    """One of the list's two sections, its groups newest first.

    Attributes:
        title: ``AFFECTS_MY_SCHEDULE`` or ``ALL_CHANGES``.
        groups: The batches with a change in the section, newest first.
    """

    title: str
    groups: tuple[ChangeGroup, ...]


def sections(
    batches: Iterable[Batch],
    saved: Collection[str],
    zone: tzinfo,
    now: datetime,
    *,
    use_24h: bool,
) -> tuple[ChangeSection, ...]:
    """Return Schedule changes' sections: "Affects My schedule" first, then "All changes".

    Each change is listed once: under "Affects My schedule" when its session is saved,
    else under "All changes". A section with no change is left out, so a log without
    saved sessions has "All changes" alone, and an empty log no section. Within a
    section, batches come newest first (a later detection first; equal ones keep the
    log's order), each under its detection time.

    Args:
        batches: The log's batches (``changes-<year>.json``), in the log's order.
        saved: The ids of the saved sessions.
        zone: The conference's zone (D-35, D-43).
        now: ``clock.now()``, for "Today" and "Yesterday".
        use_24h: Whether the device uses the 24-hour clock.
    """
    newest_first = sorted(batches, key=lambda batch: batch.detected_at, reverse=True)
    mine: list[ChangeGroup] = []
    others: list[ChangeGroup] = []
    for batch in newest_first:
        heading = detected_label(batch.detected_at, now, zone, use_24h=use_24h)
        views = [change_view(c, zone, use_24h=use_24h) for c in batch.changes]
        for group, keep in ((mine, True), (others, False)):
            picked = tuple(v for v in views if (v.change.id in saved) is keep)
            if picked:
                group.append(ChangeGroup(batch, heading, picked))
    return tuple(
        ChangeSection(title, tuple(groups))
        for title, groups in ((AFFECTS_MY_SCHEDULE, mine), (ALL_CHANGES, others))
        if groups
    )


def detected_label(
    detected_at: datetime, now: datetime, zone: tzinfo, *, use_24h: bool
) -> str:
    """Return a batch's group heading: "Today, 10:42 AM", "Yesterday, 4:15 PM", "Fri, May 15, 10:42 AM".

    Days are conference-local (D-43): "Today" is ``timefmt.today()``'s day.

    Args:
        detected_at: When the batch was detected (aware).
        now: ``clock.now()``.
        zone: The conference's zone.
        use_24h: Whether the device uses the 24-hour clock.
    """
    day = local_date(detected_at, zone)
    days_ago = (local_date(now, zone) - day).days
    named = {0: "Today", 1: "Yesterday"}.get(days_ago) or day_label(day)
    return f"{named}, {time_label(detected_at, zone, use_24h=use_24h)}"


def counted(changes: Iterable[Change]) -> tuple[Change, ...]:
    """Return the changes the counts count: moves, retimes, renames and removals.

    Additions are listed but never counted nor announced alone (D-255).

    Args:
        changes: Some changes, such as a batch's.
    """
    return tuple(change for change in changes if change.kind is not ChangeKind.ADDED)


def snackbar_text(changes: Iterable[Change], saved: Collection[str]) -> str | None:
    """Return the Review SnackBar's text for a batch, or None when it shows none (D-255).

    "2 saved sessions changed" when the batch touches saved sessions (each session
    once, whatever changed about it), else "Schedule updated · 3 changes" (each change
    once). None for a batch of additions only.

    Args:
        changes: The batch's changes.
        saved: The ids of the saved sessions.
    """
    told = counted(changes)
    if not told:
        return None
    if mine := _saved_sessions(told, saved):
        return _saved_changed(mine)
    return f"Schedule updated · {_count(len(told), 'change')}"


def now_card_text(
    batches: Iterable[Batch], saved: Collection[str], now: datetime
) -> str | None:
    """Return Now's card text, "2 saved sessions changed", or None when it has no card.

    It counts the saved sessions changed in the unseen batches detected in the last
    24 hours (``RECENT``; exactly 24 hours ago still counts), each session once;
    additions are not counted, and changes to unsaved sessions never show here
    (ux.md §5.1, D-255).

    Args:
        batches: The log's batches.
        saved: The ids of the saved sessions.
        now: ``clock.now()``.
    """
    recent = (
        change
        for batch in batches
        if not batch.seen and now - batch.detected_at <= RECENT
        for change in batch.changes
    )
    mine = _saved_sessions(counted(recent), saved)
    return _saved_changed(mine) if mine else None


# ------------------------------------------------------------------ helpers


def _when(listing: Listing, zone: tzinfo, use_24h: bool, *, with_day: bool) -> str:
    """Return a listing's range, "10:30–11:00 AM", after its day ("Sat, May 16, ")."""
    when = time_range_label(listing.start, listing.end, zone, use_24h=use_24h)
    if not with_day:
        return when
    return f"{day_label(local_date(listing.start, zone))}, {when}"


def _said_when(listing: Listing, zone: tzinfo, use_24h: bool, *, with_day: bool) -> str:
    """Return a listing's range as said: "10:30 to 11:00 AM", after "Saturday, May 16, "."""
    when = time_range_label(listing.start, listing.end, zone, use_24h=use_24h)
    when = when.replace(_DASH, " to ")
    if not with_day:
        return when
    return f"{day_heading(local_date(listing.start, zone))}, {when}"


def _where_and_when(listing: Listing, zone: tzinfo, *, use_24h: bool) -> str:
    """Return an added or removed listing's line: "Sat, May 16, 10:30–11:00 AM · Room 104A"."""
    when = _when(listing, zone, use_24h, with_day=True)
    return _SEPARATOR.join(part for part in (when, listing.location) if part)


def _spoken_listing(listing: Listing, zone: tzinfo, *, use_24h: bool) -> str:
    """Return an added or removed listing as said: "Saturday, May 16, 10:30 to 11:00 AM, Room 104A"."""
    when = _said_when(listing, zone, use_24h, with_day=True)
    return ", ".join(part for part in (when, listing.location) if part)


def _saved_sessions(changes: Iterable[Change], saved: Collection[str]) -> int:
    """Return how many saved sessions ``changes`` touch, each once."""
    return len({change.id for change in changes if change.id in saved})


def _saved_changed(count: int) -> str:
    """Return "1 saved session changed" or "2 saved sessions changed"."""
    return f"{_count(count, 'saved session')} changed"


def _count(amount: int, unit: str) -> str:
    """Return "1 change" or "3 changes"."""
    return f"{amount} {unit}" if amount == 1 else f"{amount} {unit}s"


def _joined(words: list[str]) -> str:
    """Return "time", "time and room" or "time, room and title"."""
    *rest, last = words
    return f"{', '.join(rest)} and {last}" if rest else last
