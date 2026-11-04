"""Expo hall (Map › Expo, `…/plan/expo`): the plan, a hit area per booth (EXPO-01, MAP-01).

`ExpoHall` is the floor viewer's zoom layer (`ui/zoom.py`) over the expo plan, with
a booth layer as S7 chose (D-312): one positioned `Container` per booth of
`map.toml`, faintly outlined at every zoom, in `Semantics(button=True)` named
"Booth 613, Bloomberg", "Booth 726, 4 exhibitors" or "Booth 407, Python Software
Foundation" (D-254), in number order. No double-tap detector, which would delay every
booth's tap; the zoom buttons are the single-pointer way to zoom (WCAG 2.5.1). The plan
sits on `surface`, the scaffold's, where Ionic letterboxed it in black (ux.md §6.2).

A tap selects its booth without zooming: a see-through amber fill and a dark outline,
both theme tokens that high contrast changes (`Tokens.booth_fill`, `booth_outline`;
3 dp there), which pulse twice (D-34), never under reduced motion (D-173). Without
the feed the booths are there, named by number. `ViewMemory.expo_booth` keeps the
selection for the Expo pane and `…/plan/expo` alike, and the Expo pane keeps its zoom
in `ViewMemory.map_zooms`, put back once it is laid out (D-312, D-18).

The booth layer and each booth are memoised components given values only (D-153,
F150): the selection, the pulse and the zoom live in `ExpoHall`, above them, so a
change of selection re-renders two booths, a pulse one, and a zoom none.

The selected booth's card (`screens/booth_card.py`, #403) sits at the bottom of the
`Stack` with the zoom buttons above it, so both stay in reach; its Close clears the
selection. A booth picked from the List or a `?booth=` link (`reveal`) is brought
into view above its card once that is measured (`screens/expo_camera.py`, D-377).
"""

import asyncio
from collections.abc import Callable, Sequence
from typing import cast

import flet as ft

from pycon_us.core.expo import ExpoBooth, expo_booths
from pycon_us.core.models import ConferenceData
from pycon_us.core.slugs import room_sort_key
from pycon_us.prefs import use_prefs
from pycon_us.screens.booth_card import BoothCard, hiring_line
from pycon_us.screens.expo_camera import use_camera
from pycon_us.screens.expo_layout import card_layout, covered, over_plan
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import Tokens, use_tokens
from pycon_us.ui.zoom import use_zoom, zoom_buttons, zoom_layer
from pycon_us.ui.zoom_geometry import Size, Transform
from pycon_us.year_map import EXPO_PLAN, Booth, Plan

SCREEN = "expo"
"""The screen's name in its semantics identifiers: `expo.booth.613` (decisions §M)."""

FILL_OPACITY = 0.55
"""How much of the amber covers a selected booth: its printed name still shows."""

FLASH_OPACITY = 0.9
"""The fill at the top of a pulse."""

OUTLINE_DP = 2
"""A selected booth's outline (ux.md §6.2)."""

HC_OUTLINE_DP = 3
"""A selected booth's outline in high contrast, where lines carry the structure."""

FAINT_DP = 1
"""Every other booth's outline: in sight at every zoom, under the printed booth."""

FAINT_OPACITY = 0.7
"""How much of the amber the faint outline takes."""

PULSES = 2
"""How often a booth pulses when it is selected: at most twice (D-34)."""

PULSE_MS = 300
"""Each half of a pulse, up or back (ux.md §3.8's range)."""

type OnSelect = Callable[[str], None]
"""Selects the booth of a number: `ExpoHall`'s one handler for every booth."""


def booth_phrase(item: ExpoBooth) -> str:
    """Return what a screen reader says of a booth: its number and who is there (D-254).

    Args:
        item: The booth and its exhibitors.

    Returns:
        "Booth 613, Bloomberg"; "Booth 726, 4 exhibitors" for a shared booth; "Booth
        407, Python Software Foundation", its label, for a booth without one; "Booth
        613" before the feed is there.
    """
    name = f"Booth {item.booth.number}"
    if len(item.sponsors) == 1:
        return f"{name}, {item.sponsors[0].name}"
    if item.sponsors:
        return f"{name}, {len(item.sponsors)} exhibitors"
    return f"{name}, {item.booth.label}" if item.booth.label else name


def booth_box(booth: Booth, shown: Size) -> tuple[float, float, float, float]:
    """Return a booth's `left`, `top`, `width` and `height` on the fitted plan.

    Args:
        booth: The booth, its rectangle in ratios of the plan.
        shown: The plan's fitted size (`ui.zoom_geometry.fitted()`).
    """
    width, height = shown
    return booth.x * width, booth.y * height, booth.w * width, booth.h * height


def placed_booths(
    data: ConferenceData | None, booths: Sequence[Booth]
) -> tuple[ExpoBooth, ...]:
    """Return the booths with their exhibitors, in number order; without a feed, none.

    Args:
        data: The processed feed, or None before the first fetch.
        booths: The year's booths (`MapData.booths`).
    """
    if data is not None:
        return expo_booths(data, booths).booths
    ordered = sorted(booths, key=lambda booth: room_sort_key(booth.number))
    return tuple(ExpoBooth(booth, ()) for booth in ordered)


def booth_spot(
    item: ExpoBooth,
    shown: Size,
    tokens: Tokens,
    on_select: OnSelect,
    *,
    selected: bool,
    flash: bool,
    pulse_ms: int,
) -> ft.Control:
    """Return one booth: a memoised component keyed by its number (D-153).

    Args:
        item: The booth and its exhibitors.
        shown: The plan's fitted size.
        tokens: The scheme's tokens: a memoised component reads no context (F150).
        on_select: `ExpoHall`'s handler, the same function on every render.
        selected: Whether it is the selected booth.
        flash: Whether its fill is at the top of a pulse.
        pulse_ms: How long its fill takes to change (`prefs.motion_ms()`).
    """
    # ft.component's typing (its ParamSpec) leaves out the key= its wrapper takes.
    return _BoothSpot(
        item,
        shown,
        tokens,
        on_select,
        selected=selected,
        flash=flash,
        pulse_ms=pulse_ms,
        key=item.booth.number,  # pyright: ignore[reportCallIssue]
    )


@ft.memo
@ft.component
def _BoothSpot(
    item: ExpoBooth,
    shown: Size,
    tokens: Tokens,
    on_select: OnSelect,
    *,
    selected: bool,
    flash: bool,
    pulse_ms: int,
) -> ft.Control:
    """The body of `booth_spot()`: it runs only when its props change (F34)."""
    number = item.booth.number
    left, top, width, height = booth_box(item.booth, shown)

    @report_errors
    def tap() -> None:
        on_select(number)

    if selected:
        opacity = FLASH_OPACITY if flash else FILL_OPACITY
        fill = ft.Colors.with_opacity(opacity, tokens.booth_fill)
        side = HC_OUTLINE_DP if tokens.high_contrast else OUTLINE_DP
        border = ft.Border.all(side, tokens.booth_outline)
    else:
        fill = None
        border = ft.Border.all(
            FAINT_DP, ft.Colors.with_opacity(FAINT_OPACITY, tokens.booth_fill)
        )
    return ft.Container(
        left=left,
        top=top,
        width=width,
        height=height,
        # content= by name: a positional Semantics(x) is its tooltip (F130).
        content=ft.Semantics(
            content=ft.Container(
                bgcolor=fill,
                border=border,
                animate=ft.Animation(pulse_ms, ft.AnimationCurve.EASE_OUT),
                on_click=tap,
            ),
            button=True,
            # Only the selected one says so: False would read "not selected" 60 times.
            selected=True if selected else None,
            label=booth_phrase(item),
            identifier=f"{SCREEN}.booth.{number}",
        ),
    )


@ft.memo
@ft.component
def BoothLayer(
    booths: tuple[ExpoBooth, ...],
    shown: Size,
    tokens: Tokens,
    on_select: OnSelect,
    *,
    selected: str,
    flash: bool,
    pulse_ms: int,
) -> ft.Control:
    """The booths over the plan, in number order: a memoised component of values.

    A new selection re-renders it and the two booths whose props changed; a zoom,
    which leaves its props alone, re-renders nothing here (D-153).

    Args:
        booths: The booths with their exhibitors, the same tuple for the same feed.
        shown: The plan's fitted size.
        tokens: The scheme's tokens.
        on_select: `ExpoHall`'s handler.
        selected: The selected booth's number; empty for none.
        flash: Whether the selected booth is at the top of a pulse.
        pulse_ms: How long a booth's fill takes to change.
    """
    return ft.Stack(
        [
            booth_spot(
                item,
                shown,
                tokens,
                on_select,
                selected=item.booth.number == selected,
                flash=flash and item.booth.number == selected,
                pulse_ms=pulse_ms,
            )
            for item in booths
        ],
        width=shown[0],
        height=shown[1],
    )


def expo_label(plan: Plan) -> str:
    """Return what a screen reader says of the plan itself: the booths are its nodes.

    Args:
        plan: The expo plan.
    """
    return f"{plan.title} floor plan"


@ft.component
def ExpoHall(zoom_key: str = "", reveal: str = "") -> ft.Control:
    """The expo plan with its booths: tap one to select it (EXPO-01, ux.md §6.2).

    The year must have booths, so it has the expo plan (`check_map()`).

    Args:
        zoom_key: The pane's slug, under which `ViewMemory.map_zooms` keeps its
            zoom; empty for a View that keeps it only while it is open.
        reveal: The number of a booth picked elsewhere, to bring into view when it
            is still the selected one (D-377); empty for none.
    """
    svc = use_services()
    prefs = use_prefs()
    tokens = use_tokens()
    conference = use_conference()
    memory = svc.memory
    year_map = svc.year.map
    plan = year_map.plan(EXPO_PLAN)
    assert plan is not None, "check_map(): a year with booths has the expo plan"
    data = conference.data
    booths = ft.use_memo(lambda: placed_booths(data, year_map.booths), [data])

    @report_errors
    def keep(transform: Transform) -> None:
        memory.map_zooms[zoom_key] = (transform.scale, transform.x, transform.y)

    zoom = use_zoom((plan.width, plan.height), on_transform=keep if zoom_key else None)
    ready = zoom.box[0] > 0  # laid out: the booths are placed
    # The selection is the memory's, shared with the other hall: a hall left mounted
    # under a pushed one rereads it when the route comes back (the location's
    # context re-renders it), and a tap's count re-renders this one (D-312).
    ft.use_route_location()
    selected = memory.expo_booth
    taps, set_taps = ft.use_state(0)
    flash, set_flash = ft.use_state(False)
    pulse_ms = prefs.motion_ms(PULSE_MS)

    @report_errors
    def select(number: str) -> None:
        memory.expo_booth = number
        set_taps(lambda n: n + 1)  # a tap on the selected booth pulses it again

    on_select = ft.use_callback(select, [])
    _, set_closes = ft.use_state(0)  # a Close re-renders the hall
    # The card body's own height, by booth: the card keeps no state itself (F150).
    body_size, set_body_size = ft.use_state(cast(tuple[str, float], ("", 0.0)))
    view_path = ft.use_view_path()

    @report_errors
    def close() -> None:
        memory.expo_booth = ""
        set_closes(lambda n: n + 1)

    on_close = ft.use_callback(close, [])

    @report_errors
    def body_measured(e: ft.LayoutSizeChangeEvent) -> None:
        set_body_size((memory.expo_booth, e.height))

    on_body_size = ft.use_callback(body_measured, [])

    item = next((each for each in booths if each.booth.number == selected), None)
    measured = body_size[1] if body_size[0] == selected else 0.0
    crowded = over_plan(zoom.box, zoom.shown)  # a phone in portrait (D-443)
    use_camera(
        zoom,
        memory,
        zoom_key=zoom_key,
        reveal=item.booth if item is not None and reveal == selected else None,
        cover=covered(zoom.box[1], measured, crowded=crowded) if measured else 0.0,
    )

    @report_errors
    async def pulse_twice() -> None:
        if not (taps and pulse_ms):
            return  # nothing tapped yet, or reduced motion: still (D-34, D-173)
        for _ in range(PULSES):
            set_flash(True)
            await asyncio.sleep(pulse_ms / 1000)
            set_flash(False)
            await asyncio.sleep(pulse_ms / 1000)

    # A new tap mid-pulse starts again: Flet cancels the old (F2).
    ft.use_effect(pulse_twice, [taps])

    layers: list[ft.Control] = []
    if ready:
        layers.append(
            BoothLayer(
                booths,
                zoom.shown,
                tokens,
                on_select,
                selected=selected,
                flash=flash,
                pulse_ms=pulse_ms,
            )
        )
    row, box = card_layout(zoom.box[1], measured, crowded=crowded)
    bottom: list[ft.Control] = [
        ft.Row(
            [zoom_buttons(zoom, SCREEN, row=row)], alignment=ft.MainAxisAlignment.END
        )
    ]
    if item is not None:
        hiring = hiring_line(data, item.sponsors[0]) if len(item.sponsors) == 1 else ""
        bottom.append(
            BoothCard(
                item,
                hiring=hiring,
                view_path=view_path,
                body_box=box,
                on_close=on_close,
                on_body_size=on_body_size,
                key=item.booth.number,  # pyright: ignore[reportCallIssue]  # as SessionRow's
            )
        )
    return ft.Stack(
        [
            # Booths to tap: no double-tap detector, which delays every tap (D-312).
            zoom_layer(zoom, plan.image, expo_label(plan), layers, double_tap=False),
            # No Container around the buttons and the card: a decorated box would
            # take the gestures beside them, which belong to the plan.
            ft.Column(
                bottom,
                left=16,
                right=16,
                bottom=16,
                spacing=16,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        ],
        fit=ft.StackFit.EXPAND,
        expand=True,
    )
