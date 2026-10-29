"""The shared scan screen every staff tool renders (LEAD-01, LEAD-09, LEAD-14; D-65).

ux.md §7.2: the app bar's sync chip and ``KEYBOARD`` button, the camera area, the
result panel and manual entry, then the tool's own actions. A tool gives
``ScanScreen`` its title, a context line (or a control there, as the Lead scanner's
sponsor chip) and an async ``on_badge(badge) -> ScanResult``, and may add buttons
for the result shown (``result_actions``, the Lead scanner's "Add note"): the
screen parses what was entered (``parse_badge``), applies the per-code cooldown,
awaits one handler at a time and shows what it returned, so the tools only return
data.

**Manual entry** takes the full ``code:validator`` payload, which USB and Bluetooth HID
scanners also type before Enter. A submit clears the field and puts the focus back in
it (every submit drops it, and Android's keyboard with it: F274, U254), so a hardware
scanner scans continuously; a code accepted in the last 4 s is cleared
without a word (a held code); a second submit while the handler runs is dropped, its
text kept; text that is not a badge says "Not a badge code" and stays for correction.
A handler can take a few seconds (the Lead scanner waits for its send, D-426): a
result that comes after the screen is left, or while another View is on top of it,
is dropped, so it never buzzes or speaks over another page.

**Beyond the panel** (#724, D-420): each result gives its haptics and, on iOS, an
announcement (``ui/scan_feedback.py``); the screen stays awake while mounted and in
the foreground. The **sync chip** (``ui/sync_chip.py``) opens the queue sheet with the
signed-in account's rows (``use_queue_sheet()``); at large text it heads the body
rather than the bar, so its words wrap (#752). Scanning **pauses** while the sheet
is open, or while the tool says why (``paused``, its dialogs and sheets): a submit is
dropped, its text kept, and the field says why; when the pause ends the focus goes
back to the field. It goes back there too when Back pops a page pushed over the
screen (the leads list, a picker), so a HID scanner's next scan lands in it (#775,
D-438).

**The camera** is E1, absent at the Flet pin (``capabilities.SCANNER`` is False): the
area says so and manual entry is primary; #726 brings the preview.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic

import flet as ft

from pycon_us import capabilities
from pycon_us.core.badges import NOT_A_BADGE, Badge, Cooldown, ScanResult, parse_badge
from pycon_us.locations import is_top_view
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.staff import use_staff
from pycon_us.theme import use_tokens
from pycon_us.theme_hc import hc_border
from pycon_us.ui.actions import padded
from pycon_us.ui.fields import use_field_query
from pycon_us.ui.queue_sheet import use_queue_sheet
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.scan_feedback import announce, buzz, use_wake_lock
from pycon_us.ui.scan_result import DIM_AFTER, age_line, result_panel, spoken
from pycon_us.ui.semantics import named
from pycon_us.ui.states import EmptyState
from pycon_us.ui.sync_chip import SyncChip
from pycon_us.ui.widths import LIST, sides, use_margin

type OnBadge = Callable[[Badge], Awaitable[ScanResult]]
"""A tool's handler: what a parsed, accepted badge comes to."""

type ResultActions = Callable[[ScanResult], list[ft.Control]]
"""A tool's buttons for the result on the panel ("Add note"), gone with it."""

ENTRY_LABEL = "Badge code"
KEYBOARD_TOOLTIP = "Type a badge code"
CAMERA_UNAVAILABLE = "Camera scanning isn't available in this build."
PAUSED_SHEET = "Paused while the sheet is open"
"""The field's line while the queue sheet is open: a submit is dropped (#724)."""

NOT_AVAILABLE = "Not available for this account"
NOT_AVAILABLE_BODY = "Sign in on More with an account that has access to it."
"""A tool screen's state for an account its rule refuses (architecture §12.4)."""

SWITCH_MS = 200
"""The result panel's cross-fade, 0 under reduced motion (D-173)."""


def clock() -> float:
    """Return the time the cooldown and the result's age count in: never goes back."""
    return monotonic()


@dataclass(frozen=True)
class Shown:
    """The result on the panel.

    Attributes:
        result: What the handler, or the parse, returned.
        at: When it came, in ``clock()`` seconds.
        serial: Counts the results, so each one is a new card, even an equal one.
    """

    result: ScanResult
    at: float
    serial: int


@ft.component
def ScanScreen(
    *,
    title: str,
    on_badge: OnBadge,
    context: str | ft.Control | None = None,
    actions: list[ft.Control] | None = None,
    paused: str | None = None,
    result_actions: ResultActions | None = None,
) -> ft.Control:
    """Return a staff tool's scan screen (ux.md §7.2).

    Args:
        title: The tool's name, the app bar's title.
        on_badge: Turns a badge into the result to show; awaited one at a time.
        context: A line under the bar, e.g. "Decorators, Wed 9:00 AM", or a control
            in its place: the Lead scanner's "For: Example Corp" chip (LEAD-06).
        actions: The tool's own buttons, under the field ("Add note").
        paused: Why scanning is paused, under the field ("Paused while the note
            is open"), while one of the tool's dialogs or sheets is open: submits
            are dropped, their text kept. None scans.
        result_actions: The tool's buttons for the result shown, under the field
            before ``actions``: the Lead scanner's "Add note" (#742). They belong to
            that result, so the next one (even "Not a badge code") replaces them.
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    prefs = use_prefs()
    staff = use_staff()
    tokens = use_tokens()
    margin = use_margin(LIST)  # its width class (D-305)
    query = use_field_query()
    sheet = use_queue_sheet()  # the signed-in account's rows only (D-420)
    use_wake_lock()
    cooldown = ft.use_memo(Cooldown, [])  # one per screen: its codes' last accepts
    busy = ft.use_ref(False)  # the handler runs: the single flight
    shown, set_shown = ft.use_state(no_result)
    why_paused = PAUSED_SHEET if sheet.is_open else paused
    # Scanning goes on from the field: no pause, and no View pushed on top (D-438).
    ready = why_paused is None and query.focusable
    was_held = ft.use_ref(False)
    mounted = ft.use_ref(True)  # cleared on unmount: a late result is then dropped

    @report_errors
    def unmount() -> None:
        """Mark the screen gone, so a handler still running stays quiet."""
        mounted.current = False

    ft.use_effect(lambda: None, [], cleanup=unmount)

    @report_errors
    async def resume() -> None:
        resumed = was_held.current and ready
        was_held.current = not ready
        if resumed:  # a sheet or dialog closed, or Back came: scan from the field
            await query.focus()

    ft.use_effect(resume, [ready])

    @report_errors
    async def show(result: ScanResult) -> None:
        at = clock()
        set_shown(lambda last: Shown(result, at, last.serial + 1 if last else 1))
        await buzz(svc.haptics, result.outcome)
        if prefs.announcements:  # iOS; elsewhere the panel's live region says it
            await announce(svc.semantics, result)

    @report_errors
    async def submit(e: ft.Event[ft.TextField]) -> None:
        if why_paused is not None or busy.current:
            return
        # Held until the result is felt and said, so results reach staff in order.
        busy.current = True
        try:
            raw = e.data if isinstance(e.data, str) else e.control.value or ""
            badge = parse_badge(raw)
            if badge is None:
                await show(NOT_A_BADGE)
                await query.focus()  # Enter took it out (F274); the text stays
                return
            await query.clear()  # empties the field and puts the focus back in it
            if not cooldown.accept(badge.code, clock()):
                return  # the same code again within 4 s: a held badge
            result = await on_badge(badge)
            if mounted.current and is_top_view(page.route, view_path):
                await show(result)
        finally:
            busy.current = False

    for_result = (
        result_actions(shown.result)
        if result_actions is not None and shown is not None
        else []
    )
    chip = SyncChip(
        staff, tokens=tokens, on_click=sheet.open, large_text=prefs.time_above
    )
    # At large text the chip leaves the bar for the body, where its words wrap and
    # the title keeps its room (#752).
    body: list[ft.Control] = [padded(chip)] if prefs.time_above else []
    if isinstance(context, ft.Control):
        body.append(padded(context))
    elif context:
        body.append(
            padded(
                ft.Text(
                    context,
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            )
        )
    if not capabilities.SCANNER:  # the E1 preview takes this place (#726)
        body.append(padded(CameraUnavailable()))
    body += [
        padded(ResultPanel(shown=shown)),
        padded(
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
                    # Never off, unlike a SearchField's (D-330): Flutter applies it
                    # a frame after the patch, so the focus asked for on Back would
                    # come first and be dropped (F288, D-438).
                    helper=why_paused,
                ),
            )
        ),
        *(padded(action) for action in for_result),
        *(padded(action) for action in actions or ()),
    ]
    return AppScaffold(
        title=title,
        actions=[
            *([] if prefs.time_above else [chip]),
            named(  # one node, named by its tooltip (D-234)
                "scan.keyboard",
                ft.IconButton(
                    ft.Icons.KEYBOARD, tooltip=KEYBOARD_TOOLTIP, on_click=query.focus
                ),
            ),
        ],
        body=ft.ListView(body, expand=True, padding=sides(margin, top=8, bottom=16)),
    )


def no_result() -> Shown | None:
    """Return None: nothing scanned yet, the screen's first state (a typed default)."""
    return None


@ft.component
def ResultPanel(*, shown: Shown | None) -> ft.Control:
    """Return the result panel and, under it, how old the result is.

    The panel is one live region read as the result's words, so TalkBack says each
    new result; where the platform takes announcements (iOS) the screen announces it
    instead and the panel is no live region, so it is said once (D-420); the age under it ticks every second outside it, so
    only the result is said. Its own component, so the tick re-renders the panel
    alone. A result dims after ``DIM_AFTER`` s and stays until the next.

    Args:
        shown: The result on the panel, or None before the first scan.
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
            live_region=not prefs.announcements,
            label=spoken(result, serial),
            exclude_semantics=True,  # the card's texts are its label, once
            content=ft.AnimatedSwitcher(
                result_panel(
                    result,
                    key=str(serial),
                    tokens=tokens,
                    dimmed=age >= DIM_AFTER,
                ),
                duration=prefs.motion_ms(SWITCH_MS),
                reverse_duration=prefs.motion_ms(SWITCH_MS),
            ),
        )
    ]
    if shown is not None:
        panel.append(age_line(age))
    return ft.Column(panel, spacing=4, tight=True)


@ft.component
def CameraUnavailable() -> ft.Control:
    """Return the camera area's interim: the build has no camera scanner (E1, D-63)."""
    tokens = use_tokens()
    return ft.Container(
        ft.Row(
            [
                ft.Icon(
                    ft.Icons.NO_PHOTOGRAPHY_OUTLINED,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    apply_text_scaling=True,
                ),
                ft.Semantics(
                    identifier="scan.camera_unavailable",
                    container=True,
                    content=ft.Text(
                        CAMERA_UNAVAILABLE,
                        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    expand=True,
                ),
            ],
            spacing=12,
        ),
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        padding=16,
        border_radius=12,
        border=hc_border(tokens.high_contrast),
    )


@ft.component
def NotAvailable(*, title: str) -> ft.Control:
    """Return a tool screen for an account its rule refuses (architecture §12.4).

    Signed out, without the tool's flag, or with no mock URL (D-51): a deep link to
    the tool lands here, never on its scan screen (P3 exit criterion 3).

    Args:
        title: The tool's name, the app bar's title.
    """
    margin = use_margin(LIST)  # its width class (D-305)
    return AppScaffold(
        title=title,
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
