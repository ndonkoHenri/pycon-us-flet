"""The Developer screen's Mock API section: the mock's base URL and its check (DEV-01, D-51).

``MockApiSection`` is the field that turns the private-API features on (D-73's "mock API
base URL"): **Save** checks the URL (``parse_mock_api_url()``), builds ``Services.api``
on it and keeps it in ``pycon.dev`` (``Prefs.mock_api_url``); **Clear** turns them off
again, with no client left. While a URL is saved, **Check mock connection** sends one
signed call and says whether the mock answered (``check_connection()``), so a device
reaches the mock before any sign-in screen exists (#668). Every result is said in place,
under the buttons (D-29, D-210). Apart from ``developer.py`` so that the screen stays
under about 400 lines (D-66), as the Data section is.
"""

from typing import Any

import flet as ft

from pycon_us.prefs import DEV_MOCK_API_URL, Prefs, use_prefs
from pycon_us.screens.developer_ui import option_field, said
from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.private_api import check_connection, parse_mock_api_url
from pycon_us.theme import use_tokens
from pycon_us.ui.actions import NO_OUTCOME, Outcome, action_row, outcome_line, padded
from pycon_us.ui.buttons import LABEL_PADDING
from pycon_us.ui.semantics import named

SAVE_IN_SIGHT = 304
"""How far below its text the URL field keeps in sight when it takes the focus, in dp:
its helper, the Clear and Save row and the outcome line, sized as the feed URL's
``developer.APPLY_IN_SIGHT`` is, for large text (#108)."""

HELPER = (
    "Android emulator: http://10.0.2.2:8000. iOS simulator: http://localhost:8000. "
    "A phone: the address the mock prints. Empty turns sign-in and the staff tools off."
)
"""The field's helper: the base URL for each kind of device (development.md §6)."""


def with_mock_api_url(dev: dict[str, Any], url: str | None) -> dict[str, Any]:
    """Return ``dev`` with the mock API URL set, or removed for None; the rest is kept.

    Args:
        dev: The current ``Prefs.dev``.
        url: The mock's base URL (``parse_mock_api_url()``), or None.
    """
    options = {k: v for k, v in dev.items() if k != DEV_MOCK_API_URL}
    if url is not None:
        options[DEV_MOCK_API_URL] = url
    return options


async def use_url(svc: Services, prefs: Prefs, url: str | None) -> Outcome:
    """Put a mock API URL into effect, or none, keep it, and say what was done.

    The client is rebuilt before the save, so the re-render the save causes finds it
    in place.

    Args:
        svc: The session's services: ``private_api`` and the storage.
        prefs: The ``Prefs`` store that keeps the URL in ``pycon.dev``.
        url: The mock's base URL (``parse_mock_api_url()``), or None to turn it off.

    Returns:
        The outcome line's state.
    """
    await svc.private_api.connect(url, svc.year.conference.year)
    saved = await prefs.save(svc.storage, dev=with_mock_api_url(prefs.dev, url))
    done = (
        "Saved: sign-in and the staff tools use the mock at this address."
        if url
        else "Cleared: sign-in and the staff tools are off."
    )
    return said(done, saved)


@ft.component
def MockApiSection() -> ft.Control:
    """The Mock API section: the URL field, Clear and Save, the check and the outcome.

    A component of its own: its field, its check in progress and its outcome are its
    own state, and it re-renders with ``Prefs``, whose URL shows or hides the check.
    """
    svc = use_services()
    prefs = use_prefs()
    tokens = use_tokens()
    # Controlled (D-157), seeded from what is in effect.
    text, set_text = ft.use_state(lambda: prefs.mock_api_url or "")
    error, set_error = ft.use_state("")  # "" while the field is fine
    checking, set_checking = ft.use_state(False)
    outcome, set_outcome = ft.use_state(NO_OUTCOME)

    @report_errors
    def edit(e: ft.Event[ft.TextField]) -> None:
        set_text(e.control.value)
        set_error("")
        set_outcome(NO_OUTCOME)

    @report_errors
    async def save() -> None:
        try:
            url = parse_mock_api_url(text)
        except ValueError as problem:
            set_error(str(problem))
            set_outcome(NO_OUTCOME)
            return
        set_outcome(await use_url(svc, prefs, url))

    @report_errors
    async def clear() -> None:
        set_text("")
        set_error("")
        set_outcome(await use_url(svc, prefs, None))

    @report_errors
    async def check() -> None:
        client = svc.api
        if client is None:  # cleared meanwhile
            return
        set_checking(True)
        set_outcome(NO_OUTCOME)
        try:
            set_outcome(await check_connection(client))
        finally:
            set_checking(False)

    return ft.Column(
        [
            padded(
                ft.Text(
                    "Sign-in and the staff tools only ever talk to the local mock "
                    "server, never to the PSF's. They show once its address is saved.",
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            ),
            option_field(
                "developer.mock_api_url",
                text,
                label="Mock API base URL",
                hint="http://localhost:8000",
                helper=HELPER,
                error=error,
                keyboard=ft.KeyboardType.URL,
                on_change=edit,
                reveal_below=SAVE_IN_SIGHT,
            ),
            padded(
                ft.Row(
                    [
                        named(
                            "developer.mock_api_clear",
                            ft.OutlinedButton(
                                "Clear",
                                on_click=clear,
                                style=ft.ButtonStyle(padding=LABEL_PADDING),
                            ),
                        ),
                        named(
                            "developer.mock_api_save",
                            ft.FilledButton(
                                "Save",
                                on_click=save,
                                style=ft.ButtonStyle(padding=LABEL_PADDING),
                                elevation=0,  # as Apply (D-232)
                            ),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=8,
                    wrap=True,
                )
            ),
            *(
                [check_row(prefs.mock_api_url, checking=checking, on_click=check)]
                if prefs.mock_api_url
                else []
            ),
            ft.Semantics(
                identifier="developer.mock_api_outcome",
                live_region=True,
                visible=bool(outcome[0]),
                content=outcome_line(*outcome, tokens=tokens),
            ),
        ],
        spacing=0,
    )


def check_row(
    url: str, *, checking: bool, on_click: ft.ControlEventHandler[ft.ListTile]
) -> ft.Control:
    """Return Check mock connection: the address it checks, or that it is checking.

    Args:
        url: The mock's base URL in effect.
        checking: A check is running: the row is disabled, with a small ring.
        on_click: Runs the check.
    """
    return action_row(
        "developer.mock_api_check",
        ft.Icons.LAN_OUTLINED,
        "Check mock connection",
        "Checking…" if checking else url,
        on_click,
        disabled=checking,
        # Something moves while it runs (ux.md §4), the words say what.
        trailing=(
            ft.ProgressRing(width=20, height=20, stroke_width=2) if checking else None
        ),
    )
