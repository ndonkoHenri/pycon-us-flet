# Ionic reference capture

Runs the Ionic app's own `processData` (`ConferenceData` in `src/app/providers/conference-data.ts`) on the recorded
feeds once, and commits what it made of them as facts in `tests/fixtures/ionic/<year>/` (D-77, SCHED-19, #66).
`tests/test_ionic_reference.py` compares our processed model with those facts through the normaliser in
`tests/ionic.py`; every difference is either fixed or listed in its `INTENDED_DIFFERENCES` with a decision or feature
id, and shown by a named test.

**CI never runs this tool, and contributors never need Node.** The tests only read the committed JSON.

## Provenance of the committed capture

| | |
|---|---|
| Ionic source | [PyCon/pycon-us-mobile](https://github.com/PyCon/pycon-us-mobile) at `2aa6df8a86890df2d243f9e165905957614ae47e` |
| Copied unchanged | `src/app/providers/conference-data.ts`, `src/app/location-map/room-locations.ts`, `src/app/location-map/venue-locations.ts`, `tsconfig.json` |
| npm packages (versions from Ionic's `package-lock.json`) | `markdown-to-txt` 2.0.1, `marked` 4.3.0, `lodash` 4.17.21, `lodash.escape` 4.0.1, `lodash.unescape` 4.0.1 |
| Bundler | esbuild 0.28.2, through `npx --yes esbuild@0.28.2` |
| Runtime | Node v26.8.2, npm 11.19.1, macOS; `TZ=UTC`, `LC_ALL=en_US.UTF-8` |
| Feeds | `tests/fixtures/feeds/conference-2025.json` and `conference-2026.json` (their README has the hashes) |
| Captured | 2026-10-12 |

Each year's `summary.json` repeats this under `captured`, with the environment that year ran with.

## What runs, and what is stubbed

`capture.py` builds everything in a work directory outside the repository:

1. It copies the four Ionic files above, unchanged, from a clone of the Ionic repository.
2. It adds this folder's stand-ins, which `processData` never calls into:
   - `stubs.ts`: `Injectable`, `HttpClient`, `Storage`, `ToastController` and the RxJS imports (`of`, `Observable`,
     `map`, `timeout`, `catchError`), mapped onto `@angular/*`, `@ionic/*` and `rxjs*` with esbuild's `--alias`;
   - `user-data.ts` for `./user-data` (only `filterSession` reads favourites);
   - `environment.ts` for `../../environments/environment`. Ionic's file names 2026's zone (`America/Los_Angeles`,
     UTC−7); `driver.ts` sets each year's zone and offset from `src/pycon_us/data/<year>/conference.toml`, as that
     year's build would have (2025: `America/New_York`, UTC−4).
3. It installs the npm packages Ionic's lock file pins. `markdown-to-txt` is the one third-party code that shapes the
   output (titles); `lodash` is there because `markdown-to-txt` 2.0.1 requires it without declaring it, and Ionic's
   build found the hoisted copy.
4. It bundles `driver.ts` with esbuild and runs it under Node once per feed. The driver calls `processData` and
   prints the facts; it reads the output as it is and corrects nothing.

The query methods (`getDays`, `getTimeline`, …) go through `load()`, which needs Angular's HTTP and RxJS, so the
driver reads `data` directly and sorts the days by date as `getDays` does. Newer ICU puts a narrow no-break space
before `am`/`pm` in Ionic's time labels; the driver writes a plain space, as older devices showed.

## The facts (`tests/fixtures/ionic/<year>/`)

| File | Content |
|---|---|
| `summary.json` | Provenance, then counts: sessions (and per track), duplicate ids, speakers, rooms, groups and sessions per day, and the groups Ionic left without a start time. |
| `timeline.json` | Day → time label → session ids, in Ionic's order. |
| `sessions.json` | Every session in Ionic's order: id, name, track, location, shown location, start, end, shown start, linked speaker ids, author names, the pre-registration and Spanish flags, and whether the timeline lists it. |
| `collapsed.json` | The collapsed Coffee, Break, Lunch and Posters rows: id, name, location, shown location, start, end. |
| `rooms.json` | The rooms in Ionic's order, each with its session ids. |
| `speakers.json` | The speaker directory in Ionic's order: id, name, session ids, tracks. |

Ids are strings, as in our model (D-42).

## Re-running it

Only when a recorded feed is added (2027) or the Ionic reference should move. You need Node 20 or later with npm,
and a clone of the Ionic repository (the main checkout keeps one, read-only, in `excluded/pycon-us-mobile`; its
commit is read from `.git` without running git):

```sh
uv run python tools/capture_ionic_reference/capture.py --ionic excluded/pycon-us-mobile
```

It rewrites `tests/fixtures/ionic/<year>/` for every `tests/fixtures/feeds/conference-<year>.json`. It builds in a new
temporary directory (or the one `--work` names), where `node_modules` stays; nothing is installed in the repository.
Then:

1. Update the provenance table above (the commit, versions and date are also in each `summary.json`).
2. Run `uv run pytest tests/test_ionic_reference.py`. A new difference is either fixed in `core/`, or, when we mean
   it, added to `INTENDED_DIFFERENCES` with its D-number or feature id, handled in `tests/ionic.py`'s normaliser and
   shown by its own named test.
3. Explain the fixture diff in the PR.

Re-running without changes gives byte-identical files apart from `captured.date`.
