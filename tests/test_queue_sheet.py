"""The staff queue sheet: what it reads, what it shows and what its buttons do (#694).

The rows are seeded into a real ``outbox-<year>.db`` in a temporary directory. How the
sheet looks is checked on devices (the PR).
"""

from collections.abc import Callable, Iterator
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest
from flet.components.hooks.use_ref import MutableRef

from pycon_us.account import Account
from pycon_us.core import outbox
from pycon_us.core.outbox import Row, Status
from pycon_us.services import Services
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.staff import Staff
from pycon_us.theme import LIGHT_TOKENS
from pycon_us.ui.fold import COLLAPSED
from pycon_us.ui.queue_rows import CLOSE, EMPTY, RETRY_FAILED, SYNC_NOW
from pycon_us.ui.queue_sheet import (
    CONFIRMED_SHOWN,
    UNREADABLE,
    Queue,
    SheetState,
    kick_once,
    queue_sheet,
    read_queue,
    summary,
    sync_blocked,
)

OWNER = "staff@example.com"
OTHER = "door@example.com"
NOW = 1_000_000.0


@pytest.fixture
def db(tmp_path: Path) -> Iterator[OutboxDb]:
    """Yield an empty outbox in its own directory, closed afterwards."""
    database = OutboxDb(tmp_path, 2026)
    yield database
    database.close()


def seed(
    db: OutboxDb,
    code: str,
    *,
    owner: str = OWNER,
    at: float = NOW,
    status: Status = Status.PENDING,
    maybe_sent: bool = False,
) -> Row:
    """Store a lead row of ``owner``'s for ``code``, scanned at ``at``, in a status."""
    decide = partial(
        outbox.scan_lead,
        owner=owner,
        code=code,
        payload={"badge_validator": "v"},
        sponsor_id=None,
        sponsor_name=None,
        now=at,
    )
    enqueued = db.enqueue(code, decide)
    assert enqueued is not None and enqueued.row is not None
    row = enqueued.row
    if status is not Status.PENDING or maybe_sent:
        error = "Wrong badge validator." if status is Status.FAILED else None
        row = replace(row, status=status, last_error=error, maybe_sent=maybe_sent)
        assert db.save(row)
    return row


def walk(root: Any) -> Iterator[Any]:
    """Yield ``root`` and every control under it, through each slot a tile has."""
    yield root
    for name in ("content", "controls", "title", "subtitle", "leading", "trailing"):
        child = getattr(root, name, None)
        for item in child if isinstance(child, list) else [child]:
            if isinstance(item, ft.Control):
                yield from walk(item)


def identified(root: ft.Control) -> dict[str, Any]:
    """The control under each semantics identifier below ``root``."""
    return {
        c.identifier: c.content
        for c in walk(root)
        if isinstance(c, ft.Semantics) and c.identifier
    }


def words(control: Any) -> list[str]:
    """Every text's words below ``control``, in order."""
    return [str(c.value) for c in walk(control) if isinstance(c, ft.Text)]


def sheet(queue: Queue, staff: Staff | None = None, **state: Any) -> ft.BottomSheet:
    """Build the sheet for ``queue`` with no-op handlers."""
    return queue_sheet(
        queue,
        SheetState(staff or Staff(), NOW, **state),
        tokens=LIGHT_TOKENS,
        style=ft.Animation(0),
        on_sync_now=lambda: None,
        on_retry_failed=lambda: None,
        on_confirmed=lambda _open: None,
        on_close=lambda: None,
    )


# ------------------------------------------------------------------ reading


def test_the_owner_s_unsynced_rows_come_newest_first(db: OutboxDb) -> None:
    """Pending and failed rows, newest first; confirmed rows go to their own list."""
    seed(db, "A1", at=NOW)
    seed(db, "A2", at=NOW + 1, status=Status.FAILED)
    seed(db, "A3", at=NOW + 2, status=Status.SYNCED)
    queue = read_queue(db, OWNER, others=False)
    assert [row.key for row in queue.mine] == ["A2", "A1"]
    assert [row.key for row in queue.confirmed] == ["A3"]
    assert (queue.others, queue.readable) == ((), True)


def test_the_confirmed_fold_keeps_only_the_latest(db: OutboxDb) -> None:
    """At most ``CONFIRMED_SHOWN`` confirmed rows, the newest."""
    for n in range(CONFIRMED_SHOWN + 2):
        seed(db, f"C{n}", at=NOW + n, status=Status.SYNCED)
    confirmed = read_queue(db, OWNER, others=False).confirmed
    assert len(confirmed) == CONFIRMED_SHOWN
    assert confirmed[0].key == f"C{CONFIRMED_SHOWN + 1}"


def test_other_accounts_rows_are_listed_only_when_asked(db: OutboxDb) -> None:
    """Developer asks for them (D-412): by owner, unsynced only, never the account's."""
    seed(db, "A1")
    seed(db, "B1", owner=OTHER)
    seed(db, "B2", owner=OTHER, at=NOW + 1, status=Status.FAILED)
    seed(db, "B3", owner=OTHER, status=Status.SYNCED)
    assert read_queue(db, OWNER, others=False).others == ()
    ((owner, rows),) = read_queue(db, OWNER, others=True).others
    assert owner == OTHER
    assert [row.key for row in rows] == ["B2", "B1"]


def test_signed_out_only_other_accounts_rows_are_read(db: OutboxDb) -> None:
    """Without an owner every account with unsynced rows is another's."""
    seed(db, "A1")
    queue = read_queue(db, None, others=True)
    assert queue.mine == ()
    assert [owner for owner, _ in queue.others] == [OWNER]


def test_a_failed_read_is_said_never_guessed_as_synced(db: OutboxDb) -> None:
    """A closed database reads nothing (D-120): the sheet says it couldn't read."""
    db.close()
    queue = read_queue(db, OWNER, others=True)
    assert not queue.readable
    shown = words(sheet(queue))
    assert UNREADABLE in shown and EMPTY not in shown


# ------------------------------------------------------------------ showing


def test_each_row_shows_its_icon_word_kind_code_and_age(db: OutboxDb) -> None:
    """Queued and Failed rows say so, with the failed row's last error under it."""
    pending = seed(db, "A1", at=NOW - 120)
    failed = seed(db, "A2", at=NOW - 60, status=Status.FAILED)
    found = identified(sheet(read_queue(db, OWNER, others=False)))
    tile = found[f"staff.queue.row.{failed.id}"]
    assert isinstance(tile, ft.ListTile)
    assert words(tile) == [
        "Lead · A2",
        "Failed · 1 minute ago",
        "Wrong badge validator.",
    ]
    assert cast(ft.Icon, tile.leading).icon == ft.Icons.ERROR_OUTLINE
    tile = found[f"staff.queue.row.{pending.id}"]
    assert words(tile) == ["Lead · A1", "Queued · 2 minutes ago"]
    assert cast(ft.Icon, tile.leading).icon == ft.Icons.CLOUD_UPLOAD_OUTLINED
    assert tile.trailing is None


def test_two_sponsors_leads_on_one_attendee_are_told_apart(db: OutboxDb) -> None:
    """A staff account's rows name their sponsors, so the two aren't alike (D-459)."""
    for sponsor_id, name in (("1", "Example Corp"), ("3", "Sample Systems")):
        decide = partial(
            outbox.scan_lead,
            owner=OWNER,
            code="A1",
            payload={"badge_validator": "v"},
            sponsor_id=sponsor_id,
            sponsor_name=name,
            now=NOW,
        )
        assert db.enqueue("A1", decide) is not None
    found = identified(sheet(read_queue(db, OWNER, others=False)))
    tiles = [words(tile) for key, tile in found.items() if ".row." in key]
    assert sorted(tile[2] for tile in tiles) == [
        "For Example Corp",
        "For Sample Systems",
    ]


def test_a_flagged_row_says_it_may_be_recorded_twice_beside_an_icon(
    db: OutboxDb,
) -> None:
    """#693's flag (D-410): the words and a warning icon, confirmed rows included."""
    row = seed(db, "A1", status=Status.SYNCED, maybe_sent=True)
    built = sheet(read_queue(db, OWNER, others=False), confirmed_open=True)
    tile = identified(built)[f"staff.queue.row.{row.id}"]
    assert "Confirmed · may be recorded twice · just now" in words(tile)
    assert cast(ft.Icon, tile.trailing).icon == ft.Icons.WARNING_AMBER


def test_a_check_in_the_server_refused_says_already_redeemed(db: OutboxDb) -> None:
    """A 200 reply with ``errors`` syncs the row; the sheet says so and why (D-441)."""
    decide = partial(
        outbox.admit,
        owner=OWNER,
        code="MOCK0001",
        product_ids=[10],
        session="v1",
        payload={"product-redeem-10": 10, "product-10-quantity": 1},
        sponsor_id=None,
        sponsor_name=None,
        now=NOW,
    )
    enqueued = db.enqueue("MOCK0001", decide)
    assert enqueued is not None and enqueued.row is not None
    message = "All about decorators was already redeemed."
    reply = {"errors": [{"message": message}], "redeemable_products_by_category": {}}
    row = outbox.after_success(enqueued.row, reply)
    assert db.save(row)
    built = sheet(read_queue(db, OWNER, others=False), confirmed_open=True)
    tile = identified(built)[f"staff.queue.row.{row.id}"]
    assert words(tile) == [
        "Check-in · MOCK0001",
        "Confirmed · Already redeemed · just now",
        message,
    ]
    assert cast(ft.Icon, tile.trailing).icon == ft.Icons.WARNING_AMBER


def test_with_nothing_waiting_the_sheet_says_everything_is_synced(
    db: OutboxDb,
) -> None:
    """The empty state, no Retry failed, and the confirmed rows folded away."""
    seed(db, "A1", status=Status.SYNCED)
    built = sheet(read_queue(db, OWNER, others=False))
    found = identified(built)
    assert "staff.queue.empty" in found and RETRY_FAILED not in found
    assert words(found["staff.queue.empty"]) == [EMPTY]
    assert "Recently confirmed (1)" in words(built)
    fold = [c for c in walk(found["staff.queue.confirmed"]) if isinstance(c, ft.Icon)]
    assert fold[-1].semantics_label == COLLAPSED


def test_retry_failed_shows_only_while_rows_have_failed(db: OutboxDb) -> None:
    """Pending rows alone don't offer it; one failed row does."""
    seed(db, "A1")
    assert RETRY_FAILED not in identified(sheet(read_queue(db, OWNER, others=False)))
    seed(db, "A2", status=Status.FAILED)
    assert RETRY_FAILED in identified(sheet(read_queue(db, OWNER, others=False)))


def test_sync_now_shows_the_pass_under_way_and_takes_no_tap(db: OutboxDb) -> None:
    """While syncing it is disabled, with a ring and "Syncing…"; idle, "Sync now"."""
    idle = identified(sheet(Queue()))[SYNC_NOW]
    assert not idle.disabled and words(idle) == ["Sync now"]
    busy = identified(sheet(Queue(), Staff(pending=1, syncing=True)))[SYNC_NOW]
    assert busy.disabled and words(busy) == ["Syncing…"]
    assert any(isinstance(c, ft.ProgressRing) for c in walk(busy))
    asked = identified(sheet(Queue(), asked=True))[SYNC_NOW]
    assert asked.disabled


def test_a_blocked_sync_says_why_under_a_disabled_button() -> None:
    """Signed out or expired, Sync now is disabled and the line says what to do."""
    found = identified(sheet(Queue(), blocked="Sign in to sync."))
    assert found[SYNC_NOW].disabled
    assert words(found["staff.queue.blocked"]) == ["Sign in to sync."]


def test_other_accounts_have_their_own_section(db: OutboxDb) -> None:
    """Each owner under a heading, after a line on when their rows sync."""
    seed(db, "B1", owner=OTHER)
    shown = words(sheet(read_queue(db, OWNER, others=True)))
    assert shown[-5:] == [
        "Other accounts",
        "Their rows sync when that account signs in again.",
        OTHER,
        "Lead · B1",
        "Queued · just now",
    ]


def test_the_summary_says_the_state_and_the_last_sync() -> None:
    """The live line under the title: the chip's words, then the last pass's age."""
    assert summary(Staff(), NOW) == "All synced."
    staff = Staff(pending=3, offline=True, last_sync_at=NOW - 300)
    assert summary(staff, NOW) == "Offline · 3 queued. Last synced 5 minutes ago."


# ------------------------------------------------------------------ the buttons


def test_sync_now_kicks_once_even_when_tapped_twice() -> None:
    """A second tap before the pass reports sends no second kick; after it, one more."""
    kicks: list[int] = []
    staff = Staff(pending=1)
    kicked: MutableRef[int | None] = MutableRef(None)

    def kick() -> None:
        kicks.append(1)

    assert kick_once(kicked, staff, kick)
    assert not kick_once(kicked, staff, kick)
    assert kicks == [1]
    staff.update_counts(None)  # the pass reported
    assert kick_once(kicked, staff, kick)
    staff.syncing = True
    staff.update_counts(None)
    assert not kick_once(kicked, staff, kick)  # a pass runs: it is the pass
    assert kicks == [1, 1]


def test_sync_is_blocked_signed_out_expired_or_without_a_client(
    tmp_path: Path,
) -> None:
    """Each reason in words; none while a worker can run."""
    svc = cast(Services, type("Svc", (), {"api": None, "outbox": object()})())
    account = Account()
    assert sync_blocked(svc, account) == "Set the mock API URL in Developer to sync."
    svc = cast(Services, type("Svc", (), {"api": object(), "outbox": object()})())
    assert sync_blocked(svc, account) == "Sign in to sync."
    account.email, account.signed_in, account.expired = OWNER, True, True
    assert sync_blocked(svc, account) == (
        "Your sign-in has expired. Sign in again to sync."
    )
    account.expired = False
    assert sync_blocked(svc, account) is None


def test_close_is_a_named_button_that_closes_the_sheet() -> None:
    """The sheet is the screen's height, with no scrim to tap: Close is the way out."""
    closed: list[int] = []
    built = queue_sheet(
        Queue(),
        SheetState(Staff(), NOW),
        tokens=LIGHT_TOKENS,
        style=ft.Animation(0),
        on_sync_now=lambda: None,
        on_retry_failed=lambda: None,
        on_confirmed=lambda _open: None,
        on_close=lambda: closed.append(1),
    )
    button = identified(built)[CLOSE]
    assert isinstance(button, ft.IconButton) and button.tooltip == "Close"
    cast(Callable[[], None], button.on_click)()
    assert closed == [1]
