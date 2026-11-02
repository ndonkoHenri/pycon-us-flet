"""The platform's share sheet: where it points from, a text, and a bug report (D-62).

Session detail's Share sends a text (``share_text()``, NEW-06); About this app's Report
a problem and the Developer screen's Share log send the app's ``console.log`` with the
plain diagnostics as its text, or the diagnostics alone where there is no log
(``share_console_log()``, INFO-04, D-297). Both point the sheet from the window's centre
(``centre()``), which a phone ignores and a tablet needs (D-09). A failure to open the
sheet is expected (D-71): it is logged by its class only, since the error's text repeats
the call's arguments (D-72). The rows that report a problem, About this app's and Help &
safety's, hold the share's state through ``use_problem_report()`` (INFO-11).
"""

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import NamedTuple

import flet as ft
from flet.utils import is_embedded

from pycon_us import APP_NAME
from pycon_us.favorites import Favorites, use_favorites
from pycon_us.prefs import Prefs, use_prefs
from pycon_us.services import Services, use_services
from pycon_us.services.diagnostics import diagnostics_text, gather_facts
from pycon_us.services.errors import report_errors, say
from pycon_us.services.storage import SERVICE_ERRORS
from pycon_us.state import Conference, use_conference
from pycon_us.theme import Tokens
from pycon_us.ui.actions import NO_OUTCOME, Outcome, outcome_line

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


class ProblemReport(NamedTuple):
    """A report row's state and action, from ``use_problem_report()``."""

    outcome: Outcome
    """How the last share ended, said under the rows; ``NO_OUTCOME`` before one."""
    sharing: bool
    """The share sheet is up: the row is disabled until it closes."""
    packaged: bool
    """A packaged build, whose share adds ``console.log`` (``report_subtitle()``)."""
    share: Callable[[], Awaitable[None]]
    """The row's action: ``share_console_log()``, its outcome kept for the line."""


def use_problem_report() -> ProblemReport:
    """Hold a report row's share: its outcome, whether the sheet is up, and the action.

    A hook, called from the component that owns the rows (About this app's Help us fix
    it, Help & safety's Report a problem with the app), so a share re-renders those
    rows and not their page (D-297, INFO-11). A dismissed sheet leaves no outcome.
    """
    svc = use_services()
    conference = use_conference()
    prefs = use_prefs()
    favorites = use_favorites()
    outcome, set_outcome = ft.use_state(NO_OUTCOME)
    sharing, set_sharing = ft.use_state(False)
    packaged = is_embedded()  # where the log is a file to add

    @report_errors
    async def share() -> None:
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

    return ProblemReport(outcome, sharing, packaged, share)


def report_outcome(identifier: str, outcome: Outcome, *, tokens: Tokens) -> ft.Control:
    """Return the line under a report's rows that says how the share ended (D-29, D-210).

    A live region, so a screen reader says it when a share ends; hidden while there
    are no words.

    Args:
        identifier: For UI flows, e.g. ``help.report_outcome``.
        outcome: ``ProblemReport.outcome``.
        tokens: The theme's tokens, for the line's colours.
    """
    return ft.Semantics(
        identifier=identifier,
        live_region=True,
        visible=bool(outcome[0]),
        content=outcome_line(*outcome, tokens=tokens),
    )


def new_issue_url(source_url: str) -> str:
    """Return the page that opens a new issue in the repository at ``source_url`` (D-88).

    Args:
        source_url: ``SOURCE_URL``, once the repository is public.
    """
    return f"{source_url.rstrip('/')}/issues/new"


def centre(page: ft.Page) -> ft.Offset | None:
    """Return the middle of the window, where the share sheet points from on a tablet.

    Flet sends the point without a size; since the pin ``08b89cce5`` share_plus 13.3.1
    turns that empty rectangle into a small one at the view's centre, so an iPad opens
    the sheet (F263; before, it refused, F115).
    """
    if not page.width or not page.height:
        return None
    return ft.Offset(page.width / 2, page.height / 2)


async def share_text(svc: Services, text: str, *, subject: str) -> None:
    """Open the share sheet with ``text``; call it from an event handler.

    When the platform reports that the sheet could not open, a SnackBar says so, on the
    View the button is on (D-210). Whether the person then shared or dismissed it needs
    no answer. The caller wraps it in ``focus_back()``, so the button gets the focus
    again once the sheet has closed (D-372).

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
        say(page, NOT_SHARED)


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
    problem, the Developer screen's Share log and Help & safety's Report a problem with
    the app (INFO-11). The text is
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
