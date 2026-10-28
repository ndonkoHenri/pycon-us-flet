"""The Developer screen's Data section: refresh, clear the cache, share the log, reset.

``DataActions`` is the section's rows (DEV-04, DEV-05, STORE-13; D-198): **Refresh now**,
a refresh the user asked for (D-181), with what the schedule on screen is; **Clear cached
feed**, after which the next start shows the bundled snapshot; **Share log**, the
packaged app's ``console.log`` and the diagnostics on the share sheet (``ui/share.py``'s
``share_console_log()``, D-72, D-297); **Show welcome again**, which clears
``pycon.onboarded`` and opens Welcome, keeping everything else (SHELL-02, D-73); and
**Reset app**, which deletes
what the app keeps and resets every store in memory, so the app is as after a fresh
install without a restart. The two that delete are confirmed first by an
``AlertDialog`` that lists what is lost (D-29); every outcome is said in place, under the
rows (D-29, D-210). This module is what the actions do and say; how the screen draws
them is ``ui/actions.py``'s (the rows, the outcome line) and ``developer_ui.py``'s (the
confirmations). Apart from
``developer.py`` so that the screen stays under about 400 lines (D-66), as the pickers
are in ``developer_clock.py``.
"""

import logging

import flet as ft
from flet.utils import is_embedded

from pycon_us import clock
from pycon_us.favorites import Favorites, use_favorites
from pycon_us.locations import WELCOME, start_target
from pycon_us.prefs import Prefs, use_prefs
from pycon_us.screens.developer_ui import Asking, confirmation, none_open, snapshot_day
from pycon_us.services import Services, changes_file, use_services
from pycon_us.services.errors import report_errors, show_details
from pycon_us.state import Conference, use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.actions import NO_OUTCOME, Outcome, action_row, outcome_line, refreshed
from pycon_us.ui.share import report_subtitle, share_console_log
from pycon_us.ui.status_strip import schedule_line, use_minute

logger = logging.getLogger(__name__)

CLEARED: Outcome = (
    (
        "Cached schedule deleted. The next start shows the bundled one, unless a "
        "refresh saves a new copy first."
    ),
    True,
)
NOT_CLEARED: Outcome = ("Couldn't delete the cached schedule.", False)

WELCOME_NOT_SAVED: Outcome = (
    "Couldn't save the change, so Welcome didn't open. Try again.",
    False,
)
"""Show welcome again's line when ``pycon.onboarded`` could not be cleared (D-120)."""

RESET_INCOMPLETE = (
    "App reset, but some saved data couldn't be deleted: it returns when you reopen "
    "the app."
)
"""Reset app's SnackBar when a key or the cache could not be deleted (D-120)."""


@ft.component
def DataActions() -> ft.Control:
    """The Data section: five action rows, their confirmations and their outcome line.

    A component of its own: its confirmations and its outcome are its own state, and it
    re-renders with the stores it reads (the feed's status, the saved sessions' count)
    and each minute, so the schedule's age stays current while the screen is open.
    """
    page = ft.context.page
    svc = use_services()
    conference = use_conference()
    prefs = use_prefs()
    favorites = use_favorites()
    tokens = use_tokens()
    use_minute()  # Refresh now's second line says the schedule's age
    info = svc.year.conference
    asking, set_asking = ft.use_state(none_open)  # the open confirmation
    outcome, set_outcome = ft.use_state(NO_OUTCOME)
    sharing, set_sharing = ft.use_state(False)  # the share sheet is up
    packaged = is_embedded()  # where the log is a file here, and Developer can lock

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
            set_outcome(
                await share_console_log(
                    svc,
                    packaged=packaged,
                    conference=conference,
                    prefs=prefs,
                    favorites=favorites,
                )
            )
        finally:
            set_sharing(False)

    @report_errors
    async def show_welcome() -> None:
        set_outcome(NO_OUTCOME)
        # Saved first, so Welcome shows again at the next start until its Get started.
        if not await prefs.save(svc.storage, onboarded=False):
            set_outcome(WELCOME_NOT_SAVED)  # Storage has logged the key (D-120)
            return
        page.navigate(WELCOME)  # a root replaces the stack; Get started goes to Now

    @report_errors
    async def reset() -> None:
        set_asking(None)
        complete = await reset_app(svc, conference, prefs, favorites)
        # Where a fresh start goes (D-143): Welcome, since the reset cleared
        # onboarded (DEV-05, D-287). Not "/" itself: on the iOS simulator that left
        # the app on this View, locked.
        memory = svc.memory
        page.navigate(
            start_target(
                memory.last_location, memory.search_base, onboarded=prefs.onboarded
            )
        )
        page.show_dialog(
            ft.SnackBar(
                ft.Text("App reset" if complete else RESET_INCOMPLETE),
                behavior=ft.SnackBarBehavior.FLOATING,
            )
        )

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
                # Something moves while it runs (ux.md §4), the words say what.
                trailing=ft.ProgressRing(width=20, height=20, stroke_width=2)
                if refreshing
                else None,
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
                report_subtitle(packaged),
                share_log,
                disabled=sharing,
            ),
            action_row(
                "developer.show_welcome",
                ft.Icons.WAVING_HAND_OUTLINED,
                "Show welcome again",
                "Opens Welcome; your settings and saved sessions stay",
                show_welcome,
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

    DEV-05, D-198. On the device: every ``pycon.`` preference (the settings, every
    year's favourites, the Developer options and their unlock), the feed cache and the
    change log (D-255). In memory, without a restart: real time and no error details,
    as Developer's own Reset sets them before the stores change (D-187), and no
    private-API client (D-51); the bundled
    snapshot, from the year's feed, with a running refresh cancelled and an empty change
    log (``Conference.reset()``, D-301); the settings, the saved sessions and the view
    memory at their defaults. Then a refresh starts, as at a start (D-181: quiet).

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
    # Off before the stores change too: no re-render shows a private-API feature (D-51).
    await svc.private_api.connect(None, svc.year.conference.year)
    cleared = await svc.storage.clear_prefs()
    deleted = await conference.reset(svc.storage, svc.year)
    # After the reset, which cancels a refresh: the deletion waits for its writes (D-255).
    # Its own deletion: the reset deletes the log only when a feed URL was set
    # (set_feed_url returns early otherwise), and this result goes into `complete`.
    log_deleted = await changes_file.delete_batches(svc.storage, "Reset app")
    prefs.reset()
    favorites.reset()
    svc.memory.reset()
    conference.start_refresh(svc.storage, svc.year, closed=svc.closed)
    complete = cleared and deleted and log_deleted
    logger.info("Reset app: %s", "done" if complete else "some data was not deleted")
    return complete
