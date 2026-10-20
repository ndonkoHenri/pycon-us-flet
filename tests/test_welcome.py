"""Tests for Welcome, the first-run page (#423; SHELL-02, STORE-07; D-36, D-287).

``welcome_copy()`` is pure, so its words are pinned at fixed days for two years.
``Welcome`` runs outside a renderer: its hooks are replaced and a fake page is bound
as Flet binds a session's page. How it looks and reads on a screen is checked on
devices (the PR); where the start route sends a session is ``test_routes.py``'s.
"""

import inspect
import logging
from collections.abc import Callable, Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.config import ConferenceInfo, load_year
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import welcome
from pycon_us.screens.welcome import (
    FOOTNOTE,
    INK,
    REMINDERS_ROW,
    ROWS,
    THANKS,
    Welcome,
    welcome_copy,
)
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.theme import BOOT_COLOR
from tests.fakes import (
    FakePage,
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    bound,
)
from tests.test_theme import contrast_ratio
from tests.trees import descendants, only, texts


@pytest.fixture(scope="module")
def info() -> ConferenceInfo:
    """The 2026 conference facts: PyCon US 2026, Long Beach, May 13 to 19."""
    return load_year(2026).conference


# ------------------------------------------------------------------ the words


def test_the_words_come_from_the_year_s_data(info: ConferenceInfo) -> None:
    """The title names the year's conference, the place line its city and dates."""
    copy = welcome_copy(info, date(2026, 1, 10), reminders=False)
    assert copy.title == "Welcome to PyCon US 2026"
    assert copy.place == "Long Beach, CA · May 13–19"
    assert copy.thanks is None


def test_another_year_s_data_gives_that_year_s_words() -> None:
    """Nothing is written for 2026: the 2025 data gives 2025's name, city and dates."""
    info = load_year(2025).conference
    copy = welcome_copy(info, date(2025, 1, 10), reminders=False)
    assert copy.title == f"Welcome to {info.name}" == "Welcome to PyCon US 2025"
    assert copy.place.startswith(f"{info.city} · ")


def test_the_reminders_row_shows_only_when_the_build_has_reminders(
    info: ConferenceInfo,
) -> None:
    """Without reminders the page promises two things; with them, a third: reminders."""
    day = date(2026, 1, 10)
    assert welcome_copy(info, day, reminders=False).rows == ROWS
    assert welcome_copy(info, day, reminders=True).rows == (*ROWS, REMINDERS_ROW)
    assert [phrase for _, phrase in ROWS] == [
        "Plan your schedule and save sessions",
        "Find rooms, booths and hours, even offline",
    ]


@pytest.mark.parametrize(
    ("day", "thanked"),
    [
        (date(2026, 5, 12), False),  # the day before
        (date(2026, 5, 15), False),  # a talk day
        (date(2026, 5, 19), False),  # the last sprint day
        (date(2026, 5, 20), True),  # the day after: it is over
        (date(2026, 12, 1), True),
    ],
)
def test_the_thanks_line_shows_once_the_last_day_is_over(
    info: ConferenceInfo, day: date, thanked: bool
) -> None:
    """After the last sprint day, and only then, the page thanks the reader."""
    copy = welcome_copy(info, day, reminders=False)
    assert copy.thanks == (THANKS if thanked else None)


# ------------------------------------------------------------------ the page


@pytest.fixture
def page() -> Iterator[FakePage]:
    """A ``FakePage`` at ``/``, bound as the page Flet's handlers see."""
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def shared() -> MemoryPrefs:
    """The device's SharedPreferences, in memory."""
    return MemoryPrefs()


@pytest.fixture
def svc(shared: MemoryPrefs, tmp_path: Path) -> Services:
    """The 2026 ``Services`` over in-memory prefs and device services."""
    return Services(
        year=load_year(2026),
        storage=Storage(prefs=shared, directory=tmp_path, year=2026),
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )


@pytest.fixture
def prefs() -> Prefs:
    """Fresh ``Prefs``: Welcome not yet seen."""
    return Prefs()


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch, svc: Services, prefs: Prefs, page: FakePage
) -> Iterator[Callable[[], ft.View]]:
    """Return a function that renders ``Welcome`` on a winter day before 2026's conference.

    The clock is frozen on 2026-01-10 and lifted after the test.
    """
    monkeypatch.setattr(welcome, "use_services", lambda: svc)
    monkeypatch.setattr(welcome, "use_prefs", lambda: prefs)
    clock.set_test_now(
        datetime(2026, 1, 10, 12, tzinfo=load_year(2026).conference.zone)
    )
    try:
        yield lambda: cast(ft.View, inspect.unwrap(Welcome)())
    finally:
        clock.set_test_now(None)


def start_button(view: ft.View) -> ft.FilledButton:
    """Return Get started, found by its identifier as a UI flow finds it."""
    nodes = [n for n in descendants(view) if isinstance(n, ft.Semantics)]
    named = [n for n in nodes if n.identifier == "welcome.start"]
    assert len(named) == 1
    return only(named[0], ft.FilledButton)


async def tap(button: ft.FilledButton) -> None:
    """Call a button's ``on_click``, as a tap does."""
    assert button.on_click is not None
    await cast(Callable[[], Any], button.on_click)()


def test_the_page_is_a_purple_root_without_a_bar(render: Callable[[], ft.View]) -> None:
    """Full-bleed purple in every scheme, no bar of either kind, the roots' key (D-142).

    Its body sits in a ``SafeArea``, clear of the notch and the system bars.
    """
    view = render()
    assert (view.route, view.bgcolor, view.padding) == ("/", BOOT_COLOR, 0)
    assert view.appbar is None and view.navigation_bar is None
    assert isinstance(view.controls[0], ft.SafeArea)


def test_the_page_reads_in_order_with_the_title_as_its_level_1_heading(
    render: Callable[[], ft.View],
) -> None:
    """Title, place, the rows and the footnote, in that order; the title is level 1."""
    view = render()
    assert texts(view) == [
        "Welcome to PyCon US 2026",
        "Long Beach, CA · May 13–19",
        *(phrase for _, phrase in ROWS),  # no reminders in a test run
        FOOTNOTE,
        "Get started",
    ]
    headings = [
        (node.heading_level, texts(node))
        for node in descendants(view)
        if isinstance(node, ft.Semantics) and node.header
    ]
    assert headings == [(1, ["Welcome to PyCon US 2026"])]  # D-211


def test_the_footnote_says_it_is_not_an_official_psf_app(
    render: Callable[[], ft.View],
) -> None:
    """The footnote names Python, Flet and the community, and disclaims the PSF (D-36).

    A screen reader says its two parts as two sentences, and the place's range as
    "to", rather than reading out the dot and the dash.
    """
    view = render()
    lines = {str(n.value): n for n in descendants(view) if isinstance(n, ft.Text)}
    footnote = lines[FOOTNOTE]
    assert FOOTNOTE == (
        "Built with Python and Flet by the community · Not an official PSF app"
    )
    assert footnote.semantics_label == (
        "Built with Python and Flet by the community. Not an official PSF app"
    )
    assert lines["Long Beach, CA · May 13–19"].semantics_label == (
        "Long Beach, CA. May 13 to 19"
    )


def test_each_row_is_one_phrase_beside_a_decorative_icon(
    render: Callable[[], ft.View],
) -> None:
    """A row's icon says nothing, so the row reads as its phrase alone (D-33)."""
    rows = [n for n in descendants(render()) if isinstance(n, ft.Row)]
    assert len(rows) == len(ROWS)
    for row, (icon, phrase) in zip(rows, ROWS, strict=True):
        mark, words = row.controls
        assert isinstance(mark, ft.Icon) and mark.icon == icon
        assert mark.semantics_label is None
        assert isinstance(words, ft.Text) and words.value == phrase
        assert words.expand  # it wraps at large text instead of overflowing


def test_every_text_and_the_button_stand_out_from_the_purple_at_7_to_1(
    render: Callable[[], ft.View],
) -> None:
    """White text, icons and button on the purple, and purple ink on the button, 11:1."""
    view = render()
    colours = {n.color for n in descendants(view) if isinstance(n, (ft.Text, ft.Icon))}
    colours.discard(None)  # the label inherits the button style's colour
    assert colours == {INK}
    style = start_button(view).style
    assert style is not None and (style.bgcolor, style.color) == (INK, BOOT_COLOR)
    assert contrast_ratio(INK, BOOT_COLOR) >= 7


def test_get_started_is_a_named_button_at_least_48_dp_tall(
    render: Callable[[], ft.View],
) -> None:
    """The button reads "Get started", and its padding makes it 48 dp at 100 % text.

    Its height is not fixed, so the label grows with the text and never clips.
    """
    button = start_button(render())
    assert isinstance(button.content, ft.Text) and button.content.value == "Get started"
    assert button.height is None
    style = button.style
    assert style is not None and isinstance(style.padding, ft.Padding)
    line_height = 20  # Material's label-large line, which a button's label uses
    assert line_height + style.padding.top + style.padding.bottom >= 48


async def test_get_started_saves_that_welcome_was_seen_and_goes_to_now(
    render: Callable[[], ft.View], prefs: Prefs, shared: MemoryPrefs, page: FakePage
) -> None:
    """Get started stores ``pycon.onboarded`` and replaces the route with Now."""
    await tap(start_button(render()))
    assert shared.values == {"pycon.onboarded": True}
    assert prefs.onboarded is True
    assert page.navigated == ["/now"]


async def test_a_failed_save_still_goes_to_now_and_is_logged(
    render: Callable[[], ft.View],
    prefs: Prefs,
    shared: MemoryPrefs,
    page: FakePage,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A save that fails goes to Now all the same, logged; Welcome shows again next time.

    The session keeps the value, as every failed save does (D-120), so the start route
    does not send this session back to Welcome.
    """
    shared.fail_writes = True
    with caplog.at_level(logging.WARNING):
        await tap(start_button(render()))
    assert shared.values == {}
    assert prefs.onboarded is True
    assert page.navigated == ["/now"]
    assert "pycon.onboarded" in caplog.text  # Storage names the key (D-120)
    assert "Welcome is done for this session only" in caplog.text
