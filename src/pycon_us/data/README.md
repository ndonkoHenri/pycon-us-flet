# Year data

Bundled, per-year conference data: one directory per year, e.g. `2026/`, holding

- `conference.toml`: dates, time zone, feed URL and other facts about the year;
- `content.toml`: texts and links for the info pages;
- `map.toml`: floor plans, room pins and booths;
- `conference.json`: the feed snapshot used for an offline first launch.

`pycon_us.config` loads them with `tomllib`; the loader is the schema (D-45).
They arrive with their features (P0-08, P0-17 and P2).
