"""Tests for what the staff flows expect of the app (#825).

``maestro/journeys/{lead_capture,door_check,swag_pickup}.yaml`` match the scan screen's
words by regular expression and find its controls by identifier. Those are written into
the YAML and run only on a device, so a reworded outcome or a renamed identifier would
fail weeks later, far from the PR that did it. These checks fail here instead: each
flow's expressions must match what the app's own code says about the mock's seed, as
Maestro matches them, whole.
"""

import json
import re
from dataclasses import replace
from pathlib import Path

import flet as ft

from pycon_us.core.admission import Attendee, Inventory
from pycon_us.core.badges import (
    COOLDOWN_SECONDS,
    NOT_A_BADGE,
    Badge,
    ScanOutcome,
    ScanResult,
)
from pycon_us.core.check_in import AttendeeProducts, Category, Item, RedeemReply
from pycon_us.core.outbox import Kind, Row
from pycon_us.core.staff_tools import ToolKey
from pycon_us.door_check import already, checked_in, not_registered
from pycon_us.door_inventory import Loaded
from pycon_us.lead_capture import ALREADY, CAPTURED, named
from pycon_us.screens.door_headcount import headcount_line
from pycon_us.screens.door_preload import Preload, spoken, status_words
from pycon_us.screens.more import SIGN_IN as SIGN_IN_ROW
from pycon_us.screens.staff_leads import button_label
from pycon_us.screens.staff_swag import CHOOSE
from pycon_us.staff import Staff
from pycon_us.swag import Offer, redeemed, result_of
from pycon_us.ui import scan_result
from pycon_us.ui.navigation import TABS
from pycon_us.ui.scan_result import age_line
from pycon_us.ui.swag_sheet import Handing, SheetActions, hand_out_words, swag_sheet
from pycon_us.ui.sync_chip import chip_words
from tests.filter_sheet import descendants

ROOT = Path(__file__).resolve().parent.parent
MAESTRO = ROOT / "maestro"
LEAD = MAESTRO / "journeys" / "lead_capture.yaml"
DOOR = MAESTRO / "journeys" / "door_check.yaml"
SWAG = MAESTRO / "journeys" / "swag_pickup.yaml"
COOLDOWN = MAESTRO / "subflows" / "past_cooldown.yaml"
SIGN_IN = MAESTRO / "subflows" / "sign_in_mock.yaml"

SEED = json.loads((ROOT / "tests/fixtures/mock/seed.json").read_text(encoding="utf-8"))
ATTENDEES = {person["access_code"]: person for person in SEED["attendees"]}
ADA, GRACE, LINUS, MARGARET = "MOCK0001", "MOCK0002", "MOCK0003", "MOCK0004"
SESSION = 10
"""The product of ``door.session.10``, the session ``door_check`` chooses."""

SWAG_CATEGORIES = tuple(
    Category(category["id"], category["name"])
    for category in SEED["categories"]
    if category["id"] in (3, 4)
)
"""``swag.category.3`` and ``.4``, the categories ``swag_pickup`` chooses."""

FIELD_TEXT = "not-a-badge"
"""What the flows send as not a badge: the panel shows it as the title (D-473)."""

TEXT = re.compile(r'^[ -]*text: (?:"(.*)"|(.*?))(?:\s+#.*)?$', re.MULTILINE)
"""A ``text:`` line, quoted or bare, with or without a comment after it."""

IDENTIFIER = re.compile(r"^[ -]*id: ([\w.]+)", re.MULTILINE)
"""An ``id:`` line."""


def patterns(flow: Path) -> list[str]:
    """Return the expressions in the flow's ``text:`` lines, as Maestro reads them.

    Args:
        flow: The flow's file; a double-quoted YAML string doubles its backslashes.
    """
    found = TEXT.findall(flow.read_text(encoding="utf-8"))
    return [quoted.replace("\\\\", "\\") or bare for quoted, bare in found]


def assert_expects(flow: Path, words: list[str]) -> None:
    """Assert that the flow's expressions and the app's ``words`` match, both ways.

    So a reworded outcome fails, and so does an expression added to the flow with
    nothing here to tie it to the app.

    Args:
        flow: The flow's file.
        words: What the app says at the flow's steps, whole.
    """
    expected = patterns(flow)
    for pattern in expected:
        assert any(re.fullmatch(pattern, line) for line in words), (
            f"{flow.name}: the app says nothing that matches {pattern!r}"
        )
    for line in words:
        assert any(re.fullmatch(pattern, line) for pattern in expected), (
            f"{flow.name}: no expression matches {line!r}"
        )


def panel(result: ScanResult) -> str:
    """Return ``scan.result``'s label for a result, which is what the flows match."""
    return scan_result.spoken(result, 1)


def attendee(code: str) -> Attendee:
    """Return the seed's attendee as the door's list holds them.

    Args:
        code: The attendee's access code.
    """
    person = ATTENDEES[code]
    return Attendee(
        code,
        person["full_name"],
        person["dietary"],
        person["has_allergy"],
        person["allergy"],
    )


def admitted(code: str) -> tuple[tuple[int, int], ...]:
    """Return the attendee's product and quantity for ``door_check``'s session.

    Args:
        code: The attendee's access code.
    """
    return ((SESSION, ATTENDEES[code]["products"][str(SESSION)]),)


def lead_row(code: str) -> Row:
    """Return a synced lead row holding the first name the mock's capture answers.

    Args:
        code: The attendee's access code.
    """
    answer = {"result": {"first_name": ATTENDEES[code]["first_name"]}}
    return Row(Kind.LEAD, code, answer, "sponsor@example.com", "1", None, 0, 0)


def products(code: str, *, left: bool) -> AttendeeProducts:
    """Return the attendee's swag as the mock's lookup answers, from the seed.

    Args:
        code: The attendee's access code.
        left: Whether the items are still there, or all picked up.
    """
    person = ATTENDEES[code]
    groups = []
    for category in SWAG_CATEGORIES:
        group = tuple(
            Item(
                product["id"],
                product["name"],
                person["products"][str(product["id"])] if left else 0,
                person["products"][str(product["id"])],
            )
            for product in SEED["products"]
            if product["category"] == category.id
            and str(product["id"]) in person["products"]
        )
        if group:
            groups.append((category.name, group))
    return AttendeeProducts(code, person["full_name"], tuple(groups))


def offer(code: str) -> Offer:
    """Return the offer a lookup makes the sheet, with the attendee's items left.

    Args:
        code: The attendee's access code.
    """
    validator = ATTENDEES[code]["validator"]
    return Offer(Badge(code, validator, validator), 0, products(code, left=True))


def sheet_title(code: str) -> str:
    """Return the first words on the hand-out sheet opened for the attendee.

    Args:
        code: The attendee's access code.
    """
    actions = SheetActions(print, print, print, print)
    sheet = swag_sheet(Handing(offer(code), frozenset()), actions)
    return next(c.value for c in descendants(sheet) if isinstance(c, ft.Text))


def headcount(count: int) -> str:
    """Return ``door.headcount``'s label for a count, which is what the flow matches.

    Args:
        count: How many are checked in.
    """
    line = headcount_line(count)
    assert isinstance(line, ft.Semantics)
    return str(line.label)


def age(seconds: int) -> str:
    """Return the panel's age line for a result that old.

    Args:
        seconds: The result's age.
    """
    line = age_line(seconds)
    assert isinstance(line, ft.Semantics)
    assert isinstance(line.content, ft.Text)
    return str(line.content.value)


def is_in_source(identifier: str, source: str) -> bool:
    """Return whether the app's code writes this identifier.

    One that ends in an id or a tool's key is built from that value, so its start is what
    is written: ``f"swag.item.{item.product_id}"``, or a ``PREFIX = "door.session"``.

    Args:
        identifier: The identifier a flow names.
        source: The app's code.
    """
    start, _, end = identifier.rpartition(".")
    if end.isdigit() or end in ToolKey:
        return f'f"{start}.{{' in source or f'"{start}"' in source
    return f'"{identifier}"' in source


def test_lead_capture_expects_the_app_s_words() -> None:
    """LEAD-01, LEAD-04: Ready, the count on the button, captured, already, not a badge."""
    assert_expects(
        LEAD,
        [
            scan_result.spoken(None),
            button_label(0),
            button_label(2),
            panel(named(ScanOutcome.ACCEPTED, CAPTURED, lead_row(ADA))),
            panel(named(ScanOutcome.ACCEPTED, CAPTURED, lead_row(GRACE))),
            panel(named(ScanOutcome.DUPLICATE, ALREADY, lead_row(ADA))),
            panel(replace(NOT_A_BADGE, title=FIELD_TEXT)),
            FIELD_TEXT,
        ],
    )


def test_door_check_expects_the_app_s_words() -> None:
    """DOOR-04: the list's count, the headcount, each outcome and "All synced".

    Ada comes with her dietary chip, Linus with "Admits 2", both from the seed.
    """
    bought = {code: dict(admitted(code)) for code in (ADA, LINUS)}
    loaded = Loaded(Inventory(quantities=bought), ())
    assert_expects(
        DOOR,
        [
            spoken(status_words(Preload(("staff", (SESSION,), 0), loaded=loaded))),
            headcount(0),
            headcount(2),
            panel(checked_in(attendee(ADA), admitted(ADA), offline=False)),
            panel(checked_in(attendee(LINUS), admitted(LINUS), offline=False)),
            panel(already(attendee(ADA))),
            panel(not_registered(MARGARET)),
            panel(replace(NOT_A_BADGE, title=FIELD_TEXT)),
            chip_words(Staff()),
        ],
    )


def test_swag_pickup_expects_the_app_s_words() -> None:
    """SHIRT-02: paused, the sheet and its button, each outcome.

    Grace has one item left, Ada three; Margaret bought nothing. The expression that
    takes the sheet or a rerun's "Already picked up" matches both.
    """
    handed = {30: 2, 40: 1}
    assert_expects(
        SWAG,
        [
            CHOOSE,
            sheet_title(GRACE),
            hand_out_words(1),
            panel(result_of(products(GRACE, left=True), SWAG_CATEGORIES)),
            hand_out_words(3),
            sheet_title(ADA),
            panel(redeemed(RedeemReply((), tuple(handed)), offer(ADA), handed)),
            panel(result_of(products(ADA, left=False), SWAG_CATEGORIES)),
            panel(result_of(products(MARGARET, left=False), SWAG_CATEGORIES)),
            panel(replace(NOT_A_BADGE, title=FIELD_TEXT)),
        ],
    )


def test_past_cooldown_waits_until_the_age_line_is_past_the_cooldown() -> None:
    """The subflow's expression takes 5 to 59 seconds: all past the 4 s cooldown."""
    [pattern] = patterns(COOLDOWN)
    taken = [second for second in range(120) if re.fullmatch(pattern, age(second))]
    assert taken == list(range(5, 60))
    assert taken[0] > COOLDOWN_SECONDS


def test_every_identifier_the_staff_flows_name_is_the_app_s() -> None:
    """D-33: a renamed identifier fails here, for the three flows and their sign-in.

    More's title and its Sign in row are built from their words, so those come from the
    objects that build them.
    """
    named_by_flows = {
        identifier
        for flow in (LEAD, DOOR, SWAG, SIGN_IN)
        for identifier in IDENTIFIER.findall(flow.read_text(encoding="utf-8"))
    }
    assert {"lead.consent.check", "door.preload", "swag.hand_out"} <= named_by_flows
    built = {SIGN_IN_ROW.identifier, *(tab.title_identifier for tab in TABS)}
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "src").rglob("*.py")
    )
    missing = {
        identifier
        for identifier in named_by_flows - built
        if not is_in_source(identifier, source)
    }
    assert not missing


def test_a_run_on_a_mock_just_started_can_make_the_hand_out_mandatory() -> None:
    """SHIRT-02: ``-e HAND_OUT=required`` waits for the sheet before the rerun's way out.

    Without it the flow also passes on "Already picked up", which is what a wrong lookup
    on a mock just started says too. The README says how to run it.
    """
    flow = SWAG.read_text(encoding="utf-8")
    required = (
        "      true: ${HAND_OUT == 'required'}\n"
        "    commands:\n"
        "      - extendedWaitUntil:\n"
        "          visible:\n"
        "            id: swag.hand_out\n"
    )
    assert required in flow
    assert flow.index(required) < flow.index("Already picked up.*Ada Example")
    readme = (MAESTRO / "README.md").read_text(encoding="utf-8")
    assert "-e HAND_OUT=required" in readme
