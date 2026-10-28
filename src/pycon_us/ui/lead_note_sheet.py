"""The lead note sheet: interest, follow-ups and free text for one lead (#742; LEAD-10).

ux.md §7.3. Ionic's modal labelled its choices with emoji, which screen readers read
oddly; here a modal ``BottomSheet`` with a drag handle, everything scrolling together
so Save stays in reach at 200 % text:

- a level-1 heading "Note for Ada" (the lead's name, or its code), and the code under
  it when the name is the heading;
- **Interest**, a ``SegmentedButton`` Hot · Warm · Cold with icons, empty allowed (a
  tap on the chosen one clears it), each segment read with its state;
- **Follow-up**, a filter ``Chip`` per label of ``FOLLOW_UPS``, each one stop that says
  whether it is selected;
- **Notes**, a multi-line ``TextField`` of at most 4000 characters with its counter;
- Cancel and **Save** (``lead.note.save``), and a line when the outbox can't store it.

``use_note_sheet()`` is the Lead scanner's hook: it keeps the lead being noted and the
draft, prefills it from the lead's saved note (``lead_note.saved_note()``), shows the
sheet through ``ft.use_dialog`` and saves through ``lead_note.store()`` and
``confirm()``. Save closes the sheet and says "Note saved", "Note saved. Will sync."
or "Nothing to save" in a SnackBar, unless the screen has gone meanwhile.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace

import flet as ft

from pycon_us import lead_note
from pycon_us.core.lead_notes import FOLLOW_UPS, Interest, LeadNote
from pycon_us.core.lead_sponsors import LeadSponsor
from pycon_us.core.outbox import Outcome
from pycon_us.locations import is_top_view
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.staff import use_staff
from pycon_us.theme import use_tokens
from pycon_us.theme_hc import hc_sheet_shape
from pycon_us.ui.queue_rows import heading, note
from pycon_us.ui.semantics import named, semantics_key

MAX_LENGTH = 4000
"""The note's longest free text, in characters (ux.md §7.3)."""

INTERESTS = {
    Interest.HOT: ("Hot", ft.Icons.LOCAL_FIRE_DEPARTMENT_OUTLINED),
    Interest.WARM: ("Warm", ft.Icons.WB_SUNNY_OUTLINED),
    Interest.COLD: ("Cold", ft.Icons.AC_UNIT),
}
"""Each interest's label and icon: words and a symbol, never an emoji."""

FOLLOW_UP_ICONS = {
    "Send info": ft.Icons.MAIL_OUTLINE,
    "Demo": ft.Icons.SLIDESHOW_OUTLINED,
    "Newsletter": ft.Icons.NEWSPAPER_OUTLINED,
    "Hiring": ft.Icons.WORK_OUTLINE,
    "Partner": ft.Icons.HANDSHAKE_OUTLINED,
}
"""Each follow-up chip's leading icon; Flutter's check mark takes its place once
selected (M3's filter chip)."""

SHEET_COLOR = ft.Colors.SURFACE_CONTAINER_LOW
"""M3's bottom sheet colour, which the unselected chips paint, as the filter sheet's."""


@dataclass(frozen=True)
class Editing:
    """The lead the sheet is open for, and its draft.

    Attributes:
        code: The lead's access code.
        name: The attendee's first name when the result had one, else None.
        draft: The interest and follow-ups as chosen so far, and the text the field
            started with: the field itself holds what is typed since (D-243).
        problem: Why the last Save stored nothing (``lead_note.NOT_SAVED``), or None.
    """

    code: str
    name: str | None
    draft: LeadNote
    problem: str | None = None


def title_of(editing: Editing) -> str:
    """Return the sheet's heading: "Note for Ada", or "Note for MOCK0001"."""
    return f"Note for {editing.name or editing.code}"


def interest_button(
    interest: Interest | None, on_change: ft.ControlEventHandler[ft.SegmentedButton]
) -> ft.Control:
    """Return Hot · Warm · Cold; none selected allowed, so a second tap clears it.

    Each segment is read as its label, a button and its state; its identifier
    (``lead.note.interest.<value>``) is merged into the segment's node, as the Expo's.
    """
    return ft.SegmentedButton(
        segments=[
            ft.Segment(
                value=value.value,
                icon=icon,
                label=ft.Semantics(
                    identifier=f"lead.note.interest.{value.value}",
                    content=ft.Text(label),
                ),
            )
            for value, (label, icon) in INTERESTS.items()
        ],
        selected=[] if interest is None else [interest.value],
        allow_empty_selection=True,
        on_change=on_change,
    )


def follow_up_chip(
    label: str, selected: bool, on_toggle: Callable[[str, bool], object]
) -> ft.Control:
    """Return a follow-up's filter chip: its icon, or the check mark once selected.

    One node with its identifier (``lead.note.follow_up.<key>``), read with its
    label and whether it is selected (Flutter's chip says it).
    """

    @report_errors
    def selected_now(e: ft.Event[ft.Chip]) -> None:
        # Flutter flips the chip and sends its new state before the event (chip.dart).
        on_toggle(label, bool(e.control.selected))

    return named(
        f"lead.note.follow_up.{semantics_key(label)}",
        ft.Chip(
            label=label,
            # Selected, Flutter's check mark alone: over the icon it read as a box.
            leading=None
            if selected
            else ft.Icon(FOLLOW_UP_ICONS[label], size=18, apply_text_scaling=True),
            selected=selected,
            show_checkmark=True,
            bgcolor=SHEET_COLOR,  # a chip paints `surface` otherwise (filter sheet)
            on_select=selected_now,
        ),
    )


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
        open: Opens the sheet for a lead: its code and the name, if the result had one.
        is_open: The sheet is open: the scan screen pauses scanning meanwhile.
    """

    open: Callable[[str, str | None], None]
    is_open: bool


def use_note_sheet(*, owner: str, sponsor: LeadSponsor | None) -> NoteSheet:
    """Keep the note sheet's lead and draft, show it while open; return what opens it.

    Call it on every render (D-70). The Notes field is built from what Flutter last
    reported (D-243), through a ``Ref`` made for each opening, so the prefill is sent
    once and typing is never sent back over.

    Args:
        owner: The signed-in account (``Account.owner``).
        sponsor: The sponsor a staff account scans for now; None for a sponsor's own.
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    staff = use_staff()
    prefs = use_prefs()
    tokens = use_tokens()
    editing, set_editing = ft.use_state(not_editing)
    is_open = editing is not None
    field = ft.use_memo(ft.Ref[ft.TextField], [is_open])  # a fresh one each opening
    mounted = ft.use_ref(True)  # cleared on unmount: a late SnackBar is then dropped

    @report_errors
    def unmount() -> None:
        """Mark the screen gone, so a save still waiting stays quiet."""
        mounted.current = False

    ft.use_effect(lambda: None, [], cleanup=unmount)

    @report_errors
    def open_for(code: str, name: str | None) -> None:
        draft = lead_note.saved_note(svc.outbox, owner, code)
        set_editing(Editing(code, name, draft))

    @report_errors
    def close() -> None:
        set_editing(None)

    @report_errors
    def interest(e: ft.Event[ft.SegmentedButton]) -> None:
        chosen = e.control.selected
        value = Interest(chosen[0]) if chosen else None
        set_editing(lambda last: redraft(last, interest=value))

    @report_errors
    def follow_up(label: str, selected: bool) -> None:
        set_editing(lambda last: toggled(last, label, selected))

    @report_errors
    async def save() -> None:
        if editing is None:
            return
        typed = field.current.value if field.current is not None else None
        draft = replace(editing.draft, text=typed or "")
        stored = lead_note.store(
            svc.outbox, editing.code, draft, owner=owner, sponsor=sponsor
        )
        if stored is None or svc.outbox is None:  # logged (D-120); the text stays
            set_editing(replace(editing, problem=lead_note.NOT_SAVED))
            return
        set_editing(None)  # scanning resumes while the note syncs
        words = lead_note.NOTHING_TO_SAVE
        if stored.outcome is not Outcome.IGNORED and stored.row is not None:
            words = await lead_note.confirm(
                svc.outbox, staff, svc.kick_sync, stored.row
            )
        if mounted.current and is_top_view(page.route, view_path):
            page.show_dialog(
                ft.SnackBar(ft.Text(words), behavior=ft.SnackBarBehavior.FLOATING)
            )

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
