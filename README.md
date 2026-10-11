# PyCon US 2027 app on Flet: planning folder

This folder holds the plan for rewriting the official PyCon US mobile app (Ionic 8 / Angular 17 / Capacitor 7) in Python with Flet. The rewrite would ship as version 27.0.0 of the PSF's existing App Store and Play listings, at full data parity with the 2026 app, and be presented at PyCon US 2027. Why now: the PSF has said it will rewrite the app for 2027 and asked for help, and Ionic's Appflow, which the current app uses for live updates, shuts down on 2027-12-31. For the PSF, the stack would be Python end to end, next to its Django backend. For Flet, every native gap becomes public Apache-2.0 upstream work. Owner: U, a Flet core maintainer. Status: plan of record, 2026-10-11.

## How to read it

Start with **[`PLAN.md`](PLAN.md)**. It covers the pitch, goals and success criteria, scope tiers, architecture decisions, the Flet gap register, milestones and gates, quality, release, PSF asks, the talk, risks and open decisions. Then use the companion docs:

| Doc | Read it for |
|---|---|
| [`docs/decisions.md`](docs/decisions.md) | The binding decisions record (D-01..D-136), naming conventions (section M) and verified Flet SDK facts (section N). Amend it before any doc diverges. |
| [`docs/feature-matrix.md`](docs/feature-matrix.md) | All 263 Ionic feature ids, each with its disposition, milestone, Flet approach, dependencies and gotchas. It is the source of truth for dispositions. |
| [`docs/architecture.md`](docs/architecture.md) | How to build it: modules, the route tree, stores, the data pipeline, the API client and outbox, staff tools, theming, capabilities and schemas. |
| [`docs/flet-gaps-and-extensions.md`](docs/flet-gaps-and-extensions.md) | Specs for the extensions E1-E6 and the core/CLI items U1-U15: interims, target APIs, versions, tests and upgrade steps. |
| [`docs/build-and-release.md`](docs/build-and-release.md) | `pyproject.toml`, versioning, CI workflows, signing, the release train, runbooks, content hosting and the dev loop. |
| [`docs/testing-and-quality.md`](docs/testing-and-quality.md) | Test layers and harnesses, `feature_trace`, goldens, the device lab, Badge Days, accessibility, performance, and the G4/G5 gates. |
| [`docs/backlog.md`](docs/backlog.md) | Every id with tier, owner, estimate and milestone, plus capacity by milestone, T2/T3 items, PSF asks and the burn-down. |
| [`docs/research/`](docs/research/) | Inputs: Ionic inventories (`ionic/`), Flet capability reports (`flet/`) and dates, PSF and ecosystem context (`context-and-ecosystem.md`). |

External dates are marked **confirmed** or **UNCONFIRMED**; unmarked dates are plan targets. `excluded/` holds the upstream Ionic app, cloned for reference only. It is not part of this plan.

## Key dates

From PLAN.md (sections 1, 7 and 11).

| Milestone | Date |
|---|---|
| Proposal email to PSF infrastructure | 2026-10-16 |
| G1: PSF agreement in principle | 2026-11-13 |
| Track decision (store track or community track) | 2026-12-04 |
| CFP: talk and poster submitted | 2026-12-11 (CFP expected to close ~2026-12-18, UNCONFIRMED) |
| Feature freeze (G4) | 2027-03-31 |
| Store submission | 2027-04-16 (fallback 2027-04-23) |
| Public release | 2027-04-27 target, 2027-04-30 at the latest |
| PyCon US 2027, Long Beach, CA | 2027-05-12 to 05-18 (confirmed; the per-day split is UNCONFIRMED) |
