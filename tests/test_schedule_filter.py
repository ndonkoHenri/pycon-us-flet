"""Tests for the Schedule's track filter: its words, its sheet and its summary (#87).

STORE-09, SCHED-09, SCHED-10; D-20, D-178. The pure words are checked on the 2026 year
data; the screen renders in a real Flet session through ``tests/test_schedule.py``'s
``shown`` fixture, whose ``AppScaffold`` stand-in places the app bar's actions, so the
``TUNE`` action, the sheet (``ft.use_dialog``), the chips and the summary run as Flet
runs them. How the sheet looks and scrolls at 200 % text is a device check (#87).
"""

import asyncio
import dataclasses
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.timefmt import time_label
from pycon_us.core.timeline import Slot, timeline
from pycon_us.prefs import Prefs
from pycon_us.screens.schedule_filter import (
    SHOW_ALL_INSET,
    SUMMARY_ICON,
    differs_from_default,
    hidden_tracks,
    summary_text,
)
from pycon_us.screens.schedule_sheet import (
    DEFAULT_HIDDEN,
    chip_label,
    count_label,
    filter_groups,
)
from pycon_us.state import Conference
from tests import sessions, test_schedule
from tests.fakes import MemoryPrefs
from tests.sessions import find, settle
from tests.test_schedule import DAYS, Shown
from tests.trees import texts

# The Schedule's fixtures, shared by name: pytest finds fixtures among a module's names.
now = test_schedule.now
memory = test_schedule.memory
conference = test_schedule.conference
shown = test_schedule.shown


@pytest.fixture(autouse=True)
def encoded(monkeypatch: pytest.MonkeyPatch) -> None:
    """The sheet is a dialog: its updates need encoded messages (sessions.ENCODE)."""
    monkeypatch.setattr(sessions, "ENCODE", True)


INFO = load_year(2026).conference
STORED = "pycon.excluded_tracks"

type Show = Callable[..., Awaitable[Shown]]
"""The ``shown`` fixture: render the Schedule, with ``Prefs`` fields as keywords."""


def stored(schedule: Shown) -> dict[str, Any]:
    """What SharedPreferences holds for the session (``tests/fakes.MemoryPrefs``)."""
    return cast(MemoryPrefs, schedule.storage.prefs).values


def feed_tracks(conference: Conference) -> frozenset[str]:
    """The track keys of every session the Schedule can show, on any day."""
    data = conference.data
    assert data is not None
    return frozenset(
        s.track
        for day in DAYS
        for slot in timeline(data, day, ())
        for s in slot.sessions
    )


def shown_count(conference: Conference, excluded: tuple[str, ...]) -> int:
    """The rows the Schedule shows on all days with this filter."""
    data = conference.data
    assert data is not None
    return sum(
        len(slot.sessions) for day in DAYS for slot in timeline(data, day, excluded)
    )


# ------------------------------------------------------------------ the words


def test_the_chips_follow_the_registry_groups_and_order() -> None:
    """The chips are grouped, and ordered, as the track registry says."""
    tracks = {"Break", "Talk", "Open Space", "Tutorial", "Keynote", "Informational"}
    groups = filter_groups(INFO, tracks)
    assert [(g.label, g.tracks) for g in groups] == [
        ("Talks and keynotes", ("Talk", "Keynote")),
        ("Hands-on", ("Tutorial",)),
        ("Community", ("Open Space",)),
        ("Breaks and notices", ("Informational", "Break")),
    ]


def test_a_track_the_registry_lacks_gets_a_chip_after_its_groups_known_ones() -> None:
    """Next year's feed may add a kind: it gets its humanised name and a chip."""
    groups = filter_groups(INFO, {"Talk", "Hallway-track", "Ai"})
    assert groups[0].tracks == ("Talk", "Ai", "Hallway-track")
    assert INFO.track_name("Hallway-track") == "Hallway track"


def test_every_registry_group_has_a_heading() -> None:
    """Every registry track falls in one of the sheet's groups."""
    every = {t.key for t in INFO.tracks}
    assert sum(len(g.tracks) for g in filter_groups(INFO, every)) == len(every)


def test_the_summary_lists_up_to_three_tracks_as_labels() -> None:
    """The summary lists up to three hidden tracks, then counts the rest.

    A list, not a sentence: "Hidden: Talk, Open space" read as one talk.
    """
    assert summary_text(INFO, ()) is None
    assert summary_text(INFO, ("Open Space",)) == "Hidden: Open space"
    assert summary_text(INFO, ("Talk", "Open Space")) == "Hidden: Talk, Open space"
    assert (
        summary_text(INFO, ("Talk", "Ai", "Open Space"))
        == "Hidden: Talk, AI, Open space"
    )
    assert (
        summary_text(INFO, ("Talk", "Keynote", "Ai", "Tutorial", "Break"))
        == "Hidden: Talk, Keynote, AI and 2 more"
    )


def test_hidden_tracks_are_the_ones_the_feed_has_in_the_sheets_order() -> None:
    """Hidden tracks are the excluded ones the feed has, in the sheet's order."""
    tracks = {"Talk", "Open Space", "Break"}
    assert hidden_tracks(INFO, tracks, ("Open Space", "Charla", "Talk")) == (
        "Talk",
        "Open Space",
    )
    assert hidden_tracks(INFO, {"Talk"}, DEFAULT_HIDDEN) == ()  # none published yet


def test_the_count_says_session_or_sessions() -> None:
    """The Show label says "session" for one session and "sessions" otherwise."""
    assert count_label(0) == "Show 0 sessions"
    assert count_label(1) == "Show 1 session"
    assert count_label(87) == "Show 87 sessions"


def chip_parts(label: Any) -> tuple[ft.Icon | None, ft.Text]:
    """Return a chip label's check (``None`` when it has none) and its name."""
    assert isinstance(label, ft.Container)
    row = label.content
    assert isinstance(row, ft.Row)
    *check, name = row.controls
    assert isinstance(name, ft.Text)
    assert all(isinstance(c, ft.Icon) for c in check)
    return (cast(ft.Icon, check[0]) if check else None), name


def test_a_chip_name_wraps_beside_its_check_at_large_text() -> None:
    """A chip's name is a Text that may wrap, beside the check when shown.

    #330: a string label stays on one faded line, so "Lightning talks" was cut at iOS's
    largest text. The name is a Text that may wrap, loose in its row so the chip stays
    as narrow as the name; the label, not the chip, draws the check and the side
    padding, so Flutter measures the name at the width it lays it out in (F69).
    """
    for shown in (True, False):
        label = chip_label("Lightning talks", shown)
        check, name = chip_parts(label)
        assert name.value == "Lightning talks"
        assert name.max_lines is not None and name.max_lines > 1
        assert not name.no_wrap
        assert name.expand and name.expand_loose
        assert label.bgcolor == ft.Colors.TRANSPARENT  # hit-tested at its centre
        if shown:
            assert check is not None and check.icon == ft.Icons.CHECK
            assert check.apply_text_scaling  # grows with the text, as Flutter's
        else:
            assert check is None  # unselected: the outline and the name only


def test_the_dot_shows_only_when_the_filter_differs_from_the_default() -> None:
    """D-20: the default is a filter state, but not a change."""
    tracks = {"Talk", "Open Space"}
    assert DEFAULT_HIDDEN == ("Open Space",)
    assert not differs_from_default(tracks, ("Open Space",))
    assert not differs_from_default(tracks, ("Open Space", "Charla"))  # not in feed
    assert differs_from_default(tracks, ())  # an explicit "show everything"
    assert differs_from_default(tracks, ("Open Space", "Talk"))
    assert not differs_from_default({"Talk"}, ())  # no open spaces to show anyway


# ------------------------------------------------------------------ the screen


def summary(schedule: Shown) -> str | None:
    """The filter summary's text, or None when the Schedule shows none."""
    found = find(
        schedule.session,
        ft.Semantics,
        lambda c: c.identifier == "schedule.filter_summary",
    )
    return texts(found[0])[0] if found else None


def filter_button(schedule: Shown) -> ft.IconButton:
    """The app bar's filter ``IconButton``."""
    (node,) = find(
        schedule.session, ft.Semantics, lambda c: c.identifier == "schedule.filter"
    )
    assert isinstance(node.content, ft.IconButton)
    return node.content


def sheet(schedule: Shown) -> ft.BottomSheet | None:
    """The open filter sheet, or None; there is never more than one."""
    dialogs = schedule.session.page._dialogs.controls  # pyright: ignore[reportPrivateUsage]
    found = [d for d in dialogs if isinstance(d, ft.BottomSheet) and d.open]
    assert len(found) <= 1
    return found[0] if found else None


def node(schedule: Shown, identifier: str) -> ft.Semantics:
    """Return the sheet's semantics node ``identifier``."""
    current = sheet(schedule)
    assert current is not None
    return next(
        c
        for c in _descendants(current)
        if isinstance(c, ft.Semantics) and c.identifier == identifier
    )


def in_sheet(schedule: Shown, identifier: str) -> Any:
    """Return the control under the sheet's semantics node ``identifier``."""
    return node(schedule, identifier).content


def chip(schedule: Shown, key: str) -> ft.Chip:
    """The sheet's chip for the track ``key``."""
    found = in_sheet(schedule, f"schedule.filter.{key}")
    assert isinstance(found, ft.Chip)
    return found


def reset_button(schedule: Shown) -> ft.TextButton:
    """The sheet's Reset button."""
    found = in_sheet(schedule, "schedule.filter.reset")
    assert isinstance(found, ft.TextButton)
    return found


def show_button(schedule: Shown) -> ft.FilledButton:
    """The sheet's Show button."""
    current = sheet(schedule)
    assert current is not None
    return next(c for c in _descendants(current) if isinstance(c, ft.FilledButton))


def button_label(schedule: Shown) -> str:
    """The text of the sheet's Show button."""
    content = show_button(schedule).content
    assert isinstance(content, ft.Text)
    return str(content.value)


def _descendants(control: Any) -> list[Any]:
    """Every control under ``control``, through ``content`` and ``controls``."""
    found = [control]
    for child in (getattr(control, "content", None), *getattr(control, "controls", ())):
        if isinstance(child, ft.BaseControl):
            found.extend(_descendants(child))
    return found


async def click(schedule: Shown, control: ft.BaseControl) -> None:
    """Dispatch a click on ``control``, then let the session settle."""
    await schedule.session.dispatch_event(control._i, "click", None)
    await settle()


async def open_sheet(schedule: Shown) -> ft.BottomSheet:
    """Tap the filter button and return the sheet it opens."""
    await click(schedule, filter_button(schedule))
    current = sheet(schedule)
    assert current is not None
    return current


async def tap_chip(schedule: Shown, key: str) -> None:
    """What Flutter sends for a chip tap: the flipped state, then the event."""
    target = chip(schedule, key)
    selected = not target.selected
    schedule.session.apply_patch(target._i, {"selected": selected})
    await schedule.session.dispatch_event(target._i, "select", selected)
    await settle()


async def test_the_default_hides_open_spaces_and_says_so_without_a_dot(
    shown: Show,
) -> None:
    """D-20: Ionic hid its default; here it is a visible filter state."""
    schedule = await shown()
    assert schedule.prefs.excluded_tracks == ("Open Space",)
    assert summary(schedule) == "Hidden: Open space"
    button = filter_button(schedule)
    assert cast(ft.Icon, button.icon).icon == ft.Icons.TUNE
    assert cast(ft.Tooltip, button.tooltip).message == "Filter sessions"
    node = find(
        schedule.session, ft.Semantics, lambda c: c.identifier == "schedule.filter"
    )[0]
    assert (node.label, node.value) == ("Filter sessions", None)
    assert cast(ft.Icon, button.icon).badge is None


async def test_a_wrapped_show_all_starts_its_label_under_the_summary_words(
    shown: Show,
) -> None:
    """Show all's indent and side padding put its label under the summary's words.

    #283: Material shrinks a text button's side padding as text grows (12 dp to 4), so
    at large text a "Show all" on a run of its own started right of the words. Pinned,
    and indented by the mark's width, its label starts where the words do: the mark,
    then ``SHOW_ALL_INSET`` (D-373).
    """
    schedule = await shown()
    (words,) = find(
        schedule.session,
        ft.Row,
        lambda r: any(
            isinstance(c, ft.Semantics) and c.identifier == "schedule.filter_summary"
            for c in r.controls
        ),
    )
    (show_all,) = find(
        schedule.session, ft.Semantics, lambda c: c.identifier == "schedule.show_all"
    )
    button = cast(ft.TextButton, show_all.content)
    assert button.content == "Show all"  # the label, its own node's name
    padding = cast(ft.Padding, cast(ft.ButtonStyle, button.style).padding)
    assert padding.left == padding.right == words.spacing == SHOW_ALL_INSET
    (wrap,) = find(
        schedule.session, ft.Row, lambda r: bool(r.wrap) and words in r.controls
    )
    assert wrap.spacing == 0  # nothing else between a run's start and the label
    indent = cast(ft.Container, wrap.controls[1])
    assert cast(ft.MergeSemantics, indent.content).content is show_all  # named()
    assert cast(ft.Padding, indent.padding).left == SUMMARY_ICON


async def test_the_filter_mark_is_one_line_tall_beside_the_words_first_line(
    shown: Show,
) -> None:
    """D-373: the mark scales with the text and tops the words' own row.

    In the words' row, not before the wrap, it stays beside their first line whether
    they share the button's run (centred against its 48 dp) or not (large text).
    """
    schedule = await shown()
    (mark,) = find(schedule.session, ft.Icon, lambda i: i.icon == ft.Icons.FILTER_LIST)
    assert (mark.size, mark.apply_text_scaling) == (SUMMARY_ICON, True)
    words = cast(ft.Row, mark.parent)
    assert not words.wrap and words.tight
    assert words.vertical_alignment == ft.CrossAxisAlignment.START
    summary_node = words.controls[1]
    assert isinstance(summary_node, ft.Semantics)
    assert summary_node.identifier == "schedule.filter_summary"
    assert summary_node.expand and summary_node.expand_loose  # wraps beside the mark


async def test_show_all_restores_every_track_and_stores_an_explicit_empty_list(
    shown: Show,
) -> None:
    """Show all stores [], so no track hides, and marks the filter changed."""
    schedule = await shown()
    schedule.scrolls.clear()
    (show_all,) = find(
        schedule.session, ft.Semantics, lambda c: c.identifier == "schedule.show_all"
    )
    await click(schedule, show_all.content)  # pyright: ignore[reportArgumentType]
    assert schedule.prefs.excluded_tracks == ()
    assert stored(schedule)[STORED] == []  # honoured on relaunch
    assert summary(schedule) is None
    node = find(
        schedule.session, ft.Semantics, lambda c: c.identifier == "schedule.filter"
    )[0]
    assert (
        cast(ft.Icon, filter_button(schedule).icon).badge is not None
    )  # differs from the default
    assert node.value == "Changed"  # said too, not only drawn
    assert schedule.scrolls == []  # never scrolled unasked (#313)


async def test_a_stored_filter_reads_back_absent_as_the_default_and_empty_as_none(
    shown: Show,
) -> None:
    """STORE-09: an absent key is the default; an explicit [] shows everything."""
    schedule = await shown()
    values = stored(schedule)
    assert STORED not in values
    await schedule.prefs.load(schedule.storage)
    await settle()
    assert summary(schedule) == "Hidden: Open space"
    values[STORED] = []
    await schedule.prefs.load(schedule.storage)
    await settle()
    assert schedule.prefs.excluded_tracks == ()
    assert summary(schedule) is None
    values[STORED] = ["Open Space"]  # the default, stored explicitly
    await schedule.prefs.load(schedule.storage)
    await settle()
    assert summary(schedule) == "Hidden: Open space"
    assert cast(ft.Icon, filter_button(schedule).icon).badge is None


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


def test_the_registry_is_what_the_sheet_reads() -> None:
    """The groups come from conference.toml, not code: a moved track moves its chip."""
    talk = next(t for t in INFO.tracks if t.key == "Talk")
    moved = dataclasses.replace(talk, group="community")
    edited = dataclasses.replace(
        INFO, tracks=tuple(moved if t.key == "Talk" else t for t in INFO.tracks)
    )
    groups = {g.label: g.tracks for g in filter_groups(edited, {"Talk", "Keynote"})}
    assert groups == {"Talks and keynotes": ("Keynote",), "Community": ("Talk",)}


async def test_the_summary_keeps_its_place_so_the_day_pages_keep_theirs(
    shown: Show,
) -> None:
    """#313: a line that came and went shifted the day pages, which Flutter rebuilt."""
    schedule = await shown()

    def column() -> list[ft.Control]:
        content = schedule.tabs.content
        assert isinstance(content, ft.Column)
        return content.controls

    before = column()
    assert summary(schedule) == "Hidden: Open space"
    (show_all,) = find(
        schedule.session, ft.Semantics, lambda c: c.identifier == "schedule.show_all"
    )
    await click(schedule, show_all.content)  # pyright: ignore[reportArgumentType]
    after = column()
    assert summary(schedule) is None
    assert len(after) == len(before)
    assert [type(c) for c in after][2:] == [type(c) for c in before][2:]
    pages = after[-1]  # the day pages, over the landing note (D-241)
    assert isinstance(pages, ft.Stack) and isinstance(pages.controls[-1], ft.TabBarView)
