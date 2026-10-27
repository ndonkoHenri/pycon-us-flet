"""Tests for session detail's speakers and description (SESS-06, -07; ux.md §5.5).

The header and When and where are ``test_session.py``'s.

``SessionDetail`` runs in a real Flet session (``tests/session_detail.py``), as the
rows do in ``test_session_rows.py``. How the screen looks, at 200 % text and in dark
mode, is checked on devices (the PR); here, what it says and what a tap does.
"""

from dataclasses import replace
from typing import cast

import flet as ft

from pycon_us.core.models import ConferenceData
from tests import session_detail
from tests.feeds import processed
from tests.session_detail import (
    BREAK,
    LIGHTNING,
    OPEN_SPACE,
    PANEL,
    TALK,
    VIEW,
    WELCOME,
    Detail,
    Render,
    headings,
    words,
)
from tests.trees import descendants

# The detail's fixture, shared by name: pytest finds fixtures among a module's names.
render = session_detail.render

# ------------------------------------------------------------------ speakers (SESS-07)


def speaker_rows(detail: Detail) -> list[ft.Semantics]:
    """Return the detail's speaker rows, the nodes named ``session.speaker.<id>``."""
    return [
        node
        for node in detail.session.index.values()
        if isinstance(node, ft.Semantics)
        and (node.identifier or "").startswith("session.speaker.")
    ]


async def test_a_speaker_s_row_pushes_their_page_one_level_up(render: Render) -> None:
    """A speaker's row reads their initials and name, and pushes their page."""
    detail = await render(TALK)
    (row,) = speaker_rows(detail)
    assert row.identifier == "session.speaker.150"
    assert words(row) == ["JL", "Justin Lee"]  # the avatar's initials, then the name
    tile = next(n for n in descendants(row) if isinstance(n, ft.ListTile))
    await detail.click(tile)
    assert detail.pushed == [f"{VIEW}/speaker/150"]


async def test_the_speakers_come_in_the_feed_s_order_with_their_photos(
    render: Render,
) -> None:
    """The speakers come in the feed's order, with their photos or else initials."""
    detail = await render(PANEL)
    session = processed(2026).sessions[PANEL]
    rows = speaker_rows(detail)
    assert [words(row)[1] for row in rows] == list(session.speaker_names)
    avatars = [
        next(n for n in descendants(row) if isinstance(n, ft.CircleAvatar))
        for row in rows
    ]
    # A speaker without a photo shows their initials alone, with no empty request.
    missing = [a for a in avatars if a.foreground_image_src is None]
    assert len(missing) == 5
    assert all(isinstance(a.content, ft.Text) and a.content.value for a in missing)


async def test_a_pseudo_speaker_is_plain_text_that_nothing_taps(
    render: Render,
) -> None:
    """D-125: "Hosted by …" is no person with a page (DATA-15)."""
    detail = await render(LIGHTNING)
    assert speaker_rows(detail) == []
    # Its own node, not merged into the "Speakers" heading (seen on Android).
    node = detail.node("session.name.0")
    assert node.container
    assert words(node) == ["Hosted by Abigail, Chris, Cristián, and Lorena"]
    holder: object = node
    while isinstance(holder, ft.Control):
        assert getattr(holder, "on_click", None) is None, holder
        holder = holder.parent


async def test_names_with_no_speaker_each_get_an_identifier_in_the_authors_order(
    render: Render,
) -> None:
    """D-197: two free names must not share one node id (a UI test finds each)."""
    detail = await render(PANEL)
    data = cast(ConferenceData, detail.conference.data)
    ana = data.speakers[data.sessions[PANEL].speaker_ids[0]]
    session = replace(
        data.sessions[PANEL],
        speaker_ids=(ana.id,),
        speaker_names=("Hosted by the PSF", ana.name, "A. Guest"),
    )
    newer = replace(data, sessions={**data.sessions, PANEL: session})
    detail.conference.data, detail.conference.version = newer, 2
    await detail.settle()
    assert words(detail.node("session.name.0")) == ["Hosted by the PSF"]
    assert words(detail.node("session.name.1")) == ["A. Guest"]
    assert [row.identifier for row in speaker_rows(detail)] == [
        f"session.speaker.{ana.id}"
    ]
    # In the authors' order, read down the section: a name, the speaker, a name.
    section = detail.node("session.name.0").parent
    assert isinstance(section, ft.Column)
    order = [
        node.identifier
        for node in descendants(section)
        if isinstance(node, ft.Semantics)
        and (node.identifier or "").startswith(("session.name.", "session.speaker."))
    ]
    assert order == ["session.name.0", f"session.speaker.{ana.id}", "session.name.1"]


async def test_a_session_without_speakers_has_no_speakers_section(
    render: Render,
) -> None:
    """A session without speakers has no speaker rows and no Speakers heading."""
    detail = await render(WELCOME)
    assert speaker_rows(detail) == []
    assert all(text != "Speakers" for text, _ in headings(detail))


# ------------------------------------------------------------------ about (SESS-06)


def markdown(detail: Detail) -> ft.Markdown:
    """Return the one ``Markdown`` control in the detail's description."""
    (found,) = [
        n
        for n in descendants(detail.node("session.description"))
        if isinstance(n, ft.Markdown)
    ]
    return found


async def test_the_description_follows_the_speakers_under_its_own_heading(
    render: Render,
) -> None:
    """ux.md §5.5: speakers, then About, each a level-2 section."""
    detail = await render(TALK)
    assert [h for h in headings(detail) if h[1] == 2] == [
        ("Speakers", 2),
        ("About", 2),
    ]
    text = markdown(detail)
    assert text.value == processed(2026).sessions[TALK].description_md
    assert text.selectable


async def test_a_link_in_a_description_opens_in_the_in_app_browser(
    render: Render,
) -> None:
    """A description's link opens in the in-app browser, with ``https://`` added."""
    detail = await render(OPEN_SPACE)
    text = markdown(detail)
    assert "[pytest](pytest.org)" in text.value
    await detail.session.dispatch_event(text._i, "tap_link", "pytest.org")
    await detail.settle()
    assert detail.launcher.launched == [
        ("https://pytest.org", ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]
    assert detail.pushed == []


async def test_a_session_without_a_description_has_no_about(render: Render) -> None:
    """A session without a description has no description and no About heading."""
    detail = await render(BREAK)
    assert detail.nodes("session.description") == []
    assert all(text != "About" for text, _ in headings(detail))
