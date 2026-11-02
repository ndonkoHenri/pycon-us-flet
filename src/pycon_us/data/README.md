# Year data

Bundled, per-year conference data (D-45): one folder per year, e.g. `2026/`, holding

- `conference.toml`: name, dates, time zone, venue, its address and the point Directions opens (`address`,
  `[directions]`, D-313), site and feed URLs, and the track registry;
- `content.toml`: texts and links for the info pages (today the display-time overrides, the venue's names for
  feed processing, the places that are not rooms, the Map's "Other locations", the Open spaces and Lightning
  talks pages' copy, the keynotes and panels, keyed by the feed's session ids, D-217, and the
  conference moments written by hand, the sign-ups, each with its public source, D-274; the info pages'
  tables join as each page lands, in `year_info.py`, D-263: so far `[wifi]`, the network and password, D-280,
  `[[venue_hours]]`, when each venue service is open, D-282, and, in `year_links.py`, `[psf]`, About the
  PSF's mission, Donate and links, D-283, and `[social]`, the hashtags and the profile and blog links, D-284);
- `map.toml`: the floor plans (images in `src/assets/maps/<year>/`, made by `tools/encode_plans.py`, D-312), the
  3D tour's link and the room and venue pins, keyed by `normalize_room_key()` (DATA-32; `year_map.py`), and the
  expo's booths (P2); optional: a year without it (2025) has no plans;
- `conference.json`: the feed snapshot used for an offline first launch (NEW-03, D-135), only for the
  active year.

`pycon_us.config.load_year()` loads them with `tomllib` into frozen dataclasses. The dataclasses are
the schema: an unknown or missing key, a wrong type or a broken rule fails with an error naming the
file, the key and the problem, and `tests/test_config.py` loads every year. The keynotes name sessions of
the feed, each a `Keynote` or a `Plenary`: `load_year(check_sessions=True)` checks them against the year's snapshot, which
`tests/test_year_keynotes.py` does for every year (2025, which bundles no snapshot, against its recorded feed)
and `tools/update_snapshot.py` does for a new feed. The keynotes' and panels' moments are not in the files:
`year_moments.keynote_moments()` derives them from the feed, 15 min before each starts (D-274).

The snapshot is the public feed's bytes, unchanged. `conference.toml`'s `snapshot_captured_at` says when
it was fetched; a year has that key exactly when it has the file. `YearData.read_snapshot()` reads both
on demand. To refresh it before a build, run `uv run python tools/update_snapshot.py`: it fetches the
feed of `config.YEAR`, refuses one that does not parse cleanly, replaces each file atomically (one
after the other) and prints the count changes. Review the diff like any other.

A year's links are checked by hand, since the site changes under them. The PSF archives a past year as
static pages: its feed then names `pycon-archive.python.org`, and the pages that needed the live site (a
sign-in, a form) are gone. So a link the archive doesn't serve leaves the data, and its control goes with it
(`registration_url`, `sprint_submit_url`, `speaker_discord_url`, `propose_url` and `signup_url` are optional:
no dead control), and the copy says how things stand. 2026 lost those five (#824, checked 2026-11-02).

`config.YEAR` picks the year the app shows. `2025/` is kept for its recorded feed in
`tests/fixtures/feeds/`; its Eastern time zone keeps the code honest about zones, and its keynotes and
moments test the moments in a second year (D-274).

## Rolling over to a new year

The app's code holds no year: `src/pycon_us/`'s code names 2026 only in `config.YEAR`, a licence text, comments and
docstrings. These are the steps, as a rehearsal on a synthetic 2027 found them (#842). `2027` stands for the new year.

**1. Record the feed** once it is public: `tests/fixtures/feeds/README.md` says how. `tools/check_feed.py` reports
when next year's feed answers.

**2. Add `data/2027/`, copied from the year before.** A copy loads only once its dates are in its year, and nothing
but a person can say the facts are still true. What a new year must supply:

| File | What to re-check | What catches a miss |
|---|---|---|
| `conference.toml` | `year`, `name`, the three dates, `time_zone` and its name, `venue`, `city`, `address`, `[directions]`; every URL (a new number isn't proof the page exists); `[[tracks]]`, adding the feed's new kinds and `new = true`; a track has two names, `short` and `plural`, as the comment above them says. Drop `snapshot_captured_at`: step 4 writes it | the loader, for year and date rules; an unknown track only falls back to its humanised name |
| `content.toml` | Each table has its source in a comment. Keynotes and panels, by the new feed's session ids; `[[safety_contacts]]` and `[help]`, from public pages only, with a new `checked` date (D-45, D-281); `[wifi]`; `[[venue_hours]]`; `[[event_reminders]]`; sponsor credits; `[psf]`, `[social]`; the Open spaces and Lightning talks copy; the feed-processing overrides, which name this year's rooms | the loader for dates outside the year; `tools/update_snapshot.py` for a keynote or sponsor the feed lacks; `tests/test_year_info.py` for a stale `checked`. An empty file loads: nothing catches a table left out |
| `map.toml` and `src/assets/maps/2027/` | The plans, by `tools/encode_plans.py` (their marks painted out, `NOTICE`), the pins, the booths. 2026's source arrived days before the conference (`PLAN.md`), so this comes last. Optional, as in 2025; the pins `content.toml` names must then go, as the loader says | the loader, for a pin outside a plan or a name `map.toml` lacks |

**3. Set `config.YEAR = 2027`**, in `config.py`, as the only code change.

**4. Bundle the snapshot:** `uv run python tools/update_snapshot.py` writes `conference.json` and
`snapshot_captured_at`. It works on a folder with neither, and refuses a feed that doesn't fit the year's data.

**5. Bring the tests along:**

- `tests/feeds.py`: add 2027 to `YEARS`. Every test over `YEARS` then also runs on the new feed, and needs
  `tests/fixtures/snapshots/outline-2027.json` (`--snapshot-update`, reviewed) and a capture of Ionic in
  `tests/fixtures/ionic/2027/` (`tools/capture_ionic_reference/README.md`; it needs Node, and Ionic must have a 2027).
- Keep `data/2026/`, its snapshot and `src/assets/maps/2026/`: about 250 test files pin 2026 as fixed data, on
  purpose, so a new feed moves none of their counts. They stay green, and they do not test the new year's data.
- The tests of the active year read `YEAR` (`tests/test_config.py`, `tests/test_check_feed.py`, `tests/test_feed.py`
  and the device flows' `tests/ui/`), and need the recorded feed of step 1.

**6. Update the Maestro flows, and run them on devices:** 13 files in `maestro/` write 2026's dates and facts (the
fake clock's `NOW`, `conference-2026.json`, the Wi-Fi password, a booth): `grep -rl 2026 maestro/`. No check reads
them until a device runs them.

**7. Look at the bundle.** The app never reads `2026/` again, but `flet build` copies all of `src/`, so its 860 KB
and its 1.4 MB of plans still ship. `[tool.flet.app] exclude` can drop them; this has not been tried.

A new brand's colours are not year data: they are code and build settings (`theme.py`, `pyproject.toml`'s splash and
boot screen).

The mock server and its badge sheet follow `config.YEAR` on their own. The seed's `products` keep their made-up
"Wed May 13" names, and `tests/fixtures/mock/seed.json` keeps 2026 for the tests.

### What an update does to an install

What a person kept under 2026, once an update makes 2027 the year (D-48, D-466; `tests/test_year_rollover.py`):

| Kept | Where | In the new year |
|---|---|---|
| Saved sessions, their sync state | `pycon.<year>.favorites`, `.favorites_sync` | start empty; 2026's stay, unread |
| Feed cache | `feed-<year>.json` | the bundled snapshot, then the new feed; 2026's file stays, unread |
| Change log and its marker | `changes-<year>.json`, `pycon.<year>.fetched` | start again, so no change is logged across years |
| Staff sponsor, door session, swag categories | `pycon.staff_<year>_…` | not chosen yet |
| Staff outbox | `outbox-<year>.db` | empty. A 2026 row never reaches 2027's server; one not synced stays in its file |
| Theme, contrast, filter, reminder settings, start screen, Developer options | `pycon.<name>` | carry over. A filter's track missing from the new feed is ignored; a new track shows |
| Welcome seen | `pycon.onboarded` | carries over, so Welcome doesn't show again |
| Account, scanner consent | `pycon.account`, secure keys, `pycon.staff_scanner_consent` | carry over; a key the new server refuses makes the account `expired`, as any refused key does (D-57) |
| Reminders | the OS | the first start replaces what is pending with the new year's plan (D-59) |

Reset app deletes every year's preferences, cache and change log, and this year's outbox rows. Another year's
`outbox-<year>.db` stays until the app is uninstalled: its rows may be unsynced, and no confirmation names them
(D-414, D-466). That is accepted while those rows are the mock's (D-51); D-466 says what changes if they ever aren't.
