"""Helpers that look into a built control tree, for tests that run without a renderer."""

from collections.abc import Iterator

import flet as ft

_CHILDREN = ("content", "leading", "title", "subtitle", "trailing")


def descendants(control: ft.Control) -> Iterator[ft.Control]:
    """Yield ``control`` and every control under it, depth first, in reading order.

    Follows the fields the app's builders fill: ``content``, a ``ListTile``'s parts and
    ``controls``.
    """
    yield control
    for name in _CHILDREN:
        child = getattr(control, name, None)
        if isinstance(child, ft.Control):
            yield from descendants(child)
    for child in getattr(control, "controls", None) or ():
        yield from descendants(child)


def texts(control: ft.Control) -> list[str]:
    """Return the values of the ``Text`` controls under ``control``, in reading order."""
    return [
        str(node.value) for node in descendants(control) if isinstance(node, ft.Text)
    ]


def only[T: ft.Control](control: ft.Control, kind: type[T]) -> T:
    """Return the one control of type ``kind`` under ``control``; fail on none or more."""
    found = [node for node in descendants(control) if isinstance(node, kind)]
    assert len(found) == 1, f"{len(found)} {kind.__name__} controls"
    return found[0]
