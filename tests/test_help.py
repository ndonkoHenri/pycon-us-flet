"""Tests for Help & safety (``/more/help``; INFO-07, INFO-11, D-281).

``Help`` runs outside a renderer: its services and ``AppScaffold`` are replaced, and a
fake page is bound as Flet binds a session's page; the contact rows' component body
runs inline over the same services, as ``test_rows.py`` runs it. What TalkBack and
VoiceOver read, and how the card looks at 200 % text, are checked on devices (the PR).
"""

import inspect
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest
from flet.components.component import Renderer

from pycon_us import prefs as prefs_module
from pycon_us.config import load_year
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import help as help_screen
from pycon_us.screens.help import Help, ReportProblem, contact_line, help_blocks
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from pycon_us.theme import LIGHT_TOKENS
from pycon_us.ui import info_page, rows
from pycon_us.ui.info_page import FeedBlock
from pycon_us.ui.links import OPENS_IN
from pycon_us.ui.share import LOG_SHARED, WITH_LOG
from pycon_us.year_info import SafetyContact
from pycon_us.year_map import MapData
from tests.fakes import (
    FakePage,
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPaths,
    MemoryPrefs,
    MemorySemantics,
    MemoryShare,
    bound,
    phone_margin,
)
from tests.test_about_app import (
    States,
    answer_report_hooks,
    headings,
    identified,
    text_of,
)

HOTLINE = SafetyContact(
    label="Call the Code of Conduct hotline",
    kind="tel",
    value="+15625550100",
    source="https://example.org/coc/",
    checked=date(2026, 10, 20),
)
"""A phone contact no year ships (the 2026 hotline is on no public page, D-45)."""

REPORT_PROBLEM_SECTION = ft.Container()
"""What ``ReportProblem`` renders as in the page's tests: its own tests are below."""


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """The session's services over in-memory fakes and the 2026 year data."""
    return Services(
        year=load_year(2026),
        storage=Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026),
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )


@pytest.fixture
def page(svc: Services, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakePage]:
    """A ``FakePage`` (iOS) bound, with the contact rows' body inline over ``svc``."""
    monkeypatch.setattr(
        rows, "_ExternalLinkTile", inspect.unwrap(rows._ExternalLinkTile)
    )
    monkeypatch.setattr(rows, "use_services", lambda: svc)
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch, page: FakePage
) -> Callable[[Services], dict[str, Any]]:
    """Render ``Help`` once over the given services and return its scaffold's kwargs."""
    monkeypatch.setattr(help_screen, "AppScaffold", lambda **kwargs: kwargs)
    monkeypatch.setattr(help_screen, "ReportProblem", lambda: REPORT_PROBLEM_SECTION)
    # The credit is a component of its own, tested in test_sponsor_credit.py: here a
    # node that says where it stands and whose sponsor it names.
    monkeypatch.setattr(
        help_screen,
        "SponsorCreditTile",
        lambda credit, what, identifier: ft.Semantics(
            identifier=identifier, label=f"{what}, {credit.slug if credit else ''}"
        ),
    )
    # The card is a component of its own, tested in test_location_card.py: here a
    # node that says where it stands and which pin it shows, as spot_card finds it.
    monkeypatch.setattr(
        help_screen,
        "spot_card",
        lambda data, key, *, identifier: (
            ft.Semantics(identifier=identifier, label=key)
            if key and data.pin(key)
            else None
        ),
    )
    monkeypatch.setattr(info_page, "use_margin", phone_margin)

    def render(svc: Services) -> dict[str, Any]:
        """``Help``'s body, its services answered with ``svc``."""
        monkeypatch.setattr(help_screen, "use_services", lambda: svc)
        return cast(dict[str, Any], inspect.unwrap(Help)())

    return render


def blocks_of(scaffold: dict[str, Any]) -> list[ft.Control]:
    """Return the items of the scaffold's ``ListView`` body."""
    body = scaffold["body"]
    assert isinstance(body, ft.ListView)
    return list(body.controls)


def card_of(block: ft.Control) -> ft.Card:
    """Return the Report a concern ``Card`` inside its gutter."""
    assert isinstance(block, ft.Container)
    card = block.content
    assert isinstance(card, ft.Card)
    return card


def card_items(block: ft.Control) -> list[ft.Control]:
    """Return what the card holds, top to bottom."""
    column = card_of(block).content
    assert isinstance(column, ft.Column)
    return list(column.controls)


def link_node(row: ft.Control) -> ft.Semantics:
    """Return a link row's merged ``Semantics`` node (its identifier and link flag)."""
    if isinstance(row, ft.Row):  # a phone or email row: the link, then Copy
        holder = row.controls[0]
        assert isinstance(holder, ft.Container) and holder.content is not None
        row = holder.content
    assert isinstance(row, ft.MergeSemantics)
    node = row.content
    assert isinstance(node, ft.Semantics)
    return node


def tile_of(row: ft.Control) -> ft.ListTile:
    """Return a row's ``ListTile``."""
    tile = link_node(row).content
    assert isinstance(tile, ft.ListTile)
    return tile


def copy_node(row: ft.Control) -> ft.Semantics:
    """Return the Copy button's named node beside a phone or email row."""
    assert isinstance(row, ft.Row)
    holder = row.controls[1]
    assert isinstance(holder, ft.Container)
    merged = holder.content
    assert isinstance(merged, ft.MergeSemantics)  # one node with its tooltip (D-234)
    node = merged.content
    assert isinstance(node, ft.Semantics)
    return node


async def click(control: ft.Control) -> None:
    """Await a tile's or a button's ``on_click``, as a tap does."""
    handler = getattr(control, "on_click", None)
    assert handler is not None
    await cast(Callable[[], Awaitable[None]], handler)()


def said(page: FakePage) -> list[str]:
    """The SnackBars' texts, in order."""
    texts = []
    for dialog in page.dialogs:
        assert isinstance(dialog, ft.SnackBar) and isinstance(dialog.content, ft.Text)
        texts.append(str(dialog.content.value))
    return texts


def block_named(blocks: list[ft.Control], identifier: str) -> ft.Control:
    """Return the one in-app or plain row whose merged node is ``identifier``."""
    (block,) = [
        block
        for block in blocks
        if isinstance(block, ft.MergeSemantics)
        and getattr(block.content, "identifier", None) == identifier
    ]
    return block


def outline(blocks: list[ft.Control]) -> list[str]:
    """The page as headings (``# ``), the card, row identifiers and the summary."""
    result = []
    for block in blocks:
        if block is REPORT_PROBLEM_SECTION:
            result.append("report_problem")
        elif isinstance(block, ft.Semantics) and block.header:
            heading = block.content
            assert isinstance(heading, ft.Container)
            assert isinstance(heading.content, ft.Text)
            result.append(f"# {heading.content.value}")
        elif isinstance(block, ft.Container) and isinstance(block.content, ft.Card):
            result.append("card")
        elif isinstance(block, ft.Container) and isinstance(
            block.content, ft.Semantics
        ):  # a place's location card, in the gutter
            result.append(str(block.content.identifier))
        elif isinstance(block, ft.Semantics):
            result.append(str(block.identifier))
        else:
            result.append(str(link_node(block).identifier))
    return result


def test_the_card_comes_first_then_the_venue_then_the_code_of_conduct(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """The page reads the card, the places, the CoC, then the app's row (D-281)."""
    scaffold = render(svc)
    assert scaffold["title"] == "Help & safety"
    assert outline(blocks_of(scaffold)) == [
        "card",
        "# At the venue",
        "help.info_desk",
        "help.info_desk.location",
        "help.lost_and_found",
        "help.lost_and_found.location",
        "help.quiet_room",
        "help.quiet_room.location",
        "help.quiet_room.sponsor",
        "help.all_maps",
        "# Code of Conduct",
        "help.coc_summary",
        "help.coc",
        "help.procedures",
        "report_problem",
    ]


def test_the_quiet_room_s_line_is_followed_by_its_sponsor_s_credit(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """D-337: the credit row under the quiet room names the year's sponsor."""
    (credit,) = [
        block
        for block in blocks_of(render(svc))
        if isinstance(block, ft.Semantics)
        and block.identifier == "help.quiet_room.sponsor"
    ]
    assert credit.label == "Quiet room, google"


def test_the_card_s_first_stop_is_its_level_2_heading(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """A screen reader's first stop after the title is "Report a concern" (F40, D-211)."""
    heading = card_items(blocks_of(render(svc))[0])[0]
    assert isinstance(heading, ft.Semantics)
    assert heading.header and heading.heading_level == 2 and heading.container
    assert heading.identifier == "help.report"
    holder = heading.content
    assert isinstance(holder, ft.Container) and isinstance(holder.content, ft.Row)
    icon, text = holder.content.controls
    assert isinstance(icon, ft.Icon) and icon.semantics_label is None  # decorative
    assert isinstance(text, ft.Text) and text.value == "Report a concern"


def test_the_card_is_outlined_in_error_and_reads_as_its_parts(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """An ``error`` edge, and not one node: the heading, rows and line are stops."""
    card = card_of(blocks_of(render(svc))[0])
    assert card.variant is ft.CardVariant.OUTLINED
    assert isinstance(card.shape, ft.RoundedRectangleBorder)
    assert card.shape.side is not None and card.shape.side.color == ft.Colors.ERROR
    assert card.semantic_container is False  # else one node holds them all (D-211)


def test_2026_s_card_has_the_email_row_then_the_danger_and_staff_line(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """2026 lists the report email (no public hotline, D-45), then the last line.

    It says emergency services first when someone is in danger, then reporting in
    person.
    """
    _, row, line = card_items(blocks_of(render(svc))[0])
    node = link_node(row)
    assert node.identifier == "help.report.mailto" and node.link
    tile = tile_of(row)
    # One node read as action plus value.
    assert tile.title == "Email the Code of Conduct team"
    assert tile.subtitle == "pycon-us-report@python.org"
    assert copy_node(row).identifier == "help.copy.mailto"
    assert isinstance(line, ft.Container) and isinstance(line.content, ft.Text)
    assert str(line.content.value).startswith("If someone is in danger, contact local")
    assert "staff member" in str(line.content.value)


async def test_the_email_row_copies_its_address(
    render: Callable[[Services], dict[str, Any]], svc: Services, page: FakePage
) -> None:
    """Copy puts the address on the clipboard and says so on iOS (D-182)."""
    _, row, _ = card_items(blocks_of(render(svc))[0])
    await click(cast(ft.Control, copy_node(row).content))
    assert cast(MemoryClipboard, svc.clipboard).value == "pycon-us-report@python.org"
    assert said(page) == ["Email address copied"]


async def test_a_phone_row_calls_and_copies_its_number(
    render: Callable[[Services], dict[str, Any]], svc: Services, page: FakePage
) -> None:
    """A tap hands ``tel:`` to the phone app; Copy copies the number as stored."""
    year = replace(
        svc.year, content=replace(svc.year.content, safety_contacts=(HOTLINE,))
    )
    _, row, _ = card_items(blocks_of(render(replace(svc, year=year)))[0])
    assert link_node(row).identifier == "help.report.tel"
    assert tile_of(row).subtitle == "+1 562-555-0100"
    await click(tile_of(row))
    launched = cast(MemoryLauncher, svc.launcher).launched
    assert launched == [("tel:+15625550100", ft.LaunchMode.EXTERNAL_APPLICATION)]
    await click(cast(ft.Control, copy_node(row).content))
    assert cast(MemoryClipboard, svc.clipboard).value == "+15625550100"
    assert said(page) == ["Phone number copied"]


async def test_a_call_that_cannot_open_says_so_and_copy_still_works(
    render: Callable[[Services], dict[str, Any]], svc: Services, page: FakePage
) -> None:
    """Where ``tel:`` fails (an iPad, a simulator), the row says so; Copy still copies."""
    year = replace(
        svc.year, content=replace(svc.year.content, safety_contacts=(HOTLINE,))
    )
    _, row, _ = card_items(blocks_of(render(replace(svc, year=year)))[0])
    cast(MemoryLauncher, svc.launcher).error = RuntimeError("no app for tel")
    await click(tile_of(row))
    await click(cast(ft.Control, copy_node(row).content))
    assert said(page) == ["Couldn't open the link", "Phone number copied"]
    assert cast(MemoryClipboard, svc.clipboard).value == "+15625550100"


def test_each_place_reads_as_one_phrase(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """A place's row is one merged node: its name, then where it is."""
    tile = tile_of(block_named(blocks_of(render(svc)), "help.quiet_room"))
    assert tile.title == "Quiet room"
    info = svc.year.content.help
    assert info is not None and tile.subtitle == info.quiet_room
    assert tile.on_click is None  # it opens nothing


def test_the_code_of_conduct_links_open_in_the_browser(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """The full text and the procedures are external rows on the PSF's site."""
    blocks = blocks_of(render(svc))
    coc, procedures = blocks[-3:-1]
    assert tile_of(coc).title == "Read the Code of Conduct"
    assert tile_of(coc).subtitle == "policies.python.org"
    assert isinstance(tile_of(coc).trailing, ft.Icon)  # OPEN_IN_NEW, read aloud
    assert tile_of(procedures).title == "How reports are handled"


def test_without_year_data_the_page_shows_the_feed_s_block(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """A year without the tables hands the page to the feed's ``code-of-conduct``."""
    content = replace(svc.year.content, safety_contacts=(), help=None)
    with Renderer().with_context():  # what calling a component needs, as in a render
        scaffold = render(replace(svc, year=replace(svc.year, content=content)))
    item, report = blocks_of(scaffold)
    assert report is REPORT_PROBLEM_SECTION  # the app's row ends the page still
    assert isinstance(item, ft.Component)
    assert item.fn is inspect.unwrap(FeedBlock)
    assert item.args == ("code-of-conduct",)
    assert item.kwargs["screen"] == "help"


def test_each_place_s_card_shows_the_pin_help_names(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """INFO-12: the desk, lost and found and the quiet room each show their pin."""
    cards = {
        str(block.content.identifier): block.content.label
        for block in blocks_of(render(svc))
        if isinstance(block, ft.Container) and isinstance(block.content, ft.Semantics)
    }
    assert cards == {
        "help.info_desk.location": "info-desk",
        "help.lost_and_found.location": "lost-and-found",
        "help.quiet_room.location": "quiet-room",
    }


def test_all_maps_opens_the_map_tab(
    render: Callable[[Services], dict[str, Any]], svc: Services, page: FakePage
) -> None:
    """All maps is an in-app row to ``/map`` (its Floor plans once #391 adds them)."""
    tile = tile_of(block_named(blocks_of(render(svc)), "help.all_maps"))
    assert tile.title == "All maps"
    assert tile.on_click is not None
    tile.on_click()  # type: ignore[call-arg]  # an in-app row's tap is sync
    assert page.navigated == ["/map"]


def test_a_year_without_plans_shows_no_card_and_no_all_maps(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """Without ``map.toml`` (2025's case) the places are their lines alone."""
    year = replace(svc.year, map=MapData())
    assert outline(blocks_of(render(replace(svc, year=year))))[2:7] == [
        "help.info_desk",
        "help.lost_and_found",
        "help.quiet_room",
        "help.quiet_room.sponsor",
        "# Code of Conduct",
    ]


def test_contacts_without_help_show_the_card_alone(page: FakePage) -> None:
    """The card needs only the contacts; without ``[help]`` it has no staff line."""
    (block,) = help_blocks((HOTLINE,), None)
    assert len(card_items(block)) == 2  # the heading and the row


@pytest.mark.parametrize(
    ("kind", "value", "line"),
    [
        ("tel", "+15625550100", "+1 562-555-0100"),
        ("tel", "+442071234567", "+442071234567"),
        ("mailto", "a@b.org", "a@b.org"),
        ("https", "https://example.org/report/", "example.org"),
    ],
)
def test_a_contact_s_line_is_its_value_as_it_reads(
    kind: str, value: str, line: str
) -> None:
    """A North American number in groups, others as written, a page by its host."""
    assert contact_line(replace(HOTLINE, kind=kind, value=value)) == line


# ------------------------------------------------------- Report a problem with the app


@pytest.fixture
def report_svc(svc: Services, tmp_path: Path) -> Services:
    """``svc`` with a share sheet and a packaged build's one-line ``console.log``.

    Made before a page is bound, as Flet makes a session's services.
    """
    log = tmp_path / "console.log"
    log.write_text("12:00:00.000 INFO pycon_us.app: started\n")
    paths = MemoryPaths()
    paths.console_log = str(log)
    return replace(svc, share=MemoryShare(), paths=paths)


@pytest.fixture
async def report_section(
    monkeypatch: pytest.MonkeyPatch, report_svc: Services, page: FakePage
) -> tuple[Callable[[], list[ft.Control]], Services]:
    """Render ``ReportProblem`` in a packaged build, while the repository is private.

    Returns the render and the services it shares through.
    """
    services = report_svc
    conference = Conference()
    await conference.load_local(services.storage, services.year)
    monkeypatch.setattr(prefs_module, "DEVELOPER_ALWAYS", False)  # a packaged build
    states = States()
    monkeypatch.setattr(ft, "use_state", states.use_state)
    answer_report_hooks(monkeypatch, services, conference, Prefs())
    monkeypatch.setattr(help_screen, "use_tokens", lambda: LIGHT_TOKENS)
    monkeypatch.setattr(help_screen, "SOURCE_URL", None)
    monkeypatch.setattr(rows, "use_services", lambda: services)

    def render() -> list[ft.Control]:
        """``ReportProblem``'s controls, its state kept from the last render."""
        states.index = 0
        column = inspect.unwrap(ReportProblem)()
        assert isinstance(column, ft.Column)
        return column.controls

    return render, services


def test_while_private_the_last_row_reports_a_problem_with_the_log(
    report_section: tuple[Callable[[], list[ft.Control]], Services],
) -> None:
    """While private, a level-2 "The app" heads one row that says it sends the log."""
    render, _ = report_section
    controls = render()
    assert headings(controls) == [("The app", 2)]
    assert list(identified(controls)) == ["help.report_problem", "help.report_outcome"]
    tile = identified(controls)["help.report_problem"].content
    assert isinstance(tile, ft.ListTile)
    assert text_of(tile.title) == "Report a problem with the app"
    assert text_of(tile.subtitle) == WITH_LOG
    assert identified(controls)["help.report_outcome"].visible is False


async def test_the_row_shares_the_log_and_diagnostics_and_says_so_in_place(
    report_section: tuple[Callable[[], list[ft.Control]], Services],
) -> None:
    """A tap shares console.log with the diagnostics as text, with no email in it.

    Then the line under the row says what was shared, a live region (D-29, D-210).
    """
    render, services = report_section
    row = identified(render())["help.report_problem"].content
    assert row is not None
    await click(row)
    share = cast(MemoryShare, services.share)
    [files] = share.shared
    assert len(files) == 1
    text = share.file_options[0]["text"]
    assert "Python" in text and "@" not in text  # the diagnostics, no address (D-72)
    line = identified(render())["help.report_outcome"]
    assert line.live_region is True and line.visible is True
    outcome = cast(ft.Row, cast(ft.Container, line.content).content).controls[1]
    assert text_of(outcome) == LOG_SHARED[0]


async def test_once_public_the_row_opens_a_new_issue_in_the_browser(
    report_section: tuple[Callable[[], list[ft.Control]], Services],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With ``SOURCE_URL`` set, the row is external: it reads "Opens in browser".

    It opens the repository's new issue page in the in-app browser (INFO-14, D-182).
    """
    render, services = report_section
    monkeypatch.setattr(help_screen, "SOURCE_URL", "https://example.org/conf")
    controls = render()
    assert list(identified(controls)) == ["help.report_problem", "help.report_outcome"]
    node = identified(controls)["help.report_problem"]
    assert node.link
    tile = node.content
    assert isinstance(tile, ft.ListTile)
    assert text_of(tile.title) == "Report a problem with the app"
    assert text_of(tile.subtitle) == "example.org/conf/issues/new"
    assert isinstance(tile.trailing, ft.Icon)
    assert tile.trailing.semantics_label in OPENS_IN.values()
    await click(tile)
    assert cast(MemoryLauncher, services.launcher).launched == [
        ("https://example.org/conf/issues/new", ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]
