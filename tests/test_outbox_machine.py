"""A hypothesis state machine over the outbox's rules (D-56, D-77; testing §4.3).

The machine plays the db and the ``SyncWorker`` with ``core/outbox.py``'s pure rules:
scans, notes and door admissions, sends that succeed or fail with a ``NetworkError``
(before the request left, or after: a lost answer) or an ``ApiError`` (one at a time or
in streaks, to reach the cap), "Retry failed", sponsor and account switches, and time
passing. It keeps its own record of what each row should
be, independently of the rows, and checks the invariants after every step.
"""

import math
from dataclasses import replace

from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from pycon_us.core import outbox
from pycon_us.core.outbox import Enqueued, Kind, Outcome, Row, Status

OWNERS = ("a@example.com", "b@example.com")
CODES = st.sampled_from(("A", "B", "C"))
SPONSORS = st.sampled_from((("1", "One"), ("2", "Two"), (None, None)))
SENDS = st.sampled_from(("ok", "network", "lost", "api"))
NOTES = st.sampled_from(("", "  ", "Hot", "Cold"))
PRODUCTS = st.lists(st.sampled_from((1, 2, 3)), min_size=1, max_size=3, unique=True)


def attribution(row: Row) -> tuple[object, ...]:
    """Return what a row must keep from its enqueue on: who, for whom, what and when."""
    return (
        row.kind,
        row.key,
        row.owner,
        row.sponsor_id,
        row.sponsor_name,
        row.idem_key,
        row.created_at,
    )


class OutboxMachine(RuleBasedStateMachine):
    """The outbox under any sequence of staff actions and send outcomes."""

    def __init__(self) -> None:
        """Start with an empty outbox, the first account and sponsor "One"."""
        super().__init__()
        self.rows: dict[int, Row] = {}
        self.last_id = 0
        self.now = 1_000_000.0
        self.owner = OWNERS[0]
        self.sponsor: tuple[str | None, str | None] = ("1", "One")
        self.enqueued: dict[int, tuple[object, ...]] = {}
        self.unsynced: set[int] = set()
        self.synced: set[int] = set()
        self.api_errors: dict[int, int] = {}
        self.lost: set[int] = set()

    def store(self, decision: Enqueued, *, counted_from_zero: bool) -> None:
        """Apply an enqueue's decision as the db would, and record what to expect.

        Args:
            decision: What the enqueue decided.
            counted_from_zero: Whether a changed row starts its count of failures again.
        """
        if decision.outcome is Outcome.QUEUED:
            assert decision.row is not None and decision.row.id is None
            self.last_id += 1
            row = replace(decision.row, id=self.last_id)
            self.enqueued[self.last_id] = attribution(row)
            self.api_errors[self.last_id] = 0
        elif decision.outcome is Outcome.UPDATED:
            assert decision.row is not None and decision.row.id in self.rows
            row = decision.row
            assert row.id is not None
            if counted_from_zero:
                self.api_errors[row.id] = 0
        else:
            return
        assert row.id is not None and row.status is Status.PENDING
        self.rows[row.id] = row
        self.unsynced.add(row.id)
        self.synced.discard(row.id)

    def first_due(self) -> Row | None:
        """Return the row the worker would send next, if any."""
        due = outbox.due(self.rows.values(), self.owner, self.now)
        return due[0] if due else None

    @rule(code=CODES)
    def scan_lead(self, code: str) -> None:
        """Scan a badge for the sponsor chosen; its lead already synced adds nothing."""
        existing = [
            r
            for r in self.rows.values()
            if (r.owner, r.kind, r.key, r.sponsor_id)
            == (self.owner, Kind.LEAD, code, self.sponsor[0])
        ]
        others = tuple(
            r.sponsor_name
            for r in self.rows.values()
            if (r.owner, r.kind, r.key) == (self.owner, Kind.LEAD, code)
            and r.sponsor_id != self.sponsor[0]
            and r.sponsor_name
        )
        decision = outbox.scan_lead(
            self.rows.values(),
            owner=self.owner,
            code=code,
            payload={"code": code},
            sponsor_id=self.sponsor[0],
            sponsor_name=self.sponsor[1],
            now=self.now,
        )
        assert decision.others == others
        if existing and existing[0].status is Status.SYNCED:
            assert decision == Enqueued(Outcome.ALREADY, existing[0], others)
        if not existing:
            assert decision.outcome is Outcome.QUEUED  # never dropped for another's row
        self.store(
            decision,
            counted_from_zero=bool(existing) and existing[0].status is Status.FAILED,
        )

    @rule(code=CODES, text=NOTES, pick=st.integers(0, 2))
    def save_note(self, code: str, text: str, pick: int) -> None:
        """Note one of this account's leads (the app offers notes on a lead's row).

        The sheet takes the sponsor from the lead, whichever is chosen now (D-459).
        """
        leads = [
            r
            for r in self.rows.values()
            if (r.owner, r.kind, r.key) == (self.owner, Kind.LEAD, code)
        ]
        if not leads:
            return
        lead = leads[pick % len(leads)]
        decision = outbox.save_note(
            self.rows.values(),
            owner=self.owner,
            code=code,
            note=text,
            sponsor_id=lead.sponsor_id,
            sponsor_name=lead.sponsor_name,
            now=self.now,
        )
        assert (decision.outcome is Outcome.IGNORED) == (not text.strip())
        self.store(decision, counted_from_zero=True)

    @rule(code=CODES, products=PRODUCTS, session=st.sampled_from(("s1", "s2")))
    def admit(self, code: str, products: list[int], session: str) -> None:
        """Admit an attendee at the door in a scan session."""
        decision = outbox.admit(
            self.rows.values(),
            owner=self.owner,
            code=code,
            product_ids=products,
            session=session,
            payload={"products": products},
            sponsor_id=self.sponsor[0],
            sponsor_name=self.sponsor[1],
            now=self.now,
        )
        self.store(decision, counted_from_zero=False)

    @rule(sponsor=SPONSORS)
    def switch_sponsor(self, sponsor: tuple[str | None, str | None]) -> None:
        """Choose another sponsor to scan for."""
        self.sponsor = sponsor

    @rule(owner=st.sampled_from(OWNERS))
    def switch_account(self, owner: str) -> None:
        """Sign in as another account: the previous one's synced rows are forgotten."""
        kept = outbox.forget_synced(self.rows.values(), self.owner)
        self.rows = {row.id: row for row in kept if row.id is not None}
        self.synced &= self.rows.keys()
        self.owner = owner

    @rule(seconds=st.sampled_from((0.0, 1.0, 59.0, 60.0, 600.0)))
    def tick(self, seconds: float) -> None:
        """Let time pass."""
        self.now += seconds

    @rule(outcome=SENDS)
    def send(self, outcome: str) -> None:
        """Send the next due row, as the worker would, with the given outcome."""
        row = self.first_due()
        if row is None:
            return
        assert row.id is not None
        if row.kind is Kind.NOTE:
            assert self.lead_synced(row)
        if outcome == "ok":
            self.rows[row.id] = outbox.after_success(row, {"ok": True})
            self.unsynced.discard(row.id)
            self.synced.add(row.id)
        elif outcome in ("network", "lost"):
            lost = outcome == "lost"  # the request may have reached the server
            self.rows[row.id] = outbox.after_network_error(
                row, self.now, maybe_sent=lost
            )
            if lost:
                self.lost.add(row.id)
        else:
            self.rows[row.id] = outbox.after_error(row, "500", self.now)
            self.api_errors[row.id] += 1

    @rule(count=st.integers(1, outbox.RETRY_CAP))
    def refused_repeatedly(self, count: int) -> None:
        """Let the server refuse the next due row ``count`` passes running."""
        row = self.first_due()
        if row is None or row.id is None:
            return
        row_id = row.id
        for _ in range(count):
            if row.status is not Status.PENDING:
                break
            row = outbox.after_error(row, "500", self.now)
            self.api_errors[row_id] += 1
            self.now += outbox.NETWORK_BACKOFF
        self.rows[row_id] = row

    @rule()
    def retry_failed(self) -> None:
        """Tap "Retry failed": this account's failed rows start over."""
        for row in list(self.rows.values()):
            if row.owner == self.owner and row.status is Status.FAILED:
                assert row.id is not None
                self.rows[row.id] = outbox.retry_failed(row, self.now)
                self.api_errors[row.id] = 0

    def lead_synced(self, note: Row) -> bool:
        """Return whether a note's lead row, the same sponsor's, is on the server."""
        return any(
            (r.owner, r.kind, r.key, r.sponsor_id, r.status)
            == (note.owner, Kind.LEAD, note.key, note.sponsor_id, Status.SYNCED)
            for r in self.rows.values()
        )

    @invariant()
    def no_unsynced_row_lost(self) -> None:
        """Every row not yet on the server is still in the outbox, and not synced."""
        for row_id in self.unsynced:
            assert self.rows[row_id].status is not Status.SYNCED

    @invariant()
    def attribution_fixed_at_enqueue(self) -> None:
        """Owner, sponsor snapshot, kind, code, key and scan time never change."""
        for row_id, row in self.rows.items():
            assert attribution(row) == self.enqueued[row_id]

    @invariant()
    def synced_rows_never_due(self) -> None:
        """Only rows the machine synced are synced, and none is due for any owner."""
        for row_id, row in self.rows.items():
            assert (row.status is Status.SYNCED) == (row_id in self.synced)
        for owner in OWNERS:
            assert not {
                r.id for r in outbox.due(self.rows.values(), owner, math.inf)
            } & (self.synced)

    @invariant()
    def notes_wait_for_their_lead(self) -> None:
        """A due note's lead is synced, and every unsent note still has its lead row."""
        for owner in OWNERS:
            for row in outbox.due(self.rows.values(), owner, math.inf):
                assert row.kind is not Kind.NOTE or self.lead_synced(row)
        for row in self.rows.values():
            if row.kind is Kind.NOTE and row.status is not Status.SYNCED:
                assert any(
                    (r.owner, r.kind, r.key, r.sponsor_id)
                    == (row.owner, Kind.LEAD, row.key, row.sponsor_id)
                    for r in self.rows.values()
                )

    @invariant()
    def notes_go_to_their_leads_sponsor(self) -> None:
        """A note keeps its lead's sponsor snapshot, whatever sponsor was chosen since."""
        leads = {
            (r.owner, r.key, r.sponsor_id): r
            for r in self.rows.values()
            if r.kind is Kind.LEAD
        }
        for row in self.rows.values():
            lead = leads.get((row.owner, row.key, row.sponsor_id))
            if row.kind is Kind.NOTE and lead is not None:
                assert row.sponsor_name == lead.sponsor_name

    @invariant()
    def tries_count_only_api_errors(self) -> None:
        """``tries`` is the ``ApiError``s since the last restart; failed exactly at 10."""
        for row_id, row in self.rows.items():
            assert row.tries == self.api_errors[row_id] <= outbox.RETRY_CAP
            assert (row.status is Status.FAILED) == (row.tries == outbox.RETRY_CAP)

    @invariant()
    def flagged_exactly_after_a_lost_answer(self) -> None:
        """A row says "may be recorded twice" from its first lost answer on."""
        for row_id, row in self.rows.items():
            assert row.maybe_sent == (row_id in self.lost)
            assert (outbox.MAYBE_TWICE in outbox.status_text(row)) == row.maybe_sent

    @invariant()
    def one_row_per_lead_note_and_check_in(self) -> None:
        """One lead and one note row per (owner, code, sponsor); one door row per key."""
        leads_and_notes = [
            (r.owner, r.kind, r.key, r.sponsor_id)
            for r in self.rows.values()
            if r.kind is not Kind.DOOR
        ]
        assert len(leads_and_notes) == len(set(leads_and_notes))
        keys = [r.idem_key for r in self.rows.values() if r.kind is Kind.DOOR]
        assert None not in keys and len(keys) == len(set(keys))


TestOutbox = OutboxMachine.TestCase
