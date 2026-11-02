"""``LocationCard``: a floor plan's thumbnail with a pin, which opens the floor viewer.

A place on the venue's plans, as one card (DATA-33, MAP-06; ux.md §3.9): the plan's
thumbnail, 112 dp wide, with the pin on its spot, beside the pin's label, what happens
there and the floor; a tap pushes the floor viewer at it, ``…/plan/<plan>?pin=<key>``
(ux.md §6.1). Room detail and session detail show a room's (ROOM-04, D-346, D-349;
``room_card()``). Without a pin it is the plan's
own card, which the job fair's uses (D-254): the thumbnail and the plan's title.

**Better than the original:** Ionic's pin pulsed forever and the card said nothing to
a screen reader. Here the pin pulses twice when the card first shows, then stays still,
and is still from the start under reduced motion (D-34, D-173); the card is one button
node that says where it leads ("Show Room 104A on the Concourse level floor plan"), the
thumbnail excluded. Help & safety and Venue & hours show a venue spot's card by its pin
key (``spot_card()``); the job fair's pane shows its plan's (``job_fair_card()``). At
large text (``Prefs.time_above``, D-216) the words go under the thumbnail rather than
squeeze beside it, and the card keeps the list's width (#795); nothing has a fixed
height but the image.
Apart from ``ui/rows.py`` so that it stays under about 400 lines (D-66).
"""

import asyncio

import flet as ft

from pycon_us.locations import drill_href
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.pref_keys import THEME
from pycon_us.year_map import JOB_FAIR_PLAN, MapData, Pin, Plan

THUMB_DP = 112
"""The thumbnail's width; its height follows the plan's aspect ratio."""

PIN_BOX = 32
"""The pin's box, centred on its point: room for the ring at its widest."""

DOT_DP = 12
"""The pin's dot, ``primary`` with an ``on_primary`` rim, as the floor viewer's."""

RIM_DP = 2

RING_SCALE = 2.4
"""How far the ring grows as it pulses, from the dot's size."""

RING_OPACITY = 0.4

PULSES = 2
"""How often the pin pulses when the card first shows: at most twice (D-34)."""

PULSE_MS = 300
"""Each half of a pulse, out or back (ux.md §3.8's range)."""


def card_label(plan: Plan, pin: Pin | None) -> str:
    """Return what a screen reader says of the card: where a tap leads.

    Args:
        plan: The plan the card shows.
        pin: The place marked on it, or None for the plan's own card.
    """
    if pin is None:
        return f"Open the {plan.title} floor plan"
    return f"Show {pin.label} on the {plan.title} floor plan"


def card_href(view_path: str, plan: Plan, pin: Pin | None) -> str:
    """Return the floor viewer's location, pushed on the card's View, with the pin.

    Args:
        view_path: The View the card is on.
        plan: The plan the card shows.
        pin: The place marked on it, or None.
    """
    href = drill_href(view_path, "plan", plan.id)
    return f"{href}?pin={pin.key}" if pin is not None else href


def thumb_size(plan: Plan) -> tuple[float, float]:
    """Return the thumbnail's size in dp: ``THUMB_DP`` wide, the plan's aspect ratio.

    Args:
        plan: The plan; its thumbnail is the plan fitted to 800 px, the same shape.
    """
    return THUMB_DP, THUMB_DP * plan.height / plan.width


def pin_dot(
    pin: Pin, size: tuple[float, float], *, ring: bool, ring_ms: int
) -> ft.Stack:
    """Return the pin on the thumbnail: a dot on its spot, with the ring that pulses.

    Placed from the pin's percentages, which land on the thumbnail as on the plan.

    Args:
        pin: The place marked.
        size: The thumbnail's size (``thumb_size()``).
        ring: Whether the ring is out, mid-pulse.
        ring_ms: How long the ring takes out or back (``prefs.motion_ms()``).
    """
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
        left=pin.x / 100 * size[0] - PIN_BOX / 2,
        top=pin.y / 100 * size[1] - PIN_BOX / 2,
        width=PIN_BOX,
        height=PIN_BOX,
        alignment=ft.Alignment.CENTER,
    )


def LocationCard(
    plan: Plan,
    pin: Pin | None,
    *,
    identifier: str,
    seen: set[str] | None = None,
    active: bool = True,
) -> ft.Control:
    """Return the card of a place on a plan, or of the plan alone, a memoised component.

    Given the same plan and pin, frozen and equal on every render, it skips its body
    (D-153, F34), so the screen around it re-renders no card and restarts no pulse.

    Args:
        plan: The plan to show.
        pin: The place on it (``MapData.room_pin()``, ``MapData.pin()``), or None for
            the plan's own card.
        identifier: For UI flows, ``<screen>.location``.
        seen: The pins already pulsed on this View, for a screen whose list builds
            the card again as it scrolls or changes tab (room detail's day lists): a
            card whose pin is in it stays still, and a card that pulses adds its pin.
            None: the card pulses each time it mounts.
        active: Whether the card shows: a card on a hidden tab waits, without
            claiming its pin in ``seen``, and pulses when it first shows (#602).
    """
    key = f"{plan.id}:{pin.key if pin else ''}"
    # As SessionRow's: ft.component's typing leaves out the key= its wrapper takes.
    return _LocationCard(
        plan,
        pin,
        identifier=identifier,
        seen=seen,
        active=active,
        key=key,  # pyright: ignore[reportCallIssue]
    )


def room_card(
    data: MapData,
    room_name: str,
    *,
    identifier: str,
    seen: set[str] | None = None,
    active: bool = True,
) -> ft.Control | None:
    """Return a room's ``LocationCard``, or None for a room without a pin.

    Args:
        data: The year's ``map.toml``.
        room_name: The room's name as the feed writes it, which finds its pin.
        identifier: For UI flows, ``<screen>.location``.
        seen: As ``LocationCard``'s.
        active: As ``LocationCard``'s.
    """
    pin = data.room_pin(room_name)
    plan = data.plan(pin.plan) if pin else None
    if pin is None or plan is None:
        return None
    return LocationCard(plan, pin, identifier=identifier, seen=seen, active=active)


def spot_card(data: MapData, key: str, *, identifier: str) -> ft.Control | None:
    """Return the ``LocationCard`` of the pin ``key``, or None without one.

    The loader refuses a key ``map.toml`` lacks, so None here is a place with no pin
    (an empty key) or a year with no plans.

    Args:
        data: The year's ``map.toml``.
        key: A venue spot's pin key (``info-desk``), as ``content.toml`` names it.
        identifier: The card's, ``<screen>.<place>.location``.
    """
    pin = data.pin(key) if key else None
    plan = data.plan(pin.plan) if pin else None
    if pin is None or plan is None:
        return None
    return LocationCard(plan, pin, identifier=identifier)


def job_fair_card(data: MapData, *, identifier: str) -> ft.Control | None:
    """Return the job fair plan's card, ``LocationCard``'s plan-only form, or None.

    One card in three places (D-254): it heads the Map's Job fair pane (MAP-04) and Job
    listings (SPON-10), and follows the room's on Job Fair sessions (SESS-10). A tap
    pushes ``…/plan/job-fair``, the floor viewer without pins. None for a year whose
    ``map.toml`` has no ``job-fair`` plan.

    Args:
        data: The year's ``map.toml``.
        identifier: The card's, ``<screen>.job_fair.location``.
    """
    plan = data.plan(JOB_FAIR_PLAN)
    if plan is None:
        return None
    return LocationCard(plan, None, identifier=identifier)


@ft.memo
@ft.component
def _LocationCard(
    plan: Plan, pin: Pin | None, *, identifier: str, seen: set[str] | None, active: bool
) -> ft.Control:
    """The body of ``LocationCard``; it runs only when its plan or pin changes."""
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    prefs = use_prefs()
    ring, set_ring = ft.use_state(False)
    ring_ms = prefs.motion_ms(PULSE_MS)

    @report_errors
    async def pulse_twice() -> None:
        # Once, when the card first shows: Back from the viewer finds it mounted, so
        # a return never pulses (D-18); under reduced motion it stays still (D-173).
        # A card on a hidden tab waits for its tab, its pin unclaimed (#602).
        if pin is None or not active:
            return
        if seen is not None:
            # A card whose pin pulsed on this View already (another day's list, a
            # list scrolled back) stays still. Before any await, so cards mounted
            # in the same render see each other.
            if pin.key in seen:
                return
            seen.add(pin.key)
        if not ring_ms:
            return
        # A round trip: Flutter has drawn the pin before it pulses (D-156).
        await svc.storage.get(THEME)
        try:
            for _ in range(PULSES):
                set_ring(True)
                await asyncio.sleep(ring_ms / 1000)
                set_ring(False)
                await asyncio.sleep(ring_ms / 1000)
        finally:  # a tab left mid-pulse cancels it: the ring goes back in
            set_ring(False)

    # Runs again when the card's tab shows or hides; Flet cancels a pulse still
    # running then, or on unmount (F2).
    ft.use_effect(pulse_twice, [active])

    @report_errors
    def go() -> None:
        page.navigate(card_href(view_path, plan, pin))

    size = thumb_size(plan)
    thumb = ft.Stack(
        [
            ft.Image(plan.thumb, width=size[0], height=size[1], fit=ft.BoxFit.CONTAIN),
            *([pin_dot(pin, size, ring=ring, ring_ms=ring_ms)] if pin else []),
        ],
        width=size[0],
        height=size[1],
        clip_behavior=ft.ClipBehavior.NONE,  # the ring may pass the edge
    )
    lines = ft.Column(_lines(plan, pin), spacing=2, tight=True)
    body: ft.Control
    if prefs.time_above:  # large text: the words under the thumbnail
        # A Row fills its width, as the default size's does, so the card spans the
        # list rather than shrink to its words (#795); the thumbnail keeps its size.
        body = ft.Column([ft.Row([thumb]), lines], spacing=12, tight=True)
    else:
        lines.expand = True
        body = ft.Row(
            [thumb, lines],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    return ft.MergeSemantics(  # the label and the tap's action: one node
        content=ft.Card(
            ft.Container(
                ft.Semantics(
                    label=card_label(plan, pin),
                    identifier=identifier,
                    button=True,  # it opens the floor viewer: "…, button" (D-33)
                    exclude_semantics=True,  # the label replaces the image and texts
                    content=body,
                ),
                ink=True,
                on_click=go,
                padding=12,
            ),
            variant=ft.CardVariant.OUTLINED,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,  # the ink stays inside
            margin=0,
        )
    )


def _lines(plan: Plan, pin: Pin | None) -> list[ft.Control]:
    """Return the card's words: the pin's label, what happens there and the floor.

    Args:
        plan: The plan shown: its title is the floor.
        pin: The place marked, or None: the plan's title and what is on it.
    """
    title = pin.label if pin else plan.title
    details = (pin.sublabel, plan.title) if pin else (plan.subtitle,)
    return [
        ft.Text(title, theme_style=ft.TextThemeStyle.TITLE_MEDIUM),
        *(
            ft.Text(
                text,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
            for text in details
            if text
        ),
    ]
