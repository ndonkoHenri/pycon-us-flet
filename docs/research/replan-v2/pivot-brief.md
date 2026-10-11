# Pivot brief (2026-10-11): binding input for the v2 re-plan

The v1 plan (PLAN.md + docs/*.md, snapshot in ../v1/) was written to pitch the port to the PSF as its official 2027 app.
The owner (a Flet core maintainer, "U") has changed direction. Everything below overrides v1.

## A. The owner's direction (authoritative)

1. **Purpose.** This is mainly for us and for the Flet and Python communities: show what Python + Flet can do.
   Building to the quality of the PSF's official app is the bar we hold ourselves to, **not a dependency**.
   We will **not contact the PSF** now. Maybe once the app is done and we are satisfied (or not).
2. **Pace.** Work starts now (October 2026) and continues steadily: step by step, done well, as fast as is
   compatible with quality. Presenting the app at PyCon US 2027 (Long Beach, 2027-05-12..18) is the objective,
   **not a blocking constraint**. Nothing is rushed.
3. **Platforms.** **Android and iOS only.** No web, PWA, desktop or other targets for now.
4. **Not a 1:1 port.** The Ionic app is the functional reference, not the design spec. Wherever we can give a
   better UX/UI (flows, information architecture, visual design, accessibility, offline behaviour), we do.
5. **Material only.** Material 3 on both platforms, identical UI on Android and iOS. No Cupertino or adaptive
   variants at first (consistency).
6. **Zen of Python.** Clean, simple, readable, maintainable, sufficiently documented code. Prefer the obvious
   way; avoid cleverness and speculative machinery. Explicit is better than implicit; flat is better than nested;
   if the implementation is hard to explain, it's a bad idea.
7. **Process.** A private GitHub repo now (public later). Work is tracked in issues and PRs (maybe a GitHub
   Project). The workflow will be written down in AGENTS.md.

## B. Consequences and proposed defaults (apply these; ones marked OPEN are listed as open decisions)

1. **No PSF dependencies.** Remove from the plan as dependencies: the PSF deliverables table (P1-P13), the G1 and
   store/community "Track" gates, PSF-held secrets and release environments, shipping as 27.0.0 of the PSF store
   listings (`org.pycon.us.2023.onsite`, `org.pycon.us`), Badge Days with PSF staff, Linear, outreach emails,
   PSF on-call. Keep at most a short appendix "If we later approach the PSF" (what we would offer and need).
2. **Real data = the public feed only.** `https://us.pycon.org/{YEAR}/schedule/conference.json` (2026 today, 2027
   when published) is the only real backend. The year and feed URL are configuration, not code.
3. **Private-API features are built against a local mock.** Login, favourites sync (`mobile_state`), role flags
   (`check_features`) and the staff tools (lead retrieval, door check, swag pickup, CoC capture) use the private
   PSF `/api/v1`. We implement them faithfully against a local mock server that implements the contract inferred
   from the Ionic client (`pycon-api.ts`, including the sha1 request signing), and **never call the private PSF
   endpoints without permission**. Staff tools stay in scope (they are the best showcase for the barcode-scanner
   extension) but come in a later phase. Favourites work locally without an account.
4. **Distribution (OPEN).** Development builds on our own devices (Android APK/AAB sideload or Play internal
   testing on the owner's account; iOS via the owner's Apple developer account, TestFlight internal). No public
   store listing for now: "PyCon" is a PSF trademark, so a public listing would need PSF permission. Bundle id is a
   placeholder (`<owner-reverse-domain>.pyconus`) until decided.
5. **Simplify server-side machinery.** v1 replaced Appflow OTA with remote `app-config.json`/`app-content.json`
   hosting, kill switches and version gates. Without a store listing and the PSF, prefer the simplest thing:
   year-specific content (keynotes, reminder table, Wi-Fi, booth geometry, room pins, URLs...) ships as
   **bundled, schema-checked data files** per conference year. Remote config can return later if ever needed.
6. **No analytics. No crash-reporting service at first** (local logging; an opt-in reporter can come later).
7. **Notifications.** Without the PSF's Firebase project and a sender, FCM push has no value for the app now
   (flet-firebase can still be a Flet contribution later, low priority). **Local scheduled reminders** (for
   favourited sessions and fixed event times) are server-free and high value: prioritise them (the official
   flet-dev/flet#6948 local-notifications effort plus scheduling).
8. **Theming.** Material 3 with the PyCon brand palette, light and dark, identical on both platforms (drop the
   iOS `#000` vs Android `#121212` split). High-contrast light/dark variants stay as an accessibility feature if
   they fit cleanly into Material colour schemes.
9. **Flet gaps stay capability-gated, simply.** Every gap ships an interim and upgrades when its Flet piece lands
   (barcode scanner E1, scheduled notifications E3, add-to-calendar E4, RefreshIndicator U1, ...). Keep the
   gating mechanism as small as possible while still correct (e.g. the companion app used by `flet run --android`
   must not receive controls it lacks).
10. **Dev loop.** `flet run --android/--ios` (companion app) and `flet build`/`flet debug` on devices. A desktop
    window may be used **only as a developer convenience/test host** (e.g. Flet's host-mode tests), never as a
    shipped target, and the UI is designed for phones (and works on tablets).
11. **Testing.** Keep strong tests where they protect correctness (feed processing, time zones, signing, outbox),
    but choose the simplest effective tools; cut process that only made sense for the PSF (Badge Days with PSF
    staff, release ledgers for PSF listings, contract tests against private staging).
12. **Phases, not deadlines.** Order the work in phases with exit criteria. Soft markers only: an attendee-core
    build worth demoing by about the end of November 2026 (useful if we decide to submit a PyCon CFP proposal,
    expected to close around 2026-12-18, OPEN); a complete, polished app well before May 2027.
13. **Upstream Flet work continues.** The owner contributes the missing pieces to Flet (extensions in flet-dev,
    core controls, flet-cli fixes such as the open PR flet-dev/flet#6953 for deep-linking fallback).

## C. Disposition vocabulary for v2 (replaces port/adapt/interim->upgrade/defer/drop)

- **keep**: same behaviour and purpose (copy/data rules preserved).
- **improve**: same purpose, better UX/UI or behaviour (say what improves).
- **redesign**: the flow/screen is rethought (say how).
- **mock**: needs the private PSF API; built and tested against the local mock server.
- **interim**: ships a fallback now, upgrades automatically when a named Flet piece lands.
- **later**: deliberately in a later phase than its natural one (say why).
- **drop**: not doing it (say why; e.g. web-only, PSF-only, Appflow).

Every id also gets a **phase** (P0..P4 or "later") and may combine e.g. "improve + interim".
