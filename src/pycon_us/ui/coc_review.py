"""The CoC review dialog: who it is, what happened, then Record incident (#760; MASK-03).

ux.md §7.3. A scanned badge never records by itself (MASK-04): it opens this modal
``AlertDialog``, scrollable so Record stays in reach at 200 % text, with

- a level-1 heading "Record an incident", the dialog's first stop;
- the name (or the code), "Badge: Grace S." when the badge says another, and the
  count in words with its level's icon; a code the loaded directory lacks says "Not
  in the loaded attendee list" and may still be recorded (D-434): the server knows
  the badge, and a 404 says otherwise, here;
- "What happened?", a multi-line field of at most 2000 characters with its counter
  (``coc.review.notes``), and under it, after a failed Record, why (``coc.review.problem``,
  a live region; on iOS an announcement);
- Cancel (``coc.review.cancel``) and Record incident (``coc.review.record``), which
  shows a ring and "Recording…", disabled, while the call is out; Cancel stays enabled.

``use_review()`` is the CoC tool's hook. Its ``open(code, attendee)`` shows the dialog
and returns the scan's result once it closes, so the scan screen awaits one review at
a time and drops submits meanwhile: "Incident recorded" with the reply's name and
count (``ScanOutcome.RECORDED``, neutral, D-430), or "Not recorded" on Cancel or Back.
An error keeps the dialog and its notes: the server's refusal, "No connection.
Nothing was recorded.", or, when the call may have reached the server (D-410), "The
incident may have been recorded…" with Record anyway; nothing is ever re-sent on its
own. Cancel while the call is out closes the dialog with "Not confirmed": the call
ends on its own, and a success still updates the count.

**Privacy (D-72):** the notes live only in the dialog's field. They are sent once,
never stored, never logged, and gone when it closes.
"""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace

import flet as ft
from flet.components.hooks.use_ref import MutableRef

from pycon_us import conduct
from pycon_us.core.badges import ScanOutcome, ScanResult
from pycon_us.core.conduct import (
    Attendee,
    Level,
    Recorded,
    count_level,
    count_words,
    display_name,
)
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.api import ApiError, NetworkError
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import SERVICE_ERRORS
from pycon_us.theme import Tokens, use_tokens
from pycon_us.ui.queue_rows import heading
from pycon_us.ui.scan_feedback import ANNOUNCE_WAIT_S
from pycon_us.ui.semantics import named

TITLE = "Record an incident"
NOT_LISTED = "Not in the loaded attendee list"
"""A code the loaded directory lacks: still recordable (D-434)."""

NOTES_LABEL = "What happened?"
NOTES_HINT = "What happened? Where? Witnesses?"
MAX_LENGTH = 2000
"""The notes' longest text, in characters (MASK-03)."""

RECORD = "Record incident"
RECORD_ANYWAY = "Record anyway"
RECORDING = "Recording…"

NO_CONNECTION = "No connection. Nothing was recorded."
MAYBE_RECORDED = (
    "The incident may have been recorded. Check the count before recording again."
)
"""A call that may have reached the server without an answer (D-410)."""

RECORDED = "Incident recorded"
NOT_RECORDED = "Not recorded"
NOT_CONFIRMED = "Not confirmed"
"""Cancel while the call is out: it may still land."""

LEVEL_ICONS: dict[Level, ft.IconData] = {
    Level.NONE: ft.Icons.INFO_OUTLINE,
    Level.NOTICE: ft.Icons.WARNING_AMBER,
    Level.HIGH: ft.Icons.ERROR_OUTLINE,
}
"""Each count level's icon: with the words, never colour alone (MASK-02)."""


@dataclass(frozen=True)
class Review:
    """The badge the dialog is open for, and where its Record is.

    Attributes:
        code: The attendee's access code, what the record is sent with.
        name: The display name, or the code when the directory lacks it.
        badge_name: The badge's name when it differs from ``name``, else ``""``.
        incidents: The incidents on record as the directory says, or None when the
            loaded directory lacks the code.
        sending: The call is out: Record is disabled with a ring.
        problem: Why the last Record recorded nothing, or may have; None before.
        maybe_sent: The last Record may have reached the server: "Record anyway".
    """

    code: str
    name: str
    badge_name: str = ""
    incidents: int | None = None
    sending: bool = False
    problem: str | None = None
    maybe_sent: bool = False


def review_of(code: str, attendee: Attendee | None) -> Review:
    """Return a new review of ``code``, named from the directory's row when it has one.

    Args:
        code: The scanned access code.
        attendee: The directory's row for it, or None.
    """
    if attendee is None:
        return Review(code, code)
    name = display_name(attendee)
    badge = attendee.badge_name if attendee.badge_name != name else ""
    return Review(code, name, badge, attendee.incidents)


@dataclass(frozen=True)
class DialogActions:
    """What the dialog's buttons call.

    Attributes:
        record: Record incident (or Record anyway).
        cancel: Cancel, and a dismissal by Back.
    """

    record: Callable[[], object]
    cancel: Callable[[], object]


def review_dialog(
    review: Review,
    field: ft.Ref[ft.TextField],
    text: str,
    actions: DialogActions,
    *,
    tokens: Tokens,
    live: bool = True,
) -> ft.AlertDialog:
    """Return the review dialog for ``review`` (ux.md §7.3).

    Args:
        review: The badge and where its Record is.
        field: Set to the notes field, which Record reads (D-243).
        text: The notes as Flutter last reported them: never sent back over typing.
        actions: The handlers.
        tokens: The scheme's tokens, for the level's colour.
        live: The problem line is a live region (not where iOS announces).
    """
    body: list[ft.Control] = [
        ft.Text(review.name, theme_style=ft.TextThemeStyle.TITLE_MEDIUM)
    ]
    if review.badge_name:
        body.append(_line(f"Badge: {review.badge_name}"))
    if review.incidents is None:
        body.append(_line(NOT_LISTED))
    else:
        body.append(count_line(review.incidents, tokens))
    body.append(
        ft.Container(
            named(
                "coc.review.notes",
                ft.TextField(
                    ref=field,
                    value=text,
                    label=NOTES_LABEL,
                    hint_text=NOTES_HINT,
                    multiline=True,
                    min_lines=3,
                    max_lines=8,
                    max_length=MAX_LENGTH,
                    capitalization=ft.TextCapitalization.SENTENCES,
                ),
            ),
            padding=ft.Padding.only(top=8),
        )
    )
    if review.problem:
        body.append(
            ft.Semantics(
                identifier="coc.review.problem",
                container=True,
                live_region=live,
                content=ft.Text(review.problem, color=ft.Colors.ERROR),
            )
        )
    return ft.AlertDialog(
        modal=True,
        scrollable=True,  # the field and Record stay in reach at 200 % text
        title=heading(TITLE, 1),
        content=ft.Column(
            body,
            tight=True,
            spacing=8,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        actions=[
            named(
                "coc.review.cancel", ft.TextButton("Cancel", on_click=actions.cancel)
            ),
            named("coc.review.record", record_button(review, actions.record)),
        ],
        on_dismiss=lambda _: actions.cancel(),  # Back cancels (D-208)
    )


def _line(words: str) -> ft.Control:
    """Return a line of the dialog in ``BODY_MEDIUM`` and ``on_surface_variant``."""
    return ft.Text(
        words,
        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )


def count_line(incidents: int, tokens: Tokens) -> ft.Control:
    """Return the count in words with its level's icon, one node read as the words.

    Args:
        incidents: The incidents on record.
        tokens: The scheme's tokens: a notice is in ``warning``, a high count in
            ``error``, none in ``on_surface_variant``.
    """
    level = count_level(incidents)
    color = {
        Level.NONE: ft.Colors.ON_SURFACE_VARIANT,
        Level.NOTICE: tokens.warning,
        Level.HIGH: ft.Colors.ERROR,
    }[level]
    words = count_words(incidents)
    return ft.Semantics(
        identifier="coc.review.count",
        container=True,
        label=words,
        exclude_semantics=True,  # the icon is decorative: the words say it
        content=ft.Row(
            [
                ft.Icon(LEVEL_ICONS[level], color=color, apply_text_scaling=True),
                ft.Text(words, color=color, expand=True),
            ],
            spacing=8,
        ),
    )


def record_button(review: Review, on_click: Callable[[], object]) -> ft.FilledButton:
    """Return Record incident: a ring and "Recording…", disabled, while the call is out.

    The words change with the ring, so a screen reader says the in-flight state.

    Args:
        review: The review: sending, or after a send that may have landed.
        on_click: Records.
    """
    if review.sending:
        label: ft.Control = ft.Row(
            [
                ft.ProgressRing(width=16, height=16, stroke_width=2),
                ft.Text(RECORDING),
            ],
            spacing=8,
            tight=True,
        )
    else:
        label = ft.Text(RECORD_ANYWAY if review.maybe_sent else RECORD)
    return ft.FilledButton(content=label, on_click=on_click, disabled=review.sending)


def recorded_result(review: Review, recorded: Recorded) -> ScanResult:
    """Return the panel's "Incident recorded", the name and "2 on record" (MASK-05).

    Args:
        review: The review the incident was recorded from.
        recorded: The reply: its name first, else the review's; its count when sent.
    """
    details = () if recorded.incidents is None else (f"{recorded.incidents} on record",)
    return ScanResult(
        ScanOutcome.RECORDED,
        RECORDED,
        recorded.name or review.name,
        details,
        code=review.code,
    )


def closed_result(review: Review) -> ScanResult:
    """Return the panel's result for a review closed without a reply.

    "Not recorded" and the name; while the call was out, "Not confirmed" and the
    D-410 line, since the incident may land all the same.

    Args:
        review: The review as it was closed.
    """
    if review.sending:
        return ScanResult(
            ScanOutcome.NOT_RECORDED,
            NOT_CONFIRMED,
            review.name,
            (MAYBE_RECORDED,),
            code=review.code,
        )
    return ScanResult(
        ScanOutcome.NOT_RECORDED, NOT_RECORDED, review.name, code=review.code
    )


def problem_of(error: ApiError | NetworkError) -> tuple[str, bool]:
    """Return why a Record failed, and whether the incident may be on record.

    Args:
        error: The call's error: a refusal (the server's message), an unreadable
            reply (an answer came, so it may be recorded), or no answer (D-410).
    """
    if isinstance(error, NetworkError):
        return (MAYBE_RECORDED, True) if error.maybe_sent else (NO_CONNECTION, False)
    if error.status is None:
        return MAYBE_RECORDED, True
    return f"{NOT_RECORDED}. {error.message}", False


type OnRecorded = Callable[[str, int | None], None]
"""Called with the code and the reply's count after each recorded incident."""


@dataclass(frozen=True)
class ReviewDialog:
    """What the CoC tool gets from ``use_review()``.

    Attributes:
        open: Shows the dialog for a code and its directory row (or None), and
            returns the scan's result once it closes.
        is_open: The dialog is open: the scan screen pauses scanning meanwhile.
    """

    open: Callable[[str, Attendee | None], Awaitable[ScanResult]]
    is_open: bool


def use_review(*, on_recorded: OnRecorded) -> ReviewDialog:
    """Keep the review being shown and its outcome; show the dialog while it is open.

    Call it on every render (D-70). The notes field is built from what Flutter last
    reported (D-243), through a ``Ref`` made for each opening, so typing is never sent
    back over and the next opening starts empty.

    Args:
        on_recorded: Called with the code and the new count after each incident
            recorded while the caller is mounted, so its directory row follows.
    """
    svc = use_services()
    prefs = use_prefs()
    tokens = use_tokens()
    review, set_state = ft.use_state(not_open)
    # The review as the handlers left it: a render may not have run between two
    # events (use_state only schedules one), so Record reads this (#756).
    latest: MutableRef[Review | None] = ft.use_ref(review)
    waiting: MutableRef[asyncio.Future[ScanResult] | None] = ft.use_ref(None)
    is_open = review is not None
    field = ft.use_memo(ft.Ref[ft.TextField], [is_open])  # a fresh one each opening
    mounted = ft.use_ref(True)  # cleared on unmount: a late reply then sets nothing

    def set_review(value: Review | None) -> None:
        latest.current = value
        set_state(value)

    def finish(result: ScanResult) -> None:
        """Close the dialog and hand ``result`` to the scan that opened it."""
        set_review(None)
        future, waiting.current = waiting.current, None
        if future is not None and not future.done():
            future.set_result(result)

    @report_errors
    def unmount() -> None:
        """Mark the tool gone and release the scan still waiting on the dialog."""
        mounted.current = False
        current, future = latest.current, waiting.current
        waiting.current = None
        if current is not None and future is not None and not future.done():
            future.set_result(closed_result(current))

    ft.use_effect(lambda: None, [], cleanup=unmount)

    async def open_for(code: str, attendee: Attendee | None) -> ScanResult:
        future: asyncio.Future[ScanResult] = asyncio.get_running_loop().create_future()
        waiting.current = future
        set_review(review_of(code, attendee))
        return await future

    @report_errors
    def cancel() -> None:
        current = latest.current
        if current is not None:
            finish(closed_result(current))

    @report_errors
    async def record() -> None:
        current = latest.current
        if current is None or current.sending:
            return  # a double tap sends one
        future = waiting.current
        shown = field.current
        notes = (shown.value or "") if shown is not None else ""
        sending = replace(current, sending=True, problem=None)
        set_review(sending)
        try:
            if svc.api is None:  # the mock URL went meanwhile; the guard follows
                raise NetworkError("no mock client")
            recorded = await conduct.record(svc.api, current.code, notes)
        except (ApiError, NetworkError) as error:  # nothing logged (D-72)
            problem, maybe = problem_of(error)
            if mounted.current and waiting.current is future:
                set_review(
                    replace(sending, sending=False, problem=problem, maybe_sent=maybe)
                )
            return
        if not mounted.current:
            return
        on_recorded(current.code, recorded.incidents)
        if waiting.current is future:  # still open: else Cancel has answered
            finish(recorded_result(current, recorded))

    problem = review.problem if review is not None else None

    @report_errors
    async def say() -> None:
        # VoiceOver has no live regions: iOS hears the problem this way.
        if not (problem and prefs.announcements and mounted.current):
            return
        with contextlib.suppress(*SERVICE_ERRORS, TimeoutError):
            said = svc.semantics.announce_message(problem)
            await asyncio.wait_for(said, ANNOUNCE_WAIT_S)

    ft.use_effect(say, [problem])

    text = ""  # empty on an opening's first render, then what Flutter reported
    if review is not None and field.current is not None:
        text = field.current.value or ""
    ft.use_dialog(
        review_dialog(
            review,
            field,
            text,
            DialogActions(record, cancel),
            tokens=tokens,
            live=not prefs.announcements,
        )
        if review is not None
        else None
    )
    return ReviewDialog(open_for, is_open)


def not_open() -> Review | None:
    """Return None: no review open, the hook's first state (a typed default)."""
    return None
