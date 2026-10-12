Closes #

<!--
One issue, one PR (D-92), on a branch `<type>/<issue>-<slug>`. Aim for about 400 changed lines or fewer, not
counting lockfiles, fixtures, generated files and data snapshots. Open it as a draft early; mark it ready when the
checklist holds. Add `--project "PyCon US Flet"`, the issue's type and area labels and its milestone.
-->

## What and why

## How it was tested

<!--
Commands you ran and what you saw: `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`,
`uv run pytest`, plus anything specific. Devices (Android emulator, iOS simulator, phone) and the Flet pin
(`.flet-ref`). Never claim a check you didn't run.
-->

## Screenshots

<!--
UI changes only; otherwise write "No UI change". Android emulator and iOS simulator, light and dark when relevant.
Push the PNGs to the pr-assets branch (AGENTS.md, D-162) and embed them as
![Android, light](https://github.com/ndonkoHenri/pycon-us-flet/blob/pr-assets/<pr>/<file>.png?raw=true)

| | Android emulator | iOS simulator |
|---|---|---|
| Light | | |
| Dark | | |
-->

## Reviews

<!--
- Second opinion (D-100): required for more than 400 changed lines, architecture changes or edits to
  docs/decisions.md. Name the model, link the PR comment that summarises its findings and what changed, or write
  "Not required" with the reason.
- Copilot, when requested (`gh pr edit <n> --add-reviewer @copilot`): it doesn't replace the second opinion; each
  comment is fixed or answered on its thread with the reason.
-->

## Checklist

<!-- Before merging (D-93, D-100). Tick what holds; strike through and explain what doesn't apply. -->

- [ ] The issue's acceptance criteria are met.
- [ ] Tests added or updated; checks pass on the latest commit (CI, or the local checks listed above until CI exists).
- [ ] Runs on Android and iOS, with screenshots (UI or native changes).
- [ ] Accessible: labels, contrast, 200 % text, touch targets (`docs/ux.md` checklist).
- [ ] Docs and `docs/decisions.md` updated in this PR when behaviour or decisions changed.
- [ ] Second opinion done when required; every review comment fixed or answered with a reason.
- [ ] I re-read the whole final diff.

## Follow-ups

<!-- Issues filed for work found along the way, or "None". -->

---
_Written by <agent name> (AI agent)._ <!-- agents only; humans delete this line -->
