"""Settings (``/more/settings``): Appearance, Reminders, Start screen and Data (THEME-01).

Two Material controls instead of Ionic's four-mode Cupertino sheet, both following the
OS until the user chooses otherwise (D-23, ux.md §6.9): the System, Light and Dark
radio rows, which More held until this page existed (D-169), and a High contrast
switch, which shows the OS flag until it is switched against it (D-286). A choice
applies at once and is saved with ``Prefs.save()``; one that cannot be saved still
applies for the session, and a SnackBar says so (D-120). Then Reminders, live in a build
with E3 and in D-60's interim without (``settings_reminders.py``, D-401), "Open the app on" for a signed-in lead-retrieval
account (Now or Lead scanner, D-16, #689), and Data, the
schedule's source and age with Refresh now, and the zone the times are in
(``settings_data.py``). More pushes it at ``/more/settings``, and My schedule's
Reminder settings at ``/my-schedule/settings``, so Back returns to the opener (D-17,
D-401).
"""

from typing import cast

import flet as ft

from pycon_us.account import use_account
from pycon_us.prefs import Appearance, StartScreen, use_prefs
from pycon_us.screens.settings_data import DataSection
from pycon_us.screens.settings_reminders import RemindersSection, interim_section
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.semantics import named
from pycon_us.ui.snack_bars import say_if_unsaved
from pycon_us.ui.widths import LIST, sides, use_margin

APPEARANCE_LABELS: dict[Appearance, str] = {
    "system": "System",
    "light": "Light",
    "dark": "Dark",
}
"""Appearance's rows, in order, the default first (ux.md §6.9)."""

START_SCREEN = "Open the app on"
"""The Start screen section's heading (D-16)."""

START_LABELS: dict[StartScreen, str] = {"now": "Now", "lead": "Lead scanner"}
"""The Start screen's rows, in order: ``auto`` shows as Lead scanner, its meaning."""

HIGH_CONTRAST = "High contrast"
"""The switch row's title."""

FOLLOWS_DEVICE = "Follows your device setting"
"""The switch row's subtitle while it follows the OS flag (``system``, D-286)."""

RADIO_WIDTH = 48
"""A ``Radio``'s width with its padded 48 dp tap target, the leading slot of
Appearance's rows. The switch row's icon gets a slot this wide, since a bare 24 dp
icon would start its title 24 dp left of theirs (#503's review). Data's icons get it too."""


@ft.component
def Settings() -> ft.View:
    """The Settings page: Appearance's rows and High contrast switch, Reminders, Data."""
    page = ft.context.page
    svc = use_services()
    margin = use_margin(LIST)  # its width class (D-305)
    prefs = use_prefs()
    account = use_account()

    @report_errors
    async def choose_appearance(e: ft.Event[ft.RadioGroup]) -> None:
        theme = cast(Appearance, e.control.value)
        say_if_unsaved(page, await prefs.save(svc.storage, theme=theme))

    @report_errors
    async def switch_high_contrast(e: ft.Event[ft.Switch]) -> None:
        setting = prefs.high_contrast_setting(bool(e.control.value))
        say_if_unsaved(page, await prefs.save(svc.storage, high_contrast=setting))

    @report_errors
    async def choose_start_screen(e: ft.Event[ft.RadioGroup]) -> None:
        screen = cast(StartScreen, e.control.value)
        say_if_unsaved(page, await prefs.save(svc.storage, start_screen=screen))

    rows: list[ft.Control] = [
        SectionHeader("Appearance"),  # level 2, a section of the page (D-211)
        appearance(prefs.theme, choose_appearance),
        high_contrast(
            prefs.high_contrast_on,
            follows_device=prefs.high_contrast == "system",
            on_change=switch_high_contrast,
        ),
    ]
    rows.append(
        RemindersSection(RADIO_WIDTH)
        if svc.reminders is not None  # a build with E3 (D-401)
        else interim_section(page.platform, slot=RADIO_WIDTH)
    )
    # A lead-retrieval account's only, with a mock URL, as the scanner (D-16, D-51).
    if prefs.private_api_enabled and account.lead_retrieval:
        rows.append(start_screen(prefs.start_screen, choose_start_screen))
    rows.append(DataSection(RADIO_WIDTH))
    return AppScaffold(
        title="Settings",
        source=__name__,
        body=ft.ListView(
            rows,
            expand=True,
            padding=sides(margin),
        ),
    )


def appearance(
    selected: Appearance, on_change: ft.ControlEventHandler[ft.RadioGroup]
) -> ft.Control:
    """Return Appearance's radio rows: System, Light and Dark (D-23).

    Args:
        selected: ``Prefs.theme``; the group is controlled (D-157).
        on_change: Saves the choice.
    """
    return radio_rows("settings.appearance", APPEARANCE_LABELS, selected, on_change)


def start_screen(
    selected: StartScreen, on_change: ft.ControlEventHandler[ft.RadioGroup]
) -> ft.Control:
    """Return the Start screen section: its heading over Now and Lead scanner (D-16).

    ``auto``, the stored default, shows as Lead scanner, where it opens the app; a
    choice stores ``now`` or ``lead``, and a sign-out keeps it (#689).

    Args:
        selected: ``Prefs.start_screen``.
        on_change: Saves the choice.
    """
    shown = "now" if selected == "now" else "lead"
    return ft.Column(
        [
            SectionHeader(START_SCREEN),  # level 2, as Appearance (D-211)
            radio_rows("settings.start_screen", START_LABELS, shown, on_change),
        ],
        spacing=0,
    )


def radio_rows[T: str](
    name: str,
    labels: dict[T, str],
    selected: T,
    on_change: ft.ControlEventHandler[ft.RadioGroup],
) -> ft.Control:
    """Return a controlled group of radio rows, one per value (D-169).

    Each row is a ``ListTile`` whose whole row selects (``toggle_inputs``), one node
    with its identifier, ``<name>.<value>``, read as one radio button; the rows reflow
    at any text size, where three segments in one row clipped "System" at 200 % on
    360 dp (D-169).

    Args:
        name: The identifiers' prefix, e.g. ``settings.appearance``.
        labels: Each value's title, in order.
        selected: The value the group shows (D-157).
        on_change: Saves the choice.
    """
    return ft.RadioGroup(
        value=selected,
        on_change=on_change,
        content=ft.Column(
            [
                named(
                    f"{name}.{value}",
                    ft.ListTile(
                        leading=ft.Radio(value=value),
                        title=text,
                        toggle_inputs=True,  # a tap anywhere on the row selects it
                    ),
                )
                for value, text in labels.items()
            ],
            spacing=0,
        ),
    )


def high_contrast(
    on: bool, *, follows_device: bool, on_change: ft.ControlEventHandler[ft.Switch]
) -> ft.Control:
    """Return the High contrast row: a switch the whole row toggles (D-23, D-286).

    One node with its identifier, read as "High contrast", the subtitle if any, and
    the switch's state. Its decorative icon is centred in a slot as wide as a radio,
    so it sits under Appearance's radios and its title starts where theirs do.

    Args:
        on: Whether high contrast applies (``Prefs.high_contrast_on``): under System,
            the OS flag, so the switch follows it when it is read on resume.
        follows_device: The setting is ``system``; the subtitle says so.
        on_change: Saves the setting the switch's new state stands for.
    """
    return named(
        "settings.high_contrast",
        ft.ListTile(
            leading=ft.Container(
                ft.Icon(ft.Icons.CONTRAST_OUTLINED),
                width=RADIO_WIDTH,
                alignment=ft.Alignment.CENTER,
            ),
            title=HIGH_CONTRAST,
            subtitle=FOLLOWS_DEVICE if follows_device else None,
            trailing=ft.Switch(value=on, on_change=on_change),
            toggle_inputs=True,  # a tap anywhere on the row toggles it
        ),
    )
