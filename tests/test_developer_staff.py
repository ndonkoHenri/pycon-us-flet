"""Developer › Data's Staff queue row: when it shows, what it says, what it opens (#694).

``StaffQueue`` runs outside a renderer: its hooks are replaced, and the sheet's own hook
(``use_queue_sheet()``, whose sheet ``test_queue_sheet.py`` checks) by an opener that
counts its calls. The rows are seeded into a real ``outbox-<year>.db``.
"""

import inspect
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.account import Account
from pycon_us.core import outbox_enqueue
from pycon_us.dev_options import DEV_MOCK_API_URL
from pycon_us.prefs import Prefs
from pycon_us.screens import developer_staff
from pycon_us.screens.developer_staff import (
    IDENTIFIER,
    StaffQueue,
    others_line,
    others_waiting,
)
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.staff import Staff
from pycon_us.theme import LIGHT_TOKENS
from pycon_us.ui.queue_sheet import QueueSheet

OWNER = "staff@example.com"
OTHER = "door@example.com"


@pytest.fixture
def db(tmp_path: Path) -> Iterator[OutboxDb]:
    """Yield an empty outbox in its own directory, closed afterwards."""
    database = OutboxDb(tmp_path, 2026)
    yield database
    database.close()


def seed(db: OutboxDb, code: str, owner: str) -> None:
    """Store a pending lead row of ``owner``'s for ``code``."""
    decide = partial(
        outbox_enqueue.scan_lead,
        owner=owner,
        code=code,
        payload={"badge_validator": "v"},
        sponsor_id=None,
        sponsor_name=None,
        now=1.0,
    )
    assert db.enqueue(code, decide) is not None


def test_other_accounts_waiting_rows_are_counted_without_the_account_s(
    db: OutboxDb,
) -> None:
    """Every other owner's pending and failed rows; signed out, every owner's."""
    seed(db, "A1", OWNER)
    seed(db, "B1", OTHER)
    seed(db, "B2", OTHER)
    assert others_waiting(db, OWNER) == 2
    assert others_waiting(db, None) == 3
    db.close()
    assert others_waiting(db, OWNER) is None  # a failed read, logged (D-120)


@pytest.mark.parametrize(
    ("count", "line"),
    [
        (0, None),
        (1, "1 row of other accounts waiting"),
        (4, "4 rows of other accounts waiting"),
        (None, "Couldn't read the queue."),
    ],
)
def test_the_line_about_other_accounts(count: int | None, line: str | None) -> None:
    """Nothing when none wait; a count otherwise; a failed read said as one."""
    assert others_line(count) == line


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch, db: OutboxDb
) -> Callable[..., tuple[ft.Control, list[int]]]:
    """Render ``StaffQueue`` for an account and a mock URL; return it and the opens."""

    def render(
        *, signed_in: bool = True, mock: bool = True, staff: Staff | None = None
    ) -> tuple[ft.Control, list[int]]:
        opened: list[int] = []
        account = Account(restored=True, signed_in=signed_in, email=OWNER)
        prefs = Prefs(
            loaded=True, dev={DEV_MOCK_API_URL: "http://10.0.2.2:8000"} if mock else {}
        )
        svc = SimpleNamespace(outbox=db)
        for name, value in (
            ("use_prefs", prefs),
            ("use_services", svc),
            ("use_staff", staff or Staff(pending=3)),
            ("use_account", account),
            ("use_tokens", LIGHT_TOKENS),
        ):
            monkeypatch.setattr(developer_staff, name, lambda value=value: value)
        monkeypatch.setattr(
            developer_staff,
            "use_queue_sheet",
            lambda **_: QueueSheet(lambda: opened.append(1), is_open=False),
        )
        monkeypatch.setattr(ft, "use_memo", lambda fn, _deps: fn())
        return inspect.unwrap(StaffQueue)(), opened

    return render


def texts(control: Any) -> list[str]:
    """Every text's words and every semantics label below ``control``, in order."""
    found = []
    if isinstance(control, ft.Text):
        found.append(str(control.value))
    if isinstance(control, ft.Semantics) and control.label:
        found.append(control.label)
    for name in ("content", "controls", "title", "subtitle"):
        child = getattr(control, name, None)
        for item in child if isinstance(child, list) else [child]:
            if isinstance(item, ft.Control):
                found += texts(item)
    return found


def tile(control: ft.Control) -> ft.ListTile:
    """The row's tile under its merged identifier."""
    assert isinstance(control, ft.MergeSemantics)
    named = control.content
    assert isinstance(named, ft.Semantics) and named.identifier == IDENTIFIER
    assert isinstance(named.content, ft.ListTile)
    return named.content


def test_without_a_mock_api_url_the_row_is_not_there(
    render: Callable[..., tuple[ft.Control, list[int]]],
) -> None:
    """Staff features hide without the mock (D-51), and the outbox stays unopened."""
    control, _ = render(mock=False)
    assert control.visible is False


def test_the_row_shows_the_chip_and_other_accounts_and_opens_the_sheet(
    render: Callable[..., tuple[ft.Control, list[int]]], db: OutboxDb
) -> None:
    """Its second line is the chip's words, then other accounts' rows; a tap opens."""
    seed(db, "B1", OTHER)
    control, opened = render(staff=Staff(pending=3, failed=1))
    row = tile(control)
    assert texts(row) == [
        "Staff queue",
        "3 pending · 1 failed",  # the chip, its words alone for a screen reader
        "1 row of other accounts waiting",
    ]
    cast(Callable[[], None], row.on_click)()
    assert opened == [1]


def test_signed_out_the_row_says_so_instead_of_a_chip(
    render: Callable[..., tuple[ft.Control, list[int]]],
) -> None:
    """The cleared store would say "All synced" of nobody's rows."""
    control, _ = render(signed_in=False, staff=Staff())
    assert texts(tile(control)) == ["Staff queue", "Not signed in"]
