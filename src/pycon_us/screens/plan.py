"""Floor viewer (``…/plan/<plan>``): one floor plan to zoom, with a pin (ROOM-05, MAP-05, INFO-13).

A pushed View (ux.md §6.1): the app bar names the plan and its overflow resets the
view; the plan fills the body in ``ui/zoom.py``'s zoom layer, from the fitted plan to
one image pixel per logical pixel (D-312), with a double tap for 2x or back to fit, as
nothing on it is tappable. The zoom buttons sit bottom-right, the single-pointer way to
zoom (WCAG 2.5.1).

``?pin=<key>`` (``use_query()``, U9 interim) marks a room or a venue spot of
``map.toml``: a dot on the plan, placed from its percentages, the same size on screen
at every zoom, which pulses twice when the View opens and then stays still (D-34),
still from the start under reduced motion (D-173). The label card under the plan,
outside the zoom layer, names it at any zoom. ``ViewMemory.plan_pins`` keeps a View
rebuilt in a new session (D-143) from pulsing again (D-18). An unknown pin, or one on
another plan, shows no pin; an unknown plan shows its not-found state, whose way out
is the Map (D-186, ux.md §4.6).
"""

import asyncio
from functools import partial

import flet as ft

from pycon_us.locations import use_query
from pycon_us.memory import ViewMemory
from pycon_us.prefs import use_prefs
from pycon_us.screens.stub import not_found
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import THEME
from pycon_us.ui.menus import menu_item, overflow_menu
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.semantics import named
from pycon_us.ui.zoom import (
    RESET_VIEW,
    Size,
    centred_on,
    use_zoom,
    zoom_buttons,
    zoom_layer,
)
from pycon_us.year_map import Pin, Plan

SCREEN = "plan"
"""The page's name in its semantics identifiers (decisions §M)."""

NOT_FOUND = "This floor plan isn't in this year's maps"
OPEN_MAP = "Open the map"

PIN_BOX = 48
"""The pin's box, centred on its point: room for the ring at its widest."""

DOT_DP = 20
"""The pin's dot, ``primary`` with an ``on_primary`` rim, so it shows on any plan."""

RIM_DP = 3

RING_SCALE = 2.4
"""How far the ring grows as it pulses, from the dot's size."""

RING_OPACITY = 0.4

PULSES = 2
"""How often the pin pulses when the View opens: at most twice (D-34)."""

PULSE_MS = 300
"""Each half of a pulse, out or back (ux.md §3.8's range)."""


def plan_label(plan: Plan, pin: Pin | None) -> str:
    """Return what a screen reader says of the plan: its name, and the pin it marks.

    Args:
        plan: The plan shown.
        pin: The pin on it, if any.
    """
    name = f"{plan.title} floor plan"
    return f"{name}, {pin.label} marked" if pin else name


def pin_on(plan: Plan | None, key: str, pins: dict[str, Pin]) -> Pin | None:
    """Return the pin ``key`` names, when it is on ``plan``; else None.

    Args:
        plan: The plan shown, or None for an unknown plan.
        key: The ``?pin=`` key, possibly empty.
        pins: The year's pins by key.
    """
    pin = pins.get(key)
    return pin if plan is not None and pin is not None and pin.plan == plan.id else None


def forget(memory: ViewMemory, view_path: str) -> None:
    """The pulse effect's cleanup: a floor viewer that leaves forgets its pin.

    It runs when the View leaves the stack (Back), so the next opening pulses again;
    a replaced session never runs it (F30), so the View its successor rebuilds finds
    the entry and stays still (D-18). Its presence also makes Flet cancel a pulse
    still running (F2).

    Args:
        memory: The process's ``ViewMemory``.
        view_path: The floor viewer's View path.
    """
    memory.plan_pins.pop(view_path, None)


def pin_marker(
    pin: Pin, shown: Size, *, scale: float, ring: bool, ring_ms: int
) -> ft.Control:
    """Return the pin: a dot on its point, with the ring that pulses around it.

    The zoom layer scales what is on the plan; the pin scales back by ``1 / scale``
    about its centre, so it stays one size on screen and its centre on its point.
    Decorative: the plan's ``semantics_label`` names the pin.

    Args:
        pin: The pin.
        shown: The plan's fitted size (``ui.zoom.fitted()``).
        scale: The viewer's scale.
        ring: Whether the ring is out, mid-pulse.
        ring_ms: How long the ring takes out or back (``prefs.motion_ms()``).
    """
    left, top = centred_on(pin.x, pin.y, shown, PIN_BOX)
    animation = ft.Animation(ring_ms, ft.AnimationCurve.EASE_OUT)
    halo = ft.Container(
        width=DOT_DP,
        height=DOT_DP,
        border_radius=DOT_DP / 2,
        bgcolor=ft.Colors.PRIMARY,
        opacity=RING_OPACITY if ring else 0.0,
        scale=RING_SCALE if ring else 1.0,
        animate_opacity=animation,
        animate_scale=animation,
    )
    dot = ft.Container(
        width=DOT_DP,
        height=DOT_DP,
        border_radius=DOT_DP / 2,
        bgcolor=ft.Colors.PRIMARY,
        border=ft.Border.all(RIM_DP, ft.Colors.ON_PRIMARY),
    )
    return ft.Stack(
        [halo, dot],
        left=left,
        top=top,
        width=PIN_BOX,
        height=PIN_BOX,
        alignment=ft.Alignment.CENTER,
        scale=1 / scale,
    )


def label_card(plan: Plan, pin: Pin) -> ft.Control:
    """Return the label card: the pin's name over its plan and what happens there.

    Outside the zoom layer, so it reads the same at any zoom; one node for screen
    readers ("Room 104C, Concourse level · Talk track"), ``plan.label``.

    Args:
        plan: The plan shown.
        pin: The pin on it.
    """
    where = " · ".join(part for part in (plan.title, pin.sublabel) if part)
    lines = ft.Column(
        [
            ft.Text(pin.label, theme_style=ft.TextThemeStyle.TITLE_SMALL),
            ft.Text(where, theme_style=ft.TextThemeStyle.BODY_MEDIUM),
        ],
        spacing=2,
        tight=True,
    )
    card = ft.Card(
        ft.Container(lines, padding=ft.Padding.symmetric(horizontal=16, vertical=12)),
        margin=0,
    )
    return named(f"{SCREEN}.label", card)


@ft.component
def PlanViewer(plan_id: str) -> ft.View:
    """One floor plan, zoomable, with the pin ``?pin=`` names.

    Args:
        plan_id: The plan id (``map.toml``), unquoted.
    """
    view_path = ft.use_view_path()
    svc = use_services()
    prefs = use_prefs()
    memory = svc.memory
    query = use_query()
    data = svc.year.map
    plan = data.plan(plan_id)
    pins = ft.use_memo(lambda: {pin.key: pin for pin in data.pins}, [])
    # The query seeds the pin; a View built below the top has no query (D-143).
    key = query.get("pin") or memory.plan_pins.get(view_path, "")
    pin = pin_on(plan, key, pins)
    zoom = use_zoom((plan.width, plan.height) if plan else (1.0, 1.0))
    ready = zoom.box[0] > 0  # laid out: the pin is drawn
    # Decided once, when the View mounts: a View rebuilt where its pin pulsed (a new
    # session, D-143) leaves it still (D-18).
    pulse, _ = ft.use_state(
        lambda: pin is not None and memory.plan_pins.get(view_path) != pin.key
    )
    ring, set_ring = ft.use_state(False)
    ring_ms = prefs.motion_ms(PULSE_MS)

    @report_errors
    async def pulse_twice() -> None:
        if pin is None:
            return
        memory.plan_pins[view_path] = pin.key
        if not (pulse and ready and ring_ms):
            return  # still from the start under reduced motion (D-34, D-173)
        # A round trip: Flutter has drawn the pin before it pulses (D-156).
        await svc.storage.get(THEME)
        for _ in range(PULSES):
            set_ring(True)
            await asyncio.sleep(ring_ms / 1000)
            set_ring(False)
            await asyncio.sleep(ring_ms / 1000)

    ft.use_effect(pulse_twice, [ready], cleanup=partial(forget, memory, view_path))

    if plan is None:
        return AppScaffold(
            title="Not found",
            body=ft.ListView(
                [
                    not_found(
                        NOT_FOUND,
                        icon=ft.Icons.MAP_OUTLINED,
                        action=OPEN_MAP,
                        location="/map",
                        identifier=f"{SCREEN}.not_found",
                    )
                ],
                expand=True,
            ),
        )

    @report_errors
    async def reset_view() -> None:
        await zoom.reset()

    layers: list[ft.Control] = []
    if pin is not None and ready:
        layers.append(
            pin_marker(pin, zoom.shown, scale=zoom.scale, ring=ring, ring_ms=ring_ms)
        )
    # The card bottom-left, the buttons bottom-right, side by side: at large text the
    # card wraps rather than slide under the buttons. Their row's empty space takes no
    # gestures, which reach the plan under it: no Container there, since Flet always
    # decorates one and a decorated box takes every pointer inside it.
    card = [label_card(plan, pin)] if pin is not None else []
    controls = ft.Row(
        [ft.Column(card, expand=True, tight=True), zoom_buttons(zoom, SCREEN)],
        spacing=16,
        vertical_alignment=ft.CrossAxisAlignment.END,
        left=16,
        right=16,
        bottom=16,
    )
    menu = overflow_menu(
        f"{SCREEN}.overflow",
        [
            menu_item(
                ft.Icons.CENTER_FOCUS_STRONG,
                RESET_VIEW,
                reset_view,
                identifier=f"{SCREEN}.reset_view",
            )
        ],
    )
    return AppScaffold(
        title=plan.title,
        actions=[menu],
        body=ft.Stack(
            [
                # Nothing on the floor viewer's plans is tappable: a double tap
                # delays no tap here (D-312).
                zoom_layer(
                    zoom, plan.image, plan_label(plan, pin), layers, double_tap=True
                ),
                controls,
            ],
            fit=ft.StackFit.EXPAND,
            expand=True,
        ),
    )
