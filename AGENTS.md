# AGENTS.md

How we build this app: for the humans and the AI agents (Claude Code, Codex, ...) who work on it.
Claude Code reads it through `CLAUDE.md`, which contains only `@AGENTS.md`.
People contributing from outside the team start with [`CONTRIBUTING.md`](CONTRIBUTING.md).

## The project in one minute

We are rebuilding the [PyCon US mobile app](https://github.com/PyCon/pycon-us-mobile) in Python with
[Flet](https://flet.dev), to show the Flet and Python communities what is possible. The official app is our
quality bar, not a dependency: we don't depend on the PSF. The objective is to present the app at PyCon US 2027;
that date motivates us but never justifies cutting corners.

- **Platforms:** Android and iOS only.
- **UI:** Material 3, identical on both platforms. We improve on the original wherever we can; it's not a 1:1 port.
- **Data:** the public `conference.json` feed. Features that need the PSF's private API run against our local mock server.

## Read first

1. [`PLAN.md`](PLAN.md): vision, phases, risks.
2. [`docs/decisions.md`](docs/decisions.md): **binding** decisions (D-ids), naming, verified Flet facts. Read the
   D-ids the issue cites and those for your area, using
   [CONTRIBUTING's lookup block](CONTRIBUTING.md#look-things-up), never the whole file.
3. The doc for your area: [`docs/ux.md`](docs/ux.md), [`docs/architecture.md`](docs/architecture.md),
   [`docs/flet-gaps-and-extensions.md`](docs/flet-gaps-and-extensions.md),
   [`docs/development.md`](docs/development.md), [`docs/testing-and-quality.md`](docs/testing-and-quality.md).
4. [`docs/feature-matrix.md`](docs/feature-matrix.md) for what a feature id means and its gotchas;
   [`docs/roadmap.md`](docs/roadmap.md) for the phases. GitHub issues are the live task list.
5. [`tools/README.md`](tools/README.md) lists the scripts, for setup, devices, merging and measuring: check it before
   writing a throwaway one.
6. `docs/research/` holds the raw analysis of the original app. `excluded/` holds a read-only clone of it
   (gitignored); read it, never edit it.

## Principles

1. **The Zen of Python.** Simple beats clever, readable beats short, explicit beats implicit, flat beats nested.
   If the implementation is hard to explain, it's a bad idea. No speculative abstractions: build what the current
   issue needs.
2. **Quality over speed.** Small steps, each one finished: tested, documented, reviewed.
3. **Mobile and Material only.** No web, desktop or Cupertino code paths. A desktop window may be used as a dev
   convenience only.
4. **Better than the original.** When the original UX is weak, propose a better one in the issue first (`design`
   label), then build it.
5. **Never call private PSF endpoints.** Use the public feed and the local mock server.

## Decisions and documentation

- `docs/decisions.md` is binding. To change it, open an issue labelled `needs-decision` with the options and your
  recommendation, then record the outcome as a new D-number in a PR **before or together with** the code that
  depends on it (D-101):
  - **Reversible choices** don't wait for the maintainers. The question is **settled** once you post the decision as a
    comment on the issue; then record it as a D-number in a PR, mention it in the phase status issue, and remove
    the `needs-decision` label. The maintainers can override later.
  - **Maintainer-only choices** wait for the maintainers: app identity and bundle id; making anything public (the repo, a
    store listing, builds for people outside the team); accounts or anything that costs money; contacting people
    outside this work (the PSF, social media, blogs); and anything that would lose data or need someone else's
    help to undo. Routine work is already authorised: issues, PRs and comments in this repo,
    `ndonkoHenri/pycon-us-flet`, **and nowhere else** (D-212).
- Docs live next to the code they describe and change in the **same PR** as the behaviour.
- `docs/feature-matrix.md` is the source of truth for feature dispositions; edit it directly.
- Code documentation: every module starts with a docstring saying what it is for; every public function and class
  has a docstring (Google style); comments explain **why**, not what. Markdown inline code in docstrings and comments is a
  **single** backtick, never reST's double one (a pre-commit hook rejects it, D-480). Tests too: every test function's docstring says
  the behaviour it pins, and fixtures and test helpers have docstrings (D-253; `ruff` checks `tests/`).

## Working with Flet

- This project's maintainers also maintain Flet. Every Flet package comes from PyPI at one exact version (D-481,
  `docs/development.md` §2.2), and no checkout of Flet is needed. The installed packages, by source or by
  introspection, are the source of truth for Flet APIs, instead of memory or old docs; the Dart is in the pub cache
  after a build, and §2.2 says how to clone the rest for reading. A second worktree of this repo gets its own pub
  cache: run `tools/setup_worktree.sh`, then `docs/development.md` §5.0 is the way to a device (D-176). Never edit
  Flet's files in a clone or in `.venv`: a gap is an upstream issue (below).
- Declarative style: `@ft.component`, hooks, `@ft.observable` stores, `ft.Router`. Follow the rules in
  `docs/decisions.md` D-70 (async APIs only from `async def` handlers; long-running `use_effect` work runs
  in a coroutine setup, which Flet cancels on unmount; one context per observable store; no conditional hooks).
- A missing Flet capability is an **upstream** task (see below), never a fork or a hack: ship the documented
  interim and upgrade when Flet releases the piece.

## How we work on GitHub

### Issues

- **Every change starts from an issue**, except trivial chores (typos, link fixes, lockfile bumps), which can go
  straight to a PR labelled `chore`.
- Phases are **milestones** (`P0 Foundations` ... `P4 Showcase`). Big pieces are **epics**: an issue labelled `epic`
  whose tasks are its **sub-issues** (`gh issue create --parent <epic>`).
- A good issue says: context (links to docs, feature ids, D-ids), scope (in and out), acceptance criteria as a
  checklist, and how to verify. Keep it PR-sized; split it if it isn't.
- Start from a template in `.github/ISSUE_TEMPLATE/`: `feature.md`, `bug.md`, `spike.md` (titled
  `Spike: <question>`, labelled `test`, closing with a verdict in `docs/spikes/NN-<slug>.md`, D-91) or
  `upstream.md`. A blank issue is fine for a chore. With `gh`, which doesn't fill templates in for you, copy the
  template's sections into `--body`, and add every new issue to the Project (see Project board):
  `gh issue create --label <type> --label <area> --milestone "<phase>" --project "PyCon US Flet"`.
- Labels:
  - Type: `feature`, `bug`, `design`, `docs`, `test`, `chore`, `ci`, `refactor`, `epic`, `upstream`.
  - Area: `area:shell`, `area:theme`, `area:data`, `area:schedule`, `area:speakers`, `area:rooms-maps`,
    `area:sponsors`, `area:info`, `area:notifications`, `area:account`, `area:staff`, `area:build`, `area:quality`.
  - Status: `blocked` (say on what), `needs-decision` (a decision is pending; see D-101 for who decides),
    `good first issue`.
- Unsure about something that changes behaviour or a decision? Don't guess silently: comment on the issue with the
  options and your recommendation, add `needs-decision`, and follow the decision rules above (D-101).

### Branches and commits

- Never commit to `main` directly. One branch per issue: `<type>/<issue>-<slug>`, e.g.
  `feature/14-schedule-day-tabs`, `bug/31-timezone-day-bucket`, `docs/7-agents-md` (the type is the issue's type label).
- Commit messages: imperative subject of 72 characters or fewer ("Add schedule day tabs"), a body that explains
  why when it isn't obvious, and the issue reference (`Refs #14`).
- Keep commits focused. Rebase on `main` when needed, but never force-push a branch someone else is working on.
- **`main` is protected** (D-88): every change reaches it through a squash-merged PR, and nobody pushes, force-pushes
  to or deletes `main`. A ruleset on the default branch enforces it (D-505): it requires a PR, blocks force pushes and
  deletion, and requires **no** approvals, so agents can still merge their own PRs (D-100).

### Pull requests

- **One issue, one PR** (`Closes #14` in the body). Aim for at most about 400 changed lines, not counting fixtures
  or generated files; split bigger work.
- Open a **draft PR** early for anything that takes more than a session, so progress is visible; mark it ready
  when it meets the definition of done.
- The PR template (`.github/pull_request_template.md`) asks for: `Closes #N`, what and why, how it was tested
  (commands, devices, Flet pin), screenshots or recordings for UI changes (Android emulator **and** iOS simulator,
  light and dark when relevant), reviews (second opinion and Copilot), a pre-merge checklist (definition of done,
  docs and decision updates) and follow-ups. `gh pr create --body` doesn't fill it in: use its sections.
- Add every PR to the Project: `gh pr create ... --project "PyCon US Flet"`.
- **CI runs on every PR and every push to `main`** (D-505): `ci.yml`'s job `Lint, types and tests`. The local checks
  stay: the pre-push hook runs `tools/check.sh --fast` (ruff, the pre-commit hooks, pyright) on every push that changes
  more than Markdown; run the full `tools/check.sh` before you mark a PR ready and list it in the PR; the merge gate
  runs before every merge (`tools/merge.sh`, below).
- **Screenshots** (D-162): `gh` can't upload images, so they go to the orphan branch `pr-assets`, one folder per PR,
  and the PR embeds them. Look at every image first: no tokens, personal data, notifications or real badges (it all
  stays in history and becomes public with the repo). Keep it to the images the PR needs, about 1 MB per PR.
  `tools/pr_shots.sh <pr> <shots>.png` uploads them (D-168, from any worktree) and prints the Markdown for the PR body
  or a comment, which anyone can see. Never force-push `pr-assets`.

### Reviews and merging

- **Agents merge their own PRs** (D-100). The maintainers watch and can step in at any time, but are never blockers:
  don't wait for approval. Merge only when all of these hold:
  1. **Checks pass on what will land.** Every `ci.yml` check is green on the PR's latest commit (`gh pr checks <pr>`):
     missing, pending, skipped or cancelled checks don't count (the required checks are the `ci.yml` jobs listed in
     `docs/development.md`). A PR's run tests it merged with `main` as `main` was at the push, so `tools/merge.sh <pr>`
     (D-273, D-505) still runs the merge gate, which runs the full checks
     on the PR merged onto the latest `main` and posts the result on the PR, then merges only if the gate passed. Never
     pipe the gate before a merge: that merged #868 after a failed gate. Run it with
     `GATE_SIGNATURE='_Written by <agent name> (AI agent)._'`, so its comments are signed (rule 6). For several PRs in
     a row, name them in merge order; it says when `main`'s tree isn't the gated tree, and then you run
     `tools/check.sh` on `main`.
  2. **The definition of done is met**, and you have re-read the whole final diff yourself.
  3. **A second opinion, when required.** It is required when the PR changes more than 400 lines (not counting
     lockfiles, fixtures, generated files or data snapshots), changes the architecture (module structure, state,
     routing, the data core, signing, the outbox, build or CI), or edits `docs/decisions.md`. The reviewer is a
     **different model** from the author (a Claude model, or Codex run read-only) and reviews the final diff; re-run
     it after substantive changes. Each finding is fixed, or rejected in a PR comment with the reason and
     evidence. If you still disagree on something that matters (correctness, data loss, security), ask the other
     reviewer model; if it's a product question, use `needs-decision`.
     **When the reviewer is capped** (D-458), re-read the final diff, merge after the gate, and say so in a signed
     PR comment that starts `Second opinion owed` and names the reviewer. Run the review later, on what is current
     then, and record the reviewer and the result in a signed comment on that PR. Any Claude model or Codex is
     welcome while its limit allows.
  4. **The maintainers are heard.** A request from the maintainers to stop or change something is acted on, not just
     acknowledged; every maintainer comment has a reply.
  5. **No unsettled `needs-decision` question** affects the PR.
- **A Copilot review** is back (D-505), when its quota allows. D-103 says when to request one and how to handle it; it
  never replaces the second opinion above.
- `tools/merge.sh` squash-merges and deletes the branch; the PR title becomes the commit on `main`.
- The maintainers may comment, request changes or revert at any time. Feedback that arrives after a merge becomes a new
  issue, or a revert PR when something is broken.

### Upstream Flet work

- **This repository is the only one agents work in** (D-212, the maintainers' direction). Agents never open or comment
  on an issue, nor review or send a PR, nor make any other change, in `flet-dev/flet`, `flet-dev/serious-python`,
  an extension's repository or any other repository, even when it would help the upstream track. Reading them (the
  pinned source, issues, PRs) is fine.
- When the app needs something Flet lacks, open an `upstream` issue **here** with the full analysis: what happens,
  the Flet source at the pin (files and lines), a minimal repro, the suggested fix and the interim; a short draft
  diff in a fenced block when it makes the analysis clearer, never a patch file in the app's tree (D-213). The
  maintainers, who also maintain Flet, decide whether and how to take it to Flet; the issue links the flet-dev issue
  or PR once a maintainer has opened one.
- App issues that wait on it get `blocked` plus a link; meanwhile the interim from
  `docs/flet-gaps-and-extensions.md` ships.

### Project board

- A GitHub Project ("PyCon US Flet") gives the overview with one Status field (Todo, In progress, In review,
  Done); group or filter it by milestone (the phase) and by `area:*` label (D-90, D-94). The issue is the source
  of truth; the board is a view of it.
- **The Project's built-in workflows do most of the bookkeeping.** A maintainer turned them on in the web UI
  (the API can't; #118): open issues and PRs are auto-added, "Item added" sets Todo, "Pull request linked to
  issue" sets In progress, "Item closed" and "Pull request merged" set Done, "Auto-close issue" closes an issue
  set to Done, and "Item reopened" sets Todo. Still pass `--project "PyCon US Flet"` when you create an issue
  or PR, so it's on the board at once. It can fail with "Content already exists in this project" when the auto-add
  wins the race; the issue or PR is created anyway, so don't retry it: drop the flag or use `gh project item-add`.
- **Set two statuses yourself**, on the issue and on its PR: In progress when you start, and In review when the
  PR is ready (no workflow sets In review): `tools/board.sh <n> in-progress`, `tools/board.sh <n> in-review`. `gh`
  needs the `project` scope (`gh auth refresh -s project`).
- Each phase has a pinned status issue (`P0 status`, ...). Post a short weekly update there: done, next, blocked,
  decisions needed.

## Rules for AI agents

1. Before starting: read this file, `PLAN.md` and the docs for your area; read the issue and its parent epic; from
   `docs/decisions.md`, read the D-ids the issue cites and those for your area, using CONTRIBUTING's lookup block,
   never the whole file.
2. Say you're on it: comment on the issue with a short plan when the work is non-trivial, and open a draft PR
   early so progress is visible.
3. Work on the issue branch; keep the PR scoped to the issue. Found something else? Open a new issue instead of
   widening the PR.
4. Verify for real: run the tests and linters, and for UI work run the app (emulator, simulator or device). Say
   exactly what you ran and what you saw; never claim a check you didn't do.
5. Don't guess silently on product or architecture questions: use `needs-decision` and the decision rules
   (D-101). Decide the reversible ones yourself and record them; wait only for the maintainer-only kinds.
6. Sign your work: agents act through a maintainer's GitHub account, so end every issue comment and PR comment you
   write with `_Written by <agent name> (AI agent)._`, so the history shows who did the work. Commit messages and PR
   descriptions carry no attribution line (the maintainers' harness setting); the PR's signed comments say who did it.
7. Never call private PSF endpoints, commit secrets or edit `excluded/`.
8. **Act only in this repository** (D-212). Never create or edit issues, PRs, comments, reviews, reactions or
   anything else in any other repository, the `flet-dev` repositories included, and never ask another agent to;
   every brief you give another agent (a subagent, a reviewer, Codex) repeats this rule. An upstream gap becomes an
   `upstream` issue here (see Upstream Flet work).

## Definition of done

- [ ] Acceptance criteria of the issue met.
- [ ] Tests added or updated, all passing; linters clean.
- [ ] Runs on an Android emulator and an iOS simulator (for UI or native changes), with screenshots in the PR; the
  a maintainer's iPhone only for checks that need hardware or a release build (D-102).
- [ ] Accessible: labels, contrast, text scaling, touch targets (`docs/ux.md` checklist).
- [ ] Docs and `docs/decisions.md` updated when behaviour or decisions changed.
- [ ] Follow-ups have their own issues.

After the merge: the PR is squash-merged under D-100, and the issue is closed (by `Closes #N`).

## Development setup

Follow [`docs/development.md`](docs/development.md) §5.1 to go from a fresh clone to the app on an emulator or
simulator. The guide also covers the Flet pin and its bumps, hot reload with the companion client, builds, signing,
the mock server and CI. The test strategy is [`docs/testing-and-quality.md`](docs/testing-and-quality.md).

Once per clone, turn on the pre-push hook (D-273), which every worktree of the clone shares:
`git config core.hooksPath .githooks`.
