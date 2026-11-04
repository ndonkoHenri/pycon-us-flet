"""A route change first closes the open dialogs and sheets (`ui/modals.py`, D-291).

In a real Flet session of the app's own Views (`tests/links.py`): a warm link that
arrives with a modal open closes it, waits for Flutter's dismissal, then shows the
new location; SnackBars, Banners and pickers stay as they are, each its own test. Flutter's dismissal
is the `dismiss` event the dialog sends once its exit animation ends, which Flet's
wrapper turns into the dialog leaving `page._dialogs` (`base_page.py`).
"""

import asyncio
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.ui import modals
from tests import links
from tests.links import Open, Shown

open_at = links.open_at  # the fixture, under this module's name (tests/chrome.py)

LINK = "/schedule/session/31"


def dialogs(shown: Shown) -> list[ft.DialogControl]:
    """The page's dialog list: what is open or still closing."""
    return list(shown.page._dialogs.controls)  # pyright: ignore[reportPrivateUsage]


async def dismissed(shown: Shown, dialog: ft.DialogControl) -> None:
    """Report `dialog` dismissed as Flutter does after its exit animation.

    Then wait out one look of the route change's wait (`POLL`), so it goes on.
    """
    await shown.event(dialog, "dismiss")
    await asyncio.sleep(modals.POLL * 2)
    await shown.settle()


@pytest.mark.parametrize(
    "make",
    [
        lambda: ft.AlertDialog(title=ft.Text("Clear the cached schedule?")),
        lambda: ft.BottomSheet(ft.Text("Sheet")),
    ],
    ids=["dialog", "sheet"],
)
async def test_a_link_closes_an_open_modal_then_lands(open_at: Open, make: Any) -> None:
    """A dialog or a sheet closes first; the target shows once it has gone.

    Shown earlier, the new top View would draw it again without its route (F109).
    """
    shown = await open_at("/more/developer")
    modal = make()
    shown.page.show_dialog(modal)
    await shown.settle()

    await shown.go(LINK)
    assert modal.open is False  # asked to close
    assert shown.routes() == ["/", "/more/developer"]  # not there yet: it is closing

    await dismissed(shown, modal)
    assert modal not in dialogs(shown)
    assert shown.routes() == ["/", LINK]


async def test_the_filter_sheet_closes_before_a_link_lands_on_now(
    open_at: Open,
) -> None:
    """The Schedule's filter sheet (`ft.use_dialog`) closes, and Now shows.

    The case seen on the emulator: the sheet stayed over Now (F109).
    """
    shown = await open_at("/schedule")
    button = shown.node("schedule.filter")
    while not isinstance(button, ft.IconButton):
        button = cast(Any, button).content
    await shown.click(button)
    (sheet,) = [d for d in dialogs(shown) if isinstance(d, ft.BottomSheet)]
    assert sheet.open

    await shown.go("/now")
    assert sheet.open is False
    await dismissed(shown, sheet)
    assert shown.has("now.title")
    assert not [d for d in dialogs(shown) if isinstance(d, ft.BottomSheet)]


@pytest.mark.parametrize(
    "make",
    [
        lambda: ft.SnackBar(ft.Text("Removed from My schedule")),
        lambda: ft.Banner(content=ft.Text("Reminder"), actions=[]),
    ],
    ids=["snack bar", "banner"],
)
async def test_a_link_leaves_a_message_open_and_lands_at_once(
    open_at: Open, make: Any
) -> None:
    """A SnackBar or a Banner is a message, not a route: it stays, and nothing waits.

    So an Undo outlives the link (ux.md §4.4).
    """
    shown = await open_at("/now/session/31")
    message = make()
    shown.page.show_dialog(message)
    await shown.settle()

    await shown.go(LINK)
    assert shown.routes() == ["/", LINK]
    assert message.open is True
    assert message in dialogs(shown)


@pytest.mark.parametrize(
    "make",
    [lambda: ft.DatePicker(), lambda: ft.TimePicker(), lambda: ft.DateRangePicker()],
    ids=["date picker", "time picker", "date range picker"],
)
async def test_a_link_does_not_wait_for_a_picker_flet_cannot_close(
    open_at: Open, make: Any
) -> None:
    """A picker is left as it is, and the link lands at once (U89).

    Flet's pickers have no close path, so `open = False` would close nothing and
    only make the link wait `CLOSE_WAIT`; the picker goes with its View (F109).
    """
    shown = await open_at("/more/developer")
    picker = make()
    shown.page.show_dialog(picker)
    await shown.settle()

    await shown.go(LINK)
    assert shown.routes() == ["/", LINK]
    assert picker.open is True  # not asked: Flutter would not close it


async def test_a_message_over_a_dialog_stays_while_the_dialog_closes(
    open_at: Open,
) -> None:
    """With a SnackBar shown over a dialog, only the dialog closes."""
    shown = await open_at("/more/developer")
    dialog = ft.AlertDialog(title=ft.Text("Reset the app?"))
    bar = ft.SnackBar(ft.Text("Couldn't save your change"))
    shown.page.show_dialog(dialog)
    shown.page.show_dialog(bar)
    await shown.settle()

    await shown.go(LINK)
    await dismissed(shown, dialog)
    assert (dialog.open, bar.open) == (False, True)
    assert shown.routes() == ["/", LINK]


async def test_a_dismissal_that_never_comes_delays_the_link_by_close_wait_only(
    open_at: Open, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without Flutter's answer the link still lands, `CLOSE_WAIT` later."""
    monkeypatch.setattr(modals, "CLOSE_WAIT", 0.2)
    shown = await open_at("/more/developer")
    shown.page.show_dialog(ft.AlertDialog(title=ft.Text("Reset the app?")))
    await shown.settle()

    await shown.go(LINK)
    assert shown.routes() == ["/", "/more/developer"]
    await asyncio.sleep(0.3)
    await shown.settle()
    assert shown.routes() == ["/", LINK]


async def test_a_second_link_while_the_first_waits_lands_last(open_at: Open) -> None:
    """Two quick links keep their order: the second waits behind the first."""
    shown = await open_at("/more/developer")
    dialog = ft.AlertDialog(title=ft.Text("Reset the app?"))
    shown.page.show_dialog(dialog)
    await shown.settle()

    await shown.go(LINK)
    await shown.go("/map")  # nothing open any more, but the first still waits
    await dismissed(shown, dialog)
    assert shown.routes() == ["/"]
    assert shown.has("map.title")


async def test_without_a_modal_a_route_change_shows_at_once(open_at: Open) -> None:
    """With nothing open, the change goes straight to the Router, in the same turn."""
    shown = await open_at("/now")
    handler: Any = shown.page.on_route_change
    assert handler.closes_modals  # ui.modals' handler, in front of the Router's
    shown.page.route = LINK
    handler(type("E", (), {"route": LINK})())
    await shown.settle()
    assert shown.routes() == ["/", LINK]


async def test_the_router_s_handler_is_wrapped_once(open_at: Open) -> None:
    """Every screen asks for the wrapper; the Router's handler is wrapped only once."""
    shown = await open_at("/schedule/session/31/speaker/32")  # three screens mount
    handler: Any = shown.page.on_route_change
    assert handler.closes_modals
    await shown.go("/now/session/31")  # another screen mounts and asks again
    assert shown.page.on_route_change is handler
