"""The text fields screens share: ``SearchField``, the pill that search and filters use.

One look and one behaviour for every field that narrows a list as the user types: the
Speakers filter (D-189) and the global search (D-191). A pill on
``surface_container_high`` without a line, focused or not, like Material's search bar
(ux.md §3.6), pinned above its list so it is always in reach, with a Clear button once
there is text.
"""

from collections.abc import Callable
from typing import Any

import flet as ft


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
        on_clear: Empties the field; the caller puts the focus back in it, since the
            Clear button goes away when used (D-182).
        ref: Set to the field, for the caller's ``focus()``.
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
                hint_max_lines=2,  # wraps at the largest text instead of clipping
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
