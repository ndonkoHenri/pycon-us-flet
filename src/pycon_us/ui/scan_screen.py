"""The shared scan screen every staff tool renders (LEAD-01, LEAD-09, LEAD-14; D-65).

A tool gives `ScanScreen` its title, an async `on_badge(badge) -> ScanResult` and,
optionally, a context line, buttons and a clearing rule; the screen does the rest, so
the tools only return data. The layout and every scenario are ux.md §7.2.

- **Input:** the full `code:validator` payload (`parse_badge`), from the camera, the
  field or a HID scanner's keys followed by Enter. Text that is not a badge is answered
  "Not a badge code", and "Edit code" gives it back to be corrected (D-473).
- **Concurrency:** one `on_badge` runs at a time. A submit while it runs, while
  scanning is paused (the queue sheet is open, or the tool gives `paused`) or for a code
  accepted in the last 4 s is dropped with its text, never queued (D-471).
- **Lifecycle:** the field keeps the focus, and gets it back after a pause and when
  Back pops a page pushed over the screen (F274, D-438); the screen stays awake while
  mounted; a result that arrives after the screen is left, or while another View is on
  top, is dropped, so it never buzzes or speaks over another page.
- **Results:** the panel shows each result with its haptics and announcement
  (`ui/scan_feedback.py`); `result_actions` and `result_note` belong to the result shown;
  a result the tool gets outside `on_badge` is handed over as `posted` (a `Posted`,
  `ui/scan_result.py`) and shown once per serial; `clear_after` and `clear_in_background`
  clear it (`ui/scan_clear.py`).

The camera area is `ui/scan_camera.py`, the sync chip and queue sheet `ui/sync_chip.py`.
"""

from collections.abc import Awaitable, Callable
from dataclasses import replace
from time import monotonic
from typing import cast

import flet as ft

from pycon_us import capabilities
from pycon_us.account import use_account
from pycon_us.core.badges import (
    NOT_A_BADGE,
    Badge,
    Cooldown,
    ScanResult,
    entry_title,
    parse_badge,
)
from pycon_us.core.staff_tools import ToolKey, may_open
from pycon_us.layout import use_layout
from pycon_us.locations import is_top_view
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.staff import use_staff
from pycon_us.theme import use_tokens
from pycon_us.ui.actions import padded
from pycon_us.ui.fields import use_field_query
from pycon_us.ui.hooks import use_mounted
from pycon_us.ui.queue_sheet import use_queue_sheet
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.scan_camera import CameraUnavailable
from pycon_us.ui.scan_clear import use_clear_after, use_on_background
from pycon_us.ui.scan_feedback import announce_result, buzz, use_wake_lock
from pycon_us.ui.scan_result import (
    DIM_AFTER,
    Posted,
    Shown,
    age_line,
    result_panel,
    spoken,
)
from pycon_us.ui.scrolling import FULL_LIST_EXTENT
from pycon_us.ui.semantics import named
from pycon_us.ui.states import EmptyState
from pycon_us.ui.sync_chip import SyncChip
from pycon_us.ui.tool_controls import tool_button
from pycon_us.ui.widths import LIST, sides, use_margin

type OnBadge = Callable[[Badge], Awaitable[ScanResult]]
"""A tool's handler: what a parsed, accepted badge comes to."""

type ResultActions = Callable[[Shown], list[ft.Control]]
"""A tool's buttons for the result on the panel ("Add note"), gone with it."""

type ResultNote = Callable[[Shown], ft.Control | None]
"""A tool's line under the panel for the result on it (CoC's revealed email)."""

ENTRY_LABEL = "Badge code"
KEYBOARD_TOOLTIP = "Type a badge code"
EDIT_CODE = "Edit code"
"""The button under "Not a badge code" that puts its text back in the field (D-473)."""
PAUSED_SHEET = "Paused while the sheet is open"
"""The field's line while the queue sheet is open: a submit is dropped (#724)."""

SCAN_AGAIN = "Scanned too soon: scan that badge again"
"""The field's line after a submit dropped while the handler ran, its one sign (D-471)."""

NOT_AVAILABLE = "Not available for this account"
NOT_AVAILABLE_BODY = "Sign in on More with an account that has access to it."
"""A tool screen's state for an account its rule refuses (architecture §12.4)."""

SWITCH_MS = 200
"""The result panel's cross-fade, 0 under reduced motion (D-173)."""


def clock() -> float:
    """Return the time the cooldown and the result's age count in: never goes back."""
    return monotonic()


@ft.component
def ScanScreen(
    *,
    title: str,
    source: str,
    on_badge: OnBadge,
    context: str | ft.Control | None = None,
    actions: list[ft.Control] | None = None,
    paused: str | None = None,
    result_actions: ResultActions | None = None,
    result_note: ResultNote | None = None,
    posted: Posted | None = None,
    clear_after: float | None = None,
    clear_in_background: bool = False,
) -> ft.Control:
    """Return a staff tool's scan screen (ux.md §7.2).

    Args:
        title: The tool's name, the app bar's title.
        source: The tool's `__name__`, for View source (D-461).
        on_badge: Turns a badge into the result to show; awaited one at a time.
        context: A line under the bar, e.g. "Decorators, Wed 9:00 AM", or a control
            in its place: the Lead scanner's "For: Example Corp" chip (LEAD-06). At
            large text it follows the result and its buttons (D-475).
        actions: The tool's own buttons, under the field ("Add note"); at large text
            under the result, which follows the field (D-475).
        paused: Why scanning is paused, under the field ("Paused while the note
            is open"), while one of the tool's dialogs or sheets is open: submits
            are dropped with their text (D-471). None scans.
        result_actions: The tool's buttons for the result shown, under the field
            before `actions`: the Lead scanner's "Add note" (#742). They belong to
            that result, so the next one (even "Not a badge code") replaces them. The
            screen adds "Edit code" before them to that last result (D-473).
        result_note: The tool's line for the result shown, under the panel and
            outside its live region, so it is said only when focused (#762).
        posted: The latest result the tool got outside `on_badge` (the CoC name
            search's record), shown once per serial as a scan's would be.
        clear_after: Seconds after it shows that a result clears, or None to keep
            it until the next (`ui/scan_clear.py`).
        clear_in_background: Clear the result when the app goes to the background.
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    prefs = use_prefs()
    staff = use_staff()
    tokens = use_tokens()
    margin = use_margin(LIST)  # its width class (D-305)
    layout = use_layout()
    query = use_field_query()
    sheet = use_queue_sheet()  # the signed-in account's rows only (D-420)
    use_wake_lock()
    cooldown = ft.use_memo(Cooldown, [])  # one per screen: its codes' last accepts
    busy = ft.use_ref(False)  # the handler runs: the single flight
    too_soon, set_too_soon = ft.use_state(False)  # the last submit was dropped for it
    shown, set_shown = ft.use_state(cast(Shown | None, None))
    count = ft.use_ref(0)  # the results so far: no serial comes twice, even cleared
    why_paused = PAUSED_SHEET if sheet.is_open else paused
    # Scanning goes on from the field: no pause, and no View pushed on top (D-438).
    ready = why_paused is None and query.focusable
    was_held = ft.use_ref(False)
    mounted = use_mounted()  # a late result is then dropped

    @report_errors
    async def resume() -> None:
        resumed = was_held.current and ready
        was_held.current = not ready
        if resumed:  # a sheet or dialog closed, or Back came: scan from the field
            await query.focus()

    ft.use_effect(resume, [ready])

    @report_errors
    def drop(serial: int | None = None) -> None:
        """Drop the result shown from state: `serial`'s only, or any (#762)."""
        set_shown(lambda last: None if last and serial in (None, last.serial) else last)

    # A refused entry holds no one's details, and its "Edit code" must outlast the
    # tool's clear, or a typist has that long to reach it (D-473).
    clears_in = None if shown and shown.result.entry else clear_after
    use_clear_after(shown.serial if shown else 0, clears_in, drop)
    use_on_background(drop if clear_in_background else None)

    @report_errors
    async def show(result: ScanResult) -> None:
        if clear_in_background and svc.background.is_set():
            return  # a reply that lands in the background would undo its clear (#762)
        serial = count.current = (count.current or 0) + 1
        set_shown(Shown(result, clock(), serial))
        await buzz(svc.haptics, result.outcome)
        if prefs.announcements:  # iOS; elsewhere the panel's live region says it
            await announce_result(svc.semantics, result)

    @report_errors
    async def show_posted() -> None:
        result = posted.take() if posted is not None else None
        if result and mounted.current and is_top_view(page.route, view_path):
            await show(result)

    ft.use_effect(show_posted, [posted])

    @report_errors
    async def submit(e: ft.Event[ft.TextField]) -> None:
        if why_paused is not None or busy.current:
            set_too_soon(why_paused is None)  # a pause's line says why already
            await query.clear()  # the next scan never joins this text (D-471)
            return
        set_too_soon(False)
        # Held until the result is felt and said, so results reach staff in order.
        busy.current = True
        try:
            raw = e.data if isinstance(e.data, str) else e.control.value or ""
            badge = parse_badge(raw)
            await query.clear()  # empties the field and puts the focus back in it
            if badge is None:  # what was read goes to the panel, not kept in the field
                text = raw.strip()
                await show(replace(NOT_A_BADGE, title=entry_title(text), entry=text))
                return
            if not cooldown.accept(badge.code, clock()):
                return  # the same code again within 4 s: a held badge
            result = await on_badge(badge)
            if mounted.current and is_top_view(page.route, view_path):
                await show(result)
        finally:
            busy.current = False

    @report_errors
    async def edit(_: ft.Event[ft.FilledTonalButton]) -> None:
        if shown is not None:
            drop(shown.serial)  # the text is back in the field: nothing left to edit
            await query.put(shown.result.entry)

    for_result = (
        result_actions(shown)
        if result_actions is not None and shown is not None
        else []
    )
    if shown and shown.result.entry:  # an empty entry has no text to give back (D-473)
        for_result.insert(
            0, tool_button("scan.edit", EDIT_CODE, ft.Icons.EDIT_OUTLINED, edit)
        )
    note = result_note(shown) if result_note is not None and shown else None
    chip = SyncChip(
        staff, tokens=tokens, on_click=sheet.open, large_text=prefs.time_above
    )
    # At large text the chip leaves the bar for the body, where its words wrap and
    # the title keeps its room (#752).
    status: list[ft.Control] = [padded(chip)] if prefs.time_above else []
    if isinstance(context, ft.Control):
        status.append(padded(context))
    elif context:
        status.append(
            padded(
                ft.Text(
                    context,
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            )
        )
    if not capabilities.SCANNER:  # the E1 preview takes this place (#726)
        status.append(padded(CameraUnavailable()))
    # Keyed, or the body's children are matched by position: when the text size flips
    # the order while the screen is open, the field would be rebuilt and lose its
    # focus, and a HID scanner's next scan would go nowhere.
    panel = padded(ResultPanel(shown=shown, clear_after=clears_in))
    panel.key = "scan.panel"
    field = padded(
        named(
            "scan.entry",
            ft.TextField(
                ref=query.ref,
                value=query.value,
                on_change=query.changed,
                on_submit=submit,
                label=ENTRY_LABEL,
                autofocus=True,  # a HID scanner types into it from the start
                autocorrect=False,
                enable_suggestions=False,
                capitalization=ft.TextCapitalization.NONE,
                # Android's Enter then keeps the focus and the keyboard; iOS's
                # still takes the focus, so the refocus calls stay (F274, U254).
                text_input_action=ft.TextInputAction.UNSPECIFIED,
                # Never off, unlike a SearchField's (D-330): Flutter applies it
                # a frame after the patch, so the focus asked for on Back would
                # come first and be dropped (F288, D-438).
                helper=why_paused or (ft.Text(SCAN_AGAIN) if too_soon else None),
            ),
        )
    )
    field.key = "scan.field"
    result_note_line = [padded(note)] if note is not None else []
    # One wrapping row, not a line for each: after a result with the keyboard up, a column
    # of buttons ran past the keyboard's edge and "Find by name" was cut in half (#1015).
    # They share a line while their words fit, and wrap at large text.
    tools = [*for_result, *(actions or ())]
    buttons = (
        [padded(ft.Row(tools, wrap=True, spacing=8, run_spacing=8, key="scan.buttons"))]
        if tools
        else []
    )
    if prefs.time_above or layout.short:
        # The field and the result first (D-475): the keyboard scrolls a focused field
        # into view, and below the chip, the context and the camera note it sat four
        # screens down, so the screen opened at its end and the result's heading was
        # above the bar (#955). The rest follows, a scroll away. A phone in landscape
        # too (D-501): the keyboard leaves room for the field alone, and a result that
        # grew above it pushed it under the keyboard, where Android left it (#1120).
        body = [field, panel, *result_note_line, *buttons, *status]
    else:
        body = [*status, panel, *result_note_line, field, *buttons]
    return AppScaffold(
        title=title,
        source=source,
        actions=[
            *([] if prefs.time_above else [chip]),
            named(  # one node, named by its tooltip (D-234)
                "scan.keyboard",
                ft.IconButton(
                    ft.Icons.KEYBOARD, tooltip=KEYBOARD_TOOLTIP, on_click=query.focus
                ),
            ),
        ],
        # The field must always be built, or autofocus and every focus() find nothing
        # to focus: at the largest text the panels push it past a lazy list's cache,
        # and the keyboard button then timed out with a raw error (F32, #828).
        body=ft.ListView(
            body,
            expand=True,
            padding=sides(margin, top=8, bottom=16),
            cache_extent=FULL_LIST_EXTENT,
        ),
    )


@ft.component
def ResultPanel(*, shown: Shown | None, clear_after: float | None = None) -> ft.Control:
    """Return the result panel and, under it, how old the result is.

    The panel is one live region read as the result's words, so TalkBack says each
    new result; where the platform takes announcements (iOS) the screen announces it
    instead and the panel is no live region, so it is said once (D-420); the age under
    it ticks every second outside it, so only the result is said. Its own component,
    so the tick re-renders the panel alone. A result dims after `DIM_AFTER` s and
    stays until the next, or until it clears. "Ready to scan" is no live region, so a
    clear is not said (#762).

    Args:
        shown: The result on the panel, or None before the first scan or after a clear.
        clear_after: The seconds a result stays, which the age line counts down.
    """
    svc = use_services()
    prefs = use_prefs()
    tokens = use_tokens()
    now, set_now = ft.use_state(clock)
    at = shown.at if shown is not None else None

    @report_errors
    async def tick() -> None:
        if at is not None:
            await svc.run_every(1, lambda: set_now(clock()))

    ft.use_effect(tick, [at])
    age = max(now - at, 0) if at is not None else 0
    result = shown.result if shown is not None else None
    serial = shown.serial if shown is not None else 0
    panel: list[ft.Control] = [
        ft.Semantics(
            identifier="scan.result",
            container=True,
            live_region=not prefs.announcements and shown is not None,
            label=spoken(result, serial),
            exclude_semantics=True,  # the card's texts are its label, once
            content=ft.AnimatedSwitcher(
                result_panel(
                    result,
                    key=str(serial),
                    tokens=tokens,
                    dimmed=age >= DIM_AFTER,
                    large_text=prefs.time_above,
                ),
                duration=prefs.motion_ms(SWITCH_MS),
                # The outgoing card goes at once: a switcher keeps both in a stack
                # while it fades one out, and a short "Ready to scan" showed through
                # the taller result, chips and all (#1014).
                reverse_duration=0,
            ),
        )
    ]
    if shown is not None:
        panel.append(age_line(age, clear_after))
    return ft.Column(panel, spacing=4, tight=True)


def use_tool_allowed(tool: ToolKey) -> bool:
    """Say whether a staff tool may open now: each screen's gate (architecture §12.4).

    It takes a mock URL (D-51), a signed-in account and the tool's rule; else the
    screen shows `NotAvailable`, so a deep link cannot bypass it.

    Args:
        tool: The tool whose rule applies.
    """
    prefs = use_prefs()
    account = use_account()
    return (
        prefs.private_api_enabled
        and account.signed_in
        and may_open(tool, account.role_flags)
    )


@ft.component
def NotAvailable(*, title: str, source: str) -> ft.Control:
    """Return a tool screen for an account its rule refuses (architecture §12.4).

    Signed out, without the tool's flag, or with no mock URL (D-51): a deep link to
    the tool lands here, never on its scan screen (P3 exit criterion 3).

    Args:
        title: The tool's name, the app bar's title.
        source: The tool's `__name__`, for View source (D-461).
    """
    margin = use_margin(LIST)  # its width class (D-305)
    return AppScaffold(
        title=title,
        source=source,
        body=ft.ListView(
            [
                EmptyState(
                    NOT_AVAILABLE,
                    icon=ft.Icons.LOCK_OUTLINE,
                    body=NOT_AVAILABLE_BODY,
                    identifier="staff.not_available",
                )
            ],
            expand=True,
            padding=sides(margin),
        ),
    )
