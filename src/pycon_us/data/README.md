# Year data

Bundled, per-year conference data (D-45): one folder per year, e.g. `2026/`, holding

- `conference.toml`: name, dates, time zone, venue, site and feed URLs, and the track registry;
- `content.toml`: texts and links for the info pages (today the display-time overrides, the venue's names for
  feed processing, the places that are not rooms, the Map's "Other locations", the Open spaces and Lightning
  talks pages' copy, the keynotes and panels, keyed by the feed's session ids, D-217, and the
  conference moments written by hand, the sign-ups, each with its public source, D-274; the info pages'
  tables join as each page lands, in `year_info.py`, D-263: so far `[wifi]`, the network and password, D-280,
  `[[venue_hours]]`, when each venue service is open, D-282, `[psf]`, About the PSF's mission, Donate and
  links, D-283, and `[social]`, the hashtags and the profile and blog links, D-284);
- `map.toml`: floor plans, room pins and booths (P2);
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

`config.YEAR` picks the year the app shows. `2025/` is kept for its recorded feed in
`tests/fixtures/feeds/`; its Eastern time zone keeps the code honest about zones, and its keynotes and
moments test the moments in a second year (D-274). Rolling over to
2027 means adding `2027/` and setting `config.YEAR`.
