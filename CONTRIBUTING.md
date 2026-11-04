# Contributing

Thanks for helping. This is a community rebuild of the PyCon US mobile app in Python with [Flet](https://flet.dev),
for Android and iOS. **It is not an official PSF app**: the Python Software Foundation and the PyCon US team don't run
or support it, so please report its bugs here and not to them.

**No CLA or DCO** (D-87). The project is Apache-2.0, and GitHub's terms make your contribution Apache-2.0 too. You
don't need to sign anything or add a sign-off line.

## Read this first, and no more

The docs are large: `docs/decisions.md` alone is over 900 KB. Don't read them through. Before your first PR, read:

1. [`README.md`](README.md): what the project is.
2. [`docs/development.md` §5.1](docs/development.md#51-from-a-clean-mac): setup.
3. [`AGENTS.md`](AGENTS.md), two short sections: [Principles](AGENTS.md#principles) and
   [Working with Flet](AGENTS.md#working-with-flet).
4. Six decisions, a few KB in all: non-goals (D-08), code style (D-66), Flet rules (D-70), pull requests (D-92),
   definition of done (D-93) and test docstrings (D-253). This prints them:

   ```sh
   grep -E '^\| D-(08|66|70|92|93|253) \|' docs/decisions.md
   ```

Then read only what your issue cites, and look up the rest when you need it.

## Look things up

Decisions are binding, and the docs cite them by id. Each one is a single table row, so `grep` finds it. Pasting
into zsh, macOS's default shell, run `setopt interactivecomments` first, or `#` doesn't start a comment
([§5.1](docs/development.md#51-from-a-clean-mac)):

```sh
# One decision (ids below 10 are D-01, D-02, ...)
grep '^| D-87 |' docs/decisions.md
# What else mentions it
grep -n 'D-87\b' docs/decisions.md | cut -c1-160
# A topic
grep -n -i 'favourites' docs/decisions.md | cut -c1-160
# A verified Flet fact
grep '^| F2 |' docs/decisions.md
# A feature id
grep -n 'INFO-03' docs/feature-matrix.md | cut -c1-160
# A doc's table of contents
grep -n '^#' docs/ux.md
```

A row's first words say when a later decision amends it; a struck-through part no longer applies.

| When you work on | Look in |
|---|---|
| Screens and interaction | [`docs/ux.md`](docs/ux.md), and its [accessibility checklist](docs/ux.md#9-accessibility-checklist-every-ui-pr-d-33-d-93) |
| Modules, state, routing, data | [`docs/architecture.md`](docs/architecture.md) |
| Something Flet lacks | [`docs/flet-gaps-and-extensions.md`](docs/flet-gaps-and-extensions.md) |
| Tests | [`docs/testing-and-quality.md`](docs/testing-and-quality.md) |
| Devices, hot reload, the mock server | [`docs/development.md`](docs/development.md) §5 and §6 |

## Set up

Fork the repo, then follow [`docs/development.md` §5.1](docs/development.md#51-from-a-clean-mac) with your fork in
place of its first line:

```sh
gh repo fork ndonkoHenri/pycon-us-flet --clone && cd pycon-us-flet
```

You need git and [uv](https://docs.astral.sh/uv/); without `gh`, fork on GitHub and `git clone` your fork. The checks
need no device. To run the app you need an Android emulator or phone, or a Mac with Xcode for iOS. No Mac is fine:
say so in your PR, and a maintainer checks iOS.

## Find something to work on

- Look at the [`good first issue`](https://github.com/ndonkoHenri/pycon-us-flet/labels/good%20first%20issue) label.
  Skip issues labelled `blocked`, `needs-decision` or `epic`.
- Comment on the issue before you start, so nobody duplicates your work.
- Every change starts from an issue, except trivial chores such as a typo. To propose something new, use a
  [template](.github/ISSUE_TEMPLATE/). Check D-08 first: web, desktop, Cupertino and push notifications are non-goals.
- To change a decision, a UX flow or the architecture, open an issue with the options and your recommendation
  before you write code. Maintainers settle it and record it.
- If Flet lacks something, open an `upstream` issue here ([Upstream Flet work](AGENTS.md#upstream-flet-work)). Don't
  edit `.flet-src`, and don't work around the gap with a hack.

## Run the checks

In zsh, the same `setopt interactivecomments` comes first:

```sh
# The full checks: lockfile, ruff, formatting, pyright, pytest
tools/check.sh
# The same without pytest; the pre-push hook runs this
tools/check.sh --fast
# One test file, while you work
uv run pytest tests/test_about.py
```

The pre-push hook is the `git config core.hooksPath .githooks` line in §5.1. `tools/check.sh` also runs the pre-commit
hooks of `.pre-commit-config.yaml` (file hygiene, `actionlint`, and a check that Python comments and docstrings use single
backticks, not reST's double ones). To run them on every commit too, `git config hooks.precommit true` (D-479). Run the full
checks before you ask for a review. [`docs/development.md` §7](docs/development.md#7-checks-and-github-actions-d-84-d-273) has the details.

## Branches and commits

- **Branch:** `<type>/<issue>-<slug>`, such as `feature/14-schedule-day-tabs` or `bug/31-timezone-day-bucket`. The
  type is the issue's type label.
- **Commit:** an imperative subject of 72 characters or fewer ("Add schedule day tabs"), a body that says why when
  it isn't obvious, and the issue reference (`Refs #14`).
- More in [Branches and commits](AGENTS.md#branches-and-commits).

## Pull requests

- One issue, one PR, with `Closes #14` in the body and about 400 changed lines at most. Fill in the sections of the
  PR template, and say what you ran and what you saw.
- Include tests, and docs in the same PR as the behaviour they describe. Every module, public function and test has
  a docstring. The whole bar is the [definition of done](AGENTS.md#definition-of-done).
- Open it as a draft if it will take a while. A maintainer adds labels and the milestone.
- `Lint, types and tests` must be green on your latest commit. GitHub runs it on every PR, and a maintainer may need
  to approve the first run from a new contributor.
- We squash-merge, and the PR's title becomes the commit on `main`, so write it like a commit subject.

## Screenshots

UI changes need them: Android emulator and iOS simulator, light and dark when relevant. From a fork, drag the images
into the PR on GitHub. Look at each one first: no tokens, personal data, notifications or real badges, because it all
stays public. Use only the images the PR needs.

## Where AGENTS.md doesn't apply to you

[`AGENTS.md`](AGENTS.md) is the full manual, for people and AI agents, and much of the work here is done by agents
through the owner's account. Their comments end with a signature line saying so. These parts are for them and the
maintainers, not for you:

| In AGENTS.md | For you |
|---|---|
| [Read first](AGENTS.md#read-first) (`PLAN.md`, the decisions for your area, the area's docs) | The short list above is enough. |
| [Rules for AI agents](AGENTS.md#rules-for-ai-agents), including the signature line and acting only in this repository (D-212) | Doesn't apply. You can take part in Flet's own repositories as you like. |
| [Reviews and merging](AGENTS.md#reviews-and-merging): the merge gate, second opinions, agents merging their own PRs | Maintainers do this. You get a review and a merge, or a reason. |
| [Project board](AGENTS.md#project-board), and settling decisions in `docs/decisions.md` | Maintainers do this. |
| [Screenshots](AGENTS.md#pull-requests) on the `pr-assets` branch | It needs write access. Use the PR instead. |
| [`.flet-src` per worktree](AGENTS.md#working-with-flet) and a pub cache of your own | Only for parallel builds. One clone needs just the `.flet-src` that §5.1 sets up, and no pub cache of its own. |

The rest applies to everyone.

## Until the repo is public

This file is written for the public repo. While the repo is private (D-273), GitHub Actions run only by hand, so
`Lint, types and tests` doesn't run on PRs. The local `tools/check.sh` takes its place, and a maintainer runs the
merge gate, `tools/gate.sh`, before every merge. Copilot reviews are paused too. Remove this section when the repo
goes public.
