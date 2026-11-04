"""The CoC review's flow: open it for a scan, record once, say how it ended (#760).

`use_review()` is the CoC tool's hook. Its `open(code, attendee)` shows the review
dialog (`ui/coc_review_dialog.py`) and returns the scan's result once it closes, so
the scan screen awaits one review at a time and drops submits meanwhile: "Incident
recorded" with the reply's name and count (`ScanOutcome.RECORDED`, neutral, D-430),
or "Not recorded" on Cancel or Back. An error keeps the dialog and its notes: the
server's refusal, "No connection. Nothing was recorded.", or, when the call may have
reached the server (D-410), "The incident may have been recorded…" with Record anyway;
nothing is ever re-sent on its own. Once a call may have landed, that stays said
until a reply: a later "No connection" keeps the D-410 line and Record anyway. Cancel
while the call is out, or after one that may have landed, closes the dialog with "Not
confirmed": the call ends on its own, and a success still updates the count. Each
opening's Cancel and dismissal answer only that opening, so a late dismissal of an
earlier dialog never closes the next.

**Privacy (D-72):** the notes live only in the dialog's field. They are sent once,
never stored, never logged, and gone when it closes.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from functools import partial
from typing import cast

import flet as ft
from flet.components.hooks.use_ref import MutableRef

from pycon_us import conduct
from pycon_us.core.badges import ScanOutcome, ScanResult
from pycon_us.core.conduct import Attendee, Recorded
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.api import ApiError, NetworkError
from pycon_us.services.errors import report_errors
from pycon_us.theme import use_tokens
from pycon_us.ui.coc_review_dialog import (
    DialogActions,
    Review,
    review_dialog,
    review_of,
)
from pycon_us.ui.hooks import use_latest_state
from pycon_us.ui.semantics import announce

NO_CONNECTION = "No connection. Nothing was recorded."
MAYBE_RECORDED = (
    "The incident may have been recorded. Check the count before recording again."
)
"""A call that may have reached the server without an answer (D-410)."""

RECORDED = "Incident recorded"
NOT_RECORDED = "Not recorded"
NOT_CONFIRMED = "Not confirmed"
"""Cancel while the call is out: it may still land."""


def recorded_result(review: Review, recorded: Recorded) -> ScanResult:
    """Return the panel's "Incident recorded", the name and "2 on record" (MASK-05).

    The reply's email rides along, hidden: the tool's "Show email" reveals it (#762).

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
        email=recorded.email or "",
    )


def closed_result(review: Review) -> ScanResult:
    """Return the panel's result for a review closed without a reply.

    "Not recorded" and the name; while the call was out, or after one that may have
    reached the server, "Not confirmed" and the D-410 line, since the incident may
    be on record all the same.

    Args:
        review: The review as it was closed.
    """
    if review.sending or review.maybe_sent:
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
    if error.unreadable:
        return MAYBE_RECORDED, True
    return f"{NOT_RECORDED}. {error.message}", False


type OnRecorded = Callable[[str, int | None], None]
"""Called with the code and the reply's count after each recorded incident."""


@dataclass(frozen=True)
class ReviewDialog:
    """What the CoC tool gets from `use_review()`.

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
    reported (D-243), through a `Ref` made for each opening, so typing is never sent
    back over and the next opening starts empty.

    Args:
        on_recorded: Called with the code and the new count after each incident
            recorded while the caller is mounted, so its directory row follows.
    """
    svc = use_services()
    prefs = use_prefs()
    tokens = use_tokens()
    # `latest`, the review as the handlers left it, is what Record reads (#756).
    review, latest, set_review = use_latest_state(cast(Review | None, None))
    waiting: MutableRef[asyncio.Future[ScanResult] | None] = ft.use_ref(None)
    is_open = review is not None
    field = ft.use_memo(ft.Ref[ft.TextField], [is_open])  # a fresh one each opening
    mounted = ft.use_ref(True)  # cleared on unmount: a late reply then sets nothing

    @report_errors
    def finish(result: ScanResult) -> None:
        """Close the dialog and hand `result` to the scan that opened it."""
        set_review(None)
        answer(waiting, result)

    @report_errors
    def unmount() -> None:
        """Mark the tool gone and release the scan still waiting on the dialog."""
        mounted.current = False
        if latest.current is not None:
            answer(waiting, closed_result(latest.current))

    ft.use_effect(lambda: None, [], cleanup=unmount)

    @report_errors
    def cancel(opened: asyncio.Future[ScanResult] | None) -> None:
        """Close the review `opened` answers, unless another opening replaced it.

        Flutter reports a dialog's dismissal once its route has closed, so an earlier
        dialog's may arrive after the next review opened: that one must stay.
        """
        current = latest.current
        if current is not None and waiting.current is opened:
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
            if current.maybe_sent:  # an earlier call may have landed: still so (D-410)
                problem, maybe = MAYBE_RECORDED, True
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
        await announce(svc.semantics, problem)

    ft.use_effect(say, [problem])

    text = ""  # empty on an opening's first render, then what Flutter reported
    if review is not None and field.current is not None:
        text = field.current.value or ""
    ft.use_dialog(
        review_dialog(
            review,
            field,
            text,
            DialogActions(record, partial(cancel, waiting.current)),
            tokens=tokens,
            live=not prefs.announcements,
        )
        if review is not None
        else None
    )
    return ReviewDialog(partial(wait_for_review, waiting, set_review), is_open)


async def wait_for_review(
    waiting: MutableRef[asyncio.Future[ScanResult] | None],
    show: Callable[[Review], None],
    code: str,
    attendee: Attendee | None,
) -> ScanResult:
    """Show the review of `code` and return the result its closing answers with.

    Args:
        waiting: Where the hook keeps the future the dialog answers.
        show: Sets the review on screen.
        code: The scanned access code.
        attendee: The directory's row for it, or None.
    """
    future: asyncio.Future[ScanResult] = asyncio.get_running_loop().create_future()
    waiting.current = future
    show(review_of(code, attendee))
    return await future


def answer(
    waiting: MutableRef[asyncio.Future[ScanResult] | None], result: ScanResult
) -> None:
    """Hand `result` to the scan waiting on the review, once; then nothing waits."""
    future, waiting.current = waiting.current, None
    if future is not None and not future.done():
        future.set_result(result)
