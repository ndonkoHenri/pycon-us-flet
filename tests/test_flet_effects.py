"""`use_effect`'s cleanups at the Flet pin (F2, F39, D-387; #672).

The app's effects rely on these, so a pin bump (D-81) that changes one fails here
first, not on a screen. Each test renders a small component in a real Flet session
(`tests/sessions.py`'s `rendering()`), re-renders or unmounts it through its own
state, and looks at what ran:

- a cleanup a sync setup returns survives the component's re-renders and runs on
  unmount (flet-dev/flet#6983);
- an `async def` setup still running when the component unmounts is cancelled,
  with no cleanup at all (flet-dev/flet#7005), which is what stops every ticking loop
  and pending wait in the app;
- a state setter called after the unmount renders nothing, so an answer landing before
  that cancellation reaches the task needs no `mounted` guard
  (`Component._schedule_update()` and `update()` both refuse);
- on a dependency change, the running setup is cancelled, and an `async def`
  cleanup runs to its end before the next setup starts (flet-dev/flet#7005).
"""

import asyncio
from collections.abc import Callable

import flet as ft

from tests.sessions import rendering, settle

Setter = Callable[[int], None]


async def test_a_returned_cleanup_runs_on_unmount_after_a_re_render() -> None:
    """F39 is gone: a re-render keeps the cleanup a sync setup returned."""
    ran: list[str] = []
    setters: dict[str, Setter] = {}

    @ft.component
    def Child() -> ft.Control:
        """Return a text that re-renders on its own state; its effect logs."""
        renders, set_renders = ft.use_state(0)
        setters["child"] = set_renders

        def setup() -> Callable[[], None]:
            ran.append("setup")
            return lambda: ran.append("cleanup")

        ft.use_effect(setup, [])
        return ft.Text(str(renders))

    @ft.component
    def Root() -> ft.Control:
        """Return the child while `shown` is 1, else an empty column."""
        shown, set_shown = ft.use_state(1)
        setters["root"] = set_shown
        return ft.Column([Child()] if shown else [])

    async with rendering(Root):
        setters["child"](1)  # the re-render that used to drop the cleanup
        await settle()
        assert ran == ["setup"]
        setters["root"](0)
        await settle()
        assert ran == ["setup", "cleanup"]


async def test_an_async_setup_is_cancelled_on_unmount_without_a_cleanup() -> None:
    """F2: no cleanup is needed for Flet to cancel a running setup's task."""
    tasks: list[asyncio.Task[None]] = []
    setters: dict[str, Setter] = {}

    @ft.component
    def Child() -> ft.Control:
        """Return a text whose effect waits for ever, re-rendering on its state."""
        renders, set_renders = ft.use_state(0)
        setters["child"] = set_renders

        async def setup() -> None:
            tasks.append(asyncio.current_task())  # pyright: ignore[reportArgumentType]
            await asyncio.Event().wait()  # a ticking loop, until cancelled

        ft.use_effect(setup, [])
        return ft.Text(str(renders))

    @ft.component
    def Root() -> ft.Control:
        """Return the child while `shown` is 1, else an empty column."""
        shown, set_shown = ft.use_state(1)
        setters["root"] = set_shown
        return ft.Column([Child()] if shown else [])

    async with rendering(Root):
        setters["child"](1)  # a tick's re-render: the loop goes on
        await settle()
        (task,) = tasks
        assert not task.done()
        setters["root"](0)
        await settle()
        assert task.cancelled()


async def test_a_state_setter_after_unmount_renders_nothing() -> None:
    """A late `set_state` raises nothing and never renders the unmounted component."""
    renders: list[int] = []
    setters: dict[str, Setter] = {}

    @ft.component
    def Child() -> ft.Control:
        """Return a text that logs each render of its state."""
        value, set_value = ft.use_state(0)
        setters["child"] = set_value
        renders.append(value)
        return ft.Text(str(value))

    @ft.component
    def Root() -> ft.Control:
        """Return the child while `shown` is 1, else an empty column."""
        shown, set_shown = ft.use_state(1)
        setters["root"] = set_shown
        return ft.Column([Child()] if shown else [])

    async with rendering(Root):
        setters["child"](1)  # still mounted: this one renders
        await settle()
        assert renders == [0, 1]
        setters["root"](0)
        await settle()
        setters["child"](2)  # as an answer landing late would
        await settle()
        assert renders == [0, 1]


async def test_an_async_cleanup_finishes_before_the_next_setup() -> None:
    """D-387: a dependency change cancels the setup; an async cleanup ends first."""
    ran: list[str] = []
    tasks: list[asyncio.Task[None]] = []
    setters: dict[str, Setter] = {}

    @ft.component
    def Child() -> ft.Control:
        """Return a text whose effect depends on its state and cleans up async."""
        value, set_value = ft.use_state(0)
        setters["child"] = set_value

        async def setup() -> None:
            ran.append(f"setup {value}")
            tasks.append(asyncio.current_task())  # pyright: ignore[reportArgumentType]
            await asyncio.Event().wait()

        async def cleanup() -> None:
            ran.append("cleanup started")
            await asyncio.sleep(0)
            ran.append("cleanup done")

        ft.use_effect(setup, [value], cleanup=cleanup)
        return ft.Text(str(value))

    async with rendering(Child):
        setters["child"](1)
        await settle()
        assert ran == ["setup 0", "cleanup started", "cleanup done", "setup 1"]
        first, second = tasks
        assert first.cancelled()
        assert not second.done()
