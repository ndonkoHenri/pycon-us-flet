"""The shared field pieces: ``use_field_query()`` and ``found_count()`` (D-226).

Search, Speakers and Sprints each test their own filter end to end; these tests pin
the shared behaviour once, in a real Flet session (``tests/sessions.py``) with a probe
component that renders a ``SearchField`` from the hook, as the screens do.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import cast

import flet as ft
import pytest
from flet.messaging.session import Session

from pycon_us.ui.fields import SearchField, found_count, use_field_query
from tests.sessions import find, rendering, settle

CLEAR = "Clear filter"


@dataclass
class Probe:
    """A component that renders a ``SearchField`` from ``use_field_query()``.

    Attributes:
        initial: The text the hook starts with.
        renders: How many times the component rendered.
    """

    initial: str = ""
    renders: int = 0

    def root(self) -> ft.Control:
        @ft.component
        def Filter() -> ft.Control:
            self.renders += 1
            query = use_field_query(self.initial)
            return ft.Column(
                [
                    SearchField(
                        value=query.value,
                        on_change=query.changed,
                        on_clear=query.clear,
                        ref=query.ref,
                        hint="Filter things",
                        label="Filter things",
                        clear_tooltip=CLEAR,
                        identifier="probe.filter",
                    ),
                    # Another control that goes away when used, as search's
                    # "Show all results" does: it only moves the focus.
                    ft.TextButton("Show all", on_click=query.focus),
                ]
            )

        return Filter()


@dataclass
class Shown:
    """The probe on a page, with what its field was asked to focus."""

    session: Session
    probe: Probe
    focused: list[ft.TextField]

    @property
    def text_field(self) -> ft.TextField:
        (text_field,) = find(self.session, ft.TextField)
        return text_field

    def clear_buttons(self) -> list[ft.IconButton]:
        return find(self.session, ft.IconButton, lambda b: b.tooltip == CLEAR)

    async def type(self, text: str) -> None:
        """Type into the field as Flutter reports it: the value, then the event."""
        text_field = self.text_field
        self.session.apply_patch(text_field._i, {"value": text})
        await self.session.dispatch_event(text_field._i, "change", None)
        await settle()

    async def click(self, control: ft.Control) -> None:
        await self.session.dispatch_event(control._i, "click", None)
        await settle()


@pytest.fixture
def focused(monkeypatch: pytest.MonkeyPatch) -> list[ft.TextField]:
    """The fields asked to take the focus; the harness has no Flutter to answer."""
    asked: list[ft.TextField] = []

    async def focus(self: ft.TextField) -> None:
        # As the real one, which invokes the method through the field's page.
        assert self.page is not None, "the field is not on the page"
        asked.append(self)

    monkeypatch.setattr(ft.TextField, "focus", focus)
    return asked


@pytest.fixture
async def shown(focused: list[ft.TextField]) -> AsyncIterator[Shown]:
    probe = Probe()
    async with rendering(probe.root) as session:
        yield Shown(session, probe, focused)


async def test_the_field_keeps_what_was_typed_across_re_renders(shown: Shown) -> None:
    """D-157: the text is the hook's state, so a re-render never wipes it (F33)."""
    await shown.type("py")
    await shown.type("pyt")
    assert shown.text_field.value == "pyt"
    assert shown.probe.renders == 3  # each keystroke re-rendered with its text


async def test_clear_empties_the_field_and_puts_the_focus_back_in_it(
    shown: Shown,
) -> None:
    """D-182: the Clear button goes away when used, so the field takes the focus."""
    assert shown.clear_buttons() == []  # nothing to clear yet
    await shown.type("py")
    (clear,) = shown.clear_buttons()
    await shown.click(clear)
    assert shown.text_field.value == ""
    assert shown.clear_buttons() == []
    # This render's field: the Ref is the one the clicked render built.
    assert [f._i for f in shown.focused] == [shown.text_field._i]


async def test_focus_moves_the_focus_to_the_field_and_keeps_the_text(
    shown: Shown,
) -> None:
    await shown.type("py")
    (show_all,) = find(shown.session, ft.TextButton)
    await shown.click(show_all)
    assert shown.text_field.value == "py"
    assert [f._i for f in shown.focused] == [shown.text_field._i]


async def test_the_field_starts_with_the_initial_text(
    focused: list[ft.TextField],
) -> None:
    """Search's remembered query, for a View rebuilt below a result (D-193)."""
    probe = Probe(initial="chen")
    async with rendering(probe.root) as session:
        shown = Shown(session, probe, focused)
        assert shown.text_field.value == "chen"
        assert len(shown.clear_buttons()) == 1


def test_the_count_is_a_live_region_with_its_identifier() -> None:
    """ux.md §9: a screen reader hears what typing found without leaving the field."""
    count = cast(ft.Semantics, found_count("5 speakers", identifier="speakers.count"))
    assert count.live_region
    assert count.identifier == "speakers.count"
    line = cast(ft.Text, cast(ft.Container, count.content).content)
    assert line.value == "5 speakers"
    assert line.theme_style == ft.TextThemeStyle.BODY_SMALL
    assert line.color == ft.Colors.ON_SURFACE_VARIANT


def test_the_count_has_one_padding_on_every_screen() -> None:
    """D-226: 16 dp gutters, 4 dp under the field or chips, 8 dp over the list."""
    count = cast(ft.Semantics, found_count("3 projects", identifier="sprints.count"))
    assert cast(ft.Container, count.content).padding == ft.Padding.only(
        left=16, top=4, right=16, bottom=8
    )
