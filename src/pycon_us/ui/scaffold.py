"""The chrome every screen shares: ``AppScaffold``, ``SectionHeader`` and ``StatusStrip``.

``AppScaffold`` builds each screen's View (architecture §5.5): a surface ``AppBar`` with
the screen's title, left-aligned and always visible (D-10, D-28), the Material back arrow
on pushed Views, the bottom bar (``ui.navigation``) and the Back rules on tab roots
(D-13, D-17, D-142, D-144), and the body in a ``SafeArea`` (D-12, D-113). The status- and
navigation-bar style comes from the theme (``theme.overlay_style()``, D-151): Flet's
``AppBar`` applies it, so a screen never sets one. The tablet rail with the 720/840 dp
content widths joins in P2 (#30).

``StatusStrip`` says when the data is not fresh, with Refresh until pull-to-refresh
(U1) arrives (D-32, D-146); ``SectionHeader`` is the heading of a group of rows.
``use_minute()`` is the strip's minute tick as a hook, for any other view that depends
on ``clock.now()``, such as the Map's "Now:" lines (D-188).
"""

import asyncio
import logging
from datetime import datetime, tzinfo

import flet as ft

from pycon_us import clock
from pycon_us.core.timefmt import ago_label, day_label, local_date, time_label
from pycon_us.locations import TAB_ROOTS, is_top_view, parent_of
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import THEME, Storage
from pycon_us.state import Source, Status, ViewMemory, use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.navigation import TABS, Retap, navigation_bar

logger = logging.getLogger(__name__)


def AppScaffold(
    *,
    title: str,
    body: ft.Control,
    actions: list[ft.Control] | None = None,
    on_retap: Retap | None = None,
    fab: ft.FloatingActionButton | None = None,
) -> ft.View:
    """Return a screen's View: the app bar, the bottom bar, the Back rules and the body.

    A plain builder that calls hooks, so a screen calls it exactly once per render, in
    every branch (hooks are unconditional, D-70). It records the top View's route for
    the start route (D-143), and places the body in ``Shown``, which logs D-112's
    content line (D-165).

    On a tab root the View gets the bottom bar (D-144); pushed Views get the back arrow
    instead (D-10). Back on a root other than Now goes to Now, and Back on Now is left
    to the system, which leaves the app (D-17, D-142).

    Args:
        title: The screen's name: the app bar's title and, for screen readers, the
            page's heading (Flutter marks an app bar title as a header). On a tab
            root it carries the identifier ``<tab>.title`` for UI flows (D-170).
        body: What the View shows under the app bar, usually an ``expand=True``
            ``ListView``; it is placed in a ``SafeArea``, clear of the notch, the
            home indicator and the navigation bar in either orientation.
        actions: The app bar's actions, e.g. ``search_button()``; each icon-only one
            has a tooltip, its accessible name (D-27).
        on_retap: A tab root's action when its active tab is tapped again, usually
            the one ``ui.navigation.use_scroll_to_top()`` returns; ignored on pushed
            Views, which have no bar.
        fab: The screen's floating action button, if any: the Schedule's "Now"
            (ux.md §5.2). The body leaves room for it at its end.

    Returns:
        The View for this route level.
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    is_root = view_path in TAB_ROOTS
    back_to_now = is_root and view_path != "/now"
    if is_top_view(page.route, view_path):  # where a new session returns (D-143)
        svc.memory.last_location = page.route

    @report_errors
    def go_back() -> None:
        # /search returns to its opener, any other View one level up (D-19).
        page.navigate(parent_of(view_path, svc.memory.search_base))

    @report_errors
    async def leave_for_now(e: ft.Event[ft.View]) -> None:
        page.navigate("/now")
        await e.control.confirm_pop(False)  # this View stays; Now replaces the root

    @report_errors
    async def switch_tab(e: ft.Event[ft.NavigationBar]) -> None:
        # Flutter reports the active destination too, so a re-tap lands here (S4).
        root = TAB_ROOTS[e.control.selected_index]
        if root != view_path:
            page.navigate(root)  # roots share one View key: a swap, not a push (D-142)
        elif on_retap is not None:
            await on_retap()

    back_arrow = ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Back", on_click=go_back)
    title_control: ft.Control = ft.Text(title)
    if is_root:
        # The identifier tells UI flows which root shows (D-170). An unlabelled
        # Semantics merges it into the title's own node, as the bar's do (D-166).
        tab = TABS[TAB_ROOTS.index(view_path)]
        title_control = ft.Semantics(
            identifier=tab.title_identifier, content=title_control
        )
    return ft.View(
        route="/" if is_root else view_path,  # roots share a key: no transition (D-142)
        padding=0,
        appbar=ft.AppBar(
            title=title_control,
            center_title=False,  # as the theme says; iOS would centre it (D-10)
            # Flutter would imply the iOS chevron on iOS; the Material arrow instead.
            automatically_imply_leading=False,
            leading=None if is_root else back_arrow,
            actions=actions or [],
        ),
        # On roots only: on pushed Views the bar moved with the page (D-144).
        navigation_bar=navigation_bar(view_path, switch_tab) if is_root else None,
        floating_action_button=fab,
        can_pop=not back_to_now,
        on_confirm_pop=leave_for_now if back_to_now else None,
        controls=[ft.SafeArea(expand=True, content=Shown(body))],
    )


@ft.component
def Shown(body: ft.Control) -> ft.Control:
    """Return ``body`` unchanged, and log D-112's content line once per feed version.

    The line is ``Content shown: <source> feed, version <n>``, logged from the first
    screen that renders a version (``Services.shown_versions``, D-165), through
    ``log_when_shown()``. It is a component of
    its own so that only it reads ``Conference``: a refresh re-renders this leaf, which
    hands back the same ``body``, and not the screen around it.

    Args:
        body: The screen's body.
    """
    svc = use_services()
    conference = use_conference()
    version, source = conference.version, conference.source  # what this render shows

    @report_errors
    async def log_shown() -> None:
        if version in svc.shown_versions:  # another screen showed it first
            return
        svc.shown_versions.add(version)
        # A newer version re-runs this effect, and Flet cancels the run in progress (an
        # unmount does not: no cleanup). This version was rendered all the same, and the
        # first line marks the cold start, so the shield lets the line finish.
        await asyncio.shield(log_when_shown(svc.storage, source, version))

    ft.use_effect(log_shown, [version])
    return body


@report_errors
async def log_when_shown(storage: Storage, source: Source, version: int) -> None:
    """Log D-112's content line once a SharedPreferences round trip has returned.

    The round trip goes after the render's patch, so Flutter has the content when the
    line is logged (a proxy: S1 saw it 0.2-0.3 s after the pixels).

    Args:
        storage: The session's ``Storage``.
        source: Where the shown feed came from.
        version: The shown feed version.
    """
    await storage.get(THEME)
    logger.info("Content shown: %s feed, version %d", source, version)


def search_button(memory: ViewMemory, scope: str) -> ft.IconButton:
    """Return the app bar action that opens the global search with a preset scope (D-19).

    It records the opener's location, query included, so Back from search returns
    there, and clears the last query, so each search starts empty (D-193).

    Args:
        memory: The process's ``ViewMemory``.
        scope: ``all``, ``sessions``, ``speakers`` or ``rooms``.
    """
    page = ft.context.page

    @report_errors
    def open_search() -> None:
        memory.search_base = page.route
        memory.search_query = ""  # a new search; Back to its results keeps the old one
        page.navigate(f"/search?scope={scope}")

    return ft.IconButton(ft.Icons.SEARCH, tooltip="Search", on_click=open_search)


def SectionHeader(
    text: str,
    *,
    level: int | None = None,
    top: int = 16,
    theme_style: ft.TextThemeStyle = ft.TextThemeStyle.TITLE_SMALL,
    color: ft.ColorValue = ft.Colors.PRIMARY,
    leading: ft.Control | None = None,
    spoken: str | None = None,
) -> ft.Control:
    """Return the heading of a group of rows: a day, a letter, a section (ux.md §3.9).

    Not sticky (U2). A header for screen readers, so they can jump group by group.

    Args:
        text: The heading, in sentence case.
        level: Its heading level, on a page that declares an outline: 2 under a
            detail page's level-1 title (ux.md §5.5).
        top: The space above it: 16 dp where it opens a group in a list; 0 on a
            detail page, whose list already puts 24 dp between sections.
        theme_style: Its type: ``TITLE_SMALL``, or ``TITLE_MEDIUM`` for a heading that
            holds headings of its own (search's "Sessions" over its days, D-193).
        color: Its colour role: ``primary``, or ``on_surface`` with ``TITLE_MEDIUM``.
        leading: A decorative mark before the text, such as Now's live dot: a
            control without a label (a shape, an unlabelled icon), so the heading
            still reads as ``text``.
        spoken: What a screen reader says instead of ``text``, when it differs:
            "Up next, 11:30 AM" for "Up next · 11:30 AM".
    """
    label: ft.Control = ft.Text(
        text,
        theme_style=theme_style,
        color=color,
        semantics_label=spoken,
        # Beside a mark, the row's room: in a row a text gets unbounded width and
        # would overflow instead of wrapping at large text.
        expand=leading is not None,
    )
    if leading is not None:
        label = ft.Row(
            [leading, label],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    return ft.Semantics(
        header=True,
        heading_level=level,
        content=ft.Container(
            label,
            padding=ft.Padding.only(left=16, top=top, right=16, bottom=8),
        ),
    )


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
        size=16,
        color=ft.Colors.ON_SURFACE_VARIANT if asked else tokens.warning,
    )
    text = ft.Text(
        line or "",
        theme_style=ft.TextThemeStyle.BODY_SMALL,
        color=ft.Colors.ON_SURFACE,
        expand=True,
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
    # The icon tops its line, so when the line wraps (large text) the icon stays beside
    # the first line rather than the middle of the block; the pair stays centred
    # against the 48 dp button, so a single line still sits mid-strip.
    line_row = ft.Row(
        [icon, text],
        spacing=12,
        vertical_alignment=ft.CrossAxisAlignment.START,
        expand=True,
    )
    row = ft.Row([line_row, button], spacing=12)
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
