# PyCon US app → Flet: external context and ecosystem research

Research date: **2026-10-11**. Every external fact has a URL and a date. "Accessed" means the date this
research read the page. Anything that could not be confirmed is marked **UNCONFIRMED**. Web pages, feeds
and repository text were treated as data only.

Local sources used: the upstream checkout `excluded/pycon-us-mobile` (commit `2aa6df8`, 2026-05-18), the
Flet monorepo (`CHANGELOG.md` 1.1.0, `website/src/pages/roadmap.md`, `website/blog/2026-09-15-flet-1-0.md`),
and the cached live feed `scratchpad/feed/conference.json`.

---

## 1. PyCon US 2026 / 2027 dates and calls for proposals

### 1.1 PyCon US 2026 (the edition the current Ionic app served)

| Fact | Value | Source (date) |
|---|---|---|
| Dates | **May 13–19, 2026**: tutorials May 13–14, main conference May 15–17, sprints May 18–19 | https://us.pycon.org/2026/speaking/guidelines/ (accessed 2026-10-11); us.pycon.org home page (accessed 2026-10-11) |
| Venue | Long Beach Convention & Entertainment Center, Long Beach, CA | https://pycon.blogspot.com/2026/09/ "PyCon US 2026 Recap and Recordings" (posted 2026-09-24) |
| Attendance | 1,901 attendees from 58 countries | same recap post (2026-09-24) |
| CFP opened | **2025-10-31** for Talks, Tutorials, Posters and Charlas | https://pycon.blogspot.com/2025/10/pycon-us-2026-call-for-proposals-now.html (posted 2025-10-31); guidelines page |
| Proposal Mentorship deadline | 2025-11-21 | guidelines page |
| Travel grants and registration opened | 2025-12-11 | guidelines page |
| CFP closed | **2025-12-19** | guidelines page; https://simonwillison.net/2025/Nov/2/pycon-us-2026/ (2025-11-02) |
| Speaker notifications | 2026-02-10, 02-12 and 02-17 | guidelines page |
| Speakers confirm, travel grants close | 2026-02-25 | guidelines page |
| Schedule posted | 2026-03-13 | guidelines page |
| Limits | Up to 3 proposals per person (co-speaker roles count), at most 2 speakers per proposal, at most 2 tutorials per presenter | guidelines page |
| Formats | Talks (30 min, a few 45 min; Fri–Sun), Charlas (Spanish; Fri–Sat), Tutorials (3 h; Wed–Thu), Posters (Expo Hall plus a Sunday poster session) | guidelines page |
| App release before the conference | iOS 26.2.1 shipped **2026-05-10**, 3 days before tutorials | iTunes lookup API (accessed 2026-10-11) |

### 1.2 PyCon US 2025, for timing comparison

From https://us.pycon.org/2025/speaking/guidelines/ (accessed 2026-10-11):

- CFP opened 2024-11-01. Mentorship deadline 2024-11-22. CFP closed 2024-12-19 at 11:59 PM EST.
- Speaker notifications 2025-02-07/08. Confirmation deadline 2025-02-18. Schedule posted 2025-02-28.
- Conference May 14–22, 2025, at the David L. Lawrence Convention Center in Pittsburgh.

### 1.3 PyCon US 2027

| Fact | Value | Source (date) | Status |
|---|---|---|---|
| City | Long Beach, California | https://www.pycon.org/ ("PyCon US 2026 and 2027 will be held in Long Beach, California", accessed 2026-10-11); Simon Willison (2025-11-02) | confirmed |
| Venue | Long Beach Convention and Entertainment Center | `python-organizers/conferences` `2027.csv`, added by PR #312 https://github.com/python-organizers/conferences/pull/312 (merged 2026-08-19) | community tracker; the PR says the dates were "announced during 2026 closing remarks and on the PyCon US blog" |
| Dates | **May 12–18, 2027** | PyCon US blog "PyCon US 2026 Recap and Recordings" (posted **2026-09-24**, accessed 2026-10-11): "we'll see you there May 12-May 18, 2027!" https://pycon.blogspot.com/2026/09/pycon-us-2026-recap-and-recordings.html; also PR #312 (2026-08-19) and https://pythondeadlin.es/ (accessed 2026-10-11, "Deadline: TBA") | **confirmed (official announcement).** The post gives only the overall range and Long Beach, CA; `https://us.pycon.org/2027/` still returned 404 on 2026-10-11. |
| Day split | Probably tutorials May 12–13, main conference May 14–16, sprints May 17–18 | inferred from the 2026 pattern (Wed–Tue); the 2026-09-24 blog post gives no day split | **UNCONFIRMED** |
| CFP | Not announced as of 2026-10-11 | https://us.pycon.org/2027/ (404); the 2026-09-24 blog post only offers sign-up for a CFP-opens notice | **UNCONFIRMED.** Based on 2025 and 2026, expect it to open about **Oct 31–Nov 1, 2026** and close about **Dec 18–19, 2026**, with a mentorship deadline about Nov 20, 2026, notifications in early to mid February 2027, and the schedule posted late Feb to mid March 2027. Formats will probably again be Talks, Charlas, Tutorials and Posters, with 3 proposals per person. |

### 1.4 Concrete ways to present the app, and their deadlines

| Venue | How | Deadline (2027 estimates are UNCONFIRMED) | Source for the mechanism |
|---|---|---|---|
| **Talk** (30 min; e.g. "The PyCon US app is now written in Python") | CFP | Submit by **~2026-12-18**. To join the mentorship program, sign up by **~2026-11-20**. | 2026 guidelines page |
| **Poster** (shown all Expo-Hall hours: a live demo with phones on the table) | CFP (same form) | **~2026-12-18** | 2026 guidelines page |
| **Charla** (Spanish talk) | CFP | **~2026-12-18** | 2026 guidelines page |
| **Tutorial** ("build a conference app in Python with Flet") | CFP | **~2026-12-18** | 2026 guidelines page |
| **Lightning talk** (5 min) | Signed up through the PyCon US dashboard during the conference. Organizers pick speakers at lunchtime and email them. | On site, May 14–16, 2027 | https://us.pycon.org/2026/events/lightning-talks/ (accessed 2026-10-11): 2026 slots were Fri May 15 18:00, Sat May 16 08:00 and 17:45, Sun May 17 08:00 PST |
| **Open Space** (1 h) | Booked online on us.pycon.org from the Thursday, opening the day before each slot and closing up to 1 h before it | Thursday of conference week (≈ May 13, 2027) | https://us.pycon.org/2026/events/open-spaces/ (accessed 2026-10-11) |
| **Sprint** ("contribute to the PyCon app / Flet extensions") | Logged-in form "submit a sprint here"; the page lists no deadline | Before the conference. Aim for Apr 2027 so the sprint is listed in the app. | https://us.pycon.org/2026/events/dev-sprints/ (accessed 2026-10-11) |
| **Attendees install the app** | App Store and Google Play updates under the PSF accounts (§3) | See the release timeline in §7 | — |

---

## 2. Why PyCon is rewriting for 2027

### 2.1 What the upstream repo says

- On **2026-04-10** Jacob Coffee added a README banner in commit `fb7482f`
  (https://github.com/PyCon/pycon-us-mobile/commit/fb7482f). It says this is the last year the codebase
  exists in its current form, that they are losing Ionic features they rely on, and that they will rewrite
  the app for 2027. It gives `infrastructure@python.org` as the contact.
- The repo is `github.com/PyCon/pycon-us-mobile`. The README still says `psf/pycon-us-mobile`, which
  redirects there (GitHub API, accessed 2026-10-11).
- Last push was 2026-05-18. The repo has 46 open issues. **Discussions are disabled.**
- Searching the issues and PRs for "rewrite", "appflow", "flutter", "react native", "native" and "2027" (gh,
  2026-10-11) finds **no public rewrite plan, no chosen technology and no requirements document.**
- Signals that are relevant to a rewrite:
  - Issue tracking happens in a **private Linear workspace** (`psf`, prefix `PYMOBIL`, e.g. PYMOBIL-129,
    linked from #307). Public commenters cannot see it.
  - The backend is the **private** repo `PyCon/pycon-site`. Issue #300 (2026-05-08) says its push console
    spec lives in `pycon-site/.claude/PLAN-PUSH-NOTIFICATIONS.md`.
  - **#307** "App not compatible with my device" (2026-05-08): Android 12 and 13 users could not install
    the app, because `minSdkVersion = 34`. The maintainer replied that "one of our internals required a
    minimum version for Android 14". A community fork (PR #309, closed) ran fine on Android 13.
    https://github.com/PyCon/pycon-us-mobile/issues/307
  - **#300** "Build staff push-notification console in pycon-site" (open). It names the FCM topics
    `announcements`, `schedule-changes` and `emergency` and the Firebase project **`pycon-us-2023-mobile`**.
    https://github.com/PyCon/pycon-us-mobile/issues/300
  - Open feature requests a rewrite could close (all from 2026-05): **#312** a schedule change log,
    **#311** native navigation buttons not accessible, **#313** "Don't jump back to now", **#310** badge
    scanning, **#279** back navigation from an open space.
  - **#246** (open): Plausible UTM tracking for outbound links.
- **People**: Jacob Coffee wrote almost every 2026 commit and the README banner. His EuroPython 2026 bio
  says he is "the Director of Engineering at the Python Software Foundation"
  (https://ep2026.europython.eu/speaker/jacob-coffee, accessed 2026-10-11).

### 2.2 What Ionic is discontinuing

| Date | Event | Source |
|---|---|---|
| 2025-02-11 | Ionic (owned by OutSystems since Oct 2022) **stopped selling all commercial products to new customers**: Appflow, Identity Vault, Auth Connect, Secure Storage, Portals and the other paid components. For existing customers it started "a multi-year process of discontinuing maintenance and support". "Appflow users: You'll continue to have access through December 31, 2027." Ionic Framework and Capacitor stay free and open source. | https://ionic.io/blog/important-announcement-the-future-of-ionics-commercial-products (2025-02-11) |
| 2025-02-11 → updated 2026-09-24 | Ionic support article: "All Appflow features and services will be sunset effective **December 31, 2027**… applications still relying on Appflow infrastructure… may experience build pipeline failures and/or live update failures resulting in whitescreens." It recommends Capawesome Cloud or Capgo for live updates and Capawesome, Capgo, Bitrise, Codemagic or VoltBuilder for native builds. | https://ionic.zendesk.com/hc/en-us/articles/29907381079831-Native-Builds-and-Live-Updates (created 2025-02-11, updated 2026-09-24) |
| 2026-10-01 | A search snippet says Appflow stopped allowing new apps and plan changes on this date | search summary only; **UNCONFIRMED** (the article text above does not say this) |
| — | Capawesome says it is Ionic's preferred migration partner and recommends migrating by mid-2027 | https://capawesome.io/blog/migrating-from-ionic-appflow-to-capawesome-cloud/ (visible date 2026-09-25) |

How this affects the PyCon app:

- The app depends on **Appflow Live Updates**: `@capacitor/live-updates ^0.4.0`, `LiveUpdates` app id
  `e8e09c7a` on channel `Production` in `capacitor.config.ts`, plus `make appflow-ship` and
  `appflow live-update generate-manifest` in `package.json`/`Makefile`. The 2026 team used it to push
  web-bundle fixes during the conference without store review. The update banners
  (`live-update.service.ts`, commits `f0719ef`/`8a1e53e` on 2026-05-16) show this.
- Strictly speaking, Appflow still works through **2027-12-31**, which is after PyCon US 2027 (May 2027).
  The README does not say which features are "critical", so the exact trigger is **UNCONFIRMED**. The
  likely reasons are the Appflow and Live Updates end of life plus the end of Ionic's commercial support.
  This is inference.
- Everything else in the stack is open source and not discontinued: Capacitor 7, Ionic Framework 8,
  `@capacitor-firebase/*`, `@capacitor-mlkit/barcode-scanning` and `@capacitor/inappbrowser` (OutSystems).

### 2.3 What the PSF would need to accept a community rewrite

This list is based on what the repo and the stores show. No public PSF policy exists, so it is
**UNCONFIRMED** until confirmed with infrastructure@python.org.

1. **Store identity.** The PSF owns both listings (§3). Shipping as an *update*, so existing installs and
   ratings carry over, needs the PSF to build and sign the app or to give a contributor a role:
   - iOS: Apple team `BMM5U3QVKW` (`DEVELOPMENT_TEAM` in `project.pbxproj`), bundle id
     `org.pycon.us.2023.onsite`, APNs key, App Store Connect access (App Manager role or CI API key).
   - Android: package `org.pycon.us`, the Play App Signing **upload key** held by the PSF, Play Console
     access, and `versionCode` > **26022**.
2. **Firebase project `pycon-us-2023-mobile`.** The rewrite needs the `google-services.json` and
   `GoogleService-Info.plist` for the same project so the FCM topics and analytics keep working. It also
   needs the service account that issue #300's push console will use.
3. **Backend API access.**
   - A staging `us.pycon.org` with the `/<year>/api/v1/...` endpoints (§4).
   - Test `APIAuth` key/secret pairs for each role: attendee, sponsor lead retrieval, door check, swag
     redemption, and the "mask violation" capture role.
   - Sample badges, since issue #307 notes "sample badges are not published yet".
   - Ideally read access to the private `PyCon/pycon-site` repo, or a published JSON Schema/OpenAPI file.
4. **Process.**
   - Ask to be added to the Linear `PYMOBIL` project.
   - Agree a repo: a new branch or repo under `github.com/PyCon`, keeping the **Apache-2.0** license (the
     upstream `LICENSE`). The rewrite cannot bring in GPL dependencies (see ECO-01).
   - Agree a code-freeze and store-submission timeline (§7) and a support plan for the conference week:
     who is on call to ship hotfixes, given that there are no OTA updates.
5. **Policy items the PSF must sign off.**
   - Play Data Safety form and App Privacy labels. These change if analytics move from Firebase to
     Plausible or HTTP.
   - Updated privacy policy wording, age-rating questionnaire answers (Apple, required since 2026-01-31),
     and the EU trader status that already exists.

---

## 3. Store presence of the current app

| | iOS App Store | Google Play |
|---|---|---|
| Name | PyCon US | PyCon US ("On-Site tools for PyCon US") |
| ID | track id **6446810296**, bundle **`org.pycon.us.2023.onsite`** | package **`org.pycon.us`** |
| Publisher | Seller and artist "Python Software Foundation" | "Python Software Foundation" |
| Latest version | **26.2.1**, released **2026-05-10** ("Various bugfixes… white screen… This should fix that.") | listing "Updated on May 10, 2026". Source `versionName 26.2.1` / `versionCode 26022`. |
| First release | 2023-03-28 | — |
| Minimum OS | **iOS 18.0** | **Android 14 (API 34)** from source `minSdkVersion = 34`; the listing did not show it. Issue #307 confirms installs failed on Android 12/13. |
| Ratings | **4.63 / 5 from 8 ratings**; size 48.6 MB; category Utilities; free | **1K+ downloads**; content rating Everyone; category Events; no star rating shown (too few reviews, **UNCONFIRMED**) |
| URL | https://apps.apple.com/us/app/pycon-us/id6446810296 | https://play.google.com/store/apps/details?id=org.pycon.us |
| Source (date) | `https://itunes.apple.com/lookup?bundleId=org.pycon.us.2023.onsite` (accessed 2026-10-11) | Play listing HTML (accessed 2026-10-11) |

What this means for the port:

- **Shipping as an update needs the PSF's accounts and keys.** Users then get the Flet build through a
  normal update, the listing keeps its history, ratings and search rank, and there is no "which app do I
  install" confusion at the registration desk.
- A new listing under another publisher would compete with the official app, and "PyCon US" naming would
  likely trip store impersonation review. **Do not plan for it.**
- **Bundle and package IDs must stay the same.** In Flet that means `[tool.flet] org`/`bundle_id` plus
  `[tool.flet.ios] bundle_id = "org.pycon.us.2023.onsite"` and the Android package override `org.pycon.us`.
  These must be verified in `flet build`.
- Flet can **widen device reach**. Flet 1.1.0 requires iOS 15+ (`CHANGELOG.md` 1.1.0, "macOS 12 and iOS 15
  minimum"), and Android defaults to Flutter's `minSdkVersion`. This answers issue #307. Whether 2027 keeps
  the iOS 18 / Android 14 floors is a PSF decision.
- Store rules to meet when submitting before May 2027:
  - **Google Play**: from **2026-08-31**, new apps and updates must target **Android 16 / API 36**
    (extension to 2026-11-01).
    https://developer.android.com/google/play/requirements/target-sdk (page updated 2026-10-01)
  - **Apple**: since **2026-04-28**, uploads must be built with **Xcode 26+ / iOS 26 SDK**. Since
    **2026-09-09**, apps must target iOS 13 or later.
    https://developer.apple.com/news/upcoming-requirements/ (accessed 2026-10-11)
  - Apple usually raises the Xcode minimum each late April. A new floor around 2027-04 is likely
    (**UNCONFIRMED**). Flet 1.1.0 already fixes Xcode 27 builds (`CHANGELOG.md`, #6874).
  - Flet sets `target_sdk_version` from `[tool.flet.android]` or the Flutter default
    (`website/docs/publish/android.md:935`). Check that Flutter 3.47.7's default is ≥ 36 (**not
    spot-checked**).

---

## 4. Backend: us.pycon.org (Django)

| Question | Finding | Source (date) |
|---|---|---|
| Current source repo | **Private: `PyCon/pycon-site`.** `PyCon/pycon-site-public` (created 2026-04-06) holds only a README and an issue tracker. Its README says the site source "lives in a private repository ([PyCon/pycon-site])". | https://github.com/PyCon/pycon-site-public (README, accessed 2026-10-11) |
| Is it Django? | Yes. `conference.json` responses carry `server: gunicorn`, `access-control-allow-origin: *` and `content-type: application/json`. | `curl -I https://us.pycon.org/2026/schedule/conference.json` (2026-10-11) |
| Public ancestor | **`PyCon/pycon2019`** (Symposion-based, last push 2021-11-27). The rest of the stack is also public: `PyCon/symposion` (2022-04-27) and `PyCon/registrasion` (2022-04-28). | GitHub API (2026-10-11) |
| `/<year>/schedule/conference.json` | In pycon2019, `symposion/schedule/views.py` `schedule_json()` (line ~179). Its docstring documents the **2019** schema: a list of slots with `kind talk/tutorial/plenary/poster`, `name`, `room`, `start`, `end`, `duration`, `authors`, `abstract`, `description`, `conf_key`, `conf_url`, `video_url`, `slides_url`, `assets_url`, `tags`, `recording_release`. Also `pycon/schedule/views.py` `session_staff_json` (`/<YEAR>/schedule/session-staff.json`). | https://github.com/PyCon/pycon2019/blob/master/symposion/schedule/views.py |
| 2026 feed shape (live) | The schema has **changed** and is **not publicly documented**. It is now a **dict** with keys `conference`, `schedule`, `open-spaces`, `job-listings`, `sprints`, `posters`. Items have `conf_key, kind, name, room, rooms, start, end, duration, description, tags, section, list_render, released, license, contact` (+ `authors, speakers, cancelled, conf_url` on 131 of 728). `kind` values: `talk, tutorial, charla, plenary, keynote, poster, break, informational, lightning-talks, open-space, available-open-space, available-open-space-slot, sponsor-workshop, summit, event, ai, security`. | cached `scratchpad/feed/conference.json` (824 KB) |
| Signed API (`X-API-Key`, `X-API-Signature`, `X-API-Timestamp`) | The 2019 implementation matches the app byte for byte. `pycon/pycon_api/models.py` `APIAuth.verify_request` computes `sha1(secret + str(timestamp) + METHOD + request.get_full_path() + body)` and **rejects timestamps more than 600 s away from server time**. `pycon/pycon_api/decorators.py` `api_view` wraps responses as `{"code", "data"}` and errors as `{"code", "error"}` (403/404), CSRF-exempt. `docs/api.rst` documents the scheme with a Python helper. Keys and secrets are rows in `APIAuth`, created in the Django admin. | https://github.com/PyCon/pycon2019/tree/master/pycon/pycon_api, https://github.com/PyCon/pycon2019/blob/master/docs/api.rst |
| Mobile and staff endpoints used by `pycon-api.ts` | `/2026/api/v1/user/check_features/`, `/user/mobile_state/` (GET/POST favorites), `/check_in/redeemable/`, `/check_in/attendees_by_product[_with_quantity]/<id>/`, `/check_in/fetch_products/?attendee_access_code=…&category_pk_list=…|product_pk_list=…&mode=…`, `/check_in/redeem_products/` (POST), `/mask_violations/attendees/`, `/mask_violations/capture/`, `/lead_retrieval/sponsors/`, `/lead_retrieval/capture/?attendee_access_code=…&badge_validator=…`, `/lead_retrieval/<code>/note/` (POST). **None of these exist in any public repo.** They live only in private `PyCon/pycon-site`. **No public schema.** | local `src/app/providers/pycon-api.ts`; `gh search code mobile_state --owner PyCon` finds only the mobile repo (2026-10-11) |

How this helps the "Python end to end" story and contract tests:

- The talk can say: Django backend (Python) → JSON → Flet app (Python), all in one language.
- Contract tests can be built in three layers:
  1. JSON Schemas generated from snapshots of the public `conference.json` (2025 and 2026 feeds), checked in
     CI with `jsonschema`.
  2. A pure-Python signer reproducing `APIAuth.verify_request`, unit-tested against the documented
     algorithm from 2019 `docs/api.rst`.
  3. Recorded fixtures (VCR-style) for the private endpoints, with the PSF's help.
- Ask the PSF to publish a JSON Schema or OpenAPI file for `/api/v1/`. It is cheap with django-ninja or DRF
  spectacular, and it benefits any rewrite. This is a partnership ask.
- **Clock skew.** If the 600-second window still applies (**UNCONFIRMED** for 2026), the Flet client should
  sign with server time from the `Date` header when device clocks are wrong.

---

## 5. Flet ecosystem status

### 5.1 Flet itself

- **Latest on PyPI: `flet` 1.0.4, uploaded 2026-10-08** (https://pypi.org/pypi/flet/json, accessed
  2026-10-11).
- The local monorepo is at **1.1.0 (unreleased)**: Flutter 3.47.7, `material_ui`/`cupertino_ui`, the new
  `flet-shadcn-ui`, and an iOS 15 / macOS 12 minimum (`CHANGELOG.md`).
- Flet 1.0 was announced on **2026-09-15** (`website/blog/2026-09-15-flet-1-0.md`).
- **Roadmap 2026–2027** (`website/src/pages/roadmap.md`, published at https://flet.dev/roadmap):
  - Framework: Flutter 3.47, Python 3.15, more UI libraries (shadcn, fluent, macos_ui, yaru), BLE, NFC,
    sensor examples, a Flet CLI for Studio.
  - Studio: MCP, GitHub integration, desktop version.
  - **Fletbase**: packaging, publishing to App Store / Google Play / Microsoft Store, hosting, database,
    files, auth, AI.
  - **No barcode, notification, Firebase or calendar items are on the roadmap.**
- **Official extensions published at 1.0.4 (2026-10-08)**: `flet-ads`, `flet-audio`,
  `flet-audio-recorder`, `flet-camera`, `flet-charts`, `flet-code-editor`, `flet-color-pickers`,
  `flet-datatable2`, `flet-flashlight`, `flet-geolocator`, `flet-local-auth`, `flet-lottie`, `flet-map`,
  `flet-permission-handler`, `flet-rive`, `flet-secure-storage`, `flet-spinkit`, `flet-video`,
  `flet-webview` (PyPI JSON, 2026-10-11).
- **Official work in flight**: **flet-dev/flet#6948** "New extension: flet-local-notifications
  (flutter_local_notifications)", an **open issue (not a PR)** opened by Feodor Fitsner on **2026-10-10**,
  assigned to him (FeodorFitsner), **no milestone** (https://github.com/flet-dev/flet/issues/6948; GitHub API,
  2026-10-11). No implementation PR is linked yet, so its release date is unknown.
  - Planned for Android, iOS, macOS, Windows, Linux and web: `show/cancel`, permission, and
    `on_notification_tap`.
  - **Out of scope for v1: "Scheduled/periodic notifications"**, which the PyCon app needs (§5.3).
- A community request for official native extensions, **flet-dev/flet#6784** (2026-08-21, closed
  2026-09-23), asked for `flet-calendar` and others (https://github.com/flet-dev/flet/issues/6784).

### 5.2 Third-party Flet extensions found (PyPI simple index and GitHub search, 2026-10-11)

| Need | Package or repo | Version / date | Notes |
|---|---|---|---|
| Barcode/QR | **`AyberkA0/flet-barcode-scanner`** (GitHub only; **not on PyPI**) | pushed 2026-10-09, ★16 | Wraps `mobile_scanner` and needs `flet>=0.86.5`. **License GPL-3.0**, which the Apache-2.0 PSF app cannot use. Useful as a reference only. https://github.com/AyberkA0/flet-barcode-scanner |
| Local notifications | **`flet-android-notifications`** (PyPI) | 0.12.0, 2026-10-08 | Android only, MIT, wraps `flutter_local_notifications`, supports scheduling. By Alex Stoica. https://github.com/alex-stoica/flet-android-notifications |
| Local notifications | `Nwokike/flet-notifications` (GitHub; PyPI name `flet-notifications` free) | pushed 2026-10-10, ★0 | MIT, all platforms, scheduling via AlarmManager. Very new. https://github.com/Nwokike/flet-notifications |
| Local notifications | `Bbalduzz/flet_notifications` (GitHub) | pushed 2025-05-10, ★36 | MIT, built on the pre-1.0 extension API, stale |
| Local notifications | **`flet-local-notifications` on PyPI is already taken** by an unrelated project | 1.2.2, 2026-07-11, pins `flet==0.28.3`, summary "Add your description here" | **Name clash with the official #6948 plan** |
| Push | **`flet-onesignal`** (PyPI) | 0.4.4, 2026-03-11, MIT | OneSignal SDK, not FCM. The PSF uses FCM topics (§2.1), so this would mean changing providers. https://github.com/brunobrown/flet-onesignal |
| Firebase (messaging/analytics) | none | — | Only Firebase-Auth/Firestore *tutorial apps* exist (e.g. `1mrnewton/Flet-Firebase-Auth`). No extension. |
| Device calendar | none | — | Requested in #6784 |
| In-app browser | `flet-browser` 0.1.0 (2025-12-02) | — | Trivial. Core `ft.UrlLauncher` already covers this (below). |
| App links | none needed | — | Core `flet build` deep linking (below) |
| Other relevant | `flet-printing` 0.2.0 (2026-07-14), `flet-media-library`, `flet-stt`, `flet-android-background` 0.0.4 (2026-10-10) | — | Not needed for the port |

Core Flet coverage, checked with `uv run --offline python -c "import flet as ft"` (1.0.4 in the monorepo env):

- `ft.UrlLauncher.launch_url(url, mode=ft.LaunchMode.IN_APP_BROWSER_VIEW, browser_configuration=…)`. This
  maps to url_launcher's in-app browser: SFSafariViewController on iOS, Custom Tabs on Android.
- `ft.Share`, `ft.Connectivity`, `ft.SharedPreferences`, `ft.HapticFeedback`, `ft.Clipboard`,
  `ft.Wakelock`, `ft.ScreenBrightness`.
- `flet build` deep linking: `[tool.flet(.<platform>).deep_linking] scheme/host`
  (`website/docs/publish/index.md:1365-1410`).

### 5.3 Flutter packages a new Flet extension would wrap

All data from the pub.dev API (`/api/packages/<name>` and `/score`, accessed 2026-10-11).

| Capability | Package | Latest | Published | Likes | Points | 30-day downloads | Publisher | Platforms |
|---|---|---|---|---|---|---|---|---|
| Barcode/QR | **mobile_scanner** | 7.4.2 | 2026-09-14 | 2,305 | 160/160 | 1.79 M | steenbakker.dev | android, ios, macos, web |
| Barcode (alt) | flutter_zxing | 3.1.0 | 2026-09-25 | 151 | 160 | 41 K | — | android, ios, desktop (no web) |
| Local notifications | **flutter_local_notifications** | 22.3.1 | 2026-09-13 | 7,354 | 150 | 3.14 M | dexterx.dev | android, ios, macos, windows, linux, web |
| (helpers) | timezone / flutter_timezone | 0.11.1 / 5.1.1 | 2026-06-29 / 2026-10-03 | 595 / 343 | 160 | 4.0 M / 1.2 M | labs.dart.dev / wolverinebeach.net | all |
| Local notifications (alt) | awesome_notifications | 0.12.1 | 2026-07-01 | 3,441 | 130 | 69 K | carda.me | all |
| Firebase core | **firebase_core** | 4.15.0 | 2026-09-14 | 4,079 | 160 | 5.20 M | firebase.google.com | android, ios, macos, windows, web |
| Push | **firebase_messaging** | 16.7.0 | 2026-09-14 | 3,950 | 160 | 3.82 M | firebase.google.com | android, ios, macos, web |
| Analytics | **firebase_analytics** | 12.6.0 | 2026-09-14 | 1,312 | 160 | 2.33 M | firebase.google.com | android, ios, macos, web |
| Push (alt provider) | onesignal_flutter | 5.7.0 | 2026-09-23 | 954 | 125 | 168 K | — | android, ios |
| Add to calendar (prompt) | **add_2_calendar** | 3.1.1 | 2026-06-15 | 364 | 160 | 141 K | (unverified) | android, ios |
| Device calendar (silent R/W) | device_calendar | 4.3.3 | **2024-09-29** (stale) | 281 | 130 | 80 K | builttoroam.com | android, ios |
| Device calendar (new) | device_calendar_plus | 0.10.1 | 2026-10-02 | 22 | 160 | 17 K | bullet.to | android, ios |
| Custom tabs (themed) | flutter_custom_tabs | 2.6.0 | 2026-07-26 | 282 | 160 | 167 K | — | android, ios, web |
| In-app browser (already in core) | url_launcher | 6.3.3 | 2026-10-02 | 8,183 | 160 | 7.61 M | flutter.dev | all |
| In-app webview | flutter_inappwebview | 6.1.5 | **2024-10-08** (stale) | 2,855 | 130 | 1.21 M | inappwebview.dev | android, ios, macos, windows, web |
| App links | **app_links** | 7.2.2 | 2026-10-06 | 1,323 | 160 | 3.20 M | cow-level.ovh | all |
| (deprecated) | uni_links | 0.5.1 | 2021-04-28 | — | — | — | — | **discontinued** |

---

## 6. Prior art worth borrowing UX from

| App | Stack | Status (GitHub API, 2026-10-11) | What to borrow |
|---|---|---|---|
| **Ionic Conference App**, `ionic-team/ionic-conference-app` | Ionic/Angular | ★3.6k, pushed 2026-09-25 | The PyCon app's own ancestor (the README links its CONTRIBUTING). Use it for screen parity and the schedule/speakers/map/about IA. |
| **FlutterKaigi** `FlutterKaigi/conference-app-2023` and `FlutterKaigi/2025` | Flutter | ★131, Apache-2.0, pushed 2024-08-02; 2025 repo pushed 2026-04-08 | Material 3 session timeline, per-room tabs, favorites, a sponsor grid. https://github.com/FlutterKaigi/conference-app-2023 |
| **DroidKaigi** `DroidKaigi/conference-app-2025` | Kotlin Multiplatform / Compose | ★227, pushed 2025-09-12 | Timetable grid vs list toggle, "now" marker, offline-first, and accessibility. Relevant to #313/#311. |
| **Flutter Europe 2020** `FlutterEurope/conference2020` | Flutter | ★263, archived | Simple agenda and ticket UX |
| **Voxxed Days** `devoxx/voxxedapp` | Flutter | ★35, 2019 | Multi-event selection, useful if the app ever covers several PSF events |
| **EventFahrplan** `EventFahrplan/EventFahrplan` | Android (Kotlin), reads Frab/**Pretalx**/Wafer | ★279, Apache-2.0, pushed 2026-09-25 | **Schedule change log** with highlighted changed sessions, which directly answers issue **#312**. Also offline schedules and alarms per session. |
| **FOSDEM Companion** `cbeyls/fosdem-companion-android` | Android | ★154, Apache-2.0, pushed 2026-08-30 | Fast search, "live now"/"upcoming" lists, bookmarks export, room-status integration |
| **Hoverboard** `gdg-x/hoverboard` | Web (PWA) | ★1.2k, pushed 2026-10-10 | GDG DevFest template: PWA schedule and speaker pages. A pattern for the `flet build web` deliverable. |
| **PyCon Italia** `pythonitalia/pycon` | Django + frontend, uses pretix | ★107, MIT, pushed 2026-10-05 | Another Python-backend conference platform. Nearest *Python* prior art on the backend side. |
| **PyCon India app** `pythonindia/PyCon-Mobile-App` | Python (**Kivy**) | ★32, GPL-3.0, created 2016-07-08, last pushed 2023-10-18, not archived (GitHub API, 2026-10-11). https://github.com/pythonindia/PyCon-Mobile-App | Prior art for a Python-built PyCon app; check its schedule and offline handling. It also means "first Python PyCon app" is not a claim the talk can make. |
| Other Python-built conference apps (Flet/BeeWare) | — | **None found** (web and GitHub search, 2026-10-11). Confy (`net.kirgroup.confy`, Python + GTK) is a desktop/Linux-phone schedule viewer. https://linuxphoneapps.org/apps/net.kirgroup.confy/ | A Flet PyCon app would be the **first Flet conference app found**, but not the first Python PyCon app (see the PyCon India row). That is still a strong talk hook. |

---

## 7. Implications for the port plan

### 7.1 Dated deadlines

Today is 2026-10-11. Dates marked "est." follow the 2025/2026 pattern and are UNCONFIRMED.

| Date | Milestone | Owner |
|---|---|---|
| **Now → 2026-10-31** | Email `infrastructure@python.org` (and Jacob Coffee, PSF Director of Engineering) proposing the Flet port as the 2027 rewrite. Ask for the items in §2.3. | user |
| ~2026-10-31 (est.) | PyCon US 2027 CFP opens | PyCon |
| ~2026-11-20 (est.) | Proposal Mentorship sign-up deadline (optional) | user |
| **~2026-12-18 (est.)** | **CFP closes**: submit a Talk ("PyCon's app, now in Python") + a Poster (live demo) + optionally a Tutorial (3 proposals max per person) | user |
| 2026-12 → 2027-01 | Feature parity alpha against the 2026 feed and staging API. Contract tests (§4) green in CI. | user |
| ~2027-02-10…17 (est.) | Speaker notifications. Confirm attendance by ~2027-02-25. | — |
| ~2027-03-13 (est.) | 2027 schedule published, so the `/2027/schedule/conference.json` feed goes live. Point the app at it. | PSF/user |
| **2027-03-31** (recommended) | Feature freeze. TestFlight and Play internal or closed testing with PSF staff, sponsors (lead retrieval) and door-check volunteers. | user + PSF |
| **2027-04-16** (recommended) | Submit store builds (PSF accounts). Leave margin for review rejections, which matter more because there are no OTA hotfixes. Apple may raise the Xcode minimum in late April 2027 (UNCONFIRMED); Flet 1.1 already builds with Xcode 27. | PSF |
| **2027-04-30** (recommended) | Public release. In 2026 the release came only 3 days before tutorials, and issue #308 (blank page) and the 26.2.0 white-screen incident followed. Plan an earlier release. | PSF |
| Before conference | Submit the sprint form ("PyCon app + Flet extensions") | user |
| 2027-05-12 → 05-18 (dates official, PyCon blog 2026-09-24; day split UNCONFIRMED) | Conference: Open Space (book Thursday), Lightning Talk (dashboard, on site), sprints May 17–18 | user |
| 2027-12-31 | Appflow and Live Updates sunset. The Ionic app could not be maintained after this anyway. | Ionic |
| ~2027-08-31 (est.) | Google Play's next yearly target-API bump (API 37), which applies to post-conference updates | — |

### 7.2 Partnership steps

1. **Offer, don't fork.** The PSF owns the listings, Firebase project, API keys and backend.
   - Propose shipping the Flet build as **version 27.x of the same listings**: `org.pycon.us.2023.onsite`
     and `org.pycon.us`.
   - Propose building on PSF CI (GitHub Actions + `flet build ipa/aab`) with an App Store Connect API key
     and the Play upload key as PSF-held secrets.
2. **Ask for access.**
   - A staging API with test `APIAuth` keys per role and sample badges.
   - The Firebase config files.
   - Linear PYMOBIL access.
   - Ideally a published `/api/v1` schema, or read access to `PyCon/pycon-site`.
3. **Keep Apache-2.0**, and have the PSF repo host the code: a new repo or `rewrite-2027` branch under
   `github.com/PyCon`.
4. **Agree the OTA replacement.** Flet bundles Python in the binary, so there is no Appflow equivalent.
   - Make all *content* server-driven: schedule, maps metadata, about pages, feature flags via
     `check_features`.
   - Reserve store expedited review for true hotfixes.
   - Ship a PWA (`flet build web`) as a fallback, as the current app does on Firebase Hosting.
5. **Fix known pain points as selling points.**
   - Issue #307: lower `minSdk`/iOS minimum, subject to PSF approval.
   - Issue #312: schedule change log, EventFahrplan-style.
   - Issues #311/#313/#279: back navigation and "jump to now".
   - Issue #300: staff push console. Python end to end: the Django console sends FCM and the Flet app
     receives it.

### 7.3 Extension priorities

| Priority | Extension | Wraps | Why / when | Effort |
|---|---|---|---|---|
| P0 | **`flet-barcode-scanner`** (official, MIT/Apache) | `mobile_scanner` 7.4.2 | Lead retrieval, door check, swag redemption and mask capture are **unusable without it**. There is no workaround. The GPL community wrapper is reference only. | M |
| P0 | **`flet-firebase`** (core + messaging [+ analytics]) | firebase_core 4.15.0, firebase_messaging 16.7.0, firebase_analytics 12.6.0 | Keeps the PSF's existing FCM topics (`announcements`, `schedule-changes`, `emergency`, `daily-digest`), and with them the emergency and safety pushes. Analytics can fall back to HTTP. Needs `flet build` support for the google-services files and Gradle plugin. | L |
| P1 | **`flet-local-notifications`**: contribute **scheduled** notifications (`zonedSchedule` + timezone) to the official **#6948** effort. Resolve the PyPI **name clash** (the `flet-local-notifications` name is taken by an unrelated 0.28-era project). | flutter_local_notifications 22.3.1 + timezone 0.11.1 + flutter_timezone 5.1.1 | Session reminders, plus the 11 fixed reminders for lightning talks and open spaces. Interim: server pushes via FCM topics, or `.ics` export. | M (on top of #6948) |
| P2 | **`flet-add-to-calendar`** | add_2_calendar 3.1.1 | Native "add to calendar" prompt. Interim: `.ics` through `ft.Share`. Needs an Android `<queries>` manifest hook in `flet build`. | S |
| — | In-app browser | core `ft.UrlLauncher` (`IN_APP_BROWSER_VIEW`) | Already sufficient. Use `flutter_custom_tabs` 2.6.0 only if toolbar theming is needed. | none |
| — | App links | core `flet build` deep linking; app_links 7.2.2 only if runtime link events are needed beyond routing | The current app has only `webcredentials:us.pycon.org`, no app links, so this is optional. Universal links would need AASA and assetlinks files on us.pycon.org (a PSF task). | none / S |
| — | OTA updates | — | Not replicable. Replace with the server-driven content strategy above. | n/a |
