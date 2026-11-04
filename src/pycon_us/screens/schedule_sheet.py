"""The Schedule's filter sheet: grouped track chips, Reset and a live count (D-20).

ux.md §5.3. `screens/schedule_filter.py` owns the filter (the stored list, the edits,
the action and the summary) and shows this sheet through `ft.use_dialog`; here is what
it shows, so each module stays under about 400 lines (D-66):

- `filter_sheet()`, a modal `BottomSheet` with a drag handle (none with a
  screen reader on, D-485), the screen's height
  until U32 (#238): "Filter sessions" and Reset scroll with the chips, and "Show N
  sessions" stays pinned under them;
- a `Chip` per track the feed has, with its check (not colour alone, D-33), named by
  `track_name()` as its badge is and grouped under `conference.toml`'s track groups
  (`filter_groups()`), then "What do these mean?" to the Tracks hub; its label,
  `chip_label()`, wraps at large text (D-249);
- `count_label()`, the button's words.
"""

from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass

import flet as ft

from pycon_us.config import ConferenceInfo
from pycon_us.services.errors import report_errors
from pycon_us.services.pref_keys import EXCLUDED_TRACKS
from pycon_us.theme_hc import hc_sheet_shape
from pycon_us.ui.semantics import named, semantics_key
from pycon_us.year_tracks import TRACK_GROUPS

SCREEN = "schedule"
"""The screen's name in the identifiers (decisions §M)."""

DEFAULT_HIDDEN: tuple[str, ...] = tuple(EXCLUDED_TRACKS.default)
"""The tracks hidden while the user has chosen nothing: open spaces (D-20)."""

GROUP_LABELS = {
    "talks": "Talks and keynotes",
    "hands-on": "Hands-on",
    "community": "Community",
    "logistics": "Breaks and notices",
}
"""The sheet's heading for each of `conference.toml`'s `TRACK_GROUPS`."""

SHEET_COLOR = ft.Colors.SURFACE_CONTAINER_LOW
"""M3's bottom sheet background, which the unselected chips paint. The sheet keeps its
default rather than being given it: a colour given to a shown sheet stayed light when
the device turned dark."""

type Toggle = Callable[[str, bool], Awaitable[None]]
"""What a chip tap does: show (True) or hide (False) a track, by its key."""


@dataclass(frozen=True)
class FilterGroup:
    """One heading of the sheet and its tracks.

    Attributes:
        label: The heading, e.g. "Talks and keynotes".
        tracks: Its track keys, in the registry's order.
    """

    label: str
    tracks: tuple[str, ...]


def filter_groups(
    info: ConferenceInfo, tracks: Collection[str]
) -> tuple[FilterGroup, ...]:
    """Return the sheet's groups: the given tracks under their group's heading.

    Groups come in `TRACK_GROUPS`' order and tracks in the registry's; a track the
    registry lacks (a new kind in next year's feed) goes to its stand-in's group,
    after the registry's tracks, by name. A group without tracks is left out.

    Args:
        info: The year's facts, with the track registry.
        tracks: The track keys to offer: those the feed's schedule holds.
    """
    registry = [t.key for t in info.tracks]
    known = [key for key in registry if key in tracks]
    unknown = sorted(
        (key for key in tracks if key not in registry), key=info.track_name
    )
    ordered = known + unknown
    return tuple(
        FilterGroup(
            GROUP_LABELS[group],
            tuple(key for key in ordered if info.track(key).group == group),
        )
        for group in TRACK_GROUPS
        if any(info.track(key).group == group for key in ordered)
    )


def count_label(count: int) -> str:
    """Return the sheet's button: "Show 87 sessions", "Show 1 session"."""
    return f"Show {count} session" if count == 1 else f"Show {count} sessions"


def filter_sheet(
    info: ConferenceInfo,
    groups: tuple[FilterGroup, ...],
    excluded: set[str],
    count: int,
    *,
    changed: bool,
    on_toggle: Toggle,
    on_reset: Callable[[], object],
    on_close: Callable[[], None],
    on_tracks_page: Callable[[], None],
    reduce_motion: bool,
    screen_reader: bool = False,
    high_contrast: bool = False,
) -> ft.BottomSheet:
    """Return the filter sheet (ux.md §5.3): title and Reset, chips, the count button.

    Only the button is pinned: the title and Reset scroll with the chips, so at the
    largest text the chips keep most of the sheet and the way out is still on screen.

    Args:
        info: The year's facts: the tracks' names.
        groups: The chips to offer, by heading (`filter_groups()`).
        excluded: The hidden track keys; their chips are not selected.
        count: The sessions the Schedule shows with this filter, on all days.
        changed: The filter differs from the default (`differs_from_default()`);
            Reset is disabled while it does not, since it would do nothing.
        on_toggle: A chip's tap: the track's key, and whether it now shows.
        on_reset: Reset: back to the default.
        on_close: "Show N sessions", and a dismissal (a swipe, a tap outside).
        on_tracks_page: "What do these mean?".
        reduce_motion: The OS asks for less motion: the sheet appears without its
            slide (D-34, D-173).
        screen_reader: A screen reader is on: no drag handle or scrim to stop on (D-485).
        high_contrast: HC is on screen: the sheet is the surface there, as the page
            under its scrim nearly is, so a 1 dp `outline` border draws its edge
            (D-306); the chips are outlined by the theme's chip theme.
    """
    default = ", ".join(info.track_name(key) for key in DEFAULT_HIDDEN)
    header = ft.Row(
        [
            ft.Semantics(
                header=True,
                heading_level=1,  # the sheet is a page of its own for a screen reader
                content=ft.Text(
                    "Filter sessions", theme_style=ft.TextThemeStyle.TITLE_LARGE
                ),
            ),
            named(
                f"{SCREEN}.filter.reset",
                ft.TextButton(
                    "Reset",
                    tooltip=f"Reset to the default: hide {default}",
                    disabled=not changed,
                    on_click=on_reset,
                ),
            ),
        ],
        # Wrapping, Reset at the end: at large text it moves under the title whole,
        # where beside it the title broke inside "sessions".
        wrap=True,
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    # 8 dp under it, as when it sat above the scrolling chips.
    body: list[ft.Control] = [ft.Container(header, padding=ft.Padding.only(bottom=8))]
    for group in groups:
        body.append(
            ft.Semantics(
                header=True,
                heading_level=2,
                content=ft.Container(
                    ft.Text(
                        group.label,
                        theme_style=ft.TextThemeStyle.TITLE_SMALL,
                        color=ft.Colors.PRIMARY,
                    ),
                    padding=ft.Padding.only(top=16, bottom=8),
                ),
            )
        )
        body.append(
            ft.Row(
                [
                    _chip(info, key, key not in excluded, on_toggle)
                    for key in group.tracks
                ],
                wrap=True,
                spacing=8,
                # 8 dp, as between the chips beside each other: at large text a chip
                # outgrows its 48 dp target, and with 4 dp the rows touched.
                run_spacing=8,
            )
        )
    body.append(
        ft.Container(
            named(
                f"{SCREEN}.filter.tracks",  # no track's key is "tracks", "reset", "show"
                ft.TextButton(
                    "What do these mean?",
                    icon=ft.Icons.HELP_OUTLINE,
                    on_click=on_tracks_page,
                    # Its icon near the chips' edge, as a link under them; still
                    # 48 dp tall.
                    style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=4)),
                ),
            ),
            padding=ft.Padding.only(top=8),
            # At the start: the column stretches its children, and a stretched
            # button would centre its label across the sheet.
            alignment=ft.Alignment.CENTER_LEFT,
        )
    )
    footer: list[ft.Control] = []
    if count == 0:
        footer.append(
            ft.Text(
                "Select at least one type",
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
                text_align=ft.TextAlign.CENTER,
            )
        )
    footer.append(
        named(
            f"{SCREEN}.filter.show",
            ft.FilledButton(
                # Centred when it wraps at large text, with its own padding:
                # Flutter shrinks a button's padding as the text grows, and the
                # label then touched the rounded ends.
                content=ft.Text(count_label(count), text_align=ft.TextAlign.CENTER),
                style=ft.ButtonStyle(
                    padding=ft.Padding.symmetric(horizontal=24, vertical=12)
                ),
                # M3's filled button lies flat. With a style, Flet sets every
                # state's elevation to this (1 by default), and the shadow then
                # showed through the disabled button's faint fill, dark grey.
                elevation=0,
                disabled=count == 0,
                on_click=on_close,
                # Full width from the column's STRETCH: an expand here would
                # take the sheet's whole height.
            ),
        )
    )
    return ft.BottomSheet(
        ft.Container(  # 16 dp gutters (ux.md §3.6); the button clears the home bar
            # No handle above the title with a screen reader on: the top is its own.
            padding=ft.Padding.only(
                left=16, right=16, bottom=16, top=16 if screen_reader else 0
            ),
            content=ft.Column(
                [
                    # The title and the chips scroll; the button stays: pinned, the
                    # title took about half the sheet at the largest text. Flet sizes
                    # a scrolling Column to at least the room it is given
                    # (scrollable_control.dart, #6450), and a ListView shrink-wraps
                    # only without a bound, so the sheet takes the screen's height.
                    ft.Column(
                        body,
                        spacing=0,
                        scroll=ft.ScrollMode.AUTO,
                        expand=True,
                        # Full width for the header, so its wrapping row puts Reset
                        # at the end; it shrank to its content and Reset sat by the
                        # title.
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                    ft.Column(
                        footer,
                        spacing=8,
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                ],
                spacing=8,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        ),
        show_drag_handle=not screen_reader,
        dismissible=not screen_reader,
        scrollable=True,  # the screen's height, so the chips have room at 200 % text
        use_safe_area=True,
        shape=hc_sheet_shape(high_contrast),
        on_dismiss=lambda _: on_close(),
        # Its slide is motion: none under reduced motion (D-34, D-173).
        animation_style=ft.AnimationStyle.no_animation() if reduce_motion else None,
    )


def _chip(
    info: ConferenceInfo,
    key: str,
    shown: bool,
    on_toggle: Toggle,
) -> ft.Control:
    """Return a track's chip: selected while its sessions show; a tap applies now."""

    @report_errors
    async def selected(e: ft.Event[ft.Chip]) -> None:
        # Flutter flips the chip and sends its new state before the event (chip.dart).
        await on_toggle(key, e.control.selected)

    return named(
        f"{SCREEN}.filter.{semantics_key(key)}",
        ft.Chip(
            label=chip_label(info.track_name(key), shown),
            selected=shown,
            # The label draws the check and the side padding (chip_label(), F69).
            show_checkmark=False,
            padding=ft.Padding.symmetric(vertical=8),
            label_padding=ft.Padding.all(0),
            # Unselected, only its outline on the sheet (M3's filter chip). Flutter
            # draws a chip on a canvas Material, which paints `surface` whatever
            # the chip's colour (a transparent one still showed white in light,
            # a dark well in dark), so the chip paints the sheet's colour on it.
            bgcolor=SHEET_COLOR,
            on_select=selected,
        ),
    )


def chip_label(name: str, shown: bool) -> ft.Container:
    """Return a filter chip's label: the check while it is selected, then its name.

    The name may wrap, so at the largest text a long one ("Lightning talks") shows
    whole on two lines (D-249). Flutter's chip puts a string label on one line and
    fades the rest; a `Text` label wraps, but the chip measures the label's height
    at its whole width, then lays it out beside its check mark and paddings no
    taller than that, so a name that fits one line only at the whole width lost its
    second line (F69). So the chip draws neither: the label holds the check and the
    side padding, and gets the same width both times.

    Args:
        name: The track's name, as its badge says it (`track_name()`).
        shown: The chip is selected: its sessions show.
    """
    name_text = ft.Text(
        name,
        # The chip's text style says one line; the most a track name takes at the
        # largest text on the narrowest phone is a word per line.
        max_lines=3,
        # Loose in the row: as wide as the name, and narrower when it must wrap.
        expand=True,
        expand_loose=True,
    )
    check = ft.Icon(
        ft.Icons.CHECK,
        size=18,  # M3's chip icon
        color=ft.Colors.PRIMARY,  # Flutter's selected check mark
        # It grows with the text, as Flutter's own check mark does.
        apply_text_scaling=True,
    )
    return ft.Container(
        ft.Row(
            [check, name_text] if shown else [name_text],
            spacing=8,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        # M3's 8 dp chip padding plus its 8 dp label padding; the check takes the
        # label padding's place at the start.
        padding=ft.Padding.only(left=8 if shown else 16, right=16),
        # Painted, so the label takes a tap anywhere on it: the chip hit-tests only
        # its label's centre (chip.dart), which for "AI" falls between the check
        # and the name, where a bare row would miss it.
        bgcolor=ft.Colors.TRANSPARENT,
    )
