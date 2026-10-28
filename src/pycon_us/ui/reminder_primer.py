"""The reminders primer: one sentence before the OS asks for notifications (D-61, D-395).

Never at launch or on Welcome: ``offer_on_first_favorite()`` runs after a star tap that
added a session and saved it (``ui.favorite.use_favorite_toggle()``), never after an
Undo or "Add all", and only while the primer is unasked (``ReminderSettings.primer``,
D-275). ``ask()`` is the one flow, which the first reminder switch in Settings reuses
(#449). It reads the OS's answer so far (``Scheduler.access()``, ux.md §4.8) and shows
the primer only while the OS can still ask: when it already allows notifications,
there is nothing to ask; when it won't ask again, or the status is unknown, Settings'
card is the place (#449). The primer is a ``BottomSheet`` with "Allow" and "Not now":

- **Allow** closes the sheet, then asks the OS (E3's ``request_permissions()``, F17);
  when the OS allows and session reminders are off, they come on at ``PRIMER_LEAD``
  minutes, which the scheduler applies as for any change of ``Prefs.reminders``
  (D-389); a lead the Settings switch already chose stays (D-401). Allow is
  remembered whatever the OS answers.
- **Not now**, a tap outside the sheet, a drag down or Back remember "not now".

Either way the favourite stays saved, and a star never shows the primer again. The
sheet is a modal route, so Flutter gives the screen reader's focus back to the star
when it closes (D-225); on Now, where the add moves the session into Your next
session and replaces its star, the card's star gets it (``focus_back.refocus_star()``).
It needs E3 (``Services.reminders``, ``capabilities.REMINDERS``), as Settings' live
Reminders section does (D-395, D-401).
"""

import dataclasses
from collections.abc import Awaitable, Callable
from weakref import WeakSet

import flet as ft

from pycon_us.prefs import Prefs
from pycon_us.reminder_settings import SessionLead
from pycon_us.services import Services
from pycon_us.services.errors import report_errors
from pycon_us.theme_hc import hc_sheet_shape
from pycon_us.ui.buttons import LABEL_PADDING
from pycon_us.ui.focus_back import Star, refocus_star
from pycon_us.ui.semantics import named
from pycon_us.ui.snack_bars import NOT_SAVED, SNACK_BAR_MS

SCREEN = "reminder.primer"
"""The primer's name in the identifiers (decisions §M): ``reminder.primer.allow``."""

PRIMER = (
    "Get a heads-up 10 minutes before your saved sessions start, "
    "and before keynotes and sign-ups?"
)
"""The primer's one sentence (ux.md §4.8): it names everything Allow turns on, the
session reminders and the conference moments, which default on (D-275)."""

ALLOW = "Allow"
"""The button that asks the OS."""

NOT_NOW = "Not now"
"""The button that leaves reminders as they are."""

PRIMER_LEAD: SessionLead = 10
"""The session reminders' lead that Allow turns on once the OS allows (D-275)."""

type Handler = Callable[[], Awaitable[None]]
"""A button's or the sheet's handler; Flet calls one that takes no event without it."""

_ASKING: WeakSet[ft.Page] = WeakSet()
"""The pages whose primer is being asked or shown: two quick stars show one sheet."""


async def offer_on_first_favorite(
    page: ft.Page, svc: Services, prefs: Prefs, *, star: Star | None = None
) -> None:
    """Show the primer after a star saved a session, if it was never answered (D-61).

    Args:
        page: The session's page.
        svc: The session's services: ``reminders``, None without E3.
        prefs: The session's ``Prefs``: the primer's answer so far.
        star: The star tapped, found before the add (``focus_back.star_of()``).
    """
    if prefs.reminders.primer == "unasked":
        await ask(page, svc, prefs, star=star)


async def ask(
    page: ft.Page, svc: Services, prefs: Prefs, *, star: Star | None = None
) -> None:
    """Show the primer when the OS can still ask for notifications (ux.md §4.8).

    It returns once the sheet shows, or at once when there is nothing to ask: no E3
    (the companion app, D-60), a primer already up, or an OS that allows notifications
    already, won't ask again, or did not say. The sheet's answer is handled by its
    buttons and its dismissal (``_answer()``).

    Args:
        page: The session's page.
        svc: The session's services: ``reminders``, None without E3.
        prefs: The session's ``Prefs``, where the answer is saved.
        star: The star that opened it, which gets the focus back once answered when
            a render replaced it (``focus_back.refocus_star()``, D-225); None when
            no star did.
    """
    scheduler = svc.reminders
    if scheduler is None or page in _ASKING:
        return
    _ASKING.add(page)  # before the await: a second star meanwhile shows nothing
    if await scheduler.access() != "askable":
        _ASKING.discard(page)
        return
    answered = False

    @report_errors
    async def answer(allow: bool, *, close: bool) -> None:
        nonlocal answered
        if answered:  # the dismissal that follows a button's close
            return
        answered = True
        try:
            if close:
                sheet.open = False
                sheet.update()
            granted = allow and await scheduler.request_permission()
            await _save(page, svc, prefs, allow=allow, granted=granted)
        finally:
            _ASKING.discard(page)
        if star is not None:  # after the OS's prompt too: the app is back by then
            await refocus_star(svc, page, star)

    @report_errors
    async def allow() -> None:
        await answer(True, close=True)

    @report_errors
    async def not_now() -> None:
        await answer(False, close=True)

    @report_errors
    async def dismissed() -> None:
        await answer(False, close=False)

    sheet = primer_sheet(
        on_allow=allow,
        on_not_now=not_now,
        on_dismiss=dismissed,
        high_contrast=prefs.high_contrast_on,
        reduce_motion=prefs.reduce_motion,
    )
    page.show_dialog(sheet)


async def _save(
    page: ft.Page, svc: Services, prefs: Prefs, *, allow: bool, granted: bool
) -> None:
    """Save the primer's answer, and the session reminders' lead when the OS allows.

    Read from ``prefs`` after the OS's answer, so a change made meanwhile is kept: a
    lead already on (the Settings switch that showed the primer) stays. A failed
    write keeps the answer for the session and says so (D-120).
    """
    reminders = dataclasses.replace(
        prefs.reminders, primer="accepted" if allow else "not_now"
    )
    if granted and not reminders.session_lead:
        reminders = dataclasses.replace(reminders, session_lead=PRIMER_LEAD)
    if not await prefs.save(svc.storage, reminders=reminders):
        page.show_dialog(
            ft.SnackBar(
                ft.Text(NOT_SAVED),
                behavior=ft.SnackBarBehavior.FLOATING,
                duration=SNACK_BAR_MS,
            )
        )


def primer_sheet(
    *,
    on_allow: Handler,
    on_not_now: Handler,
    on_dismiss: Handler,
    high_contrast: bool,
    reduce_motion: bool,
) -> ft.BottomSheet:
    """Return the primer: a decorative bell, ``PRIMER``, then "Not now" and "Allow".

    The buttons wrap under each other at the largest text rather than clip, Allow
    last, where M3 puts a sheet's confirming action; a sheet taller than the screen
    (200 % text in landscape) scrolls. The sentence is a node of its own
    (``reminder.primer``), read first.

    Args:
        on_allow: Allow's tap.
        on_not_now: Not now's tap.
        on_dismiss: A tap outside, a drag down or Back, after the sheet has gone;
            also after a button closed it.
        high_contrast: HC is on screen: a 1 dp ``outline`` edge (D-306).
        reduce_motion: The OS asks for less motion: the sheet does not slide (D-173).
    """
    content = ft.Column(
        [
            # Decorative: an Icon without a label has no semantics node.
            ft.Icon(ft.Icons.NOTIFICATIONS_ACTIVE_OUTLINED, color=ft.Colors.PRIMARY),
            ft.Semantics(
                identifier=SCREEN,
                content=ft.Text(
                    PRIMER,
                    theme_style=ft.TextThemeStyle.BODY_LARGE,
                    text_align=ft.TextAlign.CENTER,  # under the bell
                ),
            ),
            ft.Row(
                [
                    named(
                        f"{SCREEN}.not_now",
                        ft.TextButton(NOT_NOW, on_click=on_not_now),
                    ),
                    named(
                        f"{SCREEN}.allow",
                        ft.FilledButton(
                            ALLOW,
                            style=ft.ButtonStyle(padding=LABEL_PADDING),
                            elevation=0,  # M3's filled button lies flat
                            on_click=on_allow,
                        ),
                    ),
                ],
                alignment=ft.MainAxisAlignment.END,
                wrap=True,
                spacing=8,
                run_spacing=8,
            ),
        ],
        spacing=16,
        tight=True,
        # Taller than the sheet may be (200 % text in landscape), it scrolls, so
        # both buttons stay reachable (ux.md §9).
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
    return ft.BottomSheet(
        ft.Container(  # 16 dp gutters (ux.md §3.6); the buttons clear the home bar
            padding=ft.Padding.only(left=16, right=16, bottom=16),
            # A scrolling Column takes all the height it is given (Flet's
            # scrollable_control.dart, #6450): the intrinsic height gives it its
            # content's, up to the sheet's limit, so the sheet stays as short.
            content=ft.Row([content], intrinsic_height=True),
        ),
        show_drag_handle=True,
        scrollable=True,  # up to the screen's height, not 9/16 of it, at large text
        use_safe_area=True,
        shape=hc_sheet_shape(high_contrast),
        on_dismiss=on_dismiss,
        # Its slide is motion: none under reduced motion (D-34, D-173).
        animation_style=ft.AnimationStyle.no_animation() if reduce_motion else None,
    )
