"""Tests for the session rows: ``SessionRow``, ``NoticeRow``, ``TimeGutter`` (D-184).

Rows run in a real Flet session (``Rendered``): a list owner like the screens' renders
memoised rows under the store providers, a star tap is a dispatched click, and Flet's
own scheduler re-renders what changed, so a test sees what a device would get. How tall
a row is, how it wraps at 200 % and what TalkBack reads are checked on devices (#81's
PR); here, the semantics a screen reader is given.

The harness reaches into Flet internals, as Flet's own component tests do: it sets
``flet.controls.context._context_page``, finds controls in ``Session.index``, reads
SnackBars from ``page._dialogs`` and clicks with ``Session.dispatch_event(control._i,
...)``. A Flet pin bump (D-81) that renames one of them breaks this module's fixture,
not the rows: look there first.
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest
from flet.controls.context import _context_page
from flet.messaging.connection import Connection
from flet.messaging.session import Session
from flet.pubsub.pubsub_hub import PubSubHub

from pycon_us.config import load_year
from pycon_us.core.row_views import SessionView, session_view
from pycon_us.favorites import Favorites, FavoritesCtx, use_favorites
from pycon_us.prefs import Prefs, PrefsCtx
from pycon_us.services import Services, ServicesCtx, use_services
from pycon_us.services.storage import Storage
from pycon_us.state import Conference, ConferenceCtx, ViewMemory, use_conference
from pycon_us.theme import DARK_TOKENS, LIGHT_TOKENS
from pycon_us.ui import session_rows as rows
from pycon_us.ui.badges import (
    ADD_LABEL,
    FAVORITE_LABEL,
    NOT_SAVED,
    REMOVE_LABEL,
    REMOVED,
    UNDO,
    use_favorite_toggle,
)
from pycon_us.ui.session_rows import (
    NoticeRow,
    SessionRow,
    TimeGutter,
    elapsed_phrase,
    is_notice,
    notice_phrase,
    semantics_key,
    spoken_phrase,
    use_session_views,
)
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)
from tests.feeds import processed
from tests.test_theme import NEUTRAL_RAMP, contrast_ratio

YEAR = load_year(2026)
ZONE = YEAR.conference.zone

TALK = "142"
"""A talk with one speaker: "Python for Humans - …", 10:30-11:00 AM, Grand Ballroom A."""

CHARLA = "76"
"""A charla: badges "Charla" and "En Español"."""

TUTORIAL = "19"
"""A tutorial that needs registration."""

NOTICE = "196"
"""Registration Desk Opens, 7:30 AM: a notice with a description."""

COFFEE = "break-Expo Hall AB-2026-05-15T08:00:00-07:00"
"""A collapsed break with nothing to read."""

LIST = (TALK, CHARLA, TUTORIAL, NOTICE, COFFEE)


def view_of(session_id: str, *, use_24h: bool = False) -> SessionView:
    return session_view(processed(2026).sessions[session_id], ZONE, use_24h=use_24h)


# ------------------------------------------------------------------ a real session


@ft.component
def Owner(session_ids: tuple[str, ...]) -> ft.Control:
    """A list owner as the screens write one: it subscribes, its rows do not."""
    conference = use_conference()
    favorites = use_favorites()
    on_toggle = use_favorite_toggle(favorites)
    views = use_session_views(conference, session_ids, use_24h=False)
    info = use_services().year.conference
    return ft.Column(
        [
            NoticeRow(view, screen="test")
            if is_notice(view.session, info)
            else SessionRow(
                view,
                view.session.id in favorites.ids,
                on_toggle,
                LIGHT_TOKENS,
                screen="test",
            )
            for view in views
        ]
    )


@dataclass
class Rendered:
    """A Flet session showing ``Owner``, and what its rows did."""

    session: Session
    favorites: Favorites
    prefs: Prefs
    prefs_service: MemoryPrefs
    haptics: MemoryHaptics
    renders: list[str] = field(default_factory=list)
    """The session ids whose row bodies ran, in order (S2's ``ROW_RENDERS``)."""

    def node(self, identifier: str) -> ft.Semantics:
        """The mounted ``Semantics`` with this identifier: one, and current."""
        found = [
            c
            for c in self.session.index.values()
            if isinstance(c, ft.Semantics) and c.identifier == identifier
        ]
        assert len(found) == 1, identifier
        return found[0]

    def star(self, session_id: str) -> ft.IconButton:
        button = self.node(f"test.favorite.{session_id}").content
        assert isinstance(button, ft.IconButton)
        return button

    def filled(self, session_id: str) -> bool:
        """Whether the session's star is drawn filled."""
        return self.star(session_id).icon == ft.Icons.STAR

    def notice(self, session_id: str) -> ft.Semantics:
        return self.node(f"test.notice.{semantics_key(session_id)}")

    async def settle(self) -> None:
        """Let handlers, store writes and Flet's re-render run to the end."""
        for _ in range(20):
            await asyncio.sleep(0)

    async def tap_star(self, session_id: str) -> None:
        await self.session.dispatch_event(self.star(session_id)._i, "click", None)
        await self.settle()

    @property
    def snack_bars(self) -> list[ft.SnackBar]:
        return [
            d for d in self.session.page._dialogs.controls if isinstance(d, ft.SnackBar)
        ]


@pytest.fixture
async def rendered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Rendered]:
    prefs_service = MemoryPrefs()
    haptics = MemoryHaptics()
    storage = Storage(prefs=prefs_service, directory=tmp_path, year=2026)
    svc = Services(
        year=YEAR,
        storage=storage,
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=haptics,
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )
    conference = Conference(data=processed(2026), source="bundled", version=1)
    favorites, prefs = Favorites(), Prefs(loaded=True)
    await favorites.load(storage)
    result = Rendered(Session(_connection()), favorites, prefs, prefs_service, haptics)

    def counted(name: str) -> Callable[..., str]:
        phrase = getattr(rows, name)

        def count(*args: Any, **kwargs: Any) -> str:
            result.renders.append(cast(SessionView, args[-1]).session.id)
            return phrase(*args, **kwargs)

        return count

    # Each row body says its phrase once: counting the calls counts the bodies.
    monkeypatch.setattr(rows, "spoken_phrase", counted("spoken_phrase"))
    monkeypatch.setattr(rows, "notice_phrase", counted("notice_phrase"))

    @ft.component
    def Root() -> ft.Control:
        return ServicesCtx(
            svc,
            lambda: ConferenceCtx(
                conference,
                lambda: PrefsCtx(
                    prefs, lambda: FavoritesCtx(favorites, lambda: Owner(LIST))
                ),
            ),
        )

    page = result.session.page
    token = _context_page.set(page)  # pyright: ignore[reportArgumentType]
    try:
        page.render(Root)
        result.session.get_page_patch()
        await result.settle()
        yield result
    finally:
        result.session.close()
        await result.settle()
        _context_page.reset(token)


def _connection() -> Connection:
    """A connection to no client, as Flet's own component tests use."""
    conn = Connection()
    conn.pubsubhub = PubSubHub()
    conn.send_message = lambda message: None  # pyright: ignore[reportAttributeAccessIssue]
    return conn


# ------------------------------------------------------------------ the memoised path


async def test_each_row_renders_once_when_the_list_first_shows(
    rendered: Rendered,
) -> None:
    assert sorted(rendered.renders) == sorted(LIST)


async def test_a_star_tap_re_renders_exactly_one_row(rendered: Rendered) -> None:
    """D-153: the owner re-renders, but every other row skips its body (F34)."""
    rendered.renders.clear()
    await rendered.tap_star(CHARLA)
    assert rendered.favorites.ids == {CHARLA}
    assert rendered.renders == [CHARLA]
    assert rendered.filled(CHARLA)
    assert not rendered.filled(TALK)

    rendered.renders.clear()
    await rendered.tap_star(CHARLA)  # and back
    assert rendered.renders == [CHARLA]
    assert rendered.favorites.ids == frozenset()


async def test_the_handler_is_the_same_object_on_every_render(
    rendered: Rendered,
) -> None:
    handlers: set[int] = set()
    original = rows._SessionRow

    def spy(*args: Any, **kwargs: Any) -> ft.Control:
        handlers.add(id(args[2]))
        return original(*args, **kwargs)

    rows._SessionRow = spy  # pyright: ignore[reportAttributeAccessIssue]
    try:
        await rendered.tap_star(TALK)
        await rendered.tap_star(TUTORIAL)
    finally:
        rows._SessionRow = original  # pyright: ignore[reportAttributeAccessIssue]
    assert len(handlers) == 1  # use_callback(..., []): memoised rows stay skipped


# ------------------------------------------------------------------ the star (D-30)


async def test_adding_fills_the_star_with_a_click_and_no_snack_bar(
    rendered: Rendered,
) -> None:
    await rendered.tap_star(TALK)
    assert rendered.prefs_service.values["pycon.2026.favorites"] == [TALK]
    assert rendered.haptics.effects == ["selection_click"]
    assert rendered.snack_bars == []


async def test_removing_says_so_and_undo_saves_the_session_again(
    rendered: Rendered,
) -> None:
    await rendered.tap_star(TALK)
    await rendered.tap_star(TALK)
    (snack,) = rendered.snack_bars
    assert cast(ft.Text, snack.content).value == REMOVED
    assert snack.behavior == ft.SnackBarBehavior.FLOATING
    assert snack.persist is False  # no screen reader: it goes after 4 s
    action = cast(ft.SnackBarAction, snack.action)
    assert action.label == UNDO

    await cast(Callable[[], Any], action.on_click)()
    await rendered.settle()
    assert rendered.favorites.ids == {TALK}
    assert rendered.prefs_service.values["pycon.2026.favorites"] == [TALK]
    assert rendered.filled(TALK)
    assert len(rendered.snack_bars) == 1  # Undo itself says nothing more


async def test_with_a_screen_reader_the_undo_snack_bar_waits_to_be_used(
    rendered: Rendered,
) -> None:
    """D-184: a screen-reader user cannot reach Undo within 4 s."""
    rendered.prefs.screen_reader = True
    await rendered.tap_star(TALK)
    await rendered.tap_star(TALK)
    (snack,) = rendered.snack_bars
    assert snack.persist is True


async def test_an_add_that_was_not_saved_says_so_without_undo(
    rendered: Rendered,
) -> None:
    rendered.prefs_service.fail_writes = True
    await rendered.tap_star(TALK)
    assert rendered.filled(TALK)  # shown first, as the store does (D-172)
    (snack,) = rendered.snack_bars
    assert cast(ft.Text, snack.content).value == NOT_SAVED
    assert snack.action is None


async def test_a_removal_that_was_not_saved_says_so_once_and_keeps_undo(
    rendered: Rendered,
) -> None:
    await rendered.tap_star(TALK)
    rendered.prefs_service.fail_writes = True
    await rendered.tap_star(TALK)
    (snack,) = rendered.snack_bars  # one SnackBar for one tap (ux.md §4.4)
    assert cast(ft.Text, snack.content).value == NOT_SAVED
    assert cast(ft.SnackBarAction, snack.action).label == UNDO


async def test_a_failed_click_does_not_stop_the_star(rendered: Rendered) -> None:
    rendered.haptics.error = TimeoutError()
    await rendered.tap_star(TALK)
    assert rendered.favorites.ids == {TALK}
    assert rendered.snack_bars == []  # neither the click nor "Something went wrong"


async def test_the_star_is_one_named_toggle_for_screen_readers(
    rendered: Rendered,
) -> None:
    """S2: the IconButton alone was a nameless Button without a state in TalkBack."""
    node = rendered.node(f"test.favorite.{TALK}")
    assert (node.label, node.button, node.toggled) == (FAVORITE_LABEL, True, False)
    assert isinstance(node.parent, ft.MergeSemantics)
    button = rendered.star(TALK)
    assert (button.icon, button.icon_color) == (ft.Icons.STAR_BORDER, None)

    await rendered.tap_star(TALK)
    node = rendered.node(f"test.favorite.{TALK}")
    # The same name; only the state changes: "Save to My schedule, switch, on".
    assert (node.label, node.toggled) == (FAVORITE_LABEL, True)
    button = rendered.star(TALK)
    assert (button.icon, button.icon_color) == (ft.Icons.STAR, LIGHT_TOKENS.favorite)


async def test_the_star_s_state_is_said_once(rendered: Rendered) -> None:
    """VoiceOver read the tooltip after the label, and a "selected" after the "on"."""
    await rendered.tap_star(TALK)
    button = rendered.star(TALK)
    assert button.selected is None  # IconButton.selected adds Semantics(selected:)
    tooltip = button.tooltip
    assert isinstance(tooltip, ft.Tooltip) and tooltip.exclude_from_semantics


async def test_the_star_s_tooltip_says_what_a_tap_does(rendered: Rendered) -> None:
    """D-27, D-30: "Add to My schedule", then "Remove from My schedule"."""
    assert cast(ft.Tooltip, rendered.star(TALK).tooltip).message == ADD_LABEL
    await rendered.tap_star(TALK)
    assert cast(ft.Tooltip, rendered.star(TALK).tooltip).message == REMOVE_LABEL


# ------------------------------------------------------------------ SessionRow (SCHED-03)


async def test_a_row_s_text_is_one_node_read_as_one_phrase(
    rendered: Rendered,
) -> None:
    node = rendered.node(f"test.session.{TALK}")
    assert node.label == (
        "Talk. Python for Humans - Designing Python Code Like a User Interface. "
        "10:30 to 11:00 AM, Grand Ballroom A. Justin Lee."
    )
    assert node.exclude_semantics  # the texts are not read again after the phrase
    assert node.button  # it opens the session: "…, button"
    tappable = node.parent
    assert isinstance(tappable, ft.Container) and tappable.on_click is not None
    assert isinstance(tappable.parent, ft.MergeSemantics)  # phrase and tap: one node


async def test_a_row_shows_badges_title_meta_and_speakers(
    rendered: Rendered,
) -> None:
    column = rendered.node(f"test.session.{CHARLA}").content
    assert isinstance(column, ft.Column)
    badges, title, meta, speakers = column.controls
    assert isinstance(badges, ft.Row) and badges.wrap
    assert [
        cast(ft.Text, cast(ft.Container, b).content).value for b in badges.controls
    ] == [
        "Charla",
        "En Español",
    ]
    assert isinstance(title, ft.Text)
    assert (title.theme_style, title.max_lines) == (ft.TextThemeStyle.TITLE_MEDIUM, 3)
    assert isinstance(meta, ft.Row)
    assert [cast(ft.Text, t).value for t in meta.controls] == [
        "10:30–11:00\u00a0AM\u00a0·",
        "Room 104C",
    ]
    assert cast(ft.Text, speakers).value == "Veronica Rodriguez Viveros"


async def test_a_place_that_does_not_fit_moves_down_whole(rendered: Rendered) -> None:
    """At 200 %, "AM · Room" / "104C" broke the place and left the dot dangling."""
    column = rendered.node(f"test.session.{CHARLA}").content
    meta = cast(ft.Column, column).controls[2]
    assert isinstance(meta, ft.Row) and meta.wrap  # time and place wrap as units
    time, place = (cast(ft.Text, t).value or "" for t in meta.controls)
    assert " " not in time  # "AM" and the "·" stay on the time's line
    assert time.endswith("·") and not place.startswith("·")


async def test_no_row_part_has_a_fixed_height(rendered: Rendered) -> None:
    """Rows reflow at 200 % text: only the layout sizes them."""

    def heights(control: ft.Control) -> Iterator[object]:
        yield getattr(control, "height", None)
        for child in _children(control):
            yield from heights(child)

    for session_id in (TALK, CHARLA):
        row = rendered.node(f"test.session.{session_id}")
        assert set(heights(row)) == {None}


async def test_a_tap_on_a_row_pushes_its_session_on_this_view(
    rendered: Rendered, monkeypatch: pytest.MonkeyPatch
) -> None:
    pushed: list[str] = []
    monkeypatch.setattr(rendered.session.page, "navigate", pushed.append)
    tappable = rendered.node(f"test.session.{TALK}").parent
    assert isinstance(tappable, ft.Container)
    await rendered.session.dispatch_event(tappable._i, "click", None)
    await rendered.settle()
    assert pushed == [f"/session/{TALK}"]  # drill_href on this View's path ("")


def test_the_phrase_names_every_badge_and_skips_what_is_missing() -> None:
    view = view_of(TUTORIAL)
    phrase = spoken_phrase(["Tutorial", "Registration required"], view)
    assert phrase == (
        "Tutorial, Registration required. All about decorators. "
        "9:00 AM to 12:30 PM, Room 101B. Reuven M. Lerner."
    )
    no_speakers = spoken_phrase(["Break"], view_of(COFFEE))
    assert no_speakers == "Break. Coffee. 8:00 to 9:00 AM, Expo Hall AB."


def test_a_row_that_is_on_says_how_much_has_passed_last() -> None:
    """Now's elapsed bar is said in the row's phrase, as a sentence of its own (#95)."""
    assert elapsed_phrase(60) == "60 percent elapsed."
    assert elapsed_phrase(0) == "0 percent elapsed."


def _over(color: str, alpha: float, background: str) -> str:
    """``color`` at ``alpha`` painted over ``background``, as #RRGGBB."""
    mix = (
        round(
            alpha * int(color[i : i + 2], 16)
            + (1 - alpha) * int(background[i : i + 2], 16)
        )
        for i in (1, 3, 5)
    )
    return "#" + "".join(f"{channel:02X}" for channel in mix)


@pytest.mark.parametrize("dark", [False, True])
def test_the_elapsed_bar_shows_its_fill_and_its_end_on_every_surface(
    dark: bool,
) -> None:
    """WCAG 1.4.11: the fill reads 3:1 on its track, and the stop dot marks the end.

    The track itself is only a hint (about 1.4:1), on the list's ``surface`` and on
    the next-session card's ``surface_container_highest`` alike; M3's stop dot is what
    marks 100 % (#95).
    """
    live = DARK_TOKENS.live if dark else LIGHT_TOKENS.live
    padded = rows._elapsed_bar(60, live)
    assert isinstance(padded, ft.Container)
    bar = padded.content
    assert isinstance(bar, ft.ProgressBar)
    assert bar.year_2023 is False  # the gap and the stop dot
    assert bar.stop_indicator_color == ft.Colors.ON_SURFACE_VARIANT
    role, alpha = str(bar.bgcolor).split(",")
    assert role == ft.Colors.ON_SURFACE
    ramp = NEUTRAL_RAMP[dark]
    for surface in (ramp["surface"], ramp["surfaceContainerHighest"]):
        track = _over(ramp["onSurface"], float(alpha), surface)
        assert contrast_ratio(live, track) >= 3
        assert contrast_ratio(track, surface) >= 1.3  # a visible rail
        assert contrast_ratio(ramp["onSurfaceVariant"], surface) >= 3  # the dot


def test_a_title_that_ends_a_sentence_gets_no_second_full_stop() -> None:
    view = view_of(TALK)
    asked = replace(
        view, session=replace(view.session, name="Is Python fast?"), place=""
    )
    assert spoken_phrase([], asked) == "Is Python fast? 10:30 to 11:00 AM. Justin Lee."


# ------------------------------------------------------------------ NoticeRow (SCHED-04)


def test_breaks_and_announcements_are_notices_and_talks_are_not() -> None:
    sessions = processed(2026).sessions
    info = YEAR.conference
    assert is_notice(sessions[NOTICE], info)  # Informational
    assert is_notice(sessions[COFFEE], info)  # Break
    assert not is_notice(sessions[TALK], info)
    assert not is_notice(sessions["227"], info)  # an Event is a session


async def test_a_notice_is_its_own_node_and_has_no_star(rendered: Rendered) -> None:
    """S2: without its own merge, a notice joined the slot's heading in TalkBack."""
    node = rendered.notice(COFFEE)
    assert node.label == "Break. Coffee, 8:00 to 9:00 AM, Expo Hall AB."
    assert node.exclude_semantics
    assert isinstance(cast(ft.Control, node.parent).parent, ft.MergeSemantics)
    stars = [
        c
        for c in rendered.session.index.values()
        if isinstance(c, ft.Semantics)
        and (c.identifier or "").startswith("test.favorite.")
    ]
    assert len(stars) == 3  # the three sessions; neither notice


async def test_a_notice_opens_only_when_it_has_something_to_read(
    rendered: Rendered,
) -> None:
    with_text = rendered.notice(NOTICE)
    without = rendered.notice(COFFEE)
    assert with_text.button and not without.button
    opens, does_not = with_text.parent, without.parent
    assert isinstance(opens, ft.Container) and opens.on_click is not None
    assert isinstance(does_not, ft.Container) and does_not.on_click is None
    assert not does_not.ink


async def test_a_notice_s_title_starts_on_the_gutter_s_line(
    rendered: Rendered,
) -> None:
    """The gutter's time and a SessionRow's text start 12 dp down; so does a notice's."""
    tile = rendered.notice(COFFEE).parent
    assert isinstance(tile, ft.Container)
    margin, padding = cast(ft.Margin, tile.margin), cast(ft.Padding, tile.padding)
    assert margin.top + padding.top == 12


def test_a_semantics_key_is_safe_in_a_selector() -> None:
    """Decisions §M: a break's id has spaces and colons; its key has neither."""
    assert semantics_key(COFFEE) == "break-expo-hall-ab-2026-05-15t08-00-00-07-00"
    assert semantics_key("poster-detail-60") == "poster-detail-60"
    assert semantics_key(TALK) == TALK


def test_a_notice_reads_as_its_kind_name_and_time() -> None:
    """ux.md §3.9: "Notice. Registration opens, 7:00 AM"."""
    phrase = notice_phrase("Notice", view_of(NOTICE))
    assert phrase == "Notice. Registration Desk Opens, 7:30 AM."


# ------------------------------------------------------------------ TimeGutter (D-158)


def test_the_gutter_is_a_heading_read_once() -> None:
    gutter = TimeGutter("9:25 AM")
    assert isinstance(gutter, ft.Semantics)
    assert (gutter.header, gutter.label, gutter.exclude_semantics) == (
        True,
        "9:25 AM",
        True,  # else "9:25 AM, 9:25, AM"
    )


def gutter_columns(gutter: ft.Control) -> list[ft.Column]:
    container = cast(ft.Semantics, gutter).content
    assert isinstance(container, ft.Container)
    assert container.width is None  # no fixed width: it grows with the text
    stack = container.content
    assert isinstance(stack, ft.Stack)
    return [cast(ft.Column, c) for c in stack.controls]


def texts(column: ft.Column) -> list[str | None]:
    return [cast(ft.Text, t).value for t in column.controls]


def test_an_invisible_widest_time_sets_the_gutter_s_width() -> None:
    widest, shown = gutter_columns(TimeGutter("7:30 PM"))
    assert (texts(widest), widest.opacity) == (["10:00", "AM"], 0)
    assert texts(shown) == ["7:30", "PM"]


def test_a_24_hour_gutter_has_one_line() -> None:
    widest, shown = gutter_columns(TimeGutter("19:30"))
    assert texts(widest) == ["00:00"]
    assert texts(shown) == ["19:30"]


def _children(control: ft.Control) -> Sequence[ft.Control]:
    """A control's direct children: its ``content`` and its ``controls``."""
    found: list[ft.Control] = []
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        found.append(content)
    found.extend(
        c for c in getattr(control, "controls", None) or [] if isinstance(c, ft.Control)
    )
    return found
