"""Tests for About this app's Help us fix it section (#443; D-297).

The section runs in ``tests/about_page.py``'s stand-ins.
"""

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.prefs import Prefs
from pycon_us.screens import about_app
from pycon_us.screens.about_app import HelpUsFixIt
from pycon_us.services import Services
from pycon_us.state import Conference
from pycon_us.theme import LIGHT_TOKENS
from pycon_us.ui import rows as rows_module
from pycon_us.ui import share as share_module
from pycon_us.ui.share import DIAGNOSTICS_SHARED, LOG_SHARED, WITH_LOG, WITHOUT_LOG
from tests import about_page
from tests.about_page import States, answer_report_hooks, headings, identified, text_of
from tests.fake_page import FakePage
from tests.fakes import MemoryLauncher, MemoryPaths, MemoryShare

real_time, offline, page, svc, prefs, render, conference = (
    about_page.real_time,
    about_page.offline,
    about_page.page,
    about_page.svc,
    about_page.prefs,
    about_page.render,
    about_page.conference,
)


# ------------------------------------------------------------------ Help us fix it


@pytest.fixture
def help_section(
    monkeypatch: pytest.MonkeyPatch,
    svc: Services,
    conference: Conference,
    prefs: Prefs,
    page: FakePage,
    tmp_path: Path,
) -> Callable[[], list[ft.Control]]:
    """Render ``HelpUsFixIt`` in a packaged build with a one-line log: its controls."""
    log = tmp_path / "console.log"
    log.write_text("12:00:00.000 INFO pycon_us.app: started\n")
    cast(MemoryPaths, svc.paths).console_log = str(log)
    states = States()
    monkeypatch.setattr(ft, "use_state", states.use_state)
    answer_report_hooks(monkeypatch, svc, conference, prefs)
    monkeypatch.setattr(about_app, "use_tokens", lambda: LIGHT_TOKENS)
    monkeypatch.setattr(about_app, "SOURCE_URL", None)
    monkeypatch.setattr(
        rows_module, "_ExternalLinkTile", inspect.unwrap(rows_module._ExternalLinkTile)
    )
    monkeypatch.setattr(rows_module, "use_services", lambda: svc)

    def render() -> list[ft.Control]:
        states.index = 0
        column = inspect.unwrap(HelpUsFixIt)()
        assert isinstance(column, ft.Column)
        return column.controls

    return render


def help_tile(controls: list[ft.Control], identifier: str) -> ft.ListTile:
    """The row under ``identifier``."""
    tile = identified(controls)[identifier].content
    assert isinstance(tile, ft.ListTile)
    return tile


def report_outcome(controls: list[ft.Control]) -> str | None:
    """The words of the line under the rows, or None while it is hidden."""
    line = identified(controls)["about_app.report_outcome"]
    assert line.live_region is True  # a screen reader says it when it changes
    if not line.visible:
        return None
    text = cast(ft.Row, cast(ft.Container, line.content).content).controls[1]
    return text_of(text)


async def tap_row(render: Callable[[], list[ft.Control]], identifier: str) -> None:
    """Tap the row under ``identifier`` as Flutter would."""
    await cast(Any, help_tile(render(), identifier).on_click)()


def test_while_private_one_row_reports_a_problem_with_the_log(
    help_section: Callable[[], list[ft.Control]],
) -> None:
    """While the repository is private, Help us fix it is one Report a problem row.

    A level-2 heading over it; the row says beforehand that it sends the log and the
    diagnostics; the outcome line under it is hidden until a share ends.
    """
    controls = help_section()
    assert headings(controls) == [("Help us fix it", 2)]
    assert list(identified(controls)) == [
        "about_app.report_problem",
        "about_app.report_outcome",
    ]
    tile = help_tile(controls, "about_app.report_problem")
    assert text_of(tile.title) == "Report a problem"
    assert text_of(tile.subtitle) == WITH_LOG
    assert report_outcome(controls) is None


async def test_report_a_problem_shares_the_log_and_says_so_in_place(
    help_section: Callable[[], list[ft.Control]], svc: Services
) -> None:
    """A tap shares console.log with the diagnostics, then says so under the row."""
    await tap_row(help_section, "about_app.report_problem")
    [files] = cast(MemoryShare, svc.share).shared
    assert len(files) == 1
    assert report_outcome(help_section()) == LOG_SHARED[0]
    assert help_tile(help_section(), "about_app.report_problem").disabled is False


async def test_in_the_companion_app_the_row_says_it_sends_the_diagnostics_alone(
    help_section: Callable[[], list[ft.Control]],
    svc: Services,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outside a packaged build the row says, before the tap, that no log goes."""
    monkeypatch.setattr(share_module, "is_embedded", lambda: False)
    tile = help_tile(help_section(), "about_app.report_problem")
    assert text_of(tile.subtitle) == WITHOUT_LOG
    await tap_row(help_section, "about_app.report_problem")
    assert cast(MemoryShare, svc.share).shared == []
    assert len(cast(MemoryShare, svc.share).texts) == 1
    assert report_outcome(help_section()) == DIAGNOSTICS_SHARED[0]


async def test_the_row_is_disabled_while_the_sheet_is_up(
    help_section: Callable[[], list[ft.Control]],
    svc: Services,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """While the sheet is up the row is disabled, so a second tap opens no second one."""
    seen: list[bool | None] = []
    share = cast(MemoryShare, svc.share)
    share_files = share.share_files

    async def record_then_share(files: list[ft.ShareFile], **options: Any) -> Any:
        seen.append(help_tile(help_section(), "about_app.report_problem").disabled)
        return await share_files(files, **options)

    monkeypatch.setattr(share, "share_files", record_then_share)
    await tap_row(help_section, "about_app.report_problem")
    assert seen == [True]
    assert help_tile(help_section(), "about_app.report_problem").disabled is False


async def test_once_public_report_opens_a_new_issue_and_share_log_shares(
    help_section: Callable[[], list[ft.Control]],
    svc: Services,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With ``SOURCE_URL`` set, Report a problem links to a new issue, Share log shares.

    The link opens in the in-app browser and reads as one (INFO-14, D-182).
    """
    monkeypatch.setattr(about_app, "SOURCE_URL", "https://example.org/conf/")
    controls = help_section()
    assert list(identified(controls)) == [
        "about_app.report_problem",
        "about_app.share_log",
        "about_app.report_outcome",
    ]
    node = identified(controls)["about_app.report_problem"]
    assert node.link
    tile = node.content
    assert isinstance(tile, ft.ListTile)
    assert text_of(tile.subtitle) == "example.org/conf/issues/new"
    await cast(Callable[[], Any], tile.on_click)()
    assert cast(MemoryLauncher, svc.launcher).launched == [
        ("https://example.org/conf/issues/new", ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]
    await tap_row(help_section, "about_app.share_log")
    assert len(cast(MemoryShare, svc.share).shared) == 1
    assert report_outcome(help_section()) == LOG_SHARED[0]
