"""Tests for ``LocationCard`` (#389; DATA-33, MAP-06; ux.md §3.9).

The card runs in a real Flet session (``tests/sessions.py``) over the 2026 ``map.toml``.
Its pulse's waits are held until a test releases them (``tests/timers.py``). How the
thumbnail, the pin and the words look, at 200 % text too, is checked on devices (the
PR); here, what the card says, where it leads, where the pin sits and how it pulses.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.prefs import Prefs
from pycon_us.state import Conference
from pycon_us.ui import location_card as card
from pycon_us.year_map import Pin, Plan
from tests import sessions
from tests.timers import HeldSleeps
from tests.trees import texts

YEAR = load_year(2026)
VIEW = "/more/help"
"""The View the card is on: Help & safety, where P2-58 puts the Information desk."""

IDENTIFIER = "help.location"


def place(key: str) -> tuple[Plan, Pin]:
    """Return a pin of the 2026 ``map.toml`` and the plan it is on."""
    pin = YEAR.map.pin(key)
    assert pin is not None
    plan = YEAR.map.plan(pin.plan)
    assert plan is not None
    return plan, pin


@dataclass
class Card(sessions.Shown):
    """The harness's ``Shown`` on one ``LocationCard``."""

    sleeps: HeldSleeps = field(default_factory=HeldSleeps)
    renders: list[Callable[[], None]] = field(default_factory=list)
    """The setter that re-renders the screen around the card."""

    def pins(self) -> list[ft.Stack]:
        """The pins on the thumbnail: the ``Stack``s placed on it."""
        return [s for s in self.find(ft.Stack) if s.left is not None]

    def ring_out(self) -> bool:
        """Whether the pin's ring is out, mid-pulse."""
        (pin,) = self.pins()
        halo = cast(ft.Container, pin.controls[0])
        return halo.scale == card.RING_SCALE

    async def until_held(self, *, timeout: float = 30.0) -> None:
        """Settle until the pulse waits on a held sleep, or fail after ``timeout`` s."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while self.sleeps.held != 1:
            assert loop.time() < deadline, "the pin did not start its pulse"
            await asyncio.sleep(0.01)
        await self.settle()

    async def re_render(self) -> None:
        """Re-render the screen around the card, as a minute tick or a store would."""
        self.renders[0]()
        await self.settle()


type Render = Callable[..., Awaitable[Card]]


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Yield a function that shows a ``LocationCard`` on ``VIEW`` and returns its ``Card``.

    The pin, the plan-only form, reduced motion, large text and the View's pulsed
    pins can be set; the pulse's
    waits are held.
    """
    sleeps = HeldSleeps()
    monkeypatch.setattr(card, "asyncio", sleeps)  # the card module's name only

    async def show(
        stack: AsyncExitStack,
        key: str | None = "info-desk",
        *,
        plan_id: str = "concourse",
        reduce_motion: bool = False,
        large_text: bool = False,
        seen: set[str] | None = None,
    ) -> Card:
        renders: list[Callable[[], None]] = []
        if key is None:
            plan, pin = YEAR.map.plan(plan_id), None
            assert plan is not None
        else:
            plan, pin = place(key)

        @ft.component
        def Screen() -> ft.Control:
            count, set_count = ft.use_state(0)
            renders[:] = [lambda: set_count(count + 1)]
            return ft.Column(
                [
                    card.LocationCard(plan, pin, identifier=IDENTIFIER, seen=seen),
                    ft.Text(f"{count}"),
                ]
            )

        def make(*args: Any, **kwargs: Any) -> Card:
            return Card(*args, sleeps=sleeps, renders=renders, **kwargs)

        return await stack.enter_async_context(
            sessions.showing(
                Screen,
                year=YEAR,
                conference=Conference(),
                tmp_path=tmp_path,
                monkeypatch=monkeypatch,
                view_path=VIEW,
                prefs=Prefs(
                    loaded=True, reduce_motion=reduce_motion, time_above=large_text
                ),
                kind=make,
            )
        )

    async with AsyncExitStack() as stack:

        async def opened(*args: Any, **kwargs: Any) -> Card:
            return await show(stack, *args, **kwargs)

        yield opened


async def test_the_information_desk_card_is_one_button_that_says_where_it_leads(
    render: Render,
) -> None:
    """P2-58's card: one node named for the place and the floor, its words under it."""
    shown = await render("info-desk")
    node = shown.node(IDENTIFIER)
    assert node.label == "Show Information desk on the Concourse level floor plan"
    assert node.button
    assert node.exclude_semantics  # the thumbnail and the words say nothing more
    assert isinstance(node.parent, ft.Container)
    assert texts(node) == [
        "Information desk",
        "Promenade Lobby (Main Entrance)",
        "Concourse level",
    ]
    (image,) = shown.find(ft.Image)
    assert image.src == "maps/2026/concourse-thumb.webp"
    assert (image.width, image.height) == card.thumb_size(place("info-desk")[0])
    assert image.width == card.THUMB_DP


async def test_a_tap_pushes_the_floor_viewer_at_the_pin(render: Render) -> None:
    """The card's tap pushes ``plan/<plan>?pin=<key>`` on its own View."""
    shown = await render("info-desk")
    (tap,) = [c for c in shown.find(ft.Container) if c.on_click]
    await shown.click(tap)
    assert shown.went == [f"{VIEW}/plan/concourse?pin=info-desk"]


async def test_the_pin_sits_on_its_spot_of_the_thumbnail(render: Render) -> None:
    """At 55 %, 53 % of the thumbnail, its box centred on the point."""
    shown = await render("info-desk")
    width, height = card.thumb_size(place("info-desk")[0])
    (pin,) = shown.pins()
    assert pin.left == pytest.approx(0.55 * width - card.PIN_BOX / 2)
    assert pin.top == pytest.approx(0.53 * height - card.PIN_BOX / 2)


async def test_the_plan_only_card_opens_the_plan_without_a_pin(render: Render) -> None:
    """Without a pin: the plan's title and what is on it, no pin, the plan alone."""
    shown = await render(None, plan_id="arena")
    node = shown.node(IDENTIFIER)
    assert node.label == "Open the Arena & exhibit halls floor plan"
    assert texts(node) == [
        "Arena & exhibit halls",
        "Keynotes, lightning talks, expo hall, job fair",
    ]
    assert shown.pins() == []
    assert shown.sleeps.asked == []
    (tap,) = [c for c in shown.find(ft.Container) if c.on_click]
    await shown.click(tap)
    assert shown.went == [f"{VIEW}/plan/arena"]


async def test_the_pin_pulses_twice_then_stays_still(render: Render) -> None:
    """Out and back twice, each half ``PULSE_MS``, then no more waits (D-34)."""
    shown = await render()
    rings: list[bool] = []
    for _ in range(2 * card.PULSES):
        await shown.until_held()
        rings.append(shown.ring_out())
        await shown.sleeps.release()
        await shown.settle()
    assert rings == [True, False, True, False]
    assert shown.sleeps.asked == [card.PULSE_MS / 1000] * 4
    assert shown.sleeps.held == 0
    assert not shown.ring_out()


async def test_a_re_render_around_the_card_does_not_pulse_again(
    render: Render,
) -> None:
    """The screen re-rendering (a minute tick) leaves the pulse done (D-153)."""
    shown = await render()
    for _ in range(2 * card.PULSES):
        await shown.until_held()
        await shown.sleeps.release()
    await shown.settle()
    await shown.re_render()
    assert len(shown.sleeps.asked) == 2 * card.PULSES
    assert shown.sleeps.held == 0


async def test_reduced_motion_leaves_the_pin_still(render: Render) -> None:
    """Under reduced motion the pin shows and never pulses (D-173)."""
    shown = await render(reduce_motion=True)
    await shown.settle()
    assert len(shown.pins()) == 1
    assert not shown.ring_out()
    assert shown.sleeps.asked == []


@pytest.mark.parametrize("large_text", [False, True])
async def test_at_large_text_the_words_go_under_the_thumbnail(
    render: Render, large_text: bool
) -> None:
    """Beside the thumbnail at most sizes; under it when the text is large (D-216)."""
    shown = await render(large_text=large_text)
    body = shown.node(IDENTIFIER).content
    assert isinstance(body, ft.Column if large_text else ft.Row)


async def test_a_pin_already_pulsed_on_the_view_stays_still(render: Render) -> None:
    """A card whose pin is in ``seen`` (another day's list) never pulses."""
    shown = await render(seen={"info-desk"})
    await shown.settle()
    assert len(shown.pins()) == 1
    assert shown.sleeps.asked == []


async def test_a_card_that_pulses_marks_its_pin_seen(render: Render) -> None:
    """The first card to pulse adds its pin, so the View's other cards stay still."""
    seen: set[str] = set()
    await (await render(seen=seen)).until_held()
    assert seen == {"info-desk"}
