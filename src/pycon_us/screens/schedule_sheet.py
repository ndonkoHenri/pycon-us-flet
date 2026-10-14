"""The Schedule's filter sheet: grouped track chips, Reset and a live count (D-20).

ux.md §5.3. ``screens/schedule_filter.py`` owns the filter (the stored list, the edits,
the action and the summary) and shows this sheet through ``ft.use_dialog``; here is what
it shows, so each module stays under about 400 lines (D-66):

- ``filter_sheet()``, a modal ``BottomSheet`` with a drag handle, the screen's height
  until U32 (#238): "Filter sessions" and Reset scroll with the chips, and "Show N
  sessions" stays pinned under them;
- a ``Chip`` per track the feed has, with its check (not colour alone, D-33), named by
  ``track_name()`` as its badge is and grouped under ``conference.toml``'s track groups
  (``filter_groups()``), then "What do these mean?" to the Tracks hub;
- ``count_label()``, the button's words.
"""

from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass

import flet as ft

from pycon_us.config import TRACK_GROUPS, ConferenceInfo
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import EXCLUDED_TRACKS
from pycon_us.ui.semantics import named, semantics_key

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
"""The sheet's heading for each of ``conference.toml``'s ``TRACK_GROUPS``."""

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

    Groups come in ``TRACK_GROUPS``' order and tracks in the registry's; a track the
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
) -> ft.BottomSheet:
    """Return the filter sheet (ux.md §5.3): title and Reset, chips, the count button.

    Only the button is pinned: the title and Reset scroll with the chips, so at the
    largest text the chips keep most of the sheet and the way out is still on screen.

    Args:
        info: The year's facts: the tracks' names.
        groups: The chips to offer, by heading (``filter_groups()``).
        excluded: The hidden track keys; their chips are not selected.
        count: The sessions the Schedule shows with this filter, on all days.
        changed: The filter differs from the default (``differs_from_default()``);
            Reset is disabled while it does not, since it would do nothing.
        on_toggle: A chip's tap: the track's key, and whether it now shows.
        on_reset: Reset: back to the default.
        on_close: "Show N sessions", and a dismissal (a swipe, a tap outside).
        on_tracks_page: "What do these mean?".
        reduce_motion: The OS asks for less motion: the sheet appears without its
            slide (D-34, D-173).
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
            padding=ft.Padding.only(left=16, right=16, bottom=16),
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
        show_drag_handle=True,
        scrollable=True,  # the screen's height, so the chips have room at 200 % text
        use_safe_area=True,
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
            label=info.track_name(key),
            selected=shown,
            show_checkmark=True,
            # Unselected, only its outline on the sheet (M3's filter chip). Flutter
            # draws a chip on a canvas Material, which paints `surface` whatever
            # the chip's colour (a transparent one still showed white in light,
            # a dark well in dark), so the chip paints the sheet's colour on it.
            bgcolor=SHEET_COLOR,
            on_select=selected,
        ),
    )
