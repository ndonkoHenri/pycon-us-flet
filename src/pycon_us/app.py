"""The root component: services and stores, the boot gate, providers and the Router.

``App`` builds the session's ``Services`` and stores once, shows ``BootView`` until the
settings are read and the cached or bundled feed is published (the boot gate, SHELL-01),
then writes out one provider per store around the Router (D-69). ``bootstrap()`` is the
start sequence (DATA-35, architecture §4.3): nothing in it waits on the network.
"""

import asyncio
import logging

import flet as ft

from pycon_us import clock
from pycon_us.account import Account, AccountCtx
from pycon_us.change_log import ChangeLog, ChangeLogCtx
from pycon_us.favorites import Favorites, FavoritesCtx
from pycon_us.layout import LayoutCtx, follow_width, layout_for
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs, PrefsCtx, read_accessibility, use_prefs
from pycon_us.reminder_schedule import use_reminder_schedule, use_reminder_taps
from pycon_us.routes import ROUTES
from pycon_us.screens.changes_review import use_review_snack_bar
from pycon_us.services import Services, ServicesCtx
from pycon_us.services.errors import report_errors, show_details
from pycon_us.services.reminders import LAUNCH_WAIT
from pycon_us.state import Conference, ConferenceCtx
from pycon_us.theme import (
    BOOT_COLOR,
    THEME_MODES,
    TokensCtx,
    build_theme,
    build_tokens,
)
from pycon_us.ui.reminder_banner import use_reminder_banner
from pycon_us.ui.time_gutter import GutterProbe

logger = logging.getLogger(__name__)

RING_DELAY = 1.0
"""Seconds before the boot view shows a progress ring; most starts end sooner (ux.md §2.6)."""

NO_THEME_ANIMATION = ft.AnimationStyle(duration=0)
"""``page.theme_animation_style`` until the boot gate opens: every theme change before it
lands at once. Flutter crossfades theme changes over 200 ms, and a gate that opens sooner
showed the first screen mid-fade (iOS simulator, #72)."""


@ft.component
def App(memory: ViewMemory):
    """Build services and stores once, wait for the settings and the feed, then route.

    ``App`` subscribes to ``Prefs`` only (``use_state``), so it re-renders when a setting
    or a device fact changes, never on a feed refresh; and when the reminder Banner
    changes, at most once a minute while a saved session is about to start. It provides
    ``Layout`` without reading it: a rotation that crosses 600 dp re-renders the
    screens, not ``App``.

    Args:
        memory: The process's one ``ViewMemory`` (D-143).
    """
    page = ft.context.page
    # An explicit empty list: without one, use_memo recomputes on every render (D-69).
    account = ft.use_memo(Account, [])
    # The private-API client signs with the account's key and secret (#684).
    svc = ft.use_memo(lambda: Services.create(memory, account.credentials), [])
    favorites = ft.use_memo(Favorites, [])
    # A refresh hands each new feed to the log, whose snapshot diff reads the
    # favourites (D-255).
    change_log = ft.use_memo(lambda: ChangeLog(_favorites=favorites), [])
    conference = ft.use_memo(lambda: Conference(_change_log=change_log), [])
    # The window's class and room from its first width, so the first screen has the
    # right navigation and content width (D-277, D-305); follow_width() keeps it in step.
    layout = ft.use_memo(lambda: layout_for(page), [])
    prefs, _ = ft.use_state(Prefs)

    @report_errors
    async def start() -> None:
        await bootstrap(page, svc, conference, prefs, favorites, change_log, account)

    @report_errors
    def follow_theme() -> None:
        apply_theme(page, prefs)

    @report_errors
    def follow_window() -> None:
        follow_width(page, layout)

    ft.use_effect(start, [])
    ft.use_effect(follow_window, [])
    ft.use_effect(follow_theme, [prefs.theme, prefs.high_contrast_on])
    ready = prefs.loaded and prefs.time_measured
    # The app's one reminder Banner slot (D-60, architecture §14.2), before the gate.
    use_reminder_banner(svc, conference, favorites, prefs, ready=ready)
    # Each recorded batch's "Schedule updated · Review" (D-255, D-335), before the gate.
    use_review_snack_bar(svc, change_log, favorites, prefs)
    # E3's reminders, applied once the start has loaded, and at every change (D-389).
    use_reminder_schedule(svc, conference, favorites, change_log, prefs)
    # A reminder tap navigates once the gate is open; before, Start opens it (D-396).
    use_reminder_taps(svc, ready=ready)

    # The boot gate: no theme or filter flash, and no slot layout that changes
    # under the Schedule's first jump (D-216).
    if not ready:
        # Under Prefs' provider for GutterProbe, which measures while the app boots.
        return PrefsCtx(prefs, lambda: [BootView()])

    tokens = build_tokens(dark=prefs.dark, high_contrast=prefs.high_contrast_on)

    def router():
        return ft.Router(ROUTES, manage_views=True)  # ROUTES ends with its catch-all

    return ServicesCtx(
        svc,
        lambda: ConferenceCtx(
            conference,
            lambda: PrefsCtx(
                prefs,
                lambda: FavoritesCtx(
                    favorites,
                    lambda: AccountCtx(
                        account,
                        lambda: ChangeLogCtx(
                            change_log,
                            lambda: LayoutCtx(
                                layout, lambda: TokensCtx(tokens, router)
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


@ft.component
def BootView() -> ft.View:
    """The boot gate's view: the splash's purple, and a ring only after ``RING_DELAY``.

    It holds ``GutterProbe`` too, and the gate waits for its answer, so whether a
    slot's time goes above its rows is known before the first screen: a Schedule
    that opened with the gutter and switched a moment later lost its jump to the
    current slot, which ran against the first layout (D-216). Flutter reports the
    probe's size with its first frame (F51); should no answer come, the gate stops
    waiting with the ring, after ``RING_DELAY``, and the lists keep the gutter until
    the screens' own probes answer.
    """
    prefs = use_prefs()
    ring, set_ring = ft.use_state(False)

    @report_errors
    def stop_waiting() -> None:
        set_ring(True)
        prefs.time_measured = True

    @report_errors
    def show_ring_later():
        # A sync setup whose return value is its cleanup (F2): an unmount within the
        # delay cancels the timer.
        timer = asyncio.get_running_loop().call_later(RING_DELAY, stop_waiting)
        return timer.cancel

    ft.use_effect(show_ring_later, [])
    return ft.View(
        route="/",
        bgcolor=BOOT_COLOR,
        padding=0,
        vertical_alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=0,  # the probe is 0 dp high: the ring stays centred
        controls=[
            ft.ProgressRing(
                color=ft.Colors.WHITE, semantics_label="Loading", visible=ring
            ),
            GutterProbe(),
        ],
    )


async def bootstrap(
    page: ft.Page,
    svc: Services,
    conference: Conference,
    prefs: Prefs,
    favorites: Favorites,
    change_log: ChangeLog,
    account: Account,
) -> None:
    """Start in the order that avoids flashes and never waits on the network (DATA-35).

    0. ``page.on_close``, before anything is awaited (D-147).
    1. Settings, the OS's accessibility flags and brightness, then the theme they ask
       for, all while the boot view shows. ``main.prepare_first_page()`` has turned
       the theme animation off, so the theme lands at once. The Developer options
       take effect with the settings: the fake clock runs from its stored start, the
       feed URL serves the refreshes, and an unlock shows error details (D-187).
    2. The year's favourites (D-48), so no star fills in after the first screen, and
       the year's change log, before any refresh records in it (D-255). Then the
       mock account, from local reads only (STORE-03), whether or not a mock URL is
       set (D-398), and its role flags' refresh, in the background (D-54).
    3. The feed cache, else the bundled snapshot (D-38, D-145). Then E3's first
       answer, ``Scheduler.read_enabled()``, at most ``LAUNCH_WAIT``: E3 answers only
       once it has handed over the tap that launched the app (F246), so ``Start``
       opens that tap's session, with no flash of Now or Welcome first (D-396).
    4. ``prefs.loaded`` ends the start. The boot gate opens once ``BootView``'s probe
       has also measured the time's place (``prefs.time_measured``), or after
       ``RING_DELAY`` without an answer (D-216); the first screen shows that data.
       Theme changes crossfade again from here on, also under reduced motion: a
       crossfade changes colour, not position (D-173).
    5. A refresh in the background, not awaited (single flight, D-145).
    6. The page handlers, which only write stores (D-147); a resume runs
       ``on_resume()``.

    An unexpected error in steps 1-3 is logged and the gate opens anyway, with whatever
    loaded: a start never hangs on the boot view. A session replaced during steps 1-3
    (F26, F29) stops there: its stores belong to a destroyed session (F30).

    Args:
        page: The session's page.
        svc: The session's services.
        conference: The session's ``Conference`` store.
        prefs: The session's ``Prefs`` store.
        favorites: The session's ``Favorites`` store.
        change_log: The session's ``ChangeLog`` store.
        account: The session's ``Account`` store.
    """
    # First, so a session replaced while the start awaits gets `closed` too (D-147).
    page.on_close = svc.close
    try:
        await prefs.load(svc.storage)
        await start_developer_options(prefs, conference, svc)
        await read_accessibility(svc.semantics, prefs)
        prefs.os_dark = page.platform_brightness == ft.Brightness.DARK
        apply_theme(page, prefs)
        await favorites.load(svc.storage)
        await change_log.load(svc.storage, svc.year.conference.zone)
        await account.restore(svc.storage, svc.credentials)
        account.refresh_flags(svc.api, svc.storage, closed=svc.closed)  # not awaited
        await conference.load_local(svc.storage, svc.year)
        if svc.reminders is not None:
            await svc.reminders.read_enabled(LAUNCH_WAIT)
    except Exception:  # its own net, not report_errors: the gate opens anyway (D-161)
        if not svc.closed.is_set():  # a closed session's store write fails (F30)
            logger.exception("Start failed; opening the app with what has loaded")
    if svc.closed.is_set():
        logger.info("Session closed during the start; it stops here (D-147)")
        return
    prefs.loaded = True
    page.theme_animation_style = None  # crossfade, kept under reduced motion (D-173)
    conference.start_refresh(svc.storage, svc.year, closed=svc.closed)

    @report_errors
    def on_brightness(e: ft.Event[ft.Page]) -> None:
        # Not e.brightness: at the pin the event arrives as a plain ControlEvent whose
        # data is the name (flet_backend.dart sends a string), while the page field is
        # already updated (S4).
        prefs.os_dark = page.platform_brightness == ft.Brightness.DARK

    @report_errors
    async def on_lifecycle(e: ft.AppLifecycleStateChangeEvent) -> None:
        if e.state == ft.AppLifecycleState.INACTIVE:
            svc.presence.leave()  # another window in front, or on its way (D-372)
        elif e.state == ft.AppLifecycleState.PAUSE:
            svc.foreground.clear()  # the 60 s ticks wait for the resume (D-40)
        elif e.state == ft.AppLifecycleState.RESUME:
            await on_resume(svc, conference, prefs, account)

    page.on_platform_brightness_change = on_brightness
    page.on_app_lifecycle_state_change = on_lifecycle


async def start_developer_options(
    prefs: Prefs, conference: Conference, svc: Services
) -> None:
    """Put the stored Developer options into effect for this session (D-73, D-187).

    The fake clock runs from its stored start again, so each start of the app begins
    at the same simulated moment; the feed URL serves the refreshes; a mock API URL
    builds ``Services.api`` (D-51); and an unlock shows the exception text in
    ``report_errors``' message.

    Args:
        prefs: The loaded settings.
        conference: The session's ``Conference`` store.
        svc: The session's services: the feed cache's storage and the API client.
    """
    clock.start_fake_clock(prefs.fake_now)
    if prefs.fake_now is not None:
        logger.info("Fake clock on: it starts at %s", prefs.fake_now.isoformat())
    await conference.set_feed_url(prefs.feed_url, svc.storage)
    await svc.private_api.connect(prefs.mock_api_url, svc.year.conference.year)
    show_details(prefs.developer_unlocked)


async def on_resume(
    svc: Services, conference: Conference, prefs: Prefs, account: Account
) -> None:
    """Do what the app does each time it returns to the foreground: the one place for it.

    Each step is one consumer of the resume; a new one joins here.

    1. The 60 s ticks run again (``Services.run_every``), and catch up at once when
       one fell due in the background (D-40); ``Services.presence`` notes the
       return, so a button that opened another app's window gets the focus back
       (``ui.focus_back``, D-372).
    2. The feed refreshes when the last refresh began 15 min ago or more (D-40).
    3. E3's reminders are applied again, which brings back what the OS dropped
       meanwhile (D-222, D-389); without E3 there is nothing to apply. Asked before
       the await below, so a slow read never holds it back.
    4. The mock account's role flags are refreshed in the background, so a role
       given or taken away while the app was away shows, and a revoked key asks
       for a sign-in (D-54, D-57); signed out or with no mock URL, nothing is sent.
    5. The OS's accessibility flags are read again. The OS reports them as a snapshot,
       with no change event (F13, U17), so a setting changed while the app was away
       applies without a restart (D-23, D-34, D-173). On Android such a change can
       reach Flutter only after this read, and then applies at the next resume:
       accepted until U17 (D-183). Components follow ``Prefs`` by themselves.

    Args:
        svc: The session's services.
        conference: The session's ``Conference`` store.
        prefs: The session's ``Prefs`` store.
        account: The session's ``Account`` store.
    """
    svc.foreground.set()
    svc.presence.come_back()
    conference.start_refresh_if_due(svc.storage, svc.year, closed=svc.closed)
    if svc.reminders is not None:
        svc.reminders.request()
    account.refresh_flags(svc.api, svc.storage, closed=svc.closed)
    await read_accessibility(svc.semantics, prefs)


def apply_theme(page: ft.Page, prefs: Prefs) -> None:
    """Show the schemes and the theme mode the settings ask for (architecture §15).

    The page re-renders by itself in components mode; no ``page.update()`` (D-147).

    Args:
        page: The session's page.
        prefs: The settings: Appearance and High contrast.
    """
    page.theme = build_theme(dark=False, high_contrast=prefs.high_contrast_on)
    page.dark_theme = build_theme(dark=True, high_contrast=prefs.high_contrast_on)
    page.theme_mode = THEME_MODES[prefs.theme]
