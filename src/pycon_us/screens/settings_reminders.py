"""Settings' Reminders section: the live controls with E3, else D-60's interim (NOTIF-01).

**Live** (``RemindersSection``, a build with E3: ``Services.reminders``; ux.md §6.9,
D-401): a level-2 heading; a card while notifications need the user (``card_for()``):
"Allow notifications" while the OS can still ask, "Open settings" once only the system
settings can change it, and on Android, while session reminders are on, the Alarms &
reminders card (D-221); the "Remind me before sessions in My schedule" switch, with
the 5 · 10 · 15 min ``SegmentedButton`` only while it is on; and the three conference
moments. Each row is a ``ListTile(toggle_inputs=True)`` that saves silently: the
scheduler re-plans on any change of ``Prefs.reminders`` (D-389), and only a failed write
says so (D-120). Turning the switch on while the primer was never accepted shows it
(``reminder_primer.ask()``, D-61, D-275). The cards follow the OS: its answers are read
when the section mounts, after a change of the settings, after a card's button, and
whenever the ``Scheduler`` reads a change on resume or before an apply
(``Scheduler.watch()``).

**Interim** (``interim_section()``, without E3, always in the companion app, D-63): a
level-2 heading and one sentence that says reminders aren't available in this build and
what covers for them, with no switch that would do nothing. On iOS the sentence adds
that calendar exports carry an alarm; Android's calendar import drops it (D-272).
"""

import dataclasses
from collections.abc import Callable
from typing import Any, Literal, cast

import flet as ft

from pycon_us.prefs import Prefs, use_prefs
from pycon_us.reminder_settings import SESSION_LEADS, ReminderSettings
from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.reminders import Access
from pycon_us.ui.buttons import LABEL_PADDING
from pycon_us.ui.reminder_primer import PRIMER_LEAD, ask
from pycon_us.ui.scaffold import SectionHeader
from pycon_us.ui.semantics import named
from pycon_us.ui.snack_bars import say_if_unsaved

SCREEN = "settings.reminders"
"""The section's prefix in the identifiers (decisions §M)."""

NOT_AVAILABLE = (
    "Reminders aren't available in this build. Your next session appears on Now."
)
"""The interim's sentence on Android, whose calendar import drops the alarm (D-272)."""

WITH_ALARM = f"{NOT_AVAILABLE[:-1]}, and calendar exports include an alarm."
"""The interim's sentence on iOS, where an exported session keeps its alarm (D-60)."""

SESSIONS = "Remind me before sessions in My schedule"
"""The session reminders' switch (ux.md §6.9)."""

MOMENTS = "Conference moments"
"""The heading over the moments' switches."""

MOMENT_ROWS: tuple[tuple[str, str, ft.IconData], ...] = (
    ("keynote", "Keynotes and panels", ft.Icons.CAMPAIGN_OUTLINED),
    ("lightning", "Lightning-talk sign-ups", ft.Icons.BOLT_OUTLINED),
    ("open_space", "Open-space sign-ups", ft.Icons.FORUM_OUTLINED),
)
"""Each moment's ``ReminderSettings`` field, title and decorative icon, in order."""

ASK_TEXT = "Reminders show only once you allow notifications."
ASK_ACTION = "Allow notifications"
BLOCKED_TEXT = "Notifications are off in system settings."
EXACT_TEXT = (
    "For more timely reminders, allow Alarms & reminders. Without this permission, "
    "reminders may arrive late, including after a session starts."
)
OPEN_SETTINGS = "Open settings"

type Card = Literal["ask", "blocked", "exact"]
"""The card the section shows: notifications askable, blocked, or inexact alarms."""


def card_for(
    access: Access | None,
    settings: ReminderSettings,
    *,
    android: bool,
    exact: bool | None,
) -> Card | None:
    """Return the card the OS's answers call for, or None (ux.md §4.8, §6.9; D-401).

    Only while a reminder is on: with everything off there is nothing to allow. An
    unread or unknown status shows nothing, as §4.8 says.

    Args:
        access: ``Scheduler.access()``'s answer; None until read.
        settings: The reminder settings: what is on, and whether the app has asked
            (``primer`` ``accepted``).
        android: The app runs on Android, the one platform with the exact-alarm card.
        exact: Whether Android allows exact alarms (``Scheduler.exact``); None until
            read.

    Returns:
        ``"ask"`` while the OS may still ask; ``"blocked"`` once only the system
        settings can allow notifications, which on iOS is also "askable" after the
        app has asked, since iOS shows its prompt once (F245); ``"exact"`` on Android
        while session reminders are on, notifications allowed and exact alarms not.
    """
    moments = settings.keynote or settings.lightning or settings.open_space
    if not settings.session_lead and not moments:
        return None
    if access == "askable":
        asked = settings.primer == "accepted"
        return "blocked" if asked and not android else "ask"
    if access == "blocked":
        return "blocked"
    if access == "allowed" and android and settings.session_lead and exact is False:
        return "exact"
    return None


@ft.component
def RemindersSection(slot: int) -> ft.Control:
    """The live Reminders section: its cards, the session switch and lead, the moments.

    Args:
        slot: The width the rows' icons are centred in: Settings' radio width, so the
            titles start where Appearance's do (#503's review).
    """
    page = ft.context.page
    svc = use_services()
    prefs = use_prefs()
    scheduler = svc.reminders
    assert scheduler is not None  # Settings shows the interim without E3
    settings = prefs.reminders
    state, set_access = ft.use_state(cast(Access | None, None))
    access = cast(Access | None, state)  # None until read
    heard, set_heard = ft.use_state(0)  # bumped when the Scheduler reads a change

    @report_errors
    async def read_access() -> None:
        set_access(await scheduler.access())

    ft.use_effect(read_access, [heard, settings])

    @report_errors
    async def listen() -> None:
        stop = scheduler.watch(lambda: set_heard(lambda n: n + 1))
        try:
            await svc.closed.wait()  # until unmounted: Flet cancels the setup (D-70)
        finally:
            stop()

    ft.use_effect(listen, [])

    @report_errors
    async def switch_sessions(e: ft.Event[ft.Switch]) -> None:
        on = bool(e.control.value)
        lead = PRIMER_LEAD if on else 0
        await save(page, svc, prefs, session_lead=lead)
        if on and prefs.reminders.primer != "accepted":  # D-61's first switch
            await ask(page, svc, prefs)

    @report_errors
    async def choose_lead(e: ft.Event[ft.SegmentedButton]) -> None:
        lead = int(e.control.selected[0])
        await save(page, svc, prefs, session_lead=lead)

    @report_errors
    async def switch_moment(e: ft.Event[ft.Switch]) -> None:
        changed = {str(e.control.data): bool(e.control.value)}  # the row's field
        await save(page, svc, prefs, **changed)

    @report_errors
    async def allow() -> None:
        await scheduler.request_permission()
        if prefs.reminders.primer != "accepted":  # asked: no primer after this one
            await save(page, svc, prefs, primer="accepted")
        set_heard(lambda n: n + 1)

    @report_errors
    async def open_settings() -> None:
        if svc.permissions is not None:
            await svc.permissions.open_app_settings()  # the resume re-reads (D-221)

    @report_errors
    async def open_alarms() -> None:
        await scheduler.request_exact()

    rows: list[ft.Control] = [SectionHeader("Reminders")]  # level 2 (D-211)
    match card_for(access, settings, android=scheduler.android, exact=scheduler.exact):
        case "ask":
            rows.append(notice_card(f"{SCREEN}.allow", ASK_TEXT, ASK_ACTION, allow))
        case "blocked":
            action = OPEN_SETTINGS if svc.permissions is not None else None
            rows.append(
                notice_card(f"{SCREEN}.blocked", BLOCKED_TEXT, action, open_settings)
            )
        case "exact":
            rows.append(
                notice_card(f"{SCREEN}.exact", EXACT_TEXT, OPEN_SETTINGS, open_alarms)
            )
        case None:
            pass
    rows.append(
        toggle_row(
            f"{SCREEN}.sessions",
            SESSIONS,
            ft.Icons.NOTIFICATIONS_ACTIVE_OUTLINED,
            on=bool(settings.session_lead),
            on_change=switch_sessions,
            slot=slot,
        )
    )
    if settings.session_lead:
        rows.append(lead_picker(settings.session_lead, choose_lead))
    rows.append(
        SectionHeader(
            MOMENTS,
            level=3,  # a group inside the section (D-211)
            top=8,
            theme_style=ft.TextThemeStyle.LABEL_LARGE,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
    )
    rows += [
        toggle_row(
            f"{SCREEN}.{field}",
            title,
            icon,
            on=settings.wants(field),
            on_change=switch_moment,
            slot=slot,
            data=field,
        )
        for field, title, icon in MOMENT_ROWS
    ]
    return ft.Column(rows, spacing=0)


async def save(page: ft.Page, svc: Services, prefs: Prefs, **changes: Any) -> None:
    """Save the reminder settings with ``changes``, silently unless the write fails.

    The scheduler re-plans on the change of ``Prefs.reminders`` (D-389); a failed
    write keeps the change for the session and says so (D-120).

    Args:
        page: The session's page.
        svc: The session's services: the storage.
        prefs: The session's ``Prefs``, whose ``reminders`` change.
        **changes: ``ReminderSettings`` fields and their new values.
    """
    reminders = dataclasses.replace(prefs.reminders, **changes)
    say_if_unsaved(page, await prefs.save(svc.storage, reminders=reminders))


def toggle_row(
    identifier: str,
    title: str,
    icon: ft.IconData,
    *,
    on: bool,
    on_change: Callable[[ft.Event[ft.Switch]], object],
    slot: int,
    data: str | None = None,
) -> ft.Control:
    """Return a switch row: one node with its identifier, toggled by the whole row.

    Read as its title and the switch's state; its decorative icon is centred in
    ``slot``, so the title starts where Appearance's do (ux.md §6.9).

    Args:
        identifier: For UI flows, e.g. ``settings.reminders.sessions``.
        title: What the switch turns on.
        icon: The decorative icon.
        on: The switch's state, from ``Prefs.reminders`` (controlled, D-157).
        on_change: Saves the new state.
        slot: The width the icon is centred in.
        data: The switch's ``data``: the moment's field, which its handler reads.
    """
    return named(
        identifier,
        ft.ListTile(
            leading=ft.Container(
                ft.Icon(icon), width=slot, alignment=ft.Alignment.CENTER
            ),
            title=title,
            trailing=ft.Switch(value=on, on_change=on_change, data=data),
            toggle_inputs=True,  # a tap anywhere on the row toggles it
        ),
    )


def lead_picker(
    lead: int, on_change: Callable[[ft.Event[ft.SegmentedButton]], object]
) -> ft.Control:
    """Return the 5 · 10 · 15 min ``SegmentedButton``, the session reminders' lead.

    Each segment is read as its label, a button and its state; its identifier is
    ``settings.reminders.lead.<minutes>``, merged into the segment's node as the
    Expo's view switch's are. As wide as the list's content, so "15 min" fits at
    200 % text.

    Args:
        lead: The chosen lead, in minutes (not 0: the picker shows while on).
        on_change: Saves the picked lead.
    """
    return ft.Container(
        ft.SegmentedButton(
            segments=[
                ft.Segment(
                    value=str(minutes),
                    label=ft.Semantics(
                        identifier=f"{SCREEN}.lead.{minutes}",
                        content=ft.Text(f"{minutes} min"),
                    ),
                )
                for minutes in SESSION_LEADS
                if minutes
            ],
            selected=[str(lead)],
            on_change=on_change,
            expand=True,
        ),
        padding=ft.Padding.only(left=16, right=16, bottom=8),
    )


def notice_card(
    identifier: str,
    text: str,
    action: str | None,
    on_click: Callable[[], object],
) -> ft.Control:
    """Return a card that says what the OS needs, with the button that gets there.

    The sentence is a live region, so a screen reader says a card that appears on
    resume; the button is its own stop, ``<identifier>.action``.

    Args:
        identifier: For UI flows, e.g. ``settings.reminders.exact``.
        text: The card's sentence.
        action: The button's label; None for no button (no system settings to open).
        on_click: The button's tap.
    """
    column: list[ft.Control] = [
        ft.Semantics(
            identifier=identifier,
            live_region=True,
            content=ft.Text(text, theme_style=ft.TextThemeStyle.BODY_MEDIUM),
        )
    ]
    if action is not None:
        column.append(
            ft.Row(
                [
                    named(
                        f"{identifier}.action",
                        ft.OutlinedButton(
                            action,
                            style=ft.ButtonStyle(padding=LABEL_PADDING),
                            on_click=on_click,
                        ),
                    )
                ],
                alignment=ft.MainAxisAlignment.END,
                wrap=True,  # the label wraps under at 200 % rather than clip
            )
        )
    return ft.Container(
        ft.Card(
            ft.Container(ft.Column(column, spacing=12), padding=16),
            variant=ft.CardVariant.OUTLINED,
            margin=0,
        ),
        padding=ft.Padding.only(left=16, top=4, right=16, bottom=8),
    )


def interim_section(platform: ft.PagePlatform | None, *, slot: int) -> ft.Control:
    """Return the interim Reminders section: its heading and the sentence (D-60).

    Args:
        platform: The page's platform: iOS's sentence mentions the calendar's alarm.
        slot: The width the icon is centred in: Settings' radio width, so the
            sentence starts where Appearance's titles do (#503's review).
    """
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
        f"{SCREEN}.interim",
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
