# Year data

Bundled, per-year conference data (D-45): one folder per year, e.g. `2026/`, holding

- `conference.toml`: name, dates, time zone, venue, site and feed URLs, and the track registry;
- `content.toml`: texts and links for the info pages (today only the display-time overrides);
- `map.toml`: floor plans, room pins and booths (P2);
- `conference.json`: the feed snapshot used for an offline first launch (P0-17).

`pycon_us.config.load_year()` loads them with `tomllib` into frozen dataclasses. The dataclasses are
the schema: an unknown or missing key, a wrong type or a broken rule fails with an error naming the
file, the key and the problem, and `tests/test_config.py` loads every year.

`config.YEAR` picks the year the app shows. `2025/` is kept for its recorded feed in
`tests/fixtures/feeds/`; its Eastern time zone keeps the code honest about zones. Rolling over to
2027 means adding `2027/` and setting `config.YEAR`.
