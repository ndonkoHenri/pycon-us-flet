"""Wi-Fi (``/more/wifi``): the conference network and its password, to read and copy.

The first thing attendees look for, often with no signal (INFO-08), so both values come
from the bundled year data (``content.toml``'s ``[wifi]``, D-280) and show at once,
offline. Each is selectable monospace text, read with its label as one phrase; Copy
beside the network and a "Copy password" button, the one way to copy the password, go
through ``copy_text()``, which confirms each copy once and says when one fails (D-263),
where Ionic copied only the password and assumed it worked. A year without the table
shows the feed's own ``wifi`` block, and without that an empty state that sends the
attendee to the information desk (``InfoBody``).
"""

import flet as ft

from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors
from pycon_us.ui.info_page import GUTTER, InfoBody
from pycon_us.ui.links import copy_text
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.semantics import named
from pycon_us.ui.states import EmptyState
from pycon_us.year_info import WifiInfo

SCREEN = "wifi"
"""The page's name in its semantics identifiers (decisions §M)."""

TITLE = "Wi-Fi"
"""The page's name: its app bar's title and its More row (ux.md §4.9's spelling)."""

NETWORK = "Network"
PASSWORD = "Password"
COPY_NETWORK = "Copy network name"
COPY_PASSWORD = "Copy password"
NETWORK_COPIED = "Network name copied"
NETWORK_NOT_COPIED = "Couldn't copy the network name"
PASSWORD_COPIED = "Password copied"
PASSWORD_NOT_COPIED = "Couldn't copy the password"

NO_WIFI = "No Wi-Fi details yet"
NO_WIFI_BODY = "Ask at the information desk for the network and its password."
"""The empty state's way out: no button can bring the details (ux.md §4.6)."""

VALUE_STYLE = ft.TextStyle(
    font_family="monospace",  # Android's alias; iOS has no such family
    font_family_fallback=["Menlo"],  # so iOS takes its system monospace font
)
"""A value's font, as the feed's code spans have it (``theme.MARKDOWN_STYLE``): in a
monospace font ``l``, ``1`` and ``I``, or ``O`` and ``0``, never look alike."""

BUTTON_PADDING = ft.Padding.only(left=16, top=10, right=24, bottom=10)
""""Copy password"'s padding: M3's for a button with an icon, plus room above and below,
as the Lightning talks sign-up has it: at the largest text the label otherwise touches
the pill's edges, and 10 dp keeps the one-line button 40 dp tall."""


@ft.component
def Wifi() -> ft.View:
    """The Wi-Fi page: the year's network and password, else the feed's block."""
    svc = use_services()
    wifi = svc.year.content.wifi
    blocks = [] if wifi is None else wifi_blocks(svc, wifi)
    empty = EmptyState(
        NO_WIFI,
        icon=ft.Icons.WIFI_OFF_OUTLINED,
        body=NO_WIFI_BODY,
        identifier=f"{SCREEN}.empty",
    )
    return AppScaffold(
        title=TITLE,
        body=InfoBody(blocks, block="wifi", screen=SCREEN, empty=empty),
    )


def wifi_blocks(svc: Services, wifi: WifiInfo) -> list[ft.Control]:
    """Return the page's blocks: the network with its Copy, the password, its button.

    Args:
        svc: The session's services, for the clipboard.
        wifi: The year's network and password.
    """

    @report_errors
    async def copy_network() -> None:
        await copy_text(svc, wifi.network, NETWORK_COPIED, NETWORK_NOT_COPIED)

    @report_errors
    async def copy_password() -> None:
        await copy_text(svc, wifi.password, PASSWORD_COPIED, PASSWORD_NOT_COPIED)

    copy = ft.IconButton(
        ft.Icons.CONTENT_COPY_OUTLINED, tooltip=COPY_NETWORK, on_click=copy_network
    )
    button = ft.FilledButton(
        COPY_PASSWORD,
        icon=ft.Icons.CONTENT_COPY_OUTLINED,
        on_click=copy_password,
        style=ft.ButtonStyle(padding=BUTTON_PADDING),
    )
    return [
        # 12 dp from the edge puts Copy's 24 dp icon where a row's trailing icon sits.
        ft.Container(
            ft.Row(
                [
                    ft.Container(
                        value(NETWORK, wifi.network, f"{SCREEN}.network"),
                        expand=True,
                    ),
                    named(f"{SCREEN}.copy_network", copy),
                ],
                spacing=4,
            ),
            padding=ft.Padding.only(left=GUTTER, top=8, right=12, bottom=8),
        ),
        ft.Container(
            ft.Column(
                [
                    value(PASSWORD, wifi.password, f"{SCREEN}.password"),
                    named(f"{SCREEN}.copy_password", button),
                ],
                spacing=16,
                horizontal_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding.symmetric(horizontal=GUTTER, vertical=8),
        ),
    ]


def value(label: str, text: str, identifier: str) -> ft.Control:
    """Return a value under its label, read as one phrase: "Network, PyConUS26".

    The value is selectable, so it can also be copied by hand, in ``TITLE_LARGE`` and a
    monospace font. For screen readers it is one node that says the label, then the
    value: a selectable text is otherwise a read-only text field of its own, away from
    its label, and copying is what the Copy buttons are for.

    Args:
        label: What the value is: "Network".
        text: The value, exactly as it is typed.
        identifier: Its semantics identifier, ``wifi.<value>``.
    """
    return ft.Semantics(
        identifier=identifier,
        label=f"{label}, {text}",
        container=True,
        exclude_semantics=True,  # the label says both texts
        content=ft.Column(
            [
                ft.Text(
                    label,
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    text,
                    theme_style=ft.TextThemeStyle.TITLE_LARGE,
                    style=VALUE_STYLE,
                    color=ft.Colors.ON_SURFACE,
                    selectable=True,
                ),
            ],
            spacing=4,
        ),
    )
