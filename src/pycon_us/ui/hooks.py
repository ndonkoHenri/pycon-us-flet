"""Two small hooks: whether a component is still mounted, and state handlers read at once.

`use_mounted()` is for a **handler** that goes on after an `await`: by then the
screen may have gone, and a SnackBar or a navigation would land on another one. A
coroutine effect needs no such check: Flet cancels it on unmount (F2), and a state setter
called after the unmount renders nothing (`tests/test_flet_effects.py`).

`use_latest_state()` is for handlers that build on the state: `use_state` only
schedules a render, and one may not run between two events (#756).
"""

from collections.abc import Callable
from functools import partial

import flet as ft
from flet.components.hooks.use_ref import MutableRef

from pycon_us.services.errors import report_errors


def use_mounted() -> MutableRef[bool]:
    """Return a ref that holds True until the calling component unmounts.

    Call it on every render (D-70).
    """
    mounted = ft.use_ref(True)

    @report_errors
    def unmount() -> None:
        """Mark the component gone, so a handler still running stays quiet."""
        mounted.current = False

    ft.use_effect(lambda: None, [], cleanup=unmount)
    return mounted


def use_latest_state[T](initial: T) -> tuple[T, MutableRef[T], Callable[[T], None]]:
    """Return the state, a ref to it as the handlers left it, and a setter for both.

    Call it on every render (D-70). Handlers read the ref; the render reads the state.

    Args:
        initial: The first state. Not a callable: `use_state` and `use_ref` would
            call it.
    """
    value, set_value = ft.use_state(initial)
    latest: MutableRef[T] = ft.use_ref(value)
    return value, latest, partial(keep, latest, set_value)


def keep[T](latest: MutableRef[T], set_state: Callable[[T], None], value: T) -> None:
    """Set the state and `latest` together, so the next event sees it at once."""
    latest.current = value
    set_state(value)
