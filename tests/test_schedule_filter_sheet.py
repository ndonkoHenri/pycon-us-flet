"""Tests for the Schedule's track filter sheet: its chips, buttons and re-renders (#87).

The words and the summary are ``test_schedule_filter.py``'s.

STORE-09, SCHED-09, SCHED-10; D-20, D-178. The screen renders in a real Flet session
through ``tests/schedule_view.py``'s ``shown`` fixture, whose ``AppScaffold`` stand-in
places the app bar's actions, so the ``TUNE`` action, the sheet (``ft.use_dialog``),
the chips and the summary run as Flet runs them; ``tests/filter_sheet.py`` finds and
taps them. How the sheet looks and scrolls at 200 % text is a device check (#87).
"""

import asyncio
from collections import Counter
from typing import Any, cast

import flet as ft

from pycon_us.core.timefmt import time_label
from pycon_us.core.timeline import Slot, timeline
from pycon_us.prefs import Prefs
from pycon_us.screens.schedule_sheet import (
    count_label,
    filter_groups,
)
from pycon_us.state import Conference
from tests import filter_sheet, schedule_view
from tests.fakes import MemoryPrefs
from tests.filter_sheet import (
    INFO,
    STORED,
    Show,
    _descendants,
    button_label,
    chip,
    chip_parts,
    click,
    feed_tracks,
    filter_button,
    in_sheet,
    node,
    open_sheet,
    reset_button,
    sheet,
    show_button,
    shown_count,
    stored,
    summary,
    tap_chip,
)
from tests.schedule_view import DAYS
from tests.sessions import settle
from tests.trees import texts

# The Schedule's fixtures, shared by name: pytest finds fixtures among a module's names.
now = schedule_view.now
memory = schedule_view.memory
conference = schedule_view.conference
shown = schedule_view.shown
encoded = filter_sheet.encoded


async def test_the_sheet_offers_a_chip_per_feed_track_with_a_live_count(
    shown: Show, conference: Conference
) -> None:
    """The sheet has a chip per feed track; a tap applies, stores and recounts."""
    schedule = await shown()
    current = await open_sheet(schedule)
    assert current.show_drag_handle and current.scrollable and current.use_safe_area
    assert current.animation_style is None  # Flutter's slide, as motion is allowed
    chips = [c for c in _descendants(current) if isinstance(c, ft.Chip)]
    labels = [chip_parts(c.label)[1].value for c in chips]
    tracks = feed_tracks(conference)
    # F40: a heading needs its level. The title, then one per group the feed fills.
    levels = [
        c.heading_level
        for c in _descendants(current)
        if isinstance(c, ft.Semantics) and c.header
    ]
    assert levels == [1, *[2] * len(filter_groups(INFO, tracks))] == [1, 2, 2, 2, 2]
    assert labels == [
        INFO.track_name(key) for g in filter_groups(INFO, tracks) for key in g.tracks
    ]
    assert not chip(schedule, "open-space").selected
    assert chip_parts(chip(schedule, "open-space").label)[0] is None
    assert chip(schedule, "talk").selected
    assert chip_parts(chip(schedule, "talk").label)[0] is not None  # its check
    # The label draws the check and the side padding (F69): the chip draws neither.
    assert not any(c.show_checkmark for c in chips)
    assert all(c.label_padding == ft.Padding.all(0) for c in chips)
    default = shown_count(conference, ("Open Space",))
    assert button_label(schedule) == count_label(default)

    await tap_chip(schedule, "talk")  # hides talks at once, and persists
    assert schedule.prefs.excluded_tracks == ("Open Space", "Talk")
    assert chip_parts(chip(schedule, "talk").label)[0] is None  # its check goes too
    assert stored(schedule)[STORED] == ["Open Space", "Talk"]
    fewer = shown_count(conference, ("Open Space", "Talk"))
    assert fewer < default
    assert button_label(schedule) == count_label(fewer)
    assert summary(schedule) == "Hidden: Talk, Open space"
    assert cast(ft.Icon, filter_button(schedule).icon).badge is not None

    await tap_chip(schedule, "open-space")
    assert schedule.prefs.excluded_tracks == ("Talk",)
    assert button_label(schedule) == count_label(shown_count(conference, ("Talk",)))
    assert summary(schedule) == "Hidden: Talk"


async def test_the_sheet_appears_without_its_slide_under_reduced_motion(
    shown: Show,
) -> None:
    """D-173: every animation the app sets goes through the reduced-motion flag."""
    schedule = await shown(reduce_motion=True)
    current = await open_sheet(schedule)
    assert current.animation_style == ft.AnimationStyle.no_animation()


async def test_reset_returns_to_the_default(
    shown: Show,
) -> None:
    """Reset restores and stores the default filter, and the sheet stays open."""
    schedule = await shown(excluded_tracks=("Talk", "Tutorial"))
    current = await open_sheet(schedule)
    (reset,) = [
        c
        for c in _descendants(current)
        if isinstance(c, ft.TextButton) and c.content == "Reset"
    ]
    assert reset.tooltip == "Reset to the default: hide Open space"
    await click(schedule, reset)
    assert schedule.prefs.excluded_tracks == ("Open Space",)
    assert stored(schedule)[STORED] == ["Open Space"]
    assert summary(schedule) == "Hidden: Open space"
    assert cast(ft.Icon, filter_button(schedule).icon).badge is None
    assert sheet(schedule) is not None  # Reset applies; the sheet stays


async def test_reset_is_disabled_while_the_filter_is_the_default(
    shown: Show,
) -> None:
    """Reset, button and node, is disabled only while the filter is the default."""
    schedule = await shown()
    await open_sheet(schedule)
    assert reset_button(schedule).disabled  # a tap would do nothing
    # The node too: Flet's Semantics says enabled unless it is disabled itself.
    assert node(schedule, "schedule.filter.reset").disabled
    await tap_chip(schedule, "talk")
    assert not reset_button(schedule).disabled
    assert not node(schedule, "schedule.filter.reset").disabled
    await click(schedule, reset_button(schedule))
    assert schedule.prefs.excluded_tracks == ("Open Space",)
    assert reset_button(schedule).disabled


async def test_the_filter_survives_a_relaunch(
    shown: Show,
) -> None:
    """A chip change is read back by fresh ``Prefs``, as after a relaunch."""
    schedule = await shown()
    await open_sheet(schedule)
    await tap_chip(schedule, "tutorial")
    relaunched = Prefs()
    await relaunched.load(schedule.storage)
    assert relaunched.excluded_tracks == ("Open Space", "Tutorial")


async def test_two_quick_taps_both_count(
    shown: Show,
) -> None:
    """A second tap during the first one's write must not start from the old filter."""
    schedule = await shown()
    await open_sheet(schedule)
    shared = cast(MemoryPrefs, schedule.storage.prefs)
    write = shared._invoke_method  # pyright: ignore[reportPrivateUsage]

    async def slow(*args: Any, **kwargs: Any) -> Any:
        await asyncio.sleep(0.01)  # a SharedPreferences round trip
        return await write(*args, **kwargs)

    shared._invoke_method = slow  # pyright: ignore[reportAttributeAccessIssue]
    talk, tutorial = chip(schedule, "talk"), chip(schedule, "tutorial")
    for target in (talk, tutorial):
        schedule.session.apply_patch(target._i, {"selected": False})
    await asyncio.gather(
        schedule.session.dispatch_event(talk._i, "select", False),
        schedule.session.dispatch_event(tutorial._i, "select", False),
    )
    await settle()
    assert set(schedule.prefs.excluded_tracks) == {"Open Space", "Talk", "Tutorial"}
    assert set(shared.values[STORED]) == {"Open Space", "Talk", "Tutorial"}


async def test_a_failed_write_keeps_the_change_and_says_so(
    shown: Show,
) -> None:
    """D-120: shown for the session, and the user is told it will not last."""
    schedule = await shown()
    await open_sheet(schedule)
    cast(MemoryPrefs, schedule.storage.prefs).fail_writes = True
    await tap_chip(schedule, "talk")
    assert "Talk" in schedule.prefs.excluded_tracks
    dialogs = schedule.session.page._dialogs.controls  # pyright: ignore[reportPrivateUsage]
    (snack,) = [d for d in dialogs if isinstance(d, ft.SnackBar)]
    assert texts(snack.content)[0] == "Couldn't save your change"  # pyright: ignore[reportArgumentType]


async def test_with_every_chip_off_the_button_is_disabled_and_says_why(
    shown: Show, conference: Conference
) -> None:
    """With every chip off the flat Show button is disabled, and the sheet says why."""
    schedule = await shown(excluded_tracks=tuple(feed_tracks(conference)))
    current = await open_sheet(schedule)
    button = show_button(schedule)
    assert button_label(schedule) == "Show 0 sessions"
    assert button.disabled
    assert node(schedule, "schedule.filter.show").disabled  # said, not only shown
    # Flat: Flet's default elevation of 1 showed a shadow through the faint fill.
    assert button.elevation == 0
    assert "Select at least one type" in [
        c.value for c in _descendants(current) if isinstance(c, ft.Text)
    ]


async def test_show_n_sessions_closes_the_sheet_and_keeps_the_filter(
    shown: Show,
) -> None:
    """The Show button closes the sheet and keeps the change."""
    schedule = await shown()
    await open_sheet(schedule)
    await tap_chip(schedule, "talk")
    await click(schedule, show_button(schedule))
    assert sheet(schedule) is None
    assert "Talk" in schedule.prefs.excluded_tracks


async def test_a_swipe_that_dismisses_the_sheet_keeps_the_filter(
    shown: Show,
) -> None:
    """Ionic dropped the changes on dismiss; chips here apply at once."""
    schedule = await shown()
    current = await open_sheet(schedule)
    await tap_chip(schedule, "talk")
    await schedule.session.dispatch_event(current._i, "dismiss", None)
    await settle()
    assert sheet(schedule) is None
    assert "Talk" in schedule.prefs.excluded_tracks
    await open_sheet(schedule)  # and it opens again
    assert not chip(schedule, "talk").selected


async def test_what_do_these_mean_opens_the_tracks_hub(
    shown: Show,
) -> None:
    """The "What do these mean?" link closes the sheet and opens the Tracks hub."""
    schedule = await shown()
    await open_sheet(schedule)
    link = in_sheet(schedule, "schedule.filter.tracks")
    assert isinstance(link, ft.TextButton) and link.content == "What do these mean?"
    await click(schedule, link)
    assert schedule.went == ["/more/tracks"]
    assert sheet(schedule) is None


async def test_a_filter_change_re_renders_only_the_slots_it_changes(
    shown: Show, conference: Conference
) -> None:
    """D-153, D-178: untouched slots are the same objects, so their bodies skip.

    Fails if ``timeline()`` rebuilt every slot, or if the slot item were not memoised.
    """
    schedule = await shown()
    await open_sheet(schedule)
    data = conference.data
    assert data is not None
    before = {day: timeline(data, day, ("Open Space",)) for day in DAYS}
    after = {day: timeline(data, day, ("Open Space", "Charla")) for day in DAYS}
    expected = Counter(
        time_label(slot.start, INFO.zone, use_24h=False)
        for day in DAYS
        for index, slot in enumerate(after[day])
        if _changed(slot, index, before[day])
    )
    assert expected  # charlas are on some slots
    assert sum(expected.values()) < sum(len(s) for s in after.values()) / 2
    schedule.rows.clear()
    schedule.slots.clear()
    schedule.scrolls.clear()
    await tap_chip(schedule, "charla")
    assert Counter(schedule.slots) == expected
    assert schedule.rows == []  # every row kept its props: none re-rendered
    assert schedule.scrolls == []  # #313: a filter change never scrolls


def _changed(slot: Slot, index: int, before: tuple[Slot, ...]) -> bool:
    """Whether a slot item's props changed: other sessions, or its divider."""
    # Equal, not identical: a filtered slot is a new object per filter, equal to the
    # last one while its sessions are; the memo compares with == after `is` (F34).
    old = next((i for i, s in enumerate(before) if s == slot), None)
    return old is None or (old > 0) != (index > 0)
