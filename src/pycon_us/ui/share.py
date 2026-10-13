"""The platform's share sheet: where it points from, and sharing a text (D-62, NEW-06).

Session detail's Share sends a text (``share_text()``); the Developer screen's Share
log sends a file (``screens.developer_data.share_console_log``). Both point the sheet
from the window's centre (``centre()``), which a phone ignores and a tablet needs
(D-09). A failure to open the sheet is expected (D-71): it is logged by its class
only, since the error's text repeats the call's arguments (D-72).
"""

import logging

import flet as ft

from pycon_us.services import Services
from pycon_us.services.storage import SERVICE_ERRORS

logger = logging.getLogger(__name__)

NOT_SHARED = "Couldn't open the share sheet"
"""What a failed share says, as the Developer screen's Share log does."""


def centre(page: ft.Page) -> ft.Offset | None:
    """Return the middle of the window, where the share sheet points from on a tablet."""
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
