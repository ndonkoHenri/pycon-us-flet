"""Tests for a keynote's and a panel's session detail (``screens/keynote_people.py``).

SESS-08, #104, D-217: the feed names a keynote by its speaker and links its description
to the site, so its detail shows the year data's people and abstract. ``SessionDetail``
runs in a real Flet session (``tests/session_detail.py``).
"""

from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path

import flet as ft
import pytest

from pycon_us.core.models import ConferenceData
from pycon_us.screens import session as screen
from pycon_us.year_keynotes import keynote_of
from tests import session_detail
from tests.feeds import processed
from tests.session_detail import TALK, YEAR, Detail, Render, headings, rendering
from tests.trees import descendants

KEYNOTES = YEAR.content.keynotes

LIN_QIAO = "153"
"""A keynote by one speaker, with its own title and an abstract."""

AMANDA = "176"
"""A keynote whose talk has no title of its own."""

TOGETHER = "182"
"""A joint keynote: Rachell Calhoun & Tim Schilling."""

COUNCIL = "183"
"""The Steering Council panel: five people without a bio."""


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Yield a function that renders the detail of the session with a given id."""
    async with rendering(tmp_path, monkeypatch) as show:
        yield show


def person(detail: Detail, number: int) -> list[str]:
    """What a person's row shows after the photo's initials: the name and the role."""
    initials, *shown = detail.text(f"session.person.{number}")
    assert len(initials) <= 2 and initials.isupper()
    return shown


def about(detail: Detail) -> str:
    """The About section's Markdown."""
    (found,) = [
        n
        for n in descendants(detail.node("session.description"))
        if isinstance(n, ft.Markdown)
    ]
    return found.value


async def test_a_keynote_shows_its_speaker_with_role_and_bio(render: Render) -> None:
    """A keynote shows its speaker's name, role, photo and whole bio, from year data."""
    keynote = keynote_of(KEYNOTES, LIN_QIAO)
    assert keynote is not None
    detail = await render(LIN_QIAO)
    (lin,) = keynote.speakers
    assert person(detail, 0) == [lin.name, lin.role]
    # Name and role are one stop; the photo is decorative, its initials unread.
    node = detail.node("session.person.0")
    assert isinstance(node.parent, ft.MergeSemantics)
    (avatar,) = [n for n in descendants(node) if isinstance(n, ft.CircleAvatar)]
    assert avatar.foreground_image_src == lin.photo_url
    assert isinstance(avatar.parent, ft.Semantics) and avatar.parent.exclude_semantics
    # The whole bio: a detail page cuts nothing.
    (bio,) = [
        n for n in descendants(detail.node("session.bio.0")) if isinstance(n, ft.Text)
    ]
    assert (bio.value, bio.max_lines, bio.selectable) == (lin.bio, None, True)


async def test_the_abstract_replaces_the_feeds_link_under_the_talks_title(
    render: Render,
) -> None:
    """ux.md §5.5: Speakers, then About; the feed's description is only a link."""
    keynote = keynote_of(KEYNOTES, LIN_QIAO)
    assert keynote is not None
    detail = await render(LIN_QIAO)
    assert [h for h in headings(detail) if h[1] == 2] == [
        ("Speakers", 2),
        ("About", 2),
    ]
    assert detail.text("session.keynote_title") == [keynote.title]
    assert about(detail) == keynote.abstract
    assert "keynote-speakers" not in about(detail)


async def test_a_talk_without_a_title_of_its_own_shows_its_abstract(
    render: Render,
) -> None:
    """A keynote without a title of its own shows no title, but its abstract."""
    keynote = keynote_of(KEYNOTES, AMANDA)
    assert keynote is not None and not keynote.title
    detail = await render(AMANDA)
    assert detail.nodes("session.keynote_title") == []
    assert about(detail) == keynote.abstract


async def test_a_keynote_with_nothing_to_say_about_it_has_no_about_heading(
    render: Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No title, no abstract and an empty feed description: no heading over nothing."""
    keynote = keynote_of(KEYNOTES, LIN_QIAO)
    assert keynote is not None
    bare = replace(keynote, title="", abstract="")
    monkeypatch.setattr(screen, "keynote_of", lambda _keynotes, _id: bare)

    def without_description(year: int) -> ConferenceData:
        data = processed(year)
        sessions = dict(data.sessions)
        sessions[LIN_QIAO] = replace(sessions[LIN_QIAO], description_md="")
        return replace(data, sessions=sessions)

    monkeypatch.setattr(session_detail, "processed", without_description)
    detail = await render(LIN_QIAO)
    assert [h for h in headings(detail) if h[1] == 2] == [("Speakers", 2)]
    assert detail.nodes("session.description") == []


async def test_a_joint_keynote_lists_both_speakers_in_order(render: Render) -> None:
    """A joint keynote lists both its speakers in order, the second with a bio too."""
    detail = await render(TOGETHER)
    assert [person(detail, n)[0] for n in range(2)] == [
        "Rachell Calhoun",
        "Tim Schilling",
    ]
    assert len(detail.nodes("session.bio.1")) == 1


async def test_a_panel_lists_its_panelists_and_leaves_out_missing_bios(
    render: Render,
) -> None:
    """A panel lists its five people under "Panelists", with no empty bio."""
    keynote = keynote_of(KEYNOTES, COUNCIL)
    assert keynote is not None
    detail = await render(COUNCIL)
    assert ("Panelists", 2) in headings(detail)
    assert [person(detail, n)[0] for n in range(5)] == [
        p.name for p in keynote.speakers
    ]
    assert not any(detail.nodes(f"session.bio.{n}") for n in range(5))


async def test_a_session_without_keynote_data_keeps_the_feeds_speakers_and_text(
    render: Render,
) -> None:
    """A talk with no keynote data shows its feed text, no keynote people or title."""
    detail = await render(TALK)
    assert detail.nodes("session.person.0") == []
    assert detail.nodes("session.keynote_title") == []
    assert about(detail) == processed(2026).sessions[TALK].description_md
