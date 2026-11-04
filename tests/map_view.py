"""The Map's harness, for its tabs' and its panes' test modules (#391, #623).

`tests/test_map_tabs.py` (the tabs and the panes' places) and
`tests/test_map_panes.py` (Floor plans' cards, Job fair and the app bar) take
`render` by assignment (§3.1): `Map` runs in a real Flet session
(`tests/harness.py`'s `showing()`) over the 2026 feed and `map.toml`, with
`ListView.scroll_to` recorded in a `MapShown` instead of sent to a client.
"""

import dataclasses
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

import flet as ft
import pytest

from pycon_us.config import YearData, load_year
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import map as screen
from pycon_us.state import Conference
from tests import harness, links
from tests.feeds import processed
from tests.harness import Shown
from tests.trees import descendants

YEAR = load_year(2026)


PLAN_IDS = ["campus", "concourse", "upper", "arena", "seaside"]
"""The 2026 floor plans, in `map.toml`'s order (MAP-02): the expo's and the job
fair's are not among them."""


@dataclasses.dataclass
class MapShown(Shown):
    """The harness's `Shown` on the Map, with the scrolls its lists were asked for."""

    scrolls: list[tuple[str, dict[str, Any]]] = dataclasses.field(default_factory=list)
    """Each `scroll_to`: the list's key and its arguments."""

    @property
    def tabs(self) -> ft.Tabs:
        """The Map's one `Tabs`."""
        (found,) = self.find(ft.Tabs)
        return found

    @property
    def pane(self) -> ft.ListView:
        """The one pane shown: the `ListView` under the tab bar."""
        (found,) = self.find(ft.ListView)
        return found

    def cards(self) -> list[str]:
        """The Floor plans cards' identifiers, in the pane's order."""
        return [
            str(node.identifier)
            for row in self.pane.controls
            for node in descendants(row)
            if isinstance(node, ft.Semantics)
            and str(node.identifier or "").startswith("map.plan.")
        ]

    async def pick(self, index: int) -> None:
        """Pick a tab as the user does: Flutter moves the selection, then reports it."""
        self.session.apply_patch(self.tabs._i, {"selected_index": index})
        await self.session.dispatch_event(self.tabs._i, "change", index)
        await self.settle()

    async def scroll_end(self, pixels: float) -> None:
        """What Flutter sends when a scroll of the pane shown ends at `pixels`."""
        data = {
            "event_type": "end",
            "pixels": pixels,
            "min_scroll_extent": 0.0,
            "max_scroll_extent": 4000.0,
            "viewport_dimension": 700.0,
        }
        await self.event(self.pane, "scroll", data)


type Render = Callable[..., Awaitable[MapShown]]


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Yield a function that opens the Map at a route and returns its `MapShown`.

    The route is `/map` unless the test gives another (a query); the view memory and
    the year can be given too, a memory kept across sessions as the app keeps it.
    """
    shown_now: list[MapShown] = []

    async def scroll_to(self: ft.ListView, **kwargs: Any) -> None:
        shown_now[-1].scrolls.append((str(self.key), kwargs))

    monkeypatch.setattr(ft.ListView, "scroll_to", scroll_to)
    data = processed(2026)

    async def show(
        stack: AsyncExitStack,
        route: str = "/map",
        *,
        memory: ViewMemory | None = None,
        year: YearData = YEAR,
    ) -> MapShown:
        def make(*args: Any, **kwargs: Any) -> MapShown:
            made = MapShown(*args, **kwargs)
            shown_now.append(made)
            return made

        return await stack.enter_async_context(
            harness.showing(
                screen.Map,
                screen,
                year=year,
                conference=Conference(data=data, source="bundled", version=1),
                tmp_path=tmp_path,
                monkeypatch=monkeypatch,
                view_path="/map",
                prefs=Prefs(loaded=True),
                memory=memory,
                route=route,
                kind=make,
            )
        )

    async with AsyncExitStack() as stack:

        async def opened(*args: Any, **kwargs: Any) -> MapShown:
            return await show(stack, *args, **kwargs)

        yield opened


def pane_shown(shown: links.Shown) -> str:
    """The key of the one Map pane in the app's Views: its slug."""
    slugs = {pane.slug for pane in screen.PANES}
    (pane,) = [lv for lv in shown.find(ft.ListView) if lv.key in slugs]
    return str(pane.key)
