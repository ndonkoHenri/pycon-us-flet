"""Developer › Data's staff data: Clear staff data and Reset app's warning (#695, D-414).

``ClearStaffData`` and ``DataActions`` run outside a renderer, their hooks replaced
(``tests/data_section.py``'s hand renderer); the rows are seeded into a real
``outbox.db``. How the rows and the confirmations look is checked on devices (the PR).
"""

import inspect
from collections.abc import Callable, Iterator
from dataclasses import replace
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.core import outbox
from pycon_us.core.outbox import Status
from pycon_us.prefs import DEV_MOCK_API_URL, Prefs
from pycon_us.screens import developer_staff
from pycon_us.screens.developer_staff import (
    STAFF_CLEARED,
    ClearStaffData,
    clear_line,
)
from pycon_us.screens.developer_ui import UNREADABLE, confirmation, staff_confirmation
from pycon_us.services import Services
from pycon_us.services.outbox_db import Counts, OutboxDb
from pycon_us.services.storage import STAFF_PREFIX, Storage
from pycon_us.staff import Staff
from pycon_us.theme import LIGHT_TOKENS
from tests import data_section
from tests.data_section import Rendered, identified, press, tap
from tests.fakes import MemoryPrefs

(
    real_time,
    offline,
    page,
    svc,
    stored,
    prefs,
    conference,
    favorites,
    account,
    staff,
    packaged,
    rendered,
    minutes,
    render,
) = (
    data_section.real_time,
    data_section.offline,
    data_section.page,
    data_section.svc,
    data_section.stored,
    data_section.prefs,
    data_section.conference,
    data_section.favorites,
    data_section.account,
    data_section.staff,
    data_section.packaged,
    data_section.rendered,
    data_section.minutes,
    data_section.render,
)

A = "a@example.com"
B = "b@example.com"


def seed(db: OutboxDb, owner: str, *statuses: Status) -> None:
    """Store one lead row of ``owner``'s in each of ``statuses``."""
    for status in statuses:
        code = f"{owner[0]}{len(db.rows(owner, tuple(Status)) or [])}"
        decide = partial(
            outbox.scan_lead,
            owner=owner,
            code=code,
            payload={"badge_validator": "v"},
            sponsor_id=None,
            sponsor_name=None,
            now=1.0,
        )
        enqueued = db.enqueue(code, decide)
        assert enqueued is not None and enqueued.row is not None
        if status is not Status.PENDING:
            assert db.save(replace(enqueued.row, status=status))


def lines(dialog: ft.AlertDialog) -> list[str]:
    """The words of a confirmation's lines under its first, one per loss."""
    return [
        str(cast(ft.Text, cast(ft.Row, line).controls[1]).value)
        for line in cast(ft.Column, dialog.content).controls[1:]
    ]


def confirm(dialog: ft.AlertDialog, identifier: str) -> ft.TextButton:
    """A confirmation's confirm button."""
    button = identified(dialog)[f"{identifier}.confirm"]
    assert isinstance(button, ft.TextButton)
    return button


# ------------------------------------------------------------------ the confirmation


def test_the_confirmation_names_every_loss_and_the_unsynced_count() -> None:
    """Unsynced records: the button says how many, in ``error`` (DEV-03)."""
    dialog = staff_confirmation(
        Counts(pending=2, failed=1, synced=12),
        on_confirm=lambda: None,
        on_cancel=lambda: None,
    )
    assert dialog.title == ft.Text("Clear staff data?")
    assert lines(dialog) == [
        (
            "The staff records: 12 synced, 3 not synced yet. The ones not synced "
            "never reach the server"
        ),
        "The scanner consent",
        "The sponsor chosen to scan for",
    ]
    button = confirm(dialog, "developer.clear_staff_data")
    assert button.content == "Delete 3 unsynced records too"
    assert button.style == ft.ButtonStyle(color=ft.Colors.ERROR)


def test_without_unsynced_records_the_button_says_clear() -> None:
    """Every record synced: nothing is lost that the server lacks."""
    dialog = staff_confirmation(
        Counts(synced=4), on_confirm=lambda: None, on_cancel=lambda: None
    )
    assert confirm(dialog, "developer.clear_staff_data").content == "Clear"
    one = staff_confirmation(
        Counts(pending=1), on_confirm=lambda: None, on_cancel=lambda: None
    )
    button = confirm(one, "developer.clear_staff_data")
    assert button.content == "Delete 1 unsynced record too"


def test_records_that_can_t_be_read_can_t_be_cleared() -> None:
    """No count, no deletion: the button is disabled and the dialog says why."""
    dialog = staff_confirmation(None, on_confirm=lambda: None, on_cancel=lambda: None)
    assert lines(dialog)[0] == UNREADABLE
    assert confirm(dialog, "developer.clear_staff_data").disabled


# ------------------------------------------------------------------ the row


@pytest.fixture
def db(tmp_path: Path) -> Iterator[OutboxDb]:
    """Yield an empty outbox in its own directory, closed afterwards."""
    directory = tmp_path / "outbox"
    directory.mkdir()
    database = OutboxDb(directory)
    yield database
    database.close()


@pytest.fixture
def shared() -> MemoryPrefs:
    """The session's SharedPreferences, with a staff key and a setting."""
    prefs = MemoryPrefs()
    prefs.values.update({"pycon.staff_sponsor": "{}", "pycon.theme": "dark"})
    return prefs


@pytest.fixture
def clear(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    db: OutboxDb,
    shared: MemoryPrefs,
    rendered: Rendered,
    staff: Staff,
) -> Callable[..., ft.Control]:
    """Render ``ClearStaffData`` for a mock URL or none; return its control."""

    def render(*, mock: bool = True) -> ft.Control:
        """Render it again, with its state kept in ``rendered``."""
        prefs = Prefs(loaded=True, dev={DEV_MOCK_API_URL: "http://10.0.2.2:8000"})
        if not mock:
            prefs = Prefs(loaded=True)
        services = SimpleNamespace(
            outbox=db, storage=Storage(prefs=shared, directory=tmp_path, year=2026)
        )
        for name, value in (
            ("use_prefs", prefs),
            ("use_services", services),
            ("use_staff", staff),
            ("use_tokens", LIGHT_TOKENS),
        ):
            monkeypatch.setattr(developer_staff, name, lambda value=value: value)
        monkeypatch.setattr(ft, "use_state", rendered.use_state)
        monkeypatch.setattr(ft, "use_dialog", rendered.dialogs.append)
        monkeypatch.setattr(ft, "use_memo", lambda fn, _deps: fn())
        rendered.index = 0
        return inspect.unwrap(ClearStaffData)()

    return render


def outcome(control: ft.Control) -> str | None:
    """The words of the line under the row, or None while it is hidden."""
    line = identified(control)["developer.staff_outcome"]
    found = [
        str(c.value)
        for c in cast(ft.Row, cast(ft.Container, line).content).controls
        if isinstance(c, ft.Text)
    ]
    parent = next(
        c
        for c in cast(ft.Column, control).controls
        if isinstance(c, ft.Semantics) and c.identifier == "developer.staff_outcome"
    )
    return found[0] if parent.visible else None


def test_without_a_mock_api_url_the_row_is_not_there(
    clear: Callable[..., ft.Control], db: OutboxDb
) -> None:
    """Staff features hide without the mock (D-51), and outbox.db stays unopened."""
    assert clear(mock=False).visible is False
    assert not db.path.exists()


def test_the_row_says_how_many_records_wait(db: OutboxDb) -> None:
    """Its second line counts every account's unsynced records."""
    seed(db, A, Status.PENDING, Status.FAILED, Status.SYNCED)
    seed(db, B, Status.PENDING)
    assert clear_line(db) == (
        "Every account's records (3 not synced), the consent and the sponsor"
    )
    db.close()
    assert "(can't be read)" in clear_line(db)


async def test_clear_staff_data_asks_then_deletes_every_account_s_staff_data(
    clear: Callable[..., ft.Control],
    rendered: Rendered,
    db: OutboxDb,
    shared: MemoryPrefs,
    staff: Staff,
) -> None:
    """Cancel deletes nothing; confirming deletes the rows and keys, and says so."""
    staff.pending, staff.failed = 1, 1  # the signed-in account's, A's
    seed(db, A, Status.PENDING, Status.SYNCED)
    seed(db, B, Status.FAILED)
    row = identified(clear())["developer.clear_staff_data"]
    cast(Callable[[], None], cast(ft.ListTile, row).on_click)()
    clear()
    dialog = rendered.dialog
    assert dialog is not None
    assert confirm(dialog, "developer.clear_staff_data").content == (
        "Delete 2 unsynced records too"
    )
    await press(dialog, "developer.clear_staff_data.cancel")
    clear()
    assert rendered.dialog is None and db.counts(None) == Counts(1, 1, 1)
    cast(Callable[[], None], cast(ft.ListTile, row).on_click)()
    clear()
    await press(rendered.dialog, "developer.clear_staff_data.confirm")
    control = clear()
    assert rendered.dialog is None
    assert db.counts(None) == Counts()
    assert not [key for key in shared.values if key.startswith(STAFF_PREFIX)]
    assert shared.values["pycon.theme"] == "dark"
    assert (staff.pending, staff.failed) == (0, 0)
    assert outcome(control) == STAFF_CLEARED[0]


# ------------------------------------------------------------------ Reset app


def test_reset_names_the_staff_records_and_their_unsynced_count() -> None:
    """Reset app warns as Clear staff data does: its button says how many (D-414)."""
    dialog = confirmation(
        "reset",
        saved=0,
        packaged=False,
        snapshot_day="",
        staff=Counts(pending=2, synced=5),
        on_confirm=lambda: None,
        on_cancel=lambda: None,
    )
    assert dialog is not None
    assert lines(dialog)[-1] == "Staff records: 5 synced, 2 not synced yet"
    button = confirm(dialog, "developer.reset_app")
    assert button.content == "Delete 2 unsynced records too"
    plain = confirmation(
        "reset",
        saved=0,
        packaged=False,
        snapshot_day="",
        staff=Counts(),
        on_confirm=lambda: None,
        on_cancel=lambda: None,
    )
    assert plain is not None and len(lines(plain)) == 5  # no staff line without any
    assert confirm(plain, "developer.reset_app").content == "Reset app"


async def test_reset_app_deletes_the_staff_records_after_naming_them(
    render: Callable[[], ft.Column],
    rendered: Rendered,
    svc: Services,
    stored: dict[str, Any],
    offline: list[str],
) -> None:
    """The dialog counts every account's rows; confirming deletes them and the keys."""
    assert svc.outbox is not None
    seed(svc.outbox, A, Status.PENDING, Status.SYNCED)
    stored["pycon.staff_sponsor"] = "{}"
    await tap(render, "developer.reset_app")
    render()
    dialog = rendered.dialog
    assert dialog is not None
    assert lines(dialog)[-1] == "Staff records: 1 synced, 1 not synced yet"
    await press(dialog, "developer.reset_app.confirm")
    assert svc.outbox.counts(None) == Counts()
    assert "pycon.staff_sponsor" not in stored
