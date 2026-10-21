"""The Map's Floor plans pane: a card per plan, in the Map's order (MAP-02, ux.md §5.8).

Each card is an outlined ``Card`` with the plan's 16:10 thumbnail (bundled, so it shows
offline from the first start), its title, what is on it and ``OPEN_IN_FULL``; one node
for screen readers, a button, and a tap pushes the floor viewer (``…/plan/<id>``, one
drill level, ux.md §6.1). The Map (``screens/map.py``) shows it under its tab bar.
"""

from collections.abc import Sequence

import flet as ft

from pycon_us.locations import drill_href
from pycon_us.services.errors import report_errors
from pycon_us.ui.scrolling import SCROLL_EVENT_MS
from pycon_us.ui.widths import sides
from pycon_us.year_map import Plan

SCREEN = "map"
"""The screen's name in its semantics identifiers (decisions §M)."""

FLOOR_PLANS = "floor-plans"
"""The pane's slug: its ``?tab=`` value, its list's key and its tab's identifier."""

THUMB_RATIO = 16 / 10
"""The thumbnail's width to height: the plan is cropped to it, centred (MAP-02)."""


def plan_phrase(plan: Plan) -> str:
    """Return what a screen reader says of a plan's card: its name, then what is on it.

    Args:
        plan: The plan.
    """
    name = f"{plan.title} floor plan"
    return f"{name}, {plan.subtitle}" if plan.subtitle else name


def plan_card(plan: Plan, view_path: str) -> ft.Control:
    """Return one plan's card: the thumbnail over its title, what is on it, and an icon.

    The texts wrap at any text size: nothing in the card has a fixed height but the
    thumbnail, whose height follows the card's width. One node, read "Concourse level
    floor plan, Tutorials, talk tracks, registration, expo entry, button", identifier
    ``map.plan.<id>``.

    Args:
        plan: The plan.
        view_path: The Map's View path, so the viewer is pushed on top of it.
    """
    target = drill_href(view_path, "plan", plan.id)

    @report_errors
    def go() -> None:
        ft.context.page.navigate(target)

    texts: list[ft.Control] = [
        ft.Text(plan.title, theme_style=ft.TextThemeStyle.TITLE_MEDIUM)
    ]
    if plan.subtitle:
        texts.append(
            ft.Text(
                plan.subtitle,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    content = ft.Column(
        [
            ft.Image(
                plan.thumb,
                aspect_ratio=THUMB_RATIO,
                fit=ft.BoxFit.COVER,
                exclude_from_semantics=True,  # the card's phrase names the plan
            ),
            ft.Container(
                ft.Row(
                    [
                        ft.Column(texts, spacing=2, expand=True),
                        ft.Icon(ft.Icons.OPEN_IN_FULL),
                    ],
                    spacing=16,
                ),
                padding=16,
            ),
        ],
        spacing=0,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
    return ft.MergeSemantics(  # the phrase and the tap's action: one node
        content=ft.Card(
            ft.Container(
                ft.Semantics(
                    label=plan_phrase(plan),
                    identifier=f"{SCREEN}.plan.{plan.id}",
                    button=True,  # it opens the plan: "…, button" (D-33)
                    exclude_semantics=True,
                    content=content,
                ),
                ink=True,
                on_click=go,
            ),
            variant=ft.CardVariant.OUTLINED,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,  # the thumbnail and ink inside
            margin=ft.Margin.symmetric(horizontal=16, vertical=6),
        )
    )


def plans_pane(
    plans: Sequence[Plan],
    view_path: str,
    list_ref: ft.Ref[ft.ListView],
    on_scroll: ft.EventHandler[ft.OnScrollEvent],
    *,
    margin: float,
) -> ft.Control:
    """Return the Floor plans pane: a card per plan, in ``map.toml``'s order.

    Args:
        plans: The year's plans (``MapData.plans``).
        view_path: The Map's View path.
        list_ref: The Map's list ref, which its re-tap scrolls.
        on_scroll: The Map's scroll handler, which remembers where a scroll ended.
        margin: The screen's side margin (``use_margin()``).
    """
    return ft.ListView(
        [plan_card(plan, view_path) for plan in plans],
        key=FLOOR_PLANS,  # its own, so Flutter never reuses another pane's list (F130)
        ref=list_ref,
        expand=True,
        padding=sides(margin, top=6, bottom=8),
        scroll_interval=SCROLL_EVENT_MS,
        on_scroll=on_scroll,
    )
