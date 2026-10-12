"""The chrome every screen shares: ``AppScaffold``, ``SectionHeader`` and ``StatusStrip``.

``AppScaffold`` builds each screen's View (architecture §5.5): a surface ``AppBar`` with
the screen's title, left-aligned and always visible (D-10, D-28), the Material back arrow
on pushed Views, the Back rules of the tab roots (D-17, D-142), and the body in a
``SafeArea`` (D-12, D-113). The status- and navigation-bar style comes from the theme
(``theme.overlay_style()``, D-151): Flet's ``AppBar`` applies it, so a screen never sets
one. The bottom bar (#75) joins on tab roots only (D-144), and the tablet rail with the
720/840 dp content widths in P2 (#30).

``StatusStrip`` says when the data is not fresh, with Refresh until pull-to-refresh
(U1) arrives (D-32, D-146); ``SectionHeader`` is the heading of a group of rows.
"""

import logging
from datetime import datetime, tzinfo

import flet as ft

from pycon_us import clock
from pycon_us.core.timefmt import ago_label, day_label, local_date, time_label
from pycon_us.locations import TAB_ROOTS, is_top_view, parent_of
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import THEME
from pycon_us.state import Status, ViewMemory, use_conference
from pycon_us.theme import use_tokens

logger = logging.getLogger(__name__)


def AppScaffold(
    *, title: str, body: ft.Control, actions: list[ft.Control] | None = None
) -> ft.View:
    """Return a screen's View: the app bar, the Back rules and the body (D-10, D-17).

    A plain builder that calls hooks, so a screen calls it exactly once per render, in
    every branch (hooks are unconditional, D-70). It records the top View's route for
    the start route (D-143), and places the body in ``Shown``, which logs D-112's
    content line (D-165).

    Args:
        title: The screen's name: the app bar's title and, for screen readers, the
            page's heading (Flutter marks an app bar title as a header).
        body: What the View shows under the app bar, usually an ``expand=True``
            ``ListView``; it is placed in a ``SafeArea``, clear of the notch, the
            home indicator and the navigation bar in either orientation.
        actions: The app bar's actions, e.g. ``search_button()``; each icon-only one
            has a tooltip, its accessible name (D-27).

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

    back_arrow = ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Back", on_click=go_back)
    return ft.View(
        route="/" if is_root else view_path,  # roots share a key: no transition (D-142)
        padding=0,
        appbar=ft.AppBar(
            title=ft.Text(title),
            center_title=False,  # as the theme says; iOS would centre it (D-10)
            # Flutter would imply the iOS chevron on iOS; the Material arrow instead.
            automatically_imply_leading=False,
            leading=None if is_root else back_arrow,
            actions=actions or [],
        ),
        # The NavigationBar goes here, on tab roots only (#75, D-144).
        can_pop=not back_to_now,
        on_confirm_pop=leave_for_now if back_to_now else None,
        controls=[ft.SafeArea(expand=True, content=Shown(body))],
    )


@ft.component
def Shown(body: ft.Control) -> ft.Control:
    """Return ``body`` unchanged, and log D-112's content line once per feed version.

    The line is ``Content shown: <source> feed, version <n>``, logged from the first
    screen that renders a version (``Services.shown_versions``, D-165), after a
    SharedPreferences round trip so the patch has reached Flutter. It is a component of
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
        # Flet cancels this setup only when it re-runs, for a newer version (no cleanup,
        # so an unmount leaves it running); that version is then what is shown.
        await svc.storage.get(THEME)
        logger.info("Content shown: %s feed, version %d", source, version)

    ft.use_effect(log_shown, [version])
    return body


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


@ft.component
def StatusStrip() -> ft.Control:
    """Say when the schedule on screen is not fresh, and offer Refresh (D-32).

    Shown while refreshing, when the data is stale, and after a failed refresh;
    hidden when fresh. A live region, so a screen reader announces each change. The
    age is written when the strip renders: #82 re-renders it every 60 s while it shows
    (D-40), and adds the refresh triggers.
    """
    page = ft.context.page
    svc = use_services()
    conference = use_conference()
    tokens = use_tokens()
    info = svc.year.conference
    status = conference.status(info)
    use_24h = bool(page.media and page.media.always_use_24_hour_format)
    line = strip_line(
        status, conference.fetched_at, clock.now(), info.zone, use_24h=use_24h
    )

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
