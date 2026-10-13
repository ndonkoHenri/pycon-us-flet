"""Tests for the shared states: ``EmptyState`` and ``SkeletonList`` (#83; ux.md §3.9, §4).

The builders run outside a renderer: ``SkeletonList``'s body runs unwrapped with the
``Prefs`` the test gives it. How they look, and what TalkBack and VoiceOver read, is
checked on devices (the PR).
"""

import inspect
from collections.abc import Callable
from typing import cast

import flet as ft
import pytest

from pycon_us.prefs import Prefs
from pycon_us.ui import states
from pycon_us.ui.states import SKELETON_ROWS, EmptyState, SkeletonList
from tests.trees import descendants, only, texts


def never() -> None:
    raise AssertionError("not tapped in this test")


# ------------------------------------------------------------------ EmptyState


def test_an_empty_state_says_why_and_names_its_way_out_as_one_button() -> None:
    taps: list[str] = []
    state = EmptyState(
        "This session isn't in the current schedule",
        icon=ft.Icons.EVENT_BUSY_OUTLINED,
        action="Open schedule",
        on_action=lambda: taps.append("tap"),
    )
    assert texts(state) == ["This session isn't in the current schedule"]
    button = only(state, ft.FilledTonalButton)  # one way out, never two
    assert button.content == "Open schedule"
    assert button.on_click is not None
    cast(Callable[[], None], button.on_click)()
    assert taps == ["tap"]


def test_an_empty_state_s_icon_is_large_and_decorative() -> None:
    state = EmptyState("No rooms yet", icon=ft.Icons.PLACE_OUTLINED)
    icon = only(state, ft.Icon)
    assert icon.icon == ft.Icons.PLACE_OUTLINED
    assert icon.size == 48
    assert icon.semantics_label is None  # the sentence carries the meaning


def test_the_title_is_a_heading_and_the_text_a_live_region() -> None:
    state = EmptyState(
        "Can't load the schedule",
        icon=ft.Icons.CLOUD_OFF_OUTLINED,
        body="Connect to the internet and try again.",
        identifier="schedule.no_data",
    )
    region = [
        node
        for node in descendants(state)
        if isinstance(node, ft.Semantics) and node.live_region
    ]
    assert len(region) == 1  # announced when it replaces a list (D-33)
    assert region[0].identifier == "schedule.no_data"
    assert texts(region[0]) == [
        "Can't load the schedule",
        "Connect to the internet and try again.",
    ]
    headings = [
        node
        for node in descendants(state)
        if isinstance(node, ft.Semantics) and node.header
    ]
    assert [texts(node) for node in headings] == [["Can't load the schedule"]]
    # A node of its own: otherwise Flutter merges the heading flag into the live
    # region, and the title and body read as one heading.
    assert headings[0].container


def test_a_disabled_way_out_stays_in_place() -> None:
    state = EmptyState(
        "Can't load the schedule",
        icon=ft.Icons.CLOUD_OFF_OUTLINED,
        action="Try again",
        on_action=never,
        disabled=True,
    )
    assert only(state, ft.FilledTonalButton).disabled


def test_the_way_out_is_outside_the_live_region_so_it_is_its_own_stop() -> None:
    state = EmptyState(
        "Page not found",
        icon=ft.Icons.LINK_OFF_OUTLINED,
        action="Go to Now",
        on_action=never,
    )
    region = next(
        node
        for node in descendants(state)
        if isinstance(node, ft.Semantics) and node.live_region
    )
    assert not any(isinstance(n, ft.FilledTonalButton) for n in descendants(region))


def test_an_empty_state_whose_sentence_names_the_way_out_has_no_button() -> None:
    state = EmptyState(
        'No results for "pydanitc"',
        icon=ft.Icons.SEARCH_OFF,
        body="Search covers all days and ignores your filters.",
    )
    assert not any(isinstance(n, ft.FilledTonalButton) for n in descendants(state))


@pytest.mark.parametrize(("action", "on_action"), [("Try again", None), (None, never)])
def test_an_action_needs_both_its_label_and_its_handler(
    action: str | None, on_action: Callable[[], None] | None
) -> None:
    with pytest.raises(ValueError, match="both a label and a handler"):
        EmptyState(
            "Can't load the schedule",
            icon=ft.Icons.CLOUD_OFF_OUTLINED,
            action=action,
            on_action=on_action,
        )


def test_an_empty_state_has_no_fixed_height_so_it_reflows_at_200_percent() -> None:
    state = EmptyState(
        "Can't load the schedule",
        icon=ft.Icons.CLOUD_OFF_OUTLINED,
        body="Connect to the internet and try again.",
        action="Try again",
        on_action=never,
    )
    assert all(getattr(node, "height", None) is None for node in descendants(state))


# ------------------------------------------------------------------ SkeletonList


def skeleton(monkeypatch: pytest.MonkeyPatch, *, reduce_motion: bool) -> ft.Semantics:
    monkeypatch.setattr(states, "use_prefs", lambda: Prefs(reduce_motion=reduce_motion))
    result = inspect.unwrap(SkeletonList)()
    assert isinstance(result, ft.Semantics)
    return result


def placeholder_rows(node: ft.Control) -> list[ft.Control]:
    column = next(n for n in descendants(node) if isinstance(n, ft.Column))
    return list(column.controls)


def test_the_skeleton_shimmers_over_five_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    result = skeleton(monkeypatch, reduce_motion=False)
    shimmer = only(result, ft.Shimmer)
    assert shimmer.period == 1500
    assert len(placeholder_rows(shimmer)) == SKELETON_ROWS == 5


def test_under_reduced_motion_the_skeleton_stays_still(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = skeleton(monkeypatch, reduce_motion=True)
    assert not any(isinstance(n, ft.Shimmer) for n in descendants(result))  # D-173
    assert len(placeholder_rows(result)) == SKELETON_ROWS


def test_screen_readers_hear_one_loading_node(monkeypatch: pytest.MonkeyPatch) -> None:
    result = skeleton(monkeypatch, reduce_motion=False)
    assert result.label == "Loading schedule"
    assert result.container
    assert result.exclude_semantics  # the placeholders say nothing
    assert texts(result) == []
