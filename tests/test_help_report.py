"""Tests for Help & safety's Report a problem with the app (``/more/help``; D-281).

``ReportProblem`` runs outside a renderer over the fixtures of ``tests/help_page.py``,
with the help section's stand-ins from ``tests/about_page.py``: while the repository is
private the row shares the log and the diagnostics, once public it opens a new issue.
The page around it is tested in ``test_help.py``.
"""

import inspect
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us import prefs as prefs_module
from pycon_us.prefs import Prefs
from pycon_us.screens import help as help_screen
from pycon_us.screens.help import ReportProblem
from pycon_us.services import Services
from pycon_us.state import Conference
from pycon_us.theme import LIGHT_TOKENS
from pycon_us.ui import rows
from pycon_us.ui.links import OPENS_IN
from pycon_us.ui.share import LOG_SHARED, WITH_LOG
from tests import help_page
from tests.about_page import States, answer_report_hooks, headings, identified, text_of
from tests.fakes import FakePage, MemoryLauncher, MemoryPaths, MemoryShare
from tests.help_page import click

# The harness's fixtures, under this module's names, where pytest looks them up.
svc, page = help_page.svc, help_page.page


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
