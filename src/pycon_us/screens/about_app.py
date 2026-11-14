"""About this app (`/more/app`): what the app is, its data and its build (INFO-03).

The app's name and what it is, "Not an official PSF app." (D-36); **Conference data**:
the conference and where the schedule on screen came from, with its age (D-292); **This
build**: the version, with its build number in a packaged build (D-386), Python and
Flet (D-187); **Links**: Flet's website and, once the
repository is public, its source code (D-88, D-292); **Help us fix it**: Report a
problem, which shares the app's log and diagnostics, and once the repository is public
opens a new issue beside a Share log row (INFO-04, D-297). Seven taps on the version row
unlock the Developer screen in a packaged build, and a Developer options row appears
under the build's rows; it stays unlocked (D-187). **Licences** under them opens what
each build ships and under whose licence (D-296).
"""

import platform
from urllib.parse import urlsplit

import flet as ft
from flet.version import flet_version

from pycon_us import APP_NAME, SOURCE_URL
from pycon_us.dev_options import DEV_UNLOCKED
from pycon_us.prefs import use_prefs
from pycon_us.screens import licences
from pycon_us.services import use_services
from pycon_us.services.build import use_build
from pycon_us.services.errors import report_errors, show_details
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.actions import action_row
from pycon_us.ui.link_tile import LinkTile
from pycon_us.ui.page_title import PAGE_TITLE_AT_LARGE_TEXT
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.semantics import named
from pycon_us.ui.share import (
    new_issue_url,
    report_outcome,
    report_subtitle,
    use_problem_report,
)
from pycon_us.ui.status_strip import schedule_line, use_minute
from pycon_us.ui.widths import READING, sides, use_margin

UNLOCK_TAPS = 7
"""Taps on the version row that unlock Developer, as on Android's build number (D-73)."""

FLET_URL = "https://flet.dev"
"""Flet's website, which the Links section opens in the in-app browser (INFO-14)."""


@ft.component
def AboutApp() -> ft.View:
    """The About this app page: the app, its data, its build, its links; the unlock."""
    svc = use_services()
    margin = use_margin(READING)  # its width class (D-305)
    prefs = use_prefs()
    taps = ft.use_ref(0)  # a ref: counting re-renders nothing
    unsaved, set_unsaved = ft.use_state(False)
    build = use_build()  # "0.4.0 (812)" in a packaged build (D-386)

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
        header(info.name, large_text=prefs.time_above),
        ConferenceData(),
        SectionHeader("This build"),
        named(
            "about_app.version",
            ft.ListTile(title="Version", subtitle=build.label, on_click=count_tap),
        ),
        ft.ListTile(title="Python", subtitle=platform.python_version()),
        ft.ListTile(title="Flet", subtitle=flet_version),
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
    rows.append(HelpUsFixIt())
    return AppScaffold(
        title="About this app",
        source=__name__,
        body=ft.ListView(rows, expand=True, padding=sides(margin)),
    )


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


@ft.component
def HelpUsFixIt() -> ft.Control:
    """The Help us fix it section: a problem report with the log and diagnostics.

    A component of its own, as Developer's Data section is: whether the sheet is up and
    how the last share ended are its state, so a share re-renders these rows and not
    the page. The outcome is said in place, under the rows (D-29, D-210); a dismissed
    sheet says nothing (`use_problem_report()`).
    """
    report = use_problem_report()
    tokens = use_tokens()
    rows = help_rows(
        SOURCE_URL,
        packaged=report.packaged,
        sharing=report.sharing,
        on_share=report.share,
    )
    rows.append(
        report_outcome("about_app.report_outcome", report.outcome, tokens=tokens)
    )
    return ft.Column(rows, spacing=0)


def help_rows(
    source_url: str | None,
    *,
    packaged: bool,
    sharing: bool,
    on_share: ft.ControlEventHandler[ft.ListTile],
) -> list[ft.Control]:
    """Return Help us fix it's heading and rows, which switch on `SOURCE_URL` (D-297).

    While `SOURCE_URL` is None, one row, **Report a problem**, shares the log and
    the diagnostics: a Share log row would open the same sheet. Once it is set,
    Report a problem opens a new issue in the in-app browser (INFO-14) and **Share log**
    under it shares what to attach.

    Args:
        source_url: `SOURCE_URL`: None in a build that doesn't point at a public
            repository (D-88).
        packaged: A packaged build, whose share adds `console.log`; the row says
            beforehand whether it does.
        sharing: The share sheet is up: the share row is disabled until it closes.
        on_share: The share row's action.
    """
    rows: list[ft.Control] = [SectionHeader("Help us fix it")]
    if source_url is None:
        rows.append(
            action_row(
                "about_app.report_problem",
                ft.Icons.BUG_REPORT_OUTLINED,
                "Report a problem",
                report_subtitle(packaged),
                on_share,
                disabled=sharing,
            )
        )
        return rows
    issue_url = new_issue_url(source_url)
    rows.append(
        LinkTile(
            "Report a problem",
            issue_url,
            icon=ft.Icons.BUG_REPORT_OUTLINED,
            subtitle=shown_url(issue_url),
            identifier="about_app.report_problem",
        )
    )
    rows.append(
        action_row(
            "about_app.share_log",
            ft.Icons.SHARE_OUTLINED,
            "Share log",
            report_subtitle(packaged),
            on_share,
            disabled=sharing,
        )
    )
    return rows


def links(source_url: str | None) -> list[ft.Control]:
    """Return the Links section: Flet's website, then the source code once it is public.

    External rows by the link rule (INFO-14): each opens in the in-app browser and
    reads as a link, "Opens in browser" (D-182).

    Args:
        source_url: `SOURCE_URL`: None in a build that doesn't point at a public
            repository, which hides its row (D-88).
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
    """Return `url` as a row shows it, without scheme or final slash: "flet.dev"."""
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


def header(conference: str, *, large_text: bool = False) -> ft.Control:
    """Return the page's opening: the app's name, what it is, and that it is not the PSF's.

    Args:
        conference: The conference's name, from the year data (D-35).
        large_text: The text is large for the width (`Prefs.time_above`): the name
            steps down (D-328).
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
                        # "Companion" broke inside itself at iOS's largest text (#1095).
                        theme_style=PAGE_TITLE_AT_LARGE_TEXT
                        if large_text
                        else ft.TextThemeStyle.HEADLINE_SMALL,
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
