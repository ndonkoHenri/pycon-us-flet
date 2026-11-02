"""The Lead scanner's consent screen, asked once per account (LEAD-04, STORE-06; D-423).

Ionic asked with an alert on every entry and sent a "Cancel" to the Schedule. Here a
page asks once: an explanation, a checkbox the user ticks ("I'll only scan with
consent") and Continue, enabled only once it is ticked, which saves
``SCANNER_CONSENT``; Cancel goes where Back goes and saves nothing. The key is a staff
key (D-414), so a sign-out, a sign-in as another account and Clear staff data bring the
page back; "Sign in again" as the same expired account does not.
"""

from collections.abc import Callable

import flet as ft

from pycon_us.locations import parent_of
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.pref_keys import SCANNER_CONSENT
from pycon_us.ui.actions import padded
from pycon_us.ui.buttons import LABEL_PADDING
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.semantics import named
from pycon_us.ui.snack_bars import say_if_unsaved
from pycon_us.ui.widths import LIST, sides, use_margin

HEADING = "Scan only with consent"
EXPLANATION = (
    "Ask before you scan an attendee's badge, and scan it only if they say yes. "
    "Scanning a badge without that permission breaks the PyCon US Code of Conduct."
)
ASKED_AGAIN = "You're asked once for this account, and again after you sign out."
CHECK = "I'll only scan with consent"
CONTINUE = "Continue"
CANCEL = "Cancel"


@ft.component
def LeadConsent(*, title: str, on_given: Callable[[], None]) -> ft.Control:
    """Return the consent page shown before the Lead scanner's scan screen.

    Args:
        title: The tool's name, the app bar's title.
        on_given: Shows the scan screen in place, once the consent is saved (or kept
            for the session when the save failed, D-120).
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    margin = use_margin(LIST)  # its width class (D-305)
    ticked, set_ticked = ft.use_state(False)

    @report_errors
    def tick(e: ft.Event[ft.Checkbox]) -> None:
        set_ticked(bool(e.control.value))

    @report_errors
    async def give(_: ft.Event[ft.Button]) -> None:
        saved = await svc.storage.set(SCANNER_CONSENT, True)
        say_if_unsaved(page, saved)  # this session scans; the next start asks again
        on_given()

    @report_errors
    def cancel(_: ft.Event[ft.OutlinedButton]) -> None:
        page.navigate(parent_of(view_path, svc.memory.search_base))  # as Back

    return AppScaffold(
        title=title,
        source=__name__,
        body=ft.ListView(
            [
                padded(
                    ft.Semantics(
                        header=True,
                        heading_level=1,
                        content=ft.Text(
                            HEADING, theme_style=ft.TextThemeStyle.HEADLINE_SMALL
                        ),
                    )
                ),
                padded(ft.Text(EXPLANATION, theme_style=ft.TextThemeStyle.BODY_LARGE)),
                padded(
                    ft.Text(
                        ASKED_AGAIN,
                        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    )
                ),
                consent_check(ticked, tick),
                padded(buttons(ticked, give, cancel)),
            ],
            expand=True,
            padding=sides(margin, top=8, bottom=16),
        ),
    )


def consent_check(
    ticked: bool, on_change: Callable[[ft.Event[ft.Checkbox]], object]
) -> ft.Control:
    """Return the checkbox row: one node read as its label and state, toggled anywhere.

    A ``ListTile`` rather than the checkbox's own ``label``: Flet lays that label out
    in a ``Row`` with no room to wrap, so at 200 % text it ran off the screen; the
    tile's title wraps, and the tile is at least 56 dp tall (ux.md §9).

    Args:
        ticked: The checkbox's state (controlled, D-157).
        on_change: Takes the new state.
    """
    return named(
        "lead.consent.check",
        ft.ListTile(
            leading=ft.Checkbox(value=ticked, on_change=on_change),
            title=CHECK,
            toggle_inputs=True,  # a tap anywhere on the row ticks it
        ),
    )


def buttons(
    ticked: bool,
    on_continue: Callable[[ft.Event[ft.Button]], object],
    on_cancel: Callable[[ft.Event[ft.OutlinedButton]], object],
) -> ft.Control:
    """Return Cancel and Continue, end-aligned; Continue is disabled until ticked.

    Their own padding, as Developer's Apply: Flutter shrinks it as the text grows
    (D-232), and the row wraps at large text.

    Args:
        ticked: Whether the box is ticked.
        on_continue: Saves the consent and shows the scan screen.
        on_cancel: Goes where Back goes.
    """
    return ft.Row(
        [
            named(
                "lead.consent.cancel",
                ft.OutlinedButton(
                    CANCEL,
                    on_click=on_cancel,
                    style=ft.ButtonStyle(padding=LABEL_PADDING),
                ),
            ),
            named(
                "lead.consent.continue",
                ft.FilledButton(
                    CONTINUE,
                    on_click=on_continue,
                    disabled=not ticked,
                    style=ft.ButtonStyle(padding=LABEL_PADDING),
                    elevation=0,  # M3's filled button lies flat (D-232)
                ),
            ),
        ],
        alignment=ft.MainAxisAlignment.END,
        spacing=8,
        wrap=True,
    )
