"""The Schedule filter tests' support: the sheet's controls, taps and counts (#87).

``tests/test_schedule_filter.py`` and ``tests/test_schedule_filter_sheet.py`` share it,
over ``tests/schedule_view.py``'s ``shown`` fixture. Each takes ``encoded`` by
assignment: the sheet is a dialog, whose updates need encoded messages.
"""

from collections.abc import Awaitable, Callable
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.timeline import timeline
from pycon_us.state import Conference
from tests import sessions
from tests.fakes import MemoryPrefs
from tests.schedule_view import DAYS, Shown
from tests.sessions import find, settle
from tests.trees import texts


@pytest.fixture(autouse=True)
def encoded(monkeypatch: pytest.MonkeyPatch) -> None:
    """The sheet is a dialog: its updates need encoded messages (sessions.ENCODE)."""
    monkeypatch.setattr(sessions, "ENCODE", True)


INFO = load_year(2026).conference
STORED = "pycon.excluded_tracks"

type Show = Callable[..., Awaitable[Shown]]
"""The ``shown`` fixture: render the Schedule, with ``Prefs`` fields as keywords."""


def stored(schedule: Shown) -> dict[str, Any]:
    """What SharedPreferences holds for the session (``tests/fakes.MemoryPrefs``)."""
    return cast(MemoryPrefs, schedule.storage.prefs).values


def feed_tracks(conference: Conference) -> frozenset[str]:
    """The track keys of every session the Schedule can show, on any day."""
    data = conference.data
    assert data is not None
    return frozenset(
        s.track
        for day in DAYS
        for slot in timeline(data, day, ())
        for s in slot.sessions
    )


def shown_count(conference: Conference, excluded: tuple[str, ...]) -> int:
    """The rows the Schedule shows on all days with this filter."""
    data = conference.data
    assert data is not None
    return sum(
        len(slot.sessions) for day in DAYS for slot in timeline(data, day, excluded)
    )


def chip_parts(label: Any) -> tuple[ft.Icon | None, ft.Text]:
    """Return a chip label's check (``None`` when it has none) and its name."""
    assert isinstance(label, ft.Container)
    row = label.content
    assert isinstance(row, ft.Row)
    *check, name = row.controls
    assert isinstance(name, ft.Text)
    assert all(isinstance(c, ft.Icon) for c in check)
    return (cast(ft.Icon, check[0]) if check else None), name


def summary(schedule: Shown) -> str | None:
    """The filter summary's text, or None when the Schedule shows none."""
    found = find(
        schedule.session,
        ft.Semantics,
        lambda c: c.identifier == "schedule.filter_summary",
    )
    return texts(found[0])[0] if found else None


def filter_button(schedule: Shown) -> ft.IconButton:
    """The app bar's filter ``IconButton``."""
    (node,) = find(
        schedule.session, ft.Semantics, lambda c: c.identifier == "schedule.filter"
    )
    assert isinstance(node.content, ft.IconButton)
    return node.content


def sheet(schedule: Shown) -> ft.BottomSheet | None:
    """The open filter sheet, or None; there is never more than one."""
    dialogs = schedule.session.page._dialogs.controls  # pyright: ignore[reportPrivateUsage]
    found = [d for d in dialogs if isinstance(d, ft.BottomSheet) and d.open]
    assert len(found) <= 1
    return found[0] if found else None


def node(schedule: Shown, identifier: str) -> ft.Semantics:
    """Return the sheet's semantics node ``identifier``."""
    current = sheet(schedule)
    assert current is not None
    return next(
        c
        for c in _descendants(current)
        if isinstance(c, ft.Semantics) and c.identifier == identifier
    )


def in_sheet(schedule: Shown, identifier: str) -> Any:
    """Return the control under the sheet's semantics node ``identifier``."""
    return node(schedule, identifier).content


def chip(schedule: Shown, key: str) -> ft.Chip:
    """The sheet's chip for the track ``key``."""
    found = in_sheet(schedule, f"schedule.filter.{key}")
    assert isinstance(found, ft.Chip)
    return found


def reset_button(schedule: Shown) -> ft.TextButton:
    """The sheet's Reset button."""
    found = in_sheet(schedule, "schedule.filter.reset")
    assert isinstance(found, ft.TextButton)
    return found


def show_button(schedule: Shown) -> ft.FilledButton:
    """The sheet's Show button."""
    current = sheet(schedule)
    assert current is not None
    return next(c for c in _descendants(current) if isinstance(c, ft.FilledButton))


def button_label(schedule: Shown) -> str:
    """The text of the sheet's Show button."""
    content = show_button(schedule).content
    assert isinstance(content, ft.Text)
    return str(content.value)


def _descendants(control: Any) -> list[Any]:
    """Every control under ``control``, through ``content`` and ``controls``."""
    found = [control]
    for child in (getattr(control, "content", None), *getattr(control, "controls", ())):
        if isinstance(child, ft.BaseControl):
            found.extend(_descendants(child))
    return found


async def click(schedule: Shown, control: ft.BaseControl) -> None:
    """Dispatch a click on ``control``, then let the session settle."""
    await schedule.session.dispatch_event(control._i, "click", None)
    await settle()


async def open_sheet(schedule: Shown) -> ft.BottomSheet:
    """Tap the filter button and return the sheet it opens."""
    await click(schedule, filter_button(schedule))
    current = sheet(schedule)
    assert current is not None
    return current


async def tap_chip(schedule: Shown, key: str) -> None:
    """What Flutter sends for a chip tap: the flipped state, then the event."""
    target = chip(schedule, key)
    selected = not target.selected
    schedule.session.apply_patch(target._i, {"selected": selected})
    await schedule.session.dispatch_event(target._i, "select", selected)
    await settle()
