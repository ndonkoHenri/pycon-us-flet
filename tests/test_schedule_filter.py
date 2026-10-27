"""Tests for the Schedule's track filter: its words and its summary (#87).

The pure words are checked on the 2026 year data; the sheet is
``test_schedule_filter_sheet.py``'s.

STORE-09, SCHED-09, SCHED-10; D-20, D-178. The screen renders in a real Flet session
through ``tests/schedule_view.py``'s ``shown`` fixture, whose ``AppScaffold`` stand-in
places the app bar's actions, so the ``TUNE`` action, the sheet (``ft.use_dialog``),
the chips and the summary run as Flet runs them; ``tests/filter_sheet.py`` finds and
taps them. How the sheet looks and scrolls at 200 % text is a device check (#87).
"""

import dataclasses
from typing import cast

import flet as ft

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
from tests import filter_sheet, schedule_view
from tests.filter_sheet import (
    INFO,
    STORED,
    Show,
    chip_parts,
    click,
    filter_button,
    stored,
    summary,
)
from tests.sessions import find, settle

# The Schedule's fixtures, shared by name: pytest finds fixtures among a module's names.
now = schedule_view.now
memory = schedule_view.memory
conference = schedule_view.conference
shown = schedule_view.shown
encoded = filter_sheet.encoded

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


# ------------------------------------------------------------------ the summary


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


def test_the_registry_is_what_the_sheet_reads() -> None:
    """The groups come from conference.toml, not code: a moved track moves its chip."""
    talk = next(t for t in INFO.tracks if t.key == "Talk")
    moved = dataclasses.replace(talk, group="community")
    edited = dataclasses.replace(
        INFO, tracks=tuple(moved if t.key == "Talk" else t for t in INFO.tracks)
    )
    groups = {g.label: g.tracks for g in filter_groups(edited, {"Talk", "Keynote"})}
    assert groups == {"Talks and keynotes": ("Keynote",), "Community": ("Talk",)}
