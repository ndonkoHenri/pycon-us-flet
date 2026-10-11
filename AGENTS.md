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
  - **Reversible choices** don't wait for the owner. Post the decision as a comment on the issue, merge the PR
    that records it, mention it in the phase status issue, then remove the `needs-decision` label. The owner can
    override later.
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

### Pull requests

- **One issue, one PR** (`Closes #14` in the body). Aim for at most about 400 changed lines, not counting fixtures
  or generated files; split bigger work.
- Open a **draft PR** early for anything that takes more than a session, so progress is visible; mark it ready
  when it meets the definition of done.
- The PR template asks for: what and why, how it was tested (commands, devices), screenshots or recordings for UI
  changes (Android emulator **and** iOS simulator, light and dark when relevant), docs and decision updates, and
  follow-ups.
- CI must be green.

### Reviews and merging

- **Agents merge their own PRs** (D-100). The owner watches and can step in at any time, but is never a blocker:
  don't wait for approval. Merge only when all of these hold:
  1. **Checks pass on the PR's latest commit.** Once CI exists, every check must be green: missing, pending,
     skipped or cancelled checks don't count. Until then (P0-02), run the checks that apply locally and list them
     in the PR.
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
  5. **No open `needs-decision` question** affects the PR.
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
  Done); group or filter it by milestone (the phase) and by `area:*` label (D-90, D-94). Issues and PRs from this
  repo are added automatically. The issue is the source of truth; the board is a view of it.
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
- [ ] Runs on Android and iOS (for UI or native changes), with screenshots in the PR.
- [ ] Accessible: labels, contrast, text scaling, touch targets (`docs/ux.md` checklist).
- [ ] Docs and `docs/decisions.md` updated when behaviour or decisions changed.
- [ ] Follow-ups have their own issues.

After the merge: the PR is squash-merged under D-100, and the issue is closed (by `Closes #N`).

## Development setup

See [`docs/development.md`](docs/development.md): the Flet pin, uv, running on devices, the mock server, builds and
CI. The test strategy is [`docs/testing-and-quality.md`](docs/testing-and-quality.md). P0-05 completes the guide from
spike S5's verdict.
