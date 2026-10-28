"""Tests for the Developer screen's Mock API section (DEV-01, D-51, #668).

``MockApiSection`` runs outside a renderer, its hooks replaced, over the seeded mock
behind ``tools/mock_api/transport.py``. How it looks is checked on devices (the PR).
"""

import inspect
import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.favorites import Favorites
from pycon_us.prefs import Prefs
from pycon_us.screens import developer_api
from pycon_us.screens.developer_api import MockApiSection
from pycon_us.screens.developer_data import reset_app
from pycon_us.services import Services
from pycon_us.services.private_api import CONNECTED, PrivateApi
from pycon_us.state import Conference
from pycon_us.theme import LIGHT_TOKENS
from tests import data_section
from tests.api_clients import Recorder
from tests.developer_screen import States
from tests.fakes import MemoryPrefs
from tests.mock_calls import state_at
from tools.mock_api.transport import mock_transport

svc_without_api, prefs, offline = (
    data_section.svc,
    data_section.prefs,
    data_section.offline,
)

MOCK = "http://10.0.2.2:8000"


@pytest.fixture
def recorder() -> Recorder:
    """A transport to the seeded mock that keeps every request sent through it."""
    return Recorder(mock_transport(state_at()))


@pytest.fixture
def svc(svc_without_api: Services, recorder: Recorder) -> Services:
    """The 2026 services, whose private-API clients go to the in-process mock."""
    return Services(
        **{
            **vars(svc_without_api),
            "private_api": PrivateApi(recorder),
        }
    )


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch, svc: Services, prefs: Prefs
) -> Callable[[], ft.Column]:
    """Render the section and return its column."""
    states = States()
    monkeypatch.setattr(ft, "use_state", states.use_state)
    monkeypatch.setattr(developer_api, "use_services", lambda: svc)
    monkeypatch.setattr(developer_api, "use_prefs", lambda: prefs)
    monkeypatch.setattr(developer_api, "use_tokens", lambda: LIGHT_TOKENS)

    def render() -> ft.Column:
        """Render the section once more, its states kept."""
        states.index = 0
        return cast(ft.Column, inspect.unwrap(MockApiSection)())

    return render


def identified(root: ft.Control) -> dict[str, ft.Semantics]:
    """Every identified node under ``root``, by its identifier."""
    found: dict[str, ft.Semantics] = {}

    def visit(control: Any) -> None:
        """Note ``control`` if it has an identifier, then look under it."""
        if isinstance(control, ft.Semantics) and control.identifier:
            found[control.identifier] = control
        for name in ("content", "controls"):
            child = getattr(control, name, None)
            for item in child if isinstance(child, list) else [child]:
                if isinstance(item, ft.Control):
                    visit(item)

    visit(root)
    return found


async def type_url(render: Callable[[], ft.Column], text: str) -> None:
    """Type into the URL field as Flutter reports it: the value, then ``on_change``."""
    text_field = cast(
        ft.TextField, identified(render())["developer.mock_api_url"].content
    )
    text_field.value = text
    cast(Callable[[object], None], text_field.on_change)(
        SimpleNamespace(control=text_field)
    )


async def press(render: Callable[[], ft.Column], identifier: str) -> None:
    """Render, then click the button or row under ``identifier`` and await it."""
    control = cast(Any, identified(render())[identifier].content)
    await control.on_click()


def outcome(render: Callable[[], ft.Column]) -> str | None:
    """The words of the section's outcome line, or None while it is hidden."""
    line = identified(render())["developer.mock_api_outcome"]
    assert line.live_region is True  # announced when it changes
    if not line.visible:
        return None
    row = cast(ft.Row, cast(ft.Container, line.content).content)
    return str(cast(ft.Text, row.controls[1]).value)


def stored_dev(svc: Services) -> dict[str, Any]:
    """The Developer options as SharedPreferences holds them."""
    return json.loads(cast(MemoryPrefs, svc.storage.prefs).values["pycon.dev"])


def test_with_no_url_there_is_a_labelled_field_and_no_check(
    render: Callable[[], ft.Column], svc: Services
) -> None:
    """Without a URL: the field, Clear and Save, a hidden outcome, no check, no client."""
    nodes = identified(render())
    assert set(nodes) == {
        "developer.mock_api_url",
        "developer.mock_api_clear",
        "developer.mock_api_save",
        "developer.mock_api_outcome",
    }
    text_field = cast(ft.TextField, nodes["developer.mock_api_url"].content)
    assert text_field.label == "Mock API base URL"
    assert text_field.keyboard_type == ft.KeyboardType.URL
    helper = cast(ft.Text, text_field.helper).value
    assert "http://10.0.2.2:8000" in str(helper) and "http://localhost:8000" in str(
        helper
    )
    assert outcome(render) is None
    assert svc.api is None


async def test_save_builds_the_client_keeps_the_url_and_shows_the_check(
    render: Callable[[], ft.Column], svc: Services, prefs: Prefs
) -> None:
    """Save checks the URL, builds the client on it, stores it and says so."""
    await type_url(render, f"{MOCK}/")
    await press(render, "developer.mock_api_save")
    assert svc.private_api.base_url == MOCK and svc.api is not None
    assert stored_dev(svc) == {"unlocked": True, "mock_api_url": MOCK}
    assert prefs.private_api_enabled is True
    assert outcome(render) == (
        "Saved: sign-in and the staff tools use the mock at this address."
    )
    check = cast(ft.ListTile, identified(render())["developer.mock_api_check"].content)
    assert cast(ft.Text, check.subtitle).value == MOCK  # the address it checks


async def test_the_check_says_connected_and_is_announced(
    render: Callable[[], ft.Column], recorder: Recorder
) -> None:
    """Check mock connection sends one request and says the mock answered."""
    await type_url(render, MOCK)
    await press(render, "developer.mock_api_save")
    await press(render, "developer.mock_api_check")
    assert outcome(render) == CONNECTED
    assert len(recorder.sent) == 1


async def test_clear_turns_the_private_api_off_again(
    render: Callable[[], ft.Column], svc: Services, prefs: Prefs
) -> None:
    """Clear empties the field, drops the client and the URL, and hides the check."""
    await type_url(render, MOCK)
    await press(render, "developer.mock_api_save")
    await press(render, "developer.mock_api_clear")
    assert svc.api is None
    assert prefs.private_api_enabled is False
    assert stored_dev(svc) == {"unlocked": True}
    nodes = identified(render())
    assert "developer.mock_api_check" not in nodes
    assert cast(ft.TextField, nodes["developer.mock_api_url"].content).value == ""
    assert outcome(render) == "Cleared: sign-in and the staff tools are off."


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("10.0.2.2:8000", "Use an http:// or https:// address"),
        ("https://us.pycon.org", "That is the PSF's server. Use the mock's address"),
    ],
)
async def test_a_wrong_url_is_the_field_s_error_and_saves_nothing(
    render: Callable[[], ft.Column], svc: Services, text: str, error: str
) -> None:
    """A URL that is not http(s), or is the PSF's, stays an error; no client, no save."""
    await type_url(render, text)
    await press(render, "developer.mock_api_save")
    text_field = cast(
        ft.TextField, identified(render())["developer.mock_api_url"].content
    )
    assert text_field.error == error
    assert svc.api is None
    assert "pycon.dev" not in cast(MemoryPrefs, svc.storage.prefs).values
    await type_url(render, MOCK)  # an edit clears the error
    text_field = cast(
        ft.TextField, identified(render())["developer.mock_api_url"].content
    )
    assert text_field.error is None


async def test_reset_app_leaves_no_client(
    svc: Services, prefs: Prefs, offline: list[str]
) -> None:
    """Reset app turns the private API off with the rest of the Developer options."""
    await svc.private_api.connect(MOCK, 2026)
    conference = Conference()
    await conference.load_local(svc.storage, svc.year)
    await reset_app(svc, conference, prefs, Favorites(loaded=True))
    assert svc.api is None
    assert prefs.private_api_enabled is False
