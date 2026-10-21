"""My schedule's extras (ux.md §5.6): the app bar's overflow and the all-over notice.

- **The overflow** ("More options", D-289): Export to calendar (.ics), every saved
  session still in the schedule in one file, ``pycon-us-<year>-my-schedule.ics``, each
  event with its alarm (SESS-05). It goes to the calendar by session detail's Add to
  calendar route (``services.calendar``, D-272): iOS's "Add All" sheet, or Android's
  save dialog and a SnackBar. With nothing saved there is nothing to export, so the
  screen shows no overflow.
- **The all-over notice** heads the list when every saved session has ended (D-191).

The screen itself is ``screens/my_schedule.py``; these left it to keep it near 400
lines (D-66).
"""

from collections.abc import Callable

import flet as ft

from pycon_us import clock
from pycon_us.core.ics import calendar_file
from pycon_us.core.models import Session
from pycon_us.services import use_services
from pycon_us.services.calendar import add_to_calendar
from pycon_us.services.errors import report_errors
from pycon_us.ui.buttons import LABEL_PADDING
from pycon_us.ui.menus import menu_item, overflow_menu

SCREEN = "my_schedule"
"""The screen's name in its semantics identifiers (decisions §M)."""

EXPORT = "Export to calendar (.ics)"
"""The overflow's export item (ux.md §5.6), the same words on both platforms (D-272)."""

ALL_OVER = "All your saved sessions are over"
SEE_TODAY = "See what's on today"
CONFERENCE_OVER = "{name} is over. Your saved sessions stay here."


def export_slug(year: int) -> str:
    """Return the export's file name without ``.ics``: ``pycon-us-2026-my-schedule``.

    The year keeps one year's export from looking like another's in the Files app.

    Args:
        year: The conference year.
    """
    return f"pycon-us-{year}-my-schedule"


@ft.component
def ScheduleMenu(sessions: tuple[Session, ...]) -> ft.Control:
    """The app bar's overflow ("More options"): Export to calendar (.ics).

    The item is disabled while the calendar's sheet or the save dialog is up, so a
    second tap does not serve or save the file twice; in place, so the button and the
    item keep their nodes and the screen reader's focus comes back to the button when
    the menu closes (D-182, D-225). Its label wraps at 200 % text (``menu_item()``,
    D-233). Whatever happens is said by ``add_to_calendar()``, on this View (D-210).

    Args:
        sessions: Every saved session still in the schedule (``Agenda.sessions``); at
            least one, since the screen shows no overflow without.
    """
    svc = use_services()
    exporting, set_exporting = ft.use_state(False)

    @report_errors
    async def export() -> None:
        year = svc.year.conference.year
        data = calendar_file(sessions, year=year, now=clock.now())
        set_exporting(True)
        try:
            await add_to_calendar(svc, export_slug(year), data)
        finally:
            set_exporting(False)

    item = menu_item(
        ft.Icons.EVENT_AVAILABLE_OUTLINED,  # session detail's Add to calendar's icon
        EXPORT,
        export,
        identifier=f"{SCREEN}.export",
        disabled=exporting,
    )
    return overflow_menu(f"{SCREEN}.overflow", [item])


def all_over(
    on_see_today: Callable[[], None] | None = None, *, body: str | None = None
) -> ft.Control:
    """Return the notice that heads the list when every saved session has ended.

    Compact and start-aligned, its text on the fold tile's text column, rather than
    the full-screen empty state: the "Earlier days" tile under it is still content and
    should not be pushed to the middle of the screen (ux.md §5.6).

    Args:
        on_see_today: What "See what's on today" does, while today is a conference
            day; None after the conference, when Now has nothing on today.
        body: A second line, after the conference.
    """
    texts: list[ft.Control] = [
        ft.Semantics(  # a container of its own, as EmptyState's title (D-182)
            header=True,
            heading_level=2,  # a section under the page's title, as the day headings (D-211)
            container=True,
            content=ft.Text(ALL_OVER, theme_style=ft.TextThemeStyle.TITLE_SMALL),
        )
    ]
    if body is not None:
        texts.append(
            ft.Text(
                body,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    column: list[ft.Control] = [
        ft.Semantics(
            identifier=f"{SCREEN}.all_over",
            container=True,
            live_region=True,
            content=ft.Column(texts, spacing=4),
        )
    ]
    if on_see_today is not None:
        column.append(
            ft.FilledTonalButton(
                SEE_TODAY,
                on_click=on_see_today,
                # Material's 100 % padding at every size (D-344).
                style=ft.ButtonStyle(padding=LABEL_PADDING),
                elevation=0,  # with a style, Flet lifts it to 1 (D-344)
            )
        )
    return ft.Container(
        ft.Row(
            [
                ft.Icon(
                    ft.Icons.EVENT_AVAILABLE_OUTLINED,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Column(column, spacing=12, expand=True),
            ],
            spacing=16,  # the text on the fold tile's text column, 56 dp in
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        padding=ft.Padding.only(left=16, top=16, right=16, bottom=8),
    )
