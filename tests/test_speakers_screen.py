"""Tests for the Speakers screen's list and its filter field (#98; SPKR-01, D-153).

The screen runs in `tests/speakers_view.py`'s harness.
"""

from typing import cast

import flet as ft

from pycon_us.core.speakers import letter_groups
from pycon_us.screens import speakers as screen
from tests import speakers_view
from tests.speakers_view import ALL, Shown, _under

render, shown, focused = (
    speakers_view.render,
    speakers_view.shown,
    speakers_view.focused,
)


# ------------------------------------------------------------------ the screen


async def test_the_list_shows_every_speaker_once_without_paging(shown: Shown) -> None:
    """The list shows every speaker once, each row and letter section rendered once."""
    assert shown.listed == [entry.speaker.id for entry in ALL]
    assert sorted(shown.rows) == sorted(entry.speaker.id for entry in ALL)
    assert shown.sections == [group.letter for group in letter_groups(ALL)]


async def test_a_keystroke_re_renders_no_row_that_stays(shown: Shown) -> None:
    """D-153: the rows found are unchanged, so their bodies are skipped (F34)."""
    shown.rows.clear()
    shown.sections.clear()
    await shown.type("cristian")
    (cristian,) = [e for e in ALL if e.speaker.name.startswith("Cristián")]
    assert shown.listed == [cristian.speaker.id]
    assert shown.rows == []
    assert shown.sections == ["C"]  # its section changed; the others went
    assert shown.text_field.value == "cristian"  # controlled: the text stays (D-157)

    shown.sections.clear()
    await shown.type("cristian ")  # the same speakers: nothing re-renders
    assert (shown.rows, shown.sections) == ([], [])


async def test_a_filter_that_finds_nothing_offers_to_clear_it(
    shown: Shown, focused: list[ft.TextField]
) -> None:
    """A filter that finds nothing says so in a live region and offers to clear it.

    Clearing lists every speaker again and gives the field the focus.
    """
    await shown.type("zzz")
    assert shown.listed == []
    state = shown.node("speakers.no_match")
    assert state.live_region
    (button,) = [b for b in shown.find(ft.FilledTonalButton) if b.parent is not None]
    assert button.content == screen.CLEAR_FILTER

    await shown.click(button)
    assert shown.text_field.value == ""
    assert len(shown.listed) == len(ALL)
    # The button went: the field takes the focus.
    assert [f._i for f in focused] == [shown.text_field._i]


async def test_the_fields_clear_button_shows_only_with_text(
    shown: Shown, focused: list[ft.TextField]
) -> None:
    """The field's clear button shows only with text, over the field and not in it.

    A tap clears the text, hides the button and gives the field the focus.
    """

    def clear_buttons() -> list[ft.IconButton]:
        return [b for b in shown.find(ft.IconButton) if b.parent is not None]

    assert clear_buttons() == []
    await shown.type("ana")
    (clear,) = clear_buttons()
    assert clear.tooltip == screen.CLEAR_FILTER  # its accessible name (D-27)
    # Over the field, not in it: the field's merged node would swallow it.
    assert not _under(clear, shown.node("speakers.filter"))

    await shown.click(clear)
    assert shown.text_field.value == ""
    assert clear_buttons() == []
    # The button went: the field takes the focus.
    assert [f._i for f in focused] == [shown.text_field._i]


async def test_the_filter_field_is_named_and_identified(shown: Shown) -> None:
    """The filter field is identified, named by its hint or, with text, by its label."""
    node = shown.node("speakers.filter")
    assert node.content is shown.text_field
    assert shown.text_field.hint_text == screen.FILTER_HINT
    # The hint names the empty field; it leaves the semantics tree once there is
    # text, and the node's label takes over, never both at once (read twice).
    assert node.label is None
    assert isinstance(node.parent, ft.MergeSemantics)  # one node with the field's
    await shown.type("mu")
    assert shown.node("speakers.filter").label == screen.FILTER_HINT
    await shown.type("")
    assert shown.node("speakers.filter").label is None


async def test_the_filter_field_never_fixes_names(shown: Shown) -> None:
    """The filter field has autocorrect and suggestions off, so names stay as typed."""
    assert shown.text_field.autocorrect is False
    assert shown.text_field.enable_suggestions is False  # Android's own switch


async def test_the_filter_field_has_no_line_even_when_focused(shown: Shown) -> None:
    """ux.md §5.7: a pill like Material's search bar, not the theme's focus ring."""
    border = cast(dict[ft.ControlState, ft.OutlineInputBorder], shown.text_field.border)
    assert border.keys() == {ft.ControlState.DEFAULT, ft.ControlState.FOCUSED}
    for state in border.values():
        assert state.side == ft.BorderSide(0, ft.Colors.TRANSPARENT)
        assert state.border_radius == 28


async def test_a_filter_says_how_many_it_found_in_a_live_region(shown: Shown) -> None:
    """A filter counts the speakers it found, in words, in a live region.

    Without a filter there is no count, and a miss leaves the announcing to the no-match
    state.
    """

    def counted() -> list[ft.Semantics]:
        return [
            s
            for s in shown.find(ft.Semantics)
            if s.identifier == "speakers.count" and s.parent is not None
        ]

    assert counted() == []  # no filter: nothing to count
    await shown.type("mu")
    (count,) = counted()
    assert count.live_region
    found = len(shown.listed)
    assert found > 1
    assert cast(ft.Text, cast(ft.Container, count.content).content).value == (
        f"{found} speakers"
    )
    await shown.type("mike müller")
    (count,) = counted()
    assert cast(ft.Text, cast(ft.Container, count.content).content).value == (
        "1 speaker"
    )
    await shown.type("zzz")  # a miss: the no-match state announces itself
    assert counted() == []
