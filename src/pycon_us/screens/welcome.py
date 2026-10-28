"""Welcome (``/welcome``): the first-run screen, shown once before Now (SHELL-02, STORE-07).

One honest screen where the Ionic app had a tutorial of slides with a hard-coded year
and a permission prompt over it (ux.md §6.8): "Welcome to PyCon US 2026", the city and
the dates from ``conference.toml`` (D-35), what the app does in three rows, Get started,
and who built it: "Built with Python and Flet by the community · Not an official PSF
app" (D-36). No permission prompt (D-61), no icon until O-4 gives the app one (#15).

It is a root without a bar, in the splash's purple in every scheme, one of D-28's
identity moments. Get started saves ``pycon.onboarded`` and replaces the route with
Now, so Back on Now leaves the app rather than returning here. Back on Welcome goes to
Now, as on the other non-Now roots, whether a plain start or a link opened it (D-321).
The start route sends a plain start here until then (``locations.start_target()``,
D-287).
"""

import logging
from dataclasses import dataclass
from datetime import date

import flet as ft

from pycon_us import capabilities, clock
from pycon_us.config import ConferenceInfo
from pycon_us.core.timefmt import date_range_label, today
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.theme import BOOT_COLOR
from pycon_us.ui.semantics import named

logger = logging.getLogger(__name__)

INK = "#FFFFFF"
"""Every text, icon and the button's fill: white on the purple is 11.1:1 (ux.md §3.1)."""

ROWS: tuple[tuple[ft.IconData, str], ...] = (
    (ft.Icons.EVENT_NOTE_OUTLINED, "Plan your schedule and save sessions"),
    (ft.Icons.MAP_OUTLINED, "Find rooms, booths and hours, even offline"),
)
"""What the app does, one phrase per row (ux.md §6.8)."""

REMINDERS_ROW = (
    ft.Icons.NOTIFICATIONS_OUTLINED,
    "Get reminders before the talks you saved",
)
"""The third row, only when the build has reminders (``capabilities.REMINDERS``)."""

THANKS = "Thanks for coming. See you next year."
"""The line under the dates once the conference's last day is over."""

FOOTNOTE = "Built with Python and Flet by the community · Not an official PSF app"
"""Who made the app and who did not (D-36)."""


@dataclass(frozen=True)
class WelcomeCopy:
    """What Welcome says, from the year's data and the day.

    Attributes:
        title: The page's level-1 heading, "Welcome to PyCon US 2026".
        place: "Long Beach, CA · May 13–19".
        thanks: ``THANKS`` after the conference, else None.
        rows: The value rows, each an icon and its phrase.
    """

    title: str
    place: str
    thanks: str | None
    rows: tuple[tuple[ft.IconData, str], ...]


def welcome_copy(info: ConferenceInfo, day: date, *, reminders: bool) -> WelcomeCopy:
    """Return what Welcome says on a conference-local day.

    Args:
        info: The year's facts: its name, city and dates (D-35).
        day: Today in the conference's zone (``timefmt.today()``); after
            ``info.last_day``, the last sprint day, the page thanks the reader, as
            Now's header does then.
        reminders: The build has reminders (``capabilities.REMINDERS``);
            without them, the page does not promise any.
    """
    return WelcomeCopy(
        title=f"Welcome to {info.name}",
        place=f"{info.city} · {date_range_label(info.first_day, info.last_day)}",
        thanks=THANKS if day > info.last_day else None,
        rows=(*ROWS, REMINDERS_ROW) if reminders else ROWS,
    )


@ft.component
def Welcome() -> ft.View:
    """The Welcome page: the year, what the app does, Get started and who built it."""
    page = ft.context.page
    svc = use_services()
    prefs = use_prefs()
    info = svc.year.conference
    copy = welcome_copy(
        info, today(clock.now(), info.zone), reminders=capabilities.REMINDERS
    )

    @report_errors
    async def get_started() -> None:
        if not await prefs.save(svc.storage, onboarded=True):
            # Storage has logged the key (D-120). The app goes on all the same, and
            # Welcome shows again at the next start.
            logger.warning("Welcome is done for this session only: not saved")
        page.navigate("/now")  # a root replaces a root: Back on Now leaves the app

    @report_errors
    async def leave_for_now(e: ft.Event[ft.View]) -> None:
        # D-142's rule for a non-Now root (D-321): Now replaces Welcome rather than
        # the app closing. Not Get started: Welcome shows again at the next start.
        page.navigate("/now")
        await e.control.confirm_pop(False)

    return ft.View(
        # The roots' key, which Start's View has too: the purple Start gives way to
        # Welcome, and Welcome to Now, without a transition (D-142).
        route="/",
        can_pop=False,
        on_confirm_pop=leave_for_now,
        bgcolor=BOOT_COLOR,
        padding=0,
        spacing=0,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            status_bar(),
            ft.SafeArea(
                expand=True,
                avoid_intrusions_top=False,  # status_bar() is under the status bar
                content=ft.Column(
                    expand=True,
                    spacing=0,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.ListView(body(copy), expand=True, padding=PAGE_PADDING),
                        start_button(get_started),
                    ],
                ),
            ),
        ],
    )


STATUS_BAR_STYLE = ft.SystemOverlayStyle(
    status_bar_color=ft.Colors.TRANSPARENT,
    status_bar_icon_brightness=ft.Brightness.LIGHT,  # Android: white icons
    status_bar_brightness=ft.Brightness.DARK,  # iOS: the bar is dark, so white text
)
"""The status bar over the purple: white icons and text in every scheme."""


def status_bar() -> ft.Control:
    """Return the strip under the status bar that gives it white icons (U85 interim).

    A View without an ``AppBar`` gives the status bar the theme's style (F105),
    whose icons are dark in a light scheme: 1.9:1 on the purple. Flet has no style
    of a View's own (U85, #509), so this is an ``AppBar`` with no toolbar, the status bar's
    height, under a theme that holds only the white style, in light and dark alike.
    Flutter takes the status bar's style from the frontmost region at its middle, so
    this one wins over the View's. The navigation bar keeps the theme's (D-151).
    Goes when U85 is in the pinned Flet.
    """
    theme = ft.Theme(system_overlay_style=STATUS_BAR_STYLE)
    return ft.Container(
        theme=theme,
        dark_theme=theme,
        content=ft.AppBar(
            toolbar_height=0,
            bgcolor=BOOT_COLOR,
            elevation=0,
            elevation_on_scroll=0,
            automatically_imply_leading=False,
        ),
    )


PAGE_PADDING = ft.Padding.only(left=24, top=48, right=24, bottom=16)
"""Around what scrolls: the margins of a page without a bar."""


def body(copy: WelcomeCopy) -> list[ft.Control]:
    """Return what scrolls, from the top: the heading, the place, the rows, the footnote.

    Each line is a node of its own, read in order, and a row is one phrase: its icon
    is decorative (D-33).

    Args:
        copy: ``welcome_copy()``'s words.
    """
    lines: list[ft.Control] = [
        # No bar, so the page's own title is its level-1 heading (D-211).
        ft.Semantics(
            header=True,
            heading_level=1,
            content=line(copy.title, ft.TextThemeStyle.HEADLINE_SMALL),
        ),
        gap(8),
        line(copy.place, ft.TextThemeStyle.TITLE_MEDIUM, said=spoken(copy.place)),
    ]
    if copy.thanks is not None:
        lines += [gap(8), line(copy.thanks, ft.TextThemeStyle.BODY_LARGE)]
    lines.append(gap(32))
    for icon, phrase in copy.rows:
        lines += [value_row(icon, phrase), gap(20)]
    lines += [
        gap(12),
        line(FOOTNOTE, ft.TextThemeStyle.BODY_MEDIUM, said=spoken(FOOTNOTE)),
    ]
    return lines


def line(text: str, style: ft.TextThemeStyle, *, said: str | None = None) -> ft.Text:
    """Return a line of the page in white, which wraps at large text.

    Args:
        text: What it says.
        style: Its type.
        said: What a screen reader says instead, when it differs.
    """
    return ft.Text(text, theme_style=style, color=INK, semantics_label=said)


def gap(height: int) -> ft.Container:
    """Return empty space between two lines, in dp; it holds no text, so it never clips."""
    return ft.Container(height=height)


def spoken(text: str) -> str:
    """Return ``text`` as a screen reader should say it: a " · " is a full stop.

    "Long Beach, CA. May 13 to 19": the range's dash is "to", as Now's header says it.

    Args:
        text: What the screen shows.
    """
    return text.replace(" · ", ". ").replace("–", " to ")


def value_row(icon: ft.IconData, phrase: str) -> ft.Control:
    """Return one thing the app does: a decorative icon beside its phrase.

    The icon has no label, so the row reads as its phrase alone (D-33), and it sits
    beside the phrase's first line when the phrase wraps.

    Args:
        icon: An outlined Material icon (D-27).
        phrase: What the app does, one sentence without a full stop.
    """
    return ft.Row(
        spacing=16,
        vertical_alignment=ft.CrossAxisAlignment.START,
        controls=[
            ft.Icon(icon, color=INK, size=24),
            ft.Text(
                phrase,
                theme_style=ft.TextThemeStyle.BODY_LARGE,
                color=INK,
                # In a row a text gets unbounded width: it must take the rest of
                # the row to wrap at large text instead of overflowing.
                expand=True,
            ),
        ],
    )


def start_button(on_click: ft.ControlEventHandler[ft.Button]) -> ft.Control:
    """Return Get started, pinned under what scrolls, the full width (``welcome.start``).

    White with the purple's ink (11.1:1), since the theme's filled button is the
    scheme's indigo, which barely stands out on the purple. Its padding makes it 48
    dp tall at 100 % text and lets it grow with the text, never clipping it.

    Args:
        on_click: Saves that Welcome was seen and goes to Now.
    """
    return ft.Container(
        padding=ft.Padding.only(left=24, top=8, right=24, bottom=16),
        content=named(
            "welcome.start",
            ft.FilledButton(
                content=ft.Text("Get started", text_align=ft.TextAlign.CENTER),
                style=ft.ButtonStyle(
                    bgcolor=INK,
                    color=BOOT_COLOR,
                    padding=ft.Padding.symmetric(horizontal=24, vertical=14),
                ),
                # M3's filled button lies flat; a style would give it elevation 1.
                elevation=0,
                on_click=on_click,
            ),
        ),
    )
