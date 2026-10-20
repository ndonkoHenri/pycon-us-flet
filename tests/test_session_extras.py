"""Tests for session detail's extras (NEW-06, SESS-09, SESS-11; ux.md §5.5, D-206).

Share and its text, a Posters row's posters, an open space's image and site link
(``screens/session_extras.py``), in ``SessionDetail`` as ``tests/session_detail.py``
renders it. How they look, at 200 % text and in dark mode, is checked on devices (the
PR); here, what they say and what a tap does.
"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.locations import parent_of
from pycon_us.prefs import Prefs
from pycon_us.screens import session_extras as extras
from pycon_us.ui.share import NOT_SHARED
from tests.session_detail import (
    BREAK,
    TALK,
    VIEW,
    Detail,
    Render,
    headings,
    rendering,
    words,
)


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Return a function that renders a session's detail at ``VIEW``, given its id."""
    async with rendering(tmp_path, monkeypatch) as show:
        yield show


# ------------------------------------------------------------------ Share (NEW-06)

POSTERS = "poster-Expo Hall AB-2026-05-17T09:30:00-07:00"
"""The Posters row: the poster session, Sun May 17 9:30 AM-1:00 PM, Expo Hall AB."""

FIRST_POSTER = "poster-detail-60"
"""The first of its 25 posters by title: Beyond “LGTM”, by Daaimah Tibrey."""

SPACE_WITH_IMAGE = "9119"
"""5K Fun Run: an open space with an image."""

SPACE_WITHOUT_IMAGE = "9078"
"""GeoData Show & Tell / Meetup: an open space without one."""


def actions(detail: Detail) -> list[str | None]:
    """The app bar's actions, by identifier, in order: the row that holds Share."""
    for row in detail.session.index.values():
        if isinstance(row, ft.Row):
            found = [identifier(control) for control in row.controls]
            if "session.share" in found:
                return found
    raise AssertionError("no Share in the app bar")


def identifier(control: ft.Control) -> str | None:
    """The semantics identifier a control carries, merged or not; None for none."""
    node: object = control
    while node is not None:
        if isinstance(node, ft.Semantics) and node.identifier:
            return node.identifier
        node = (
            node._b
            if isinstance(node, ft.Component)
            else getattr(node, "content", None)
        )
    return None


def share_button(detail: Detail) -> ft.IconButton:
    """The Share button in the session's app bar."""
    return cast(ft.IconButton, detail.node("session.share").content)


async def test_share_sits_between_the_star_and_the_overflow(render: Render) -> None:
    """ux.md §5.5: the star, Share, then More options."""
    detail = await render(TALK)
    assert actions(detail) == ["session.favorite", "session.share", "session.overflow"]
    button = share_button(detail)
    assert button.icon == ft.Icons.SHARE_OUTLINED
    assert button.tooltip == extras.SHARE_TOOLTIP


async def test_more_options_is_one_node_with_its_identifier(render: Render) -> None:
    """#239: bare, the identifier's node took the tooltip and the button went unnamed."""
    detail = await render(TALK)
    node = detail.node("session.overflow")
    assert isinstance(node.parent, ft.MergeSemantics)
    assert isinstance(node.content, ft.PopupMenuButton)
    assert node.content.tooltip == "More options"


async def test_share_sends_the_title_when_and_where_and_the_public_page(
    render: Render,
) -> None:
    """Share sends three lines: the title, when and where, and the public page.

    The title is the share's subject too.
    """
    detail = await render(TALK)
    await detail.click(share_button(detail))
    ((text, options),) = detail.share.texts
    assert text.split("\n") == [
        "Python for Humans - Designing Python Code Like a User Interface",
        "PyCon US 2026 · Saturday, May 16, 10:30–11:00 AM PDT · Grand Ballroom A",
        "https://us.pycon.org/2026/schedule/presentation/142/",
    ]
    assert options["subject"] == (
        "Python for Humans - Designing Python Code Like a User Interface"
    )


async def test_a_break_shares_its_time_without_a_url(render: Render) -> None:
    """NEW-06: a synthetic id has no page; a break has no star, but can be shared."""
    detail = await render(BREAK)
    assert actions(detail) == ["session.share"]
    await detail.click(share_button(detail))
    ((text, _),) = detail.share.texts
    assert text == "Break\nPyCon US 2026 · Saturday, May 16, 10:05–10:30 AM PDT"


async def test_a_share_sheet_that_fails_to_open_says_so(render: Render) -> None:
    """A share sheet that fails to open says so, and Share stays enabled for a retry."""
    detail = await render(TALK)
    detail.share.error = RuntimeError("share_text failed")
    await detail.click(share_button(detail))
    (snack,) = detail.snack_bars
    assert cast(ft.Text, snack.content).value == NOT_SHARED
    assert not share_button(detail).disabled  # it can be tried again


async def test_share_is_disabled_while_the_sheet_is_up(render: Render) -> None:
    """ux.md §5.5: a second tap does not ask for a second sheet, and says so (F42)."""
    detail = await render(TALK)
    detail.share.gate = asyncio.Event()
    shown = asyncio.create_task(detail.click(share_button(detail)))
    await detail.settle()
    assert share_button(detail).disabled
    assert detail.node("session.share").disabled  # the merged node says so too
    detail.share.gate.set()
    await shown
    await detail.settle()
    assert not share_button(detail).disabled
    assert not detail.node("session.share").disabled
    assert len(detail.share.texts) == 1


# ------------------------------------------------------------------ posters (SESS-09)


def poster_rows(detail: Detail) -> list[ft.Semantics]:
    """The poster rows in the detail, found by their identifiers' prefix."""
    return [
        node
        for node in detail.session.index.values()
        if isinstance(node, ft.Semantics)
        and (node.identifier or "").startswith("session.session.poster-detail-")
    ]


async def test_the_posters_row_lists_its_posters_under_a_count(render: Render) -> None:
    """The Posters detail lists its 25 posters under a level-2 heading with the count.

    A poster's row reads its title and its speakers only.
    """
    detail = await render(POSTERS)
    assert ("Posters (25)", 2) in headings(detail)
    rows = poster_rows(detail)
    assert len(rows) == 25
    assert rows[0].identifier == f"session.session.{FIRST_POSTER}"
    title = (
        "Beyond “LGTM”: Building a Python Bot That Teaches Teams How to Actually "
        "Talk to Each Other"
    )
    # Neither the badge, the time nor the place: the page above says them all.
    assert rows[0].label == f"{title}. Daaimah Tibrey."
    assert words(rows[0]) == [title, "Daaimah Tibrey"]


async def test_a_poster_pushes_its_detail_and_back_returns_to_the_posters(
    render: Render,
) -> None:
    """D-17: one View per hop, so Back from the poster pops to the Posters detail."""
    detail = await render(POSTERS)
    row = next(
        c
        for c in detail.session.index.values()
        if isinstance(c, ft.Container) and c.content is poster_rows(detail)[0]
    )
    await detail.click(row)
    assert detail.pushed == [f"{VIEW}/session/{FIRST_POSTER}"]
    assert parent_of(detail.pushed[0]) == VIEW


async def test_a_poster_s_star_saves_that_poster(render: Render) -> None:
    """A poster's own star in the Posters detail saves that poster."""
    detail = await render(POSTERS)
    star = cast(ft.IconButton, detail.node(f"session.favorite.{FIRST_POSTER}").content)
    await detail.click(star)
    assert detail.favorites.ids == {FIRST_POSTER}


async def test_other_sessions_list_no_posters(render: Render) -> None:
    """A detail other than the Posters row's, here a poster's, lists no posters."""
    detail = await render(FIRST_POSTER)
    assert poster_rows(detail) == []
    assert "Posters (25)" not in [text for text, _ in headings(detail)]


# ------------------------------------------------------------------ open spaces (SESS-11)


def images(detail: Detail) -> list[ft.Image]:
    """Every image in the detail: the open space's image and its blurred copy."""
    return [c for c in detail.session.index.values() if isinstance(c, ft.Image)]


def image(detail: Detail) -> ft.Image:
    """The image screen readers name, not its blurred copy behind it."""
    (found,) = (c for c in images(detail) if not c.exclude_from_semantics)
    return found


def backdrop(detail: Detail) -> ft.Image:
    """The image's blurred copy behind it, which screen readers skip."""
    (found,) = (c for c in images(detail) if c.exclude_from_semantics)
    return found


async def test_an_open_space_shows_its_image_named_for_screen_readers(
    render: Render,
) -> None:
    """An open space shows its image, named for screen readers after its title."""
    detail = await render(SPACE_WITH_IMAGE)
    shown = image(detail)
    assert shown.src == (
        "https://pycon-assets.s3.amazonaws.com/2026/media/open_spaces_images/"
        "running-sand.png"
    )
    assert shown.semantics_label == "Image for “5K Fun Run”"
    assert not shown.exclude_from_semantics
    assert detail.nodes("session.image")


async def test_an_image_that_does_not_load_says_so_in_its_frame(render: Render) -> None:
    """An image that does not load shows the image error message in its place."""
    detail = await render(SPACE_WITH_IMAGE)
    fallback = image(detail).error_content
    assert fallback is not None
    assert words(fallback) == [extras.IMAGE_ERROR]


async def test_the_image_fits_a_frame_the_content_s_width(render: Render) -> None:
    """Scaled down within the content width, never cropped (fit, not cover)."""
    detail = await render(SPACE_WITH_IMAGE)
    shown = image(detail)
    assert shown.fit == ft.BoxFit.CONTAIN
    assert (shown.width, shown.height) == (None, None)  # its frame decides
    (stack,) = (
        c
        for c in detail.session.index.values()
        if isinstance(c, ft.Stack) and shown in c.controls
    )
    assert stack.controls[-1] is shown  # on top, centred, not positioned
    assert (shown.left, shown.top, shown.right, shown.bottom) == (None,) * 4
    frame = next(
        c
        for c in detail.session.index.values()
        if isinstance(c, ft.Container) and c.content is stack
    )
    assert frame.aspect_ratio == extras.IMAGE_RATIO


async def test_the_frame_around_the_image_is_its_own_blurred_copy(
    render: Render,
) -> None:
    """D-206: no grey bars beside a portrait image; one name, one error message."""
    detail = await render(SPACE_WITH_IMAGE)
    copy, shown = backdrop(detail), image(detail)
    assert copy.src == shown.src
    assert copy.fit == ft.BoxFit.COVER
    assert (copy.left, copy.top, copy.right, copy.bottom) == (0, 0, 0, 0)
    assert copy.error_content is not None
    assert words(copy.error_content) == []
    (scrim,) = (
        c
        for c in detail.session.index.values()
        if isinstance(c, ft.Container) and c.blur is not None
    )
    assert (scrim.left, scrim.top, scrim.right, scrim.bottom) == (0, 0, 0, 0)


async def test_the_image_fades_in_once_loaded(render: Render) -> None:
    """The image fades in once loaded, but its blurred copy behind it does not."""
    detail = await render(SPACE_WITH_IMAGE)
    animation = cast(ft.Animation, image(detail).fade_in_animation)
    assert animation.duration == extras.IMAGE_FADE_MS
    # Not the copy behind it: a fading image is laid out loose, so it would not
    # cover the frame (F45).
    assert backdrop(detail).fade_in_animation is None


async def test_under_reduced_motion_the_image_appears_at_once(
    render: Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Under reduced motion, the image's fade-in takes no time."""
    monkeypatch.setattr(Prefs, "motion_ms", lambda self, ms: 0)
    detail = await render(SPACE_WITH_IMAGE)
    assert cast(ft.Animation, image(detail).fade_in_animation).duration == 0


async def test_an_open_space_without_an_image_has_no_frame(render: Render) -> None:
    """An open space without an image shows no image, but still links its site entry."""
    detail = await render(SPACE_WITHOUT_IMAGE)
    assert not [c for c in detail.session.index.values() if isinstance(c, ft.Image)]
    assert detail.nodes("session.site")


async def test_an_open_space_links_its_entry_on_the_site_in_the_page(
    render: Render,
) -> None:
    """SESS-11, D-206: the link is in the page, so there is no overflow to repeat it."""
    detail = await render(SPACE_WITH_IMAGE)
    assert detail.nodes("session.overflow") == []
    link = detail.node("session.site")
    assert link.link  # it leaves the app (ux.md §4.7)
    tile = next(
        c
        for c in detail.session.index.values()
        if isinstance(c, ft.ListTile) and c.title == "Open on us.pycon.org"
    )
    await detail.click(tile)
    assert detail.launcher.launched == [
        (
            "https://us.pycon.org/2026/schedule/open-spaces/#OpenSpace-119",
            ft.LaunchMode.IN_APP_BROWSER_VIEW,
        )
    ]


async def test_a_talk_has_no_image_and_no_site_link_in_the_page(
    render: Render,
) -> None:
    """A talk shows neither an image nor a link to the site."""
    detail = await render(TALK)
    assert detail.nodes("session.site") == []
    assert detail.nodes("session.image") == []
