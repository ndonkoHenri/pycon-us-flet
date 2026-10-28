"""Tests for where the app opens a lead-retrieval account: the Start screen (#689).

D-16: a cold start of a ``lead_retrieval`` account opens the Lead scanner unless
Settings' "Open the app on" says Now; door-check-only staff and everyone else open
Now. ``start_target()`` and ``starts_on_lead()`` are pure, tested on every combination;
``Start`` is run outside a renderer, as in ``test_routes_locations.py``. The landing
after a sign-in is ``test_sign_in.py``'s, the Settings rows ``test_settings.py``'s.
"""

import inspect
import itertools
from collections.abc import Callable
from types import SimpleNamespace

import flet as ft
import pytest

from pycon_us import routes
from pycon_us.account import Account
from pycon_us.core.staff_tools import TOOLS, ToolKey, starts_on_lead
from pycon_us.locations import (
    LEAD_SCANNER,
    PAGES,
    WELCOME,
    lands_on_lead,
    launch_target,
    parent_of,
    start_target,
)
from pycon_us.memory import ViewMemory
from pycon_us.prefs import DEV_MOCK_API_URL, START_SCREENS, Prefs, StartScreen
from tests.fake_page import FakePage, bound

FLAG_NAMES = ("lead_retrieval", "door_check", "mask_violation")
"""The role flags ``Account.role_flags`` gives, as ``starts_on_lead()`` takes them."""

MOCK = {DEV_MOCK_API_URL: "http://127.0.0.1:8080"}
"""Developer options with a mock URL set: the staff tools show (D-51)."""

SEARCH_BASE = "/schedule/session/42"
"""Where Search was opened from, for the targets that read it."""


def every_flag_set() -> list[dict[str, bool]]:
    """Every combination of the three role flags, all off to all on."""
    return [
        dict(zip(FLAG_NAMES, values, strict=True))
        for values in itertools.product([False, True], repeat=len(FLAG_NAMES))
    ]


def sponsor(**changes: object) -> Account:
    """A signed-in account with ``lead_retrieval`` only, as the seeded sponsor."""
    fields: dict[str, object] = {
        "restored": True,
        "signed_in": True,
        "lead_retrieval": True,
    }
    return Account(**{**fields, **changes})  # type: ignore[arg-type]


# ------------------------------------------------------------------ the pure rule


@pytest.mark.parametrize("flags", every_flag_set())
@pytest.mark.parametrize("setting", START_SCREENS)
def test_only_lead_retrieval_opens_on_the_scanner_unless_the_setting_says_now(
    flags: dict[str, bool], setting: StartScreen
) -> None:
    """``lead_retrieval`` opens on the scanner under ``auto`` and ``lead``, never ``now``.

    Door-check-only staff, who may open the scanner too, and every other account
    open on Now (architecture §12.4).
    """
    assert starts_on_lead(flags, setting) is (
        flags["lead_retrieval"] and setting != "now"
    )


def test_an_absent_or_untrue_flag_is_off() -> None:
    """A flag the server left out, or anything but True, never opens the scanner."""
    assert not starts_on_lead({}, "lead")
    assert not starts_on_lead({"lead_retrieval": 1}, "auto")


@pytest.mark.parametrize("lead", [False, True])
@pytest.mark.parametrize("onboarded", [False, True])
@pytest.mark.parametrize(
    "last_location", ["", "/now/session/42", "/more/settings", "/search?scope=places"]
)
def test_the_start_target_for_every_lead_start_onboarding_and_location(
    lead: bool, onboarded: bool, last_location: str
) -> None:
    """Welcome first (D-287), then where the user was (D-143), then the cold start's.

    Only a cold start, with no location yet, opens the Lead scanner: a new session in
    the same process rebuilds the user's stack, as for everyone.
    """
    if not onboarded:
        target = WELCOME
    elif last_location.startswith("/search"):
        target = SEARCH_BASE
    elif last_location:
        target = last_location
    else:
        target = LEAD_SCANNER if lead else "/now"
    assert (
        start_target(last_location, SEARCH_BASE, onboarded=onboarded, lead=lead)
        == target
    )


def test_a_reminder_tap_wins_over_the_lead_start() -> None:
    """A tapped reminder opens its route, as a link does, even for a sponsor (D-396)."""
    tap = "/my-schedule/session/142"
    assert launch_target(tap, "", SEARCH_BASE, onboarded=True, lead=True) == tap
    assert launch_target("", "", SEARCH_BASE, onboarded=True, lead=True) == (
        LEAD_SCANNER
    )


def test_the_lead_scanner_is_the_staff_tool_s_page_under_more() -> None:
    """The start lands on the Lead scanner's own route, whose Back returns to More."""
    (lead,) = [tool for tool in TOOLS if tool.key is ToolKey.LEAD]
    assert lead.route == LEAD_SCANNER
    assert LEAD_SCANNER in PAGES
    assert parent_of(LEAD_SCANNER) == "/more"


@pytest.mark.parametrize(
    ("dev", "account", "setting", "lands"),
    [
        (MOCK, sponsor(), "auto", True),  # the default for a sponsor
        (MOCK, sponsor(), "lead", True),
        (MOCK, sponsor(), "now", False),  # switched off in Settings
        ({}, sponsor(), "auto", False),  # no mock URL: the scanner isn't there (D-51)
        (MOCK, sponsor(lead_retrieval=False, door_check=True), "auto", False),
        (MOCK, sponsor(lead_retrieval=False), "lead", False),  # an attendee
        (MOCK, Account(restored=True), "lead", False),  # signed out
    ],
)
def test_a_cold_start_or_sign_in_lands_on_the_scanner_only_for_a_sponsor(
    dev: dict[str, str], account: Account, setting: StartScreen, lands: bool
) -> None:
    """``lands_on_lead()`` reads the setting, the account's flags and the mock URL."""
    prefs = Prefs(dev=dev, start_screen=setting)
    assert lands_on_lead(prefs, account) is lands


# ------------------------------------------------------------------ Start


def started(
    monkeypatch: pytest.MonkeyPatch,
    account: Account,
    *,
    setting: StartScreen = "auto",
    last_location: str = "",
    route: str = "/",
) -> list[str]:
    """Run ``Start`` once, at ``route``, and return where it navigated.

    Args:
        monkeypatch: Replaces ``Start``'s hooks.
        account: The restored account.
        setting: ``Prefs.start_screen``.
        last_location: ``ViewMemory.last_location``; empty on a cold start.
        route: The page's route: ``/`` for a plain start, a link's for a link start.
    """
    memory = ViewMemory(last_location=last_location)
    prefs = Prefs(onboarded=True, dev=MOCK, start_screen=setting, loaded=True)
    effects: list[Callable[[], None]] = []
    monkeypatch.setattr(
        routes, "use_services", lambda: SimpleNamespace(memory=memory, reminders=None)
    )
    monkeypatch.setattr(routes, "use_prefs", lambda: prefs)
    monkeypatch.setattr(routes, "use_account", lambda: account)
    monkeypatch.setattr(
        ft, "use_effect", lambda setup, deps=None: effects.append(setup)
    )
    page = FakePage()
    page.route = route
    with bound(page):
        inspect.unwrap(routes.Start)()
        (go,) = effects
        go()
    return page.navigated


@pytest.mark.parametrize(
    ("account", "setting", "target"),
    [
        (sponsor(), "auto", LEAD_SCANNER),
        (sponsor(), "now", "/now"),
        (sponsor(lead_retrieval=False, door_check=True), "auto", "/now"),
        (sponsor(lead_retrieval=False), "auto", "/now"),  # an attendee
    ],
)
def test_a_cold_start_opens_the_scanner_for_a_sponsor_and_now_for_others(
    monkeypatch: pytest.MonkeyPatch,
    account: Account,
    setting: StartScreen,
    target: str,
) -> None:
    """``Start`` reads the restored account and the setting the boot gate loaded."""
    assert started(monkeypatch, account, setting=setting) == [target]


def test_a_new_session_of_a_sponsor_returns_to_where_they_were(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An Android recreation rebuilds the stack, not the scanner (D-143)."""
    assert started(monkeypatch, sponsor(), last_location="/more/settings") == [
        "/more/settings"
    ]


def test_a_link_start_of_a_sponsor_opens_its_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A link start never reaches ``/``: ``Start`` below a modal stays put (D-287)."""
    assert started(monkeypatch, sponsor(), route="/search") == []
