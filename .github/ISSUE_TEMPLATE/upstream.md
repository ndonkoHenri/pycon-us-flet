---
name: Upstream
about: Write up a missing Flet capability for the owner to take upstream (D-97, D-212).
title: "Upstream: "
labels: upstream
---

<!--
Title: "Upstream: <capability> (<U-id or E-id>)", e.g. "Upstream: RefreshIndicator in Flet core (U1)".
Agents never post in flet-dev or any other repository (D-212): this issue holds the full analysis, and the owner
decides whether to take it to Flet; it links the flet-dev issue or PR once the owner has opened one. Add exactly one `area:*` label,
the milestone of the phase that needs it (none if the need is "later") and `--project "PyCon US Flet"`.
App issues that wait on it get `blocked` and a link here. See docs/flet-gaps-and-extensions.md.
-->

## Context

- **Upstream id:** <!-- U1..U20 or E1..E6 (docs/flet-gaps-and-extensions.md) -->
- **flet-dev link:** <!-- added once the owner has opened one; agents never open it (D-212) -->
- **Decisions:** <!-- e.g. D-97, D-98 -->

## What Flet lacks

<!-- What happens, the Flet source at the pin (files and lines), a minimal repro, the suggested fix. -->

## Interim in the app

<!-- What ships meanwhile (docs/flet-gaps-and-extensions.md), and the app issues blocked on this. -->

## Acceptance criteria

- [ ] The flet-dev issue or PR is merged, or its status is recorded here.
- [ ] An app issue exists for replacing the interim after the Flet pin bump (D-64).

## How to verify

<!--
Link the merged flet-dev PR (or the extension release) and the Flet commit or version that contains it, and
link the app issue that replaces the interim after the pin bump.
-->
