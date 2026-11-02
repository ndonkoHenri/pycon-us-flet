"""The lead note sheet: interest, follow-ups and free text for one lead (#742; LEAD-10).

ux.md §7.3. Ionic's modal labelled its choices with emoji, which screen readers read
oddly; here a modal ``BottomSheet`` with a drag handle, everything scrolling together
so Save stays in reach at 200 % text:

- a level-1 heading "Note for Ada" (the lead's name, or its code), the code under it
  when the name is the heading, and "For Example Corp" on a staff account's lead, since
  each sponsor's lead on an attendee has its own note (D-459);
- **Interest**, a ``SegmentedButton`` Hot · Warm · Cold with icons, empty allowed (a
  tap on the chosen one clears it), each segment read with its state;
- **Follow-up**, a filter ``Chip`` per label of ``FOLLOW_UPS``, each one stop that says
  whether it is selected;
- **Notes**, a multi-line ``TextField`` of at most 4000 characters with its counter;
- Cancel and **Save** (``lead.note.save``), and a line when the outbox can't store it.

The Interest button and the Follow-up chips are built in ``ui/lead_note_fields.py``.

``use_note_sheet()`` is the Lead scanner's hook: it keeps the lead being noted and the
draft, prefills it from the lead's saved note (``lead_note.saved_note()``), shows the
sheet through ``ft.use_dialog`` and saves through ``lead_note.store()`` and
``confirm()``. Save closes the sheet and says "Note saved", "Note saved. Will sync."
or "Nothing to save" in a SnackBar, unless the screen has gone meanwhile. When the
saved note can't be read, the sheet stays closed and a SnackBar says so: a blank
prefill would save over it.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import partial

import flet as ft
from flet.components.hooks.use_ref import MutableRef

from pycon_us import lead_note
from pycon_us.core.lead_notes import FOLLOW_UPS, Interest, LeadNote
from pycon_us.core.lead_sponsors import LeadSponsor
from pycon_us.core.lead_views import for_line
from pycon_us.core.outbox_enqueue import Outcome
from pycon_us.locations import is_top_view
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.staff import use_staff
from pycon_us.theme import use_tokens
from pycon_us.theme_hc import hc_sheet_shape
from pycon_us.ui.lead_note_fields import follow_up_chip, interest_button
from pycon_us.ui.queue_rows import heading, note
from pycon_us.ui.semantics import named

type OpenNote = Callable[[str, str | None, LeadSponsor | None], None]
"""Opens the sheet for a lead: its code, the name if any, and the sponsor it was scanned
for (None for a sponsor's own lead)."""

MAX_LENGTH = 4000
"""The note's longest free text, in characters (ux.md §7.3)."""


@dataclass(frozen=True)
class Editing:
    """The lead the sheet is open for, and its draft.

    Attributes:
        code: The lead's access code.
        name: The attendee's first name when the result had one, else None.
        draft: The interest and follow-ups as chosen so far, and the text the field
            started with: the field itself holds what is typed since (D-243).
        problem: Why the last Save stored nothing (``lead_note.NOT_SAVED``), or None.
        sponsor: The sponsor the lead was scanned for; None for a sponsor's own lead.
    """

    code: str
    name: str | None
    draft: LeadNote
    problem: str | None = None
    sponsor: LeadSponsor | None = None


def title_of(editing: Editing) -> str:
    """Return the sheet's heading: "Note for Ada", or "Note for MOCK0001"."""
    return f"Note for {editing.name or editing.code}"


@dataclass(frozen=True)
class SheetActions:
    """What the sheet's controls call.

    Attributes:
        interest: The segmented button's change.
        follow_up: A chip's toggle, with its label and new state.
        save: Save.
        cancel: Cancel, and a dismissal: a swipe, Back, a tap on the scrim.
    """

    interest: ft.ControlEventHandler[ft.SegmentedButton]
    follow_up: Callable[[str, bool], object]
    save: Callable[[], object]
    cancel: Callable[[], object]


def note_sheet(
    editing: Editing,
    field: ft.Ref[ft.TextField],
    text: str,
    actions: SheetActions,
    *,
    high_contrast: bool = False,
    reduce_motion: bool = False,
) -> ft.BottomSheet:
    """Return the note sheet for ``editing`` (ux.md §7.3).

    Args:
        editing: The lead and its draft.
        field: Set to the Notes field, which Save reads (D-243).
        text: The Notes field's text: the prefill, or what Flutter last reported.
        actions: The handlers.
        high_contrast: HC is on screen: a 1 dp ``outline`` edge draws the sheet.
        reduce_motion: The sheet appears without its slide (D-34, D-173).
    """
    draft = editing.draft
    body: list[ft.Control] = [heading(title_of(editing), 1)]
    if editing.name:
        body.append(note(editing.code))
    if editing.sponsor is not None:
        line = for_line(editing.sponsor.name)
        body.append(note(line, identifier="lead.note.sponsor"))
    body += [
        heading("Interest", 2),
        interest_button(draft.interest, actions.interest),
        heading("Follow-up", 2),
        ft.Row(
            [
                follow_up_chip(label, label in draft.follow_ups, actions.follow_up)
                for label in FOLLOW_UPS
            ],
            wrap=True,
            spacing=8,
            run_spacing=8,
        ),
        ft.Container(
            named(
                "lead.note.text",
                ft.TextField(
                    ref=field,
                    value=text,
                    label="Notes",
                    multiline=True,
                    min_lines=3,
                    max_lines=8,
                    max_length=MAX_LENGTH,
                    capitalization=ft.TextCapitalization.SENTENCES,
                ),
            ),
            padding=ft.Padding.only(top=24),
        ),
    ]
    if editing.problem:
        body.append(
            ft.Semantics(
                identifier="lead.note.problem",
                live_region=True,
                content=ft.Text(editing.problem, color=ft.Colors.ERROR),
            )
        )
    body.append(
        ft.Container(
            ft.Row(
                [
                    named(
                        "lead.note.cancel",
                        ft.TextButton("Cancel", on_click=actions.cancel),
                    ),
                    named(
                        "lead.note.save",
                        ft.FilledButton(
                            "Save",
                            icon=ft.Icons.SAVE_OUTLINED,
                            on_click=actions.save,
                        ),
                    ),
                ],
                alignment=ft.MainAxisAlignment.END,
                wrap=True,
                spacing=8,
                run_spacing=8,
            ),
            padding=ft.Padding.only(top=8),
        )
    )
    return ft.BottomSheet(
        ft.Container(  # 16 dp gutters (ux.md §3.6), clear of the home bar
            padding=ft.Padding.only(left=16, right=16, bottom=16),
            content=ft.Column(
                body,
                spacing=8,
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        ),
        show_drag_handle=True,
        scrollable=True,  # up to the screen's height: Save stays in reach at 200 %
        use_safe_area=True,
        shape=hc_sheet_shape(high_contrast),
        on_dismiss=lambda _: actions.cancel(),
        animation_style=ft.AnimationStyle.no_animation() if reduce_motion else None,
    )


@dataclass(frozen=True)
class NoteSheet:
    """What the Lead scanner gets from ``use_note_sheet()``.

    Attributes:
        open: Opens the sheet for a lead.
        is_open: The sheet is open: the scan screen pauses scanning meanwhile.
    """

    open: OpenNote
    is_open: bool


def use_note_sheet(*, owner: str) -> NoteSheet:
    """Keep the note sheet's lead and draft, show it while open; return what opens it.

    Call it on every render (D-70). The Notes field is built from what Flutter last
    reported (D-243), through a ``Ref`` made for each opening, so the prefill is sent
    once and typing is never sent back over.

    Args:
        owner: The signed-in account (``Account.owner``).
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    staff = use_staff()
    prefs = use_prefs()
    tokens = use_tokens()
    editing, set_state = ft.use_state(not_editing)
    # The draft as the handlers left it: a render may not have run between two
    # events (use_state only schedules one), so Save reads this, not `editing`.
    latest: MutableRef[Editing | None] = ft.use_ref(editing)
    is_open = editing is not None
    field = ft.use_memo(ft.Ref[ft.TextField], [is_open])  # a fresh one each opening
    mounted = ft.use_ref(True)  # cleared on unmount: a late SnackBar is then dropped

    @report_errors
    def unmount() -> None:
        """Mark the screen gone, so a save still waiting stays quiet."""
        mounted.current = False

    ft.use_effect(lambda: None, [], cleanup=unmount)

    set_editing = partial(keep, latest, set_state)

    @report_errors
    def open_for(code: str, name: str | None, sponsor: LeadSponsor | None) -> None:
        sponsor_id = None if sponsor is None else sponsor.id
        draft = lead_note.saved_note(svc.outbox, owner, code, sponsor_id)
        if draft is None:  # logged; a blank prefill would save over the note
            page.show_dialog(snack_bar(lead_note.NOT_LOADED))
            return
        set_editing(Editing(code, name, draft, sponsor=sponsor))

    @report_errors
    def close() -> None:
        set_editing(None)

    @report_errors
    def interest(e: ft.Event[ft.SegmentedButton]) -> None:
        chosen = e.control.selected
        value = Interest(chosen[0]) if chosen else None
        set_editing(redraft(latest.current, interest=value))

    @report_errors
    def follow_up(label: str, selected: bool) -> None:
        set_editing(toggled(latest.current, label, selected))

    @report_errors
    async def save() -> None:
        current = latest.current
        if current is None:
            return
        shown = field.current  # None before the sheet's first render: the prefill
        typed = current.draft.text if shown is None else shown.value or ""
        draft = replace(current.draft, text=typed)
        stored = lead_note.store(
            svc.outbox, current.code, draft, owner=owner, sponsor=current.sponsor
        )
        if stored is None or svc.outbox is None:  # logged (D-120); the text stays
            set_editing(replace(current, problem=lead_note.NOT_SAVED))
            return
        set_editing(None)  # scanning resumes while the note syncs
        words = lead_note.NOTHING_TO_SAVE
        if stored.outcome is not Outcome.IGNORED and stored.row is not None:
            words = await lead_note.confirm(
                svc.outbox, staff, svc.kick_sync, stored.row
            )
        if mounted.current and is_top_view(page.route, view_path):
            page.show_dialog(snack_bar(words))

    text = ""  # the prefill on an opening's first render, then what Flutter reported
    if editing is not None:
        shown = field.current
        text = editing.draft.text if shown is None else shown.value or ""
    ft.use_dialog(
        note_sheet(
            editing,
            field,
            text,
            SheetActions(interest, follow_up, save, close),
            high_contrast=tokens.high_contrast,
            reduce_motion=prefs.reduce_motion,
        )
        if editing is not None
        else None
    )
    return NoteSheet(open_for, is_open)


def keep(
    latest: MutableRef[Editing | None],
    set_state: Callable[[Editing | None], None],
    value: Editing | None,
) -> None:
    """Set the sheet's state and ``latest`` together, so the next event sees it at once."""
    latest.current = value
    set_state(value)


def snack_bar(words: str) -> ft.SnackBar:
    """Return the floating SnackBar that says ``words``."""
    return ft.SnackBar(ft.Text(words), behavior=ft.SnackBarBehavior.FLOATING)


def toggled(last: Editing | None, label: str, selected: bool) -> Editing | None:
    """Return ``last`` with a follow-up chosen or not; None stays None."""
    if last is None:
        return None
    kept = tuple(f for f in last.draft.follow_ups if f != label)
    return redraft(last, follow_ups=(*kept, label) if selected else kept)


def redraft(last: Editing | None, **change: object) -> Editing | None:
    """Return ``last`` with its draft changed, and no problem shown; None stays None."""
    if last is None:
        return None
    return replace(last, draft=replace(last.draft, **change), problem=None)


def not_editing() -> Editing | None:
    """Return None: no sheet open, the hook's first state (a typed default)."""
    return None
