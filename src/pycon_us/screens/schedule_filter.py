"""The Schedule's track filter: its app bar action, its summary and its edits (D-20).

Only the Schedule filters (D-20, D-178): this module is what it places for that.

- ``use_track_filter()``, the Schedule's hook: the ``TUNE`` action ("Filter sessions"),
  with a dot only when the filter differs from the default; the summary under the day
  tabs whenever a track is hidden, the default included ("Hidden: Open space" with
  "Show all"); and the sheet (``screens/schedule_sheet.py``, ux.md §5.3), a modal
  ``BottomSheet`` shown through ``ft.use_dialog``.
- The words, as pure functions: ``hidden_tracks()``, ``summary_text()`` and
  ``differs_from_default()``.

A chip applies at once and persists (``Prefs.save``), so a swipe that dismisses the
sheet keeps it (Ionic dropped the changes). The filter is the stored list of hidden
track keys, ``Prefs.excluded_tracks``: absent, the default (open spaces hidden); an
explicit empty list hides nothing. Changing it never scrolls a list (#313): the
Schedule's memoised path re-renders only the slots the change touched (D-153, D-178).
"""

import asyncio
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass

import flet as ft

from pycon_us.config import ConferenceInfo
from pycon_us.prefs import Prefs, use_prefs
from pycon_us.screens.schedule_sheet import (
    DEFAULT_HIDDEN,
    filter_groups,
    filter_sheet,
)
from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors
from pycon_us.ui.badges import NOT_SAVED, SNACK_BAR_MS, selection_click
from pycon_us.ui.semantics import named

SCREEN = "schedule"
"""The screen's name in the identifiers (decisions §M)."""

TRACKS_PAGE = "/more/tracks"
"""Where "What do these mean?" leads: Tracks & session types (ux.md §5.10)."""

SUMMARY_NAMES = 3
"""How many hidden tracks the summary names before "and N more"."""


@dataclass(frozen=True)
class TrackFilter:
    """What the Schedule places for its filter (``use_track_filter()``).

    Attributes:
        button: The app bar's ``TUNE`` action, which opens the sheet.
        summary: The line under the day tabs, or an empty placeholder while nothing
            is hidden: always one control, so the controls after it keep their
            places. Without it, the line coming or going shifted the day pages in
            Flutter's ``Column``, which rebuilt them and put every day list back at
            its top (#313).
        show_all: Hide no track; stable across renders, so a memoised day list given
            it ("Clear filters") stays skipped (D-153).
    """

    button: ft.Control
    summary: ft.Control
    show_all: Callable[[], object]


def hidden_tracks(
    info: ConferenceInfo, tracks: Collection[str], excluded: Iterable[str]
) -> tuple[str, ...]:
    """Return the tracks the filter hides that the feed has, in the sheet's order.

    A stored key that the feed does not have (open spaces before they are published)
    hides nothing, so it is not said to.

    Args:
        info: The year's facts.
        tracks: The track keys the feed's schedule holds.
        excluded: The stored filter, ``Prefs.excluded_tracks``.
    """
    hidden = set(excluded)
    return tuple(
        key
        for group in filter_groups(info, tracks)
        for key in group.tracks
        if key in hidden
    )


def summary_text(info: ConferenceInfo, hidden: Sequence[str]) -> str | None:
    """Return the summary under the day tabs: "Hidden: Open space", or None.

    Names the first ``SUMMARY_NAMES`` tracks by ``track_name()``, as their chips and
    badges do, then "and N more": "Hidden: Talk, Tutorial, Poster", "Hidden: Talk,
    Keynote, AI and 4 more". A list of labels, not a sentence: "Hiding: Talk and Open
    space" read as one talk and one open space, where the badge names stand for kinds.

    Args:
        info: The year's facts.
        hidden: The hidden tracks, from ``hidden_tracks()``.
    """
    if not hidden:
        return None
    names = [info.track_name(key) for key in hidden]
    named = ", ".join(names[:SUMMARY_NAMES])
    if len(names) > SUMMARY_NAMES:
        return f"Hidden: {named} and {len(names) - SUMMARY_NAMES} more"
    return f"Hidden: {named}"


def differs_from_default(tracks: Collection[str], excluded: Iterable[str]) -> bool:
    """Whether the filter hides other tracks than the default does (D-20's dot).

    Compared over the tracks the feed has, as the summary and the chips are, so a
    stored key the feed lacks never lights the dot with nothing to show for it.

    Args:
        tracks: The track keys the feed's schedule holds.
        excluded: The stored filter, ``Prefs.excluded_tracks``.
    """
    present = set(tracks)
    return set(excluded) & present != set(DEFAULT_HIDDEN) & present


def use_track_filter(
    info: ConferenceInfo, tracks: frozenset[str], count: int
) -> TrackFilter:
    """The Schedule's filter: its action, its summary and its sheet (a hook, D-70).

    Call it on every render, before any early return. Edits take turns (one lock), so
    two quick chip taps both count: each reads the filter the last one saved.

    Args:
        info: The year's facts.
        tracks: The track keys the feed's schedule holds, on any day.
        count: The sessions the Schedule shows with the current filter, on all days.
    """
    page = ft.context.page
    svc = use_services()
    prefs = use_prefs()
    is_open, set_open = ft.use_state(False)
    lock = ft.use_memo(asyncio.Lock, [])
    excluded = prefs.excluded_tracks

    @report_errors
    async def show_all() -> None:
        await _save(prefs, svc, lock, lambda _: ())

    on_show_all = ft.use_callback(show_all, [])

    @report_errors
    async def reset() -> None:
        await _save(prefs, svc, lock, lambda _: DEFAULT_HIDDEN)

    @report_errors
    async def toggle(key: str, shown: bool) -> None:
        await selection_click(svc.haptics)  # first: the tap is felt at once
        await _save(prefs, svc, lock, lambda now: _toggled(now, key, shown=shown))

    @report_errors
    def what_they_mean() -> None:
        set_open(False)
        page.navigate(TRACKS_PAGE)

    @report_errors
    def open_sheet() -> None:
        set_open(True)

    @report_errors
    def close_sheet() -> None:
        set_open(False)

    changed = differs_from_default(tracks, excluded)
    # Built only while shown: the Schedule re-renders on every favourite and day
    # switch (D-153). The hook itself is called on every render (D-70).
    ft.use_dialog(
        filter_sheet(
            info,
            filter_groups(info, tracks),
            set(excluded),
            count,
            changed=changed,
            on_toggle=toggle,
            on_reset=reset,
            on_close=close_sheet,
            on_tracks_page=what_they_mean,
            reduce_motion=prefs.reduce_motion,
        )
        if is_open and tracks
        else None
    )
    text = summary_text(info, hidden_tracks(info, tracks, excluded))
    return TrackFilter(
        button=_button(changed, open_sheet),
        summary=_summary(text, on_show_all) if text else ft.Container(),
        show_all=on_show_all,
    )


async def _save(
    prefs: Prefs,
    svc: Services,
    lock: asyncio.Lock,
    change: Callable[[tuple[str, ...]], tuple[str, ...]],
) -> None:
    """Store the filter ``change`` makes of the current one, one edit at a time.

    The lock makes a second tap wait for the first one's write, so it reads the filter
    that one saved: without it, both would start from the same filter and the second
    would drop the first. A failed write keeps the change for the session and says so
    (D-120).
    """
    async with lock:
        excluded = change(prefs.excluded_tracks)
        if not await prefs.save(svc.storage, excluded_tracks=excluded):
            _not_saved(ft.context.page)


def _toggled(excluded: tuple[str, ...], key: str, *, shown: bool) -> tuple[str, ...]:
    """Return ``excluded`` with ``key`` shown (removed) or hidden (added at the end)."""
    kept = tuple(k for k in excluded if k != key)
    return kept if shown else (*kept, key)


def _not_saved(page: ft.Page) -> None:
    """Say that a filter change shows but will be lost on relaunch (D-120)."""
    page.show_dialog(
        ft.SnackBar(
            ft.Text(NOT_SAVED),
            behavior=ft.SnackBarBehavior.FLOATING,
            duration=SNACK_BAR_MS,
        )
    )


def _button(changed: bool, on_click: Callable[[], None]) -> ft.Control:
    """Return the ``TUNE`` action: "Filter sessions", with a dot when changed (D-20)."""
    return ft.MergeSemantics(  # the identifier on the button's own node (D-190)
        content=ft.Semantics(
            identifier=f"{SCREEN}.filter",
            # The name is the node's label, not the tooltip: beside a value,
            # Android read the node as "Changed" alone. The dot says "changed" to
            # the eye; a screen reader hears it after the name.
            label="Filter sessions",
            value="Changed" if changed else None,
            button=True,
            content=ft.IconButton(
                # The dot on the icon itself: on the 48 dp button it sat at the
                # target's corner, by the screen's edge.
                ft.Icon(
                    ft.Icons.TUNE, badge=ft.Badge(small_size=8) if changed else None
                ),
                # Shown on a long press, but not said again: iOS reads a node's
                # tooltip after its label (D-184).
                tooltip=ft.Tooltip("Filter sessions", exclude_from_semantics=True),
                on_click=on_click,
            ),
        )
    )


def _summary(text: str, on_show_all: Callable[[], object]) -> ft.Control:
    """Return the line under the day tabs: what is hidden, and "Show all" (D-20).

    The words and the button share a wrapping row, the button at its end: at large
    text the button moves under the words whole, instead of squeezing them into a
    narrow column beside it.
    """
    words = ft.Semantics(
        identifier=f"{SCREEN}.filter_summary",
        content=ft.Text(
            text,
            theme_style=ft.TextThemeStyle.BODY_MEDIUM,
            color=ft.Colors.ON_SURFACE_VARIANT,
        ),
    )
    show_all = named(
        f"{SCREEN}.show_all", ft.TextButton("Show all", on_click=on_show_all)
    )
    return ft.Container(
        ft.Row(
            [
                # Unlabelled, so decorative: the words say it. In a 48 dp box, so it
                # stays beside the first line, which the button's height centres.
                ft.Container(
                    ft.Icon(
                        ft.Icons.FILTER_LIST,
                        size=18,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    height=48,
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Row(
                    [words, show_all],
                    wrap=True,
                    spacing=8,
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    expand=True,  # a bounded width, so the words wrap in it
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        padding=ft.Padding.only(left=16, right=8),
    )
