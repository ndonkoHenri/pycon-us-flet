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
| Public feed check (§12) | `tools/check_feed.py`, `httpx.MockTransport` in its tests | weekly | yes (cron) |

## 2. Layout, configuration and commands

```
tests/
  __init__.py          # tests are a package, so flows can import tests.ui.helpers
  conftest.py          # hypothesis profile, --snapshot-update, machine_tz, snapshot fixtures
  feeds.py, ionic.py   # helpers: the recorded feeds; Ionic's capture and its normaliser (§3.3)
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
| Accept a reviewed snapshot change | `uv run pytest tests/test_feed_invariants.py --snapshot-update` |
| UI flows on the Android emulator (development.md §5.7) | `uv run flet test android -d <emulator-id> --tests-dir tests/ui -v` |
| UI flows on the iOS simulator | `uv run flet test ios -d <simulator-udid> --tests-dir tests/ui -v` |
| One flow | add `-k shell` |
| Record or update goldens (P4) | add `-k goldens -u`, or `--update-failed-goldens` |
| Public feed check | `uv run python -m tools.check_feed` (add years to check others, e.g. `2025 2026`) |

## 3. Unit tests

### 3.1 Conventions

- **Descriptive names** (`test_lunch_row_spans_earliest_start_to_latest_end`). A feature id may appear in the docstring; nothing enforces it (D-04).
- **`core` takes `now` as an argument** (D-43), so tests pass fixed aware datetimes. Only `clock.now()` itself is tested with its override.
- **No network, no Flet runtime.** `core/` tests import no Flet (D-68). Stores are plain `@ft.observable` dataclasses and run without a page; `Observable.subscribe(fn)` checks that a change notifies. `subscribe` holds listeners weakly (a `weakref.WeakSet`): in tests bind the listener to a local name (`def on_change(sender, field): ...`) and keep it alive for the test; never pass a lambda, which is collected at once and never called.
- **Hypothesis** runs derandomised in CI (`--hypothesis-profile=ci`): hypothesis's built-in `ci` profile (no deadline, no example database, `too_slow` health check off, `@reproduce_failure` blob printed), which `tests/conftest.py` extends to 200 examples per property; `tests/test_hypothesis_profile.py` pins those values. CI names the profile on the command line instead of leaving it to the `CI` variable, which hypothesis also reads. Local runs use the default profile (100 random examples, 200 ms deadline) unless a `CI` variable is set in the shell; add `--hypothesis-profile=ci` to reproduce a CI failure.
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
| Ids are strings in four stable forms | `test_ids_are_unique_stable_strings_in_ionics_forms` (an invariant) | DATA-26, D-42 |
| A malformed slot is skipped and logged; the rest of the day survives | `test_bad_slot_is_skipped_and_logged` (uses `caplog`) | D-41 |

**Bundled snapshot** (NEW-03, D-135). `test_the_bundled_snapshot_processes_cleanly` processes `src/pycon_us/data/<YEAR>/conference.json` and expects no skipped record, the bar `tools/update_snapshot.py` applies before it writes; the invariants below take the snapshot as an input too. The tool's own tests serve the recorded feed, or a broken copy, through `httpx.MockTransport`.

**Invariants** (`tools/feed_invariants.py`, tested by `tests/test_feed_invariants.py`; built in P0-13, shared in P0-07). Each invariant returns its problems, one line each, instead of asserting. One test per invariant asserts the list is empty on every fixture year under both machine zones, and `tools/check_feed.py` prints the lists for the live feed every week (§12), so both run the same code. An empty list proves nothing about an invariant that cannot fail, so `tests/test_check_feed.py` also breaks the 2026 model once per invariant (`BREAKS`: reversed days, a session in UTC, a missing speaker, ...) and asserts the problem it reports. Two more tests check that every invariant the tool runs has both its fixture test and a way to break it:

1. No session lost: every raw slot is its own session or listed in `ConferenceData.dropped` under exactly one named rule (D-123); every collapsed slot lies within a row of its kind on its day; every open space is a session or unscheduled, judged from its raw times and room; every raw poster, top-level or nested (D-121), has its detail session.
2. Ids are unique strings in Ionic's four forms, and processing the same bytes twice gives the same outline.
3. Every session lies in exactly one conference-local day within the conference dates, and timeline sessions are in exactly one time group.
4. All datetimes are aware, in the year's zone; `start <= end`.
5. Every time group has a start; groups are sorted; within a group, rows are ordered by location, then name (D-31).
6. No raw slot of a dropped category (free or duplicate open spaces, placeholders, the Posters plenary, blanks) or of a collapsed kind is a session of its own; each day with poster slots has exactly one Posters row; a feed with break slots has at least one break row.
7. Exactly one Lunch row per conference day that has lunch.
8. Every session shows its start shifted by the first display-time override its title matches, or unshifted; grouping keeps the start (the Job Fair, DATA-11).
9. Every speaker a session links is in the directory and named in it, and every directory speaker has a session; no pseudo-speaker is in the directory.
10. One room per slug, naturally sorted, listing exactly the sessions that name it, by start, then name.

Processing is pure by construction: `process()` takes bytes and returns new frozen values.

**Snapshot of our model.** A compact, reviewable outline of the processed model is compared with `tests/fixtures/snapshots/outline-<year>.json`: days → groups (by conference-local `HH:MM`) → one line per session, `id | name | track | shown location | start-end`, then `shown HH:MM`, `pre-registration`, `español`, `speakers <ids>` and `text <names not in the directory>` when they apply; then the sessions outside the timeline (poster details), the rooms with their counts, the speaker directory, the drop counts and the skipped records; last, `markdown`: every content block's Markdown and the first value that conversion changed of each other converted field, one Markdown line per JSON string (D-140). The outline function, `outline()`, lives in `tools/feed_invariants.py` next to the stable-ids invariant that compares two outlines; a full `dataclasses.asdict` dump would be too large to review. It runs under both machine zones, so it also proves the model does not depend on the machine's zone. When a parser change alters the outline, the PR runs `uv run pytest tests/test_feed_invariants.py --snapshot-update` and explains the diff in its body.

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

**Ionic reference (captured once).** `tools/capture_ionic_reference/` copies Ionic's `conference-data.ts` (and what it imports for `processData`) unchanged, stubs Angular and RxJS, bundles it with esbuild and runs `processData` under Node on both feeds; it writes the facts to `tests/fixtures/ionic/<year>/` (`summary`, `timeline`, `sessions`, `collapsed`, `rooms`, `speakers`), and its README records the provenance (Ionic commit, Node, esbuild and package versions, date) and how to re-run it. CI and contributors never need Node (D-77). `tests/test_ionic_reference.py` compares our model with those facts through the normaliser in `tests/ionic.py`, on both feeds and under both machine zones:

- the session ids (including Ionic's synthetic ids) and each session's name, track, location, shown location, start, end, shown start (the Job Fair's label), linked speakers, author names and flags;
- the days, their time groups in order and the rows in each (as sets: D-31);
- the collapsed rows and their spans;
- the rooms with their sessions, and the room order (`room_sort_key` against Ionic's `localeCompare`);
- the speaker directory, in order, and each speaker's sessions.

Deliberate differences live in one dict, `INTENDED_DIFFERENCES` (D-121 nested posters, D-122 the hall prefix, D-124 the lightning talks' place, D-125 the pseudo-speaker and room order, D-31 row order, DATA-13 group starts, MAP-08 sprint rooms), each with its own named test that shows it on the captured output. Every other difference is a bug to fix: the first capture found 2025's code spans in titles (Ionic's `markdownToTxt` drops the backticks), now stripped in `core/names.py`. Ionic is a reference, not an oracle.

### 3.4 Other `core/` modules

| Module | What the tests pin | Ids / D |
|---|---|---|
| `queries.py` | Search folds case and accents, needs **all words**, matches text not markup. My schedule, Now and Search ignore filters. Happening means `start <= now < end`; next session = the earliest saved session with `end > now` that is ongoing or starts within 3 h (none otherwise); overlaps flag both rows | D-46, NEW-02, D-20, SCHED-25, NEW-01 |
| `timefmt.py` | 12/24 h from the flag; "Pacific Time" note when zones differ; DST; local day bucket; relative ages | D-35, DATA-12, DATA-31 |
| `slugs.py` | Room, track and sponsor slugs on real names (vectors cite their Ionic source line) | DATA-16, DATA-29 |
| `html_md.py` | Every tag in the S3 census and each "could change meaning" case of `docs/spikes/03-html-markdown.md`, on its 22 feed samples and the synthetic hazard line; links made absolute, only `http(s)`/`mailto` linked; unknown tags unwrapped; plain-text paragraphs kept; escaping (LaTeX, GFM, block markers); boundaries (emphasis next to punctuation, link-edge whitespace, URLs with punctuation, queries and entities, URLs inside link text, an item holding only a nested list, multi-paragraph items, `br` in a heading, empty or space-edged code); an invariant over both fixtures: no character lost or added and no raw tag, `$` or LaTeX opener outside code; the search text has no markup and keeps word boundaries; hypothesis properties: plain text and random tag mixes keep every visible character (D-131's boundaries came from them). Expected sample Markdown is `tests/fixtures/html_md/samples.json`, equal to what S3 checked on the emulator | D-44, D-114, D-115, D-130, D-131, SESS-06 |
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
| Capabilities (`tests/test_capabilities.py`) | With `FLET_PLATFORM` unset (`monkeypatch.delenv`, then `importlib.reload(capabilities)`, because the capabilities are import-time constants), every capability constant is `False` even when every extension is findable, and `available()` is `False` for every module, so the companion app gets interims; embedded, each constant follows `find_spec` | D-63 |
| Routes | `drill_href()` round-trips every id form, including synthetic ids with spaces or slashes, URL-quoted (`quote(ident, safe="")`), and the drill route decodes it back. `parent_of(route, search_base)` on every route shape: drops the last drill pair, else walks up to the nearest page (`/more/tracks/python` → `/more/tracks`, `/more/staff/lead` → `/more`), and `/search` returns the remembered base, query included | D-42, D-21, D-19 |
| Storage keys | Every key in the table starts with `pycon.`, keys are unique, values have SharedPreferences types | D-49, F12 |
| `Conference` (`tests/test_state.py`) | `httpx.MockTransport` + temporary data dir + the in-memory SharedPreferences (`tests/fakes.py`): two concurrent refreshes send one request, and cancelling one caller leaves the shared refresh running; a connect error, timeout, HTTP error, HTML page or truncated body keeps the published data and the cache file and sets `problem`; a good refresh caches the raw bytes and clears it; an unexpected error is logged as soon as the refresh ends, awaited or not; a cache that cannot be written still publishes; a corrupt cache is deleted, then the snapshot is used; `status()` under `clock.set_test_now()` in both machine zones: 6 h on conference days, 24 h otherwise; `refresh_due()` 15 min after a refresh began, failed or not, and at once after a clock set back; none is due while one is in flight, and an automatic refresh that fails (every failure above) keeps the data and the cache file; an automatic refresh, the start's included, is quiet: over fresh, stale and offline data `status()` says what it said before at every notification, while `refreshing` is set; `refresh()` says `refreshing` until it ends, outranks the last problem, and joining a quiet refresh says so at once with one request; the next automatic one is quiet again | D-39, D-120, D-145, D-146, D-175, D-181, DATA-02, DATA-03 |
| `Services.run_every` (`tests/test_services.py`) | Millisecond intervals on the test's loop: a call at once, then one per interval; none while `foreground` is clear, and one at once on resume; cancelling the task (an unmount) stops the calls; a closed session ends the loop, also while it waits in the background | D-40, D-147, D-175 |
| `StatusStrip` ticks (`tests/test_scaffold.py`) | The component's body with its hooks answered by the test and `Services.run_every` recorded: the effect has a cleanup, so Flet cancels it on unmount (F2, F39); a tick re-renders only when the minute changed, and shows the strip once the data turns stale; with `auto_refresh` a tick starts a refresh when due and not 1 s before; without it never; Now and Schedule pass `auto_refresh=True`, My schedule does not; the strip during a refresh: the user's says "Updating the schedule…" with Refresh disabled; an automatic one keeps the strip hidden over fresh data, and over an offline strip leaves its visibility, icon, colour, line and button the same at every render while the bar comes and goes; Refresh during a quiet one re-renders it as the user's at once | D-40, D-175, D-181 |
| `Prefs` (`tests/test_prefs.py`) | The in-memory SharedPreferences: defaults on first launch (Open Space hidden, an explicit `[]` kept); stored values read back; an unknown Appearance or High contrast value reads as `system`, logged with the key only; `save()` persists and survives a relaunch, writes only what it is given, keeps a change that could not be saved and returns `False`, and rejects an unknown value before writing; `dark` and `high_contrast_on` follow the OS only under System | D-120, D-160 |
| Start sequence (`tests/test_app.py`) | `bootstrap()` with the fakes of `tests/fakes.py` and `api.fetch_feed` replaced: the gate opens on the bundled feed while the network is held; the stored theme is on the page, with no theme animation, and the year's favourites are loaded, before the gate opens; cache before snapshot; offline and online starts; an unexpected error is logged and the gate still opens, and one before the favourites' read leaves them unsaved rather than written over; the page handlers write the stores, and `page.on_close` stops the refresh, also when the session closes during the start (no gate, no refresh, no error logged); `pause` clears `Services.foreground` and `resume` sets it, refreshes once the last refresh began 15 min ago (not before) and, offline, keeps the data and says so; a resume re-reads the accessibility flags, and a failed read on resume keeps the last ones; theme changes still crossfade under reduced motion. The components themselves (`BootView`, the providers) are checked on devices | D-69, D-147, D-161, D-173, D-175, DATA-35 |
| `fetch_feed` (`tests/test_api.py`) | `httpx.MockTransport`: the body byte for byte, a 10 s timeout, redirects followed; every transport error is a `NetworkError`, an error status or a redirect loop an `ApiError` | D-53, D-146, DATA-01 |
| `Favorites` (`tests/test_favorites.py`) | The in-memory SharedPreferences: favourites survive a relaunch (saved sorted as `list[str]`); a 2026 favourite never marks a 2027 session; an unreadable value reads as none, logged; a change that cannot be saved is kept and reported (`saved=False`); after a failed read, or with no read at all, edits are shown but never written over the saved list, and `loaded` stays False; a toggle notifies exactly once and shows before the write answers; two taps during one write keep both; `add_many` and `remove_many` report only what they changed and notify once; an edit that changes nothing neither notifies nor writes; a lone string is refused; Undo of a toggle, `add_many` and `remove_many`, an Undo undone, and an Undo after the user changed the same session | D-48, D-120, D-172 |
| Favourites sync (P3) | First sync is the union; a dirty local list is pushed before a pull; sign-out keeps the local list; a failed PATCH sets `dirty` | D-55, API-04 |
| `@report_errors` (`tests/test_errors.py`) | On a sync and an async callable, with a fake page bound as Flet binds it: logs the traceback with the function's name, shows the floating SnackBar (the exception only when not embedded) and returns None; a success returns its value (a sync effect's cleanup included) and shows nothing; `CancelledError` and other `BaseException`s propagate, and a cancelled effect task ends cancelled; with no page it still logs; the wrapper keeps the original's async-ness (`inspect.iscoroutinefunction`) and Flet's parameter count (`__wrapped__`); generator functions are refused. `tests/test_app.py` checks that a page handler's unexpected error is reported instead of raised, and an AST check finds every function defined inside `main.py`, `routes.py`, `screens/` and `ui/` (each one a handler or an effect setup) decorated with `@report_errors`. That the session then lives on is a device check | D-71, D-163 |
| Logging (`tests/test_errors.py`) | `setup_logging()` adds one stderr handler at INFO, however often it is called, and a second call keeps the levels set since; the logging tests start from untouched loggers, whatever ran before; lines carry time, level, logger and message; `FLET_LOG_LEVEL` sets the level; a request whose URL holds a fake secret, email and badge code leaves none of them in `caplog.text` (without the setup, httpx's INFO line shows them) | D-72, D-163 |
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
| Broken on device (#78) | `take_screenshot` works once per run on Android: it converts the Flutter surface to an image on every call, and the second call fails ("Surface already converted to an image"). `find_by_icon` sends Flet's packed icon value (`int(ft.Icons.CHEVRON_RIGHT)` is `0x10551`, set and index) where the device builds `IconData(<value>, fontFamily: "MaterialIcons")` from it (`_parseIcon` in `flet_integration_test`'s `remote_widget_tester.dart`), so it cannot match a Material icon (read in the source, not tried on a device). Flows use `adb exec-out screencap` / `simctl io screenshot` and find rows by text or identifier (D-171). |
| Lifecycle | Every run packages the app's Python again, then `flutter test` installs a debug build, launches it and uninstalls it when the flow ends: each flow starts from a fresh install, with the app's own bundle id (development.md §5.7). Finders skip offstage widgets (Flutter's `skipOffstage`): once a push has finished, the covered View's controls are no longer found, which is how a flow knows a push or a pop is over. |
| Assertions | A Flutter-side error (for example "RenderFlex overflowed") makes `flutter test` exit non-zero, and `FletTestApp.teardown()` then raises, so the test fails even if every Python assertion passed. |
| Targets | `FletTestApp` points the app at `10.0.2.2` on Android and `127.0.0.1` on iOS (`flet_test_app.py:295`). Those reach the laptop only from an **emulator or simulator**, so flows run there; the iPhone is covered by the device checklist (§9). |

### 5.2 Driving state without test hooks

- **Identifiers.** Key controls carry `Semantics(identifier="<screen>.<element>[.<key>]")` (D-33, §M), e.g. `schedule.favorite.42`, `now.next_session`. They become Android `resource-id` and iOS `accessibilityIdentifier`, so they never contain names, emails or badge codes. Plain string literals; a typo fails a flow.
- **The Developer screen** (D-73) sets the scene; flows unlock it with 7 taps on the version row, as a person would. It needs `developer.reset` (+ confirm), `developer.fake_clock` (ISO 8601 text), `developer.feed_url`, `developer.mock_url` (P3) and `developer.apply`.
- **Data.** The `feed_url` fixture (in `tests/ui/conftest.py`) serves `tests/fixtures/feeds/` from the laptop with `http.server.ThreadingHTTPServer` on `127.0.0.1` and returns the URL the app can reach: `http://10.0.2.2:<port>/conference-2026.json` on Android, `http://127.0.0.1:<port>/…` on iOS. The fake clock sits inside the 2026 dates. "Offline" is a feed URL on a closed port: real airplane mode would also cut the tester's socket.
- **Which screen.** A `Finder` only counts matches, and a root's title also shows as its tab's label, so each tab root's app-bar title carries `<tab>.title` (`now.title` … `more.title`, D-170); a pushed View is known by its back arrow (`find_by_tooltip("Back")`) and by the bar's absence (D-144).
- **Back.** Both platforms: tap the app bar's back arrow (`tap_back_arrow`). Android also: the Back key, `adb -s $FLET_TEST_DEVICE shell input keyevent KEYCODE_BACK` from the test (`press_system_back`). The iOS edge swipe and Android predictive back stay manual (§9).
- **Settling.** Indeterminate progress and shimmer never settle, so helpers poll with `pump(duration)` until a finder matches, or stops matching. While a push or a pop runs, both Views are on screen, and a tap on the one leaving is lost: a flow waits for the leaving View's marker to be gone, and `tap_back_arrow` for exactly one back arrow (#78 lost a tap that way). Android emulators run with the three animation scales at 0 (`adb shell settings put global transition_animation_scale 0`, etc.); Flutter reports that as `disable_animations`, which the app honours (D-34).

`tests/ui/helpers.py` (D-171):

| Helper | What it does |
|---|---|
| `remote(flet_app)` | The `RemoteTester`; fails outside device mode |
| `wait_for(t, find, what, gone=, count=)` | Pumps 100 ms at a time until `find()` matches (or matches none, or exactly `count`), at most 15 s; on a timeout saves `timed-out.png` if the device still answers, and fails with what it saw |
| `wait_for_id`, `wait_for_text`, `wait_for_tooltip` | `wait_for` with an identifier, an exact text or a tooltip |
| `tap(t, finder)`, `tap_id`, `tap_text` | Tap the first match once it is on screen, then pump once |
| `tap_first_text(t, texts)` | Tap whichever of these texts shows first: for rows a feed refresh may change, such as the first speakers |
| `tap_back_arrow(t)`, `press_system_back(t)` | Back, as above |
| `screenshot(name)` | `build/ui/<platform>/<name>.png` through `adb exec-out screencap -p` or `xcrun simctl io <udid> screenshot`, not `take_screenshot` (§5.1) |

`tests/ui/conftest.py` holds `feed_url`. The harness arrived in P0 with the shell flow (P0-27, #78); `open_developer()` and `fresh_start()` arrive with the first P1 flows (P1-30), once the Developer screen exists. `open_developer(t)` taps More → About this app → the version row (`about_app.version`) 7 times → Developer. `fresh_start(t, now=..., feed_url=...)` opens Developer, resets (confirmed), unlocks again, enters the clock and feed URL, applies and returns to Now.

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
| Shell | `test_shell_starts` | P0 | The test build starts on Now (`now.title`) with the five `app.nav.*` tabs; each tab shows its root; the Schedule stub shows its `schedule.source` label and the first conference day; More → Speakers (a pushed page, no bar) → one of the snapshot's first five speakers (a drill level; a networked device lists the live feed's, P1-30's `fresh_start()` makes it a recorded one); the back arrow pops one level at a time to the More root and its bar; on Android the Back key pops a push and takes the More root to Now; no Flutter error. No offline assertion: the feed-URL override comes with the Developer screen (P1-28) | SHELL-03, SHELL-05, NEW-03, D-17, D-141, D-144 |
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

A unit test checks every declared text/background pair in each scheme: light and dark from P0, high contrast from P2. Text needs 4.5:1, or 7:1 in high contrast. Track badges and `Tokens` (`live`, `warning`, `success`, `favorite`) are checked the same way: a tonal badge's label on its fill, and the outlined "Registration required" badge's label on every surface of the neutral ramp, since it has no fill of its own (D-174). A test also checks that every `Tokens` field is one of the two kinds, and that every track key of every year has its own pair.

Roles left to the seed are computed by Flutter's `ColorScheme.fromSeed` on the Dart side (F9), so Python cannot check them. Hence one rule, also enforced by the test: **an overridden role is always declared with its "on" partner**. Seeded pairs are spot-checked on screen with Accessibility Scanner (§7.3). Light and dark also declare `surface`, `on_surface` and `on_surface_variant` (the values of Flet's neutral ramp) and `error` / `on_error` (the seed's own, D-174), and the test checks those text roles, `primary` (links) and the tokens on every surface of that ramp (`surface`, `surface_bright`, `surface_dim` and the five `surface_container*`), mirrored from `neutralizeSurfaces` in Flet's `utils/theme.dart`, since cards, sheets, bars and Markdown code spans sit on them.

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
| Cold start to the cached schedule | ≤ 2.5 s | Median of 5 frame counts on a screen recording, from the icon tap to the first frame with session rows. iPhone: swipe the app away in the app switcher before each launch, and record with the Control Center screen recorder (the tap shows as the icon's highlight). Android emulator: the log-based method of D-112. After `am force-stop`, run `adb shell am start -W` ×10 on a quiet host; cold start = the app's content line minus logcat's `ActivityTaskManager: START u0` line (`adb logcat -v epoch`). `AppScaffold` logs it, `Content shown: <source> feed, version <n>`, once per feed version per session, from the first screen that renders that version (D-165): a cold start logs version 1 (cache or bundled) on whatever screen it opens, and the refresh's version 2 follows; tab switches log nothing. The first line after `START u0` is the mark. Record `TotalTime` too, but it ends at Flet's boot screen, about 330 ms before the content (S1). The log line is a late proxy (0.2-0.3 s after the pixels in S1's recordings), good for build-to-build comparison. Baseline: 760 ms (D-112) |
| First launch (no cache: bundled snapshot) | recorded | Same, after clearing the app's data. iPhone: delete the app and reinstall the same build (this removes the data directory and SharedPreferences; Keychain items, SecureStorage from P3, survive). Android emulator: `adb shell pm clear <package>` |
| Feed processing | ≤ 400 ms | The app logs `feed processed in N ms` on every parse; median of 5 refreshes from the shared log (D-72) |
| Scrolling the busiest day | no visible jank | iPhone: Instruments' Animation Hitches. Android emulator (relative): Perfetto with the `android.surfaceflinger.frametimeline` data source during scripted flings (`adb shell input swipe`), janky frames recorded. Plus the eye test at 200 % text |
| Star tap, search keystroke and day switch latency | median handler → patch within one frame (16 ms) for star taps and keystrokes on the busiest day on the emulator (day switches recorded); the iPhone's numbers recorded (D-159) | D-159: the app's `<action>-in` / `patched` log lines for Python's share, and a screen recording for the screen (the keystroke's character, the tab indicator, or for a star a keystroke at the start that maps the video clock onto the log). `docs/spikes/02-day-list/drive_android.py` runs it. Baseline: star and keystroke 3 ms, day switch 2 ms (S2) |
| App size | recorded, not gated | APK and AAB size; download size with `bundletool get-size total`; IPA size from TestFlight |

Before an emulator run, check that the emulator is not throttled: during S2 it twice ran 3-4.4× slower for half an hour or more, each time some 20-30 minutes after the host's user went idle, with priority 4 (background) on every qemu thread (`ps -M -p <qemu pid>`). Compare the app's `feed processed in N ms` line with the last run first (66 ms on `pycon_pixel6a_api36` in S2); if it is far off, the run is not comparable: measure while the host is in use.

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

- **`ci.yml`** (every PR and push to `main`, Linux): `uv sync --locked`, `ruff check`, `ruff format --check`, `pyright`, `pytest --hypothesis-profile=ci` (hypothesis's built-in profile, extended in `tests/conftest.py`, §3.1). Target under 2 minutes. UI flows are excluded by `addopts = ["--ignore=tests/ui"]` (§2).
- **`feed-check.yml`** (weekly): `tools/check_feed.py` runs our parser and the invariants on the current year's public feed, and says whether next year's feed answers yet (a 404 is "not published yet", never a failure). Keys the recorded feeds lack are printed, not failed. Its tests serve the recorded feed, broken copies of it and HTTP errors through `httpx.MockTransport` (`tests/test_check_feed.py`).
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
| `RemoteTester.take_screenshot` fails from its second call on Android (#78) | `adb exec-out screencap -p`, `xcrun simctl io <udid> screenshot` | Convert the surface to an image only once per run (`flet_integration_test`'s `takeScreenshot`) |
| `RemoteTester.find_by_icon` sends Flet's packed icon value, so it cannot find a Material icon (#78, from the source) | Find by text, tooltip or identifier | Decode the packed value on the device, as Flet's own icon parsing does |
| No profile build or performance overlay | Perfetto, Instruments on release builds (§8) | A profile build mode in `flet build` |

## 14. Open points

- **Developer screen (D-73).** The flows need the identifiers in §5.2 and a fake-clock text field; a "Show semantics" switch is proposed (§7.3). Both land with P1-28, whose acceptance criteria list the identifiers and the 7-tap unlock.

Resolved on 2026-10-11 in PLAN and the decisions record: PLAN P3 exit 2 now matches D-57 (exactly once under idempotent semantics; never lost, with every duplicate detected and shown, under non-idempotent ones); D-75 lists `flet[test]` and the Flet host tooling; D-78 says flows run in device mode, and a `flet test linux` job comes only as a separate workflow after S9; §M lists the test paths and the `app.<element>` identifiers; D-96 keeps this file as the test strategy next to `development.md`.
