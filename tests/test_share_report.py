"""Tests for `share_console_log()`: the log and the diagnostics on the share sheet (#443).

The one way the app shares a bug report (INFO-04, D-297): About this app's Report a
problem and Developer's Share log call it. The share sheet and the log's path are
in-memory fakes, and a fake page is bound as Flet binds a session's page. The sheet
itself, and where it points from on an iPad, are checked on devices (the PR).
"""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest
from flet.controls.services import share as flet_share

from pycon_us.config import load_year
from pycon_us.favorites import Favorites
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.services import Services, api
from pycon_us.services.errors import LOG_DATE_FORMAT, LOG_FORMAT, RedactingFormatter
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from pycon_us.ui.actions import NO_OUTCOME
from pycon_us.ui.share import (
    DIAGNOSTICS_SHARED,
    LOG_SHARED,
    NO_LOG_YET,
    REPORT_NOT_SHARED,
    REPORT_OFFERED,
    REPORT_SUBJECT,
    centre,
    share_console_log,
)
from tests.fake_page import FakePage, bound
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPaths,
    MemoryPrefs,
    MemorySemantics,
    MemoryShare,
)

ANCHOR = ft.Offset(200, 400)
"""Where the sheet points from on the 400 x 800 dp fake page: its centre (D-62)."""


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reaches the network: every fetch finds no answer."""

    async def fetch(url: str, **_: Any) -> bytes:
        raise api.NetworkError("ConnectError: offline")

    monkeypatch.setattr(api, "fetch_feed", fetch)


@pytest.fixture
def page(svc: Services) -> Iterator[FakePage]:
    """A fake 400 x 800 dp page, bound as the session's page until the test ends.

    Bound after the services are made: a service made under a bound page registers
    with it, which a fake page cannot do.
    """
    fake = FakePage()
    fake.width, fake.height = 400, 800
    with bound(fake):
        yield fake


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """The 2026 services over in-memory fakes, with a share sheet and storage paths."""
    return Services(
        year=load_year(2026),
        storage=Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026),
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
        share=MemoryShare(),
        paths=MemoryPaths(),
    )


@pytest.fixture
async def conference(svc: Services) -> Conference:
    """A Conference store that has published the bundled 2026 snapshot."""
    store = Conference()
    await store.load_local(svc.storage, svc.year)
    return store


@pytest.fixture
def log(svc: Services, tmp_path: Path) -> Path:
    """A `console.log` with one line, where the storage paths say the log is."""
    path = tmp_path / "console.log"
    path.write_text("12:00:00.000 INFO pycon_us.app: started\n")
    cast(MemoryPaths, svc.paths).console_log = str(path)
    return path


def share_of(svc: Services) -> MemoryShare:
    """The fake share sheet, to read what it was given."""
    return cast(MemoryShare, svc.share)


async def report(
    svc: Services, conference: Conference, *, packaged: bool = True
) -> tuple[str, bool]:
    """Share a report as About this app's row does, with fresh settings and no saves."""
    return await share_console_log(
        svc,
        packaged=packaged,
        conference=conference,
        prefs=Prefs(loaded=True),
        favorites=Favorites(loaded=True),
    )


async def test_a_packaged_build_shares_the_log_with_the_diagnostics_as_its_text(
    page: FakePage, svc: Services, conference: Conference, log: Path
) -> None:
    """A packaged build shares console.log, the diagnostics as its text, then says so.

    The sheet points from the window's centre, which anchors it on an iPad (D-62).
    """
    assert await report(svc, conference) == LOG_SHARED
    [files] = share_of(svc).shared
    assert [file.path for file in files] == [str(log)]
    [options] = share_of(svc).file_options
    assert options["text"].splitlines()[0].startswith("App: ")
    assert "Saved sessions: 0" in options["text"]
    assert options["subject"] == REPORT_SUBJECT
    assert options["share_position_origin"] == ANCHOR
    assert share_of(svc).texts == []


async def test_the_companion_app_shares_the_diagnostics_alone(
    page: FakePage, svc: Services, conference: Conference, log: Path
) -> None:
    """Outside a packaged build there is no log to add: the diagnostics go as a text.

    The log's path is not even asked for: the companion app's Python runs on the laptop.
    """
    cast(MemoryPaths, svc.paths).error = AssertionError("the path was asked for")
    assert await report(svc, conference, packaged=False) == DIAGNOSTICS_SHARED
    assert share_of(svc).shared == []
    [(text, options)] = share_of(svc).texts
    assert text.startswith("App: ")
    assert options["subject"] == REPORT_SUBJECT
    assert options["share_position_origin"] == ANCHOR


@pytest.mark.parametrize("content", [None, ""])
async def test_a_packaged_build_without_a_log_shares_the_diagnostics_and_says_so(
    page: FakePage,
    svc: Services,
    conference: Conference,
    tmp_path: Path,
    content: str | None,
) -> None:
    """A missing or empty log is left out: the diagnostics go alone, and it says why."""
    path = tmp_path / "console.log"
    if content is not None:
        path.write_text(content)
    cast(MemoryPaths, svc.paths).console_log = str(path)
    assert await report(svc, conference) == NO_LOG_YET
    assert share_of(svc).shared == []
    assert len(share_of(svc).texts) == 1


async def test_a_log_path_that_cannot_be_read_leaves_the_log_out_and_logs_its_class(
    page: FakePage,
    svc: Services,
    conference: Conference,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the platform cannot give the log's path, the diagnostics still go alone."""
    cast(MemoryPaths, svc.paths).error = TimeoutError("get_console_log_filename")
    with caplog.at_level(logging.WARNING, logger="pycon_us.ui.share"):
        assert await report(svc, conference) == NO_LOG_YET
    assert [r.getMessage() for r in caplog.records] == [
        "Could not find the log: TimeoutError"
    ]


@pytest.mark.parametrize(
    ("status", "says"),
    [
        (ft.ShareResultStatus.DISMISSED, NO_OUTCOME),
        # Some Android targets report neither: the sheet had the report either way.
        (ft.ShareResultStatus.UNAVAILABLE, REPORT_OFFERED),
    ],
)
async def test_a_dismissed_sheet_says_nothing_and_an_unknown_end_says_it_was_offered(
    page: FakePage,
    svc: Services,
    conference: Conference,
    log: Path,
    status: ft.ShareResultStatus,
    says: tuple[str, bool],
) -> None:
    """Dismissing the sheet says nothing; a status the platform cannot give, the offer."""
    share_of(svc).status = status
    assert await report(svc, conference) == says


async def test_a_sheet_that_fails_says_so_and_logs_only_the_error_s_class(
    page: FakePage,
    svc: Services,
    conference: Conference,
    log: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed share says so and logs the error's class, never the path or the text.

    Flet's invoke error repeats the call's arguments, the path included (D-72).
    """
    share_of(svc).error = RuntimeError(f"share_files({log}) failed")
    with caplog.at_level(logging.WARNING, logger="pycon_us.ui.share"):
        assert await report(svc, conference) == REPORT_NOT_SHARED
    assert [r.getMessage() for r in caplog.records] == [
        "Could not share a report: RuntimeError"
    ]


async def test_a_logged_email_is_shared_as_a_placeholder(
    page: FakePage, svc: Services, conference: Conference, log: Path
) -> None:
    """An address a log line quotes reaches the shared console.log as `<email>`.

    The app's handler writes the file through `RedactingFormatter` (D-196); the
    report shares that file as it is, so no address leaves the device in it.
    """
    handler = logging.FileHandler(log, mode="w", encoding="utf-8")
    handler.setFormatter(RedactingFormatter(LOG_FORMAT, LOG_DATE_FORMAT))
    logger = logging.getLogger("pycon_us.test_share_report")
    logger.addHandler(handler)
    try:
        logger.warning("No app for mailto:ada@example.org")
    finally:
        logger.removeHandler(handler)
        handler.close()
    assert await report(svc, conference) == LOG_SHARED
    [[shared]] = share_of(svc).shared
    assert shared.path is not None
    written = Path(shared.path).read_text(encoding="utf-8")
    assert "mailto:<email>" in written
    assert "ada@example.org" not in written


def test_flet_still_sends_the_sheet_s_origin_without_a_size() -> None:
    """At the pin Flet sends the origin as a point with no size (U95).

    An iPad opens the sheet anyway, pointing from the view's centre: share_plus 13.3.1
    makes a small rectangle there out of an empty one (F263, which supersedes F115). A
    tripwire for the Flet bump that lets the origin carry a size: when this fails, the
    popover can point from the origin we send, and `centre()` needs another look.
    """
    args = flet_share._share_args(share_position_origin=ft.Offset(200, 400))
    assert args["share_position_origin"] == {"x": 200, "y": 400}


def test_no_anchor_before_flutter_reports_the_window_size() -> None:
    """Without the page's size there is no centre: the sheet gets no origin."""
    assert centre(cast(ft.Page, FakePage())) is None
