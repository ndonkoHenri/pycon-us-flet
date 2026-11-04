"""Tests for the shared states: `EmptyState`, `NoDataState` and `SkeletonList`.

The builders run outside a renderer: `SkeletonList`'s body runs unwrapped with the
`Prefs` the test gives it. How they look, and what TalkBack and VoiceOver read, is
checked on devices (the PR). `test_no_data_screens.py` holds `NoDataState` on each
screen (#83, #902; ux.md §3.9, §4).
"""

import inspect
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.feed_refresh import Problem
from pycon_us.prefs import Prefs
from pycon_us.services import Services
from pycon_us.state import Conference
from pycon_us.theme import HC_DARK_TOKENS, LIGHT_TOKENS, Tokens
from pycon_us.ui import states
from pycon_us.ui.buttons import ICON_PADDING, LABEL_PADDING
from pycon_us.ui.states import (
    NO_DATA_BODY,
    SKELETON_ROWS,
    EmptyState,
    NoDataState,
    SkeletonList,
)
from tests.sessions import memory_services
from tests.trees import descendants, only, texts


def never() -> None:
    """A handler that fails the test if anything calls it."""
    raise AssertionError("not tapped in this test")


# ------------------------------------------------------------------ EmptyState


def test_an_empty_state_says_why_and_names_its_way_out_as_one_button() -> None:
    """An empty state shows its sentence and one button that calls its handler."""
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
    """The empty state's icon is 48 dp and has no label for screen readers."""
    state = EmptyState("No rooms yet", icon=ft.Icons.PLACE_OUTLINED)
    icon = only(state, ft.Icon)
    assert icon.icon == ft.Icons.PLACE_OUTLINED
    assert icon.size == 48
    assert icon.semantics_label is None  # the sentence carries the meaning


def test_the_title_is_a_heading_and_the_text_a_live_region() -> None:
    """Title and body are live regions, title first; the title is a level-2 heading.

    One region around both read the body before the heading inside it (#1083).
    """
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
    # Announced when it replaces a list (D-33), each line a live node of its own; the
    # region around them has no text of its own to read before them.
    holder, *lines = region
    assert holder.identifier == "schedule.no_data" and not holder.label
    assert [texts(node) for node in lines] == [
        ["Can't load the schedule"],
        ["Connect to the internet and try again."],
    ]
    assert all(node.container for node in lines)
    headings = [
        node
        for node in descendants(state)
        if isinstance(node, ft.Semantics) and node.header
    ]
    assert [texts(node) for node in headings] == [["Can't load the schedule"]]
    assert headings[0].heading_level == 2  # under the page's title (D-211)
    # A node of its own: otherwise Flutter merges the heading flag into the live
    # region, and the title and body read as one heading.
    assert headings[0].container


def test_a_disabled_way_out_stays_in_place() -> None:
    """A disabled way out is still shown, as a disabled button."""
    state = EmptyState(
        "Can't load the schedule",
        icon=ft.Icons.CLOUD_OFF_OUTLINED,
        action="Try again",
        on_action=never,
        disabled=True,
    )
    assert only(state, ft.FilledTonalButton).disabled


@pytest.mark.parametrize("disabled", [False, True], ids=["enabled", "disabled"])
@pytest.mark.parametrize(
    ("link_id", "padding"),
    [(None, LABEL_PADDING), ("states.web", ICON_PADDING)],
    ids=["label", "web-link"],
)
def test_the_way_out_keeps_material_s_padding_at_every_text_size(
    link_id: str | None, padding: ft.Padding, disabled: bool
) -> None:
    """The way out pins its padding, so a large label never meets the pill's ends.

    Flutter shrinks the side padding as the text grows (D-344): a label-only button
    takes `LABEL_PADDING`, a web link's, with its icon, `ICON_PADDING`. It stays
    flat, enabled or disabled: with a style, Flet lifts every state to the button's
    `elevation`, 1 unless it is set to 0.
    """
    state = EmptyState(
        "No talks yet",
        icon=ft.Icons.EVENT_BUSY_OUTLINED,
        action="Try again",
        on_action=never,
        disabled=disabled,
        link_id=link_id,
    )
    button = only(state, ft.FilledTonalButton)
    assert button.disabled is disabled
    assert button.style is not None
    assert button.style.padding == padding
    assert button.elevation == 0


def test_the_way_out_is_outside_the_live_region_so_it_is_its_own_stop() -> None:
    """The button is outside the live region, a screen-reader stop of its own."""
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
    """With no action, as when the sentence names the way out, there is no button."""
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
    """An action label without a handler, or the reverse, raises `ValueError`."""
    with pytest.raises(ValueError, match="both a label and a handler"):
        EmptyState(
            "Can't load the schedule",
            icon=ft.Icons.CLOUD_OFF_OUTLINED,
            action=action,
            on_action=on_action,
        )


def test_an_empty_state_has_no_fixed_height_so_it_reflows_at_200_percent() -> None:
    """No control of an empty state sets a height, so it reflows at 200 % text."""
    state = EmptyState(
        "Can't load the schedule",
        icon=ft.Icons.CLOUD_OFF_OUTLINED,
        body="Connect to the internet and try again.",
        action="Try again",
        on_action=never,
    )
    assert all(getattr(node, "height", None) is None for node in descendants(state))


# ------------------------------------------------------------------ NoDataState


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """Return a session's services with the memory fakes."""
    return memory_services(load_year(2026), tmp_path)


def conference_with(problem: Problem, *, asked: bool = False) -> Conference:
    """Return a store whose fetch failed, and a refresh runs: asked for, or quiet."""
    conference = Conference(problem=problem)
    conference.refreshing, conference._asked = True, asked
    return conference


def test_no_data_shows_the_skeleton_until_a_fetch_has_failed(
    svc: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before a failure: the skeleton, saying what loads, and no button (NEW-03)."""
    # A text of its label: a component needs a renderer.
    monkeypatch.setattr(states, "SkeletonList", lambda label: ft.Text(label))
    conference = Conference()
    assert texts(NoDataState(conference, svc, "x.no_data")) == ["Loading schedule"]
    named = NoDataState(conference, svc, "x.no_data", loading="Loading rooms")
    assert texts(named) == ["Loading rooms"]


@pytest.mark.parametrize(("problem", "body"), NO_DATA_BODY.items())
def test_a_failed_fetch_says_what_failed_why_and_offers_try_again(
    svc: Services, problem: Problem, body: str
) -> None:
    """The title by the screen, the body by the problem, one button; `identifier`'s."""
    state = NoDataState(Conference(problem=problem), svc, "x.no_data", title="Can't")
    assert texts(state) == ["Can't", body]
    assert only(state, ft.Icon).icon == ft.Icons.CLOUD_OFF_OUTLINED
    assert only(state, ft.FilledTonalButton).content == "Try again"
    (region,) = [
        n
        for n in descendants(state)
        if isinstance(n, ft.Semantics) and n.identifier == "x.no_data"
    ]
    assert region.live_region


def test_the_title_says_the_schedule_unless_the_screen_names_something_else(
    svc: Services,
) -> None:
    """Most screens show the schedule, and say so."""
    state = NoDataState(Conference(problem="offline"), svc, "x.no_data")
    assert texts(state)[0] == "Can't load the schedule"


def test_a_quiet_refresh_leaves_try_again_enabled(svc: Services) -> None:
    """D-181: a refresh the app started greys nothing out, so a tap joins it."""
    state = NoDataState(conference_with("offline"), svc, "x.no_data")
    assert not only(state, ft.FilledTonalButton).disabled


def test_the_user_s_refresh_keeps_the_state_with_its_button_disabled(
    svc: Services,
) -> None:
    """The state doesn't go back to the skeleton: focus stays on the button (D-182)."""
    conference = conference_with("offline", asked=True)
    state = NoDataState(conference, svc, "x.no_data")
    assert texts(state)[1] == NO_DATA_BODY["offline"]
    assert only(state, ft.FilledTonalButton).disabled


async def test_try_again_is_the_user_s_refresh_and_reports_what_escapes(
    svc: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It refreshes with the session's services; an unexpected error isn't fatal."""
    calls: list[tuple[object, ...]] = []

    async def refresh(_: Conference, *args: object, closed: object) -> None:
        """Record the arguments, then fail as nothing expected does."""
        calls.append((*args, closed))
        raise RuntimeError("unexpected")

    # On the class: assigning to the store would notify, also when the patch is undone.
    monkeypatch.setattr(Conference, "refresh", refresh)
    state = NoDataState(Conference(problem="offline"), svc, "x.no_data")
    tap = cast(
        Callable[[], Awaitable[None]], only(state, ft.FilledTonalButton).on_click
    )
    await tap()  # returns: report_errors caught it
    assert calls == [(svc.storage, svc.year, svc.closed)]


# ------------------------------------------------------------------ SkeletonList


def skeleton(
    monkeypatch: pytest.MonkeyPatch,
    *,
    reduce_motion: bool,
    tokens: Tokens = LIGHT_TOKENS,
) -> ft.Semantics:
    """Build `SkeletonList` outside a renderer, with `reduce_motion` set."""
    monkeypatch.setattr(states, "use_prefs", lambda: Prefs(reduce_motion=reduce_motion))
    monkeypatch.setattr(states, "use_tokens", lambda: tokens)
    result = inspect.unwrap(SkeletonList)()
    assert isinstance(result, ft.Semantics)
    return result


def placeholder_rows(node: ft.Control) -> list[ft.Control]:
    """The placeholder rows: the controls of the first Column in `node`."""
    column = next(n for n in descendants(node) if isinstance(n, ft.Column))
    return list(column.controls)


def test_the_skeleton_shimmers_over_five_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """The skeleton shimmers over five placeholder rows, every 1.5 s."""
    result = skeleton(monkeypatch, reduce_motion=False)
    shimmer = only(result, ft.Shimmer)
    assert shimmer.period == 1500
    assert len(placeholder_rows(shimmer)) == SKELETON_ROWS == 5


def test_under_reduced_motion_the_skeleton_stays_still(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under reduced motion the skeleton keeps its rows but has no shimmer."""
    result = skeleton(monkeypatch, reduce_motion=True)
    assert not any(isinstance(n, ft.Shimmer) for n in descendants(result))  # D-173
    assert len(placeholder_rows(result)) == SKELETON_ROWS


def test_screen_readers_hear_one_loading_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """The skeleton is one node, "Loading schedule", whose rows say nothing."""
    result = skeleton(monkeypatch, reduce_motion=False)
    assert result.label == "Loading schedule"
    assert result.container
    assert result.exclude_semantics  # the placeholders say nothing
    assert texts(result) == []


def placeholders(node: ft.Control) -> list[ft.Container]:
    """The skeleton's placeholder shapes: every sized or expanding Container in it."""
    return [
        n
        for n in descendants(node)
        if isinstance(n, ft.Container) and n.height in (12, 16)
    ]


def test_in_high_contrast_the_shimmer_paints_unfilled_outlines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In HC each placeholder is an unfilled 1 dp outline, painted in `outline`.

    The fill is the surface there; the shimmer paints whatever its rows paint, so a
    fill would turn the whole block to ink (D-306).
    """
    result = skeleton(monkeypatch, reduce_motion=False, tokens=HC_DARK_TOKENS)
    shimmer = only(result, ft.Shimmer)
    assert shimmer.base_color == ft.Colors.OUTLINE
    shapes = placeholders(result)
    assert len(shapes) == 5 * SKELETON_ROWS
    for shape in shapes:
        assert shape.bgcolor is None
        assert shape.border == ft.Border.all(1, ft.Colors.OUTLINE)


def test_outside_high_contrast_the_placeholders_are_tonal_fills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outside HC the placeholders keep their tonal fill and have no border."""
    result = skeleton(monkeypatch, reduce_motion=False)
    shapes = placeholders(result)
    assert len(shapes) == 5 * SKELETON_ROWS
    for shape in shapes:
        assert shape.bgcolor == ft.Colors.SURFACE_CONTAINER_HIGHEST
        assert shape.border is None
