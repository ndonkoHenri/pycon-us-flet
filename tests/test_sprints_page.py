"""Tests for the Sprints page's screen: its cards, filter, menu and states (#106).

EVT-05..08, D-46. The screen runs in a real Flet session (`tests/sessions.py`'s
`showing()`), as the Speakers list's does (`tests/test_speakers_screen.py`): a
keystroke is the field's value patched in and its change event dispatched, and a test
sees which card bodies ran (D-153). The harness and lookups are
`tests/sprints_page.py`'s; the query is `test_sprints.py`'s. How the cards look,
wrap at 200 % and read to TalkBack and VoiceOver is checked on devices (the PR).
"""

import asyncio
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any, cast

import flet as ft
import httpx
import pytest

from pycon_us.prefs import Prefs
from pycon_us.screens import sprints as screen
from pycon_us.services import api
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from tests import sprints_page, strip
from tests.fakes import MemoryLauncher, MemoryPrefs
from tests.feeds import recorded
from tests.sessions import menu_text
from tests.sprints_page import (
    ALL,
    CARD,
    DATA,
    INFO,
    YEAR,
    card_of,
    named,
    text_of,
    under,
    with_sprints,
    year_with,
)

FORM_URL = "https://example.org/2026/sprints/project/submit/"
"""A project form for 2026, whose own went with the live site (#824)."""

show, focused = sprints_page.show, sprints_page.focused
network, finished = strip.network, strip.finished


async def test_every_project_has_a_card_in_the_pages_order(show: Any) -> None:
    """Each project has a card in the page's order, named by a level-3 heading.

    The cards sit under one level-2 heading, "Projects".
    """
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
    """The dates line spans the sprint days, or names one, and is gone without any."""
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
    """A filter's matches are counted in a live region; no filter or a miss has none."""
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
    """A filter that finds nothing says so, and its button clears it.

    The field is emptied and takes the focus, and all 24 projects come back.
    """
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
    """A card's logo fits a white tile, with the initials when it cannot load."""
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
    """A card says "by" its submitter, and a project without one has no such line."""
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
    """A cut description's "More" shows it whole, as Markdown with its links.

    "Less" folds it back, and the toggle says which state it is in.
    """
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
    """A short description shows whole, with no line limit and no "More"."""
    short = named("PursuedPyBear")
    shown = await show(conference=with_sprints(short))
    (text,) = [t for t in shown.find(ft.Text) if t.value == short.description_text]
    assert text.max_lines is None  # never cut: whole at any text size
    assert shown.nodes("sprints.more.") == []


async def test_the_menu_opens_the_sprint_page_and_the_project_form(
    show: Any,
) -> None:
    """EVT-08: both from the year data, in the in-app browser."""
    shown = await show(year=year_with(sprint_submit_url=FORM_URL))
    (menu,) = shown.find(ft.PopupMenuButton)
    assert menu.tooltip == "More options"
    assert shown.node("sprints.menu").content is menu
    assert isinstance(shown.node("sprints.menu").parent, ft.MergeSemantics)  # D-190
    labels = [menu_text(item).value for item in menu.items]
    assert labels == ["Sprint info on us.pycon.org", screen.SUBMIT]
    assert [shown.node(f"sprints.{key}") for key in ("info", "submit")] == [
        item.content for item in menu.items
    ]
    for item in menu.items:
        title = cast(ft.ListTile, cast(ft.Semantics, item.content).content).title
        assert cast(ft.Semantics, title).link  # each one wraps (F47, D-233)
        assert str(menu_text(item).semantics_label).endswith("\nOpens in browser")
        await shown.click(item)
    assert shown.launched == [INFO.sprints_url, FORM_URL]


async def test_a_year_without_the_pages_has_no_menu(show: Any) -> None:
    """With neither sprint page there is no menu; with the form alone, it has that."""
    shown = await show(year=year_with(sprints_url="", sprint_submit_url=""))
    assert shown.find(ft.PopupMenuButton) == []
    only_form = await show(year=year_with(sprints_url="", sprint_submit_url=FORM_URL))
    (menu,) = only_form.find(ft.PopupMenuButton)
    assert [menu_text(item).value for item in menu.items] == [screen.SUBMIT]


async def test_2026_s_menu_has_the_info_page_alone_since_its_form_is_gone(
    show: Any,
) -> None:
    """The project form went with the live site, so no dead item for it (#824)."""
    shown = await show()
    (menu,) = shown.find(ft.PopupMenuButton)
    assert [menu_text(item).value for item in menu.items] == [
        "Sprint info on us.pycon.org"
    ]


async def test_no_projects_yet_offers_the_form_and_no_filter(show: Any) -> None:
    """With no projects there is no filter, and a button opens the project form.

    The sprint days still show; a year without the form has no button.
    """
    shown = await show(
        conference=with_sprints(), year=year_with(sprint_submit_url=FORM_URL)
    )
    assert shown.node("sprints.none").live_region
    assert shown.find(ft.TextField) == []  # nothing to filter
    assert shown.nodes("sprints.dates")  # the days are known all the same
    (button,) = shown.find(ft.FilledTonalButton)
    assert button.content == "Submit a project"
    await shown.click(button)
    assert shown.launched == [FORM_URL]
    without_form = await show(conference=with_sprints())  # 2026's, since #824
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


async def test_a_pull_on_the_list_refreshes_once_and_offline_keeps_the_projects(
    show: Any, network: strip.Network, finished: list[ft.RefreshIndicator]
) -> None:
    """EVT-07, D-449: the list pulls to refresh; a second pull joins the first.

    Offline, both spinners end, the projects stay, and only the status strip says
    so, with its "Offline" line and an enabled Refresh that runs the same refresh
    (the accessible way to the pull, D-32): no "Something went wrong".
    """
    shown = await show()
    (indicator,) = shown.find(ft.RefreshIndicator)
    assert isinstance(indicator.content, ft.ListView)
    assert indicator.expand  # the list's place in the body
    first = strip.pull(shown, indicator)
    await network.arrived.wait()
    second = strip.pull(shown, indicator)  # while the first runs
    await shown.settle()
    assert finished == []  # the spinner turns while the refresh runs
    network.error = api.NetworkError("ConnectError: offline")
    network.released.set()
    await asyncio.gather(first, second)

    assert network.requests == 1
    # Each pull's spinner ends, through the indicator the refresh's renders left (F299).
    (mounted,) = shown.find(ft.RefreshIndicator)
    assert finished == [mounted, mounted]
    assert shown.conference.problem == "offline"
    assert len(shown.listed) == 24
    assert shown.snack_bars == []
    assert any(text.startswith("Offline") for text in shown.texts())  # the strip's
    (button,) = [b for b in shown.find(ft.TextButton) if b.content == "Refresh"]
    assert not button.disabled
    await shown.click(button)
    assert network.requests == 2  # the pull's refresh, from the strip


@pytest.mark.parametrize("large_text", [False, True])
async def test_at_large_text_the_strip_and_the_field_scroll_with_the_list(
    show: Any, large_text: bool
) -> None:
    """Pinned over the list; at large text they head it (#649, D-449).

    Pinned, the two would take a third of the screen at the largest sizes.
    """
    offline = Conference(data=DATA, source="bundled", version=1, problem="offline")
    shown = await show(
        conference=offline, prefs=Prefs(loaded=True, time_above=large_text)
    )
    (text_field,) = shown.find(ft.TextField)
    (strip_line,) = shown.nodes("app.status")  # the strip shows offline
    for control in (text_field, strip_line):
        node = control.parent
        while node is not None and not isinstance(node, ft.ListView):
            node = node.parent
        assert (node is not None) is large_text
