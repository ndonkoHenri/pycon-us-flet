"""Tests for the expo's Map | List switch and its List (#404; EXPO-01, EXPO-04, D-254).

The rows' order and filter are `core.expo`'s, tested over the 2026 feed and
`map.toml`. The Map runs in a real Flet session (`tests/sessions.py`) on its Expo
pane; `ListView.scroll_to` is recorded instead of sent to a client. How the List
looks, and what TalkBack and VoiceOver say, are checked on devices (the PR).
"""

import dataclasses
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.expo import (
    ExpoRow,
    by_name,
    expo_booths,
    filter_rows,
    filter_sponsors,
    list_rows,
)
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import expo_list, expo_pane, plan
from pycon_us.screens import map as screen
from pycon_us.screens.expo import placed_booths
from pycon_us.state import Conference
from tests import harness
from tests.feeds import processed
from tests.trees import descendants
from tests.viewers import FakeViewer

YEAR = load_year(2026)
DATA = processed(2026)
EXPO = expo_booths(DATA, YEAR.map.booths)
ROWS = list_rows(EXPO.booths)


def keys(rows: tuple[ExpoRow, ...]) -> list[str]:
    """The rows' keys, in order."""
    return [row.key for row in rows]


# ------------------------------------------------------------------ the rows


def test_the_list_has_a_row_per_exhibitor_and_per_empty_booth_by_booth() -> None:
    """61 booths make 68 rows: shared booths' exhibitors together, by name (D-254)."""
    assert len(ROWS) == 68
    assert ROWS[0].number == "112"
    numbers = [row.number for row in ROWS]
    assert numbers == sorted(numbers, key=lambda n: (len(n), n))  # natural order
    shared = [row.name for row in ROWS if row.number == "726"]
    assert shared == [
        "Inland Empire Python Users Group",
        "PyBeach",
        "San Diego Python",
        "SoCal Python",
    ]
    (lounge,) = [row for row in ROWS if row.number == "606"]
    assert (lounge.sponsor, lounge.name, lounge.key) == (None, "Attendee lounge", "606")


def test_name_order_is_folded_names_then_booths_and_nameless_rows_last() -> None:
    """Sort by name: one name per row, A to Z as people read it; numbers alone last."""
    named = by_name(ROWS)
    assert sorted(keys(named)) == sorted(keys(ROWS))
    folded = [row.name.casefold() for row in named]
    assert folded == sorted(folded)
    before_feed = list_rows(placed_booths(None, YEAR.map.booths))
    assert {row.name for row in before_feed} == {
        "Python Software Foundation",
        "Attendee lounge",
        "",
    }
    assert [row.name for row in by_name(before_feed)][:2] == [
        "Attendee lounge",
        "Python Software Foundation",
    ]


@pytest.mark.parametrize(
    ("query", "found"),
    [
        ("socal", ["726.socal-python"]),
        ("613", ["613.bloomberg"]),
        ("SÖCAL  python", ["726.socal-python"]),
        ("lounge", ["606"]),
        ("726 pybeach", ["726.pybeach"]),
    ],
)
def test_the_filter_matches_names_and_numbers_folded(
    query: str, found: list[str]
) -> None:
    """Every word must be in the row's number or name, case and accents ignored."""
    assert keys(filter_rows(ROWS, query)) == found


@pytest.mark.parametrize("query", ["", "  ", "\N{RIGHT SINGLE QUOTATION MARK}"])
def test_a_filter_with_no_word_keeps_the_rows_and_sponsors_themselves(
    query: str,
) -> None:
    """A blank filter returns the very tuples, so the screen knows nothing narrowed."""
    assert filter_rows(ROWS, query) is ROWS
    assert filter_sponsors(EXPO.unplaced, query) is EXPO.unplaced


def test_unplaced_sponsors_are_found_by_name_or_booth() -> None:
    """The sponsors off the plan (2026: Phemeral at 139, Astral at 336) filter too."""
    assert [s.name for s in EXPO.unplaced] == ["Phemeral", "Astral"]
    assert [s.name for s in filter_sponsors(EXPO.unplaced, "139")] == ["Phemeral"]
    assert [s.name for s in filter_sponsors(EXPO.unplaced, "astral")] == ["Astral"]


def test_a_row_reads_as_its_booth_name_and_level() -> None:
    """One phrase per row (D-33): booth, name, level; a label alone; a number alone."""
    by_key = {row.key: row for row in ROWS}
    pybeach, psf = by_key["726.pybeach"], by_key["407"]
    assert expo_list.row_phrase(pybeach) == "Booth 726, PyBeach, Community sponsor"
    assert expo_list.row_line(pybeach) == "Booth 726 \N{MIDDLE DOT} Community"
    assert expo_list.row_phrase(psf) == "Booth 407, Python Software Foundation"
    assert expo_list.row_line(psf) == "Booth 407"
    (bare, *_) = [r for r in list_rows(placed_booths(None, YEAR.map.booths))]
    assert (expo_list.row_phrase(bare), expo_list.row_line(bare)) == ("Booth 112", "")


# ------------------------------------------------------------------ the pane


@dataclasses.dataclass
class ListShown(harness.Shown):
    """The harness's `Shown` on the Expo pane, with the scrolls its List asked for."""

    scrolls: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    """Each `scroll_to`'s arguments."""

    @property
    def switch(self) -> ft.SegmentedButton:
        """The pane's Map | List switch."""
        (found,) = self.find(ft.SegmentedButton)
        return found

    @property
    def listed(self) -> list[str]:
        """The List's row and sponsor identifiers, in its order."""
        (listed,) = self.find(ft.ListView)
        return [
            str(node.identifier).removeprefix("expo.")
            for item in listed.controls
            # A row is a component: its rendered body is its `_b` (Flet's).
            for node in descendants(getattr(item, "_b", item))
            if isinstance(node, ft.Semantics)
            and str(node.identifier or "").startswith(("expo.row.", "expo.sponsor."))
        ]

    async def show(self, view: str) -> None:
        """Pick a segment as the user does: Flutter moves the selection, then reports."""
        self.session.apply_patch(self.switch._i, {"selected": [view]})
        await self.session.dispatch_event(self.switch._i, "change", [view])
        await self.settle()

    async def type(self, text: str) -> None:
        """Type into the filter as Flutter reports it: the value, then the event."""
        (field,) = self.find(ft.TextField)
        self.session.apply_patch(field._i, {"value": text})
        await self.event(field, "change", None)

    async def tap_row(self, key: str) -> None:
        """Tap a row: its `Container`, around its node."""
        await self.click(cast(ft.Container, self.node(f"expo.row.{key}").parent))
        await self.settle()

    async def scroll_end(self, pixels: float) -> None:
        """What Flutter sends when a scroll of the List ends at `pixels`."""
        (listed,) = self.find(ft.ListView)
        data = {
            "event_type": "end",
            "pixels": pixels,
            "min_scroll_extent": 0.0,
            "max_scroll_extent": 4000.0,
            "viewport_dimension": 600.0,
        }
        await self.event(listed, "scroll", data)


type Render = Callable[..., Awaitable[ListShown]]


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Yield a function that opens the Map's Expo pane and returns its `ListShown`.

    A screen reader can be on, and a view memory given, kept as the app keeps it.
    """
    shown_now: list[ListShown] = []

    async def scroll_to(self: ft.ListView, **kwargs: Any) -> None:
        shown_now[-1].scrolls.append(kwargs)

    monkeypatch.setattr(ft.ListView, "scroll_to", scroll_to)

    async def show(
        stack: AsyncExitStack,
        *,
        screen_reader: bool = False,
        memory: ViewMemory | None = None,
    ) -> ListShown:
        def make(*args: Any, **kwargs: Any) -> ListShown:
            made = ListShown(*args, **kwargs)
            shown_now.append(made)
            return made

        return await stack.enter_async_context(
            harness.showing(
                screen.Map,
                screen,
                year=YEAR,
                conference=Conference(data=DATA, source="bundled", version=1),
                tmp_path=tmp_path,
                monkeypatch=monkeypatch,
                view_path="/map",
                prefs=Prefs(loaded=True, screen_reader=screen_reader),
                memory=memory,
                route="/map?tab=expo",
                kind=make,
            )
        )

    async with AsyncExitStack() as stack:

        async def opened(**kwargs: Any) -> ListShown:
            return await show(stack, **kwargs)

        yield opened


async def test_the_pane_opens_on_the_map_or_on_the_list_under_a_reader(
    render: Render,
) -> None:
    """The plan first; the List first while a screen reader is on (ux.md §6.2)."""
    shown = await render()
    assert shown.switch.selected == [expo_pane.MAP]
    assert shown.find(ft.ListView) == []
    assert len(shown.find(ft.InteractiveViewer)) == 1
    read = await render(screen_reader=True)
    assert read.switch.selected == [expo_pane.LIST_VIEW]
    assert read.find(ft.InteractiveViewer) == []
    assert read.memory.expo_view == ""  # not a pick: the reader's default
    assert len(read.nodes("expo.view.")) == 2


async def test_the_list_shows_every_row_then_the_sponsors_off_the_plan(
    render: Render,
) -> None:
    """68 rows by booth, then "Not on the map yet" with Phemeral and Astral."""
    shown = await render(screen_reader=True)
    rows = shown.listed
    assert rows[:68] == [f"row.{key}" for key in keys(ROWS)]
    assert rows[68:] == ["sponsor.phemeral", "sponsor.astral"]
    assert expo_list.UNPLACED in shown.texts()
    assert shown.node("expo.row.613.bloomberg").label == (
        "Booth 613, Bloomberg, Visionary sponsor"
    )


async def test_a_pick_of_the_switch_is_remembered(render: Render) -> None:
    """A segment picked shows its view and stays for the next opening (D-18)."""
    memory = ViewMemory()
    shown = await render(memory=memory)
    await shown.show(expo_pane.LIST_VIEW)
    assert memory.expo_view == "list"
    assert len(shown.find(ft.ListView)) == 1
    again = await render(memory=memory)
    assert again.switch.selected == ["list"]
    await again.show(expo_pane.MAP)
    assert memory.expo_view == "map"
    after = await render(memory=memory, screen_reader=True)
    assert after.switch.selected == ["map"]  # the user's pick beats the reader's


async def test_a_row_shows_its_booth_on_the_map_with_its_card(render: Render) -> None:
    """A tap switches to the Map with the booth selected and its card (EXPO-04)."""
    shown = await render(screen_reader=True)
    await shown.tap_row("726.pybeach")
    assert (shown.memory.expo_booth, shown.memory.expo_view) == ("726", "map")
    assert shown.switch.selected == ["map"]
    assert shown.node("expo.card").label == "Booth 726, Community, 4 exhibitors"


async def test_back_to_the_list_keeps_its_filter_order_and_scroll(
    render: Render,
) -> None:
    """Map and back: the filter's text, the name order and the offset come back."""
    shown = await render(screen_reader=True)
    await shown.scroll_end(300.0)
    (chip,) = shown.find(ft.Chip)
    await shown.click(chip)
    await shown.type("python")
    await shown.tap_row("726.socal-python")
    await shown.show(expo_pane.LIST_VIEW)
    (field,) = shown.find(ft.TextField)
    assert field.value == "python"
    (chip,) = shown.find(ft.Chip)
    assert chip.selected
    rows = [row.removeprefix("row.") for row in shown.listed]
    assert rows == keys(filter_rows(by_name(ROWS), "python"))
    assert shown.scrolls[-1] == {"offset": 300.0, "duration": 0}


async def test_the_count_says_what_the_filter_found_and_a_miss_offers_clear(
    render: Render,
) -> None:
    """The count line while the filter narrows; a miss has its own state (D-226)."""
    shown = await render(screen_reader=True)
    assert shown.nodes("expo.count") == []
    await shown.type("socal")
    assert shown.listed == ["row.726.socal-python"]
    assert "1 match" in shown.texts()
    await shown.type("139")
    assert shown.listed == ["sponsor.phemeral"]
    await shown.type("nowhere")
    assert shown.listed == []
    assert shown.nodes("expo.count") == []
    assert len(shown.nodes("expo.no_match")) == 1


def test_the_count_line_says_match_or_matches() -> None:
    """One match, then matches."""
    assert expo_list.found_line(1) == "1 match"
    assert expo_list.found_line(4) == "4 matches"


async def test_a_pushed_hall_keeps_its_zoom_across_the_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`…/plan/expo`: Map, List, Map puts the zoom back, under the View's path (D-18)."""
    viewer = FakeViewer()
    viewer.install(monkeypatch)
    path = "/map/plan/expo"
    async with harness.showing(
        plan.ExpoPlan,
        plan,
        year=YEAR,
        conference=Conference(data=DATA, source="bundled", version=1),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        view_path=path,
        prefs=Prefs(loaded=True, reduce_motion=True),
        kind=ListShown,
    ) as shown:

        async def lay_out() -> None:
            """Report the hall's size, as Flutter does after its first layout."""
            (sized,) = [c for c in shown.find(ft.Container) if c.on_size_change]
            await shown.event(sized, "size_change", {"w": 382.0, "h": 560.0})

        await lay_out()
        viewer.scale, viewer.x, viewer.y = 3.0, -300.0, -150.0
        (layer,) = shown.find(ft.InteractiveViewer)
        data = {"s": 3.0, "tx": -300.0, "ty": -150.0, "tz": 0.0, "m": []}
        await shown.event(layer, "transform_changed", data)
        assert shown.memory.map_zooms == {path: (3.0, -300.0, -150.0)}
        await shown.show(expo_pane.LIST_VIEW)
        viewer.scale, viewer.x, viewer.y = 1.0, 0.0, 0.0  # the next viewer is new
        viewer.calls.clear()
        await shown.show(expo_pane.MAP)
        await lay_out()
        assert [name for name, _ in viewer.calls] == ["reset", "zoom", "pan"]
        assert (viewer.scale, viewer.x, viewer.y) == pytest.approx(
            (3.0, -300.0, -150.0)
        )


# ------------------------------------------------------------------ the app bar


@asynccontextmanager
async def pushed_hall(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    route: str = "/map/plan/expo",
    memory: ViewMemory | None = None,
) -> AsyncIterator[ListShown]:
    """Open `…/plan/expo` at `route` as the harness's pushed View."""
    async with harness.showing(
        plan.ExpoPlan,
        plan,
        year=YEAR,
        conference=Conference(data=DATA, source="bundled", version=1),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        view_path="/map/plan/expo",
        prefs=Prefs(loaded=True, reduce_motion=True),
        memory=memory,
        route=route,
        kind=ListShown,
    ) as shown:
        yield shown


async def test_the_pushed_hall_s_bar_is_still_on_the_map_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The booth card scrolls inside the Map, so its bar stays; the List scrolls the page.

    Flutter's `AppBar` takes the card's scroll for the page's and tints the bar
    (#962, F297): the Map's bar is still, the List's tints as every list's does.
    """
    FakeViewer().install(monkeypatch)
    async with pushed_hall(tmp_path, monkeypatch) as shown:
        assert shown.still_bars[-1] is True
        await shown.show(expo_pane.LIST_VIEW)
        assert shown.still_bars[-1] is False
        await shown.show(expo_pane.MAP)
        assert shown.still_bars[-1] is True


async def test_a_link_off_the_plan_opens_the_list_with_a_tinting_bar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Booth 139 is not on the plan, so the List shows though the memory says Map."""
    FakeViewer().install(monkeypatch)
    memory = ViewMemory(expo_view=expo_pane.MAP)
    route = "/map/plan/expo?booth=139"
    async with pushed_hall(tmp_path, monkeypatch, route, memory) as shown:
        assert shown.switch.selected == [expo_pane.LIST_VIEW]
        assert shown.still_bars[-1] is False


async def test_the_map_tab_s_bar_is_still_on_the_expo_map_only(
    render: Render,
) -> None:
    """The Map tab's Expo pane has the same card: still on its Map, not on its List."""
    shown = await render()
    assert shown.still_bars[-1] is True
    await shown.show(expo_pane.LIST_VIEW)
    assert shown.still_bars[-1] is False
    await shown.show(expo_pane.MAP)
    assert shown.still_bars[-1] is True


async def test_the_map_tab_s_other_panes_keep_a_tinting_bar(render: Render) -> None:
    """Rooms scrolls the page under the bar, even after the Expo's Map was shown."""
    shown = await render()
    assert shown.still_bars[-1] is True
    (tabs,) = shown.find(ft.Tabs)
    shown.session.apply_patch(tabs._i, {"selected_index": 0})
    await shown.session.dispatch_event(tabs._i, "change", 0)
    await shown.settle()
    assert shown.memory.map_tab != "expo"
    assert shown.still_bars[-1] is False


async def test_the_expo_tab_corrects_the_flag_when_it_comes_back(render: Render) -> None:
    """Rooms, then a List picked elsewhere, then Expo: the bar follows the view shown.

    The parent's flag outlives the pane (it is the last view the pane told), so the
    pane that mounts again must correct it (#962).
    """
    shown = await render()
    slugs = [pane.slug for pane in screen.panes_of(YEAR.map)]
    (tabs,) = shown.find(ft.Tabs)

    async def pick(slug: str) -> None:
        index = slugs.index(slug)
        shown.session.apply_patch(tabs._i, {"selected_index": index})
        await shown.session.dispatch_event(tabs._i, "change", index)
        await shown.settle()

    await pick(screen.ROOMS)
    assert shown.still_bars[-1] is False
    shown.memory.expo_view = expo_pane.LIST_VIEW  # as the pushed hall's switch does
    await pick(screen.EXPO)
    assert shown.switch.selected == [expo_pane.LIST_VIEW]
    assert shown.still_bars[-1] is False
