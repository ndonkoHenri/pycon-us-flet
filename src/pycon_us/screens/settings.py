"""Settings (``/more/settings``): Appearance and its High contrast switch (THEME-01).

Two Material controls instead of Ionic's four-mode Cupertino sheet, both following the
OS until the user chooses otherwise (D-23, ux.md §6.9): the System, Light and Dark
radio rows, which More held until this page existed (D-169), and a High contrast
switch, which shows the OS flag until it is switched against it (D-286). A choice
applies at once and is saved with ``Prefs.save()``; one that cannot be saved still
applies for the session, and a SnackBar says so (D-120). Reminders (#27) and Data
(P2-62) join the page with their issues. More pushes it, so Back returns there (D-17).
"""

from typing import cast

import flet as ft

from pycon_us.prefs import Appearance, use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.ui.favorite import NOT_SAVED
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.semantics import named

APPEARANCE_LABELS: dict[Appearance, str] = {
    "system": "System",
    "light": "Light",
    "dark": "Dark",
}
"""Appearance's rows, in order, the default first (ux.md §6.9)."""

HIGH_CONTRAST = "High contrast"
"""The switch row's title."""

FOLLOWS_DEVICE = "Follows your device setting"
"""The switch row's subtitle while it follows the OS flag (``system``, D-286)."""


@ft.component
def Settings() -> ft.View:
    """The Settings page: Appearance's three rows and the High contrast switch."""
    page = ft.context.page
    svc = use_services()
    prefs = use_prefs()

    @report_errors
    async def choose_appearance(e: ft.Event[ft.RadioGroup]) -> None:
        theme = cast(Appearance, e.control.value)
        say_if_unsaved(page, await prefs.save(svc.storage, theme=theme))

    @report_errors
    async def switch_high_contrast(e: ft.Event[ft.Switch]) -> None:
        setting = prefs.high_contrast_setting(bool(e.control.value))
        say_if_unsaved(page, await prefs.save(svc.storage, high_contrast=setting))

    return AppScaffold(
        title="Settings",
        body=ft.ListView(
            [
                SectionHeader("Appearance"),  # level 2, a section of the page (D-211)
                appearance(prefs.theme, choose_appearance),
                high_contrast(
                    prefs.high_contrast_on,
                    follows_device=prefs.high_contrast == "system",
                    on_change=switch_high_contrast,
                ),
            ],
            expand=True,
        ),
    )


def say_if_unsaved(page: ft.Page, saved: bool) -> None:
    """Show "Couldn't save your change" when a setting was applied but not saved (D-120).

    The setting still applies for the session; the SnackBar says it ends on relaunch.

    Args:
        page: The session's page.
        saved: What ``Prefs.save()`` returned.
    """
    if not saved:
        page.show_dialog(
            ft.SnackBar(ft.Text(NOT_SAVED), behavior=ft.SnackBarBehavior.FLOATING)
        )


def appearance(
    selected: Appearance, on_change: ft.ControlEventHandler[ft.RadioGroup]
) -> ft.Control:
    """Return Appearance's radio rows: System, Light and Dark (D-23).

    Each row is a ``ListTile`` whose whole row selects (``toggle_inputs``), one node
    with its identifier, read as one radio button; the rows reflow at any text size,
    where three segments in one row clipped "System" at 200 % on 360 dp (D-169).

    Args:
        selected: ``Prefs.theme``; the group is controlled (D-157).
        on_change: Saves the choice.
    """
    return ft.RadioGroup(
        value=selected,
        on_change=on_change,
        content=ft.Column(
            [
                named(
                    f"settings.appearance.{value}",
                    ft.ListTile(
                        leading=ft.Radio(value=value),
                        title=text,
                        toggle_inputs=True,  # a tap anywhere on the row selects it
                    ),
                )
                for value, text in APPEARANCE_LABELS.items()
            ],
            spacing=0,
        ),
    )


def high_contrast(
    on: bool, *, follows_device: bool, on_change: ft.ControlEventHandler[ft.Switch]
) -> ft.Control:
    """Return the High contrast row: a switch the whole row toggles (D-23, D-286).

    One node with its identifier, read as "High contrast", the subtitle if any, and
    the switch's state. Its icon lines its title up with Appearance's options, after
    their radios, and is decorative.

    Args:
        on: Whether high contrast applies (``Prefs.high_contrast_on``): under System,
            the OS flag, so the switch follows it when it is read on resume.
        follows_device: The setting is ``system``; the subtitle says so.
        on_change: Saves the setting the switch's new state stands for.
    """
    return named(
        "settings.high_contrast",
        ft.ListTile(
            leading=ft.Icon(ft.Icons.CONTRAST_OUTLINED),
            title=HIGH_CONTRAST,
            subtitle=FOLLOWS_DEVICE if follows_device else None,
            trailing=ft.Switch(value=on, on_change=on_change),
            toggle_inputs=True,  # a tap anywhere on the row toggles it
        ),
    )
