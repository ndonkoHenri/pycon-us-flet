# Tools

What's here, and when you'd reach for it. Run from the repo's root; each script's opening lines give its options.

## Everyday

| Tool | When |
|---|---|
| `setup_worktree.sh` | A fresh worktree: venv, pub cache, hook (`docs/development.md` §5.8) |
| `check.sh` | The checks: `--fast` before a push, in full before a PR is ready; it runs the `.pre-commit-config.yaml` hooks too |
| `check_backticks.py` | Reject reST double backticks in Python comments and docstrings (a pre-commit hook; D-480) |
| `merge.sh` | Gate a PR and merge it. Don't pipe the gate yourself (AGENTS.md) |
| `gate.sh` | The gate alone: what `merge.sh` runs |
| `pr_shots.sh` | Upload a PR's screenshots to `pr-assets` and print the Markdown |
| `board.sh` | Set an issue's or a PR's status on the Project |

## Devices

| Tool | When |
|---|---|
| `device.py` | Boot and shut down your own emulator or simulator; set its text, contrast and appearance |
| `mock_api/own.py` | Keep a mock on your checkout's own port |
| `mock_api/` | The mock API itself ([`README.md`](mock_api/README.md)) |
| `demo_videos.py` | Film the demo clips (`maestro/demo/`) on a new simulator (`record`), and lay a clip's frames out to read (`sheets`) |
| `clip_processing.py` | The video half of `demo_videos.py`: trim a recording to the stretches that change, and the contact sheets and flash checks of a clip |
| `sweep.py` | Photograph the staff tools per text size and appearance, for a person to read |
| `offline_scans.py` | Run the offline scans journey, with a mock whose listener can stop and keep its captures |
| `feed_pair.py` | Serve a change-log feed pair for the change log's device check |
| `shifted_feed.py` | Write the feed shifted in time, to check reminders in real time |
| `a11y_tree.py` | Print Android's accessibility tree with headings; `a11y_tree_apk/` is its helper |

## Measuring

| Tool | When |
|---|---|
| `cold_start.py` | Android cold starts as `docs/testing-and-quality.md` §8 says |
| `frames.py` | Read a screen recording: a pixel's colour changes, or the screen's |

## Data

| Tool | When |
|---|---|
| `update_snapshot.py` | Refresh the bundled feed before a build for testers |
| `check_feed.py` | Check the live public feed |
| `feed_invariants.py`, `sponsor_invariants.py` | The invariants the tests and `check_feed.py` share |
| `feed_outline.py` | The reviewed snapshot's view of a feed |
| `encode_plans.py` | Encode a year's floor plans |
| `check_matrix.py` | Check `docs/feature-matrix.md` after editing it |
| `capture_ionic_reference/` | Capture the Ionic app's reference fixtures ([`README.md`](capture_ionic_reference/README.md)) |
