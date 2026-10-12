# Recorded public feeds

The public PyCon US feeds, recorded once and committed unchanged, so the feed tests run offline and
on fixed data (D-76, D-77). They are public JSON; tests read them as data.

| File | URL | Recorded | Bytes | SHA-256 |
|---|---|---|---|---|
| `conference-2025.json` | https://us.pycon.org/2025/schedule/conference.json | 2026-10-12 | 543,527 | `469359039797262ab090ad51c03c804a5ceba02258f966b5aea06dfced571349` |
| `conference-2026.json` | https://us.pycon.org/2026/schedule/conference.json | 2026-10-12 | 822,356 | `67ee054ea618360aa8295ca113054be313f28ea5f76268c72639b8f99ce6f2df` |

Notes for readers of the tests:

- 2025 is in Eastern time (`-04:00`), 2026 in Pacific time (`-07:00`).
- The 2025 feed has no `posters`, `sprints` or `job-listings` sections; its posters sit in the
  `sessions` list of one `poster` slot (`conf_key` 154), and processing reads them as posters (D-121).
- Edge cases are built in the tests from deep copies of these files, never as hand-written JSON.

To record the 2027 feed when it appears: `curl -sSfo tests/fixtures/feeds/conference-2027.json
https://us.pycon.org/2027/schedule/conference.json`, then add its row with `shasum -a 256`.
