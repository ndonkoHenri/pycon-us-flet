"""The one screen behind the boot gate until the route table lands (#74).

It shows what the start sequence published: where the feed came from, when, the data
status and the first day's session count, so "bundled first, a refresh replaces it" is
visible on a phone. Its Appearance buttons exercise ``Prefs.save()`` and the theme until
Settings exists (P2). #74 replaces it with the tab roots.
"""

import logging
from datetime import tzinfo
from typing import cast

import flet as ft

from pycon_us import APP_NAME
from pycon_us.core.timefmt import day_label, local_date, time_label
from pycon_us.prefs import Appearance, use_prefs
from pycon_us.services import use_services
from pycon_us.services.storage import THEME
from pycon_us.state import Conference, use_conference

logger = logging.getLogger(__name__)

SOURCE_LABELS = {
    "none": "No schedule yet",
    "bundled": "Schedule bundled with the app",
    "cache": "Schedule saved on this device",
    "network": "Schedule downloaded",
}

STATUS_LABELS = {
    "fresh": "Up to date",
    "stale": "May be out of date",
    "refreshing": "Refreshing…",
    "offline": "Offline: showing the saved schedule",
    "problem": "Couldn't refresh: showing the saved schedule",
}

APPEARANCE_LABELS: dict[Appearance, str] = {
    "system": "System",
    "light": "Light",
    "dark": "Dark",
}


@ft.component
def Stub() -> ft.View:
    """The data the boot gate published, a Refresh button and the Appearance setting."""
    page = ft.context.page
    svc = use_services()
    conference = use_conference()
    prefs = use_prefs()

    async def log_shown() -> None:
        # D-112's content line: a SharedPreferences round trip after the render, so the
        # patch has reached Flutter when it is logged.
        await svc.storage.get(THEME)
        logger.info(
            "Content shown: %s feed, version %d", conference.source, conference.version
        )

    ft.use_effect(log_shown, [conference.version])

    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    async def choose_appearance(e: ft.Event[ft.SegmentedButton]) -> None:
        theme = cast(Appearance, e.control.selected[0])
        if not await prefs.save(svc.storage, theme=theme):
            page.show_dialog(
                ft.SnackBar(
                    ft.Text("Couldn't save your change"),
                    behavior=ft.SnackBarBehavior.FLOATING,
                )
            )

    use_24h = bool(page.media and page.media.always_use_24_hour_format)
    status = STATUS_LABELS[conference.status(svc.year.conference)]
    return ft.View(
        route="/",
        padding=16,
        appbar=ft.AppBar(title=ft.Text(APP_NAME), center_title=False),
        controls=[
            ft.SafeArea(
                expand=True,
                content=ft.Column(
                    scroll=ft.ScrollMode.AUTO,
                    spacing=12,
                    expand=True,
                    controls=[
                        ft.Text(
                            SOURCE_LABELS[conference.source],
                            theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
                        ),
                        ft.Text(
                            _fetched(conference, svc.year.conference.zone, use_24h),
                            theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                        ),
                        ft.Text(status, theme_style=ft.TextThemeStyle.BODY_MEDIUM),
                        ft.Text(
                            _first_day(conference),
                            theme_style=ft.TextThemeStyle.BODY_LARGE,
                        ),
                        ft.FilledTonalButton(
                            "Refresh",
                            icon=ft.Icons.REFRESH,
                            on_click=refresh,
                            disabled=conference.refreshing,
                        ),
                        ft.Text(
                            "Appearance", theme_style=ft.TextThemeStyle.TITLE_SMALL
                        ),
                        ft.SegmentedButton(
                            selected=[prefs.theme],  # controlled (D-157)
                            segments=[
                                ft.Segment(value=value, label=ft.Text(label))
                                for value, label in APPEARANCE_LABELS.items()
                            ],
                            on_change=choose_appearance,
                        ),
                        ft.Text(
                            "Not an official PSF app.",
                            theme_style=ft.TextThemeStyle.BODY_SMALL,
                        ),
                    ],
                ),
            )
        ],
    )


def _fetched(conference: Conference, zone: tzinfo, use_24h: bool) -> str:
    if conference.fetched_at is None:
        return ""
    day = day_label(local_date(conference.fetched_at, zone))
    return f"Fetched {day}, {time_label(conference.fetched_at, zone, use_24h=use_24h)}"


def _first_day(conference: Conference) -> str:
    if conference.data is None or not conference.data.days:
        return "No sessions"
    day = conference.data.days[0]
    count = sum(len(group.session_ids) for group in day.groups)
    return f"{day_label(day.date)}: {count} sessions"
