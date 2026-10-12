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
    there.

    Args:
        memory: The process's ``ViewMemory``.
        scope: ``all``, ``sessions``, ``speakers`` or ``rooms``.
    """
    page = ft.context.page

    @report_errors
    def open_search() -> None:
        memory.search_base = page.route
        page.navigate(f"/search?scope={scope}")

    return ft.IconButton(ft.Icons.SEARCH, tooltip="Search", on_click=open_search)


def SectionHeader(text: str) -> ft.Control:
    """Return the heading of a group of rows: a day, a letter, a section (ux.md §3.9).

    Not sticky (U2). A header for screen readers, so they can jump group by group.

    Args:
        text: The heading, in sentence case.
    """
    return ft.Semantics(
        header=True,
        content=ft.Container(
            ft.Text(
                text, theme_style=ft.TextThemeStyle.TITLE_SMALL, color=ft.Colors.PRIMARY
            ),
            padding=ft.Padding.only(left=16, top=16, right=16, bottom=8),
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


TICK_SECONDS = 60
"""How often a shown strip reads the clock again: its age, and fresh turning stale (D-40)."""


@ft.component
def StatusStrip(*, auto_refresh: bool = False) -> ft.Control:
    """Say when the schedule on screen is not fresh, and offer Refresh (D-32).

    Shown while refreshing, when the data is stale, and after a failed refresh;
    hidden when fresh. A live region, so a screen reader announces each change.

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

    refreshing = status == "refreshing"
    icon = ft.Icon(
        STATUS_ICONS.get(status, ft.Icons.UPDATE),  # fresh: hidden, any icon
        size=16,
        color=ft.Colors.ON_SURFACE_VARIANT if refreshing else tokens.warning,
    )
    text = ft.Text(
        line or "",
        theme_style=ft.TextThemeStyle.BODY_SMALL,
        color=ft.Colors.ON_SURFACE,
        expand=True,
    )
    button = ft.TextButton("Refresh", on_click=refresh, disabled=refreshing)
    progress = ft.ProgressBar(
        bar_height=2,
        value=None,  # indeterminate
        visible=refreshing,
        # No label: the line says it, and the strip's node would say it twice.
    )
    row = ft.Row([icon, text, button], spacing=12)
    return ft.Semantics(
        identifier="app.status",
        container=True,
        live_region=True,
        visible=line is not None,
        content=ft.Container(
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            content=ft.Column(
                [
                    ft.Container(row, padding=ft.Padding.only(left=16, right=8)),
                    progress,
                ],
                spacing=0,
            ),
        ),
    )


def current_minute() -> int:
    """Return the minute ``clock.now()`` is in, counted from the epoch: the tick's state."""
    return int(clock.now().timestamp()) // 60


def stop_ticks() -> None:
    """The strip's effect cleanup: it has nothing of its own to undo.

    Flet cancels an effect's task on unmount only when the effect has a cleanup (F2),
    and that cancel is what stops the ticks. A cleanup returned by a sync setup would
    not do: the component's next render replaces it with ``use_effect``'s argument
    (F39), and the strip re-renders every minute.
    """
