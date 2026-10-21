"""Settings' Reminders section, in D-60's honest interim (NOTIF-01, P2-69).

Until scheduled notifications (E3) are in the pinned Flet, and always in the companion
app (D-63), the section is a level-2 heading and one sentence that says reminders aren't
available in this build and what covers for them, with no switch that would do nothing
(ux.md §6.9). On iOS the sentence adds that calendar exports carry an alarm; Android's
calendar import drops it, so there it doesn't (D-272). A module of its own so that P2-89
replaces its body with the live controls once ``capabilities.REMINDERS`` is true.
"""

import flet as ft

from pycon_us import capabilities
from pycon_us.ui.scaffold import SectionHeader
from pycon_us.ui.semantics import named

NOT_AVAILABLE = (
    "Reminders aren't available in this build. Your next session appears on Now."
)
"""The interim's sentence on Android, whose calendar import drops the alarm (D-272)."""

WITH_ALARM = f"{NOT_AVAILABLE[:-1]}, and calendar exports include an alarm."
"""The interim's sentence on iOS, where an exported session keeps its alarm (D-60)."""


def reminders_section(
    platform: ft.PagePlatform | None, *, slot: int
) -> ft.Control | None:
    """Return the Reminders section: its heading and the interim's sentence.

    ``None`` in a build that has E3 (``capabilities.REMINDERS``): its live controls are
    P2-89's, and until they exist the page shows no section rather than a wrong one.

    Args:
        platform: The page's platform: iOS's sentence mentions the calendar's alarm.
        slot: The width the icon is centred in: Settings' radio width, so the
            sentence starts where Appearance's titles do (#503's review).
    """
    if capabilities.REMINDERS:
        return None
    text = WITH_ALARM if platform == ft.PagePlatform.IOS else NOT_AVAILABLE
    return ft.Column(
        [
            SectionHeader("Reminders"),  # level 2, a section of the page (D-211)
            interim_row(text, slot=slot),
        ],
        spacing=0,
    )


def interim_row(text: str, *, slot: int) -> ft.Control:
    """Return the row that says reminders aren't available: one node, read as its words.

    Not a button and no switch: there is nothing to change in this build (D-60).

    Args:
        text: The interim's sentence for the platform.
        slot: The width the icon is centred in.
    """
    return named(
        "settings.reminders.interim",
        ft.ListTile(
            # Decorative: the words say it.
            leading=ft.Container(
                ft.Icon(ft.Icons.NOTIFICATIONS_OFF_OUTLINED),
                width=slot,
                alignment=ft.Alignment.CENTER,
            ),
            title=text,
            title_alignment=ft.ListTileTitleAlignment.TOP,
            min_vertical_padding=14,
        ),
    )
