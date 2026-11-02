Closes #

<!--
One issue, one PR (D-92), on a branch `<type>/<issue>-<slug>`. Aim for about 400 changed lines or fewer, not
counting lockfiles, fixtures, generated files and data snapshots. Open it as a draft early; mark it ready when the
checklist holds. Add `--project "PyCon US Flet"`, the issue's type and area labels and its milestone.
-->

## What and why

## How it was tested

<!--
Commands you ran and what you saw: the full `tools/check.sh` (D-273; `uv sync --locked`, `ruff check`,
`ruff format --check`, `pyright`, `pytest --hypothesis-profile=ci`), plus anything specific. Devices (Android
emulator, iOS simulator, phone) and the Flet pin (`.flet-ref`). Never claim a check you didn't run.
-->

## Screenshots

<!--
UI changes only; otherwise write "No UI change". Android emulator and iOS simulator, light and dark when relevant.
Push the PNGs to the pr-assets branch (AGENTS.md, D-162) and embed them as
![Android, light](https://github.com/ndonkoHenri/pycon-us-flet/blob/pr-assets/<pr>/<file>.png?raw=true)
From a fork, drag the images into the PR instead (CONTRIBUTING.md).

| | Android emulator | iOS simulator |
|---|---|---|
| Light | | |
| Dark | | |
-->

## Reviews

<!--
- Second opinion (D-100): required for more than 400 changed lines, architecture changes or edits to
  docs/decisions.md. Name the model, link the PR comment that summarises its findings and what changed, or write
  "Not required" with the reason, or "Owed (capped), D-458" when the reviewer is capped.
- Copilot, when requested (`gh pr edit <n> --add-reviewer @copilot`; paused while the repo is private, D-273): it
  doesn't replace the second opinion; each comment is fixed or answered on its thread with the reason.
-->

## Checklist

<!-- Before merging (D-93, D-100). Tick what holds; strike through and explain what doesn't apply. -->

- [ ] The issue's acceptance criteria are met.
- [ ] Tests added or updated; the full `tools/check.sh` passes on the latest commit, and the merge gate
  (`tools/gate.sh`) passed on what will land before merging (D-273; `ci.yml` once the repo is public).
- [ ] Runs on Android and iOS, with screenshots (UI or native changes).
- [ ] Accessible: labels, contrast, 200 % text, touch targets (`docs/ux.md` checklist).
- [ ] Docs and `docs/decisions.md` updated in this PR when behaviour or decisions changed.
- [ ] Second opinion done when required, or owed under D-458; every review comment fixed or answered with a reason.
- [ ] I re-read the whole final diff.

## Follow-ups

<!-- Issues filed for work found along the way, or "None". -->
