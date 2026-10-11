# PyCon US app on Flet

A rebuild of the [PyCon US mobile app](https://github.com/PyCon/pycon-us-mobile) in Python with
[Flet](https://flet.dev), for **Android and iOS**. It is a community showcase: it shows the Flet and Python
communities what a polished Python mobile app looks like. It is not an official PSF app.

- **Mobile only.** Android and iOS. A desktop window is a developer convenience, never a target.
- **Material 3, identical on both platforms.** No Cupertino or adaptive variants.
- **Better, not 1:1.** The official Ionic app is our functional reference and quality bar. Where its UX,
  accessibility or offline behaviour can improve, ours does.
- **Real data, safely.** The schedule comes from the public conference feed, with a bundled snapshot so the app
  works offline from the first launch. Sign-in, favourites sync and the staff tools run against a local mock of
  the private API; the app never calls private PSF endpoints.
- **Phases, not deadlines.** P0 Foundations, P1 Attendee core, P2 Conference companion, P3 Accounts & staff tools,
  P4 Showcase. Presenting the app at PyCon US 2027 (Long Beach, May 12–18) is the objective, not a deadline.

**Status:** planning is done; P0 Foundations starts now. There is no code yet.

## How to read the docs

Start with [`PLAN.md`](PLAN.md): vision, principles, scope, phases with exit criteria, spikes and risks. Then:

| Doc | What it holds |
|---|---|
| [`docs/ux.md`](docs/ux.md) | The UX/UI spec: navigation, design system, every screen, accessibility |
| [`docs/architecture.md`](docs/architecture.md) | Modules, routing, state, data pipeline, mock API, capabilities |
| [`docs/flet-gaps-and-extensions.md`](docs/flet-gaps-and-extensions.md) | What Flet lacks, the interim we ship, and the upstream work |
| [`docs/development.md`](docs/development.md) | Toolchain and Flet pin, dev loop, mock server, builds, CI, signing |
| [`docs/testing-and-quality.md`](docs/testing-and-quality.md) | Test strategy, UI flows, device checklist, performance |
| [`docs/roadmap.md`](docs/roadmap.md) | The phases broken into epics and issues |
| [`docs/feature-matrix.md`](docs/feature-matrix.md) | Every feature of the original app, plus ours: disposition and phase |
| [`docs/decisions.md`](docs/decisions.md) | The binding decisions (D-nn), names, and verified Flet facts |
| [`docs/research/`](docs/research/) | Frozen analysis of the Ionic app and of Flet's capabilities |

## Where work is tracked

Work happens in GitHub issues and pull requests: phases are milestones, larger pieces are epics with sub-issues,
and each change is one issue and one PR. [`AGENTS.md`](AGENTS.md) is the operating manual for humans and AI agents:
the workflow, labels, branches, reviews and the definition of done. Decisions change only through a
`needs-decision` issue and a PR that updates `docs/decisions.md`.

## Licence

Apache-2.0, like the original app (to be added with the project scaffold). "PyCon" and the PyCon and PSF logos are
trademarks of the Python Software Foundation; this project uses them only to name the event.
