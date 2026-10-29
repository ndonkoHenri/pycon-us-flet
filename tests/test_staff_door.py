"""Tests for Door check's route and its session picker (#764; DOOR-01, DOOR-02; D-433).

``screens/staff_door.py``'s ``DoorCheck`` and ``screens/door_session.py``'s
``SessionPicker`` run in a real Flet session (``tests/harness.py``) over the mock's own
transport, signed with the seeded staff account's key, so the catalog is what the mock's
``handle()`` answers; a switch takes the transport offline. One test's sessions share
one SharedPreferences, so a second render is a relaunch. The picker lists the door's
categories, then a category's sessions by day, saves a tap and goes back; Door check is
paused until a session is chosen, opens the picker once by itself, then heads the
screen with the session's chip. Only ``door_check`` accounts reach either.
"""

import json
import re
from typing import Any, cast

import flet as ft
import httpx
import pytest
from flet.components.component import Component

from pycon_us.account import Account
from pycon_us.core.door_sessions import to_stored
from pycon_us.screens.door_session import ALL_SESSIONS, NONE_AVAILABLE, NOT_LOADED
from pycon_us.screens.door_session import TITLE as PICKER_TITLE
from pycon_us.screens.staff_door import NO_SESSION, TITLE
from pycon_us.services.storage import STAFF_DOOR_SESSION, STAFF_PREFIX
from pycon_us.ui.scan_screen import NOT_AVAILABLE
from tests import door_rig, harness
from tests.door_rig import (
    ASYNC,
    PICKER,
    VIEW,
    Show,
    chip_text,
    helper,
    preload_line,
    staff,
    stored_choice,
    tap,
)
from tests.harness import Shown
from tests.picker_rig import Switch, search
from tests.trees import texts

stored, switch, show = door_rig.stored, door_rig.switch, door_rig.show

WEDNESDAY = "h2 Wednesday, May 13"
READY_ONE = "Ready, works offline, 1 attendee"
"""Async in depth's list: Grace alone bought it."""


def listing(shown: Shown) -> list[str]:
    """The picker's list in order: "h2 <heading>" per day, each row's phrase."""
    (body,) = shown.find(ft.ListView)
    found: list[str] = []

    def walk(control: object) -> None:
        """Note the headings and rows under ``control``, depth first."""
        if isinstance(control, ft.Semantics):
            if control.header:
                found.append(f"h{control.heading_level} {' '.join(texts(control))}")
            elif re.fullmatch(r"door\.session\.(\d+|all)", str(control.identifier)):
                found.append(str(control.label))
        for name in ("content", "_b"):
            child = getattr(control, name, None)
            for item in child if isinstance(child, list) else [child]:
                if isinstance(item, ft.BaseControl):
                    walk(item)
        for child in getattr(control, "controls", None) or ():
            walk(child)

    walk(body)
    return found


# ------------------------------------------------------------------ the picker


async def test_the_door_s_categories_show_and_tutorials_lists_wednesday(
    show: Show,
) -> None:
    """Tutorials and Summits, not the swag; then All, and Wednesday's two in order."""
    shown = await show(PICKER)
    assert shown.titles[-1] == PICKER_TITLE
    chips = sorted(str(n.identifier) for n in shown.nodes("door.category."))
    assert chips == ["door.category.1", "door.category.2"]
    assert not shown.nodes("door.session.search")  # no category yet
    await tap(shown, "door.category.1")
    assert listing(shown) == [
        ALL_SESSIONS,
        WEDNESDAY,
        "All about decorators, Wednesday 9:00 AM",
        "Async in depth, Wednesday 1:30 PM",
    ]
    assert shown.nodes("door.session.search")


async def test_a_second_tap_on_the_category_clears_it(show: Show) -> None:
    """Single-select: the chip says its state, and a second tap leaves none chosen."""
    shown = await show(PICKER)
    await tap(shown, "door.category.2")
    assert cast(ft.Chip, shown.node("door.category.2").content).selected
    assert listing(shown)[1:] == [
        "h2 Thursday, May 14",
        "Example Summit, Thursday 10:00 AM",
    ]
    await tap(shown, "door.category.2")
    assert not cast(ft.Chip, shown.node("door.category.2").content).selected
    assert listing(shown) == []


async def test_searching_async_leaves_async_in_depth(show: Show) -> None:
    """The search keeps the session; a miss says so and offers to clear."""
    shown = await show(PICKER)
    await tap(shown, "door.category.1")
    await search(shown, "async")
    assert listing(shown) == [WEDNESDAY, "Async in depth, Wednesday 1:30 PM"]
    await search(shown, "zzz")
    assert listing(shown) == [
        "h2 No sessions match \N{LEFT DOUBLE QUOTATION MARK}zzz\N{RIGHT DOUBLE QUOTATION MARK}"
    ]
    assert shown.nodes("door.session.no_match")


async def test_a_session_tapped_is_saved_and_the_page_goes_back(show: Show) -> None:
    """The choice is stored with its label; the page pops to Door check."""
    shown = await show(PICKER)
    await tap(shown, "door.category.1")
    await tap(shown, "door.session.11")
    assert await stored_choice(shown) == to_stored(ASYNC)
    assert shown.went == [VIEW]


async def test_all_sessions_saves_every_id_of_the_category(show: Show) -> None:
    """Choosing all of Tutorials stores both of its ids, and says it is all."""
    shown = await show(PICKER)
    await tap(shown, "door.category.1")
    await tap(shown, "door.session.all")
    assert await stored_choice(shown) == {
        "category_id": 1,
        "product_ids": [10, 11],
        "label": "Tutorials \N{MIDDLE DOT} All sessions",
        "all": True,
    }


async def test_the_saved_choice_opens_its_category_ticked_and_cancel_keeps_it(
    show: Show,
) -> None:
    """The page opens on the choice's category, its row selected; Cancel is Back."""
    shown = await show(PICKER, chosen=ASYNC)
    assert "Async in depth, Wednesday 1:30 PM, selected" in listing(shown)
    (cancel,) = [b for b in shown.find(ft.IconButton) if b.tooltip == "Cancel"]
    await shown.click(cancel)
    assert shown.went == [VIEW]
    assert await stored_choice(shown) == to_stored(ASYNC)


async def test_offline_it_says_so_and_retry_loads(show: Show, switch: Switch) -> None:
    """No connection: "Couldn't load sessions" with Retry, which loads once back."""
    switch.offline = True
    shown = await show(PICKER)
    assert NOT_LOADED in shown.texts()
    assert not shown.nodes("door.category.")
    switch.offline = False
    (retry,) = shown.find(ft.FilledTonalButton)
    await shown.click(retry)
    assert NOT_LOADED not in shown.texts()
    assert len(shown.nodes("door.category.")) == 2


async def test_a_refusal_is_said_as_not_loaded(show: Show) -> None:
    """An error answer (here 500) is the same state as offline (D-120)."""
    transport = httpx.MockTransport(lambda _: httpx.Response(500, json={}))
    shown = await show(PICKER, transport=transport)
    assert NOT_LOADED in shown.texts()


async def test_a_catalog_of_swag_only_says_none_are_available(show: Show) -> None:
    """With no door category left, "No sessions available", and no chips."""
    reply = {
        "redeemable_categories": [{"id": 3, "name": "T-Shirt"}],
        "redeemable_products": [{"id": 30, "name": "T-Shirt (M)", "category": 3}],
    }
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=reply))
    shown = await show(PICKER, transport=transport)
    assert NONE_AVAILABLE in shown.texts()
    assert not shown.nodes("door.category.")


@pytest.mark.parametrize("view", [VIEW, PICKER])
@pytest.mark.parametrize(
    "account",
    [
        staff(door_check=False, lead_retrieval=True),
        staff(door_check=False, mask_violation=True),
        Account(restored=True),
    ],
    ids=["sponsor", "coc", "signed out"],
)
async def test_only_door_staff_reach_door_check_and_its_picker(
    show: Show, view: str, account: Account
) -> None:
    """A ``lead_retrieval``-only account, others and a signed-out session are refused."""
    shown = await show(view, account)
    assert NOT_AVAILABLE in shown.texts()
    assert not shown.nodes("scan.entry")
    assert not shown.nodes("door.category.")


# ------------------------------------------------------------------ Door check


async def test_without_a_session_the_picker_opens_once_and_scanning_waits(
    show: Show,
) -> None:
    """The picker opens by itself once; the screen says why it waits, with a button."""
    shown = await show(VIEW)
    assert shown.titles[-1] == TITLE
    assert shown.went == [PICKER]
    assert helper(shown) == NO_SESSION
    assert chip_text(shown) is None
    await shown.settle()
    assert shown.went == [PICKER]  # once
    await shown.click(cast(ft.Control, shown.node("door.session.choose").content))
    assert shown.went == [PICKER, PICKER]
    assert shown.memory.staff_tool == "door"  # Now's card's tool (D-421)


async def test_a_chosen_session_heads_the_screen_and_its_list_loads(
    show: Show,
) -> None:
    """The chip names the session, read as a button to change it; its list loads."""
    shown = await show(VIEW, chosen=ASYNC)
    assert shown.went == []
    assert chip_text(shown) == "Async in depth \N{MIDDLE DOT} Wed 1:30 PM"
    node = shown.node("door.session_chip")
    assert node.button
    assert node.label == "Checking in for Async in depth, Wed 1:30 PM, change session"
    assert preload_line(shown) == READY_ONE
    assert helper(shown) is None  # scanning
    await tap(shown, "door.session_chip")
    assert shown.went == [PICKER]


async def test_the_choice_survives_a_relaunch(show: Show) -> None:
    """Chosen on the picker, it heads Door check in the next session too."""
    picker = await show(PICKER)
    await tap(picker, "door.category.1")
    await tap(picker, "door.session.all")
    shown = await show(VIEW)
    assert chip_text(shown) == "Tutorials \N{MIDDLE DOT} All sessions"


async def test_back_from_the_picker_shows_the_session_chosen(
    show: Show, stored: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The key is read again when the location changes (D-433); Cancel leaves none."""
    location = [PICKER]
    monkeypatch.setattr(ft, "use_route_location", lambda: location[0])
    account = staff()
    shown = await show(VIEW, account)
    location[0] = VIEW  # Cancel: back with nothing chosen
    account.nickname = "Back"  # a render, as the Router's on a location change
    await shown.settle()
    assert helper(shown) == NO_SESSION
    assert shown.went == [PICKER]  # not asked again
    location[0] = PICKER
    account.nickname = "Picker"
    await shown.settle()
    stored[STAFF_DOOR_SESSION.key] = json.dumps(to_stored(ASYNC))
    location[0] = VIEW  # a tap: back with Async in depth
    account.nickname = "Chosen"
    await shown.settle()
    assert chip_text(shown) == ASYNC.label
    assert preload_line(shown) == READY_ONE


async def test_the_session_goes_with_a_sign_out_and_a_switch(
    show: Show, stored: dict[str, Any]
) -> None:
    """The staff keys' removal (D-414) takes the session; the screen pauses again."""
    account = staff()
    shown = await show(VIEW, account, chosen=ASYNC)
    assert chip_text(shown) is not None
    account.signed_in = False  # Account.sign_out() clears the staff keys too
    assert await shown.storage.clear_prefs(STAFF_PREFIX)
    await shown.settle()
    account.signed_in = True
    await shown.settle()
    assert chip_text(shown) is None
    assert helper(shown) == NO_SESSION
    stored[STAFF_DOOR_SESSION.key] = json.dumps(to_stored(ASYNC))
    assert await shown.storage.clear_prefs(STAFF_PREFIX)  # as a switch's sign-in
    account.email = "b@example.com"
    await shown.settle()
    assert chip_text(shown) is None
    assert helper(shown) == NO_SESSION


async def test_every_component_keeps_its_hooks_from_reading_to_scanning(
    show: Show, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each render runs all its component's hooks, from the read to the chip (D-70).

    The stand-in scaffold calls a hook, as the real one does: called from
    ``DoorTool``'s reading branch only, it would leave a hook unused after the read.
    """
    stand_in = harness._scaffold

    def scaffold(**kwargs: Any) -> ft.Control:
        """Call a hook, as ``AppScaffold`` does, then stand in for it."""
        ft.use_state(0)
        return stand_in(**kwargs)

    renders: list[tuple[str, int, int]] = []
    run_effects = Component._run_render_effects

    def record(component: Component) -> None:
        """Record each render's hooks used and hooks held, then run its effects."""
        state = component._state
        renders.append((component.fn.__name__, state.hook_cursor, len(state.hooks)))
        run_effects(component)

    monkeypatch.setattr(harness, "_scaffold", scaffold)
    monkeypatch.setattr(Component, "_run_render_effects", record)
    await show(VIEW, chosen=ASYNC)
    picker = await show(PICKER)  # on the choice's category, Tutorials
    await search(picker, "async")
    await tap(picker, "door.category.2")
    names = {name for name, *_ in renders}
    assert names >= {"DoorTool", "Reading", "ScanScreen", "SessionList"}
    assert [render for render in renders if render[1] != render[2]] == []
