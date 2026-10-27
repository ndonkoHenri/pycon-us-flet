"""Tests for the Speakers screen's headings, rows, taps and states without data (#98).

The screen runs in ``tests/speakers_view.py``'s harness.
"""

from dataclasses import replace
from typing import cast

import flet as ft

from pycon_us.core.speakers import initials, letter_groups
from pycon_us.screens import speakers as screen
from pycon_us.state import Conference
from pycon_us.ui.rows import speaker_phrase
from tests import speakers_view
from tests.feeds import processed
from tests.speakers_view import ALL, ROW, Render, Shown, _under

render, shown = (speakers_view.render, speakers_view.shown)


async def test_each_letter_is_a_heading_node_of_its_own(shown: Shown) -> None:
    """Each letter is a heading inside a container node of its own, one per group.

    D-33: headings let screen readers jump letter by letter; a node of its own keeps
    the heading's focus on the letter, not on its whole section.
    """
    headings = [s for s in shown.find(ft.Semantics) if s.header]
    assert len(headings) == len(letter_groups(ALL))
    for heading in headings:
        wrapper = heading.parent
        assert isinstance(wrapper, ft.Semantics) and wrapper.container


async def test_a_row_is_one_button_read_as_its_phrase(shown: Shown) -> None:
    """A speaker row is one merged button node that reads its phrase alone."""
    (mike,) = [e for e in ALL if e.speaker.name == "Mike Müller"]
    node = shown.node(f"speakers.speaker.{mike.speaker.id}")
    assert node.label == speaker_phrase(mike)
    assert node.button
    assert node.exclude_semantics  # the texts and initials are not read again
    tap = node.parent
    assert isinstance(tap, ft.Container) and tap.on_click is not None
    assert isinstance(tap.parent, ft.MergeSemantics)


async def test_a_row_shows_the_photo_over_the_initials(shown: Shown) -> None:
    """Each row's avatar shows the speaker's initials under their photo, if any."""
    by_id = {e.speaker.id: e for e in ALL}
    avatars = [a for a in shown.find(ft.CircleAvatar) if a.parent is not None]
    assert len(avatars) == len(ALL)
    with_photo = [a for a in avatars if a.foreground_image_src]
    assert with_photo  # the public feed has photos for most speakers
    for avatar in avatars:
        row = avatar
        while not (
            isinstance(row, ft.Semantics)
            and str(row.identifier).startswith("speakers.")
        ):
            row = cast(ft.Control, row.parent)
        speaker = by_id[str(row.identifier).removeprefix("speakers.speaker.")].speaker
        assert cast(ft.Text, avatar.content).value == initials(speaker.name)
        assert avatar.foreground_image_src == (speaker.photo_url or None)
        assert avatar.bgcolor == ft.Colors.PRIMARY_CONTAINER  # a tested pair (theme)
        assert avatar.color == ft.Colors.ON_PRIMARY_CONTAINER


async def test_a_row_with_more_sessions_says_so_after_the_first(shown: Shown) -> None:
    """A row with more sessions puts "+1 more" on a line of its own, below its title.

    The title stops at two lines, so it never cuts the count.
    """
    (entry,) = [e for e in ALL if e.speaker.name == "Catherine Nelson"]
    assert entry.first_session is not None and entry.more == 1
    node = shown.node(f"speakers.speaker.{entry.speaker.id}")
    texts = [
        str(t.value)
        for t in shown.find(ft.Text)
        if _under(t, node) and t.parent is not None
    ]
    title, more = texts[-2:]
    assert title == entry.first_session.name
    assert more == "+1\N{NO-BREAK SPACE}more"  # its own line, never cut by the title
    (title_text,) = [
        t for t in shown.find(ft.Text) if t.value == title and _under(t, node)
    ]
    assert title_text.max_lines == 2


async def test_a_tap_pushes_the_speakers_detail(shown: Shown) -> None:
    """A tap on a row pushes that speaker's detail, one drill level down."""
    went = shown.went  # what page.navigate was asked for
    entry = ALL[0]
    node = shown.node(f"{ROW}{entry.speaker.id}")
    await shown.click(cast(ft.Control, node.parent))
    assert len(went) == 1
    assert went[0].endswith(f"/speaker/{entry.speaker.id}")  # one drill level


async def test_without_data_the_skeleton_shows_until_the_first_fetch_fails(
    render: Render,
) -> None:
    """ux.md §4.1, NEW-03: no data at all is the only time anything loads."""
    loading = await render(Conference())
    labels = [node.label for node in loading.find(ft.Semantics)]
    assert "Loading speakers" in labels
    assert loading.listed == []


async def test_after_a_failed_first_fetch_it_offers_to_try_again(
    render: Render,
) -> None:
    """After a failed first fetch, a live no-data state offers Try again."""
    failed = await render(Conference(problem="offline"))
    state = failed.node("speakers.no_data")
    assert state.live_region
    buttons = [b.content for b in failed.find(ft.FilledTonalButton)]
    assert buttons == ["Try again"]


async def test_a_feed_without_speakers_says_none_are_announced(
    render: Render,
) -> None:
    """Not a filter miss: nothing was filtered, so there is nothing to clear."""
    data = replace(processed(2026), speakers={})
    empty = await render(Conference(data=data, version=1))
    state = empty.node("speakers.not_announced")
    assert state.live_region
    titles = [str(t.value) for t in empty.find(ft.Text)]
    assert screen.NOT_ANNOUNCED in titles
    assert not any(t.startswith("No speakers match") for t in titles)
    assert empty.find(ft.FilledTonalButton) == []  # no Clear filter, no button


async def test_a_new_feed_version_rebuilds_the_list_and_its_filter(
    render: Render,
) -> None:
    """The memo keys on ``Conference.version``: a refresh must reach the list."""
    full = processed(2026)
    (mike,) = [e for e in ALL if e.speaker.name == "Mike Müller"]
    speakers = {k: v for k, v in full.speakers.items() if k != mike.speaker.id}
    conference = Conference(data=replace(full, speakers=speakers), version=1)
    refreshed = await render(conference)
    assert mike.speaker.id not in refreshed.listed
    await refreshed.type("mike müller")
    assert refreshed.listed == []

    conference.data = full  # as a refresh publishes it (Conference._publish)
    conference.version += 1
    await refreshed.settle()
    assert refreshed.listed == [mike.speaker.id]  # the new index finds him
    await refreshed.type("")
    assert mike.speaker.id in refreshed.listed
    assert len(refreshed.listed) == len(ALL)
