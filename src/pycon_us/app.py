"""The root component: services and stores, the boot gate, providers and the Router.

``App`` builds the session's ``Services`` and stores once, shows ``BootView`` until the
settings are read and the cached or bundled feed is published (the boot gate, SHELL-01),
then writes out one provider per store around the Router (D-69). ``bootstrap()`` is the
start sequence (DATA-35, architecture §4.3): nothing in it waits on the network.
"""

import asyncio
import logging

import flet as ft

from pycon_us.prefs import Prefs, PrefsCtx
from pycon_us.screens.stub import Stub
from pycon_us.services import Services, ServicesCtx
from pycon_us.state import Conference, ConferenceCtx, ViewMemory
from pycon_us.theme import THEME_MODES, TokensCtx, build_theme, build_tokens

logger = logging.getLogger(__name__)

BOOT_COLOR = "#680579"
"""The splash's purple (``[tool.flet.splash]``, ux.md §2.6), so the launch never flashes."""

RING_DELAY = 1.0
"""Seconds before the boot view shows a progress ring; most starts end sooner (ux.md §2.6)."""

SERVICE_ERRORS = (TimeoutError, RuntimeError)
"""What a Flet service call raises when the Flutter side times out or fails."""

NO_THEME_ANIMATION = ft.AnimationStyle(duration=0)
"""``page.theme_animation_style`` while the boot view shows: the stored theme at once."""

ROUTES = [ft.Route(index=True, component=Stub)]
"""One stub screen until the route table lands (#74)."""


@ft.component
def App(memory: ViewMemory):
    """Build services and stores once, wait for the settings and the feed, then route.

    ``App`` subscribes to ``Prefs`` only (``use_state``), so it re-renders when a setting
    or a device fact changes, never on a feed refresh.

    Args:
        memory: The process's one ``ViewMemory`` (D-143).
    """
    page = ft.context.page
    # An explicit empty list: without one, use_memo recomputes on every render (D-69).
    svc = ft.use_memo(lambda: Services.create(memory), [])
    conference = ft.use_memo(Conference, [])
    prefs, _ = ft.use_state(Prefs)

    async def start() -> None:
        await bootstrap(page, svc, conference, prefs)

    def follow_theme() -> None:
        apply_theme(page, prefs)

    ft.use_effect(start, [])
    ft.use_effect(follow_theme, [prefs.theme, prefs.high_contrast_on])

    if not prefs.loaded:  # the boot gate: no theme or filter flash
        return [BootView()]

    tokens = build_tokens(dark=prefs.dark, high_contrast=prefs.high_contrast_on)

    def router():
        return ft.Router(ROUTES, manage_views=True)

    return ServicesCtx(
        svc,
        lambda: ConferenceCtx(
            conference,
            lambda: PrefsCtx(prefs, lambda: TokensCtx(tokens, router)),
        ),
    )


@ft.component
def BootView() -> ft.View:
    """The boot gate's view: the splash's purple, and a ring only after ``RING_DELAY``."""
    ring, set_ring = ft.use_state(False)

    def show_ring_later():
        # A sync setup whose return value is its cleanup (F2): an unmount within the
        # delay cancels the timer.
        timer = asyncio.get_running_loop().call_later(RING_DELAY, set_ring, True)
        return timer.cancel

    ft.use_effect(show_ring_later, [])
    return ft.View(
        route="/",
        bgcolor=BOOT_COLOR,
        padding=0,
        vertical_alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.ProgressRing(
                color=ft.Colors.WHITE, semantics_label="Loading", visible=ring
            )
        ],
    )


async def bootstrap(
    page: ft.Page, svc: Services, conference: Conference, prefs: Prefs
) -> None:
    """Start in the order that avoids flashes and never waits on the network (DATA-35).

    1. Settings, the OS's accessibility flags and brightness, then the theme they ask
       for, all while the boot view shows, with no theme animation.
    2. The feed cache, else the bundled snapshot (D-38, D-145).
    3. ``prefs.loaded`` opens the boot gate: the first screen shows that data.
    4. A refresh in the background, not awaited (single flight, D-145).
    5. The page handlers, which only write stores (D-147), and ``page.on_close``.

    An unexpected error in steps 1-2 is logged and the gate opens anyway, with whatever
    loaded: a start never hangs on the boot view.

    Args:
        page: The session's page.
        svc: The session's services.
        conference: The session's ``Conference`` store.
        prefs: The session's ``Prefs`` store.
    """
    # Flutter crossfades theme changes over 200 ms; the stored theme must land at once,
    # or a gate that opens sooner shows the first screen mid-fade (iOS simulator, #72).
    page.theme_animation_style = NO_THEME_ANIMATION
    try:
        await prefs.load(svc.storage)
        await read_accessibility(svc.semantics, prefs)
        prefs.os_dark = page.platform_brightness == ft.Brightness.DARK
        apply_theme(page, prefs)
        await conference.load_local(svc.storage, svc.year)
    except Exception:  # #73's report_errors takes over reporting
        logger.exception("Start failed; opening the app with what has loaded")
    prefs.loaded = True
    page.theme_animation_style = None  # later changes crossfade, as Flutter's default
    conference.start_refresh(svc.storage, svc.year, closed=svc.closed)

    def on_brightness(e: ft.Event[ft.Page]) -> None:
        # Not e.brightness: at the pin the event arrives as a plain ControlEvent whose
        # data is the name (flet_backend.dart sends a string), while the page field is
        # already updated (S4).
        prefs.os_dark = page.platform_brightness == ft.Brightness.DARK

    async def on_lifecycle(e: ft.AppLifecycleStateChangeEvent) -> None:
        if e.state == ft.AppLifecycleState.RESUME:
            await read_accessibility(svc.semantics, prefs)  # a snapshot (F13, U17)

    page.on_platform_brightness_change = on_brightness
    page.on_app_lifecycle_state_change = on_lifecycle
    page.on_close = svc.close  # a new session replaced this one (D-147)


async def read_accessibility(semantics: ft.SemanticsService, prefs: Prefs) -> None:
    """Copy the OS's high-contrast and reduced-motion flags into ``prefs`` (D-23, D-34).

    The platform reports a snapshot with no change event (F13), so this runs at start
    and on resume. A failed read is logged and keeps the previous values.

    Args:
        semantics: The session's ``SemanticsService``.
        prefs: The store to update.
    """
    try:
        features = await semantics.get_accessibility_features()
    except SERVICE_ERRORS:
        logger.warning("Could not read the accessibility features", exc_info=True)
        return
    prefs.os_high_contrast = features.high_contrast
    prefs.reduce_motion = features.reduce_motion or features.disable_animations


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
