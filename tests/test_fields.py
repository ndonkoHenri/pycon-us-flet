"""The shared field pieces: ``use_field_query()`` and ``found_count()`` (D-226).

Search, Speakers and Sprints each test their own filter end to end; these tests pin
the shared behaviour once, in a real Flet session (``tests/sessions.py``) with a probe
component that renders a ``SearchField`` from the hook, as the screens do. The session
records the texts it sends to the field, so a burst of keystrokes can be played as a
busy host delivers it: Flutter's reports, the change events and the re-renders
interleaved (D-243).
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, cast

import flet as ft
import pytest
from flet.messaging.protocol import Message, PatchControlBody
from flet.messaging.session import Session

from pycon_us.ui.fields import SearchField, found_count, use_field_query
from tests.sessions import connection, find, rendering, settle

CLEAR = "Clear filter"


@dataclass
class Probe:
    """A component that renders a ``SearchField`` from ``use_field_query()``.

    Attributes:
        initial: The text the hook starts with.
        renders: How many times the component rendered.
        filtered: The text each render would filter by, in order.
    """

    initial: str = ""
    renders: int = 0
    filtered: list[str] = field(default_factory=list)

    def root(self) -> ft.Control:
        """Return the probe: the field, then a Show all and a Clear all button."""

        @ft.component
        def Filter() -> ft.Control:
            self.renders += 1
            query = use_field_query(self.initial)
            self.filtered.append(query.value)
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
                    # A no-match state's "Clear filter", there whatever the text.
                    ft.TextButton("Clear all", on_click=query.clear),
                ]
            )

        return Filter()


def recording() -> tuple[Session, list[str]]:
    """Return a session, and the texts its patches send to a field, in order."""
    sent: list[str] = []
    conn = connection()

    def send(message: Message) -> None:
        if isinstance(message.body, PatchControlBody):
            # An operation is [kind, node, property, value]; the probe's only
            # control with a ``value`` is the field.
            ops: list[Any] = message.body.patch[1:]
            sent.extend(op[3] for op in ops if len(op) == 4 and op[2] == "value")

    conn.send_message = send  # pyright: ignore[reportAttributeAccessIssue]
    return Session(conn), sent


@dataclass
class Shown:
    """The probe on a page, with what its field was asked to focus and was sent."""

    session: Session
    probe: Probe
    focused: list[ft.TextField]
    sent: list[str] = field(default_factory=list)
    """The texts sent to the field after the first render."""

    @property
    def text_field(self) -> ft.TextField:
        """The probe's one ``TextField``, from the session's current tree."""
        (text_field,) = find(self.session, ft.TextField)
        return text_field

    def clear_buttons(self) -> list[ft.IconButton]:
        """Return the page's Clear icon buttons, found by their tooltip."""
        return find(self.session, ft.IconButton, lambda b: b.tooltip == CLEAR)

    def text_button(self, text: str) -> ft.TextButton:
        """Return the one ``TextButton`` whose content is ``text``."""
        (button,) = find(self.session, ft.TextButton, lambda b: b.content == text)
        return button

    async def type(self, text: str) -> None:
        """Type into the field as Flutter reports it: the value, then the event."""
        self.report(text)
        await self.session.dispatch_event(self.text_field._i, "change", None)
        await settle()

    def report(self, text: str) -> None:
        """Apply Flutter's report of the field's text, as Flet does when it arrives."""
        self.session.apply_patch(self.text_field._i, {"value": text})

    async def burst(self, *texts: str) -> None:
        """Type ``texts`` faster than the screen re-renders (#307).

        Flet applies each report as it arrives and runs each change event as a task
        of its own, so on a busy host a re-render for one keystroke can run after
        the next keystroke's report: each report here lands after the event before
        it has run, and before the re-render that event asked for.
        """
        for text in texts:
            self.report(text)
            await asyncio.sleep(0)  # the previous event's re-render has not run
            # As Flet's transport does: the event in a task of its own.
            asyncio.get_running_loop().create_task(
                self.session.dispatch_event(self.text_field._i, "change", None)
            )
            await asyncio.sleep(0)  # the event runs and asks for a re-render
        await settle()

    async def click(self, control: ft.Control) -> None:
        """Click ``control`` as Flutter reports it, then let the session settle."""
        await self.session.dispatch_event(control._i, "click", None)
        await settle()


@pytest.fixture
def answer() -> asyncio.Event:
    """Flutter's answer to a focus request: given at once, unless a test clears it."""
    given = asyncio.Event()
    given.set()
    return given


@pytest.fixture
def focused(
    monkeypatch: pytest.MonkeyPatch, answer: asyncio.Event
) -> list[ft.TextField]:
    """The fields asked to take the focus; the harness has no Flutter to answer."""
    asked: list[ft.TextField] = []

    async def focus(self: ft.TextField) -> None:
        # As the real one, which invokes the method through the field's page.
        assert self.page is not None, "the field is not on the page"
        asked.append(self)
        await answer.wait()

    monkeypatch.setattr(ft.TextField, "focus", focus)
    return asked


@pytest.fixture
async def shown(focused: list[ft.TextField]) -> AsyncIterator[Shown]:
    """The probe on a recording page, with the first render's sends dropped."""
    probe = Probe()
    session, sent = recording()
    async with rendering(probe.root, session):
        sent.clear()  # the first render's page
        yield Shown(session, probe, focused, sent)


async def test_the_field_keeps_what_was_typed_across_re_renders(shown: Shown) -> None:
    """D-157: the text is the hook's state, so a re-render never wipes it (F33)."""
    await shown.type("py")
    await shown.type("pyt")
    assert shown.text_field.value == "pyt"
    assert shown.probe.renders == 3  # each keystroke re-rendered with its text


async def test_typing_never_sends_the_text_back_to_the_field(shown: Shown) -> None:
    """D-243: Flutter holds what was typed; a re-render that sent it back could race."""
    await shown.type("p")
    await shown.type("py")
    assert shown.sent == []
    assert shown.probe.filtered[-1] == "py"


async def test_a_burst_of_keys_leaves_the_field_and_the_filter_in_step(
    shown: Shown,
) -> None:
    """#307: a re-render for an earlier key never rewrites a later one in the field.

    Before D-243 the re-render for "ch", run after Flutter had reported "che", sent
    "ch" back and Flutter showed it; the last re-render then sent nothing, since the
    state and the last report agreed on "chen", so the field kept "ch" under a list
    filtered by "chen".
    """
    await shown.burst("c", "ch", "che", "chen")
    assert shown.sent == []  # nothing rewrote what Flutter shows
    assert shown.text_field.value == "chen"
    assert shown.probe.filtered[-1] == "chen"
    # Each re-render filtered by what the field showed then, never by older text.
    assert all("chen".startswith(text) for text in shown.probe.filtered)


async def test_clear_sends_the_empty_text_once(shown: Shown) -> None:
    """A Clear sends the empty text once; then a key sends nothing and filters by it."""
    await shown.type("py")
    (clear,) = shown.clear_buttons()
    await shown.click(clear)
    assert shown.sent == [""]
    await shown.type("x")  # the next key starts from the empty field
    assert shown.sent == [""]
    assert shown.probe.filtered[-1] == "x"


async def test_clear_empties_a_field_whose_text_the_screen_has_not_seen(
    shown: Shown,
) -> None:
    """A Clear tapped before the last key's event ran still empties the field.

    The text is then still empty in state, so setting it again would not re-render:
    each Clear re-renders on its own, and sends the empty text.
    """
    shown.report("py")  # Flutter's report arrived; its change event has not run
    await shown.click(shown.text_button("Clear all"))
    assert shown.sent == [""]
    assert shown.text_field.value == ""
    assert shown.probe.filtered[-1] == ""


async def test_a_key_typed_while_a_clear_lands_is_dropped_with_the_field(
    shown: Shown, answer: asyncio.Event
) -> None:
    """#307: Flutter puts the Clear over a key typed before the empty text arrived.

    Its report comes in after the empty text was sent and before Flutter answers the
    focus request that followed it; the screen drops it, as Flutter did, and sends
    the empty text again over what the report left on the field.
    """
    await shown.type("mu")
    answer.clear()  # Flutter has not had the empty text yet
    (clear,) = shown.clear_buttons()
    await shown.click(clear)
    assert shown.sent == [""]
    await shown.type("mumu")  # typed on the old text, before the Clear landed
    answer.set()
    await settle()
    assert shown.sent == ["", ""]
    assert shown.text_field.value == ""
    assert shown.probe.filtered[-1] == ""
    assert shown.clear_buttons() == []
    await shown.type("x")  # once landed, keys count again
    assert shown.probe.filtered[-1] == "x"
    assert shown.sent == ["", ""]


async def test_keys_reported_before_a_clear_renders_are_dropped(
    shown: Shown, answer: asyncio.Event
) -> None:
    """#307: keys typed right after Clear, on the old text, are dropped as Flutter does.

    Seen on the simulator with slow renders: Clear, then "sweigart" in one burst,
    whose reports all came in before the Clear's re-render; the field and the list
    must both end empty, never one empty and the other on the keys.
    """
    await shown.type("chen")
    (clear,) = shown.clear_buttons()
    answer.clear()  # all of it reaches Flutter before the empty text does
    await shown.session.dispatch_event(clear._i, "click", None)  # no re-render yet
    await shown.burst("chens", "chensw", "chenswe")
    answer.set()
    await settle()
    assert shown.text_field.value == ""
    assert shown.probe.filtered[-1] == ""
    assert set(shown.sent) == {""}  # only ever the empty text


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
    """Show all, which only moves the focus, focuses the field and keeps its text."""
    await shown.type("py")
    await shown.click(shown.text_button("Show all"))
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


def field_of(control: ft.Control) -> ft.TextField:
    """Return the ``TextField`` inside a ``SearchField``'s pill."""
    stack = cast(ft.Stack, cast(ft.Container, control).content)
    merge = cast(ft.MergeSemantics, stack.controls[0])
    return cast(ft.TextField, cast(ft.Semantics, merge.content).content)


@pytest.mark.parametrize(
    ("on_submit", "action"),
    [(lambda e: None, ft.TextInputAction.SEARCH), (None, None)],
    ids=["searches", "filters"],
)
def test_the_action_key_is_search_only_on_a_field_that_submits(
    on_submit: ft.ControlEventHandler[ft.TextField] | None,
    action: ft.TextInputAction | None,
) -> None:
    """U30: a field that searches on its action key shows Search; a filter keeps Done."""
    pill = SearchField(
        value="",
        on_change=lambda e: None,
        on_clear=lambda: None,
        ref=ft.Ref[ft.TextField](),
        hint="Search",
        label="Search",
        clear_tooltip=CLEAR,
        identifier="probe.field",
        on_submit=on_submit,
    )
    assert field_of(pill).text_input_action is action


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
