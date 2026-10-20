"""About this app (``/more/app``): what the app is, its data and its build (INFO-03).

The app's name and what it is, "Not an official PSF app." (D-36); **Conference data**:
the conference and where the schedule on screen came from, with its age (D-292); **This
build**: the version, Python and Flet (D-187); **Links**: Flet's website and, once the
repository is public, its source code (D-88, D-292). Seven taps on the version row
unlock the Developer screen in a packaged build, and a Developer options row appears
under the build's rows; it stays unlocked (D-187). **Licences** under them opens what
each build ships and under whose licence (D-296). P2 adds Share log (#443).
"""

import platform
from urllib.parse import urlsplit

import flet as ft

from pycon_us import APP_NAME, FLET_VERSION, SOURCE_URL, __version__
from pycon_us.prefs import DEV_UNLOCKED, use_prefs
from pycon_us.screens import licences
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors, show_details
from pycon_us.state import use_conference
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.semantics import named
from pycon_us.ui.status_strip import schedule_line, use_minute

UNLOCK_TAPS = 7
"""Taps on the version row that unlock Developer, as on Android's build number (D-73)."""

FLET_URL = "https://flet.dev"
"""Flet's website, which the Links section opens in the in-app browser (INFO-14)."""


@ft.component
def AboutApp() -> ft.View:
    """The About this app page: the app, its data, its build, its links; the unlock."""
    svc = use_services()
    prefs = use_prefs()
    taps = ft.use_ref(0)  # a ref: counting re-renders nothing
    unsaved, set_unsaved = ft.use_state(False)

    @report_errors
    async def count_tap() -> None:
        taps.current = (taps.current or 0) + 1
        if taps.current < UNLOCK_TAPS or prefs.developer:
            return
        taps.current = 0
        show_details(True)
        saved = await prefs.save(svc.storage, dev={**prefs.dev, DEV_UNLOCKED: True})
        # Unlocked for this session either way; a failed save is lost on relaunch (D-120).
        set_unsaved(not saved)

    info = svc.year.conference
    rows: list[ft.Control] = [
        header(info.name),
        ConferenceData(),
        SectionHeader("This build"),
        named(
            "about_app.version",
            ft.ListTile(title="Version", subtitle=__version__, on_click=count_tap),
        ),
        ft.ListTile(title="Python", subtitle=platform.python_version()),
        ft.ListTile(title="Flet", subtitle=FLET_VERSION),
    ]
    if prefs.developer:
        rows.append(developer_row(unsaved))
    rows.append(
        LinkTile(
            licences.TITLE,
            licences.LOCATION,
            icon=ft.Icons.DESCRIPTION_OUTLINED,
            identifier="about_app.licences",
        )
    )
    rows.extend(links(SOURCE_URL))
    return AppScaffold(title="About this app", body=ft.ListView(rows, expand=True))


@ft.component
def ConferenceData() -> ft.Control:
    """The Conference data section: the conference, and the schedule's source and age.

    A component of its own, so that the store's changes and the minute's tick
    re-render these rows and not the page: a refresh that ends while the page is open
    says "From the feed, updated just now", and the age then counts up (D-292).
    """
    svc = use_services()
    conference = use_conference()
    use_minute()  # the age keeps up while the page is open, and moves with a fake clock
    line = schedule_line(conference.source, conference.fetched_at)
    return ft.Column(
        [
            SectionHeader("Conference data"),
            ft.ListTile(title="Conference", subtitle=svc.year.conference.name),
            named("about_app.schedule", ft.ListTile(title="Schedule", subtitle=line)),
        ],
        spacing=0,
    )


def links(source_url: str | None) -> list[ft.Control]:
    """Return the Links section: Flet's website, then the source code once it is public.

    External rows by the link rule (INFO-14): each opens in the in-app browser and
    reads as a link, "Opens in browser" (D-182).

    Args:
        source_url: ``SOURCE_URL``: None while the repository is private, which hides
            its row (D-88).
    """
    rows: list[ft.Control] = [
        SectionHeader("Links"),
        LinkTile(
            "Flet website",
            FLET_URL,
            icon=ft.Icons.LANGUAGE,
            subtitle=shown_url(FLET_URL),
            identifier="about_app.flet",
        ),
    ]
    if source_url is not None:
        rows.append(
            LinkTile(
                "Source code",
                source_url,
                icon=ft.Icons.CODE,
                subtitle=shown_url(source_url),
                identifier="about_app.source",
            )
        )
    return rows


def shown_url(url: str) -> str:
    """Return ``url`` as a row shows it, without scheme or final slash: "flet.dev"."""
    parts = urlsplit(url)
    return f"{parts.netloc}{parts.path}".rstrip("/")


def developer_row(unsaved: bool) -> ft.Control:
    """Return the row the unlock adds: the way to Developer, said where the taps were.

    In place, where the taps were, rather than in a SnackBar: the row is the result the
    taps wait for, and the way on (D-29, D-210). A live region, so a screen reader says
    it when the 7th tap adds it.

    Args:
        unsaved: The unlock could not be saved, so it ends with the app (D-120).
    """
    return ft.Semantics(
        live_region=True,
        content=LinkTile(
            "Developer options",
            "/more/developer",
            icon=ft.Icons.DEVELOPER_MODE_OUTLINED,
            subtitle="On until you close the app" if unsaved else "On",
            identifier="about_app.developer",
        ),
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
                # A level-2 heading under the bar's "About this app" (D-211), and the
                # lines under it, each a node of its own: without the containers the
                # lines merged into the heading, and with only the heading's, the
                # lines' node came first, read before the name (UiAutomation, #205).
                ft.Semantics(
                    header=True,
                    heading_level=2,
                    container=True,
                    content=ft.Text(
                        APP_NAME,
                        theme_style=ft.TextThemeStyle.HEADLINE_SMALL,
                        color=ft.Colors.ON_SURFACE,
                    ),
                ),
                ft.Semantics(
                    container=True,
                    content=ft.Column(
                        spacing=8,
                        controls=[
                            ft.Text(
                                f"A companion for {conference}, built with Python "
                                "and Flet.",
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
                ),
            ],
        ),
    )
