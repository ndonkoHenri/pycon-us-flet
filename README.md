# Conf Companion

A conference companion for PyCon US on Android and iOS, written in Python with [Flet](https://flet.dev).
**Not an official PSF app.**

It is a community project that shows the Flet and Python communities what a full mobile app in Python can be. The
[official PyCon US app](https://github.com/PyCon/pycon-us-mobile) is our functional reference and quality bar, but
this is not a 1:1 port: where its UX, accessibility or offline behaviour can improve, ours does.

## What the app does

- **Now, Schedule, My schedule, Map and More** are the five tabs. The app opens on Now, which shows what is on and
  your next session.
- **Your own plan:** save sessions, see where they overlap and get reminders.
- **Finding your way:** search across the conference, floor plans with room pins, and pages for speakers, sponsors,
  open spaces, sprints, job listings and the venue.
- **Offline from the first launch:** a snapshot of the public conference feed ships inside the app, and the app shows
  how fresh its data is.
- **One design:** Material 3, the same on both platforms, with light, dark and high-contrast schemes.
- **Accounts and staff tools:** sign-in, favourites sync, lead retrieval, door check, swag pickup and Code of Conduct
  capture run against [our local mock server](tools/mock_api/README.md), not PyCon's servers.

## Status

The app is under active development and has no public builds. To try it, build it from source. It carries the 2026
conference data until the 2027 feed is published.

- **P0 Foundations and P1 Attendee core** are done.
- **P2 Conference companion** is built; what remains is mainly its exit checks on devices, and pull to refresh, which
  waits on a fix in Flet.
- **P3 Accounts & staff tools** is built against the mock, at version 0.4.0. What remains is the scanner's camera
  preview, which waits on a barcode-scanner extension for Flet. Until then, badge codes are typed in.
- **P4 Showcase** is what comes next: the performance pass, the accessibility audit, a View source action on each
  screen, the 2027 data and the licence and trademark review. The repository is private for now, and making it public
  is part of this phase.

The objective is to present the app at PyCon US 2027. GitHub issues hold the live task list;
[`docs/roadmap.md`](docs/roadmap.md) describes the phases.

## What it isn't

- **It is not an official app.** The Python Software Foundation (PSF) and the PyCon US organisers don't make or endorse
  it. For the official app, see the link above.
- **It doesn't talk to the PSF's private API.** Conference data comes from the public feed. Everything that would need
  the private API uses the mock server instead, so real PyCon accounts don't work here.
- **It is for phones and tablets only.** There are no web or desktop versions, and a desktop window is only a
  convenience for development.

## Why Flet

Flet lets you write a mobile interface in Python: Flutter draws the screen, and the Python runtime ships inside the
app. That gives one codebase for both platforms, in a language many developers at PyCon can read and change.

The app is also a test of Flet. When it needs something Flet lacks, we ship a documented interim and record the gap in
[`docs/flet-gaps-and-extensions.md`](docs/flet-gaps-and-extensions.md). The project's owner maintains Flet.

## Screenshots

None yet: they wait for a stable UI.

## Accessibility

These rules apply to every screen, and every UI change goes through the
[checklist in `docs/ux.md`](docs/ux.md#9-accessibility-checklist-every-ui-pr-d-33-d-93):

- **Screen readers:** controls have a name, role and state, a row reads as one phrase with its star as a separate stop,
  and headings have levels.
- **Touch:** targets are at least 48 dp, and gestures have a button alternative, such as the zoom buttons on maps, a
  list view of the expo hall and typed badge codes.
- **Contrast:** AA in the light and dark schemes, and 7:1 for text in high contrast, which follows the OS or a switch in
  Settings. Tests check the colour pairs the theme declares.
- **Large text:** layouts are built to reflow at 200 % text size, without fixed heights around text.
- **Motion:** the app honours the OS's reduced-motion setting.
- **Colour:** it is never the only signal; badges have text, and outcomes have an icon and a word.

Some flows have been checked with TalkBack on an Android emulator. VoiceOver needs a real iPhone, and that check is
still to come. The full audit of every screen hasn't run yet either; its results will be here when it has. Limits that
come from Flet are listed in [`docs/flet-gaps-and-extensions.md`](docs/flet-gaps-and-extensions.md).

## Running it

[`docs/development.md`, section 5.1](docs/development.md#51-from-a-clean-mac) goes from a clean checkout to the
app on an emulator or simulator. You need git and [uv](https://docs.astral.sh/uv/); Android also needs an emulator or a
phone, and iOS needs a Mac with Xcode. The tests need no device. While the repository is private, cloning it needs
access to it.

## Contributing and docs

- [`CONTRIBUTING.md`](CONTRIBUTING.md): how to set up, find an issue and send a PR.
- [`AGENTS.md`](AGENTS.md): how we work, for humans and AI agents: issues, branches, reviews and the definition of done.
- [`PLAN.md`](PLAN.md): the vision, scope, phases and risks.

| Doc | What it holds |
|---|---|
| [`docs/ux.md`](docs/ux.md) | The UX and UI spec: navigation, design system, every screen, accessibility |
| [`docs/architecture.md`](docs/architecture.md) | Modules, routing, state, the data pipeline, the mock API |
| [`docs/flet-gaps-and-extensions.md`](docs/flet-gaps-and-extensions.md) | What Flet lacks, the interim we ship, and the upstream work |
| [`docs/development.md`](docs/development.md) | Toolchain and Flet pin, dev loop, mock server, builds, checks, signing |
| [`docs/testing-and-quality.md`](docs/testing-and-quality.md) | Test strategy, UI flows, device checklist, performance |
| [`docs/roadmap.md`](docs/roadmap.md) | The phases broken into epics and issues |
| [`docs/demo-script.md`](docs/demo-script.md) | The stage demo, a draft: its beats, timings and fallbacks, with no Wi-Fi |
| [`docs/feature-matrix.md`](docs/feature-matrix.md) | Every feature of the official app, plus ours: what we do with it, and in which phase |
| [`docs/decisions.md`](docs/decisions.md) | The binding decisions (D-numbers) and verified Flet facts. It is large, so search it by id |
| [`docs/spikes/`](docs/spikes/) | The verdicts of our technical spikes |
| [`docs/research/`](docs/research/) | The frozen analysis of the official app and of Flet's capabilities |

## Licence

[Apache-2.0](LICENSE), the same as the official app. [`NOTICE`](NOTICE) credits that app and lists the third-party
assets we use.

"PyCon" and "Python" are trademarks of the Python Software Foundation, and the licence grants no rights to them. We use
the names only to say which event and language this is about; the app's name and icon use no PSF mark.
