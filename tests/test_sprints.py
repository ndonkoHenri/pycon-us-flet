"""Tests for the Sprints query (``core/sprints.py``) and the Tracks hub's row (#106).

EVT-05..08, D-46. The query is pure and runs on the recorded 2026 feed (2025's has no
sprint projects) and on projects built from it: the page's order, the all-words filter
over text that never holds markup, and when a card cuts its description. The screen is
``test_sprints_page.py``'s; both take the harness and lookups from
``tests/sprints_page.py``.
"""

from dataclasses import replace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.core.html_md import to_text
from pycon_us.core.models import ConferenceData
from pycon_us.core.queries import fold
from pycon_us.core.sprints import PREVIEW_CHARS, cut_short, filter_projects
from pycon_us.screens import tracks as hub_screen
from pycon_us.state import Conference
from tests import sprints_page
from tests.sprints_page import (
    ALL,
    DATA,
    INFO,
    named,
    names,
    text_of,
    year_with,
)

show = sprints_page.show

# ------------------------------------------------------------------ the data


def test_each_project_has_its_description_text_and_a_folded_search_text() -> None:
    """D-140's rule for sessions, for the sprints: converted once, at processing."""
    assert len(DATA.sprints) == 24
    for sprint in DATA.sprints:
        text = to_text(sprint.description)
        assert sprint.description_text == text
        assert sprint.search_text == fold(f"{sprint.name} {sprint.submitter} {text}")


def test_the_search_text_never_holds_markup() -> None:
    """D-46: BeeWare's description links its challenge coins; only the words count."""
    beeware = named("BeeWare")
    assert 'href="https://beeware.org/contributing/challenge-coins/"' in (
        beeware.description
    )
    assert "challenge coin" in beeware.search_text
    for sprint in DATA.sprints:
        for markup in ("<", "href", "](", "challenge-coins"):
            assert markup not in sprint.search_text, sprint.name


# ------------------------------------------------------------------ the query


def test_projects_are_listed_by_name_as_people_read_it() -> None:
    """D-46's fold: the feed puts lower-case names last; here conda is among the Cs."""
    assert len(ALL) == 24
    assert names(ALL)[:9] == [
        "aio-libs: aiohttp and the ecosystem",
        "Arcade",
        "BeeWare",
        "Civic Data Tech",
        "CivicBand",
        "Cloud Custodian",
        "conda",
        "CPython",
        "CUDA Python",
    ]
    assert [fold(name) for name in names(ALL)] == sorted(fold(n) for n in names(ALL))


def test_the_filter_needs_every_word_in_any_order() -> None:
    """EVT-06: all words must match (AND), unlike Ionic's schedule search (OR)."""
    assert names(filter_projects(ALL, "mentorship django")) == ["Djangonaut Space"]
    assert names(filter_projects(ALL, "flask quart")) == ["Pallets"]
    assert filter_projects(ALL, "web python") == filter_projects(ALL, "python web")
    assert names(filter_projects(ALL, "game python")) == ["Arcade"]
    assert filter_projects(ALL, "flask django") == ()


def test_the_filter_matches_the_submitter_and_ignores_case_and_accents() -> None:
    """The filter matches a submitter's name, whatever its case and accents."""
    assert names(filter_projects(ALL, "antonia")) == ["ScanAPI"]  # Maria Antônia
    assert names(filter_projects(ALL, "ANTÔNIA")) == ["ScanAPI"]
    assert "Djangonaut Space" in names(filter_projects(ALL, "tim"))


def test_the_filter_ignores_markup() -> None:
    """Ionic matched raw HTML: "href" found every project with a link."""
    assert names(filter_projects(ALL, "challenge coin")) == ["BeeWare"]
    for markup in ("href", "challenge-coins", "beeware.org/contributing", "<a"):
        assert filter_projects(ALL, markup) == (), markup


@pytest.mark.parametrize("query", ["", "   ", "\N{RIGHT SINGLE QUOTATION MARK}"])
def test_a_filter_with_no_word_keeps_the_list_itself(query: str) -> None:
    """The same object, so the screen knows no filter applies (no count line)."""
    assert filter_projects(ALL, query) is ALL


def test_a_short_one_paragraph_description_shows_whole() -> None:
    """EVT-05: no "More" for what fits; never cut, so it shows whole at 200 % too."""
    short = named("PursuedPyBear")
    assert short.description_text == "Unbearably fun game development!"
    assert not cut_short(short)
    assert not cut_short(replace(short, description_text="x" * PREVIEW_CHARS))


def test_a_long_description_or_one_with_links_or_paragraphs_is_cut() -> None:
    """A description over the preview's length, with a link or in two paragraphs is cut.

    Five of the 2026 projects are not cut.
    """
    short = named("PursuedPyBear")
    assert cut_short(replace(short, description_text="x" * (PREVIEW_CHARS + 1)))
    assert cut_short(replace(short, description_md="See [docs](https://ppb.dev/)."))
    assert cut_short(replace(short, description_md="One.\n\nTwo."))
    assert sum(not cut_short(sprint) for sprint in ALL) == 5


# ------------------------------------------------------------------ the Tracks hub


async def test_the_tracks_hub_ends_community_with_a_sprints_row(show: Any) -> None:
    """Sprints are not a feed track (D-126), but a way to take part (#106)."""
    shown = await show(hub_screen.Tracks)
    rows = shown.nodes("tracks.")
    assert str(rows[-1].identifier) == "tracks.sprints"
    node = shown.node("tracks.sprints")
    assert node.button and node.exclude_semantics
    assert node.label == (
        f"Sprints. {hub_screen.SPRINTS_LEGEND}. May 18 to 19, 24 projects."
    )
    assert "May 18–19 · 24 projects" in shown.texts()
    await shown.click(cast(ft.Control, node.parent))
    assert shown.went == ["/more/tracks/sprints"]  # under the hub, Back returns to it


async def test_the_sprints_row_keeps_its_community_heading(show: Any) -> None:
    """A year whose community tracks have no sessions still heads the row."""
    sessions = {
        k: s
        for k, s in DATA.sessions.items()
        if s.track not in {"Open Space", "Summit", "Event"}
    }
    data = replace(DATA, sessions=sessions)
    shown = await show(hub_screen.Tracks, conference=Conference(data=data, version=1))
    headings = [text_of(n) for n in shown.find(ft.Semantics) if n.header]
    assert headings == ["Presentations", "Hands-on", "Community"]
    assert shown.nodes("tracks.sprints")


async def test_a_year_without_sprints_has_no_sprints_row(show: Any) -> None:
    """Without projects or sprint days, the Tracks hub has no Sprints row."""
    data: ConferenceData = replace(DATA, sprints=())
    shown = await show(
        hub_screen.Tracks,
        conference=Conference(data=data, version=1),
        year=year_with(last_day=INFO.last_talk_day),
    )
    assert shown.nodes("tracks.sprints") == []


def test_the_sprints_row_says_what_it_knows() -> None:
    """The Sprints row gives its days and project count, either alone, or nothing."""
    assert hub_screen.sprints_marks(INFO, 24) == (
        "May 18–19 · 24 projects",
        "May 18 to 19, 24 projects",
    )
    assert hub_screen.sprints_marks(INFO, 1)[0] == "May 18–19 · 1 project"
    assert hub_screen.sprints_marks(INFO, 0) == ("May 18–19", "May 18 to 19")
    no_days = replace(INFO, last_day=INFO.last_talk_day)
    assert hub_screen.sprints_marks(no_days, 2) == ("2 projects", "2 projects")
    assert hub_screen.sprints_marks(no_days, 0) == ("", "")
