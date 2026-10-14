"""The text fields screens share: ``SearchField``, the pill that search and filters use.

One look and one behaviour for every field that narrows a list as the user types: the
Speakers and Sprints filters (D-189, D-202) and the global search (D-193). A pill on
``surface_container_high`` without a line, focused or not, like Material's search bar
(ux.md §3.6), pinned above its list so it is always in reach, with a Clear button once
there is text. ``use_field_query()`` holds the field's text, its ``Ref`` and the Clear
that puts the focus back in it, and ``found_count()`` is the live line under the field
that says what the text found (D-226).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import flet as ft

from pycon_us.services.errors import report_errors


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

    Controlled (D-157): its value is the screen's state, which ``on_change`` sets, so a
    re-render never wipes what the user typed (F33). Autocorrect and Android's
    suggestions are off: they would "fix" names and identifiers (``asyncio``).

    The hint names the field only while it is empty, so the field's semantics node is
    merged with ``label`` once there is text. A merge takes in every descendant, so the
    Clear button lies over the field, in a ``Stack``, rather than inside it as its
    suffix, where it would stop being a button of its own (D-189).

    Args:
        value: The text as typed.
        on_change: Sets the screen's state from the field.
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
    clear_button = ft.IconButton(
        ft.Icons.CLOSE, tooltip=clear_tooltip, on_click=on_clear, right=4
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
    """A ``SearchField``'s state and handlers for one render, from ``use_field_query()``.

    Attributes:
        value: The text as typed, the field's ``value``.
        ref: This render's ``Ref``, the field's ``ref``.
        changed: The field's ``on_change``: sets ``value`` from the field.
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
    """Return a ``SearchField``'s controlled text, its ``Ref`` and its Clear (a hook).

    A plain function that calls hooks, so the screen calls it once per render, before
    any early return (D-70). The text is state its ``changed`` sets at every keystroke,
    so a re-render never wipes it (D-157). Each render gets a fresh ``Ref``, as Flet's
    declarative examples do: it holds this render's field, the one this render's
    handlers act on. A Clear goes away once the text is empty, so ``clear()`` puts the
    focus back in the field, ready to type again, rather than lose a screen reader's
    place (D-182). A screen that keeps more state with the text (search's
    ``ViewMemory``, D-193) wraps ``changed`` and ``clear`` in handlers of its own.

    Args:
        initial: The text the field starts with (search's remembered query).
    """
    value, set_value = ft.use_state(initial)
    ref: ft.Ref[ft.TextField] = ft.Ref()

    @report_errors
    def changed(e: ft.Event[ft.TextField]) -> None:
        set_value(e.control.value)

    @report_errors
    async def focus() -> None:
        if ref.current is not None:  # None until the field has been built
            await ref.current.focus()

    @report_errors
    async def clear() -> None:
        set_value("")
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
