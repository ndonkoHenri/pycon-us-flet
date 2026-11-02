"""Tests for the CoC name search, ``ui/coc_search.py`` and its sheet (#761; MASK-02, MASK-03).

The tool runs in a real Flet session over the mock's transport, as in
``tests/test_staff_coc.py``, whose fixtures these share. Find by name is disabled with
its reason until the directory has loaded and while offline; it opens a sheet that
pauses scanning; typing finds rows (every folded word, D-46; at most 25); a row's tap
opens the review dialog of ``tests/test_coc_review.py``, whose Record reaches the panel
through ``ScanScreen(posted=)``; and the query, the rows and the access codes stay out
of storage, identifiers and logs (D-56, D-72).
"""

import asyncio
import logging
from typing import Any, cast

import flet as ft
import pytest
from flet.utils.object_model import patch_dataclass

from pycon_us.core.conduct import Attendee
from pycon_us.screens import staff_coc
from pycon_us.screens.staff_coc import LOADING, OFFLINE, REVIEW_OPEN, find_reason
from pycon_us.ui import coc_search
from pycon_us.ui.coc_search import SEARCH_OPEN
from pycon_us.ui.coc_search_sheet import BEFORE, FIND, MORE, TITLE, phrase
from tests import test_coc_review, test_staff_coc
from tests.harness import Shown
from tests.scan_rig import panel
from tests.test_coc_review import (
    badge_field,
    dialog,
    enter,
    helper,
    tap,
    texts,
    type_notes,
    walk,
)
from tests.test_staff_coc import ATTENDEES, Show, Switch, seeded_mock

show, switch, stored = test_staff_coc.show, test_staff_coc.switch, test_staff_coc.stored
mock, focused = test_coc_review.mock, test_coc_review.focused

NOTES = "Hall B: shouted at a volunteer"


@pytest.fixture(autouse=True)
def no_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """The rows follow the text at once: the 250 ms pause is the debounce's own test."""
    monkeypatch.setattr(coc_search, "DEBOUNCE_SECONDS", 0)


def sheet(shown: Shown) -> ft.BottomSheet | None:
    """The open search sheet, or None."""
    dialogs = shown.session.page._dialogs.controls  # pyright: ignore[reportPrivateUsage]
    found = [d for d in dialogs if isinstance(d, ft.BottomSheet) and d.open]
    assert len(found) <= 1
    return found[0] if found else None


def in_sheet(shown: Shown, prefix: str) -> list[ft.Semantics]:
    """The open sheet's semantics nodes whose identifier starts with ``prefix``."""
    current = sheet(shown)
    assert current is not None
    return [
        c
        for c in walk(current)
        if isinstance(c, ft.Semantics) and str(c.identifier or "").startswith(prefix)
    ]


def sheet_texts(shown: Shown) -> list[str]:
    """Every text in the open sheet."""
    current = sheet(shown)
    assert current is not None
    return [str(c.value) for c in walk(current) if isinstance(c, ft.Text)]


def rows(shown: Shown) -> list[str]:
    """The rows' phrases, in order: one node each (ux.md §9)."""
    return [str(n.label) for n in in_sheet(shown, "coc.search.row.")]


def find_button(shown: Shown) -> Any:
    """Find by name's node, under the badge field."""
    return shown.node("coc.find")


async def open_find(shown: Shown) -> None:
    """Tap Find by name: the sheet opens."""
    node = find_button(shown)
    button = node.content
    while not isinstance(button, ft.OutlinedButton):
        button = button.content
    await shown.click(button)
    assert sheet(shown) is not None


async def search_for(shown: Shown, text: str) -> None:
    """Type ``text`` in the search field, as Flutter reports it."""
    (node,) = [n for n in in_sheet(shown, "coc.search") if n.identifier == "coc.search"]
    field = node.content
    assert isinstance(field, ft.TextField)
    patch_dataclass(field, {"value": text})
    await shown.event(field, "change", text)
    await shown.settle()


async def tap_row(shown: Shown, index: int) -> asyncio.Task[None]:
    """Tap row ``index`` as a task: it waits on the review it opens, until it opens."""
    node = in_sheet(shown, f"coc.search.row.{index}")[0]
    container = next(
        c
        for c in walk(sheet(shown))
        if isinstance(c, ft.Container) and c.content is node
    )
    task = asyncio.create_task(shown.click(container))
    for _ in range(50):
        await shown.settle()
        if dialog(shown) is not None:
            break
    return task


async def test_find_by_name_waits_for_the_directory_and_a_connection(
    show: Show, switch: Switch
) -> None:
    """Disabled with #759's words while loading and offline; enabled once loaded."""
    switch.gate = asyncio.Event()
    shown = await show(settle=False)
    await shown.settle()
    node = find_button(shown)
    assert node.disabled
    assert node.content.label == f"{FIND}. {LOADING}"  # its name says why
    switch.gate.set()
    await shown.settle()
    node = find_button(shown)
    assert not node.disabled and not isinstance(node.content, ft.Semantics)


async def test_find_by_name_is_disabled_offline_with_the_reason(
    show: Show, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Offline (D-56): disabled, its name "Find by name. CoC capture needs a connection"."""
    monkeypatch.setattr(staff_coc, "use_online", lambda svc, *, watch: False)
    shown = await show()
    node = find_button(shown)
    assert node.disabled and node.content.label == f"{FIND}. {OFFLINE}"


def test_find_reason_follows_the_directory_and_the_connection() -> None:
    """Offline says so first; a directory not loaded gives its words; loaded, none."""
    loaded = staff_coc.Directory("coc@example.com", "loaded", {})
    failed = staff_coc.Directory("coc@example.com", "failed", {})
    assert find_reason(loaded, "4 attendees", online=False) == OFFLINE
    assert find_reason(failed, "Couldn't load", online=True) == "Couldn't load"
    assert find_reason(loaded, "4 attendees", online=True) is None


async def test_the_sheet_opens_empty_focused_and_pauses_scanning(show: Show) -> None:
    """The heading, the focused field, the hint; scanning paused, a HID submit dropped."""
    shown = await show()
    await open_find(shown)
    current = cast(ft.BottomSheet, sheet(shown))
    assert current.show_drag_handle and current.scrollable
    assert TITLE in sheet_texts(shown) and BEFORE in sheet_texts(shown)
    headings = [
        c for c in walk(current) if isinstance(c, ft.Semantics) and c.heading_level
    ]
    assert headings[0].heading_level == 1
    (node,) = [n for n in in_sheet(shown, "coc.search") if n.identifier == "coc.search"]
    assert cast(ft.TextField, node.content).autofocus
    assert helper(shown) == SEARCH_OPEN
    await enter(shown, "MOCK0002:x")  # a HID scanner typing while it is open
    assert badge_field(shown).value == ""  # dropped with its text (D-471)
    assert dialog(shown) is None and sheet(shown) is not None


async def test_rows_match_every_word_with_the_badge_and_count_in_words(
    show: Show,
) -> None:
    """Every word matches: Margaret Test, badge Maggie; Linus's 3 with its level's icon."""
    shown = await show()
    await open_find(shown)
    await search_for(shown, "mar test")
    assert rows(shown) == ["Margaret Test, badge Maggie, no incidents on record"]
    assert "Badge: Maggie" in sheet_texts(shown)
    assert "1 attendee" in sheet_texts(shown)
    await search_for(shown, "linus")
    assert rows(shown) == ["Linus Placeholder, badge Linus, 3 incidents on record"]
    icons = [c.icon for c in walk(sheet(shown)) if isinstance(c, ft.Icon)]
    assert ft.Icons.ERROR_OUTLINE in icons  # the level never by colour alone
    await search_for(shown, "ada")  # the nickname, and the name
    assert rows(shown)[0].startswith("Ada Example")


async def test_no_match_offers_clear_search(show: Show, focused: list[int]) -> None:
    """No match says so, with Clear search, which empties the field, focus in it."""
    shown = await show()
    await open_find(shown)
    await search_for(shown, "zz")
    assert "No attendees match \N{LEFT DOUBLE QUOTATION MARK}zz\N{RIGHT DOUBLE QUOTATION MARK}" in sheet_texts(shown)  # fmt: skip
    clear = next(
        c
        for c in walk(sheet(shown))
        if isinstance(c, ft.Button) and getattr(c, "content", None) == "Clear search"
    )
    before = focused[0]
    await shown.click(clear)
    assert BEFORE in sheet_texts(shown)
    (node,) = [n for n in in_sheet(shown, "coc.search") if n.identifier == "coc.search"]
    assert cast(ft.TextField, node.content).value == ""
    assert focused[0] > before  # Clear went: the focus is back in the field


async def test_a_broad_query_shows_25_rows_and_asks_to_refine(
    show: Show, switch: Switch
) -> None:
    """3,004 attendees: "a" gives 25 rows and "Showing 25. Refine your search."."""
    switch.inner = seeded_mock(attendees=3000)
    shown = await show()
    await open_find(shown)
    await search_for(shown, "a")
    assert len(rows(shown)) == 25
    (more,) = in_sheet(shown, "coc.search.more")
    assert more.live_region and MORE in sheet_texts(shown)
    await search_for(shown, "zoe")  # folded: Zoë
    assert rows(shown) and all(r.startswith("Zoë") for r in rows(shown))


async def test_a_row_opens_the_review_and_record_reaches_the_panel(
    show: Show, mock: Any, switch: Switch, focused: list[int]
) -> None:
    """A tap: the sheet closes, the review opens; Record: one incident, the panel, the count."""
    shown = await show()
    await open_find(shown)
    await search_for(shown, "mar test")
    task = await tap_row(shown, 0)
    assert sheet(shown) is None
    assert texts(shown)[1:3] == ["Margaret Test", "Badge: Maggie"]
    assert helper(shown) == REVIEW_OPEN  # still paused: no gap between the two
    await type_notes(shown, NOTES)
    before = focused[0]
    await tap(shown, "coc.review.record")
    await asyncio.wait_for(task, 2)
    assert [(i.access_code, i.notes, i.forced) for i in mock.incidents] == [
        ("MOCK0004", NOTES, True)
    ]
    assert panel(shown) == "Incident recorded\nMargaret Test\n1 on record\nScan 1"
    assert helper(shown) is None and focused[0] > before  # back in the badge field
    await open_find(shown)
    await search_for(shown, "mar test")  # a new search shows the new count
    assert rows(shown) == ["Margaret Test, badge Maggie, 1 incident on record"]
    assert switch.paths.count(ATTENDEES) == 1  # the directory was not fetched again


async def test_cancel_in_the_review_says_not_recorded(show: Show, mock: Any) -> None:
    """Cancel in the review from a row: "Not recorded" on the panel, nothing sent."""
    shown = await show()
    await open_find(shown)
    await search_for(shown, "linus")
    task = await tap_row(shown, 0)
    await tap(shown, "coc.review.cancel")
    await asyncio.wait_for(task, 2)
    assert panel(shown) == "Not recorded\nLinus Placeholder\nScan 1"
    assert mock.incidents == []


@pytest.mark.parametrize("how", ["close", "dismiss"])
async def test_closing_forgets_the_query_and_refocuses_the_field(
    show: Show, focused: list[int], how: str
) -> None:
    """Close or Back (D-208): the sheet goes, the next opens empty, focus in the field."""
    shown = await show()
    await open_find(shown)
    await search_for(shown, "linus")
    before = focused[0]
    if how == "close":
        (close,) = in_sheet(shown, "coc.search.close")
        await shown.click(cast(ft.IconButton, close.content))
    else:
        await shown.event(cast(ft.BottomSheet, sheet(shown)), "dismiss")
    assert sheet(shown) is None
    assert helper(shown) is None and focused[0] > before
    await open_find(shown)
    assert rows(shown) == [] and BEFORE in sheet_texts(shown)
    (node,) = [n for n in in_sheet(shown, "coc.search") if n.identifier == "coc.search"]
    assert cast(ft.TextField, node.content).value == ""


async def test_a_late_dismissal_of_the_last_sheet_leaves_the_next_open(
    show: Show,
) -> None:
    """Flutter reports a closed sheet's dismissal late: the next sheet stays open."""
    shown = await show()
    await open_find(shown)
    first = cast(ft.BottomSheet, sheet(shown))
    (close,) = in_sheet(shown, "coc.search.close")
    await shown.click(cast(ft.IconButton, close.content))
    await open_find(shown)
    await shown.event(first, "dismiss")  # the first sheet's route has finished closing
    assert sheet(shown) is not None and helper(shown) == SEARCH_OPEN


async def test_no_identifier_or_log_holds_an_access_code_or_the_query(
    show: Show, mock: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """D-72: rows are named by their place; searching and recording log nothing of it."""
    caplog.set_level(logging.INFO)
    caplog.set_level(logging.DEBUG, logger="pycon_us")
    shown = await show()
    await open_find(shown)
    await search_for(shown, "margaret")
    names = [str(n.identifier) for n in in_sheet(shown, "coc.")]
    assert names and not any("MOCK" in n for n in names)
    task = await tap_row(shown, 0)
    await type_notes(shown, NOTES)
    await tap(shown, "coc.review.record")
    await asyncio.wait_for(task, 2)
    logged = caplog.text
    assert "margaret" not in logged.lower() and "MOCK0004" not in logged
    assert NOTES not in logged
    assert "margaret" not in str(shown.storage.prefs.values).lower()  # pyright: ignore[reportAttributeAccessIssue]


def test_a_row_reads_as_one_phrase() -> None:
    """The name, the badge only when it differs, the count in words."""
    same = Attendee("C1", "Ada", "", "Ada", 2)
    other = Attendee("C2", "Grace Sample", "", "Grace S.", 0)
    assert phrase(same) == "Ada, 2 incidents on record"
    assert phrase(other) == "Grace Sample, badge Grace S., no incidents on record"


async def test_the_rows_wait_for_typing_to_pause(
    show: Show, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-46's debounce: the rows follow the text only once typing has paused."""
    monkeypatch.setattr(coc_search, "DEBOUNCE_SECONDS", 0.05)
    shown = await show()
    await open_find(shown)
    await search_for(shown, "linus")
    assert rows(shown) == [] and BEFORE in sheet_texts(shown)  # still typing
    await asyncio.sleep(0.1)
    await shown.settle()
    assert rows(shown) == ["Linus Placeholder, badge Linus, 3 incidents on record"]


@pytest.fixture
def answer(monkeypatch: pytest.MonkeyPatch) -> asyncio.Event:
    """Flutter's answer to a focus request: at once, unless a test clears it (D-243)."""
    given = asyncio.Event()
    given.set()

    async def focus(_: ft.TextField) -> None:
        await given.wait()

    monkeypatch.setattr(ft.TextField, "focus", focus)
    return given


def search_field(shown: Shown) -> ft.TextField:
    """The open sheet's search field."""
    (node,) = [n for n in in_sheet(shown, "coc.search") if n.identifier == "coc.search"]
    return cast(ft.TextField, node.content)


def clear_button(shown: Shown) -> ft.IconButton:
    """The search field's Clear button, shown while it holds text."""
    return next(
        c
        for c in walk(sheet(shown))
        if isinstance(c, ft.IconButton) and c.tooltip == "Clear search"
    )


async def report(shown: Shown, text: str) -> None:
    """Flutter's report of ``text`` in the search field, its event not run out."""
    field = search_field(shown)
    patch_dataclass(field, {"value": text})
    await shown.session.dispatch_event(field._i, "change", text)


async def test_a_key_reported_after_clear_renders_is_dropped_with_the_field(
    show: Show, answer: asyncio.Event
) -> None:
    """D-243: a key typed on the old text before Clear landed never brings it back.

    Its report comes in after the render that sent the empty text and before
    Flutter answers the focus that followed: dropped, and the empty text sent again.
    """
    shown = await show()
    await open_find(shown)
    answer.set()
    await search_for(shown, "lin")
    answer.clear()  # Flutter has not had the empty text yet
    await shown.click(clear_button(shown))
    await search_for(shown, "linus")  # typed on the old text, in flight
    answer.set()
    await shown.settle()
    assert search_field(shown).value == ""
    assert rows(shown) == [] and BEFORE in sheet_texts(shown)
    await search_for(shown, "ada")  # once landed, keys count again
    assert rows(shown)[0].startswith("Ada Example")


async def test_keys_reported_before_clear_renders_are_dropped(
    show: Show, answer: asyncio.Event
) -> None:
    """D-243: keys whose reports beat Clear's re-render are dropped, as Flutter does."""
    shown = await show()
    await open_find(shown)
    answer.set()
    await search_for(shown, "lin")
    answer.clear()
    await shown.session.dispatch_event(clear_button(shown)._i, "click", None)
    await report(shown, "linu")
    await report(shown, "linus")
    answer.set()
    await shown.settle()
    assert search_field(shown).value == ""
    assert rows(shown) == [] and BEFORE in sheet_texts(shown)


async def test_a_tap_on_a_row_the_results_replaced_is_dropped(show: Show) -> None:
    """A tap sent from Linus's row, delayed past new results, never opens Ada's review."""
    shown = await show()
    await open_find(shown)
    await search_for(shown, "linus")
    node = in_sheet(shown, "coc.search.row.0")[0]
    linus = next(
        c
        for c in walk(sheet(shown))
        if isinstance(c, ft.Container) and c.content is node
    )
    await search_for(shown, "ada")  # Ada's row now sits where Linus's was
    task = asyncio.create_task(shown.click(linus))  # a pick waits on its review
    await shown.settle()
    assert dialog(shown) is None and sheet(shown) is not None
    await asyncio.wait_for(task, 2)
