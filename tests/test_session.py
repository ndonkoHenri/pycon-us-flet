"""Tests for the session detail stub's line under the title: track and place (#170).

``SessionDetail`` runs outside a renderer, as in ``test_more.py``: its hooks and
``AppScaffold`` are replaced, and a fake page is bound as Flet binds a session's page.
The sessions are the recorded 2026 feed's. How the screen looks is checked on devices
(the PR); P1's real session detail replaces the stub.
"""

import inspect
from collections.abc import Callable, Iterator
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.core.models import ConferenceData, Session
from pycon_us.screens import session as screen
from pycon_us.screens.session import SessionDetail
from tests.fakes import FakePage, bound
from tests.feeds import processed

# A generic break: its rooms are listed, but it has no one place to show (DATA-16).
BREAK = (
    "break-Room 103ABC, Room 104AB, Room 104C, Grand Ballroom A, Grand Ballroom B"
    "-2026-05-16T10:05:00-07:00"
)
TALK = "142"  # in Grand Ballroom A


@pytest.fixture(scope="module")
def data() -> ConferenceData:
    return processed(2026)


@pytest.fixture
def page() -> Iterator[FakePage]:
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def lines_under_title(
    monkeypatch: pytest.MonkeyPatch, data: ConferenceData, page: FakePage
) -> Callable[[Session], list[str]]:
    """Return render(session): the text lines of its detail, after the route line."""
    monkeypatch.setattr(ft, "use_view_path", lambda: "/schedule/session/x")
    monkeypatch.setattr(ft, "use_route_params", dict)
    monkeypatch.setattr(screen, "AppScaffold", lambda **kwargs: kwargs)

    def render(session: Session) -> list[str]:
        only = SimpleNamespace(
            sessions={session.id: session}, rooms=data.rooms, speakers=data.speakers
        )
        monkeypatch.setattr(
            screen, "use_conference", lambda: SimpleNamespace(data=only)
        )
        scaffold = cast(dict[str, Any], inspect.unwrap(SessionDetail)(session.id))
        body = scaffold["body"]
        assert isinstance(body, ft.ListView)
        texts = [
            str(row.content.value)
            for row in body.controls
            if isinstance(row, ft.Container) and isinstance(row.content, ft.Text)
        ]
        return texts[1:]  # the first is stub_body's route line

    return render


def test_a_session_with_a_place_reads_its_track_then_the_place(
    lines_under_title: Callable[[Session], list[str]], data: ConferenceData
) -> None:
    assert lines_under_title(data.sessions[TALK]) == ["Talk · Grand Ballroom A"]


def test_a_break_without_a_place_reads_its_track_alone(
    lines_under_title: Callable[[Session], list[str]], data: ConferenceData
) -> None:
    generic_break = data.sessions[BREAK]
    assert generic_break.display_location == ""
    assert lines_under_title(generic_break) == ["Break"]  # not "Break ·"


def test_a_session_with_neither_has_no_line_under_its_title(
    lines_under_title: Callable[[Session], list[str]], data: ConferenceData
) -> None:
    nothing = replace(data.sessions[BREAK], track="")
    assert lines_under_title(nothing) == []
