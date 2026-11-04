"""Tests for the Map's Job fair pane (#407; MAP-04, SPON-10, D-254, ux.md §6.3).

`JobFairPane` runs outside a renderer, as `test_map.py` runs the Rooms pane: its
hooks are replaced, and a fake page is bound as Flet binds a session's page. The
tables themselves are `core.expo.job_fair_tables` (`test_expo.py`); the pane in
the Map, its tab, its card's tap and a row's way to the sponsor and back are
`test_map_tabs.py`'s. How the pane looks and reads is checked on devices (the PR).
"""

import dataclasses
import inspect
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.expo import JobFairTable, job_fair_tables
from pycon_us.core.models import ConferenceData
from pycon_us.memory import ViewMemory
from pycon_us.screens import map_job_fair as pane_module
from pycon_us.screens.map_job_fair import (
    JobFairPane,
    roles_phrase,
    table_line,
    table_phrase,
)
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.ui import states
from pycon_us.year_map import MapData
from tests.fake_page import FakePage, bound, phone_margin
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)
from tests.feeds import processed
from tests.trees import descendants, texts

YEAR = load_year(2026)
STRIP = ft.Text("strip")
"""What the test's `StatusStrip` stands in for."""

CARD = ft.Text("card")
"""What the test's `job_fair_card()` stands in for: a component needs a renderer."""

NOTE = "The printed plan shows some tables with other sponsors."
"""The start of 2026's note, `map.toml`'s `note` on the `job-fair` plan."""


@pytest.fixture(scope="module")
def data() -> ConferenceData:
    """Return the recorded 2026 feed, processed once for the module."""
    return processed(2026)


@pytest.fixture
def page() -> Iterator[FakePage]:
    """Yield a fake page bound as Flet binds a session's page."""
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """Return a session's services with the memory fakes, storing under `tmp_path`."""
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    return Services(
        year=YEAR,
        storage=storage,
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )


class FakeConference(SimpleNamespace):
    """The parts of `Conference` the pane reads, and its refresh, recorded."""

    def __init__(self, data: ConferenceData | None, problem: str | None = None):
        """Hold `data` and `problem`, not refreshing, with no refresh counted."""
        super().__init__(
            data=data, problem=problem, refreshing=False, asked=False, refreshes=0
        )

    def status(self, _info: object) -> str:
        """Say `refreshing` only while a refresh the user asked for runs (D-181)."""
        return "refreshing" if self.refreshing and self.asked else "fresh"

    async def refresh(self, *args: object, **kwargs: object) -> None:
        """Count a refresh, as the Try again button asks for one."""
        self.refreshes += 1


type Render = Callable[..., list[ft.Control]]
"""The `render` fixture's function: the pane's rows at a conference."""


@pytest.fixture
def render(monkeypatch: pytest.MonkeyPatch, svc: Services, page: FakePage) -> Render:
    """Render `JobFairPane` once and return its rows, checking it is the pane's list.

    The card's stand-in records the map data and identifier it was asked for.
    """
    monkeypatch.setattr(pane_module, "use_services", lambda: svc)
    monkeypatch.setattr(pane_module, "use_margin", phone_margin)
    monkeypatch.setattr(pane_module, "StatusStrip", lambda: STRIP)
    monkeypatch.setattr(states, "SkeletonList", lambda label: ft.Text(label))

    def card(data: MapData, *, identifier: str) -> ft.Control | None:
        assert identifier == "map.job_fair.location"
        return CARD if data.plan("job-fair") else None

    monkeypatch.setattr(pane_module, "job_fair_card", card)
    monkeypatch.setattr(ft, "use_view_path", lambda: "/map")

    def render(conference: FakeConference) -> list[ft.Control]:
        monkeypatch.setattr(pane_module, "use_conference", lambda: conference)
        pane = inspect.unwrap(JobFairPane)(ft.Ref[ft.ListView](), lambda _: None)
        assert isinstance(pane, ft.ListView)
        assert pane.key == "job-fair"
        return list(pane.controls)

    return render


def all_texts(rows: list[ft.Control]) -> list[str]:
    """Return every text under `rows`, in reading order."""
    return [text for row in rows for text in texts(row)]


def table_nodes(rows: list[ft.Control]) -> list[ft.Semantics]:
    """Return the table rows' nodes, in the pane's order."""
    return [
        node
        for row in rows
        for node in descendants(row)
        if isinstance(node, ft.Semantics)
        and str(node.identifier or "").startswith("map.table.")
    ]


def descendants_of(rows: list[ft.Control]) -> list[ft.Control]:
    """Return every control under `rows`, the rows included, in reading order."""
    return [node for row in rows for node in descendants(row)]


def state(rows: list[ft.Control], identifier: str) -> ft.Semantics:
    """Return the one `Semantics` node with `identifier` under `rows`."""
    (found,) = [
        node
        for row in rows
        for node in descendants(row)
        if isinstance(node, ft.Semantics) and node.identifier == identifier
    ]
    return found


# ------------------------------------------------------------------ the list


def test_the_card_and_note_head_the_tables(
    render: Render, data: ConferenceData
) -> None:
    """The plan's card, then the note, then "Tables" and a row per sponsor (D-254).

    The note wraps with no line limit; "Tables" is a level-2 heading.
    """
    rows = render(FakeConference(data))
    assert rows[0].content is CARD  # pyright: ignore[reportAttributeAccessIssue]
    note = cast(ft.Text, cast(ft.Container, rows[1]).content)
    assert str(note.value).startswith(NOTE)
    assert note.max_lines is None
    heading = rows[2]
    assert isinstance(heading, ft.Semantics) and heading.header
    assert texts(heading) == ["Tables"]
    nodes = table_nodes(rows)
    assert [str(node.identifier) for node in nodes] == [
        f"map.table.{row.sponsor.slug}" for row in job_fair_tables(data)
    ]


def test_a_row_reads_its_table_sponsor_and_roles(
    render: Render, data: ConferenceData, page: FakePage
) -> None:
    """A row shows "T2 · Bloomberg · 15 open roles", read "Table T2, Bloomberg, …".

    One button node, its line excluded; a tap pushes the sponsor on the Map.
    """
    rows = render(FakeConference(data))
    (node,) = [n for n in table_nodes(rows) if n.identifier == "map.table.bloomberg"]
    assert node.label == "Table T2, Bloomberg, 15 open roles"
    assert node.button and node.exclude_semantics
    assert texts(node) == ["T2 · Bloomberg · 15 open roles"]
    (row,) = [
        r
        for r in descendants_of(rows)
        if isinstance(r, ft.MergeSemantics)
        and isinstance(r.content, ft.Container)
        and r.content.content is node
    ]
    cast(Callable[[], None], cast(ft.Container, row.content).on_click)()
    assert page.navigated == ["/map/sponsor/bloomberg"]


def test_a_row_s_map_button_shows_its_table_on_the_plan(
    render: Render, data: ConferenceData, page: FakePage
) -> None:
    """Beside each row, its own stop: "Show table T7 on the plan", a 48 dp map button.

    It pushes `…/plan/job-fair?table=T7` on the Map (#464); both of T7's sponsors
    have one, and the row itself still pushes the sponsor.
    """
    rows = render(FakeConference(data))
    for slug in ("chainguard", "red-hat"):
        node = state(rows, f"map.show_table.{slug}")
        button = cast(ft.IconButton, node.content)
        assert button.icon == ft.Icons.MAP_OUTLINED
        assert button.tooltip == "Show table T7 on the plan"
        cast(Callable[[], None], button.on_click)()
    assert page.navigated == ["/map/plan/job-fair?table=T7"] * 2


def test_the_count_shows_only_with_roles() -> None:
    """No roles, no count: "T1 · Google", read "Table T1, Google"; one role is singular."""
    sponsor = next(
        row.sponsor for row in job_fair_tables(processed(2026)) if row.table == "T1"
    )
    none = JobFairTable("T1", sponsor, 0)
    assert (table_line(none), table_phrase(none)) == ("T1 · Google", "Table T1, Google")
    assert roles_phrase(1) == "1 open role"
    assert roles_phrase(0) == ""


def test_a_year_without_a_note_shows_none(
    render: Render,
    svc: Services,
    data: ConferenceData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `job-fair` plan without a note: the card, then the tables' heading."""
    plans = tuple(dataclasses.replace(plan, note="") for plan in YEAR.map.plans)
    year = dataclasses.replace(YEAR, map=dataclasses.replace(YEAR.map, plans=plans))
    bare = dataclasses.replace(svc, year=year)
    monkeypatch.setattr(pane_module, "use_services", lambda: bare)
    rows = render(FakeConference(data))
    assert rows[0].content is CARD  # pyright: ignore[reportAttributeAccessIssue]
    assert texts(rows[1]) == ["Tables"]
    assert not any(text.startswith(NOTE) for text in all_texts(rows))


# ------------------------------------------------------------------ the states


def test_while_loading_the_card_stays_over_the_skeleton(render: Render) -> None:
    """Without data yet: the strip, the card (the plan is bundled) and the skeleton."""
    rows = render(FakeConference(None))
    assert rows[0] is STRIP
    assert rows[1].content is CARD  # pyright: ignore[reportAttributeAccessIssue]
    assert texts(rows[-1]) == ["Loading tables"]
    assert table_nodes(rows) == []


async def test_a_failed_first_fetch_offers_try_again(render: Render) -> None:
    """After a failed first fetch: "Can't load the tables", whose button refreshes."""
    conference = FakeConference(None, problem="offline")
    rows = render(conference)
    found = state(rows, "map.job_fair.no_data")
    assert texts(found)[:2] == [
        "Can't load the tables",
        "Connect to the internet and try again.",
    ]
    (button,) = [
        node
        for row in rows
        for node in descendants(row)
        if isinstance(node, ft.FilledTonalButton)
    ]
    await cast(Callable[[], Any], button.on_click)()
    assert conference.refreshes == 1


def test_a_feed_without_tables_keeps_the_card_and_says_so(
    render: Render, data: ConferenceData
) -> None:
    """No sponsor with a table: the card, the note and "No job fair tables yet"."""
    levels = tuple(
        dataclasses.replace(
            level,
            sponsors=tuple(
                dataclasses.replace(sponsor, job_fair_table=None)
                for sponsor in level.sponsors
            ),
        )
        for level in data.sponsor_levels
    )
    bare = dataclasses.replace(data, sponsor_levels=levels)
    rows = render(FakeConference(bare))
    assert rows[0].content is CARD  # pyright: ignore[reportAttributeAccessIssue]
    assert texts(state(rows, "map.job_fair.empty"))[0] == "No job fair tables yet"
    assert "Tables" not in all_texts(rows)
