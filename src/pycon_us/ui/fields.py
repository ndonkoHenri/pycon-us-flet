"""The text fields screens share: ``SearchField``, the pill that search and filters use.

One look and one behaviour for every field that narrows a list as the user types: the
Speakers and Sprints filters (D-189, D-202) and the global search (D-193). A pill on
``surface_container_high`` without a line, focused or not, like Material's search bar
(ux.md §3.6), pinned above its list so it is always in reach, with a Clear button once
there is text. ``use_field_query()`` holds the field's text, its ``Ref`` and the Clear
that puts the focus back in it, and keeps the field in step with what the screen
filters by however fast the keys come (D-243); ``found_count()`` is the live line under
the field that says what the text found (D-226).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import flet as ft

from pycon_us.services.errors import report_errors
from pycon_us.ui.semantics import merged


def SearchField(
    *,
    value: str,
    on_change: ft.ControlEventHandler[ft.TextField],
    on_clear: Callable[[], Any],
    ref: ft.Ref[ft.TextField],
    hint: str,
    label: str,
    clear_tooltip: str,
    identifier: str,
    autofocus: bool = False,
    on_submit: ft.ControlEventHandler[ft.TextField] | None = None,
    keyboard_type: ft.KeyboardType = ft.KeyboardType.TEXT,
) -> ft.Control:
    """Return a pill-shaped search or filter field with its Clear button.

    Controlled (D-157) through ``use_field_query()``: its value is what Flutter last
    reported, so a re-render never wipes what the user typed (F33) nor sends an older
    keystroke's text back over it (D-243). Autocorrect and Android's suggestions are
    off: they would "fix" names and identifiers (``asyncio``).

    The hint names the field only while it is empty, so the field's semantics node is
    merged with ``label`` once there is text. A merge takes in every descendant, so the
    Clear button lies over the field, in a ``Stack``, rather than inside it as its
    suffix, where it would stop being a button of its own (D-189).

    Args:
        value: The text, ``FieldQuery.value``.
        on_change: Re-renders the screen with the typed text.
        on_clear: Empties the field and puts the focus back in it, since the Clear
            button goes away when used (D-182): ``use_field_query()``'s ``clear``.
        ref: Set to the field, for that ``focus()``.
        hint: The hint while the field is empty, which is also its name then.
        label: The field's name for screen readers once it holds text.
        clear_tooltip: The Clear button's tooltip, its accessible name (D-27).
        identifier: The field's semantics identifier, ``<screen>.<element>``.
        autofocus: Focus the field, and open the keyboard, when the View shows.
        on_submit: Called when the keyboard's action key is pressed.
        keyboard_type: The keyboard to show.
    """
    pill = ft.OutlineInputBorder(
        border_radius=28,  # full radius, as search fields have
        side=ft.BorderSide(0, ft.Colors.TRANSPARENT),
    )
    text_field = ft.MergeSemantics(
        ft.Semantics(
            identifier=identifier,
            # Not while empty: the hint names the field then, and both would read it.
            label=label if value else None,
            content=ft.TextField(
                ref=ref,
                value=value,
                on_change=on_change,
                on_submit=on_submit,
                autofocus=autofocus,
                keyboard_type=keyboard_type,
                hint_text=hint,
                # While empty the hint wraps at the largest text instead of clipping;
                # with text it is hidden but still laid out, and two lines kept a
                # blank line under the text at the largest size.
                hint_max_lines=1 if value else 2,
                prefix_icon=ft.Icons.SEARCH,
                # Room for the Clear button above it, so text never runs under it.
                suffix_icon=ft.Container(width=48, height=48) if value else None,
                filled=True,
                fill_color=ft.Colors.SURFACE_CONTAINER_HIGH,
                # The focused entry too: else the theme draws a 2 dp primary ring.
                border={ft.ControlState.DEFAULT: pill, ft.ControlState.FOCUSED: pill},
                autocorrect=False,
                enable_suggestions=False,
            ),
        )
    )
    # Merged, so the tooltip names the button's own node (F55, D-234); placed in
    # the Stack by a Container, since a MergeSemantics takes no position.
    clear_button = ft.Container(
        merged(ft.IconButton(ft.Icons.CLOSE, tooltip=clear_tooltip, on_click=on_clear)),
        right=4,
    )
    return ft.Container(
        ft.Stack(
            [text_field, *([clear_button] if value else [])],
            alignment=ft.Alignment.CENTER_RIGHT,  # the button, level with the text
            fit=ft.StackFit.PASS_THROUGH,  # the field keeps the screen's width
        ),
        padding=ft.Padding.only(left=16, top=8, right=16, bottom=4),
    )


@dataclass(frozen=True, eq=False)
class FieldQuery:
    """A ``SearchField``'s text and handlers for one render, from ``use_field_query()``.

    Attributes:
        value: The text the field shows, which the screen filters or searches by
            and passes as the field's ``value``: one value for both, so they never
            part (D-243).
        ref: The field's ``ref``; one ``Ref`` for the screen's life (D-243).
        changed: The field's ``on_change``: re-renders with the typed text.
        clear: The field's ``on_clear``, and a no-match state's "Clear …": empties the
            text, then puts the focus back in the field.
        focus: Puts the focus in the field, for another control that goes away when
            used (search's "Show all results").
    """

    value: str
    ref: ft.Ref[ft.TextField]
    changed: Callable[[ft.Event[ft.TextField]], None]
    clear: Callable[[], Awaitable[None]]
    focus: Callable[[], Awaitable[None]]


def use_field_query(initial: str = "") -> FieldQuery:
    """Return a ``SearchField``'s text, its ``Ref`` and its Clear (a hook).

    A plain function that calls hooks, so the screen calls it once per render, before
    any early return (D-70). The field stays controlled (D-157), but by what Flutter
    last reported, never by an older keystroke (D-243, F63): Flutter's reports of the
    typed text update the field the last render built as soon as they arrive, while
    the change events and re-renders that follow run later. A render built from the
    text of an earlier event would differ from that report, and the diff would send
    the older text back over what the user typed since. So each render reads the text
    from that field, through a ``Ref`` kept for the screen's life, and the diff sends
    nothing; only the initial text and a Clear are sent to the field. ``changed``
    still sets state, which is what re-renders the screen at each keystroke.

    A Clear goes away once the text is empty, so ``clear()`` puts the focus back in
    the field, ready to type again, rather than lose a screen reader's place (D-182).
    A screen that keeps more state with the text (search's ``ViewMemory``, D-193)
    wraps ``changed`` and ``clear`` in handlers of its own.

    Args:
        initial: The text the field starts with (search's remembered query).
    """
    typed, set_typed = ft.use_state(initial)
    # Counted rather than flagged: each Clear re-renders, even when the state is
    # already empty, and is sent to the field exactly once.
    clears, set_clears = ft.use_state(0)
    sent_clears = ft.use_ref(0)
    ref = ft.use_memo(ft.Ref[ft.TextField], [])  # one for the screen's life
    shown = ref.current  # the field the last render built, None until the first
    if shown is None or clears != sent_clears.current:
        sent_clears.current = clears
        value = typed  # the initial text, or Clear's "": the diff sends it
    else:
        value = shown.value  # what Flutter last reported: the diff sends nothing

    @report_errors
    def changed(e: ft.Event[ft.TextField]) -> None:
        set_typed(e.control.value)

    @report_errors
    async def focus() -> None:
        if ref.current is not None:  # None until the field has been built
            await ref.current.focus()

    @report_errors
    async def clear() -> None:
        set_typed("")
        set_clears(lambda n: n + 1)
        await focus()

    return FieldQuery(value=value, ref=ref, changed=changed, clear=clear, focus=focus)


def found_count(line: str, *, identifier: str) -> ft.Control:
    """Return the line under a field that says what it found, a polite live region.

    A filter or a search changes the list at every keystroke or pause: the live region
    lets a screen reader hear what typing did without leaving the field (ux.md §9).
    The caller shows it only while the text finds something; a miss has its no-match
    state, which announces itself. ``BODY_SMALL`` in ``on_surface_variant``, 16 dp from
    the sides, 4 dp under what is above it and 8 dp over the list, which scrolls under
    the pinned line and so never touches it (D-226).

    Args:
        line: What was found, "5 speakers" or "12 sessions, 3 speakers".
        identifier: Its semantics identifier, ``<screen>.count``.
    """
    return ft.Semantics(
        live_region=True,
        identifier=identifier,
        content=ft.Container(
            ft.Text(
                line,
                theme_style=ft.TextThemeStyle.BODY_SMALL,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            padding=ft.Padding.only(left=16, top=4, right=16, bottom=8),
        ),
    )
