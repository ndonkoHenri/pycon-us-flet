# AGENTS.md

How we build this app: for the humans and the AI agents (Claude Code, Codex, ...) who work on it.
Claude Code reads it through `CLAUDE.md`, which contains only `@AGENTS.md`.

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
2. [`docs/decisions.md`](docs/decisions.md): **binding** decisions (D-ids), naming, verified Flet facts.
3. The doc for your area: [`docs/ux.md`](docs/ux.md), [`docs/architecture.md`](docs/architecture.md),
   [`docs/flet-gaps-and-extensions.md`](docs/flet-gaps-and-extensions.md),
   [`docs/development.md`](docs/development.md), [`docs/testing-and-quality.md`](docs/testing-and-quality.md).
4. [`docs/feature-matrix.md`](docs/feature-matrix.md) for what a feature id means and its gotchas;
   [`docs/roadmap.md`](docs/roadmap.md) for the phases. GitHub issues are the live task list.
5. `docs/research/` holds the raw analysis of the original app. `excluded/` holds a read-only clone of it
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
  - **Reversible choices** don't wait for the owner. The question is **settled** once you post the decision as a
    comment on the issue; then record it as a D-number in a PR, mention it in the phase status issue, and remove
    the `needs-decision` label. The owner can override later.
  - **Owner-only choices** wait for the owner: app identity and bundle id; making anything public (the repo, a
    store listing, builds for people outside the team); accounts or anything that costs money; contacting people
    outside this work (the PSF, social media, blogs); and anything that would lose data or need someone else's
    help to undo. Routine work is already authorised: issues, PRs and comments in this repo, and the flet-dev
    issues and PRs the upstream track needs.
- Docs live next to the code they describe and change in the **same PR** as the behaviour.
- `docs/feature-matrix.md` is the source of truth for feature dispositions; edit it directly.
- Code documentation: every module starts with a docstring saying what it is for; every public function and class
  has a docstring (Google style); comments explain **why**, not what.

## Working with Flet

- The owner maintains Flet. Until Flet 1.1.0 is on PyPI we build against a pinned flet-dev/flet commit: the
  `.flet-src` checkout at the SHA in `.flet-ref` (D-81, `docs/development.md` §2.2). That checkout is the source of
  truth for Flet APIs: check controls, properties and signatures there (or by introspection) instead of trusting
  memory or old docs.
- Declarative style: `@ft.component`, hooks, `@ft.observable` stores, `ft.Router`. Follow the rules in
  `docs/decisions.md` D-70 (async APIs only from `async def` handlers; `use_effect` setups are coroutine
  functions with sync cleanups; one context per observable store; no conditional hooks).
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
- **`main` is protected by convention** (D-88): every change reaches it through a squash-merged PR, and nobody
  pushes, force-pushes to or deletes `main`. GitHub can't enforce this yet: creating a ruleset on this private
  repo on GitHub Free fails with `Upgrade to GitHub Pro or make this repository public to enable this feature.
  (HTTP 403)` (tried 2026-10-11). When the repo goes public (P4), add a ruleset on the default branch that
  requires a PR, blocks force pushes and deletion, and requires **no** approvals, so agents can still merge
  their own PRs (D-100).

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
- CI must be green.
- **Screenshots** (D-162): `gh` can't upload images, so they go to the orphan branch `pr-assets`, one folder per PR,
  and the PR embeds them:
  ```sh
  git fetch origin pr-assets && git worktree add --detach <scratch>/pr-assets origin/pr-assets
  cd <scratch>/pr-assets && mkdir -p <pr> && cp <shots>.png <pr>/ && sips -Z 1000 <pr>/*.png   # downscale
  git add <pr> && git commit -m "Add screenshots for #<pr>"
  git push origin HEAD:pr-assets || { git pull --rebase origin pr-assets && git push origin HEAD:pr-assets; }
  cd - && git worktree remove <scratch>/pr-assets
  ```
  Work detached (as above), so parallel agents never fight over a checked-out branch. Then write
  `![Android, light](https://github.com/ndonkoHenri/pycon-us-flet/blob/pr-assets/<pr>/<file>.png?raw=true)` in the PR
  body or a comment.

### Reviews and merging

- **Agents merge their own PRs** (D-100). The owner watches and can step in at any time, but is never a blocker:
  don't wait for approval. Merge only when all of these hold:
  1. **Checks pass on the PR's latest commit.** Once CI exists, every check must be green: missing, pending,
     skipped or cancelled checks don't count (the required checks are the `ci.yml` jobs listed in
     `docs/development.md`). Until CI exists (P0-02), run the checks that apply locally and list them in the PR.
  2. **The definition of done is met**, and you have re-read the whole final diff yourself.
  3. **A second opinion, when required.** It is required when the PR changes more than 400 lines (not counting
     lockfiles, fixtures, generated files or data snapshots), changes the architecture (module structure, state,
     routing, the data core, signing, the outbox, build or CI), or edits `docs/decisions.md`. The reviewer is a
     **different model** from the author (Claude Fable, or Codex run read-only) and reviews the final diff; re-run
     it after substantive changes. Each finding is fixed, or rejected in a PR comment with the reason and
     evidence. If you still disagree on something that matters (correctness, data loss, security), ask the other
     reviewer model; if it's a product question, use `needs-decision`.
  4. **The owner is heard.** A request from the owner to stop or change something is acted on, not just
     acknowledged; every owner comment has a reply.
  5. **No unsettled `needs-decision` question** affects the PR.
- **A Copilot review** (D-103). On every PR that changes code or configuration, request one right after opening
  it: `gh pr edit <n> --add-reviewer @copilot`. It arrives in about 5 to 15 minutes as a review by
  `copilot-pull-request-reviewer[bot]`, with inline comments by `Copilot`. Handle its comments before merging, like
  any reviewer's: fix, or reply on the thread with the reason and evidence. If nothing has arrived after about 20
  minutes, or the review only says the Copilot quota is used up, say so in the PR and go on. It never replaces the
  second opinion above.
- Merge with `gh pr merge <n> --squash --delete-branch` (the PR title becomes the commit on `main`).
- The owner may comment, request changes or revert at any time. Feedback that arrives after a merge becomes a new
  issue, or a revert PR when something is broken.

### Upstream Flet work

- When the app needs something Flet lacks, open (or link) the issue or PR in `flet-dev/flet` (or the extension's
  repo). Track it here with an `upstream` issue that links it.
- App issues that wait on it get `blocked` plus a link; meanwhile the interim from
  `docs/flet-gaps-and-extensions.md` ships.

### Project board

- A GitHub Project ("PyCon US Flet") gives the overview with one Status field (Todo, In progress, In review,
  Done); group or filter it by milestone (the phase) and by `area:*` label (D-90, D-94). The issue is the source
  of truth; the board is a view of it.
- **The Project's built-in workflows do most of the bookkeeping.** The owner turned them on in the web UI
  (the API can't; #118): open issues and PRs are auto-added, "Item added" sets Todo, "Pull request linked to
  issue" sets In progress, "Item closed" and "Pull request merged" set Done, "Auto-close issue" closes an issue
  set to Done, and "Item reopened" sets Todo. Still pass `--project "PyCon US Flet"` when you create an issue
  or PR, so it's on the board at once; adding twice is harmless.
- **Set two statuses yourself**, on the issue and on its PR: In progress when you start, and In review when the
  PR is ready (no workflow sets In review). `gh` needs the `project` scope (`gh auth refresh -s project`). The
  ids below are stable; if the Project is ever rebuilt, look them up again with the first two commands.

  ```sh
  gh project view 2 --owner ndonkoHenri --format json --jq .id   # project id
  gh project field-list 2 --owner ndonkoHenri --format json \
    --jq '.fields[] | select(.name == "Status") | {id, options}'   # Status field id and option ids
  # The item id of an issue or PR (adds it to the Project if it isn't there yet):
  item=$(gh project item-add 2 --owner ndonkoHenri --format json --jq .id \
    --url https://github.com/ndonkoHenri/pycon-us-flet/issues/<n>)   # or .../pull/<n>
  gh project item-edit --project-id PVT_kwHOBeZJHs4BmmHp --id "$item" \
    --field-id PVTSSF_lAHOBeZJHs4BmmHpzhlOeUE --single-select-option-id <option id>
  ```

  | Status | Option id |
  |---|---|
  | Todo | `876879f0` |
  | In progress | `921d2845` |
  | In review | `0361c618` |
  | Done | `40195126` |
- Each phase has a pinned status issue (`P0 status`, ...). Post a short weekly update there: done, next, blocked,
  decisions needed.

## Rules for AI agents

1. Before starting: read this file, `PLAN.md`, `docs/decisions.md` and the docs for your area; read the issue and
   its parent epic.
2. Say you're on it: comment on the issue with a short plan when the work is non-trivial, and open a draft PR
   early so progress is visible.
3. Work on the issue branch; keep the PR scoped to the issue. Found something else? Open a new issue instead of
   widening the PR.
4. Verify for real: run the tests and linters, and for UI work run the app (emulator, simulator or device). Say
   exactly what you ran and what you saw; never claim a check you didn't do.
5. Don't guess silently on product or architecture questions: use `needs-decision` and the decision rules
   (D-101). Decide the reversible ones yourself and record them; wait only for the owner-only kinds.
6. Sign your work: agents act through the owner's GitHub account, so end every PR description and issue comment
   you write with `_Written by <agent name> (AI agent)._`, so the history shows who did the work.
7. Never call private PSF endpoints, commit secrets or edit `excluded/`.

## Definition of done

- [ ] Acceptance criteria of the issue met.
- [ ] Tests added or updated, all passing; linters clean.
- [ ] Runs on an Android emulator and an iOS simulator (for UI or native changes), with screenshots in the PR; the
  owner's iPhone only for checks that need hardware or a release build (D-102).
- [ ] Accessible: labels, contrast, text scaling, touch targets (`docs/ux.md` checklist).
- [ ] Docs and `docs/decisions.md` updated when behaviour or decisions changed.
- [ ] Follow-ups have their own issues.

After the merge: the PR is squash-merged under D-100, and the issue is closed (by `Closes #N`).

## Development setup

Follow [`docs/development.md`](docs/development.md) §5.1 to go from a fresh clone to the app on an emulator or
simulator. The guide also covers the Flet pin and its bumps, hot reload with the companion client, builds, signing,
the mock server and CI. The test strategy is [`docs/testing-and-quality.md`](docs/testing-and-quality.md).
