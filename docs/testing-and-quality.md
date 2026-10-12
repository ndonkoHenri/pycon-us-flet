# Testing and quality (v2)

**Status:** plan of record, 2026-10-11. Replaces the v1 testing document (kept in git history, not binding).
**Binding inputs:** [`PLAN.md`](../PLAN.md) §7 (exit criteria) and §9 (quality bar); [`decisions.md`](decisions.md) D-76..D-80 (testing), D-33 (accessibility), D-41..D-43 (feed, time), D-50..D-57 (mock, outbox), D-84 (CI), D-93 (done), §M (names), §N (Flet facts).
**Flet ground truth:** the local monorepo at `9fbe52a61` (unreleased 1.1.0): `flet/testing/` (`FletTestApp`, `Tester`, `Finder`, `remote_tester.RemoteTester`), `flet/pytest_plugin.py` (fixture `flet_app`), `flet_cli/commands/test.py` (`flet test`), `packages/flet/integration_tests/README.md` and the integration-testing guide. Gaps Flet has today, with interims, are in §13.

> Per D-96 this file is the test strategy (D-76..D-80). [`development.md`](development.md) is the developer guide (toolchain, dev loop, builds, CI) and links here.

---

## 0. Principles

1. **Test what protects correctness.** Feed rules, time zones, ids, signing, the outbox and the PSF guard get thorough, fast tests. Screens get a few journey flows, not a test per feature id (D-04).
2. **One obvious tool per layer.** pytest (+ hypothesis) for logic, `httpx.MockTransport` over the mock's `handle()` for the API, `flet test` for UI. No Node, jsonschema or snapshot libraries.
3. **API evidence is not device evidence.** Device behaviour is proven by spikes, flows and the phase checklist (D-79).
4. **No test-only code in the app.** Flows use the real UI, including the Developer screen (D-73). Unit tests inject `now`, `httpx` transports and temporary directories.
5. **Measure, don't gate, what CI cannot see.** Device performance and accessibility are measured at phase exits and recorded in the phase status issue (D-79, D-80).

## 1. Layers at a glance

| Layer | Tool | When | In CI |
|---|---|---|---|
| Unit: `core/` and helpers (§3) | pytest, hypothesis | every PR | yes |
| Feed: rules, invariants, snapshot, Ionic reference (§3.3) | pytest, recorded feeds | every PR | yes |
| Mock API, client, signing, outbox (§4) | `httpx.MockTransport`, hypothesis | every PR, from P3 | yes |
| UI smoke flows (§5) | `flet test`, `flet_app`, `RemoteTester` | UI-heavy PRs; phase exits | no |
| Goldens (§6) | `take_screenshot`, `assert_screenshot` | P4 only | no |
| Accessibility (§7) | contrast test; flows at 200 %; screen readers | every PR (contrast); phase exits | contrast only |
| Device checklist and performance (§8, §9) | packaged builds on an Android emulator and an iOS simulator; the iPhone for hardware checks (D-102) | phase exits | no |
| Public feed check (§12) | `tools/check_feed.py` | weekly | yes (cron) |

## 2. Layout, configuration and commands

```
tests/
  __init__.py          # tests are a package, so flows can import tests.ui.helpers
  conftest.py          # hypothesis profile, --snapshot-update, machine_tz, snapshot fixtures
  test_<module>.py     # unit tests, one file per module under test (D-67, section M)
  fixtures/
    feeds/conference-2025.json, conference-2026.json   # recorded public feeds (+ README: date, URL)
    feeds/pairs/<name>/{old,new}.json                  # change-log cases (#312)
    snapshots/outline-<year>.json                      # reviewed outline of our processed model
    ionic/<year>/*.json, ionic/signing.json            # captured once from Ionic's own code (D-77, D-52)
    mock/                                              # accounts per role, sponsors, products, attendees (D-50)
  ui/
    __init__.py, conftest.py, helpers.py               # see §5
    test_<journey>.py, golden/<platform>/...           # flows; goldens in P4
```

All these paths are listed in decisions §M (Tests).

The project file is the one in [`development.md`](development.md) §3; these are its testing parts, and both documents show the same values:

```toml
# pyproject.toml (excerpt)
[dependency-groups]
dev = [                      # host only; flet-* come from .flet-src via [tool.uv.sources] (D-81)
    "flet-cli",              # flet run / build / test; without it the `flet` script pip-installs a PyPI flet-cli at runtime
    "flet-web",
    "flet-desktop",
    "flet-platform-assets",
    "flet[test]",            # pytest-asyncio, numpy, Pillow, scikit-image
    "pytest",
    "hypothesis",
    "ruff",
    "pyright",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"        # required: Flet's guide says so, and it runs our async unit tests
testpaths = ["tests"]
pythonpath = ["."]           # tools.mock_api; pycon_us is installed editable by uv sync ([build-system], D-82)
addopts = ["--ignore=tests/ui"]  # UI flows run only through flet test (see below)

[tool.ruff.lint]
extend-select = ["I", "UP", "B", "SIM", "D", "DTZ"]  # DTZ: no naive datetime.now()/utcnow() (D-43)
```

`flet[test]` brings `pytest-asyncio`, numpy, Pillow and scikit-image (screenshot comparison). It is needed by `flet test`, and `pytest-asyncio` runs our async client tests. Flet's pytest plugin defines the `flet_app` fixture only when `pytest_asyncio` imports, so `flet[test]` stays in `dev`, not in a separate group that `uv sync` skips. This is D-75's dev list: the Flet host tooling is listed by name so uv takes it from `.flet-src` at the pin. `pycon_us` itself is importable because the project has a `[build-system]` (`uv_build`), so `uv sync` installs it editable from `src/` (D-82; development.md §3.1).

`flet` registers a pytest plugin (`pytest11` entry point) that would provision a Flutter test host whenever a test asks for `flet_app`. So plain `uv run pytest` must never collect the UI flows. `addopts = ["--ignore=tests/ui"]` is the one gate: `flet test` passes `tests/ui` to pytest explicitly, and an explicit path overrides `--ignore` (checked with pytest), so the flows still run there.

| Task | Command |
|---|---|
| Lint, format, types | `uv run ruff check && uv run ruff format --check && uv run pyright` |
| Unit and mock tests (under 2 min, D-84) | `uv run pytest` |
| Accept a reviewed snapshot change | `uv run pytest tests/test_feed.py --snapshot-update` |
| UI flows on the Android emulator | `uv run flet test android -d emulator-5554 --tests-dir tests/ui` |
| UI flows on the iOS simulator | `uv run flet test ios -d <simulator-udid> --tests-dir tests/ui` |
| One flow, verbose | add `-k favourite -v`; pytest options after `--` (e.g. `-- -x`) |
| Record or update goldens (P4) | add `-k goldens -u`, or `--update-failed-goldens` |
| Public feed check | `uv run python tools/check_feed.py` |

## 3. Unit tests

### 3.1 Conventions

- **Descriptive names** (`test_lunch_row_spans_earliest_start_to_latest_end`). A feature id may appear in the docstring; nothing enforces it (D-04).
- **`core` takes `now` as an argument** (D-43), so tests pass fixed aware datetimes. Only `clock.now()` itself is tested with its override.
- **No network, no Flet runtime.** `core/` tests import no Flet (D-68). Stores are plain `@ft.observable` dataclasses and run without a page; `Observable.subscribe(fn)` checks that a change notifies. `subscribe` holds listeners weakly (a `weakref.WeakSet`): in tests bind the listener to a local name (`def on_change(sender, field): ...`) and keep it alive for the test; never pass a lambda, which is collected at once and never called.
- **Hypothesis** runs derandomised in CI (`--hypothesis-profile=ci`: 200 examples, `deadline=None`), registered in `tests/conftest.py`.
- **Fast.** The whole suite stays under 2 minutes on CI (D-84). A slow test is a design smell, not a reason for a marker.

### 3.2 Two machine time zones

Code that is correct only in Pacific time is wrong. Time-sensitive modules (`test_timefmt.py`, `test_feed.py`, `test_queries.py`, `test_ics.py`, `test_reminders.py`) run every test under two machine zones far apart (D-43), without a CI matrix:

```python
# tests/conftest.py (excerpt)
@pytest.fixture(params=["America/Los_Angeles", "Pacific/Kiritimati"])
def machine_tz(request: pytest.FixtureRequest) -> Iterator[str]:
    """Run the test with the process time zone set to each value in turn (D-43)."""
    with pytest.MonkeyPatch.context() as patch:  # restores only TZ, never another fixture's patches
        patch.setenv("TZ", request.param)
        time.tzset()
        yield request.param
    time.tzset()
```

Each of those modules starts with `pytestmark = pytest.mark.usefixtures("machine_tz")`. Ruff's `DTZ` rules catch naive datetimes statically.

### 3.3 Feed processing (D-41, D-77)

**Fixtures.** The 2025 and 2026 public feeds, recorded once and committed with a README (URL, date, SHA-256). The 2027 feed is added when published. Mutated copies for edge cases are built in the test from these files (`copy.deepcopy`, change one slot), never hand-written JSON blobs.

**Named rule tests.** One test per rule, on the real fixtures, each asserting the concrete case from the feed:

| Rule (D-41) | Example test | Ids |
|---|---|---|
| Dropped: `available-open-space*` rows, `kind=open-space` duplicates of `open-spaces[]`, cancelled stubs (Ionic's `isPlaceholderSlot`; poster and break exempt), the duplicate plenary "Posters" slot, and kind `blank` / name `Slot` rows | `test_placeholder_slots_dropped_but_posters_and_breaks_kept` | DATA-04 |
| Open spaces become sessions with id `conf_key + 9000` and `room_display` location | `test_open_spaces_become_sessions_with_offset_ids` | DATA-05 |
| Break and poster slots collapse by Ionic's key; Lunch spans earliest start to latest end | `test_lunch_row_spans_earliest_start_to_latest_end` | DATA-06, SCHED-19 |
| Synthetic `poster-detail-<k>` sessions inherit the Posters row's time and place | `test_poster_details_inherit_posters_row` | DATA-07 |
| Title and location cleaning (markdown links, entities, trailing `(X)`, `Hall` → `Expo Hall`) | `test_keynote_room_moves_from_title_to_location` | DATA-08 |
| Pre-registration and Spanish flags (`ñ` and `n`, any case) | `test_spanish_flag_matches_espanol_with_and_without_tilde` | DATA-09, DATA-10 |
| Job Fair is grouped at 10:00 and labelled 9:30 (override from `content.toml`) | `test_job_fair_grouped_at_ten_labelled_nine_thirty` | DATA-11 |
| Every time group has an aware start in the conference zone; groups sort by start | `test_every_group_has_aware_start` | DATA-12, DATA-13 |
| Speakers link by name; pseudo-speakers ("Hosted by …") are text, not directory entries | `test_hosted_by_is_not_a_speaker` | DATA-15 |
| Rooms fan out from multi-room strings | `test_multi_room_session_appears_in_each_room` | DATA-16 |
| Sprint-only rooms from `map.toml` are seeded (from P2, with the pin registry) | `test_sprint_only_rooms_are_seeded` | MAP-08, DATA-32 |
| Ids are strings in four stable forms | `test_ids_are_strings_in_known_forms` | DATA-26, D-42 |
| A malformed slot is skipped and logged; the rest of the day survives | `test_bad_slot_is_skipped_and_logged` (uses `caplog`) | D-41 |

**Invariants.** One parametrised test per invariant, run on every fixture year (and by `tools/check_feed.py` on the live feed):

1. No session lost: every raw slot maps to a session id, a documented collapsed row, or one of the named drop rules (each drop counted and logged).
2. Ids are unique strings, and processing the same bytes twice gives the same ids.
3. Processing is pure: the decoded input is unchanged afterwards.
4. Every session lies in exactly one conference-local day, and the days are the conference dates.
5. All datetimes are aware, in the year's zone; `start <= end`.
6. Every time group has a start; groups are sorted; within a slot, rows are ordered by room (D-31).
7. No dropped category survives; posters and breaks remain.
8. Exactly one Lunch row per conference day that has lunch.
9. Every speaker referenced by a session exists in the registry, and every registry speaker has a session.
10. Every session room has a slug, and slugs are unique per room name.

**Snapshot of our model.** A compact, reviewable outline of the processed model (days → groups → `(id, title, room, track, speaker ids, start, end)`) is compared with `tests/fixtures/snapshots/outline-<year>.json`. The outline function lives in the test module so the snapshot stays readable; a full `dataclasses.asdict` dump would be too large to review. When a parser change alters the outline, the PR runs `--snapshot-update` and explains the diff in its body.

```python
# tests/conftest.py (excerpt)
import json
from pathlib import Path

import pytest

SNAPSHOTS = Path(__file__).parent / "fixtures" / "snapshots"


def pytest_addoption(parser):
    parser.addoption(
        "--snapshot-update",
        action="store_true",
        help="Rewrite snapshot files instead of comparing with them.",
    )


@pytest.fixture
def snapshot(request):
    """Return check(name, data): compare data with a committed JSON snapshot."""
    update = request.config.getoption("--snapshot-update")

    def check(name: str, data: object) -> None:
        path = SNAPSHOTS / f"{name}.json"
        text = json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False, default=str) + "\n"
        if update:
            path.write_text(text, encoding="utf-8")
            return
        assert path.exists(), f"No snapshot {path.name}; run with --snapshot-update and review it"
        assert path.read_text(encoding="utf-8") == text, (
            f"{name} changed; review the diff, then run with --snapshot-update"
        )

    return check
```

**Ionic reference (captured once).** In P0, `tools/capture_ionic_reference/` runs Ionic's `processData` and key queries under Node on both feeds and writes `tests/fixtures/ionic/<year>/*.json` (README: Ionic commit, Node version, date). CI and contributors never need Node (D-77). `test_feed.py` compares a few facts that settle ambiguous rules, not whole outputs:

- the set of session ids (including Ionic's synthetic ids);
- the collapsed-row ids and their time spans;
- group start times per day, and the Job Fair label;
- speaker-to-session links.

Deliberate differences live in one dict, `INTENDED_DIFFERENCES = {"DATA-13": "every group has a start time", ...}`, each with its own named test. Ionic is a reference, not an oracle.

### 3.4 Other `core/` modules

| Module | What the tests pin | Ids / D |
|---|---|---|
| `queries.py` | Search folds case and accents, needs **all words**, matches text not markup. My schedule, Now and Search ignore filters. Happening means `start <= now < end`; next session = the earliest saved session with `end > now` that is ongoing or starts within 3 h (none otherwise); overlaps flag both rows | D-46, NEW-02, D-20, SCHED-25, NEW-01 |
| `timefmt.py` | 12/24 h from the flag; "Pacific Time" note when zones differ; DST; local day bucket; relative ages | D-35, DATA-12, DATA-31 |
| `slugs.py` | Room, track and sponsor slugs on real names (vectors cite their Ionic source line) | DATA-16, DATA-29 |
| `html_md.py` | Every tag in the 2025/2026 tag census (S3); links made absolute; unknown tags degrade to text; plain text unchanged | D-44, SESS-06 |
| `diff.py` | Feed pairs: moved, retimed, renamed, added, removed; no diff on first install, and no false diff after a parser change (the cache keeps raw bytes) | D-47, NEW-04 |
| `ics.py` | UTC times, stable UID, RFC 5545 escaping, 75-octet folding, `VALARM`; one session and a whole agenda | D-62, SESS-05 |
| `badges.py` | Access code is segment 0; door and swag send the first validator, lead the last; CoC sends the code only | LEAD-03 |
| `admission.py` | Inventory first, then online lookup; "Already checked in" on product overlap; unknown offline → "Entry not permitted" | DOOR-04 |
| `signing.py`, `outbox.py` | §4 | D-52, D-56 |
| reminders `plan()` | Deterministic ids (the numeric session id, or 1,000,000 + crc32(id) % 1,000,000 for synthetic ids; event reminders at 8000-8099; the test reminder at 8999), no collisions in a year's plan, only future reminders, at most 60, and the same inputs give the same plan | D-59, NEW-05 |
| `staff_entries(flags)` | Exhaustive truth table over every role-flag combination, signed in and out | D-54, AUTH-05 |

### 3.5 Outside `core/`

| Subject | Test | D |
|---|---|---|
| Year data | Every `data/<year>/` loads; a malformed file fails with an error naming the file and key; safety contacts are present | D-45 |
| Capabilities | With `FLET_PLATFORM` unset (`monkeypatch.delenv`, then `importlib.reload(capabilities)`, because the capabilities are import-time constants), every capability constant is `False` and `available()` is `False` for every module, so the companion app gets interims | D-63 |
| Routes | `drill_href()` round-trips every id form, including synthetic ids with spaces or slashes, URL-quoted (`quote(ident, safe="")`), and the drill route decodes it back. `parent_of(route, search_base)` on every route shape: drops the last drill pair, else walks up to the nearest page (`/more/tracks/python` → `/more/tracks`, `/more/staff/lead` → `/more`), and `/search` returns the remembered base, query included | D-42, D-21, D-19 |
| Storage keys | Every key in the table starts with `pycon.`, keys are unique, values have SharedPreferences types | D-49, F12 |
| `Conference.start_refresh` | `httpx.MockTransport` + temporary data dir: two concurrent refreshes send one request; a connect error, HTTP 500 or corrupt body keeps the last good data and the cache file; a corrupt cache is deleted, then the snapshot is used | D-39, DATA-02 |
| `Favorites` | Add, remove, Undo; per-year keys; a 2026 favourite never marks a 2027 session | D-48 |
| Favourites sync (P3) | First sync is the union; a dirty local list is pushed before a pull; sign-out keeps the local list; a failed PATCH sets `dirty` | D-55, API-04 |
| `@report_errors` | On a sync and an async callable: logs the traceback, shows the SnackBar and keeps the session; re-raises `CancelledError`; the wrapper keeps the original's async-ness (`inspect.iscoroutinefunction`) and signature (`__wrapped__`) | D-71 |
| Logging | Requests made with a fake secret, email and badge code leave none of them in `caplog.text` | D-72 |
| Theme contrast | §7.1 | D-25, D-33 |
| Version | `pycon_us.__version__` equals `[project].version` | D-83 |
| `core` purity | An `ast` scan of `core/` finds no `flet` import | D-68 |
| PSF guard | The API client raises before sending any `/api/v1` request to a `*.pycon.org` host, for every endpoint; and with no mock base URL set, sign-in, account and every staff entry are hidden (`staff_entries` and the More list return none), whatever flags are stored | D-51 |

## 4. Signing, the mock server and the outbox (P3)

### 4.1 Signing vectors (D-52)

`tests/fixtures/ionic/signing.json` holds vectors produced once by Ionic's own `buildRequestAuthHeaders` (`providers/pycon-api.ts`) under Node, with provenance (commit, Node version, date). Client and mock share `core/signing.py`, so only outside vectors catch a shared mistake. Cases:

- an empty-body GET with a query (lead capture: `encodeURIComponent`-encoded) and one whose query Ionic leaves unencoded (`fetch_products`);
- a JSON body with non-ASCII text, quotes and slashes (serialised once with `separators=(",", ":")`, `ensure_ascii=False`);
- timestamps on both sides of `x.5` seconds (`Math.round(Date.now() / 1000)`);
- the same request with query parameters in a different order (different signature expected).

### 4.2 Mock API tests (D-50, D-57)

`MockState` holds the state seeded from `tests/fixtures/mock/`, and D-50's pure `handle(state, method, path, headers, body) -> (status, headers, body)` serves it. Tests call `handle` directly (signature and timestamp window, `{code, data}` / `{code, error}` envelopes, role accounts) and through the real client, using `tools/mock_api/transport.py` (architecture §11):

```python
# tools/mock_api/transport.py (excerpt)
import httpx

from tools.mock_api.handlers import MockState, handle


def mock_transport(state: MockState) -> httpx.MockTransport:
    """Route the client's requests to the in-process mock."""

    def respond(request: httpx.Request) -> httpx.Response:
        status, headers, body = handle(
            state, request.method, request.url.raw_path.decode(), dict(request.headers), request.content
        )
        return httpx.Response(status, headers=headers, content=body)

    return httpx.MockTransport(respond)
```

Faults are raised by the transport or set on the mock, never by code in the app:

| Fault | How | Expected client behaviour |
|---|---|---|
| Connection refused | transport raises `httpx.ConnectError` before `handle` | `NetworkError`; outbox tries not counted |
| Timeout | transport raises `httpx.ReadTimeout`; per-endpoint timeouts match Ionic's table (API-12) | `NetworkError` |
| Server committed, response lost | transport calls `handle`, then raises `httpx.ReadError` | row stays pending; the retry must not duplicate (below) |
| Expired auth | mock answers 401/403 for the key | `ApiError.is_auth`; sign-in prompt; queue kept |
| Skewed clock | mock clock offset of ±10 min | skew learned from `Date`, one retry, then success |
| Account or sponsor switch with rows pending | changed between syncs | rows keep owner and sponsor snapshot |

**Both capture semantics.** Sync tests are parametrised over `MockState(capture="idempotent")` and `"non_idempotent"`. Idempotent: every record is stored exactly once. Non-idempotent: a lost response plus a retry can create a second server record, which no client can prevent, so the test asserts what the client guarantees: never lost, never misattributed, one local synced row, and every duplicate traced to an ambiguous failure in the mock's log (§14).

### 4.3 Outbox (D-56)

A hypothesis `RuleBasedStateMachine` drives the pure state in `core/outbox.py` with rules for enqueue (lead, note, door), sync success, network failure, server failure, sponsor switch, sign-out request and "Retry failed". Invariants after every step:

- no pending row is ever lost;
- a row's owner, sponsor snapshot and idempotency key never change after enqueue;
- network failures never increase `tries`; 10 counted failures make a row `failed`;
- a note is never sent before its lead is synced;
- synced rows are kept; at most one door row per (code, product, session).

The machine records each row's attribution at enqueue time and compares it in an `@invariant()`; `TestOutbox = OutboxMachine.TestCase` exposes it to pytest. The sqlite layer (`services/`) gets plain tests on a temporary file: rows survive closing and reopening the connection mid-sync; `PRAGMA user_version` migrations run from every earlier version; WAL mode is on.

## 5. UI flows with `flet test` (D-78)

### 5.1 What the Flet testing API gives us (verified)

| Piece | In the pinned Flet |
|---|---|
| Runner | `flet test` provisions a Flutter test host through the `flet build` pipeline (cached by input hash), then runs pytest with `FLET_TEST_DEVICE_MODE=1` (`flet_cli/commands/test.py`). |
| Mode | Always **device mode**: the app runs embedded (`is_embedded()` is True, so bundled extensions are used) and the laptop drives it over a socket. `flutter test` builds a **debug** binary, so flows say nothing about performance. Flet's in-process host mode is how Flet tests itself; we don't use it. |
| Fixture | `flet_app` (function scope, `flet/pytest_plugin.py`): each test function is a fresh `flutter test` launch, so **one journey per test function**. `flet_app.page` is not available in device mode (it raises `RuntimeError: page is not initialized`). Flows reach the app only through `flet_app.tester` finders. |
| Tester | `flet_app.tester` is a `RemoteTester` (`flet.testing.remote_tester`): `find_by_semantics_identifier`, `find_by_text`, `find_by_text_containing`, `find_by_tooltip`, `find_by_key`, `find_by_icon`, `tap`, `long_press`, `enter_text`, `mouse_hover`, `pump(duration)`, `pump_and_settle(duration)`, `take_screenshot(name)`. A `Finder` has `count`, `first`, `last`, `at(i)`. |
| Absent on device | `drag`, `drag_from`, `tap_at`, `mouse_click`, `right_mouse_click`, `mouse_double_click` and the `*_at` variants exist only on the host `Tester` (F21). `RemoteTester.pump_and_settle` has no `timeout` argument; each call fails after a fixed 60 s. |
| Assertions | A Flutter-side error (for example "RenderFlex overflowed") makes `flutter test` exit non-zero, and `FletTestApp.teardown()` then raises, so the test fails even if every Python assertion passed. |
| Targets | `FletTestApp` points the app at `10.0.2.2` on Android and `127.0.0.1` on iOS (`flet_test_app.py:295`). Those reach the laptop only from an **emulator or simulator**, so flows run there; the iPhone is covered by the device checklist (§9). |

### 5.2 Driving state without test hooks

- **Identifiers.** Key controls carry `Semantics(identifier="<screen>.<element>[.<key>]")` (D-33, §M), e.g. `schedule.favorite.42`, `now.next_session`. They become Android `resource-id` and iOS `accessibilityIdentifier`, so they never contain names, emails or badge codes. Plain string literals; a typo fails a flow.
- **The Developer screen** (D-73) sets the scene; flows unlock it with 7 taps on the version row, as a person would. It needs `developer.reset` (+ confirm), `developer.fake_clock` (ISO 8601 text), `developer.feed_url`, `developer.mock_url` (P3) and `developer.apply`.
- **Data.** The `feed_url` fixture (in `tests/ui/conftest.py`) serves `tests/fixtures/feeds/` from the laptop with `http.server.ThreadingHTTPServer` on `127.0.0.1` and returns the URL the app can reach: `http://10.0.2.2:<port>/conference-2026.json` on Android, `http://127.0.0.1:<port>/…` on iOS. The fake clock sits inside the 2026 dates. "Offline" is a feed URL on a closed port: real airplane mode would also cut the tester's socket.
- **Back.** Android: `adb -s $FLET_TEST_DEVICE shell input keyevent KEYCODE_BACK` from the test. iOS: tap the app bar's back button, `find_by_tooltip("Back")`. The iOS edge swipe and Android predictive back stay manual (§9).
- **Settling.** Indeterminate progress and shimmer never settle, so helpers poll with `pump(duration)` until a finder matches. Android emulators run with the three animation scales at 0 (`adb shell settings put global transition_animation_scale 0`, etc.); Flutter reports that as `disable_animations`, which the app honours (D-34).

```python
# tests/ui/helpers.py (excerpt)
"""Helpers for UI flows. They drive the app only through its own UI."""

import time

import flet as ft
from flet.testing import Finder

STEP = ft.Duration(milliseconds=100)


async def wait_for_id(t, identifier: str, timeout: float = 15.0) -> Finder:
    """Pump frames until a control with this semantics identifier is built."""
    deadline = time.monotonic() + timeout
    while True:
        finder = await t.find_by_semantics_identifier(identifier)
        if finder.count:
            return finder
        if time.monotonic() > deadline:
            raise AssertionError(f"{identifier!r} not found within {timeout} s")
        await t.pump(STEP)


async def wait_for_text(t, text: str, timeout: float = 15.0) -> Finder:
    """Pump frames until a control showing exactly this text is built."""
    deadline = time.monotonic() + timeout
    while True:
        finder = await t.find_by_text(text)
        if finder.count:
            return finder
        if time.monotonic() > deadline:
            raise AssertionError(f"text {text!r} not found within {timeout} s")
        await t.pump(STEP)


async def tap_id(t, identifier: str) -> None:
    """Tap the first control with this identifier and let the result render."""
    await t.tap((await wait_for_id(t, identifier)).first)
    await t.pump(STEP)
```

The harness (`conftest.py` with `feed_url`, and the helpers above) arrives in P0 with the shell flow (P0-27); `open_developer()` and `fresh_start()` arrive with the first P1 flows (P1-30), once the Developer screen exists. `open_developer(t)` taps More → About this app → the version row (`about_app.version`) 7 times → Developer. `fresh_start(t, now=..., feed_url=...)` opens Developer, resets (confirmed), unlocks again, enters the clock and feed URL, applies and returns to Now.

### 5.3 An example flow

```python
# tests/ui/test_favourite.py
"""Save a session, find it in My schedule, remove it and undo (D-30, NEW-01)."""

import flet.testing as ftt

from tests.ui.helpers import fresh_start, tap_id, wait_for_id, wait_for_text

SESSION = "42"  # a talk on Friday in tests/fixtures/feeds/conference-2026.json


async def test_favourite_with_undo(flet_app: ftt.FletTestApp, feed_url: str):
    t = flet_app.tester
    await fresh_start(t, now="2026-05-15T09:00:00-07:00", feed_url=feed_url)

    await tap_id(t, "app.nav.schedule")
    await tap_id(t, f"schedule.favorite.{SESSION}")
    await tap_id(t, "app.nav.my_schedule")
    await wait_for_id(t, f"my_schedule.row.{SESSION}")

    # The star's accessible name carries its state (D-27, D-30).
    assert (await t.find_by_tooltip("Remove from My schedule")).count >= 1

    await tap_id(t, f"my_schedule.favorite.{SESSION}")
    # The SnackBar appears only after the on-device handler runs: poll for it.
    await t.tap((await wait_for_text(t, "Undo")).first)
    await wait_for_id(t, f"my_schedule.row.{SESSION}")
```

Shell controls (the navigation bar, app-wide chrome) use `app.<element>[.<key>]`, such as `app.nav.schedule` (decisions §M).

### 5.4 The flows

About eight journeys, added in the phase that builds them. Each runs on the Android emulator and the iOS simulator.

| # | Test | Phase | Journey and assertions | Ids / D |
|---|---|---|---|---|
| Shell | `test_shell_starts` | P0 | The test build starts; the five `app.nav.*` tabs are found; the Schedule stub shows the bundled days and its `schedule.source` label; no error screen. No offline assertion: the feed-URL override comes with the Developer screen (P1-28) | SHELL-03, SHELL-05, NEW-03 |
| F1 | `test_start_offline_shows_schedule` | P1 (after P1-08, P1-28) | With an unreachable feed URL set in Developer, the bundled rows render and no error screen appears; the status strip says offline and Refresh keeps the rows | NEW-03, DATA-02, SCHED-14, D-32, D-39 |
| F2 | `test_switch_days_keeps_selection` | P1 | Third day tab shows its rows; session → Back keeps the day | DATA-17, SCHED-01, D-18 |
| F3 | `test_search_finds_session_speaker_room` | P1 | An accent-folded query finds a session, a speaker and a room on different days; result → Back keeps the query | NEW-02, D-19, D-46 |
| F4 | `test_favourite_with_undo` | P1 | §5.3 | D-30, NEW-01 |
| F5 | `test_drill_back_one_step` | P1 | Session → speaker → session; each Back returns one step (titles); Back on the Schedule root goes to Now (Android) | SESS-12, SHELL-16, D-17 (#279) |
| F6 | `test_now_shows_next_session` | P1 | Fake clock during the conference with a saved session 25 min later: `now.next_session` shows it; a session that ended is not "happening now" | SCHED-25, D-14 |
| F7 | `test_room_pin_from_session` | P2 | Session → "Show on map" → floor plan with `map.pin.<room-slug>`; Back returns to the session | ROOM-04, MAP-05, DATA-32 |
| F8 | `test_offline_scans_sync_once` | P3 | Mock lead account (in-process mock, URL set in Developer); stop the mock; two manual entries show Queued; restart; Sync now → Confirmed; the mock holds one capture per code with the scan-time sponsor | LEAD-07, API-10, D-56, D-65 |

Scroll position (#313, Jump to now) cannot be read through a `Finder`, so it stays on the device checklist.

**When they run.** Locally before merging a PR that changes a journey (one platform), at every phase exit and after every Flet pin bump (both platforms), and once per phase at 200 % text (§7.2). A flaky flow gets a `test` issue and is fixed or deleted, never retried in a loop.

## 6. Goldens (P4 only)

Goldens churn while the UI evolves, so a handful arrive only in P4 (D-78):

- **Set:** Now, Schedule and Session detail, each in light and dark: six images.
- **One test, one launch:** `tests/ui/test_goldens.py` visits all six with the fixture feed and a fixed clock, switching the theme in Settings: `flet_app.assert_screenshot(name, await t.take_screenshot(name))` (99.0 % similarity by default).
- **One device:** a named Android emulator (recorded in the docstring); images in `tests/ui/golden/android/goldens/`. iOS goldens are optional.
- **Updating:** `-u` records; after an intentional change, `--update-failed-goldens` rewrites only what changed. The PR explains the image diffs. If the status bar shows in captures, freeze its clock with SystemUI demo mode.

## 7. Accessibility checks (D-33)

### 7.1 Automated: contrast

A unit test checks every declared text/background pair in each scheme: light and dark from P0, high contrast from P2. Text needs 4.5:1, or 7:1 in high contrast. Track badges and `Tokens` (`live`, `warning`, `success`, `favorite`) are checked the same way.

Roles left to the seed are computed by Flutter's `ColorScheme.fromSeed` on the Dart side (F9), so Python cannot check them. Hence one rule, also enforced by the test: **an overridden role is always declared with its "on" partner**. Seeded pairs are spot-checked on screen with Accessibility Scanner (§7.3).

```python
# tests/test_theme.py (excerpt)
import pytest

from pycon_us.theme import build_theme

PAIRS = [
    ("primary", "on_primary"),
    ("primary_container", "on_primary_container"),
    ("secondary", "on_secondary"),
    ("secondary_container", "on_secondary_container"),
    ("tertiary", "on_tertiary"),
    ("tertiary_container", "on_tertiary_container"),
    ("error", "on_error"),
    ("surface", "on_surface"),
    ("surface", "on_surface_variant"),
]


def luminance(hex_color: str) -> float:
    """Relative luminance of #RRGGBB, as defined by WCAG 2.x."""
    channels = [int(hex_color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    lighter, darker = sorted((luminance(a), luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("high_contrast", [False, True])
def test_declared_colour_pairs_are_readable(dark, high_contrast):
    scheme = build_theme(dark=dark, high_contrast=high_contrast).color_scheme
    minimum = 7.0 if high_contrast else 4.5
    for background, foreground in PAIRS:
        bg, fg = getattr(scheme, background), getattr(scheme, foreground)
        assert (bg is None) == (fg is None), f"{background} overridden without {foreground}"
        if bg is not None:
            assert contrast_ratio(fg, bg) >= minimum, (background, foreground)
```

### 7.2 Semi-automated: names, identifiers, large text

- **Names and states.** Flows find user-facing controls by their accessible names where it matters (`find_by_tooltip("Add to My schedule")`), which checks the label and its state (D-27, D-30). Structure is found by identifier.
- **200 % text.** Once per phase exit, the P1+ flows run with the largest text: Android `adb shell settings put system font_scale 2.0`; iOS `xcrun simctl ui <udid> content_size accessibility-extra-extra-extra-large`. A Flutter overflow error fails the run (§5.1). Confirm in the first such run that overflow is reported this way.
- **Reduced motion.** Flows run with animations disabled (§5.2), exercising the reduced-motion path.

### 7.3 Manual, at every phase exit

- **Screen readers.** TalkBack on an Android emulator (Google APIs images include it) and VoiceOver on the iPhone (the simulator has none) complete the phase's flows (D-102). Every control is reached in visual order and announced with name, role and state; each row reads as one phrase, with the star as its own stop; SnackBars and scan outcomes are announced.

  | Phase | Flows |
  |---|---|
  | P1 | Search → favourite → session detail (exit criterion 4); Now → your next session → room; change day and apply a filter |
  | P2 | Find a room on the map's list view; copy the Wi-Fi password; turn on reminders, including the permission primer |
  | P3 | Sign in with autofill; manual badge entry → outcome announced; open the sync queue and retry a failed row |
  | P4 | Every screen, once |

- **Tools.** Accessibility Scanner on Android (48 dp targets, contrast of seeded roles as rendered); Xcode's Accessibility Inspector on the simulator; a proposed "Show semantics" Developer switch setting `page.show_semantics_debugger` (exists in `BasePage`).
- **System settings.** Bold Text (iOS), high contrast where the OS reports it (iOS, Android 34+; re-read on resume, D-23), "Remove animations".

## 8. Performance (D-80, D-102)

Measured by hand at each phase exit, always on **release** builds (`flet build apk` / `ipa`), never on `flet run`, `flet test` or debug builds. S1 and S2 may revise the targets in the decisions record. The targets are written for a mid-range Android phone, which we don't have (D-102):
- **The iPhone** gives the numbers held against the targets (`ipa`, installed through TestFlight or Xcode).
- **An Android emulator** gives a relative regression signal only: the same emulator image (e.g. `Pixel_9_Pro_XL_API_35`, cold boot) on the same host, compared build to build and never against the targets. The host's load skews it, so close other heavy work while measuring, and report the host with the numbers.
- **A borrowed mid-range Android phone**, if we get one before P4, gives the absolute Android numbers (PLAN §11).

| Metric | Target | Method |
|---|---|---|
| Cold start to the cached schedule | ≤ 2.5 s | Median of 5 frame counts on a screen recording, from the icon tap to the first frame with session rows. iPhone: swipe the app away in the app switcher before each launch, and record with the Control Center screen recorder (the tap shows as the icon's highlight). Android emulator: the log-based method of D-112. After `am force-stop`, run `adb shell am start -W` ×10 on a quiet host; cold start = the app's "cached content rendered" log line minus logcat's `ActivityTaskManager: START u0` line (`adb logcat -v epoch`). Record `TotalTime` too, but it ends at Flet's boot screen, about 330 ms before the content (S1). The log line is a late proxy (0.2-0.3 s after the pixels in S1's recordings), good for build-to-build comparison. Baseline: 760 ms (D-112) |
| First launch (no cache: bundled snapshot) | recorded | Same, after clearing the app's data. iPhone: delete the app and reinstall the same build (this removes the data directory and SharedPreferences; Keychain items, SecureStorage from P3, survive). Android emulator: `adb shell pm clear <package>` |
| Feed processing | ≤ 400 ms | The app logs `feed processed in N ms` on every parse; median of 5 refreshes from the shared log (D-72) |
| Scrolling the busiest day | no visible jank | iPhone: Instruments' Animation Hitches. Android emulator (relative): Perfetto with the `android.surfaceflinger.frametimeline` data source during scripted flings (`adb shell input swipe`), janky frames recorded. Plus the eye test at 200 % text |
| Star tap and search keystroke latency | recorded (S2 sets any budget) | Frame counting on a screen recording |
| App size | recorded, not gated | APK and AAB size; download size with `bundletool get-size total`; IPA size from TestFlight |

Results go into the phase status issue (date, device or emulator image and host, OS, build, Flet pin). S1's reproducer (`docs/spikes/01-packaged-runtime/`) shows the logging, and its verdict the emulator baseline. A busy host moved S1's medians by about 25 %, so repeat a suspect run before filing. A regression over 20 % from the previous phase, on the iPhone or on the same emulator setup, gets a `bug` + `area:quality` issue.

## 9. Device checklist (D-79)

At each phase exit, with packaged builds on an Android emulator and an iOS simulator, and on the iPhone for the items that need hardware or a release build: items 1 and 2 with a TestFlight install of the phase build, the phase's exit journeys that name the iPhone (PLAN §7), VoiceOver (item 5), reminder delivery (item 12) and the camera (S8, E1) (D-102). Android items that would want hardware (a reboot, exact alarms, TalkBack) run on the emulator, and the results say so. Items marked with a phase start then. Results go into the phase status issue with device or emulator image, OS, build number and Flet pin.

1. Install over the previous build: favourites, settings and cache survive.
2. Cold start online; cold start in airplane mode (bundled or cached data, honest status strip from P1); kill and relaunch.
3. Light and dark; high contrast (P2).
4. Largest OS text and Bold Text on every screen of the phase: nothing clipped; titles wrap (D-26).
5. TalkBack and VoiceOver: the phase's flows (§7.3).
6. Android 3-button and gesture navigation: content never under system bars; edge-to-edge in light and dark, with status- and navigation-bar icons visible (`Theme.system_overlay_style`, #311, D-12).
7. Back: Android back and predictive back, iOS edge swipe; Back pops one step; Back on a root goes to Now, then exits (D-17).
8. Position: Schedule opens at the current slot once per app session; it never scrolls on Back, refresh or a filter change (#313, D-18).
9. Background for more than 15 minutes, then resume: refresh happens, accessibility flags are re-read.
10. Landscape, and a tablet emulator (rail from P2).
11. The companion app (`flet run --android` / `--ios`) shows the interim for every capability (P0 exit 3).
12. Reminders (P2): with E3 pinned, they fire with the app killed (on the iPhone and the emulator) and after a reboot of the emulator, and the tap opens the session with a back stack; without E3, the settings say "Reminders aren't available in this build" and Now, the Banner and `.ics` work (D-60). A denied permission never blocks a task.
13. Scans (P3): queue in airplane mode, survive kill and relaunch, sync once; sign-out with unsynced rows asks first.
14. The shared log contains no secret, email or badge code (D-72).
15. Deep links (P2): `adb shell am start -a android.intent.action.VIEW -d '<scheme>://app/schedule/session/<id>'` and `xcrun simctl openurl <udid> '<scheme>://app/...'`, cold and warm: the link lands on the session with its root below, so Back returns to the root; an unknown id lands on the root with a SnackBar (D-21).

## 10. Definition of done for a PR (D-93)

Every PR:
- [ ] Links its issue (`Closes #N`); CI is green.
- [ ] New behaviour has tests; a fixed bug has a test that failed before the fix.
- [ ] "How tested" lists the commands actually run, the devices or emulators used, and the Flet pin. Agents report only checks they ran.
- [ ] Docs and `decisions.md` are updated in the same PR.
- [ ] Follow-ups are filed as issues.

By kind of change:

| Change | Also required |
|---|---|
| `core/` or feed rules | Named rule tests; invariants still pass on every fixture year; any snapshot diff reviewed and explained in the PR body |
| Services and stores | Failure paths tested (network, HTTP error, corrupt data); no write to the cache before a good parse |
| UI | Screenshots on Android and iOS, light and dark. On an emulator or device: labels and states (TalkBack or the semantics debugger), 200 % text, targets ≥ 48 dp, reduced motion if it animates. Identifiers on new key controls. A changed §5.4 journey passes locally |
| Colours or theme | The contrast test covers every new pair |
| Private API or mock | Contract README updated with Ionic file:line; the PSF guard test unchanged and green |
| List rows, startup, feed parsing | Before and after numbers from a release build |
| Flet pin or dependency bump | Its own PR; all flows on the Android emulator and the iOS simulator; a packaged build smoke-tested on the emulator and the simulator (`flet build apk`, `flet build ios-simulator`) |

## 11. Quality gates per phase

Testing gates per phase, from PLAN §7's exit criteria (the milestone description carries the full list). A new testing gate is added to PLAN §7 in the same PR.

| Phase | Automated (CI green) | UI flows | Device, accessibility, performance |
|---|---|---|---|
| **P0** | Feed rules, invariants, snapshot (2025, 2026); Ionic reference captured; two-zone fixture; capabilities, storage keys, version, `core` purity; light/dark contrast | The shell flow (`test_shell_starts`) passes with `flet test` on an emulator and a simulator (PLAN P0 exit 3) | Checklist 1, 2, 6, 7, 11 on an Android emulator and an iOS simulator, 1 and 2 also on the iPhone; S1–S5 verdicts in `docs/spikes/`; D-80 targets confirmed or revised (D-102) |
| **P1** | + queries, time formatting, slugs, HTML→Markdown, refresh failure paths, favourites, track badges | The shell flow and F1–F6 on both platforms, once at 200 % text | Checklist 1–11; P1 screen-reader flows; a simulated conference day; D-80 numbers recorded |
| **P2** | + diff (#312), `.ics`, reminder plan, all year data, sprint-only rooms seeded from `map.toml` (MAP-08), high-contrast schemes | + F7 | + checklist 3, 10, 12, 15 (deep links); P2 screen-reader flows; an external tester's unaided task; numbers and app size re-recorded |
| **P3** | + signing vectors, mock contract, faults under both semantics, outbox machine, sqlite, staff truth table, favourites sync, PSF guard | + F8 | + checklist 13; P3 screen-reader flows; if E1 is bundled, printed mock badges scan on the iPhone (on Android, the emulator's virtual scene camera), including two devices checking in one attendee; otherwise the same scenario passes with manual or HID entry (PLAN P3 exit 5); compared with the mock's log |
| **P4** | All green; goldens added | All flows, both platforms, twice in a row | Full audit with both screen readers; targets met; no known data-loss or task-blocking bugs; clean-checkout build ≤ 30 min; the demo script runs end to end twice without Wi-Fi |

## 12. CI wiring (D-84)

- **`ci.yml`** (every PR and push to `main`, Linux): `uv sync --locked`, `ruff check`, `ruff format --check`, `pyright`, `pytest --hypothesis-profile=ci` (plain `pytest` until `tests/conftest.py` registers the profile, #114). Target under 2 minutes. UI flows are excluded by `addopts = ["--ignore=tests/ui"]` (§2).
- **`feed-check.yml`** (weekly): `tools/check_feed.py` runs our parser and the invariants on the current year's public feed (and next year's once it answers 200); unknown keys are printed, not failed.
- **`build-android.yml`** (manual and `v*` tags): a debug-signed APK artifact. iOS builds and all device work stay local.
- **Not in CI:** flows, goldens, device checks, performance. Spike S9 (PLAN §8; `Spike: flet test linux in CI`, label `test`, P2 at the earliest) tries `flet test linux` on `ubuntu-latest` under `xvfb-run` with a phone-sized window. Once it has run green for two weeks, it is proposed as a separate workflow through a `needs-decision` issue, since D-84 fixes three workflows and keeps `ci.yml` under 2 minutes; it never goes into `ci.yml` (D-78).

## 13. Flet testing gaps

Not in Flet today. Each has an interim; the upstream fixes are candidates without U-ids, filed as `upstream` issues only when a gap blocks a real test.

| Gap | Interim | Candidate upstream fix |
|---|---|---|
| `RemoteTester` has no drag, fling or scroll | Reach targets via search, day tabs, Jump to now; `adb shell input swipe` on Android | Drag and `scroll_until_visible` in the device protocol |
| Flows can't reach physical phones (`10.0.2.2` / `127.0.0.1` fixed, `flet_test_app.py:295`) | Emulator and simulator; the iPhone via the checklist | A host override (`adb reverse` on Android) |
| A `Finder` only counts matches | Assert presence of text, tooltips, identifiers | Finder text, bounds and semantics flags |
| `RemoteTester.pump_and_settle` has a fixed 60 s timeout | `wait_for_id` polling | A `timeout` argument, as on `Tester` |
| No accessibility guideline checks | Accessibility Scanner, Accessibility Inspector | Flutter's `meetsGuideline` on the tester |
| No text-scale emulation | `adb` / `simctl` settings (§7.2) | With U16 `PageMediaData.text_scale_factor` |
| No profile build or performance overlay | Perfetto, Instruments on release builds (§8) | A profile build mode in `flet build` |

## 14. Open points

- **Developer screen (D-73).** The flows need the identifiers in §5.2 and a fake-clock text field; a "Show semantics" switch is proposed (§7.3). Both land with P1-28, whose acceptance criteria list the identifiers and the 7-tap unlock.

Resolved on 2026-10-11 in PLAN and the decisions record: PLAN P3 exit 2 now matches D-57 (exactly once under idempotent semantics; never lost, with every duplicate detected and shown, under non-idempotent ones); D-75 lists `flet[test]` and the Flet host tooling; D-78 says flows run in device mode, and a `flet test linux` job comes only as a separate workflow after S9; §M lists the test paths and the `app.<element>` identifiers; D-96 keeps this file as the test strategy next to `development.md`.
