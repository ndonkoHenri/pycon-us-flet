"""The Schedule's filter sheet: grouped track chips, Reset and a live count (D-20).

ux.md §5.3. ``screens/schedule_filter.py`` owns the filter (the stored list, the edits,
the action and the summary) and shows this sheet through ``ft.use_dialog``; here is what
it shows, so each module stays under about 400 lines (D-66):

- ``filter_sheet()``, a modal ``BottomSheet`` with a drag handle, as tall as its chips
  need and scrolling past the screen at large text: "Filter sessions" and Reset on top,
  "Show N sessions" at the bottom, both in place while the chips scroll between them;
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
from pycon_us.ui.session_rows import semantics_key

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
"""The sheet's heading for each track group of ``conference.toml`` (``TRACK_GROUPS``)."""

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
    on_toggle: Toggle,
    on_reset: Callable[[], object],
    on_close: Callable[[], None],
    on_tracks_page: Callable[[], None],
    reduce_motion: bool,
) -> ft.BottomSheet:
    """Return the filter sheet (ux.md §5.3): title and Reset, chips, the count button.

    The title and the button stay in place while the chips scroll between them, so at
    200 % text the way out is always on screen.

    Args:
        info: The year's facts: the tracks' names.
        groups: The chips to offer, by heading (``filter_groups()``).
        excluded: The hidden track keys; their chips are not selected.
        count: The sessions the Schedule shows with this filter, on all days.
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
                expand=True,
                content=ft.Text(
                    "Filter sessions", theme_style=ft.TextThemeStyle.TITLE_LARGE
                ),
            ),
            ft.MergeSemantics(
                content=ft.Semantics(
                    identifier=f"{SCREEN}.filter.reset",
                    content=ft.TextButton(
                        "Reset",
                        tooltip=f"Reset to the default: hide {default}",
                        on_click=on_reset,
                    ),
                )
            ),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    body: list[ft.Control] = []
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
                run_spacing=0,  # each chip's 48 dp target already spaces the runs
            )
        )
    body.append(
        ft.Container(
            ft.TextButton(
                "What do these mean?",
                icon=ft.Icons.HELP_OUTLINE,
                on_click=on_tracks_page,
            ),
            margin=ft.Margin.only(left=-12, top=8),  # its label on the chips' edge
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
        ft.MergeSemantics(
            content=ft.Semantics(
                identifier=f"{SCREEN}.filter.show",
                content=ft.FilledButton(
                    count_label(count),
                    disabled=count == 0,
                    on_click=on_close,
                    expand=True,
                ),
            )
        )
    )
    return ft.BottomSheet(
        ft.Column(
            [
                header,
                ft.Column(  # the chips scroll; the title and the button stay
                    body,
                    spacing=0,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                    expand_loose=True,
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
        ),
        show_drag_handle=True,
        scrollable=True,  # as tall as the chips need, up to the screen (200 % text)
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
    """Return a track's chip: selected while its sessions show; a tap applies at once."""

    @report_errors
    async def selected(e: ft.Event[ft.Chip]) -> None:
        # Flutter flips the chip and sends its new state before the event (chip.dart).
        await on_toggle(key, e.control.selected)

    return ft.MergeSemantics(
        content=ft.Semantics(
            identifier=f"{SCREEN}.filter.{semantics_key(key)}",
            content=ft.Chip(
                label=info.track_name(key),
                selected=shown,
                show_checkmark=True,
                on_select=selected,
            ),
        )
    )
