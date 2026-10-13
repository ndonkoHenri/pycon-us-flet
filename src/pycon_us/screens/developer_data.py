"""The Developer screen's Data section: refresh, clear the cache, share the log, reset.

``DataActions`` is the section's rows (DEV-04, DEV-05, STORE-13; D-195): **Refresh now**,
a refresh the user asked for (D-181), with what the schedule on screen is; **Clear cached
feed**, after which the next start shows the bundled snapshot; **Share log**, the
packaged app's ``console.log`` on the share sheet (D-72); and **Reset app**, which deletes
what the app keeps and resets every store in memory, so the app is as after a fresh
install without a restart. The two that delete are confirmed first by an
``AlertDialog`` that lists what is lost (D-29); every outcome is said in place, under the
rows (#197). Apart from ``developer.py`` so that the screen stays under about 400 lines
(D-66), as the pickers are in ``developer_clock.py``, and the confirmations are
``developer_confirm.py``'s; ``padded()`` and ``outcome_line()``, which the screen draws
with too, are here.
"""

import logging
from datetime import datetime
from pathlib import Path

import flet as ft
from flet.utils import is_embedded

from pycon_us import clock
from pycon_us.core.timefmt import ago_label
from pycon_us.favorites import Favorites, use_favorites
from pycon_us.prefs import Prefs, use_prefs
from pycon_us.screens.developer_confirm import (
    Asking,
    confirmation,
    merged,
    none_open,
    snapshot_day,
)
from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors, show_details
from pycon_us.services.storage import SERVICE_ERRORS
from pycon_us.state import Conference, Problem, Source, use_conference
from pycon_us.theme import Tokens, use_tokens

logger = logging.getLogger(__name__)

type Outcome = tuple[str, bool]
"""What an action did, in words, and whether it went as asked: the line under the rows."""

NO_OUTCOME: Outcome = ("", True)
"""The outcome line's state before an action and after an edit: no words, hidden."""

SOURCES: dict[Source, str] = {
    "bundled": "Bundled with the app",
    "cache": "From the cache",
    "network": "From the feed",
}
"""Where the schedule on screen came from, as Refresh now's second line says it."""

CLEARED: Outcome = (
    (
        "Cached schedule deleted. The next start shows the bundled one, unless a "
        "refresh saves a new copy first."
    ),
    True,
)
NOT_CLEARED: Outcome = ("Couldn't delete the cached schedule.", False)
NO_LOG: Outcome = ("There's no log to share yet.", False)
LOG_NOT_FOUND: Outcome = ("Couldn't find the log.", False)
NOT_SHARED: Outcome = ("Couldn't open the share sheet.", False)
LOG_SHARED: Outcome = ("Log shared.", True)

RESET_INCOMPLETE = (
    "App reset, but some saved data couldn't be deleted: it returns when you reopen "
    "the app."
)
"""Reset app's SnackBar when a key or the cache could not be deleted (D-120)."""


@ft.component
def DataActions() -> ft.Control:
    """The Data section: four action rows, their confirmations and their outcome line.

    A component of its own: its confirmations and its outcome are its own state, and it
    re-renders with the stores it reads (the feed's status, the saved sessions' count).
    """
    page = ft.context.page
    svc = use_services()
    conference = use_conference()
    prefs = use_prefs()
    favorites = use_favorites()
    tokens = use_tokens()
    info = svc.year.conference
    asking, set_asking = ft.use_state(none_open)  # the open confirmation
    outcome, set_outcome = ft.use_state(NO_OUTCOME)
    sharing, set_sharing = ft.use_state(False)  # the share sheet is up

    @report_errors
    async def refresh_now() -> None:
        set_outcome(NO_OUTCOME)
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)
        set_outcome(refreshed(conference.problem))

    @report_errors
    def ask(kind: Asking) -> None:
        set_outcome(NO_OUTCOME)
        set_asking(kind)

    @report_errors
    def cancel() -> None:
        set_asking(None)

    @report_errors
    async def clear_cache() -> None:
        set_asking(None)
        deleted = await svc.storage.delete_feed("Clear cached feed (Developer)")
        set_outcome(CLEARED if deleted else NOT_CLEARED)

    @report_errors
    async def share_log() -> None:
        set_outcome(NO_OUTCOME)
        set_sharing(True)
        try:
            set_outcome(await share_console_log(svc, origin=centre(page)))
        finally:
            set_sharing(False)

    @report_errors
    async def reset() -> None:
        set_asking(None)
        complete = await reset_app(svc, conference, prefs, favorites)
        page.navigate("/")  # the index route: Now, and Welcome from P2 (DEV-05)
        page.show_dialog(
            ft.SnackBar(
                ft.Text("App reset" if complete else RESET_INCOMPLETE),
                behavior=ft.SnackBarBehavior.FLOATING,
            )
        )

    packaged = is_embedded()  # where the log is a file here, and Developer can lock
    ft.use_dialog(
        confirmation(
            asking,
            saved=len(favorites.ids),
            packaged=packaged,
            snapshot_day=snapshot_day(info),
            on_confirm=clear_cache if asking == "clear" else reset,
            on_cancel=cancel,
        )
    )
    refreshing = conference.status(info) == "refreshing"  # as every Refresh (D-181)
    has_cache = svc.storage.feed_path.exists()
    return ft.Column(
        [
            action_row(
                "developer.refresh_now",
                ft.Icons.REFRESH,
                "Refresh now",
                "Updating the schedule…"
                if refreshing
                else schedule_line(conference.source, conference.fetched_at),
                refresh_now,
                disabled=refreshing,
            ),
            action_row(
                "developer.clear_cache",
                ft.Icons.DELETE_OUTLINE,
                "Clear cached feed",
                "The next start shows the bundled schedule"
                if has_cache
                else "No cached schedule on this device",
                lambda: ask("clear"),
                disabled=not has_cache,
            ),
            action_row(
                "developer.share_log",
                ft.Icons.SHARE_OUTLINED,
                "Share log",
                "Sends console.log, for a bug report"
                if packaged
                else "Not a packaged build: the log is in the terminal that runs it",
                share_log,
                disabled=sharing or not packaged,
            ),
            action_row(
                "developer.reset_app",
                ft.Icons.RESTART_ALT,
                "Reset app",
                "Deletes your settings, saved sessions, the cached schedule and "
                "the Developer options",
                lambda: ask("reset"),
                color=ft.Colors.ERROR,
            ),
            ft.Semantics(
                identifier="developer.data_outcome",
                live_region=True,
                visible=bool(outcome[0]),
                content=outcome_line(*outcome, tokens=tokens),
            ),
        ],
        spacing=0,
    )


async def reset_app(
    svc: Services, conference: Conference, prefs: Prefs, favorites: Favorites
) -> bool:
    """Delete what the app keeps and reset every store, as after a fresh install.

    DEV-05, D-195. On the device: every ``pycon.`` preference (the settings, every
    year's favourites, the Developer options and their unlock) and the feed cache. In
    memory, without a restart: real time and no error details, as Developer's own Reset
    sets them before the stores change (D-187); the bundled snapshot, from the year's
    feed, with a running refresh cancelled; the settings, the saved sessions and the
    view memory at their defaults. Then a refresh starts, as at a start (D-181: quiet).

    Args:
        svc: The session's services.
        conference: The session's ``Conference`` store.
        prefs: The session's ``Prefs`` store.
        favorites: The session's ``Favorites`` store.

    Returns:
        Whether everything stored was deleted; when not (logged), the session is reset
        all the same, and what remains comes back at the next start (D-120).
    """
    # Before the stores change: the re-render that they cause reads real time.
    clock.start_fake_clock(None)
    show_details(False)
    cleared = await svc.storage.clear_prefs()
    deleted = await conference.reset(svc.storage, svc.year)
    prefs.reset()
    favorites.reset()
    svc.memory.reset()
    conference.start_refresh(svc.storage, svc.year, closed=svc.closed)
    complete = cleared and deleted
    logger.info("Reset app: %s", "done" if complete else "some data was not deleted")
    return complete


async def share_console_log(
    svc: Services, *, origin: ft.Offset | None = None
) -> Outcome:
    """Open the share sheet with the packaged app's ``console.log`` (D-72).

    The log holds no secrets or email addresses: the app never logs them, and the
    handler redacts any address a line quotes (D-196).

    Args:
        svc: The session's services: the storage paths and the share sheet.
        origin: Where the sheet points from on a tablet (D-62); a phone ignores it.

    Returns:
        What to say: that it was shared, that there is no log or that it failed;
        nothing (``NO_OUTCOME``) when the sheet was dismissed.
    """
    try:
        path = await svc.paths.get_console_log_filename()
    except SERVICE_ERRORS as error:
        logger.warning("Could not find the log: %s", type(error).__name__)
        return LOG_NOT_FOUND
    if not has_text(Path(path)):
        return NO_LOG
    try:
        result = await svc.share.share_files(
            [ft.ShareFile.from_path(path)],
            title="Share the app log",
            subject="App log",
            share_position_origin=origin,
        )
    except SERVICE_ERRORS as error:
        # The class only: an invoke error's text repeats the call's arguments (D-72).
        logger.warning("Could not share the log: %s", type(error).__name__)
        return NOT_SHARED
    return LOG_SHARED if result.status == ft.ShareResultStatus.SUCCESS else NO_OUTCOME


def has_text(path: Path) -> bool:
    """Return whether ``path`` is a file with something in it; unreadable counts as no."""
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def centre(page: ft.Page) -> ft.Offset | None:
    """Return the middle of the window, where the share sheet points from on a tablet."""
    if not page.width or not page.height:
        return None
    return ft.Offset(page.width / 2, page.height / 2)


def refreshed(problem: Problem | None) -> Outcome:
    """Return what Refresh now says once its refresh has ended (D-146).

    Args:
        problem: ``Conference.problem`` after it: None when it published the feed.
    """
    if problem is None:
        return ("Schedule updated from the feed.", True)
    if problem == "offline":
        return ("No answer from the feed: the app keeps the schedule it has.", False)
    return (
        "The feed's answer couldn't be used: the app keeps the schedule it has.",
        False,
    )


def schedule_line(
    source: Source, fetched_at: datetime | None, now: datetime | None = None
) -> str:
    """Return Refresh now's second line: where the schedule on screen came from, its age.

    Args:
        source: ``Conference.source``.
        fetched_at: ``Conference.fetched_at``; None before anything is published.
        now: The time to count the age to; ``clock.now()`` when None.
    """
    if source == "none" or fetched_at is None:
        return "No schedule yet"
    return f"{SOURCES[source]}, updated {ago_label(fetched_at, now or clock.now())}"


def action_row(
    identifier: str,
    icon: ft.IconData,
    title: str,
    subtitle: str,
    on_click: ft.ControlEventHandler[ft.ListTile],
    *,
    disabled: bool = False,
    color: ft.ColorValue | None = None,
) -> ft.Control:
    """Return one action: a two-line ``ListTile``, one node named by both lines.

    Its icons and title sit 14 dp from the top at every height, as a ``LinkTile`` with
    a subtitle does (D-188). A disabled row says so to screen readers.

    Args:
        identifier: For UI flows, e.g. ``developer.reset_app``.
        icon: The leading icon, outlined (D-27).
        title: What a tap does, a verb first.
        subtitle: What it touches, or why the row is disabled.
        on_click: The action.
        disabled: Whether the action is unavailable now.
        color: The icon's and the title's colour: ``ERROR`` for Reset app.
    """
    return merged(
        identifier,
        ft.ListTile(
            leading=ft.Icon(icon, color=None if disabled else color),
            title=ft.Text(title, color=None if disabled else color),
            subtitle=subtitle,
            on_click=on_click,
            disabled=disabled,
            title_alignment=ft.ListTileTitleAlignment.TOP,
            min_vertical_padding=14,
        ),
    )


def padded(control: ft.Control) -> ft.Container:
    """Return ``control`` with the list's 16 dp sides and 8 dp above and below (ux.md §3.6)."""
    return ft.Container(
        control, padding=ft.Padding.symmetric(horizontal=16, vertical=8)
    )


def outcome_line(text: str, ok: bool, *, tokens: Tokens) -> ft.Control:
    """Return the line under a group of buttons: an icon and what was done.

    Args:
        text: What was done, or why not, e.g. "Back to real time and the year's feed."
        ok: Whether it went as asked: a check in ``success``, else a warning in
            ``warning``; the words carry the meaning (ux.md §9).
        tokens: The scheme's tokens.
    """
    return padded(
        ft.Row(
            [
                # Decorative: the words carry the meaning (ux.md §9).
                ft.Icon(
                    ft.Icons.CHECK_CIRCLE_OUTLINE if ok else ft.Icons.WARNING_AMBER,
                    color=tokens.success if ok else tokens.warning,
                    size=20,
                ),
                ft.Text(
                    text,
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE,
                    expand=True,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    )
