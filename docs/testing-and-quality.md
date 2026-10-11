# Testing and quality: PyCon US 2027 app on Flet

**Status:** companion to [`PLAN.md`](../PLAN.md) §8, written 2026-10-11. **Owner:** U.

**Binding inputs**
- The decisions record ([`decisions.md`](decisions.md)): D-97..D-100 (testing), amended by D-119 and D-129, D-14 (Badge Days), D-70 (a11y), D-85..D-88 (errors and crash reporting), section M (names), section N (SDK facts).
- [`PLAN.md`](../PLAN.md): §2 (criteria S1-S12), [§7.4](../PLAN.md#74-gono-go-checkpoints) (gates) and [§8](../PLAN.md#8-quality).
- [`feature-matrix.md`](feature-matrix.md) for the ids, such as `SCHED-16`.

**Flet ground truth.** Testing names were read from the local 1.1.0 monorepo on 2026-10-11: `flet/testing/` (`FletTestApp`, `Tester`, `Finder`, `RemoteTester`; `RemoteTester` is not in `flet.testing.__all__`, so import it from `flet.testing.remote_tester`), `flet/pytest_plugin.py` (fixtures `flet_app`, `flet_app_function`), `flet_cli/commands/test.py` (`flet test`), `packages/flet/integration_tests/README.md` and the integration-testing guide. Anything not yet in Flet carries its upstream id (U1..U15, E1..E6).

---

## 1. Layers at a glance

| # | Layer | Where | Tools | Cadence and gate | Proves |
|---|---|---|---|---|---|
| L1 | Unit | `tests/unit/` | pytest, hypothesis | every PR | `core/` rules, stores, API client, caps, tokens |
| L2 | Differential | `tests/differential/`, `tools/ionic_reference/` | Node 22, esbuild, pytest | every PR | Python `core` equals Ionic's own code on the 2025 and 2026 feeds (criterion S2) |
| L3 | Contract | `tests/contract/` | jsonschema | PR (recorded) + nightly (live) | feed and `/api/v1` shapes; drift opens an issue |
| L4 | UI flows | `tests/ui/` | `flet_app`, `Tester`/`RemoteTester` | PR smoke (host) + nightly (all host flows + device mode) | 29 user flows with their ids (§6) |
| L5 | Fallback parity | `tests/fallback/` | L4 + caps fakes | nightly; PR when `platform/` changes | every capability works on (upgrade) and off (interim) |
| L6 | Feature trace | `tools/feature_trace.py` | AST + junit XML | PR gate (ramped), weekly burn-down | each non-dropped id has a passing test (criterion S1) |
| L7 | Goldens | `tests/golden/` | `take_screenshot` + `assert_screenshot` | nightly full, PR subset | 14 screens × 5 modes × 2 widths + text scale 2.0 |
| L8 | Device lab | §10 | physical devices (D-100) | each RC | hardware, store update path, budgets |
| L9 | Field | §11 | printed badges, PSF staff, server audit | 2027-02-24, 2027-04-09 | criterion S4, gates G-Staff and G5 |

Also covered: a11y (§12, criterion S7), performance (§13, criterion S6), observability (§14, criterion S5), CI wiring (§15), gates G4 and G5 (§16), and the open points (§17).

**Naming (D-98):** `test_<AREA>_<NN>_<slug>`, e.g. `test_SCHED_10_default_excludes_open_space`. Tests without an id use lower-case prefixes (`test_gh312_*`, `test_obs_*`, `test_tool_*`), which `feature_trace` ignores.

---

## 2. Shared infrastructure

### 2.1 Layout and configuration

```
tests/
  conftest.py            # hypothesis profiles, markers (skips `device_only` in host mode, `host_only` in device mode), autouse `scenario` fixture
  fixtures/  feeds/conference-{2025,2026}.json (+2027 sample from P8)   api/<endpoint>/<case>.json
             app-config/ app-content/ (valid + invalid)   badges.csv (P3)   media/ (images for goldens)
  harness/   scenario.py  host_main.py  fakes.py  devserver_client.py  nav.py     # no test_ files
  unit/ differential/ contract/ ui/ fallback/ golden/ perf/
```

```toml
[dependency-groups]
dev = ["flet[test]==1.1.*", "flet-cli==1.1.*", "flet-desktop==1.1.*", "hypothesis", "jsonschema", "playwright"]  # exact pins at M0; the flet-main job relaxes these (§7)

[tool.pytest.ini_options]
asyncio_mode = "auto"                 # required: tests share the flet_app fixture's loop
pythonpath = [".", "src"]
testpaths = ["tests/unit", "tests/differential", "tests/contract"]   # bare `uv run pytest` never starts Flutter
markers = ["scenario(**kw)", "smoke", "device_only", "host_only", "live"]
```

`flet[test]` (pytest, pytest-asyncio, numpy, Pillow, scikit-image) is pinned like `flet` (D-20).

### 2.2 Devserver and scenarios

`tools/devserver.py` (D-94) serves:
- the recorded feeds, app-config and app-content;
- a fake signed `/{YEAR}/api/v1` that **verifies** the sha1 signature as `APIAuth.verify_request` does, so signing is tested end to end;
- check-in, lead, CoC and `mobile_state` semantics from `tests/fixtures/`.

Test-only endpoints: `PUT`/`GET /__test__/scenario` (the test sets it, the app reads it at boot); `PUT /__test__/network {"up", "latency_ms", "status"}` (offline as connection reset, slow link → `Timeout`, 5xx/403); `GET /__test__/log` (recorded calls for assertions); `POST /__test__/reset`.

**App-side hook**, active only when `page.test is True` **and** `settings.PYCON_ENV == "dev"`. `page.test` is True under any Flet test run: in device mode via `--dart-define=FLET_TEST=true`, which `FletTestApp` passes, and in host mode because the host client attaches a tester. Host mode never reaches the HTTP hook, because `host_main.main` skips bootstrap step 0. In device mode, bootstrap step 0 (test-only, before D-46 step 1; §17.4) reads `GET /__test__/scenario` from `http://10.0.2.2:8765` on the Android emulator (DEV-07), `http://127.0.0.1:8765` elsewhere. Release builds are `prod` and never get `FLET_TEST`; `tools/check_release.py` also refuses a release `build_info` with `PYCON_ENV="dev"`.

**Scenario fields.** Each one drives an existing mechanism; none adds behaviour.

| Field | Default | Drives |
|---|---|---|
| `reset_storage` | `True` | the DEV-05 "nuke" path, run before prefs load |
| `fake_now`, `clock` | `None`, `"frozen"` | `conf_now()` override, as `PYCON_FAKE_NOW` (D-52) |
| `feed`, `seed_cache` | `"2026"`, `False` | the served fixture; a pre-written `conference-{YEAR}.json` |
| `theme`, `prefs` | `None` | pre-seeded SharedPreferences (D-60 keys) |
| `role` | `None` | login with a devserver key: `attendee`, `lead`, `door`, `door_lead` or `mask` (Ionic has three role flags; Swag is gated by `door_check`, D-41, so Swag tests use `door`) |
| `app_config` | `{}` | merge patch: veto-only `features`, `banners`, `latest`, `min_supported` |
| `caps` | `"manifest"` | §7 |
| `animations` | `False` | forces the `reduce_motion` path (D-70) and freezes banner rotation, so `pump_and_settle()` can settle |

**Host mode** skips HTTP for app state. The plugin imports `tests/harness/host_main.main` (`FLET_TEST_APP_PATH=tests/harness`, `FLET_TEST_APP_MODULE=host_main`), which skips bootstrap step 0 and calls `page.render_views(App, overrides=...)` with an in-process devserver `Transport` (D-75), `FakeClock` and `InMemorySecureStore` (`flet_secure_storage` on Linux needs a Secret Service that CI lacks). pytest runs autouse fixtures before requested ones of the same scope, so the `scenario` fixture is set before `flet_app` starts the app. The plugin puts `tests/harness` on `sys.path` and imports the module under the bare name `host_main`, while tests import the harness as the `tests.harness.*` package, so the two would hold separate module copies. Rule: `host_main` imports its scenario, fakes and transport from the `tests.harness.*` package (for example `from tests.harness.scenario import current_scenario`) and keeps no module-level state of its own; the `scenario` fixture writes only to `tests.harness.scenario`.

### 2.3 Helpers and identifiers (`tests/harness/nav.py`)

- `until(t, find, timeout=10)` pumps `t.pump(duration=100 ms)` until `(await find()).count > 0`, with its own deadline around `pump`; it is the mode-agnostic wait. Use it while a spinner is visible. Shared helpers call `pump_and_settle()` **without** `timeout=`: only the host `Tester` accepts it (default 10 s); `RemoteTester.pump_and_settle` takes only `duration` and raises `TimeoutError` after its fixed 60 s RPC timeout. Both fail on endless animations.
- `goto(t, screen)` navigates by tapping only, so it works in both modes. Host-only deep-link tests use `await flet_app.page.push_route(route)` followed by `await t.pump_and_settle()` (or `until`); `page.navigate` is fire-and-forget and would race the assertion.
- `back(t)`: host mode taps `find_by_tooltip("Back")`; device mode on Android runs `adb shell input keyevent KEYCODE_BACK`.

**Identifiers.** `Semantics(identifier=...)` is the test key (D-70) and is found with `Tester.find_by_semantics_identifier`, which shipped in Flet 1.0.2.
- The constants live in one module imported by both the app and the tests (`pycon_us/ui/ids.py`, §17).
- Scheme: `<area>.<element>[.<index>]`, for example `nav.tab.schedule`, `sched.row.3`, `sched.jump_now`, `staff.manual.input`, `lead.row.0`, `door.headcount`.
- Identifiers become Android `resource-id` and iOS `accessibilityIdentifier`, so they **never** contain codes, emails or names.

---

## 3. L1 Unit tests

**Run:** `uv run pytest tests/unit` (about 30 s).

**Hypothesis profiles:**
- `ci`: 200 examples, `derandomize=True`, `deadline=None`;
- `nightly`: 2000 examples (`--hypothesis-profile=nightly`).

**Time zones.** `ci.yml` (`test` job) runs the unit suite under `TZ=America/Los_Angeles` and again under `TZ=Pacific/Kiritimati`; labels and day buckets must not change (D-52). Ruff `DTZ` rules reject naive `datetime.now()` in `core/`.

| Module | What is tested | Technique | Ids |
|---|---|---|---|
| `core/signing.py` | 2019 `docs/api.rst` vector + staging captures (P3); body bytes serialised once; `fetch_products` query unencoded, `capture` encoded | vectors + hypothesis | API-01, AUTH-03 |
| `api/client.py` | timeouts (§3.1); the seven typed errors (D-56); skew from `Date`, one retry on a skew 403 | devserver transport | API-12 |
| `core/badges.py` | code = `seg[0]`; validator = `seg[1]` for door/swag, the **last** segment for lead; CoC uses the code only | `badges.csv` + hypothesis | LEAD-03 |
| `core/admission.py` | `decide()` decision table: inventory first, then `fetch_products`, optimistic admit; "Already" on product overlap; unknown offline → "Entry not permitted" | table-driven | DOOR-03, DOOR-04 |
| `core/outbox.py` | transitions, caps 10/20/30, note-after-capture, door idem key, favourites coalesce, synced rows kept, purge (D-59, D-61) | hypothesis `RuleBasedStateMachine` (enqueue, sync ok/fail, clock, sponsor switch, logout, purge); invariants: no pending row lost, attribution fixed, tries ≤ cap | API-10, API-11, LEAD-07, LEAD-11, DOOR-07, STORE-12 |
| `core/process.py` | every D-50 named rule (placeholder filter, Break location, Lunch span, Job Fair 10:00/9:30, speakers by name, 16 sprint rooms, `start_time` set, bad slot skipped and reported) | fixtures + mutated feeds | DATA-04..16, DATA-26, SCHED-19 |
| `core/queries.py` | ANY word over name + description **text** + speakers; speakers ANY word in the name; sprints/jobs ALL words; the favourites view ignores the track filter; Now/Next uses end times and no track filter | truth tables | SCHED-05, SCHED-07, SCHED-17, SCHED-25, DATA-18, EVT-06, SPON-07 |
| `core/timefmt.py` | `9:25 am`, `Wed`, local day bucket, DST edges, `PYCON_FAKE_NOW` | fixed instants + TZ matrix | DATA-12, SCHED-18, DATA-31 |
| `core/slugs.py` | room, track and sponsor slugs, e.g. `qube-research--technologies` | room slugs: vectors exported by L2; track and sponsor slugs (page-level code, not bundled): L1 vectors citing `schedule-list.page.ts:208` and `sponsors.page.ts:55` | DATA-29, SPON-02, ROOM-06 |
| `core/ics.py` | RFC 5545 escaping, 75-octet folding, `VALARM`, TZID | vectors + hypothesis | SESS-05, NOTIF-05 |
| `core/html_md.py` | tag coverage, absolute links, plain text unchanged | feed snippets | DATA-23, DATA-25, INFO-05 |
| `core/changelog.py` | diff by id over start, end, room, title, cancelled, added, removed | feed pairs | `test_gh312_*` |
| `stores/` | `Prefs` keeps `None` and `[]` apart; `Favorites.ids` is a `list[str]`; ints coerced to `str`; union merge on first sync (OD-5) | `Observable` subscribe, no Flet runtime | SCHED-10, STORE-02, STORE-09, AUTH-12 |
| staff gating | the D-41 truth table over all role flags × logged in/out (`test_AUTH_05_gating_truth_table`) | exhaustive | AUTH-05, SHELL-06, SHELL-11 |
| `platform/caps.py` | on iff manifest ∧ probe; remote features only veto; empty manifest under `flet run` | parametrised | §7 |
| `ui/theme/tokens.py` | contrast of every declared pair (§12.1) | WCAG formula | THEME-02..06, THEME-08 |
| `config/` | the bundled app-content and sample app-config validate; a bad bundled file fails CI (D-88) | jsonschema | DATA-32, NOTIF-12 |
| `services/crash.py` | Sentry scrubbers (§14.2) | hypothesis-injected PII | `test_obs_*`, INFO-04 |
| `tools/check_release.py` | build number `YY*1000+MINOR*100+PATCH*10+RESPIN`; ledger; tag = version | vectors | DEV-08 |

### 3.1 Timeout vectors (API-12)

These are Ionic's values from `providers/pycon-api.ts` and `pages/login/login.ts`; each case cites its Ionic line.

| Endpoint | s | Endpoint | s |
|---|---|---|---|
| `authenticate/` | 3 | `check_in/fetch_products/`, `check_in/redeem_products/` | 10 |
| `user/check_features/`, `user/mobile_state/` (GET, PATCH) | 2 | `mask_violations/attendees/` | 15 |
| `check_in/redeemable/`, `check_in/attendees_by_product/` | 2 | `mask_violations/capture/` (GET, POST) | 5 |
| `lead_retrieval/capture/`, `lead_retrieval/<code>/note/` | **2** | `lead_retrieval/sponsors/` | 5 |
| `check_in/attendees_by_product_with_quantity/` (inventory) | 20 | | |

The table follows Ionic where D-56's wording differs (§17.1).

---

## 4. L2 Differential harness

**Goal:** criterion S2 by 2027-01-31. Spike S4 (M0) produces the first reference JSON.

### 4.1 What is bundled

The Ionic sources are copied verbatim into `tools/ionic_reference/vendor/` from tag `v26.2.1` on `ionic-2026` (D-101); the commit today is `2aa6df8`.
- The SHA is recorded in `vendor/REF`.
- `tools/ionic_reference/sync.sh` refreshes the copy. Nobody edits it.

| Ionic file | Used for |
|---|---|
| `src/app/providers/conference-data.ts` | `processData`, `isPlaceholderSlot`, `slugifyRoom`, `parseTime`, `getDays`, `getTimeline`, `getAllDaysTimeline`, `getSessions`, `filterSession`, `getRooms`, `getRoom`, `getSpeakers`, `querySponsors`, `getTracks`, `getSprints`, `getPosters`, `getJobListings`; the `DISPLAY_TIME_OVERRIDES` table is a `const` local to `processData` (`match: RegExp`), so it is not exported (see `sync.sh` below) |
| `src/app/pipes/{track-name,session-order,date-ago}.pipe.ts` | `trackName` (short/long/plural), `sessionOrder`, `dateAgo` |
| `src/app/location-map/{room-locations,venue-locations}.ts` | `ROOM_LOCATIONS` (DATA-32, MAP-07) |
| `src/environments/environment.ts` (what `conference-data.ts` imports and the bundle resolves; no alias to `environment.prod.ts`, whose values are the same today) | `timezone: 'America/Los_Angeles'`, `utcOffset: -7` |

**Real npm packages**, pinned exactly in `tools/ionic_reference/package.json` from Ionic's lockfile:
- `rxjs@7.8.2`: `load()` returns Observables.
- `markdown-to-txt@2.0.1`: used on slot names (DATA-08); the Python port must match its output on every feed name.

**Shims** (`tools/ionic_reference/shims/`, one directory each so subpaths resolve): `angular-core` (no-op `Injectable`/`Pipe`), `angular-common/http.ts` (unused `HttpClient`), `ionic-angular` (`ToastController`), `ionic-storage-angular` (in-memory `Storage`). `UserData` is `{hasFavorite(id)}` over the scenario's favourites.

**Not bundled.** Page-level logic (the `now` page filter, sprints and jobs search, `parseRoles`/`shortenUrl`) pulls in Angular and Ionic UI. It is covered by L1 vectors that cite the Ionic file and line.

### 4.2 Build and run

```bash
npm ci --prefix tools/ionic_reference                       # Node 22 LTS; esbuild pinned exactly
npx --prefix tools/ionic_reference esbuild tools/ionic_reference/entry.ts \
  --bundle --platform=node --format=cjs --target=node22 \
  --tsconfig=tools/ionic_reference/tsconfig.json \
  --alias:@angular/core=./tools/ionic_reference/shims/angular-core \
  --alias:@angular/common=./tools/ionic_reference/shims/angular-common \
  --alias:@ionic/angular=./tools/ionic_reference/shims/ionic-angular \
  --alias:@ionic/storage-angular=./tools/ionic_reference/shims/ionic-storage-angular \
  --outfile=tools/ionic_reference/dist/ionic_reference.cjs
TZ=UTC LC_ALL=en_US.UTF-8 node tools/ionic_reference/dist/ionic_reference.cjs \
  --feed tests/fixtures/feeds/conference-2026.json --matrix tools/ionic_reference/matrix.json \
  --now 2026-05-16T17:05:00Z --out build/ionic_ref/2026.json
uv run pytest tests/differential        # rebuilds build/ionic_ref/ when vendor/REF or a feed changed
```

`tsconfig.json` sets `experimentalDecorators: true`. esbuild resolves alias targets from the working directory, so run from the repo root.

**`entry.ts`**
- Builds `new ConferenceData(http, user, storage, toast)` from the shims.
- Calls `processData(structuredClone(feed))`, because Ionic mutates its input.
- Runs the matrix through `load()`, which returns `of(this.data)` once data is set.
- Exports `ROOM_LOCATIONS` and `VENUE_LOCATIONS` (module exports) and the instance fields `trackIcons` and `slotColors`, read from the constructed `ConferenceData`, to `build/ionic_ref/tables.json`. The track colour palette is not in TypeScript: it lives in the `src/global.scss` `[data-track=…]` rules (lines 142-153), which an esbuild node bundle cannot reach. `sync.sh` extracts it into `tables.json` and fails if the extraction fails; otherwise THEME-08 is covered by L1 vectors citing `global.scss:142-153`.
- `DISPLAY_TIME_OVERRIDES` is local to `processData`, so `entry.ts` cannot reach it. `sync.sh` extracts it from the vendored source into `tables.json` as `{source, flags, startOffsetMinutes}` (regex source and flags) and fails if the extraction fails; the vendored file stays unpatched. As a second proof, the differential suite compares Python's app-content-driven `timeStart` with Ionic's `processData` output on the Job Fair row.
- Python loads `tables.json` as its app-content fixture, so both sides run on **identical yearly tables**. This is how DATA-11 and DATA-32 (tables moved to app-content) are proven.

### 4.3 Query matrix (per feed)

| Function | Inputs |
|---|---|
| `processData` | the whole model: days, groups, sessions, speakers, rooms, tracks |
| `getDays` | - |
| `getTimeline(day, q, excl, seg)`, `getAllDaysTimeline`, `getSessions` | every day × q ∈ {`""`, `python`, `data science`, `keynote`, `rust, web`} × excl ∈ {`[]`, `["Open Space"]`, all tracks except `Talk`} × seg ∈ {`all`, `favorites`} (5 fixed favourites) |
| `getRooms`, `getRoom(slug)` | every slug, plus one unknown slug |
| `getSpeakers` | `""`, `an`, `van rossum` |
| `querySponsors` | `""` and one word |
| `getTracks`, `getSprints`, `getPosters`, `getJobListings` | no arguments (full output); sprint and job search is page-level (§4.1) |
| `trackName` | every track × `short`/`long`/`plural` |
| `sessionOrder` | every group |
| `dateAgo` | 0, 5, 30, 59, 60, 3599, 3600, 86 400, 2 592 000 and 31 536 000 s, and `null`, with `Date.now` fixed |

### 4.4 Normalisation (`tests/differential/normalise.py`)

1. **Ids** are compared as `str` (D-50).
2. **Field names**: Python uses `dataclasses.asdict`, renamed through `fieldmap.json` (snake_case → camelCase).
3. **View flags**: Ionic's `hide`, `shownSessions` and `favorite` (written into shared objects) are dropped. Each query is compared on its **visible id lists** instead (D-47).
4. **Spaces**: U+202F and U+00A0 become a normal space. Recent ICU puts a narrow no-break space before am/pm in `toLocaleTimeString`; Python emits `9:25 am`.
5. **Instants**: UTC ISO-8601 with ms and `Z` (as `JSON.stringify(Date)`).
6. **Missing**: `undefined`, absent and `None` are equal.
7. **Order**: arrays keep their order (days, groups, sessions, speakers within a session). Registries and sets are sorted by key. Both sorts are stable.
8. **Description HTML** is compared raw. `html_md` is tested in L1.
9. **Deliberate divergences** live in `tests/differential/divergences.yaml`, one per adapt id. Each needs a named test, which `feature_trace` enforces.

   | Id | Divergence | Comparison rule |
   |---|---|---|
   | SCHED-05, SCHED-17, DATA-18 | search over description **text** | Drop from Ionic's visible set any session matched only inside a tag or attribute (word absent after `re.sub(r"<[^>]+>", " ", d)`) |
   | SCHED-07 | the favourites view ignores the track filter | For `seg=favorites`, re-run Ionic with `excl=[]` |
   | SCHED-25 | Now/Next respects end times | Not in the matrix (page logic); L1 truth table |

Any uncovered difference fails the run with a JSON-pointer diff of at most 50 entries, naming the feed and the session id.

**Refresh.**
- Add the P8 sample feed (2027-02-15) and the live `/2027/` feed (~03-13, UNCONFIRMED) to the matrix.
- Ionic is never patched to agree.

---

## 5. L3 Contract tests

| Schema (`tests/contract/schemas/`, Draft 2020-12) | Samples | Notes |
|---|---|---|
| `feed.schema.json` | the 2025/2026 feeds, the P8 sample, the live feed | Required keys are typed; `additionalProperties: true`, plus an "unknown keys" report. `slot` has `"not": {"required": ["sessions"]}` (`test_DATA_27_slot_sessions_absent`, D-08) |
| `api/*.schema.json` for `authenticate`, `user/check_features`, `user/mobile_state` (GET, PATCH), `check_in/{redeemable, attendees_by_product, attendees_by_product_with_quantity, fetch_products, redeem_products}`, `lead_retrieval/{sponsors, capture, <code>/note}`, `mask_violations/{attendees, capture}` | `tools/record_fixtures.py` against staging, per role (P3), scrubbed | `{code, data}` / `{code, error}` envelopes (D-56); 403, 404 and validation errors recorded too |
| `config/app-config.schema.json`, `config/app-content.schema.json` | `config/<year>/<env>/`, the bundled fallback | PSF-I co-owns them in CODEOWNERS; reminder ids ≥ 8000; booth ratios in [0, 1] |

The schemas are offered to `pycon-site` as plain JSON (PLAN §8.1), as are the signing vectors (D-48).

**PR mode.** `uv run pytest tests/contract` validates every fixture and config file, **and** every devserver response. The fakes therefore cannot drift from staging.

**Nightly** (`contract-live` job, environment `staging` with PSF-held keys): `uv run pytest tests/contract -m live` checks:
1. the live `https://us.pycon.org/{YEAR}/schedule/conference.json` for 2026, and for 2027 once it returns 200;
2. every staging endpoint per role, writing only test badges and the test sponsor;
3. the hosted staging and prod app-config and app-content.

**On failure**, the job writes `build/contract-report.md` (schema, JSON pointer, expected type, example). It then runs `gh issue create`, or `gh issue comment` on the open issue with the same title, with the label `contract-drift`. Unknown keys produce a comment, never a failure.

G4.3 needs 7 consecutive green runs ending 2027-03-31.

---

## 6. L4 UI flows

### 6.1 The real Flet testing API

| Piece | Name in local 1.1.0 | Notes |
|---|---|---|
| Fixtures | `flet_app` (function scope, fresh app per test), `flet_app_function` (host mode only; binds `ft.context.page`; errors in device mode because `FletTestApp.page` is unset) | plugin `flet.pytest_plugin`; needs `asyncio_mode = "auto"`. Tests that can run in device mode use only `flet_app` |
| Controller | `flet.testing.FletTestApp`: `.tester`, `.page`, `.assert_screenshot(name, png, similarity_threshold=0)`, `.assert_control_screenshot(...)`, `.take_page_controls_screenshot()`, `.resize_page(w, h)`, `.create_gif`/`.assert_gif` | `.page` is the app page only in host mode |
| Finders | `find_by_key`, `find_by_text`, `find_by_text_containing` (regex), `find_by_tooltip`, `find_by_icon`, `find_by_semantics_identifier` → `Finder(.count, .first, .last, .at(i))` | on both `Tester` and `RemoteTester` |
| Actions (both) | `tap`, `long_press` (600 ms), `enter_text`, `mouse_hover`, `pump(duration)`, `take_screenshot(name)` | `take_screenshot`: iOS and Android only |
| `pump_and_settle` (host) | `Tester.pump_and_settle(duration=None, timeout=10)` | |
| `pump_and_settle` (device) | `RemoteTester.pump_and_settle(duration=None)` | no `timeout` argument (`TypeError` if passed); raises `TimeoutError` after the fixed 60 s RPC timeout (§17.3) |
| Host-only actions | `drag`, `drag_from`, `tap_at`, `mouse_click(_at)`, `right_mouse_click(_at)`, `mouse_double_click(_at)` | not in `RemoteTester` (§17.3); `RemoteTester` is imported from `flet.testing.remote_tester` (not in `flet.testing.__all__`) |
| CLI | `flet test [platform] [-d ID] [--tests-dir DIR] [-u] [--update-failed-goldens] [--flutter-test-host DIR] [-k EXPR] [--yes] [-v] [-- pytest args]` | provisions a cached test host through the `flet build` pipeline and runs pytest with `FLET_TEST_DEVICE_MODE=1`. CI always passes `--yes` (answers the Flutter SDK / JDK / Android SDK install prompts), as Flet's own CI does, and may pin `--python-version` |

**Environment variables:** `FLET_TEST_PLATFORM`, `FLET_TEST_DEVICE`; `FLET_TEST_GOLDEN` (`1` records, `failed` rewrites only missing or mismatched images, new in 1.1.0); `FLET_TEST_SCREENSHOTS_PIXEL_RATIO` (2.0); `FLET_TEST_SCREENSHOTS_SIMILARITY_THRESHOLD` (99.0); `FLET_TEST_USE_HTTP`; `FLET_TEST_DISABLE_FVM` (`flet test` sets it to `1`; plain `uv run pytest` host mode does not, so it runs `fvm flutter test` unless it is set: `1` in CI, with `flutter` on `PATH` or `FLET_TEST_FLUTTER_EXE` set); `FLET_TEST_VERBOSE`; and for host mode `FLET_TEST_DEVICE_MODE` (plugin default `1`), `FLET_TEST_FLUTTER_APP_DIR`, `FLET_TEST_APP_PATH`, `FLET_TEST_APP_MODULE`, `FLET_TEST_ASSETS_DIR`.

**Flutter-side failures** (including "RenderFlex overflowed") fail the test even when every Python assertion passed: `FletTestApp.teardown()` raises `RuntimeError` on a non-zero `flutter test` exit. This is how text-scale goldens catch clipping (§12).

### 6.2 Two modes

| | Host mode ("fast lane") | Device mode ("real lane") |
|---|---|---|
| What runs where | app in the pytest process, rendered by a Flutter host client | `flet build` app with embedded Python on the device, driven via `RemoteTester` |
| How | `FLET_TEST_DEVICE_MODE=0`; a shallow checkout of flet-dev/flet at tag `v<pinned flet>` into `.flet/` (sparse: `client/`, `packages/`, `sdk/python/packages/*/src/flutter`, `.fvmrc`; `client/pubspec.yaml` reaches the Flet Dart package, `flet_integration_test` and every extension through `../` path dependencies, so `client/` alone fails at `pub get`), with `FLET_TEST_FLUTTER_APP_DIR=.flet/client` (its `integration_test/app_test.dart` calls `runFletHostTest`); `FLET_TEST_APP_PATH`/`FLET_TEST_APP_MODULE` as in §2.2; `FLET_TEST_DISABLE_FVM=1` with `flutter` on `PATH` or `FLET_TEST_FLUTTER_EXE` set (otherwise fvm is a local prerequisite). Run: `FLET_TEST_DEVICE_MODE=0 FLET_TEST_DISABLE_FVM=1 FLET_TEST_FLUTTER_APP_DIR=.flet/client FLET_TEST_APP_PATH=tests/harness FLET_TEST_APP_MODULE=host_main xvfb-run -a uv run pytest tests/ui -m smoke` (drop `-m smoke` for all host flows; `xvfb-run -a` only on Linux). Paths must be explicit: `testpaths` excludes `tests/ui` and `tests/fallback`, and without `FLET_TEST_DEVICE_MODE=0` the plugin defaults to device mode and tries to provision a device test host | `uv run flet test android -d emulator-5554 --tests-dir tests/ui --yes` (or `ios -d <sim-udid>`) |
| State | fakes injected directly | devserver scenario |
| Extensions | never rendered: fakes at the protocol seam (the monorepo client lacks E1-E4) | the real manifest; E1 renders but cannot decode on an emulator or simulator |
| Extra powers | `drag`, `await page.push_route(...)`, `resize_page` (followed by `page.update()` and a pump), advancing `FakeClock` | real packaging and permissions; `adb` (back key, `font_scale`, `wm size`); `take_screenshot` |
| Used for | PR smoke, L5, host-only flows | nightly flows, L7, RC smoke |
| CI | `ubuntu-latest` + `xvfb-run -a` with `LIBGL_ALWAYS_SOFTWARE=true` and `GALLIUM_DRIVER=llvmpipe` (adapted from Flet's `flet test linux` job; Flet runs its own host-mode suite on `macos-26`, so Linux host mode is an M0 spike item); fall back to `macos-26` if flaky | `reactivecircus/android-emulator-runner@v2` (API 35, x86_64, `google_apis`) on ubuntu + KVM; `macos-26` for iOS |

**Determinism rules**
- No `asyncio.sleep`; use `pump`/`until`. Scenario `animations=False` plus `page.theme_animation_style = ft.AnimationStyle.no_animation()`.
- Pump debounces explicitly: search 250 ms (D-51), door re-arm 250 ms, lead 500 ms (D-82).
- **No real airplane mode in device mode:** `FletTestApp` connects `RemoteTester` through `10.0.2.2` on Android, so it would cut the test channel. Use `PUT /__test__/network {"up": false}`; real airplane mode is covered in §10 and §11.
- Each device-mode test costs one `flutter test` launch (~30-90 s warm), so flows are one per journey and goldens batch screens (§9).

### 6.3 Example

```python
# tests/ui/test_lead.py
import pytest, flet.testing as ftt
from tests.harness.nav import goto, until

@pytest.mark.smoke
@pytest.mark.scenario(role="door", app_config={"features": {"scanner": False}})
async def test_LEAD_07_offline_scan_pending_then_synced(flet_app: ftt.FletTestApp, scenario):
    t = flet_app.tester
    await goto(t, "lead-retrieval")
    await scenario.set_network(up=False)            # host: fake transport; device: PUT /__test__/network
    await t.enter_text(await t.find_by_semantics_identifier("staff.manual.input"), "SIM12345:SIMULATED")
    await t.tap(await t.find_by_semantics_identifier("staff.manual.submit"))
    await until(t, lambda: t.find_by_text("Pending"))
    await scenario.set_network(up=True)
    await t.tap(await t.find_by_text("Sync now"))    # LEAD-13 interim until U1
    await until(t, lambda: t.find_by_text(scenario.badge_first_name))   # Ionic shows the first name once captured
    assert (await t.find_by_text("Pending")).count == 0
    [call] = await scenario.api_log(path_endswith="/api/v1/lead_retrieval/capture/")
    assert call.query["sponsor_id"] == scenario.staff_sponsor_at_scan   # snapshot (D-59)
```

### 6.4 The 29 flows

**Mode:** H = host, D = device (Android nightly; ★ = also on the iOS 26 simulator). **Lane:** PR = host-mode smoke on every PR (15 flows, about 6 min); N = nightly.

| # | Test | Ids | Asserts | Mode | Lane |
|---|---|---|---|---|---|
| F01 | `test_SHELL_02_first_run_welcome_to_schedule` | SHELL-02, SHELL-03, STORE-07 | Empty storage → Welcome → Schedule; the next launch skips Welcome | H, D★ | PR |
| F02 | `test_SCHED_01_today_tab_autoselect` | SCHED-01, DATA-17, SCHED-18 | `fake_now` Sat 10:05 PDT → Sat tab; before the conference → first day | H, D | PR |
| F03 | `test_SCHED_11_swipe_and_longpress_favorite` | SCHED-11, SESS-03, STORE-02 | H: `drag(row, ft.Offset(-400, 0))` snaps back, star on, Ionic SnackBar copy. D: `long_press` → menu. Info rows not swipeable | H, D | PR |
| F04 | `test_SCHED_07_favorites_only_and_empty_state` | SCHED-07, SCHED-08 | "Show favorites" ⇄ "Show all sessions"; empty state; other days; favourited Open Space shown despite the filter (OD-13) | H, D | N |
| F05 | `test_SCHED_05_live_search_all_days` | SCHED-05, SCHED-06, DATA-19 | Filters 250 ms after typing; "Search all days"; `nofollow` matches nothing | H, D★ | PR |
| F06 | `test_SCHED_09_filter_modal_persists` | SCHED-09, SCHED-10, STORE-09 | Local modal; the default (Open Space hidden) reads "Filter sessions (some tracks hidden)"; untick another track → "Filter sessions (custom filters active)"; Reset → back to "Filter sessions (some tracks hidden)"; survives a relaunch (D) | H, D | N |
| F07 | `test_SCHED_16_jump_to_now_and_back_no_rescroll` | SCHED-15, SCHED-16 (#313) | Jump to Now shows the slot; session → Back keeps the same header; refresh does not jump | H, D★ | PR |
| F08 | `test_SESS_12_drill_back_one_hop` | SESS-12, SESS-07, SESS-02, SHELL-04 (#279) | Session → speaker → session → room; each Back returns one hop (title check) | H, D | PR |
| F09 | `test_SHELL_16_android_back_root_exits` | SHELL-16, SHELL-09 (#311) | A drawer destination replaces the stack; `KEYCODE_BACK` on a root backgrounds the app (`dumpsys activity activities`) | D (Android) | N |
| F10 | `test_SCHED_25_now_next_respects_end_times` | SCHED-25, SCHED-26 | During a 3 h tutorial it is under "Happening Now"; "Up Next" is the next group; the track filter is ignored (OD-12) | H, D | PR |
| F11 | `test_SCHED_24_favorite_all_track_with_undo` | SCHED-21, SCHED-24 | Favourite the whole filtered track; Undo restores (OD-11) | H, D | N |
| F12 | `test_THEME_01_theme_picker_modes` | THEME-01, STORE-08 | Five values; each persists; "Match system" is the default (OD-6) | H, D | N |
| F13 | `test_DATA_02_offline_cold_start_from_cache` | DATA-02, SCHED-14 | Cache + offline → schedule + "Updated N h ago" chip; no cache → Ionic error copy; cache never deleted | H, D★ | PR |
| F14 | `test_ROOM_05_floor_plan_global_modal_over_drill` | ROOM-04, ROOM-05, INFO-13, MAP-05 | Drilled room → map card → `/floor-plan/:plan?pin=` → "Close floor plan" → same stack | H, D | N |
| F15 | `test_SHELL_04_short_link_redirects` | SHELL-04, DATA-26 | `await flet_app.page.push_route("/s/<id>")` + `await t.pump_and_settle()` → canonical route; Back → Schedule root | H | N |
| F16 | `test_AUTH_08_login_lands_on_lead_scanner` | AUTH-01, AUTH-04, AUTH-08, SHELL-03 (#310) | `lead` → Lead Scanner after login and at cold start; door-only → Schedule (D-42) | H, D★ | PR |
| F17 | `test_AUTH_12_login_merges_favorites` | AUTH-12, API-04, SCHED-12 | {a,b} local + {b,c} server = {a,b,c}; one GET, then a debounced full-list PATCH | H, D | N |
| F18 | `test_AUTH_11_logout_guard_pending_rows` | AUTH-11, SHELL-13, STORE-04 | "Sync now / Log out anyway (1 unsynced)"; cleared vs kept data exactly as D-62 | H, D | PR |
| F19 | `test_AUTH_05_staff_entry_points_per_role` | AUTH-05, AUTH-06, SHELL-06, SHELL-07, SHELL-11 | 4 staff roles (`lead`, `door`, `door_lead`, `mask`) + `attendee`: Scanner tab, sheet items, drawer Apps; typed staff URL → "Not available for this account" | H | PR |
| F20 | `test_LEAD_07_offline_scan_pending_then_synced` | LEAD-01, LEAD-05, LEAD-07, LEAD-08, LEAD-09, API-10 | §6.3; a sponsor switch while pending keeps the original `sponsor_id` | H, D | PR |
| F21 | `test_LEAD_10_note_waits_for_capture` | LEAD-04, LEAD-10, LEAD-11 | Consent gate; modal `lead-retrieval/note/:code`; an offline note syncs after its capture | H, D | N |
| F22 | `test_DOOR_04_admission_outcomes` | DOOR-01..DOOR-07 | "Checked in" (+1); "Already checked in"; offline unknown → "Entry not permitted"; garbage → "Entry not permitted" (parity: Door Check has no "Invalid QR code" state); offline admits queued | H, D★ | PR |
| F23 | `test_SHIRT_04_redeem_online_only` | SHIRT-01..SHIRT-04 | Non-badge QR → "Invalid QR code" card for ≥ 2 s (SHIRT-02); online redeem shows the toast; offline shows the explicit message and queues nothing (D-83) | H, D | N |
| F24 | `test_MASK_04_capture_cooldown` | MASK-02..MASK-05 | Name search + notes (POST); the same code twice within 3 s → 1 capture; `FakeClock.advance(3.1)` → a 2nd (OD-10) | H | PR |
| F25 | `test_AUTH_05_kill_switch_hides_tool` | AUTH-05 | `features.door_check=false` hides Door Check and guards its URL; `features.swag=false` hides Swag; each is re-derived without a restart (D-74, D-83) | H | N |
| F26 | `test_NOTIF_12_update_gates` | NOTIF-12, LIVE-02..LIVE-04 | `latest` above the build → banner, drawer card, dot; `min_supported` above → blocking dialog | H, D | PR |
| F27 | `test_NOTIF_02_master_toggle_mixed_state` | NOTIF-01..NOTIF-03 | Six toggles; the master shows a mixed state; persisted; emergency banners still show in-app (OD-18) | H | N |
| F28 | `test_gh312_change_log_banner` | (#312) | Feed v1 → v2 with a moved session: banner, "Changed" chip, `schedule/changes` | H, D | N |
| F29 | `test_SHELL_14_wide_layout_permanent_drawer` | SHELL-14 (T2) | `flet_app.resize_page(1024, 768); flet_app.page.update(); await t.pump_and_settle()`, then assert `flet_app.page.width` changed (`resize_page` silently does nothing when the window size is unknown) and the permanent 304 px drawer column | H | N |

Nightly runs every H flow in `ui-host` and every D flow on Android (about 45 min), plus the 6 ★ flows on iOS.

---

## 7. L5 Fallback parity

**Principle (PLAN [§5.7](../PLAN.md#57-platform-and-capability-abstraction), D-74, D-75).** Screens never import an extension, and providers are chosen in one place. Host mode therefore swaps in **fakes at the protocol seam**: "on" uses a fake, "off" uses the interim, and "veto" means the manifest says on but app-config says off. Real extension controls are covered only by device mode and physical devices.

**Selecting the state.** Scenario `caps` is `"manifest"` (real derivation), `"all_off"` (empty manifest), `"all_on"` (every key, probes patched, fakes from `tests/harness/fakes.py`) or `{key: "on"|"off"|"veto"}`.

`tests/fallback/test_matrix.py` re-runs the listed flows under `all_off`, `all_on` and each single-key veto.

**Run** (host mode, nightly `fallback-parity` job, and on PRs that touch `platform/`): `FLET_TEST_DEVICE_MODE=0 FLET_TEST_DISABLE_FVM=1 FLET_TEST_FLUTTER_APP_DIR=.flet/client FLET_TEST_APP_PATH=tests/harness FLET_TEST_APP_MODULE=host_main xvfb-run -a uv run pytest tests/fallback`. The `flet-main` job (below) runs `uv run flet test android -d emulator-5554 --tests-dir tests/ui --yes -- -m smoke` against the `main` override (pytest arguments go after `--`; `flet test` rejects unrecognised options).

| Cap | Interim asserted (off or veto) | Upgrade asserted (on, fake) | Ids | Flows / tests |
|---|---|---|---|---|
| `scanner` | `ManualEntryScanner`: input, submit, HID wedge (Enter-terminated) | `FakeScanner.emit("CODE:VAL")` takes the same `parse_badge` path; paused while the swag modal is open; torch button | LEAD-01, LEAD-02, DOOR-04, SHIRT-02, MASK-04 | F20, F22, F23, F24 |
| `push` | `BannerPoller` banners filtered by the toggles | `FakePush.deliver(topic, msg)` shows the top banner; subscriptions follow the toggles | NOTIF-04, 06, 08, 11, NATIVE-04 | F27, `test_NOTIF_04_*` |
| `local_notifications` | In-app reminder banners + `.ics` with `VALARM` | Cancel 8000-80xx, then reschedule the enabled future reminders; inexact fallback | NOTIF-05, NOTIF-07, DEV-06 | `test_NOTIF_05_*` |
| `calendar` | `IcsShare` | `FakeCalendar.add_event(title, start, end, location, description, url)` | SESS-04, SESS-05 | `test_SESS_04_*` |
| `analytics` | `NullAnalytics` makes no calls | Off in 27.0 (OD-3) | NOTIF-09 | unit |
| `refresh_indicator` | Refresh `IconButton` + `ProgressBar` (D-67) for SCHED-13, SCHED-26, EVT-07, SPON-08; for LEAD-13 the 'Sync now' button (+ 'Retry failed') | The `Refreshable` fake wrapper awaits the store | SCHED-13, SCHED-26, EVT-07, SPON-08, LEAD-13 | F07, F20 |
| `app_info` | `BuildInfoAppInfo` | Fake `PageAppInfo` (U4) | INFO-03 | `test_INFO_03_*` |
| `iv_set_transform` | Highlight + `InteractiveViewer.reset/zoom/pan` | Fake `zoom_to_rect` (U3) with the booth rect | EXPO-05 | `test_EXPO_05_*` |
| `html` | `html_md` Markdown | The fake HTML control (E5) gets the raw HTML | INFO-05, SESS-06, DATA-23, DATA-25, MAP-09 | unit, F14 |
| `slidable` | `Dismissible` + long press (D-72) | Fake revealed buttons (E6) | SCHED-11 | F03 |
| `sticky_headers` | Dividers such as "Sat - 9:25 am" (D-71) | Fake sliver header (U2) | SCHED-02 | `test_SCHED_02_*` |

**Invariants checked in every cell**
1. No `screens/` or `ui/` module imports an extension (an AST lint).
2. A veto takes effect within one app-config refresh, with no restart.
3. Remote features can never turn a cap on.
4. The interim UI and its copy are identical under `all_off` and under veto.
5. `python -m pycon_us.platform.caps` prints the same matrix.

**Nightly `flet-main` job.** It builds the device test host with `flet`, `flet-cli` and the extensions taken from flet-dev/flet `main`, through a nightly-only `[tool.uv.sources]` override that never appears in a release (D-89). It runs the smoke flows on Android. A red run opens a `flet-main-drift` issue and never blocks the app. A sources override alone is not enough: a git-installed `flet` has no CI-patched version (metadata `0.1.0`; `flet.version` falls back to the nearest git tag and `.fvmrc` above the installed package, so it finds the pycon repo or nothing), and `flet test` then exits with "Unable to determine the required Flutter SDK version". The job therefore also:
1. checks out flet-dev/flet `main` and installs `flet`, `flet-cli` and the extensions editable from inside that checkout, so the git-tag and `.fvmrc` lookups resolve against the Flet repo (or patches `flet/version.py` as Flet's CI does; `docs/build-and-release.md` stamps the checkout as 1.99.0);
2. uses the `main` build template: an editable `flet-cli` from the checkout picks up its local `templates/build` and in-repo `flet_integration_test` automatically; any other install passes `--template-ref main` (or sets `[tool.flet.template].ref = "main"` only in the nightly override), because the template ref and the `flet_integration_test` git ref otherwise come from `flet_version` (`v<flet_version>`);
3. relaxes or drops the `==1.1.*` dev pins in the override (or uses a uv `override-dependencies` entry), since they do not match the source version.

The job is an M0 spike item until a run has been seen to pass.

---

## 8. L6 `feature_trace` (D-98)

**Command:** `uv run python tools/feature_trace.py [--check] [--junit build/junit/*.xml] [--today YYYY-MM-DD] [--burndown] [--json out.json]`.

1. **Ids.** Parsed from the rows of `docs/feature-matrix.md` whose first cell matches `^[A-Z]+-\d{2}$` (columns: id, area, feature, roles, disposition, milestone). Anything other than exactly 263 ids → exit 2.
2. **Tests.** Discovered statically with `ast`: every `def`/`async def test_*` in `tests/**/test_*.py`, class methods included. The id comes from `re.match(r"test_([A-Z]+)_(\d{2})_", name)`. An id that is not in the matrix is an error (typo guard).
3. **Status** from optional junit XML (merged on `classname` + `name`): **green** = ≥ 1 traced test passed and none failed; **yellow** = all skipped; **red** = no test or any failure.
4. **Dropped ids** (LIVE-01, DATA-27) are never required. DATA-27 keeps its contract test anyway.
5. **Gate (`--check`)**, exit 1 when a required id has no test:
   - Until 2026-12-06 it only reports.
   - From M2 (2026-12-07), "required" means the non-dropped ids whose milestone **exit date** has passed: M0 11-13, M1 12-06, M2 01-31, M3 03-05, M4 03-31, M5 04-30.
   - From G4 (2027-03-31), every non-dropped id is required, NATIVE-10 (M5) included. This is criterion S1.
   - Ids of the current milestone appear as warnings (§17.2).
   - From G4, `--check --junit <PR + nightly junit>` also exits 1 when any required id is red or yellow.
6. **Interim pairs** (warning only): each `interim->upgrade` id should have one test with `_interim_` and one with `_upgrade_` in its slug.
7. **Burn-down** (`--burndown`, Mondays in `nightly.yml`):
   - Per milestone: committed ids, ids with a test, green ids, and plan-expected green (linear within the window, 100 % at exit).
   - Behind % = (expected − green) / expected. Over 15 % at a milestone exit → cut order (D-05, D-19). Over 30 % at G2 → the PSF chooses.
   - The output goes into the weekly Linear PYMOBIL status (D-104).

---

## 9. L7 Golden screenshots

### 9.1 Matrix

**14 screens:** Welcome, Schedule, Session detail, Speakers, Speaker detail, Now, Rooms, Room detail, Conference Map, Sponsors, Sponsor detail, Code of Conduct, Account, Door Check.

**5 modes** (D-64): `light`, `dark`, `high-contrast-light`, `high-contrast-dark`, and `system` under OS dark (`adb shell cmd uimode night yes`), which proves the "Match system" path. OS high-contrast following is checked in the device lab: Flet reports `high_contrast` on iOS and Android API 34+ (`SemanticsService.get_accessibility_features()`); it is not detectable below API 34 (OD-1). It is checked on iOS and on the API 34/35 devices (§10 row 5).

**2 widths** on one AVD, set before launch: **390 dp** (`adb shell wm size 1170x2532`, `wm density 480`) and **1024 dp** (`wm size 2048x1536`, `wm density 320`; ≥ 992 px, so SHELL-14 renders). **Text scale 2.0:** the app-level `Tokens.text_scale` 2.0, set through scenario `prefs` (PLAN §8.1, §8.2). This is an emulation, because Flet cannot set the OS text scaler, so these goldens are not OS text-scale coverage; the OS font size is covered by the manual device passes (§10 row 6). `adb shell settings put system font_scale 2.0` is not used: it scales non-linearly on Android 14+ and is not 200 % for large text.

| Set | Count | Where | Lane |
|---|---|---|---|
| Full matrix | 14 × 5 × 2 = 140 | Android emulator API 35 (reference AVD) | nightly |
| Text scale 2.0 | 14 × `light` × 390 = 14 | same | nightly |
| iOS dark surfaces (`#000`, THEME-03) | 14 × `dark` = 14 | iPhone 16 simulator, iOS 26 | nightly |
| PR subset (`test_THEME_01_golden_pr_subset`, selected with `-k golden_pr_subset`) | Schedule, Session, Now, Door Check × {`light`, `high-contrast-dark`} × 390, plus Schedule and Session at 2.0 = 10 | Android emulator | PR |

If D-17 or D-05 cuts wide goldens or SHELL-14, the 1024 dp column is removed (98 goldens); if devserver semantics are cut, device-mode staff flows fall back to host mode.

### 9.2 Determinism

| Noise | Control |
|---|---|
| Clock | DEMO clock `2026-05-16T10:05:00-07:00` on the 2026 fixture; moves to the 2027 equivalent after P9 (03-20), with a full re-record |
| Data and images | The DEMO feed (D-84) is the 2026 fixture. `tools/record_fixtures.py` rewrites image URLs to devserver `/media/...` |
| Motion | `animations=False`; emulator `disable-animations`; `AnimationStyle.no_animation()` for themes; sponsor rotation frozen at index 0 |
| System bars | Android SystemUI demo mode (`settings put global sysui_demo_allowed 1`; `am broadcast -a com.android.systemui.demo -e command clock -e hhmm 0941`); iOS `xcrun simctl status_bar <udid> override --time 9:41` |
| Toolchain | One AVD image; Flutter fixed by the pinned flet; images stored per `FLET_TEST_PLATFORM` |
| Threshold | Default 99.0. A per-call `similarity_threshold=` needs a comment explaining why |

### 9.3 Layout

One test per (mode, width) launches the app once and walks the 14 screens:

```python
@pytest.mark.device_only
@pytest.mark.parametrize("width", [390, 1024])
@pytest.mark.parametrize("mode", MODES)
async def test_THEME_01_golden_screens(flet_app: ftt.FletTestApp, mode, width, scenario):
    t = flet_app.tester
    for screen in SCREENS:
        await goto(t, screen)
        name = f"{screen}-{mode}-{width}"
        flet_app.assert_screenshot(name, await t.take_screenshot(name))
```

A separate `test_THEME_01_golden_pr_subset` (parametrised over `light` and `high-contrast-dark` at 390, plus one text-scale 2.0 case for Schedule and Session) walks the 4 PR screens; CI selects it with `-k golden_pr_subset`.

**Paths.** `assert_screenshot` writes and reads `<test dir>/golden/<platform>/<module minus "test_">/<name>.png`, for example `tests/golden/golden/android/screens/session-high-contrast-dark-390.png`. On a mismatch it writes `<module>_<name>_actual.png` beside the golden; these are git-ignored and uploaded as CI artifacts.

### 9.4 Update workflow

1. **Local:** `uv run flet test android -d emulator-5554 --tests-dir tests/golden --update-failed-goldens --yes` (= `FLET_TEST_GOLDEN=failed`) rewrites only missing or changed images. Use `-u` (`FLET_TEST_GOLDEN=1`, rewrite all) only after a Flet, Flutter or AVD pin change.
2. **No local emulator:** run `nightly.yml` with `workflow_dispatch` input `update_goldens=failed`. It runs the same command and opens a `goldens/<branch>` PR with only the changed PNGs.
3. **Review:** GitHub's image diff. Merging needs the label `goldens-approved` from U or a co-maintainer, and the PR body lists each changed image with the feature id that changed it.
4. **Pin changes** get their own PR: a full re-record, eyeballed at 100 % on all HC images plus 10 random ones.

---

## 10. L8 Device lab and per-RC checklist

**Devices (D-100):** Pixel 6a (API 34/35); low-RAM Android (API 34); Pixel 9 (API 36, 3-button navigation); an API 26 device only if OD-1 passes; iPhone SE 2 (iOS 15/16); iPhone 12 (iOS 18); iPhone 16 (iOS 26); an iPad. **Extras:** a USB-C and a Bluetooth HID scanner (the G2 fallback), 20 printed sample badges (P3), and a dimmable lamp.

**Which binary.** Each RC uses the **exact** `release.yml` binary from TestFlight or the Play internal track (D-92). Rows marked (S) use the staging-flavour build of the same commit, because the RC reads prod app-config.

| # | Check | Devices | Ids / criterion |
|---|---|---|---|
| 1 | Update over store 26.x: "Welcome back"; favourites return at login | 1 per OS | NATIVE-10, NATIVE-01 |
| 2 | Fresh install: splash `#680579` until first feed; Welcome → Schedule | all | SHELL-01, SHELL-02 |
| 3 | Cold start and first launch (§13) | Pixel 6a, iPhone 12, low-RAM | criterion S6 |
| 4 | Real airplane mode: cache start, stale chip, staff queue, drain on reconnect (`ft.Connectivity.on_change`) | Pixel 6a, iPhone 12 | DATA-02, LEAD-12 |
| 5 | 5 theme modes; iOS Increase Contrast and Android 14+ high-contrast text → HC on resume; iOS Reduce Motion (`reduce_motion`) and Android Remove animations (`disable_animations`) stop the pulsing pins and banner animation | iPhone 12, Pixel 6a | THEME-01, THEME-09 |
| 6 | Max text size (iOS accessibility sizes; Android font + display size): no clipped actions | SE 2, low-RAM | criterion S7 |
| 7 | 3-button navigation bar visible; back gesture; drill Back; deep link `pyconus://app/app/tabs/schedule` | Pixel 9, iPhone 16 | SHELL-16, SESS-12 |
| 8 | Per role key: E1 decode of 20 badges (normal and dim light); manual entry; HID on Android and iPad; camera denied → card → Settings | all phones, iPad | LEAD-01, LEAD-02, DOOR-04 |
| 9 | iPad landscape (≥ 992 px) → permanent drawer; portrait (< 992 px) → modal drawer | iPad | SHELL-14 |
| 10 | Expo map at max zoom: memory (§13) | low-RAM | budget |
| 11 | 3 of the 12 screen-reader flows, rotating (§12.2) | iPhone 12, Pixel 6a | criterion S7 |
| 12 | Developer Info caps equal the release-notes matrix | 1 per OS | INFO-03 |
| 13 | Sentry shows release `27.0.0+<build>` with sessions and no new issues; opt-out stops events | 1 per OS | criterion S5 |
| 14 | (S) Veto `features.lead_retrieval` → hidden within 5 min or on resume; update gates as F26 | 1 per OS | D-83, NOTIF-12 |
| 15 | Store size: Play Console download size (arm64); App Store Connect size | - | criterion S6 |
| 16 | Only if E2/E3 shipped: prompt only at the D-78 moment; topic round-trip; reminder fires | 1 per OS | NOTIF-04..07 |
| 17 | PWA (if T2 survives): first load in Chrome and Safari; browse-only | - | NATIVE-09 |

Results go in the RC issue (check × device); failures in rows 1-8 or 11-13 are P0/P1 candidates.

---

## 11. L9 Badge Day protocol

**Badge Day 1** (2027-02-24, D-14): staging (P3), latest internal build; feeds **G-Staff** (02-26). **Badge Day 2** (2027-04-09): **RC1**; feeds **G5**. BD2 preferably targets production `/2027/api/v1` with PSF test badges and a test sponsor (PSF-I removes the records afterwards); the fallback is the staging-flavour build of the RC1 commit, with the device lab carrying the "exact binary" proof. **People (P10):** U leads, one PSF-E operator per station, PSF-I exports server data.

**Badge deck** (`tests/fixtures/badges.csv`, BD1 / BD2):

| Group | BD1 / BD2 | Purpose |
|---|---|---|
| Valid, products include the session | 80 / 120 | normal path |
| Valid, product not included | 10 / 15 | "Entry not permitted" |
| Unknown or void | 10 / 10 | offline unknown; lead error copy |
| Damaged or low-contrast print | 5 / 10 | E1 under stress (excluded from the first-try rate) |
| Non-badge QR | 5 / 5 | "Invalid QR code" at Swag; "Entry not permitted" at Door (parity) |

### 11.1 Script

| Block | BD1 | BD2 | Actions |
|---|---|---|---|
| Setup (30 min) | ✓ | ✓ | Fresh install; role logins (lead, door, door + "scan on behalf of", mask; Swag uses the door login, D-41); network time; Developer Info screenshot; outbox empty |
| A. Online (45 min) | ≥ 300 | ≥ 350 | Lead ×2 (exhibitor; door staff scanning for sponsor X); Door ×2 sessions; Swag; CoC (scans + name search with notes) |
| B. Airplane | optional 10 min | **30 min, ≥ 150** | Lead/Door queue; Swag/CoC show offline messages (expected refusals); staff device switches X → Y mid-block; **two Door devices scan the same 20 attendees** |
| C. Reconnect (15 min) | ✓ | ✓ | Time to `pending = 0`; "Retry failed"; screenshot counters |
| D. Edge (20 min) | ✓ | ✓ | HID on Android and iPad; typed entry; badge held 10 s at CoC (≤ 4 captures); logout with a pending row; shared-device account switch (D-61) |
| E. Wrap-up | ✓ | ✓ | Device exports (§11.3) |

The block minimums add up to at least the §11.4 volumes: BD1 300 (block A), BD2 350 + 150 = 500 (blocks A and B).

**Tally sheet per station:** badge #, time, outcome shown, presentations until decode, notes. A presentation counts as a retry when nothing decodes within 2 s.

### 11.2 Metrics

| Metric | Definition |
|---|---|
| Lost | The device showed success or queued, but no server record exists after drain |
| Misattributed | Lead: server `sponsor_id` ≠ the row's snapshot. Door: product or session mismatch |
| Duplicates | More than one server record per (code, sponsor) for lead, or per idem key for door. Accepted only if P3 confirms server idempotency, else P1 |
| Orphans | A server record with no device row (an export or clock problem) |
| First-try decode | Presentations decoded on the first try within 2 s ÷ presentations, excluding the damaged group |
| Drain time | Airplane off → `pending = 0` |
| Feedback latency (diagnostic) | Decode → card + announcement + haptic, from a 240 fps video of 10 scans; target < 500 ms |
| Stability | Crashes, `SESSION_CRASHED` screens, ANRs (Sentry, Play vitals, notes) |

### 11.3 Audit (within 24 h)

1. **Device export.** Dev Tools (7-tap) → "Storage stats and dump" (DEV-02) → share the outbox rows: `id, kind, key, sponsor_id, sponsor_name, owner, status, tries, created_at, last_error, idem_key`. This is sample-badge data only. INFO-04 diagnostics deliberately contain no codes, so they cannot be used.
2. **Server export.** PSF-I exports, as CSV, the lead captures, door and swag redemptions and CoC captures for the test codes in the window.
3. **Join.** `uv run python tools/badge_day_audit.py --manifest tests/fixtures/badges.csv --devices exports/*.json --server server/*.csv --out audit.md` joins on code (+ sponsor for lead, + idem key for door) and lists every metric with its offending rows.
4. **Sign-off.** U, PSF-E and PSF-I sign `audit.md` in the G-Staff or G5 issue. PSF-I then deletes production test records if any were created.

### 11.4 Pass criteria

| | BD1 → G-Staff | BD2 → G5 |
|---|---|---|
| Volume | ≥ 300 scans across the 4 tools | ≥ 500 across the 4 tools, including 30 min in airplane mode |
| Lost / misattributed | 0 / 0 | 0 / 0 |
| Two devices, one attendee | recommended | required: "Already" online, or correct server reconciliation after the offline overlap |
| E1 first try (if present) | ≥ 95 % | ≥ 98 % (criterion S4) |
| Crashes; silent failures | 0; 0 (every failed row is in "Retry failed") | same |
| If NO | Fix list and retest at BD2; a failing tool ships behind its kill switch with the manual path | G5 "If NO" (§16) |

---

## 12. Accessibility (criterion S7, D-70)

### 12.1 Automated checks

**Contrast.** `tests/unit/test_THEME_0x_contrast.py` computes the WCAG ratio for each `(fg, bg, kind)` in `Tokens.CONTRAST_PAIRS`, for all four themes, with dark resolved per platform (`#000` iOS, `#121212` Android).
Text ≥ 4.5:1 (≥ 7:1 HC); non-text ≥ 3:1 (WCAG 1.4.11, set here). Pairs: text on surfaces; white header text/icons on `#3B3EA9`/`#680579`; badge text on every track colour; favourite `#fbbf24`; status chips; `#4a0072`, `#ffd60a`/`#0b0f17` in HC. If an Ionic hex fails, change the **foreground** token, never a brand colour (D-65), and record the ratio.

**Labels kept verbatim** (`test_a11y_aria_labels_verbatim`, read against the vendored Ionic HTML; lower-case prefix, so `feature_trace` does not count it for any id. THEME-07, keyboard-focus affordances, has its own `test_THEME_07_focus_order`):

| Ionic label | Where |
|---|---|
| `Show favorites` / `Show all sessions` | schedule star (SCHED-07) |
| `Filter sessions` / `… (some tracks hidden)` / `… (custom filters active)` | funnel (SCHED-10) |
| `View <name> sponsor details` | sponsor banner (SHELL-08) |
| `Show booth <N> on the Expo Hall map` | booth chip (SPON-04) |
| `Show <label> on the <floor> floor plan` / `Open <plan> floor plan` | location and map cards (MAP-06, MAP-02) |
| `Location` (pin fallback when no pin label) | floor-plan modal (MAP-05, INFO-13) |
| `Close floor plan` / `Close booth details` / `Search booths` | INFO-13, EXPO-03, EXPO-04 |
| `Total checked in for this session` | DOOR-06 |
| `App theme` | THEME-01 |
| `X`, `Bluesky` | INFO-10 |

**Scan announcements** (PLAN §8.2). Every outcome is rendered in a status line wrapped in `ft.Semantics(live_region=True)` and plays a distinct `ft.HapticFeedback` pattern. `await SemanticsService().announce_message(msg)` is called **only** when `(await SemanticsService().get_accessibility_features()).supports_announcements` is True (iOS, web), because Android discourages direct announcements and may ignore them; `assertiveness` has an effect only on web. These calls are coroutines (N.1). The haptic patterns are set here. `test_LEAD_07_announcement_table` checks the table and covers both paths (probe True and False). A spy on the `platform` seam asserts, in F20 and F22, exactly one live-region update per outcome, plus exactly one `announce_message` call only when the probe reports `supports_announcements=True`.

| Outcome | Haptic |
|---|---|
| `Checked in` | `light_impact()` |
| `Already checked in` | `medium_impact()` ×2 |
| `Entry not permitted` | `heavy_impact()` |
| `Invalid QR code` | `vibrate()` |
| `Captured` (lead, CoC): status-line copy set by this plan (§17.6); Ionic shows only the attendee's first name (lead) or the name and "N incidents on record" (CoC) | `light_impact()` |

The first four are Ionic copy (`Invalid QR code` at Swag only).

**Also:** text-scale 2.0 goldens fail on overflow (§6.1); a lint rejects interactive controls under 48 dp or with `visual_density=COMPACT`; a unit test asserts every repeating animation (pulsing pins, banner rotation, Jump-to-Now collapse) checks `reduce_motion or disable_animations` (THEME-09).

### 12.2 The 12 scripted screen-reader flows (at M4, then 3 per RC)

VoiceOver on the iPhone 12, TalkBack on the Pixel 6a. **Pass** = completed without sighted help, the expected label and role on every control, and focus order matching the visual order. Findings are P1 (never cut, D-06). At M4 a CC audit and Android Accessibility Scanner / Xcode Accessibility Inspector runs on the 14 golden screens happen alongside.

| # | Flow | Ids |
|---|---|---|
| A1 | Welcome → Schedule | SHELL-02 |
| A2 | Change day; a row reads time, title, room, speakers, track, favourite state | SCHED-01, SCHED-03 |
| A3 | Favourite without swiping (long-press menu or the detail star) | SCHED-11, SESS-03 |
| A4 | Search, then "Search all days" | SCHED-05, SCHED-06 |
| A5 | Filter modal: untick a track; the funnel label changes | SCHED-09, SCHED-10 |
| A6 | Session → speaker → Back | SESS-07, SPKR-03, SESS-12 |
| A7 | Now & Next | SCHED-25 |
| A8 | Room → floor plan → "Close floor plan" | ROOM-05, INFO-13 |
| A9 | Sponsor → "Show booth N on the Expo Hall map" → "Search booths" | SPON-04, EXPO-04 |
| A10 | "App theme" → high contrast | THEME-01 |
| A11 | Log in; log out through the pending-rows guard | AUTH-01, AUTH-11 |
| A12 | Door check by manual entry: hear "Checked in", then "Already checked in" (on TalkBack, read from the live-region status line) | DOOR-04, LEAD-01 |

---

## 13. Performance method and budgets (criterion S6, D-99, PLAN [§8.3](../PLAN.md#83-performance-budgets))

**Marks.** Every build prints `PYCON_MARK <name> <monotonic_ms>` for `py_main`, `cache_published` and `first_schedule_rows`, plus `feed_process_ms`. Embedded-Python stdout reaches Android logcat (`flet.python`/`python` tags), the iOS console and the browser console.

| Budget | Target | Method | Runs |
|---|---|---|---|
| Cold start → cached schedule | p50 ≤ 2.5 s Pixel 6a, ≤ 2.0 s iPhone 12 | **Android:** `am force-stop org.pycon.us`; `logcat -c`; `adb shell am start -W $(adb shell cmd package resolve-activity --brief org.pycon.us \| tail -1)`; duration = the `logcat -v epoch` time of the `first_schedule_rows` line − the time of ActivityTaskManager's `START u0` line (both device clock). **iOS:** `xcrun devicectl device process launch --terminate-existing` with console output attached (flag checked at M0); host time before launch → host receipt of the mark; cross-checked on 3 runs against a 60 fps screen recording | 20 after 1 warm-up; p50, p90 |
| First Android launch | ≤ 6 s | as above after `adb shell pm clear org.pycon.us` (includes unpacking `app.zip` on first launch) | 5; max |
| Feed processing (824 KB) | ≤ 400 ms | `feed_process_ms`; spike S3; `asyncio.to_thread` only if > 150 ms (D-49) | 20; p50 |
| Scroll | ≤ 1 % janky frames | **Android:** Perfetto FrameTimeline during a scripted 30 s fling of Saturday (`adb shell input swipe` loop); jank = app-layer frames with a jank type ≠ None ÷ frames. **iOS:** `xcrun xctrace record --template 'Animation Hitches'` | 3; worst |
| Memory at max expo zoom | ≤ 300 MB | `adb shell dumpsys meminfo org.pycon.us` TOTAL PSS after max zoom and a corner-to-corner pan on EXPO-01 | low-RAM; 3; max |
| Download size | Play ≤ 40 MB arm64; iOS ≤ 60 MB | Play Console download size; locally `bundletool get-size total --apks <apks> --device-spec arm64.json`; App Store Connect size or the App Thinning Size Report | per RC |
| Web first load | ≤ 8 s on 4G | Playwright Chromium + CDP `Network.emulateNetworkConditions` (9 Mbps down, 1.5 up, 170 ms RTT, cache off) → `first_schedule_rows` console mark. Over 8 s → "install the app" page (D-93) | 5; p50 |

**Tripwires (nightly, non-gating):** `test_perf_feed_process_tripwire` (lower-case prefix, ignored by `feature_trace`; DATA-35 is traced by `test_DATA_35_bootstrap_order`, which asserts the D-46 sequence) fails above 2× the median in `tests/perf/baseline.json` (nightly `tripwires` job: `uv run pytest tests/perf`); emulator cold start is a trend only. R13 is checked at M2; G5 needs every row met on the RC.

---

## 14. Observability (criterion S5, D-86, D-87, PLAN [§8.4](../PLAN.md#84-observability))

### 14.1 Sentry configuration (`services/crash.py`)

```python
sentry_sdk.init(
    dsn=settings.SENTRY_DSN,               # per-env constant (DSNs are public); None in dev/test
    release=f"{build_info.VERSION}+{build_info.BUILD_NUMBER}",   # "27.0.0+27000" (D-86)
    environment=build_info.PYCON_ENV,
    send_default_pii=False,
    include_local_variables=False,         # notes, names and codes never leave the device
    max_request_body_size="never",
    max_breadcrumbs=50,
    traces_sample_rate=0.0,
    before_send=scrub_event,
    before_breadcrumb=scrub_breadcrumb,
)
sentry_sdk.set_tag("caps", caps.as_tag())
sentry_sdk.set_tag("target", build_info.TARGET)
```

Inputs (D-86): the `flet` logger handler, the asyncio exception handler and `@safe`.

**Spike S6** checks on device that sending and release-health sessions work from the embedded runtime, and whether `sentry-sdk`'s logging and asyncio integrations can replace the hand-written handlers.

Fallback: the envelope reporter, with crash-free figures from Play vitals and the Xcode Organizer. The web build sends nothing unless spike S6 also passes on Pyodide (proposal). Opt-out: the `crash_opt_out` pref (D-60) skips `init`; disclosed in P11.

### 14.2 Scrubbing rules

| Data | Rule |
|---|---|
| API key and secret | Exact-value replacement anywhere in the event (values loaded from SecureStorage) |
| Headers `X-API-Key`, `X-API-Signature`, `X-API-Timestamp`, `Authorization`, `Cookie` | Dropped |
| Query parameters `attendee_access_code`, `badge_validator`, `access_code` | Value → `[code]` |
| Path `lead_retrieval/<code>/note/` | → `lead_retrieval/[code]/note/` |
| Badge payloads | Any token `core.badges.parse_badge` accepts → `[badge]` |
| Emails | Regex → `[email]` |
| Notes, attendee names, dietary/allergy data | Never sent: no bodies, no locals; log messages pass through the scrubber; breadcrumbs carry only method, scrubbed URL and status |
| Public feed data, sponsor and session ids | Kept |

`test_obs_sentry_scrubber` injects hypothesis-generated PII into the message, exception, breadcrumbs, tags and extra, and asserts that none survives. `test_INFO_04_diagnostics_redacted` does the same for the diagnostics JSON (D-87).

### 14.3 Dashboards and alerts

| View | Source | For |
|---|---|---|
| Crash-free per release | Sentry release health (if spike S6 passes), Play vitals, Xcode Organizer | criterion S5, G5, G6 |
| Issues by `caps`/`target` | Sentry | capability failures, kill-switch calls |
| Outbox failures | `capture_message("outbox.failed", level="warning")`, tags `kind`, `tries` (no code) | staff health |
| 27.x adoption | Play Console, App Store Connect, Sentry release adoption | criterion S8 |
| Banner delivery | hosting logs: `app-config.json` requests 5/15/60 min after `starts_at` (no analytics, OD-3) | announcements |

The conference-week board (05-05 → 05-18) links all five. **Alerts:** crash-free < 99.5 % over 1 h → page the P12 on-call pair; a new issue in the current release → email and Discord; > 5 `outbox.failed` in 15 min → staff channel.

---

## 15. CI wiring (test jobs; full YAML in `docs/build-and-release.md`)

| Workflow | Jobs |
|---|---|
| `ci.yml` (PR, no secrets, ~25 min wall) | `lint` (ruff incl. DTZ, pyright, no-flet-in-core, no-extension-in-screens, touch targets); `test` (one job: unit × 2 time zones, `TZ=America/Los_Angeles` and `TZ=Pacific/Kiritimati`; differential, Node 22 + esbuild, cached on `vendor/REF` + lockfile; contract, recorded; app-config/app-content schemas); `ui-smoke` (host mode, `-m smoke`, `xvfb-run`, `FLET_TEST_DISABLE_FVM=1`; the sparse flet-dev/flet checkout at the pinned tag in `.flet/` (§6.2), whole tree cached); `golden-subset` (Android emulator, `uv run flet test android -d emulator-5554 --tests-dir tests/golden -k golden_pr_subset --yes`, uploads `*_actual.png`); `trace` (after the other test jobs, even when they fail: `feature_trace.py --check --junit` over the PR jobs' junit plus the `nightly-*.xml` of the newest completed `nightly.yml` run on `main`; from G4 a red or yellow required id fails, §8) |
| `nightly.yml` | `ui-host` (every H flow: `FLET_TEST_DEVICE_MODE=0 FLET_TEST_DISABLE_FVM=1 FLET_TEST_FLUTTER_APP_DIR=.flet/client FLET_TEST_APP_PATH=tests/harness FLET_TEST_APP_MODULE=host_main xvfb-run -a uv run pytest tests/ui`, no `-m smoke`); `ui-device-android`, `ui-device-ios` (★ subset, `macos-26`); `golden-full` (input `update_goldens`); `fallback-parity`; `flet-main`; `contract-live`; `perf-web` (`flet build web`, then `uv run pytest tests/perf -k web_first_load --web-url <served build>`; `test_perf_web_first_load` skips without `--web-url`); `tripwires` (`uv run pytest tests/perf`); `burndown` (Mondays, to the job summary). Every test job uploads its junit as `junit-<job>` (`nightly-<job>.xml`) for `trace` and `burndown` |
| `release.yml` | no tests: it promotes the binary that passed G5 (D-92) |

Android jobs save a filtered logcat (`flet.python:V python:V AndroidRuntime:E "*:S"`) as an artifact, as the Flet CI does.

---

## 16. Quality gates G4 and G5

**G4: 2027-03-31.** If NO: apply the cut order until green (PLAN §7.4).

| # | Criterion | Evidence |
|---|---|---|
| G4.1 | Every non-dropped id green in `feature_trace --check --junit` over the merged PR + nightly junit (≥ 1 traced test passed, none failed or skipped); 0 open P0/P1 parity bugs (criterion S1) | `trace` on `main` |
| G4.2 | The live `/2027/` feed (P8 sample if late) validates, processes with no skipped slots, and passes the differential suite | `contract-live`, `differential` |
| G4.3 | Contract nightly green for 7 consecutive days (03-25 → 03-31) | `contract-live` history |
| G4.4 | The 12 flows done on VoiceOver and TalkBack; contrast, label and text-scale tests green; CC audit P1s fixed (criterion S7) | M4 a11y issue |
| G4.5 | All goldens in the active matrix (168; 98 if the D-17 zero-contributor cuts drop the 1024 dp width) and fallback parity green for 3 consecutive nights | nightly history |
| G4.6 | 2027 app-content (P9, 03-20) validates and renders on the 14 screens | `contract`, a goldens re-record PR |
| G4.7 | A co-maintainer has cut the `v27.0.0-alpha.5` freeze build (D-107, amended by D-126) | `release.yml` run log |

**G5: 2027-04-14.** If NO: submit by 04-23 if only server-mitigable P1s remain; otherwise the PSF decides (Ionic + an Appflow content update).

| # | Criterion | Evidence |
|---|---|---|
| G5.1 | Beta crash-free ≥ 99.5 % over 04-01 → 04-14 (criterion S5) | §14.3 |
| G5.2 | 0 open P0 | issue query |
| G5.3 | Badge Day 2 passed (§11.4, criterion S4) | signed `audit.md` |
| G5.4 | Every §13 budget met on the RC (criterion S6) | RC device-lab sheet |
| G5.5 | P11 ready: Data Safety, App Privacy, privacy policy, age rating, export compliance, review demo account with staff roles (D-95) | PSF confirmation |
| G5.6 | §10 checklist complete on the RC to be promoted, with no open P0/P1 from it | RC issue |
| G5.7 | Every non-dropped id green in `feature_trace --check --junit` over the merged PR + nightly junit (≥ 1 traced test passed, none failed or skipped), and all nightly jobs green on the RC commit | CI |


---

## 17. Open points and amendments

Items 1-5 are recorded in section P of [`decisions.md`](decisions.md) and are binding; item 6 is still open and needs a D-number before it is binding.

1. **D-56 timeouts (resolved by D-116):** "lead sponsors and capture 5 s" holds only for CoC capture; Ionic uses 2 s for lead capture, lead notes and `attendees_by_product`. §3.1 follows Ionic.
2. **D-98 gate (resolved by D-129):** read literally, it fails every PR from 2026-12-07 because M3/M4 ids cannot have tests yet. §8 ramps by milestone exit and requires every id from G4 (criterion S1).
3. **`RemoteTester` lacks `drag`, `drag_from`, `tap_at` and all `mouse_click`/`right_mouse_click`/`mouse_double_click` (+`_at`) methods, and its `pump_and_settle` has no `timeout`** (fixed 60 s RPC timeout; local 1.1.0). CAP-66 lists `drag` without saying it is host-only. SCHED-11 swipe is host-mode only. A small upstream PR (`RemoteTester` + `remote_widget_tester.dart`, plus a `timeout` on `RemoteTester.pump_and_settle`) closes it; candidate new U-id (recorded in D-129 and §N.20; no U-id yet).
4. **New names and amendments beyond section M (resolved by D-136):** `pycon_us/ui/ids.py`, `tests/harness/`, `tests/perf/baseline.json`, repo-level `config/<year>/<env>/` (app-config and app-content sources), `tools/badge_day_audit.py`, devserver `/__test__/*`, `settings.SENTRY_DSN`, `PYCON_MARK` lines, CI environment `staging`; and the test-only bootstrap step 0 (reads `/__test__/scenario`, gated by `page.test` and `PYCON_ENV == "dev"`) ahead of D-46 step 1.
5. **Additions to P3/P10 (resolved by D-129; PLAN §10.2):** a server export of test-badge records within 24 h of each Badge Day; whether BD2 may run on production with test badges; staging keys for the nightly contract job.
6. **Thresholds and copy set here (open):** non-text contrast ≥ 3:1, haptic patterns, feedback latency < 500 ms (diagnostic), the DEMO clock instant, the golden PR subset, the 4G profile, the `Captured` status-line copy (§12.1).
