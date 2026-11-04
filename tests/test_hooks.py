"""`ui/hooks.py`'s two hooks, in a real Flet session (#909).

A coroutine effect needs neither: `tests/test_flet_effects.py` pins that Flet cancels
it on unmount and that a state setter called after the unmount renders nothing.
"""

from collections.abc import Callable
from typing import cast

import flet as ft
from flet.components.hooks.use_ref import MutableRef

from pycon_us.ui.hooks import use_latest_state, use_mounted
from tests.sessions import rendering, settle


async def test_use_mounted_holds_true_until_the_unmount() -> None:
    """The ref holds True through a re-render and False once the component has gone."""
    refs: list[MutableRef[bool]] = []
    setters: dict[str, Callable[[int], None]] = {}

    @ft.component
    def Child() -> ft.Control:
        """Return a text that re-renders on its own state; keep each render's ref."""
        renders, set_renders = ft.use_state(0)
        setters["child"] = set_renders
        refs.append(use_mounted())
        return ft.Text(str(renders))

    @ft.component
    def Root() -> ft.Control:
        """Return the child while `shown` is 1, else an empty column."""
        shown, set_shown = ft.use_state(1)
        setters["root"] = set_shown
        return ft.Column([Child()] if shown else [])

    async with rendering(Root):
        setters["child"](1)
        await settle()
        assert len(refs) == 2
        assert refs[0] is refs[1] and refs[0].current is True
        setters["root"](0)
        await settle()
        assert refs[0].current is False


async def test_the_latest_state_is_there_before_the_render() -> None:
    """The ref holds a set value at once; the next render's state holds the last one."""
    renders: list[int | None] = []
    hooks: list[tuple[MutableRef[int | None], Callable[[int | None], None]]] = []

    @ft.component
    def Root() -> ft.Control:
        """Return a text of the state; log each render and keep the ref and setter."""
        value, latest, set_value = use_latest_state(cast(int | None, None))
        renders.append(value)
        hooks.append((latest, set_value))
        return ft.Text(str(value))

    async with rendering(Root):
        latest, set_value = hooks[-1]
        assert latest.current is None
        set_value(1)
        assert latest.current == 1  # two events with no render between them see it
        set_value(2)
        assert latest.current == 2
        assert renders == [None]
        await settle()
        assert renders == [None, 2]
        assert hooks[-1][0] is latest and latest.current == 2
