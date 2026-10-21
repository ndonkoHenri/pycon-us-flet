"""What a screen shows instead of its content: ``EmptyState`` and ``SkeletonList``.

``EmptyState`` is for a screen with nothing to show (ux.md §4.1): no match, an unknown
id, no data after a failed first fetch. It says why in one sentence and names a way
out, as its button or, where no button can help, in its sentence (§4.6).
``SkeletonList`` is shown only while there is no data at all and the first fetch runs
(NEW-03): with data, the screen shows it and the status strip says how old it is
(D-32). ``NoDataState`` picks between the skeleton and the failed first fetch for every
screen that shows the feed.
"""

from collections.abc import Callable
from typing import Any

import flet as ft

from pycon_us.feed_refresh import Problem
from pycon_us.prefs import use_prefs
from pycon_us.theme import use_tokens
from pycon_us.theme_hc import hc_border
from pycon_us.ui.links import OPENS_IN, LinkKind, external

ICON_SIZE = 48
"""The empty state's icon, in dp (ux.md §3.9)."""

SKELETON_ROWS = 5
"""Placeholder rows in a ``SkeletonList`` (ux.md §3.9): enough to fill a phone."""

SHIMMER_MS = 1500
"""One sweep of the skeleton's shimmer (Flet's default period), 0 under reduced motion."""

NO_DATA_BODY: dict[Problem, str] = {
    "offline": "Connect to the internet and try again.",
    "server": "The schedule couldn't be read. Try again in a few minutes.",
}
"""The way out after a failed first fetch, by why it failed (D-146, ux.md §4.6)."""


def EmptyState(
    title: str,
    *,
    icon: ft.IconData,
    body: str | None = None,
    action: str | None = None,
    on_action: Callable[[], Any] | None = None,
    disabled: bool = False,
    link_id: str | None = None,
    identifier: str | None = None,
) -> ft.Control:
    """Return a screen's empty state: an icon, why it is empty, and the way out.

    Centred, padded and without a fixed height, so it reflows at 200 % text inside the
    screen's ``ListView``. For screen readers the title is a level-2 heading node of
    its own, under the page's title (D-211), and, with the body, inside a live region,
    so the state is announced when it replaces a list (D-33); the icon is decorative;
    the button is a stop of its own.

    Every empty state names a way out (ux.md §4.6): ``action`` is a button that takes
    the user somewhere useful ("Open schedule", "Try again"). Only a state where no
    button can help names it in its sentence instead ("Search covers all days and
    ignores your filters.").

    Args:
        title: Why the screen is empty, as one sentence in sentence case: "This
            session isn't in the current schedule".
        icon: An outlined icon for the case (D-27), e.g. ``CLOUD_OFF_OUTLINED``.
        body: A second, smaller line, if the title needs one.
        action: The button's label, a verb ("Open schedule"); given with
            ``on_action``.
        on_action: What the button does, wrapped in ``report_errors`` by the caller.
        disabled: The button is shown but cannot be tapped, while its action runs: it
            stays in place, so a screen reader's focus stays on it.
        link_id: For a button that opens a web page (``on_action`` calls
            ``open_link()``), its identifier: the button then looks and reads as any
            link that leaves the app, ``OPEN_IN_NEW`` and "Opens in browser", and is
            marked as one (``links.external()``, ux.md §4.7).
        identifier: The text's semantics identifier for UI tests, e.g.
            ``session.not_found`` (decisions §M).

    Raises:
        ValueError: Only one of ``action`` and ``on_action`` is given.
    """
    if (action is None) != (on_action is None):
        raise ValueError("an empty state's action needs both a label and a handler")
    texts: list[ft.Control] = [
        # A container of its own: without it, the heading flag and the body's text
        # merge into the live region, and the whole state reads as one heading.
        ft.Semantics(
            header=True,
            heading_level=2,
            container=True,
            content=ft.Text(
                title,
                theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
                text_align=ft.TextAlign.CENTER,
            ),
        )
    ]
    if body is not None:
        texts.append(
            ft.Text(
                body,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
                text_align=ft.TextAlign.CENTER,
            )
        )
    controls: list[ft.Control] = [
        ft.Icon(icon, size=ICON_SIZE, color=ft.Colors.ON_SURFACE_VARIANT),
        ft.Semantics(
            identifier=identifier,
            container=True,
            live_region=True,
            content=ft.Column(
                texts,
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ),
    ]
    if action is not None:
        button: ft.Control
        if link_id is None:
            button = ft.FilledTonalButton(action, on_click=on_action, disabled=disabled)
        else:
            button = external(
                link_id,
                ft.FilledTonalButton(
                    # On the text: an icon's label would be read before it (D-186).
                    ft.Text(
                        action, semantics_label=f"{action}\n{OPENS_IN[LinkKind.WEB]}"
                    ),
                    icon=ft.Icons.OPEN_IN_NEW,
                    on_click=on_action,
                    disabled=disabled,
                ),
            )
        controls.append(ft.Container(button, padding=ft.Padding.only(top=8)))
    return ft.Container(
        ft.Column(
            controls,
            spacing=16,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=32, vertical=48),
        alignment=ft.Alignment.TOP_CENTER,
    )


def NoDataState(
    problem: Problem | None,
    *,
    on_retry: Callable[[], Any],
    retrying: bool,
    identifier: str,
) -> ft.Control:
    """Return what a screen that shows the feed shows without any data (NEW-03).

    The skeleton while the first fetch runs, before it has failed; then "Can't load
    the schedule" with "Try again", its body by why the fetch failed (ux.md §4.1,
    §4.6). The state stays during a retry, its button disabled: swapping it for the
    skeleton would remove the focused button and lose a screen reader's place.

    Args:
        problem: Why the last fetch failed (``Conference.problem``), None before one has.
        on_retry: What "Try again" does: the user's refresh, ``Conference.refresh()``.
        retrying: A refresh the user asked for runs (``status() == "refreshing"``,
            D-181): the button is disabled, never during a quiet one, which a tap joins.
        identifier: The failed state's semantics identifier, ``<screen>.no_data``.
    """
    if problem is None:
        return SkeletonList()
    return EmptyState(
        "Can't load the schedule",
        icon=ft.Icons.CLOUD_OFF_OUTLINED,
        body=NO_DATA_BODY[problem],
        action="Try again",
        on_action=on_retry,
        disabled=retrying,
        identifier=identifier,
    )


@ft.component
def SkeletonList(label: str = "Loading schedule") -> ft.Control:
    """Placeholder rows shown while the first fetch runs and there is no data at all.

    Five rows shaped like session rows (a time, a badge, two lines of title, a line of
    meta), in ``surface_container_highest``. ``ft.Shimmer`` sweeps a lighter band across
    them; under reduced motion (``prefs.motion_ms()``, D-173) the rows stay still. The
    shimmer is not ambient motion (D-34): like a progress indicator, it shows work
    running and goes when the data arrives. Screen readers hear one node, ``label``.
    In high contrast, where that fill is the surface, each placeholder is an unfilled
    1 dp ``outline`` shape instead, and the shimmer paints those lines (D-306).

    Args:
        label: What is loading, read by screen readers.
    """
    prefs = use_prefs()
    hc = use_tokens().high_contrast
    period = prefs.motion_ms(SHIMMER_MS)
    rows: ft.Control = ft.Column(
        [_placeholder_row(hc) for _ in range(SKELETON_ROWS)], spacing=0
    )
    if period:
        # The shimmer paints what the rows paint in its own colours: in HC, the lines.
        base, highlight = (
            (ft.Colors.OUTLINE, ft.Colors.SURFACE)
            if hc
            else (ft.Colors.SURFACE_CONTAINER_HIGHEST, ft.Colors.SURFACE_CONTAINER_LOW)
        )
        rows = ft.Shimmer(
            rows, base_color=base, highlight_color=highlight, period=period
        )
    return ft.Semantics(
        label=label,
        container=True,
        exclude_semantics=True,  # the placeholders say nothing
        content=rows,
    )


def _placeholder_row(hc: bool) -> ft.Control:
    """One row in a session row's shape: a time on the left, three lines beside it.

    ``hc``: high contrast, whose placeholders are outlined (``hc_border()``).
    """
    return ft.Container(
        ft.Row(
            [
                _block(40, 16, hc),  # the time
                ft.Column(
                    [
                        _block(56, 16, hc),  # a track badge
                        _line(16, 1, 0, hc),  # the title, on two lines
                        _line(16, 3, 2, hc),
                        _line(12, 2, 3, hc),  # time and room
                    ],
                    spacing=8,
                    expand=True,
                ),
            ],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        padding=ft.Padding.symmetric(horizontal=16, vertical=12),
    )


def _block(width: int, height: int, hc: bool) -> ft.Container:
    """A placeholder of a fixed size, rounded like a badge; outlined in HC."""
    return ft.Container(
        width=width,
        height=height,
        border_radius=8,
        bgcolor=_fill(hc),
        border=hc_border(hc),
    )


def _fill(hc: bool) -> ft.ColorValue | None:
    """A placeholder's fill: none in HC, where the shimmer would paint it all in ink."""
    return None if hc else ft.Colors.SURFACE_CONTAINER_HIGHEST


def _line(height: int, filled: int, empty: int, hc: bool) -> ft.Row:
    """A placeholder line over ``filled`` parts of the width, then ``empty`` parts.

    Outlined in HC, as ``_block()`` is.
    """
    bar = ft.Container(
        height=height,
        expand=filled,
        border_radius=4,
        bgcolor=_fill(hc),
        border=hc_border(hc),
    )
    gap = [ft.Container(expand=empty)] if empty else []
    return ft.Row([bar, *gap], spacing=0)
