"""Tests for Door check's tags and headcount (#767; DOOR-05, DOOR-06; D-442).

`core/admission.tags()` turns an attendee's allergy and dietary needs into the
result's chips, and `headcount()` counts the account's distinct check-ins for the
session from its door rows. On the screen (`tests/door_rig.py`: a real Flet session
over the mock, one outbox per test, so a second render is a relaunch), each seed
attendee's result carries their chips, and "1 checked in" under the session chip
follows the admissions, ignores a duplicate, survives a relaunch and comes back with
its session.
"""

from dataclasses import replace

import flet as ft
import pytest

from pycon_us.core.admission import Attendee, headcount, tags
from pycon_us.core.badges import Tag
from pycon_us.core.door_sessions import DoorChoice
from pycon_us.core.outbox import Kind, Status
from pycon_us.door_check import ALREADY, CHECKED_IN
from pycon_us.screens.door_headcount import (
    UNAVAILABLE,
    WORDS,
    WORDS_SIZE,
    headcount_line,
    headcount_words,
    read_headcount,
)
from pycon_us.ui import scan_screen
from tests import door_rig
from tests.door_rig import ASYNC, VIEW, Show
from tests.harness import Shown
from tests.scan_rig import enter, panel
from tests.test_admission import door_row

stored, switch, show = door_rig.stored, door_rig.switch, door_rig.show

DECORATORS = DoorChoice(1, (10,), "All about decorators \N{MIDDLE DOT} Wed 9:00 AM")
TUTORIALS = DoorChoice(1, (10, 11), "Tutorials")
ALLERGY = Tag("Allergy", warning=True)


def count(shown: Shown) -> str:
    """What the headcount's one node says."""
    node = shown.node("door.headcount")
    assert node.container and not node.live_region  # not said after every scan
    return str(node.label)


# ------------------------------------------------------------------ the rules


@pytest.mark.parametrize(
    ("attendee", "expected"),
    [
        (Attendee("A", dietary="vegetarian"), (Tag("Vegetarian"),)),
        (
            Attendee("G", has_allergy=True, allergy="peanuts"),
            (Tag("Allergy: peanuts", warning=True),),
        ),
        (Attendee("L", dietary="vegan", has_allergy=True), (ALLERGY, Tag("Vegan"))),
        (Attendee("M"), ()),
        (Attendee("X", allergy="sesame"), (Tag("Allergy: sesame", warning=True),)),
    ],
    ids=["diet", "named-allergy", "allergy-and-diet", "none", "allergy-without-flag"],
)
def test_an_attendee_s_tags_put_the_allergy_first(
    attendee: Attendee, expected: tuple[Tag, ...]
) -> None:
    """An allergy is a warning first, "Allergy: x" or "Allergy"; then the diet."""
    assert tags(attendee) == expected


def test_the_headcount_counts_distinct_codes_for_the_session_s_products() -> None:
    """Distinct codes of any status count; another session or a lead row doesn't."""
    rows = [
        door_row("A", 10),
        door_row("B", 10, 11, status=Status.SYNCED),
        door_row("C", 11, status=Status.FAILED),
        door_row("A", 11),  # A again, for the other tutorial
        door_row("D", 20),  # the summit
        replace(door_row("E", 10), kind=Kind.LEAD),
    ]
    assert headcount(rows, (10, 11)) == 3
    assert headcount(rows, (10,)) == 2
    assert headcount(rows, (20,)) == 1
    assert headcount([], (10,)) == 0


def test_a_failed_read_is_never_shown_as_zero() -> None:
    """No outbox: None, said as "unavailable" (D-120); no session: 0 without a read."""
    assert read_headcount(None, "staff@example.com", (10,)) is None
    assert read_headcount(None, "staff@example.com", ()) == 0
    assert headcount_words(None) == UNAVAILABLE
    assert headcount_words(1234) == "1,234 checked in"


def test_only_the_number_takes_the_display_size() -> None:
    """The words are smaller, so "checked" isn't split at iOS's largest text (#828)."""
    node = headcount_line(1234)
    assert isinstance(node, ft.Semantics)
    assert node.label == "1,234 checked in for this session"
    text = node.content
    assert isinstance(text, ft.Text) and text.spans
    assert text.value == "1,234"
    assert text.theme_style == ft.TextThemeStyle.DISPLAY_SMALL
    (words,) = text.spans
    assert words.text == WORDS
    assert words.style and words.style.size == WORDS_SIZE


# ------------------------------------------------------------------ the screen


async def test_each_seed_attendee_shows_their_chips(
    show: Show, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each seed attendee's chips show, and a rescan of Grace keeps her allergy.

    Ada is vegetarian, Grace "Allergy: peanuts", Linus "Allergy" and vegan.
    """
    now = [100.0]
    monkeypatch.setattr(scan_screen, "clock", lambda: now[0])
    shown = await show(VIEW, chosen=TUTORIALS)
    await enter(shown, "MOCK0001:v4l1d01")
    assert panel(shown) == f"{CHECKED_IN}\nAda Example\nVegetarian.\nScan 1"
    await enter(shown, "MOCK0002:v4l1d02")
    assert panel(shown) == f"{CHECKED_IN}\nGrace Sample\nAllergy: peanuts.\nScan 2"
    await enter(shown, "MOCK0003:v4l1d03")
    assert panel(shown) == (
        f"{CHECKED_IN}\nLinus Placeholder\nAllergy. Vegan.\nAdmits 2\nScan 3"
    )
    now[0] += 5
    await enter(shown, "MOCK0002:v4l1d02")
    assert panel(shown) == f"{ALREADY}\nGrace Sample\nAllergy: peanuts.\nScan 4"
    assert count(shown) == "3 checked in for this session"


async def test_the_headcount_follows_admissions_and_outlives_a_relaunch(
    show: Show, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The count follows admissions only, and outlives a relaunch (D-442).

    0, then 1 after Grace; a duplicate keeps 1; a relaunch shows 1; another session
    has its own count, and choosing Async again brings its 1 back.
    """
    now = [100.0]
    monkeypatch.setattr(scan_screen, "clock", lambda: now[0])
    shown = await show(VIEW, chosen=ASYNC)
    assert count(shown) == "0 checked in for this session"
    await enter(shown, "MOCK0002:v4l1d02")
    assert count(shown) == "1 checked in for this session"
    now[0] += 5
    await enter(shown, "MOCK0002:v4l1d02")
    assert panel(shown).startswith(ALREADY)
    assert count(shown) == "1 checked in for this session"
    relaunched = await show(VIEW, chosen=ASYNC)
    assert count(relaunched) == "1 checked in for this session"
    other = await show(VIEW, chosen=DECORATORS)
    assert count(other) == "0 checked in for this session"
    again = await show(VIEW, chosen=ASYNC)
    assert count(again) == "1 checked in for this session"
