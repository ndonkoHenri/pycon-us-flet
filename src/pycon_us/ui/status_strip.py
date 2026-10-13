"""The status strip and the minute tick: ``StatusStrip``, ``strip_line()``, ``use_minute()``.

``StatusStrip`` says when the data is not fresh, with Refresh until pull-to-refresh
(U1) arrives (D-32, D-146); the screens that show the feed's state place it under
their app bar. It ticks every ``TICK_SECONDS`` while it shows (D-40, D-175), and
``use_minute()`` is that tick as a hook, for any other view that depends on
``clock.now()``, such as the Map's "Now:" lines (D-188). ``current_minute()`` and
``stop_ticks()`` are the ticking effects' state and cleanup (D-200).
"""

from datetime import datetime, tzinfo

import flet as ft

from pycon_us import clock
from pycon_us.core.timefmt import ago_label, day_label, local_date, time_label
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import Status, use_conference
from pycon_us.theme import use_tokens

STATUS_ICONS: dict[Status, ft.IconData] = {
    "refreshing": ft.Icons.SYNC,
    "stale": ft.Icons.UPDATE,
    "offline": ft.Icons.CLOUD_OFF_OUTLINED,
    "problem": ft.Icons.SYNC_PROBLEM,
}
"""The strip's icon for each status it shows; the line beside it says the same."""


def strip_line(
    status: Status,
    fetched_at: datetime | None,
    now: datetime,
    zone: tzinfo,
    *,
    use_24h: bool,
) -> str | None:
    """Return what the status strip says, or None when it is hidden (D-32, D-146).

    Args:
        status: ``Conference.status()``.
        fetched_at: When the data on screen was fetched; None without data.
        now: ``clock.now()``, so the Developer fake clock moves the age too.
        zone: The conference's zone; times are always conference time (D-35).
        use_24h: The device's 24-hour setting.

    Returns:
        The line, e.g. "Updated 9 hours ago" or "Offline · schedule from Tue, May 12,
        10:42 AM" ("Offline · no schedule yet" without data); None when the data is
        fresh.
    """
    if status == "fresh":
        return None
    if status == "refreshing":
        return "Updating the schedule…"
    if status == "stale":
        if fetched_at is None:  # nothing loaded at all (rare, NEW-03)
            return "No schedule yet"
        return f"Updated {ago_label(fetched_at, now)}"
    if fetched_at is None:  # a failed refresh with nothing loaded: no "from" to give
        since = "no schedule yet"
    else:
        day = day_label(local_date(fetched_at, zone))
        since = f"schedule from {day}, {time_label(fetched_at, zone, use_24h=use_24h)}"
    if status == "offline":  # no answer: a better network may help
        return f"Offline · {since}"
    return f"Couldn't update · {since}"  # an answer we could not use


ICON_SIZE = 16
"""The strip's icon at 100 % text, in dp: the height of a ``BODY_SMALL`` line (12/16)."""

LINE_PAD = 8
"""Space above and below the strip's line, in dp, inside its run."""

REFRESH_INDENT = 16
"""Space before Refresh, in dp: on a run of its own, its label starts under the words."""

PROGRESS_HEIGHT = 2
"""The height of the strip's refresh bar, in dp (ux.md §3.9)."""

TICK_SECONDS = 60
"""How often a shown strip reads the clock again: its age, and fresh turning stale (D-40)."""


@ft.component
def StatusStrip(*, auto_refresh: bool = False) -> ft.Control:
    """Say when the schedule on screen is not fresh, and offer Refresh (D-32).

    Shown while a refresh the user asked for runs, when the data is stale, and after a
    failed refresh; hidden when fresh. A live region, so a screen reader announces each
    change. An automatic refresh is quiet (D-181): the line, its icon and the button
    stay as they were, and only the 2 dp bar runs, so the strip stays hidden over fresh
    data and the live region changes only when the outcome does.

    While it is mounted and the app is in the foreground, it ticks every
    ``TICK_SECONDS`` (``Services.run_every``): it re-renders when the minute has
    changed, so its age keeps up and it appears when the data turns stale, and with
    ``auto_refresh`` it starts a refresh whenever one is due (D-40). Leaving the
    screen stops the ticks, and so does the background.

    Args:
        auto_refresh: True on Now and Schedule, the screens that refresh the feed
            every 15 min while they show (``Conference.refresh_due()``, D-40).
    """
    page = ft.context.page
    svc = use_services()
    conference = use_conference()
    tokens = use_tokens()
    _, set_minute = ft.use_state(current_minute)
    info = svc.year.conference
    status = conference.status(info)
    use_24h = bool(page.media and page.media.always_use_24_hour_format)
    line = strip_line(
        status, conference.fetched_at, clock.now(), info.zone, use_24h=use_24h
    )

    @report_errors
    def tick() -> None:
        set_minute(current_minute())  # the same minute renders nothing new
        if auto_refresh:
            conference.start_refresh_if_due(svc.storage, svc.year, closed=svc.closed)

    @report_errors
    async def keep_up() -> None:
        await svc.run_every(TICK_SECONDS, tick)

    ft.use_effect(keep_up, [auto_refresh], cleanup=stop_ticks)

    @report_errors
    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    asked = status == "refreshing"  # the user's refresh; an automatic one is quiet
    icon = ft.Icon(
        STATUS_ICONS.get(status, ft.Icons.UPDATE),  # fresh: hidden, any icon
        size=ICON_SIZE,
        # Scaled as the text is, so at any text size it is as tall as the line it
        # sits beside, not a 16 dp speck at the top of a line three times its height.
        apply_text_scaling=True,
        color=ft.Colors.ON_SURFACE_VARIANT if asked else tokens.warning,
    )
    text = ft.Text(
        line or "",
        theme_style=ft.TextThemeStyle.BODY_SMALL,
        color=ft.Colors.ON_SURFACE,
        # Its own width up to what is left beside the icon: wide enough to wrap,
        # narrow enough to leave the button room on the same run when it fits.
        expand=True,
        expand_loose=True,
    )
    # Enabled during a quiet refresh: a tap joins it and makes it the user's (D-181).
    button = ft.TextButton("Refresh", on_click=refresh, disabled=asked)
    progress = ft.ProgressBar(
        bar_height=PROGRESS_HEIGHT,
        value=None,  # indeterminate
        visible=conference.refreshing,  # any refresh, the quiet ones too (D-181)
        # No label: the line says it, and the strip's node would say it twice.
    )
    # The bar's slot keeps its height when the bar hides, so the strip and the list
    # under it do not move by 2 dp when a refresh starts or ends.
    progress_slot = ft.Container(progress, height=PROGRESS_HEIGHT)
    # The icon tops its line and is one line tall, so when the line wraps (large text)
    # it stays beside the first line rather than the middle of the block.
    line_row = ft.Row(
        [icon, text],
        spacing=12,
        tight=True,  # the line's own width, so the wrap below can measure it
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
    # 8 dp above and below the line: centred against the 48 dp button they change
    # nothing, and when Refresh is on a run of its own they keep the line off the
    # strip's top edge.
    line_box = ft.Container(line_row, padding=ft.Padding.symmetric(vertical=LINE_PAD))
    # The icon's 16 dp and its 12 dp gap, less the button's own 12 dp inset: on a run
    # of its own, Refresh's label starts under the line's words at 100 % text, as
    # "Show all" does under the filter bar's (D-195).
    button_box = ft.Container(button, padding=ft.Padding.only(left=REFRESH_INDENT))
    # When the line fits beside the button, the two share a run, the line centred
    # against the 48 dp button and the button at the end. When it does not (large
    # text, or a long line such as "Couldn't update · …" at 100 %), the button moves
    # under the line, which keeps the whole width instead of wrapping word by word
    # beside it. The icon stays in the line's row rather than before the wrap (as the
    # filter bar has it), so it is level with the line on either layout.
    row = ft.Row(
        [line_box, button_box],
        wrap=True,
        spacing=0,  # the button's indent is the gap between them
        run_spacing=0,  # the button's 48 dp height already spaces it from the line
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    return ft.Semantics(
        identifier="app.status",
        container=True,
        live_region=True,
        visible=line is not None,
        content=ft.Container(
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            content=ft.Column(
                [
                    # 4 dp above and below: at 200 % text the line wraps, and it
                    # would touch the strip's edges; at 100 % the strip is 56 dp,
                    # an M3 one-line list item.
                    ft.Container(
                        row, padding=ft.Padding.only(left=16, top=4, right=8, bottom=4)
                    ),
                    progress_slot,
                ],
                spacing=0,
                # The full width for the wrap: a Wrap is only as wide as its runs,
                # and SPACE_BETWEEN needs the width to put Refresh at the end.
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        ),
    )


def current_minute() -> int:
    """Return the minute ``clock.now()`` is in, counted from the epoch: the tick's state."""
    return int(clock.now().timestamp()) // 60


def use_minute() -> int:
    """Re-render the calling component whenever the minute of ``clock.now()`` changes.

    A hook for the views that depend on the time, such as the Map's "Now:" lines: they
    recompute every 60 s while they are mounted and the app is in the foreground, on
    the strip's loop (``Services.run_every``, ``TICK_SECONDS``; D-40, D-175), and catch
    up at once on a resume. Leaving the screen stops the ticks. The Developer fake
    clock moves the minute too.

    Returns:
        The minute, counted from the epoch; read it to recompute only when it changes.
    """
    svc = use_services()
    minute, set_minute = ft.use_state(current_minute)

    @report_errors
    def tick() -> None:
        set_minute(current_minute())  # the same minute renders nothing new

    @report_errors
    async def keep_up() -> None:
        await svc.run_every(TICK_SECONDS, tick)

    ft.use_effect(keep_up, [], cleanup=stop_ticks)
    return minute


def stop_ticks() -> None:
    """The ticking effects' cleanup (the strip's, ``use_minute()``'s): nothing to undo.

    Flet cancels an effect's task on unmount only when the effect has a cleanup (F2),
    and that cancel is what stops the ticks. A cleanup returned by a sync setup would
    not do: the component's next render replaces it with ``use_effect``'s argument
    (F39), and the strip re-renders every minute.
    """
