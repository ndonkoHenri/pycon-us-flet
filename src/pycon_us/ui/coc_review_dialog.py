"""The CoC review dialog's look: who it is, what happened, then Record (#760; MASK-03).

ux.md §7.3. A scanned badge never records by itself (MASK-04): it opens this modal
``AlertDialog``, scrollable so Record stays in reach at 200 % text, with

- a level-1 heading "Record an incident", the dialog's first stop;
- the name (or the code), "Badge: Grace S." when the badge says another, and the
  count in words with its level's icon; a code the loaded directory lacks says "Not
  in the loaded attendee list" and may still be recorded (D-434): the server knows
  the badge, and a 404 says otherwise, here;
- "What happened?", a multi-line field of at most 2000 characters with its counter
  (``coc.review.notes``), and under it, after a failed Record, why
  (``coc.review.problem``, a live region; on iOS ``ui/coc_review.py`` announces it);
- Cancel (``coc.review.cancel``) and Record incident (``coc.review.record``), which
  shows a ring and "Recording…", disabled, while the call is out; Cancel stays enabled.

Built from data only: ``ui/coc_review.py``'s ``use_review()`` keeps the ``Review`` and
the handlers.
"""

from collections.abc import Callable
from dataclasses import dataclass

import flet as ft

from pycon_us.core.conduct import (
    Attendee,
    Level,
    count_level,
    count_words,
    display_name,
)
from pycon_us.theme import Tokens
from pycon_us.ui.queue_rows import heading
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
