"""Tests for the boundaries high contrast draws with lines where fills drew them (#457).

D-306; THEME-06; ux.md §3.2, §3.3, §9. HC has one surface, so each part that a tint
set apart from the page (the bars, the selected pill, chips, fields, bands, notes,
frames and circles) takes a line in ``outline`` there, and keeps its fill elsewhere.
The status strip's lines are tested with the strip, the skeleton's with the skeleton.
"""

from collections.abc import Callable
from typing import cast

import flet as ft
import pytest

from pycon_us import theme
from pycon_us.config import load_year
from pycon_us.layout import Layout
from pycon_us.screens.now_header import GOLD, HeaderCopy, Season, StatusHeader
from pycon_us.screens.schedule_sheet import filter_sheet
from pycon_us.screens.tracks import sprints_row, track_circle
from pycon_us.services import Services
from pycon_us.theme import (
    DARK_TOKENS,
    HC_DARK_TOKENS,
    HC_LIGHT_TOKENS,
    LIGHT_TOKENS,
    Tokens,
)
from pycon_us.theme_hc import HC_INDICATOR_BORDER, hc_border
from pycon_us.ui import scaffold
from pycon_us.ui.fields import SearchField
from pycon_us.ui.fold import FoldTile
from pycon_us.ui.scaffold import AppScaffold
from tests import chrome
from tests.chrome import view_at
from tests.fakes import FakePage, Hooks
from tests.sessions import find, rendering, settle
from tests.test_theme import contrast_ratio
from tests.trees import descendants

year, svc, page, conference, hooks = (
    chrome.year,
    chrome.svc,
    chrome.page,
    chrome.conference,
    chrome.hooks,
)

INFO = load_year(2026).conference

NON_TEXT = 3.0
"""WCAG 1.4.11's minimum for a state indicator or a boundary."""

HC_TOKENS = [HC_LIGHT_TOKENS, HC_DARK_TOKENS]
STANDARD_TOKENS = [LIGHT_TOKENS, DARK_TOKENS]
SCHEMES = ["light", "dark"]


def hc_theme(dark: bool) -> ft.Theme:
    """Return the high-contrast light or dark theme."""
    return theme.build_theme(dark=dark, high_contrast=True)


def surface_of(built: ft.Theme) -> str:
    """Return a theme's surface colour, as a hex."""
    assert built.color_scheme is not None
    return str(built.color_scheme.surface)


def never(*_: object) -> None:
    """A handler that fails the test if anything calls it."""
    raise AssertionError("not called in this test")


# ------------------------------------------------------------------ the theme


@pytest.mark.parametrize("dark", [False, True], ids=SCHEMES)
@pytest.mark.parametrize("bar", ["navigation_bar_theme", "navigation_rail_theme"])
def test_hc_rings_the_selected_pill_at_3_to_1_on_every_tab(
    dark: bool, bar: str
) -> None:
    """The bar's and the rail's selected pill has a 2 dp ring in ``outline``.

    A non-text cue at 3:1 or more on the surface for every destination, More's too,
    whose icon has no filled form; the colour is a hex, as a component theme resolves
    a role against the seeded scheme (U64).
    """
    built = hc_theme(dark)
    shape = getattr(built, bar).indicator_shape
    assert isinstance(shape, ft.StadiumBorder)
    assert shape.side is not None
    assert shape.side.width == HC_INDICATOR_BORDER == 2
    assert built.color_scheme is not None
    assert shape.side.color == built.color_scheme.outline
    assert contrast_ratio(str(shape.side.color), surface_of(built)) >= NON_TEXT


@pytest.mark.parametrize("dark", [False, True], ids=SCHEMES)
def test_the_pill_alone_is_below_3_to_1_in_hc(dark: bool) -> None:
    """Why the ring: the pill's fill is 1.18:1 or 1.25:1 on the surface (D-265)."""
    built = hc_theme(dark)
    assert built.color_scheme is not None
    pill = str(built.color_scheme.secondary_container)
    assert contrast_ratio(pill, surface_of(built)) < NON_TEXT


@pytest.mark.parametrize("dark", [False, True], ids=SCHEMES)
def test_hc_outlines_every_chip_selected_or_not(dark: bool) -> None:
    """Every chip has a 1 dp ``outline`` border in HC; the selected fill is 1.2:1."""
    built = hc_theme(dark)
    assert built.chip_theme is not None and built.chip_theme.border_side is not None
    side = built.chip_theme.border_side
    assert built.color_scheme is not None
    assert (side.width, side.color) == (1, built.color_scheme.outline)


@pytest.mark.parametrize("dark", [False, True], ids=SCHEMES)
def test_standard_themes_keep_material_s_pill_and_chips(dark: bool) -> None:
    """Outside HC no component theme rings the pill or outlines the chips."""
    built = theme.build_theme(dark=dark, high_contrast=False)
    assert built.navigation_bar_theme is None
    assert built.navigation_rail_theme is None
    assert built.chip_theme is None


# ------------------------------------------------------------------ the app bar


@pytest.mark.parametrize("tokens", HC_TOKENS, ids=SCHEMES)
@pytest.mark.parametrize("location", ["/now", "/schedule/session/42"])
def test_in_hc_a_line_separates_the_app_bar_from_the_page(
    hooks: Hooks, page: FakePage, tokens: Tokens, location: str
) -> None:
    """In HC a View's body opens with a 1 dp ``outline`` line, right under its bar.

    The bar keeps the page's colour when a list scrolls under it there (D-306).
    """
    hooks.tokens = tokens
    line = view_at(hooks, page, location).controls[0]
    assert isinstance(line, ft.Divider) and line.visible is True
    assert (line.height, line.thickness, line.color) == (1, 1, ft.Colors.OUTLINE)


@pytest.mark.parametrize("tokens", STANDARD_TOKENS, ids=SCHEMES)
def test_outside_hc_nothing_separates_the_app_bar(
    hooks: Hooks, page: FakePage, tokens: Tokens
) -> None:
    """Outside HC the View opens with its body: the bar's scrolled-under tint is its edge."""
    hooks.tokens = tokens
    view = view_at(hooks, page, "/schedule/session/42")
    line = view.controls[0]
    assert isinstance(line, ft.Divider) and line.visible is False


@pytest.mark.parametrize("location", ["/schedule", "/schedule/session/42"])
async def test_a_contrast_change_keeps_the_body_mounted(
    monkeypatch: pytest.MonkeyPatch, svc: Services, location: str
) -> None:
    """Turning HC on and off keeps the body's controls and components (D-18, D-306).

    The lines keep their slots, hidden outside HC: one added before the body would
    shift it, and Flet would replace it, a list's scroll with it, on resume.
    """
    mounts: list[str] = []
    set_tokens: list[Callable[[Tokens], None]] = []
    shown: dict[str, Tokens] = {}

    @ft.component
    def Body() -> ft.Control:
        """A list that records each mount of its component."""

        async def mounted() -> None:
            mounts.append("mounted")

        ft.use_effect(mounted, [])
        return ft.ListView([ft.Text("row")], expand=True)

    @ft.component
    def Passthrough(body: ft.Control) -> ft.Control:
        """``Shown`` without its content line."""
        return body

    @ft.component
    def Root() -> ft.View:
        """A screen whose tokens the test switches."""
        tokens, set_ = ft.use_state(LIGHT_TOKENS)
        set_tokens.append(set_)
        shown["tokens"] = tokens
        return AppScaffold(title="Schedule", body=Body())

    monkeypatch.setattr(ft, "use_view_path", lambda: location)
    monkeypatch.setattr(scaffold, "use_services", lambda: svc)
    monkeypatch.setattr(scaffold, "use_layout", Layout)
    monkeypatch.setattr(scaffold, "use_tokens", lambda: shown["tokens"])
    monkeypatch.setattr(scaffold, "Shown", Passthrough)
    monkeypatch.setattr(scaffold, "GutterProbe", chrome.Probe)
    monkeypatch.setattr(scaffold, "use_modals_close_on_route_change", lambda: None)
    async with rendering(Root, views=True) as session:
        (first,) = find(session, ft.ListView)
        for tokens in [HC_LIGHT_TOKENS, LIGHT_TOKENS]:
            set_tokens[-1](tokens)
            await settle()
            lines = find(session, ft.Divider, lambda d: d.visible is not False)
            on_root = location == "/schedule"  # its line above the bar too
            assert len(lines) == ((2 if on_root else 1) if tokens.high_contrast else 0)
            assert [c._i for c in find(session, ft.ListView)] == [first._i]
    assert mounts == ["mounted"]


# ------------------------------------------------------------------ the parts


def field_border(high_contrast: bool) -> ft.BorderSide:
    """Return the side of a ``SearchField``'s pill, with or without HC."""
    holder = SearchField(
        value="",
        on_change=never,
        on_clear=never,
        ref=ft.Ref[ft.TextField](),
        hint="Filter",
        label="Filter",
        clear_tooltip="Clear",
        identifier="test.field",
        high_contrast=high_contrast,
    )
    (field,) = [n for n in descendants(holder) if isinstance(n, ft.TextField)]
    borders = cast(dict[ft.ControlState, ft.OutlineInputBorder], field.border)
    side, *others = [border.side for border in borders.values()]
    assert side is not None
    assert all(other == side for other in others)  # focused or not
    return side


def test_in_hc_a_search_field_is_ringed_in_outline() -> None:
    """In HC the field's pill has a 1 dp ``outline`` ring, focused or not."""
    side = field_border(True)
    assert (side.width, side.color) == (1, ft.Colors.OUTLINE)


def test_outside_hc_a_search_field_has_no_line() -> None:
    """Outside HC the pill is its tonal fill, without a line, like M3's search bar."""
    assert field_border(False).width == 0


def test_hc_border_is_a_1_dp_outline_only_in_hc() -> None:
    """Notes, frames and notice tiles take ``hc_border()``: 1 dp in HC, else none."""
    assert hc_border(True) == ft.Border.all(1, ft.Colors.OUTLINE)
    assert hc_border(False) is None


@pytest.mark.parametrize("tokens", HC_TOKENS, ids=SCHEMES)
def test_in_hc_a_track_s_circle_is_a_ring_as_its_badge_is(tokens: Tokens) -> None:
    """A track's circle takes its outlined badge's 1.5 dp ink ring, so it keeps its shape."""
    track = INFO.track("Talk")
    circle = track_circle(track, tokens.track_badge(track.key))
    assert isinstance(circle, ft.Container)
    assert circle.bgcolor is None
    ink = tokens.track_badge(track.key).text
    assert circle.border == ft.Border.all(1.5, ink)


@pytest.mark.parametrize("tokens", STANDARD_TOKENS, ids=SCHEMES)
def test_outside_hc_a_track_s_circle_is_its_badge_s_fill(tokens: Tokens) -> None:
    """Outside HC the circle is the badge's tonal fill, without a ring."""
    track = INFO.track("Talk")
    circle = track_circle(track, tokens.track_badge(track.key))
    assert isinstance(circle, ft.Container)
    assert circle.bgcolor == tokens.track_badge(track.key).fill
    assert circle.border is None


@pytest.mark.parametrize(
    ("tokens", "ringed"),
    [(HC_LIGHT_TOKENS, True), (HC_DARK_TOKENS, True), (LIGHT_TOKENS, False)],
    ids=["hc-light", "hc-dark", "light"],
)
def test_the_sprints_circle_is_ringed_only_in_hc(
    page: FakePage, tokens: Tokens, ringed: bool
) -> None:
    """The Sprints row's neutral circle is a ring in HC, a tonal fill elsewhere."""
    row = sprints_row(INFO, 3, tokens)
    circles = [
        n
        for n in descendants(row)
        if isinstance(n, ft.Container) and n.shape == ft.BoxShape.CIRCLE
    ]
    (circle,) = circles
    assert (circle.border is not None) == ringed
    assert (circle.bgcolor is None) == ringed


@pytest.mark.parametrize(
    ("dark", "high_contrast", "icon"),
    [
        (False, False, GOLD),
        (True, False, GOLD),
        (False, True, ft.Colors.ON_PRIMARY),
        (True, True, ft.Colors.ON_PRIMARY_CONTAINER),
    ],
)
def test_now_s_header_icon_takes_the_ink_in_hc(
    dark: bool, high_contrast: bool, icon: str
) -> None:
    """The header's icon is gold on the indigo, the header's ink in HC (D-306).

    The gold was 1.03:1 on HC dark's yellow ``primary``.
    """
    copy = HeaderCopy(Season.CONFERENCE, "Day 3 of 5 · Friday", "Long Beach")
    header = StatusHeader("PyCon US 2026", copy, dark=dark, high_contrast=high_contrast)
    (found,) = [n for n in descendants(header) if isinstance(n, ft.Icon)]
    assert found.color == icon


def test_gold_all_but_disappears_on_hc_dark_s_yellow() -> None:
    """Why the HC rule: gold on HC dark's ``primary`` is under 3:1."""
    assert contrast_ratio(GOLD, "#FFD60A") < NON_TEXT


@pytest.mark.parametrize("high_contrast", [False, True], ids=["standard", "hc"])
def test_the_filter_sheet_is_outlined_only_in_hc(high_contrast: bool) -> None:
    """In HC the sheet has a 1 dp ``outline`` edge with M3's 28 dp top corners."""
    sheet = filter_sheet(
        INFO,
        (),
        set(),
        1,
        changed=False,
        on_toggle=never,  # type: ignore[arg-type]
        on_reset=never,
        on_close=never,
        on_tracks_page=never,
        reduce_motion=True,
        high_contrast=high_contrast,
    )
    if not high_contrast:
        assert sheet.shape is None
        return
    shape = sheet.shape
    assert isinstance(shape, ft.RoundedRectangleBorder)
    assert shape.radius == ft.BorderRadius.only(top_left=28, top_right=28)
    assert shape.side == ft.BorderSide(1, ft.Colors.OUTLINE)


@pytest.mark.parametrize("lines", [False, True])
def test_a_fold_keeps_material_s_lines_only_when_asked(lines: bool) -> None:
    """With ``lines`` an open fold draws a line above and below it, in ``outline``."""
    line = ft.BorderSide(1, ft.Colors.OUTLINE)
    for expanded in (False, True):
        fold = FoldTile(
            ft.Text("Earlier days"),
            [],
            expanded=expanded,
            on_change=never,
            style=ft.Animation(0),
            identifier="my_schedule.earlier_days",
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            lines=lines,
        )
        drawn = ft.Border(top=line, bottom=line) if expanded and lines else None
        assert fold.border == drawn
