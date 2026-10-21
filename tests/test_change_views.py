"""The change log's words: each change's line and sentence, sections and counts (NEW-04).

Most cases build a ``Change`` by hand, so each string is pinned exactly; one runs a real
feed pair (``tests/feeds.py``) through ``diff()``. Every test runs under both machine
zones (``machine_tz``, D-43): the words are in conference time whatever the device's.
"""

from datetime import UTC, datetime, timedelta, tzinfo
from itertools import chain
from zoneinfo import ZoneInfo

import pytest

from pycon_us.core.change_batches import Batch
from pycon_us.core.change_views import (
    AFFECTS_MY_SCHEDULE,
    ALL_CHANGES,
    REMOVED_NOTE,
    ChangeView,
    change_view,
    changed_phrase,
    detected_label,
    item_phrase,
    now_card_text,
    sections,
    snackbar_text,
)
from pycon_us.core.diff import Change, ChangeKind, Listing, diff
from pycon_us.core.feed import process
from tests.feeds import add, move, pair, processed, remove, rename, retime, settings

pytestmark = pytest.mark.usefixtures("machine_tz")

LA = ZoneInfo("America/Los_Angeles")
NY = ZoneInfo("America/New_York")

NOW = datetime(2026, 5, 16, 17, 42, tzinfo=UTC)
"""10:42 AM on Saturday, May 16 in Long Beach."""


def at(day: int, hour: int, minute: int = 0, zone: tzinfo = LA) -> datetime:
    """A moment of May 2026 in ``zone``, Long Beach's by default."""
    return datetime(2026, 5, day, hour, minute, tzinfo=zone)


def listing(
    title: str = "Python for Humans",
    start: datetime | None = None,
    minutes: int = 30,
    location: str = "Room 104A",
) -> Listing:
    """A session's listing; by default Saturday 10:30–11:00 AM in Room 104A."""
    begins = start or at(16, 10, 30)
    return Listing(title, begins, begins + timedelta(minutes=minutes), location)


def change(
    kind: ChangeKind,
    old: Listing | None,
    new: Listing | None,
    key: str = "142",
) -> Change:
    """A change of session ``key``."""
    return Change(key, kind, old, new)


def view(c: Change, zone: tzinfo = LA, *, use_24h: bool = False) -> ChangeView:
    """The view of ``c`` in ``zone``."""
    return change_view(c, zone, use_24h=use_24h)


def test_a_room_change_names_both_rooms() -> None:
    """A move shows and says the old room, then the new one, by name."""
    v = view(change(ChangeKind.ROOM, listing(), listing(location="Grand Ballroom A")))
    assert (v.old, v.new) == ("Room 104A", "Grand Ballroom A")
    assert v.sentence == (
        "Python for Humans: room changed from Room 104A to Grand Ballroom A."
    )
    assert v.title == "Python for Humans"


def test_an_empty_room_is_said_as_no_room() -> None:
    """A side without a location reads "No room", never an empty word."""
    v = view(change(ChangeKind.ROOM, listing(location=""), listing()))
    assert (v.old, v.new) == ("No room", "Room 104A")
    assert v.sentence == "Python for Humans: room changed from No room to Room 104A."


def test_a_same_day_retime_shows_the_ranges_alone() -> None:
    """A retime within the day shows two ranges, and says them with "to"."""
    v = view(
        change(ChangeKind.TIME, listing(), listing(start=at(16, 11, 30), minutes=45))
    )
    assert (v.old, v.new) == ("10:30–11:00 AM", "11:30 AM–12:15 PM")
    assert v.sentence == (
        "Python for Humans: time changed. "
        "Was 10:30 to 11:00 AM, now 11:30 AM to 12:15 PM."
    )


def test_a_cross_day_retime_puts_the_day_before_each_range() -> None:
    """A retime to another day shows each side's day, and says it in full."""
    v = view(change(ChangeKind.TIME, listing(), listing(start=at(17, 9))))
    assert (v.old, v.new) == (
        "Sat, May 16, 10:30–11:00 AM",
        "Sun, May 17, 9:00–9:30 AM",
    )
    assert v.sentence == (
        "Python for Humans: time changed. "
        "Was Saturday, May 16, 10:30 to 11:00 AM, now Sunday, May 17, 9:00 to 9:30 AM."
    )


def test_the_day_is_the_conference_s_not_utc_s() -> None:
    """Late evening in Long Beach is the next day in UTC, but the same conference day."""
    late = at(16, 18)  # 01:00 UTC on May 17
    v = view(change(ChangeKind.TIME, listing(start=at(16, 9)), listing(start=late)))
    assert (v.old, v.new) == ("9:00–9:30 AM", "6:00–6:30 PM")


def test_times_are_in_the_conference_zone_given() -> None:
    """2025's changes read in Eastern time, whatever zone the instants carry."""
    start = datetime(2025, 5, 16, 14, 30, tzinfo=UTC)  # 10:30 AM in Pittsburgh
    v = view(
        change(
            ChangeKind.TIME,
            listing(start=start),
            listing(start=start + timedelta(hours=1)),
        ),
        NY,
    )
    assert (v.old, v.new) == ("10:30–11:00 AM", "11:30 AM–12:00 PM")


def test_24_hour_times_when_the_device_asks() -> None:
    """With the 24-hour clock, lines and sentences use it (F23)."""
    v = view(
        change(ChangeKind.TIME, listing(), listing(start=at(16, 13, 30))), use_24h=True
    )
    assert (v.old, v.new) == ("10:30–11:00", "13:30–14:00")
    assert v.sentence.endswith("Was 10:30 to 11:00, now 13:30 to 14:00.")


def test_a_rename_is_said_under_the_new_title() -> None:
    """A rename's item is titled with the new name and says the old one."""
    v = view(change(ChangeKind.TITLE, listing(), listing(title="Python for Robots")))
    assert (v.title, v.old, v.new) == (
        "Python for Robots",
        "Python for Humans",
        "Python for Robots",
    )
    assert v.sentence == "Python for Robots: renamed from “Python for Humans”."


def test_an_addition_shows_its_day_time_and_room() -> None:
    """An added session has no old value; its line says when and where it is."""
    v = view(change(ChangeKind.ADDED, None, listing()))
    assert (v.old, v.new) == ("", "Sat, May 16, 10:30–11:00 AM · Room 104A")
    assert v.sentence == (
        "Python for Humans: added, Saturday, May 16, 10:30 to 11:00 AM, Room 104A."
    )


def test_a_removal_keeps_its_last_listing_and_never_says_cancelled() -> None:
    """A removed session shows its last day, time and room, and the D-47 words."""
    v = view(change(ChangeKind.REMOVED, listing(), None))
    assert (v.old, v.new) == ("Sat, May 16, 10:30–11:00 AM · Room 104A", "")
    assert v.sentence == (
        "Python for Humans: removed from the latest schedule. "
        "Was Saturday, May 16, 10:30 to 11:00 AM, Room 104A."
    )
    assert REMOVED_NOTE == "Removed from the latest schedule"


def test_a_listing_without_a_room_leaves_it_out() -> None:
    """An addition with no location shows and says its time alone."""
    v = view(change(ChangeKind.ADDED, None, listing(location="")))
    assert v.new == "Sat, May 16, 10:30–11:00 AM"
    assert v.sentence.endswith("added, Saturday, May 16, 10:30 to 11:00 AM.")


def test_item_phrase_says_a_saved_session_is_in_my_schedule() -> None:
    """The item's phrase ends "In My schedule." only for a saved session."""
    v = view(change(ChangeKind.ROOM, listing(), listing(location="Room 103ABC")))
    assert item_phrase(v, saved=True) == (
        "Python for Humans: room changed from Room 104A to Room 103ABC. In My schedule."
    )
    assert item_phrase(v, saved=False) == v.sentence


def test_item_phrase_starts_with_new_while_unseen() -> None:
    """An unseen item's phrase starts "New: ", as its dot shows (ux.md §6.4)."""
    v = view(change(ChangeKind.ROOM, listing(), listing(location="Room 103ABC")))
    assert item_phrase(v, saved=True, unseen=True) == (
        "New: Python for Humans: room changed from Room 104A to Room 103ABC."
        " In My schedule."
    )


@pytest.mark.parametrize(
    ("kinds", "phrase"),
    [
        ([ChangeKind.ROOM], "Room changed"),
        ([ChangeKind.TIME], "Time changed"),
        ([ChangeKind.TITLE], "Title changed"),
        ([ChangeKind.ROOM, ChangeKind.TIME, ChangeKind.ROOM], "Time and room changed"),
        (
            [ChangeKind.TITLE, ChangeKind.ROOM, ChangeKind.TIME],
            "Time, room and title changed",
        ),
        ([ChangeKind.ADDED, ChangeKind.REMOVED], ""),
        ([], ""),
    ],
)
def test_changed_phrase(kinds: list[ChangeKind], phrase: str) -> None:
    """The badge's spoken part names each marked kind once, in order; none for the rest."""
    assert changed_phrase(kinds) == phrase


@pytest.mark.parametrize(
    ("detected", "label"),
    [
        (at(16, 10, 42), "Today, 10:42 AM"),
        (at(16, 0, 5), "Today, 12:05 AM"),
        (at(15, 23, 59), "Yesterday, 11:59 PM"),
        (at(14, 16, 15), "Thu, May 14, 4:15 PM"),
    ],
)
def test_detected_label(detected: datetime, label: str) -> None:
    """A group's heading names today and yesterday by conference day, other days by date."""
    assert detected_label(detected, NOW, LA, use_24h=False) == label


def test_detected_label_in_24_hour_form() -> None:
    """The heading's time follows the device's clock format."""
    assert detected_label(at(16, 16, 15), NOW, LA, use_24h=True) == "Today, 16:15"


def batch_of(*changes: Change, at_: datetime = NOW, seen: bool = False) -> Batch:
    """A batch of ``changes`` detected at ``at_``."""
    return Batch(detected_at=at_, changes=changes, seen=seen)


MOVED = change(ChangeKind.ROOM, listing(), listing(location="Room 103ABC"), key="1")
RETIMED = change(ChangeKind.TIME, listing(), listing(start=at(16, 15)), key="2")
RENAMED = change(ChangeKind.TITLE, listing(), listing(title="New name"), key="1")
REMOVED = change(ChangeKind.REMOVED, listing(), None, key="3")
ADDED = change(ChangeKind.ADDED, None, listing(), key="4")


def test_sections_put_my_schedule_first_and_list_each_change_once() -> None:
    """Saved sessions' changes come first; every other change is under All changes."""
    older = batch_of(MOVED, RETIMED, at_=at(15, 16, 15))
    newer = batch_of(RENAMED, REMOVED, ADDED, at_=at(16, 10, 42))
    found = sections([older, newer], {"1", "3"}, LA, NOW, use_24h=False)
    assert [s.title for s in found] == [AFFECTS_MY_SCHEDULE, ALL_CHANGES]
    mine, rest = found
    assert [g.heading for g in mine.groups] == ["Today, 10:42 AM", "Yesterday, 4:15 PM"]
    assert [[v.change for v in g.views] for g in mine.groups] == [
        [RENAMED, REMOVED],
        [MOVED],
    ]
    assert [g.batch for g in mine.groups] == [newer, older]
    assert [[v.change for v in g.views] for g in rest.groups] == [[ADDED], [RETIMED]]


def test_without_saved_changes_there_is_only_all_changes() -> None:
    """A log that touches no saved session has one section; an empty log has none."""
    found = sections([batch_of(MOVED, ADDED)], {"99"}, LA, NOW, use_24h=False)
    assert [s.title for s in found] == [ALL_CHANGES]
    assert sections([], {"1"}, LA, NOW, use_24h=False) == ()


def test_only_saved_changes_give_only_my_schedule() -> None:
    """When every change is to a saved session, All changes is left out."""
    found = sections([batch_of(MOVED)], {"1"}, LA, NOW, use_24h=False)
    assert [s.title for s in found] == [AFFECTS_MY_SCHEDULE]


@pytest.mark.parametrize(
    ("changes", "saved", "text"),
    [
        ((MOVED, RENAMED, RETIMED), {"1"}, "1 saved session changed"),
        ((MOVED, RETIMED, REMOVED), {"1", "2", "3"}, "3 saved sessions changed"),
        ((MOVED,), set(), "Schedule updated · 1 change"),
        (
            (MOVED, RENAMED, RETIMED, REMOVED, ADDED),
            set(),
            "Schedule updated · 4 changes",
        ),
        ((ADDED,), {"4"}, None),
        ((), set(), None),
    ],
)
def test_snackbar_text(
    changes: tuple[Change, ...], saved: set[str], text: str | None
) -> None:
    """Saved sessions are counted once each, else changes; additions are never counted."""
    assert snackbar_text(changes, saved) == text


def test_now_card_counts_unseen_saved_changes_of_the_last_24_hours() -> None:
    """Only unseen batches of the last 24 h count, and only their saved sessions."""
    recent = batch_of(MOVED, RENAMED, RETIMED, at_=NOW - timedelta(hours=24))
    seen = batch_of(REMOVED, seen=True)
    old = batch_of(REMOVED, at_=NOW - timedelta(hours=24, seconds=1))
    saved = {"1", "3", "4"}
    assert now_card_text([recent, seen, old], saved, NOW) == "1 saved session changed"
    added = batch_of(ADDED, change(ChangeKind.REMOVED, listing(), None, key="4"))
    assert now_card_text([recent, added], saved, NOW) == "2 saved sessions changed"
    assert now_card_text([recent], {"2", "9"}, NOW) == "1 saved session changed"
    assert now_card_text([recent], {"9"}, NOW) is None
    assert now_card_text([batch_of(ADDED)], saved, NOW) is None


@pytest.mark.parametrize("year", [2025, 2026])
def test_real_feed_changes_never_say_cancel(year: int) -> None:
    """Every kind from a real feed pair reads in words without "cancel", in both clocks."""
    zone = {2025: NY, 2026: LA}[year]
    edited, dropped = {2025: (104, 103), 2026: (142, 51)}[year]
    _, new = pair(
        year,
        move(edited, "Room 999"),
        rename(edited, "A renamed talk"),
        add(990001, like=edited, name="An added talk"),
        remove(dropped),
    )
    changes = diff(processed(year), process(new, settings(year)))
    assert {c.kind for c in changes} == set(ChangeKind) - {ChangeKind.TIME}
    log = [batch_of(*changes)]
    saved = {c.id for c in changes}
    for use_24h in (False, True):
        views = [change_view(c, zone, use_24h=use_24h) for c in changes]
        words = chain.from_iterable(
            (v.old, v.new, v.sentence, item_phrase(v, saved=True)) for v in views
        )
        texts = [
            *words,
            *(
                g.heading
                for s in sections(log, saved, zone, NOW, use_24h=use_24h)
                for g in s.groups
            ),
            snackbar_text(changes, saved) or "",
            snackbar_text(changes, set()) or "",
            now_card_text(log, saved, NOW) or "",
            changed_phrase(c.kind for c in changes),
        ]
        assert all("cancel" not in text.lower() for text in texts)


def test_a_real_cross_day_retime() -> None:
    """A recorded 2026 talk moved to the next day reads with both days, in Pacific time."""
    old = processed(2026).sessions["142"]
    start = old.start + timedelta(days=1)
    _, new = pair(
        2026,
        retime(142, start.isoformat(), (start + (old.end - old.start)).isoformat()),
    )
    (retimed,) = diff(processed(2026), process(new, settings(2026)))
    v = view(retimed)
    assert v.old.startswith(f"{old.start.astimezone(LA):%a, %b} {old.start.day}, ")
    assert v.new.startswith(
        f"{start.astimezone(LA):%a, %b} {start.astimezone(LA).day}, "
    )
    assert " to " in v.sentence and "–" not in v.sentence
