"""The platform's share sheet: where it points from, a text, and a bug report (D-62).

Session detail's Share sends a text (``share_text()``, NEW-06); About this app's Report
a problem and the Developer screen's Share log send the app's ``console.log`` with the
plain diagnostics as its text, or the diagnostics alone where there is no log
(``share_console_log()``, INFO-04, D-297). Both point the sheet from the window's centre
(``centre()``), which a phone ignores and a tablet needs (D-09). A failure to open the
sheet is expected (D-71): it is logged by its class only, since the error's text repeats
the call's arguments (D-72).
"""

import logging
from pathlib import Path

import flet as ft

from pycon_us import APP_NAME
from pycon_us.favorites import Favorites
from pycon_us.prefs import Prefs
from pycon_us.services import Services
from pycon_us.services.diagnostics import diagnostics_text, gather_facts
from pycon_us.services.storage import SERVICE_ERRORS
from pycon_us.state import Conference
from pycon_us.ui.actions import NO_OUTCOME, Outcome

logger = logging.getLogger(__name__)

NOT_SHARED = "Couldn't open the share sheet"
"""What a failed share says: session detail's SnackBar, and a report's outcome line."""

WITH_LOG = "Sends the app's log and diagnostics, for a bug report"
"""A report row's second line in a packaged build, where ``console.log`` is a file (F14)."""

WITHOUT_LOG = (
    "Sends diagnostics. Not a packaged build: the log is in the terminal that runs it"
)
"""A report row's second line in the companion app, said before the tap (D-297)."""

REPORT_NOT_SHARED: Outcome = (f"{NOT_SHARED}.", False)
LOG_SHARED: Outcome = ("Log and diagnostics shared.", True)
DIAGNOSTICS_SHARED: Outcome = ("Diagnostics shared.", True)
NO_LOG_YET: Outcome = ("Diagnostics shared. There was no log to add yet.", True)
REPORT_OFFERED: Outcome = ("Handed to the share sheet.", True)
"""When the platform cannot say how the sheet ended (``UNAVAILABLE``): true either way."""

REPORT_SUBJECT = f"{APP_NAME}: problem report"
"""The subject of an email made from a report."""


def centre(page: ft.Page) -> ft.Offset | None:
    """Return the middle of the window, where the share sheet points from on a tablet.

    At the pin an iPad still refuses it: Flet sends the point without a size, and
    share_plus wants a rectangle that is not empty, so a share there fails and says so
    (F115, U95).
    """
    if not page.width or not page.height:
        return None
    return ft.Offset(page.width / 2, page.height / 2)


async def share_text(svc: Services, text: str, *, subject: str) -> None:
    """Open the share sheet with ``text``; call it from an event handler.

    When the platform reports that the sheet could not open, a SnackBar says so, on the
    View the button is on (D-210). Whether the person then shared or dismissed it needs
    no answer.

    Args:
        svc: The session's services, for the share sheet.
        text: What to share.
        subject: The subject of an email made from it: the session's title.
    """
    page = ft.context.page
    try:
        await svc.share.share_text(
            text, subject=subject, share_position_origin=centre(page)
        )
    except SERVICE_ERRORS as error:
        logger.warning("Could not share a text: %s", type(error).__name__)
        page.show_dialog(
            ft.SnackBar(ft.Text(NOT_SHARED), behavior=ft.SnackBarBehavior.FLOATING)
        )


def report_subtitle(packaged: bool) -> str:
    """Return a report row's second line: what a tap sends, said before it (D-297).

    Args:
        packaged: A packaged build (``is_embedded()``), which writes ``console.log``.
    """
    return WITH_LOG if packaged else WITHOUT_LOG


async def share_console_log(
    svc: Services,
    *,
    packaged: bool,
    conference: Conference,
    prefs: Prefs,
    favorites: Favorites,
) -> Outcome:
    """Open the share sheet with ``console.log`` and the diagnostics as its text.

    The one way the app shares a bug report (INFO-04, D-297): About this app's Report a
    problem, the Developer screen's Share log and, later, Help & safety. The text is
    ``diagnostics_text()`` (D-271); the log holds no secrets or email addresses: the app
    never logs them, and the handler writes any address a line quotes as ``<email>``
    (D-196). Where there is no log to add, the companion app's run, whose Python is on
    the laptop (F14), or a packaged build's empty or unreadable log, the diagnostics go
    alone. Call it from an ``async`` handler (D-70); the sheet points from the window's
    centre (D-62).

    Args:
        svc: The session's services: the year, the storage paths and the share sheet.
        packaged: A packaged build, where the template writes ``console.log``.
        conference: The published schedule, for the diagnostics.
        prefs: The Developer options in effect, for the diagnostics.
        favorites: The saved sessions, counted in the diagnostics.

    Returns:
        What to say: what was shared, or that the sheet failed; nothing
        (``NO_OUTCOME``) when it was dismissed; that the sheet had the report when the
        platform cannot say which (``UNAVAILABLE``, on some Android share targets).
    """
    page = ft.context.page
    facts = await gather_facts(
        page,
        info=svc.year.conference,
        conference=conference,
        prefs=prefs,
        favorites=favorites,
    )
    text = diagnostics_text(facts)
    log = await _console_log(svc) if packaged else None
    origin = centre(page)
    try:
        if log is None:
            result = await svc.share.share_text(
                text,
                title="Share diagnostics",
                subject=REPORT_SUBJECT,
                share_position_origin=origin,
            )
        else:
            result = await svc.share.share_files(
                [ft.ShareFile.from_path(str(log))],
                title="Share the log and diagnostics",
                text=text,
                subject=REPORT_SUBJECT,
                share_position_origin=origin,
            )
    except SERVICE_ERRORS as error:
        # The class only: an invoke error's text repeats the call's arguments (D-72).
        logger.warning("Could not share a report: %s", type(error).__name__)
        return REPORT_NOT_SHARED
    match result.status:
        case ft.ShareResultStatus.SUCCESS:
            if log is not None:
                return LOG_SHARED
            return NO_LOG_YET if packaged else DIAGNOSTICS_SHARED
        case ft.ShareResultStatus.DISMISSED:
            return NO_OUTCOME
        case _:
            return REPORT_OFFERED


async def _console_log(svc: Services) -> Path | None:
    """Return the packaged app's ``console.log`` when it has something in it, else None.

    A path the platform cannot give is logged by its class (D-72); the report then
    carries the diagnostics alone.

    Args:
        svc: The session's services, for the storage paths.
    """
    try:
        path = Path(await svc.paths.get_console_log_filename())
    except SERVICE_ERRORS as error:
        logger.warning("Could not find the log: %s", type(error).__name__)
        return None
    try:
        return path if path.is_file() and path.stat().st_size > 0 else None
    except OSError:
        return None
