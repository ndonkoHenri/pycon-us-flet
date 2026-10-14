"""Tests for the Sprints page: its query (``core/sprints.py``) and its screen (#106).

EVT-05..08, D-46. The query is pure and runs on the recorded 2026 feed (2025's has no
sprint projects) and on projects built from it: the page's order, the all-words filter
over text that never holds markup, and when a card cuts its description. The screen runs
in a real Flet session (``tests/sessions.py``'s ``showing()``), as the Speakers list's
does (``tests/test_speakers.py``): a
keystroke is the field's value patched in and its change event dispatched, and a test
sees which card bodies ran (D-153). How the cards look, wrap at 200 % and read to
TalkBack and VoiceOver is checked on devices (the PR).
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any, cast

import flet as ft
import httpx
import pytest

from pycon_us.config import YearData, load_year
from pycon_us.core.html_md import to_text
from pycon_us.core.models import ConferenceData, Sprint
from pycon_us.core.queries import fold
from pycon_us.core.sprints import PREVIEW_CHARS, cut_short, filter_projects, projects
from pycon_us.screens import sprint_card
from pycon_us.screens import sprints as screen
from pycon_us.screens import tracks as hub_screen
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from tests import sessions
from tests.fakes import MemoryLauncher, MemoryPrefs
from tests.feeds import processed, recorded

YEAR = load_year(2026)
INFO = YEAR.conference
DATA = processed(2026)
ALL = projects(DATA)
CARD = "sprints.project."
"""The prefix of a card's name heading's semantics identifier."""


def named(name: str) -> Sprint:
    (found,) = [sprint for sprint in ALL if sprint.name == name]
    return found


def names(listed: tuple[Sprint, ...]) -> list[str]:
    return [sprint.name for sprint in listed]


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
    short = named("PursuedPyBear")
    assert cut_short(replace(short, description_text="x" * (PREVIEW_CHARS + 1)))
    assert cut_short(replace(short, description_md="See [docs](https://ppb.dev/)."))
    assert cut_short(replace(short, description_md="One.\n\nTwo."))
    assert sum(not cut_short(sprint) for sprint in ALL) == 5


# ------------------------------------------------------------------ the screen


@dataclass
class Shown(sessions.Shown):
    """The harness's ``Shown`` (``tests/sessions.py``), and which cards ran."""

    cards: list[str] = field(default_factory=list)
    """The project ids whose card bodies ran, in order."""

    @property
    def listed(self) -> list[str]:
        """The project ids of the cards on screen, in order."""
        return [str(n.identifier).removeprefix(CARD) for n in self.nodes(CARD)]

    @property
    def launched(self) -> list[str]:
        return [url for url, _ in self.launcher.launched]

    async def type(self, text: str) -> None:
        """Type into the filter as Flutter reports it: the value, then the event."""
        (text_field,) = self.find(ft.TextField)
        self.session.apply_patch(text_field._i, {"value": text})
        await self.event(text_field, "change", None)


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Any]:
    """Return show(screen, conference=..., year=...): that screen over the feed."""
    counted = sprint_card.cut_short

    def cut(sprint: Sprint) -> bool:
        sessions.current(Shown).cards.append(sprint.id)
        return counted(sprint)

    # Each card body asks once: counting the calls counts the bodies (S2).
    monkeypatch.setattr(sprint_card, "cut_short", cut)

    async with AsyncExitStack() as stack:

        async def render(
            component: Any = screen.Sprints,
            conference: Conference | None = None,
            year: YearData = YEAR,
        ) -> Shown:
            return await stack.enter_async_context(
                sessions.showing(
                    component,
                    screen,
                    hub_screen,
                    year=year,
                    conference=Conference(data=DATA, source="bundled", version=1)
                    if conference is None
                    else conference,
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path="",  # no Router: what ft.use_view_path() says outside one
                    kind=Shown,
                )
            )

        yield render


@pytest.fixture
def focused(monkeypatch: pytest.MonkeyPatch) -> list[ft.TextField]:
    """The fields asked to take the focus; the harness has no Flutter to answer."""
    asked: list[ft.TextField] = []

    async def focus(self: ft.TextField) -> None:
        asked.append(self)

    monkeypatch.setattr(ft.TextField, "focus", focus)
    return asked


def year_with(**changes: Any) -> YearData:
    return replace(YEAR, conference=replace(INFO, **changes))


def with_sprints(*sprints: Sprint) -> Conference:
    return Conference(data=replace(DATA, sprints=sprints), source="bundled", version=1)


def text_of(control: object) -> str:
    """The first ``Text`` value under ``control``, following ``content``."""
    while control is not None and not isinstance(control, ft.Text):
        control = getattr(control, "content", None)
    return str(control.value) if control is not None else ""


def card_of(shown: Shown, sprint: Sprint) -> ft.Card:
    heading: ft.BaseControl | None = shown.node(f"{CARD}{sprint.id}")
    while heading is not None and not isinstance(heading, ft.Card):
        heading = heading.parent
    assert isinstance(heading, ft.Card)
    return heading


def under(control: ft.BaseControl, root: ft.BaseControl) -> bool:
    node: ft.BaseControl | None = control
    while node is not None:
        if node is root:
            return True
        node = node.parent
    return False


async def test_every_project_has_a_card_in_the_pages_order(show: Any) -> None:
    shown = await show()
    assert shown.listed == [sprint.id for sprint in ALL]
    assert sorted(shown.cards) == sorted(sprint.id for sprint in ALL)
    for node in shown.nodes(CARD):  # a screen reader goes card by card (F40)
        assert node.header and node.heading_level == 3
    heading = [n for n in shown.find(ft.Semantics) if n.header and n.heading_level == 2]
    assert [text_of(n) for n in heading] == ["Projects"]


async def test_the_page_says_when_the_sprints_are_from_the_year_data(
    show: Any,
) -> None:
    shown = await show()
    dates = shown.node("sprints.dates")
    assert dates.label == "Sprints: Monday, May 18 to Tuesday, May 19"
    assert "Mon, May 18 – Tue, May 19" in shown.texts()
    one_day = await show(year=year_with(last_day=date(2026, 5, 18)))
    assert one_day.node("sprints.dates").label == "Sprints: Monday, May 18"
    none = await show(year=year_with(last_day=INFO.last_talk_day))
    assert none.nodes("sprints.dates") == []


async def test_a_keystroke_re_renders_no_card_that_stays(show: Any) -> None:
    """D-153: the cards found are the same objects, so their bodies are skipped."""
    shown = await show()
    shown.cards.clear()
    await shown.type("django")
    assert shown.listed == [named("Django").id, named("Djangonaut Space").id, "7"]
    assert shown.cards == []
    await shown.type("django ")  # the same projects: nothing re-renders
    assert shown.cards == []


async def test_a_filter_says_how_many_it_found_in_a_live_region(show: Any) -> None:
    shown = await show()
    assert shown.nodes("sprints.count") == []  # no filter: nothing to count
    await shown.type("django")
    (count,) = shown.nodes("sprints.count")
    assert count.live_region and text_of(count) == "3 projects"
    await shown.type("mentorship django")
    assert text_of(shown.node("sprints.count")) == "1 project"
    await shown.type("zzz")  # a miss: the no-match state announces itself
    assert shown.nodes("sprints.count") == []


async def test_a_filter_that_finds_nothing_offers_to_clear_it(
    show: Any, focused: list[ft.TextField]
) -> None:
    shown = await show()
    await shown.type("zzz")
    assert shown.listed == []
    assert shown.node("sprints.no_match").live_region
    assert (
        "No projects match \N{LEFT DOUBLE QUOTATION MARK}zzz\N{RIGHT DOUBLE QUOTATION MARK}"
        in (shown.texts())
    )
    (button,) = shown.find(ft.FilledTonalButton)
    assert button.content == screen.CLEAR_FILTER
    await shown.click(button)
    assert len(shown.listed) == 24
    (text_field,) = shown.find(ft.TextField)
    assert text_field.value == ""
    assert [f._i for f in focused] == [text_field._i]  # the button went: the field


async def test_a_card_shows_the_logo_on_a_white_tile_over_the_initials(
    show: Any,
) -> None:
    shown = await show()
    arcade = card_of(shown, named("Arcade"))
    # Not one node: TalkBack read "by Darren" and the text before the name heading.
    assert arcade.semantic_container is False
    (image,) = [i for i in shown.find(ft.Image) if under(i, arcade)]
    assert image.src == named("Arcade").logo_url
    assert image.fit == ft.BoxFit.CONTAIN
    # When it cannot load (offline), the initials take its place.
    assert isinstance(image.error_content, ft.CircleAvatar)
    assert text_of(image.error_content) == "A"
    tile = cast(ft.Container, image.parent)
    assert tile.bgcolor == ft.Colors.WHITE


async def test_a_project_without_a_logo_shows_its_initials(show: Any) -> None:
    """Two 2026 projects have none (DATA-24)."""
    cuda = named("CUDA Python")
    assert cuda.logo_url is None
    shown = await show()
    card = card_of(shown, cuda)
    assert [i for i in shown.find(ft.Image) if under(i, card)] == []
    (avatar,) = [a for a in shown.find(ft.CircleAvatar) if under(a, card)]
    assert text_of(avatar) == "CP"


async def test_a_card_says_who_signed_the_project_up_when_the_feed_does(
    show: Any,
) -> None:
    arcade = named("Arcade")
    anonymous = replace(named("Pallets"), submitter="")
    shown = await show(conference=with_sprints(arcade, anonymous))
    assert "by Darren" in shown.texts()
    card = card_of(shown, anonymous)
    texts = [str(t.value) for t in shown.find(ft.Text) if under(t, card)]
    assert "Pallets" in texts
    assert not any(text.startswith("by ") for text in texts)


async def test_project_page_opens_the_feeds_url_as_a_web_page(show: Any) -> None:
    """D-197's rule: "documentdb.io" is a web address written without its scheme."""
    shown = await show(conference=with_sprints(named("DocumentDB"), named("Arcade")))
    page = shown.node(f"sprints.project_page.{named('DocumentDB').id}")
    assert isinstance(page.parent, ft.MergeSemantics)
    button = cast(ft.Semantics, page.content).content
    assert isinstance(button, ft.TextButton) and button.icon == ft.Icons.OPEN_IN_NEW
    assert cast(ft.Semantics, page.content).link
    label = cast(ft.Text, button.content).semantics_label
    assert label == "DocumentDB project page\nOpens in browser"
    await shown.click(button)
    assert shown.launched == ["https://documentdb.io"]
    launcher = cast(MemoryLauncher, shown.services.launcher)
    assert launcher.launched[0][1] == ft.LaunchMode.IN_APP_BROWSER_VIEW


async def test_a_url_that_names_no_web_page_leaves_no_project_page(show: Any) -> None:
    """No dead control (ux.md §1): a word or another scheme opens nothing."""
    odd = replace(named("Pallets"), url="see our wiki")
    shown = await show(conference=with_sprints(odd))
    assert shown.nodes("sprints.project_page.") == []


async def test_more_shows_the_whole_description_with_its_links(show: Any) -> None:
    beeware = named("BeeWare")
    shown = await show(conference=with_sprints(beeware))
    card = card_of(shown, beeware)
    (preview,) = [t for t in shown.find(ft.Text) if t.value == beeware.description_text]
    assert preview.max_lines == 4 and under(preview, card)
    more = shown.node(f"sprints.more.{beeware.id}")
    toggle = cast(ft.Semantics, more.content)
    assert toggle.expanded is False  # said "collapsed"
    button = cast(ft.TextButton, toggle.content)
    assert text_of(button) == "More"
    # The visible word first (WCAG 2.5.3), and it follows the state.
    assert cast(ft.Text, button.content).semantics_label == "More about BeeWare"

    await shown.click(button)
    (markdown,) = shown.find(ft.Markdown)
    assert markdown.value == beeware.description_md and markdown.selectable
    assert "](https://beeware.org/contributing/challenge-coins/)" in markdown.value
    toggle = cast(ft.Semantics, shown.node(f"sprints.more.{beeware.id}").content)
    assert toggle.expanded is True
    assert text_of(toggle.content) == "Less"
    less = cast(ft.TextButton, toggle.content)
    assert cast(ft.Text, less.content).semantics_label == "Less about BeeWare"
    await shown.click(less)
    assert shown.find(ft.Markdown) == []


async def test_a_short_description_has_no_more(show: Any) -> None:
    short = named("PursuedPyBear")
    shown = await show(conference=with_sprints(short))
    (text,) = [t for t in shown.find(ft.Text) if t.value == short.description_text]
    assert text.max_lines is None  # never cut: whole at any text size
    assert shown.nodes("sprints.more.") == []


async def test_the_menu_opens_the_sprint_page_and_the_project_form(
    show: Any,
) -> None:
    """EVT-08: both from the year data, in the in-app browser."""
    shown = await show()
    (menu,) = shown.find(ft.PopupMenuButton)
    assert menu.tooltip == "More options"
    assert shown.node("sprints.menu").content is menu
    assert isinstance(shown.node("sprints.menu").parent, ft.MergeSemantics)  # D-190
    labels = [text_of(item.content) for item in menu.items]
    assert labels == ["Sprint info on us.pycon.org", screen.SUBMIT]
    for item in menu.items:
        semantics = cast(ft.Semantics, item.content)
        assert semantics.link
        assert str(cast(ft.Text, semantics.content).semantics_label).endswith(
            "\nOpens in browser"
        )
        await shown.click(item)
    assert shown.launched == [INFO.sprints_url, INFO.sprint_submit_url]


async def test_a_year_without_the_pages_has_no_menu(show: Any) -> None:
    shown = await show(year=year_with(sprints_url="", sprint_submit_url=""))
    assert shown.find(ft.PopupMenuButton) == []
    only_form = await show(year=year_with(sprints_url=""))
    (menu,) = only_form.find(ft.PopupMenuButton)
    assert [text_of(item.content) for item in menu.items] == [screen.SUBMIT]


async def test_no_projects_yet_offers_the_form_and_no_filter(show: Any) -> None:
    shown = await show(conference=with_sprints())
    assert shown.node("sprints.none").live_region
    assert shown.find(ft.TextField) == []  # nothing to filter
    assert shown.nodes("sprints.dates")  # the days are known all the same
    (button,) = shown.find(ft.FilledTonalButton)
    assert button.content == "Submit a project"
    await shown.click(button)
    assert shown.launched == [INFO.sprint_submit_url]
    without_form = await show(
        conference=with_sprints(), year=year_with(sprint_submit_url="")
    )
    assert without_form.find(ft.FilledTonalButton) == []


async def test_without_data_the_page_loads_then_offers_to_try_again(
    show: Any,
) -> None:
    """ux.md §4.1: the skeleton until the first fetch has failed, then the way out."""
    loading = await show(conference=Conference())
    assert "Loading sprint projects" in [n.label for n in loading.find(ft.Semantics)]
    failed = await show(conference=Conference(problem="offline"))
    assert failed.node("sprints.no_data").live_region
    assert [b.content for b in failed.find(ft.FilledTonalButton)] == ["Try again"]


async def test_a_failed_refresh_keeps_the_projects_and_the_cache(
    show: Any, tmp_path: Path
) -> None:
    """EVT-07, D-145: Ionic's refresh could wipe the only offline copy; ours never."""
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    assert await storage.write_feed(recorded(2026))
    conference = Conference()
    await conference.load_local(storage, YEAR)
    shown = await show(conference=conference)
    assert len(shown.listed) == 24

    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    await conference.refresh(storage, YEAR, transport=httpx.MockTransport(offline))
    await shown.settle()

    assert conference.problem == "offline"
    assert len(shown.listed) == 24
    assert storage.feed_path.read_bytes() == recorded(2026)


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
    data: ConferenceData = replace(DATA, sprints=())
    shown = await show(
        hub_screen.Tracks,
        conference=Conference(data=data, version=1),
        year=year_with(last_day=INFO.last_talk_day),
    )
    assert shown.nodes("tracks.sprints") == []


def test_the_sprints_row_says_what_it_knows() -> None:
    assert hub_screen.sprints_marks(INFO, 24) == (
        "May 18–19 · 24 projects",
        "May 18 to 19, 24 projects",
    )
    assert hub_screen.sprints_marks(INFO, 1)[0] == "May 18–19 · 1 project"
    assert hub_screen.sprints_marks(INFO, 0) == ("May 18–19", "May 18 to 19")
    no_days = replace(INFO, last_day=INFO.last_talk_day)
    assert hub_screen.sprints_marks(no_days, 2) == ("2 projects", "2 projects")
    assert hub_screen.sprints_marks(no_days, 0) == ("", "")
