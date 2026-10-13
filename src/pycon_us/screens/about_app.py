"""About this app (``/more/app``): what the app is and which build this is (INFO-03).

The minimal P1 page (D-73): the app's name and what it is, "Not an official PSF app."
(D-36), then the build's version, Python and Flet. Seven taps on the version row unlock
the Developer screen in a packaged build; it stays unlocked (D-184). P2 completes the
page (#30): the feed's age, links, licences and "Share log".
"""

import platform

import flet as ft

from pycon_us import APP_NAME, __version__
from pycon_us.prefs import DEV_UNLOCKED, use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors, show_details
from pycon_us.ui.scaffold import AppScaffold, SectionHeader

UNLOCK_TAPS = 7
"""Taps on the version row that unlock Developer, as on Android's build number (D-73)."""

FLET_VERSION = "source build"
"""What the Flet row says while the app builds from the pinned source checkout (D-81): a
packaged app reports ``0.1.0`` then, the host the nearest tag (development.md §2.2). The
PR that pins ``flet==1.1.0`` shows ``flet.version.flet_version`` instead."""

DEVELOPER_LOCATION = "/more/developer"


@ft.component
def AboutApp() -> ft.View:
    """The About this app page: the app, its build, and the Developer unlock."""
    page = ft.context.page
    svc = use_services()
    prefs = use_prefs()
    taps = ft.use_ref(0)  # a ref: counting re-renders nothing

    @report_errors
    def open_developer() -> None:
        page.navigate(DEVELOPER_LOCATION)

    @report_errors
    async def count_tap() -> None:
        taps.current = (taps.current or 0) + 1
        if taps.current < UNLOCK_TAPS:
            return
        taps.current = 0
        if prefs.developer:
            page.show_dialog(snack("Developer options are already on", open_developer))
            return
        show_details(True)
        saved = await prefs.save(svc.storage, dev={**prefs.dev, DEV_UNLOCKED: True})
        # Unlocked for this session either way; a failed save is lost on relaunch (D-120).
        text = (
            "Developer options unlocked"
            if saved
            else "Developer options unlocked until you close the app"
        )
        page.show_dialog(snack(text, open_developer))

    info = svc.year.conference
    return AppScaffold(
        title="About this app",
        body=ft.ListView(
            [
                header(info.name),
                SectionHeader("This build"),
                ft.MergeSemantics(
                    content=ft.Semantics(
                        identifier="about_app.version",
                        content=ft.ListTile(
                            title="Version", subtitle=__version__, on_click=count_tap
                        ),
                    )
                ),
                ft.ListTile(title="Python", subtitle=platform.python_version()),
                ft.ListTile(title="Flet", subtitle=FLET_VERSION),
            ],
            expand=True,
        ),
    )


def snack(text: str, on_open: ft.ControlEventHandler[ft.SnackBar]) -> ft.SnackBar:
    """Return the unlock's SnackBar: what happened, and Open, which shows Developer.

    Args:
        text: What happened, e.g. "Developer options unlocked".
        on_open: Opens the Developer screen.
    """
    return ft.SnackBar(
        ft.Text(text),
        action="Open",
        on_action=on_open,
        persist=False,  # with an action, Flet would keep it on screen until tapped
        behavior=ft.SnackBarBehavior.FLOATING,
    )


def header(conference: str) -> ft.Control:
    """Return the page's opening: the app's name, what it is, and that it is not the PSF's.

    Args:
        conference: The conference's name, from the year data (D-35).
    """
    return ft.Container(
        padding=ft.Padding.only(left=16, top=24, right=16, bottom=8),
        content=ft.Column(
            spacing=8,
            controls=[
                ft.Semantics(
                    header=True,
                    content=ft.Text(
                        APP_NAME,
                        theme_style=ft.TextThemeStyle.HEADLINE_SMALL,
                        color=ft.Colors.ON_SURFACE,
                    ),
                ),
                ft.Text(
                    f"A companion for {conference}, built with Python and Flet.",
                    theme_style=ft.TextThemeStyle.BODY_LARGE,
                    color=ft.Colors.ON_SURFACE,
                ),
                ft.Text(
                    "Not an official PSF app.",
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
        ),
    )
