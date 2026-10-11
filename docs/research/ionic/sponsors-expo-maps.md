# Ionic inventory — Sponsors, Expo Hall & Maps slice

Source tree: `/Users/ndonkohenri/PycharmProjects/flet-dev/others/pycon-us/excluded/pycon-us-mobile/src/app/`
Stack: Ionic 8.4 / Angular 17.3 / Capacitor 7, `@ciag/ngx-pinch-zoom` 13.3.0 (pinned exact).
This document describes the *existing Ionic behaviour only*; it proposes no Flet design.

## 0. Files read (all read in full)

| Area | Files | Lines (ts/html/scss) |
|---|---|---|
| Sponsors list | `pages/sponsors/sponsors.page.{ts,html,scss}`, `sponsors.module.ts`, `sponsors-routing.module.ts` | 62 / 38 / 70 |
| Sponsor detail | `pages/sponsor-detail/sponsor-detail.{ts,html,scss}`, `sponsor-detail.module.ts`, `-routing.module.ts` | 140 / 60 / 108 |
| Job listings | `pages/job-listings/job-listings.page.{ts,html,scss}`, modules | 178 / 62 / 226 |
| Conference map page | `pages/conference-map/conference-map.page.{ts,html,scss}`, modules | 125 / 87 / 89 |
| Expo hall map component | `expo-hall-map/expo-hall-map.component.{ts,html,scss}`, `expo-hall-map.module.ts` | 388 / 80 / 206 |
| Floor plan modal | `floor-plan-modal/floor-plan-modal.component.{ts,html,scss}`, module | 27 / 36 / 67 |
| Location map card | `location-map/location-map.component.{ts,html,scss}`, `room-locations.ts` (165), `venue-locations.ts` (85), module | 36 / 24 / 123 |
| Venue & hours | `pages/venues-hours/venues-hours.page.{ts,html,scss}`, modules | 181 / 68 / 145 |
| Context (partial) | `pages/tabs-page/tabs-page-routing.module.ts`, `tabs-page.html`, `tabs-page.ts` (menu/banner), `app.component.ts` (menu), `providers/conference-data.ts` (load/getSponsors/getJobListings/getContent/invalidateCache/rooms seeding), `pages/room-detail/*`, `pages/session-detail/*` (room links + job-fair card), `pages/help/*`, `pages/wifi/wifi.page.html`, `theme/variables.scss`, `global.scss`, `environments/*`, `capacitor.config.ts`, `package.json` | — |

`LiveUpdateService` is injected as `public liveUpdateService` in Sponsors, SponsorDetail, JobListings, ConferenceMap and VenuesHours, but **no template in this slice references it** — it is dead injection (safe to ignore in a port).

---

## 1. Shared context for this slice

### 1.1 Routes (from `tabs-page-routing.module.ts`; all under `/app/tabs/`)

| Path | Loads | Notes |
|---|---|---|
| `sponsors` | `SponsorsPageModule` (child `''` → `SponsorsPage`) | |
| `sponsors/sponsor-detail/:sponsorId` | `SponsorDetailModule` | `:sponsorId` is a **slug of the sponsor name**, not an id from the feed |
| `expo-hall` | `ConferenceMapPageModule` with route `data: { initialView: 'expo-hall', pageTitle: 'Expo Hall' }` | Same page class as conference-map, different initial segment + title. Accepts `?booth=<id>` |
| `conference-map` | `ConferenceMapPageModule` (no data → `mapView='floor-plans'`, title `'Conference Center'`) | Bound to the bottom tab button `tab="conference-map"` |
| `job-listings` | `JobListingsPageModule` | |
| `venues-hours` | `VenuesHoursPageModule` | |
| `rooms/room-detail/:roomSlug` (outside slice) | hosts `<app-location-map>` | see §6 deep links |
| `help` (outside slice) | hosts `<app-location-map>` + opens `FloorPlanModalComponent` | |

Because `expo-hall` and `conference-map` are **different path segments**, Ionic's tab outlet keeps **two independent `ConferenceMapPage` instances** alive (each with its own `ExpoHallMapComponent`, search state, zoom state).

### 1.2 Entry points (menu / tab bar) — `app.component.ts`, `tabs-page.html`

| Entry | Label | Ionicon | Target |
|---|---|---|---|
| Side menu, group `expoPages` | `Sponsors` | `business-outline` | `/app/tabs/sponsors` |
| Side menu, group `expoPages` | `Expo Hall` | `storefront-outline` | `/app/tabs/expo-hall` |
| Side menu, group `expoPages` | `Job Listings` | `briefcase-outline` | `/app/tabs/job-listings` |
| Side menu, group `aboutPages` | `Venue & Hours` | `location-outline` | `/app/tabs/venues-hours` |
| Side menu, group `infoPages` | `Conference Maps` | `map-outline` | `/app/tabs/conference-map` |
| Bottom tab bar (2nd of 4–6 buttons) | `Map` | `map` | tab `conference-map` |
| Tab-bar sponsor banner (`tabs-page.html`, rotates every 30 s among sponsors with `mobile_banner: true`) | "`<name>` is a `<level>` Sponsor of PyCon US 2026" | — | `goToSponsor()` → `/app/tabs/sponsors/sponsor-detail/<slug>` |

### 1.3 Data contract (`providers/conference-data.ts`)

* Single feed: `GET ${environment.baseUrl}/2026/schedule/conference.json` with RxJS `timeout(10000)`. `baseUrl` = `https://us.pycon.org` (prod and base), `http://127.0.0.1:8000` / `http://10.0.2.2:8000` (dev).
* `load()` semantics (important for every page here): if `this.data` is in memory → `of(data)` (sync, one emission, completes). Otherwise: read Ionic Storage key **`schedule-cache`** (DB name = `environment.storageKey` = `__pycon_us_mobile_2026` in prod) → if present, `processData(cached)` and **emit #1**; then HTTP fetch → on success `processData(fresh)`, **emit #2**, complete; on error: if cache was served → complete silently (console.log), else present a toast (`'Unable to load schedule, no offline cache available'`, 3000 ms, top, icon `exclamation`) and error the observable. `processData` re-writes the cache key on every call.
* `invalidateCache()` = `this.data = null; storage.remove('schedule-cache')`.
* Slice accessors (all `load().pipe(map(...))`, so they inherit the 1-or-2-emission behaviour):
  * `getSponsors()` → `data.conference.sponsors` — an **object keyed by level name → array of sponsor objects**.
  * `getJobListings()` → `data['job-listings'] || []` — array.
  * `getContent()` → `data.conference.content` — object of HTML strings keyed `about`, `about-psf`, `social-media`, `code-of-conduct`, `venues-hours`, `wifi`.
  * `load()` is called directly by SponsorDetail to get both sponsors and job listings.
* No polling in this slice; no `user:login`/`user:logout` listeners in this slice.

### 1.4 Feed shapes actually present (inspected local `conference.json`)

Sponsor object fields (105 sponsors, 13 levels): `name`, `level`, `level_order` (0..12), `mobile_banner` (bool), `logo_url` (all `https://s3.dualstack.us-east-2.amazonaws.com/pythondotorg-assets/media/sponsor_web_logos/…`), `description` (plain text, 0–1188 chars, 4 contain `\n`; **no HTML tags in any**), `booth_number` (string like `"613"` or `null`; 61 sponsors have one), `job_fair_table_number` (string like `"T2"` or `null`; 19 have one).
Fields the templates test for but **absent from the current feed**: `external_url` (→ "Visit Website" button never renders), `hide` (→ `[hidden]` never true).

Levels in order: `Visionary`(0) · `Sustainability`(1) · `Maintaining`(2) · `Contributing`(3) · `Supporting`(4) · `Partner`(5) · `Participating`(6) · `Associate`(7) · `Standalone Only`(8) · `AV Partner`(9) · `Media`(10) · `Startup Row`(11) · `Community`(12).

Job-listing object fields (13 listings): `id`, `sponsor_name`, `sponsor_logo_url`, `sponsor_level`, `description_html`. **No `postings` field in any listing** (the structured path in `processListings` is dead with the current feed).

`content['venues-hours']` (1394 chars of HTML) = `<h2>Dates, Times, Locations</h2>` + address paragraphs, then `<h3>` sections: `Registration Hours &amp; Location:`, `Information Desk Hours &amp; Location:`, `Swag Pickup Hours &amp; Location`, `Attendee Quiet Room`, `Lost &amp; Found (Room 203AB)`, `Luggage Check`, each followed by `<p>`/`<ul><li>` hour lines (e.g. `Wednesday, May 13: 7:30am - 6pm`).

### 1.5 Theme values referenced by this slice

Ionic named colors are **Ionic defaults, not re-branded** (`variables.scss` `:root`): `primary #3880ff`, `secondary #3dc2ff`, `tertiary #5260ff`, `medium #92949c`, `light #f4f5f8`, `danger #eb445a`. Dark theme: `primary #428cff`, `tertiary #6a64ff`, `medium #989aa2`, `light #222428`; `.dark-theme.ios` bg `#000`, `.dark-theme.md` bg `#121212`, item bg `#1e1e1e`; steps `--ion-color-step-100 #1a1a1a/#2a2a2a`, `-150 #262626/#363636`, `-400 #666/#717171`, `-600 #999/#a0a0a0`, `-650 #a6a6a6/#acacac`. High-contrast light/dark themes exist (`.high-contrast-light-theme`, `.high-contrast-dark-theme`, both also carry `.high-contrast-theme`): HC-light primary `#4a0072`, HC-dark primary `#ffd60a`.
Brand hexes hard-coded in this slice's SCSS: `#3B3EA9` (header/hero indigo), `#101136` (hero gradient end), `#5833E9` (level badge, section headings, sponsor-name links), `#DD04D2` (magenta: hero icons, pins, popup border), `#25C8EB` (job-listings hero icon), `#f0c040` / `rgba(240,192,64,…)` (booth highlight yellow).
Global rules that matter: `ion-header ion-toolbar ion-menu-button:not([color])`, `ion-back-button:not([color])` → `--color:#fff` (white icons on branded headers); `ion-content p/li/[innerHTML]` → `overflow-wrap:anywhere; word-break:break-word`; `prefers-reduced-motion: reduce` → all animations/transitions ≈ 0 ms and `animation-iteration-count:1` (explicitly to stop the two infinite pin-pulse animations). `*[hidden]{display:none!important}`. Viewport meta: `maximum-scale=1.0, user-scalable=no` (required by pinch-zoom).

---

## 2. SponsorsPage — `/app/tabs/sponsors`

**Route / reach.** Side menu → "Sponsors". Also the `defaultHref` back target from SponsorDetail.

**Purpose.** Grouped, read-only list of all sponsors by level; tap → sponsor detail.

**Data.** `ngOnInit()` → `reloadSponsors()`:
1. `LoadingController.create({ message: 'Fetching latest...', duration: 10000 })` → `present()`.
2. `confData.getSponsors().subscribe(sponsors => { this.sponsors = sponsors; changeDetection.detectChanges(); setTimeout(() => loader.dismiss(), 100); })` — the loader is dismissed on the **first** emission (cache); a second emission (network) silently refreshes the list. If `load()` errors (no cache, offline) the loader stays until its 10 s `duration` auto-dismiss and the provider's toast is shown; the page stays empty.
`updateSponsors()` exists but is unused. No storage keys of its own, no pull-to-refresh, no search.

**UI structure.**
* `<ion-header class="ion-no-border">` painted solid `#3B3EA9` (`::after` hidden). Toolbar transparent, `--color:#fff`; start: `ion-menu-button` (white); `ion-title` "Sponsors" with `opacity:0` → `.title-visible` (`opacity:1`, 0.25 s ease) when `showTitle` (content `scrollTop > 100`, via `scrollEvents="true" (ionScroll)`).
* Hero block `.sponsors-hero`: column, centered, padding `16px 24px 32px`, background `linear-gradient(180deg, #3B3EA9 23.5%, #101136 53.29%)`, white text; `ion-icon name="heart"` 40 px `#DD04D2` (margin-bottom 10); `<h1>` "Our Sponsors" (1.6 rem, 700); `<p>` "PyCon US wouldn't be possible without them" (0.9 rem, opacity .8).
* Then `*ngFor="let sponsorLevel of sponsors | keyvalue : levelOrder"` → one `<ion-list lines="full">` per level, ordered by `value[0].level_order` ascending (comparator `levelOrder(a,b)`). Each list: `<ion-list-header><ion-label>{{ level name }}</ion-label>` then `<ion-item button detail routerLink="/app/tabs/sponsors/sponsor-detail/<slug>" [hidden]="sponsor.hide">`:
  * `slot="start"` `.sponsor-logo-thumb`: 48×48, white background, radius 10, padding 6, `margin-inline-end:12px`, shadow `0 1px 4px rgba(0,0,0,.08)`, `<img [src]=logo_url [alt]="name + ' logo'">` `object-fit:contain`.
  * `<ion-label>`: `<h2>{{name}}</h2>`, `<p *ngIf="booth_number">Expo Booth {{booth_number}}</p>`.
  * Trailing chevron from `detail="true"`.
* `<div style="height:80px">` spacer at the end (clears the tab bar / sponsor banner).
* No empty state, no error state.

**State & lifecycle.** `showTitle`, `sponsors` only. `ChangeDetectorRef.detectChanges()` forced after data. 100 ms `setTimeout` before loader dismiss.

**Navigation out.** Item tap → `/app/tabs/sponsors/sponsor-detail/<getSponsorSlug(name)>` (same tab stack, so back returns here).

**Edge cases / a11y.** Logo `alt` = `"<name> logo"`. `keyvalue` pipe would throw if `sponsors` were an array (it is an object). Slug collisions would route to the first match (none in the current feed).

**Complexity: 2** — plain grouped list; only nuance is level ordering and the loader-with-double-emission.

---

## 3. SponsorDetailPage — `/app/tabs/sponsors/sponsor-detail/:sponsorId`

**Route / reach.** From Sponsors list, Job Listings sponsor header, Expo Hall booth popup (only when booth has `level`), Venue & Hours "Sponsored by Google" card, Wi-Fi page sponsor card, tab-bar sponsor banner. `:sponsorId` = `getSponsorSlug(name)` = `name.toLowerCase().replace(/\s+/g,'-').replace(/[^a-z0-9-]/g,'')` (e.g. `Anaconda, Inc` → `anaconda-inc`, `Reuven Lerner — Python training` → `reuven-lerner--python-training`, `Qube Research & Technologies` → `qube-research--technologies`).

**Data / lifecycle.**
* `ionViewWillEnter()` (fires on every entry — Angular reuses the component instance across different `:sponsorId` values because the route config is identical; hence the explicit reset): `this.sponsor = undefined; this.jobListings = [];` then `dataProvider.load().subscribe(data => …)`: linear scan over `Object.values(data.conference.sponsors)` arrays, first sponsor whose slug equals `sponsorId` (labelled `break outer`). Then `jobListings = (data['job-listings']||[]).filter(l => l.sponsor_name === sponsor.name).map(l => ({...l, roles: parseRoles(l.description_html)}))`. Match is **exact name equality** (listing `sponsor_name` vs sponsor `name`).
* `ionViewDidEnter()`: `backHref = queryParamMap.get('prevUrl') || '/app/tabs/sponsors'`. **Nobody in the codebase passes `prevUrl` to sponsor-detail**, so it is always `/app/tabs/sponsors` (used only when there is no in-stack history, e.g. cold deep link / cross-tab entry).
* `parseRoles(html)` (2-field variant `{title,url}`; identical algorithm to Job Listings minus `location`) — see §10.1.
* `openUrl(url)` → `window.open(url, '_system', 'location=yes')`.
* `goToBooth(n)` → `NavController.navigateRoot(['/app/tabs/expo-hall'], { queryParams: { booth: String(n) } })`. Comment in source: `routerLink` was avoided because Ionic's tab outlet caches on path segment only, so `?booth=613` → `?booth=127` looked like "same page" and the new query never reached the map; `navigateRoot` forces a fresh activation (root direction: no back animation, and the Expo Hall page shows a **menu button, not a back button**, so return is via menu/tab bar).

**UI structure.**
* Header `ion-no-border`, `translucent="false"`, background `#3B3EA9`, toolbar transparent; start: `ion-back-button [defaultHref]="backHref"` white. No title.
* `.sponsor-hero`: gradient `180deg #3B3EA9 23.5% → #101136 53.29%`, flex-centered, padding `16px 32px 48px`; inside `.sponsor-logo-container`: white, radius 16, padding `20px 24px`, `max-width:260px; width:100%`, shadow `0 8px 32px rgba(0,0,0,.25)`; `<img class="sponsor-logo">` only if `logo_url` (`max-height:100px`, contain).
* `<ion-card class="sponsor-info-card">`: `margin:-24px 16px 8px` (overlaps hero), radius 16, shadow `0 4px 16px rgba(16,17,54,.1)`, z-index 1; `ion-card-content` centered, padding 20:
  * `<h1>{{name}}</h1>` 1.4 rem / 700.
  * `.level-badge` pill if `level`: 0.7 rem uppercase, letter-spacing .08em, padding `3px 12px`, radius 99, bg `#5833E9`, white, 600.
  * `.sponsor-locations` (flex, wrap, centered, gap 6, margin-top 12) shown if `booth_number || job_fair_table_number`:
    * `<ion-chip outline color="primary" (click)="goToBooth(booth_number)" aria-label="Show booth N on the Expo Hall map">` with `ion-icon storefront-outline` + label `Expo Booth {{booth_number}}`.
    * `<ion-chip outline color="tertiary">` (no click handler) with `ion-icon people-outline` + label `Job Fair Table {{job_fair_table_number}}`.
  * `<p class="sponsor-desc" [innerHtml]="description">` if description: left-aligned, 0.9 rem, line-height 1.6, margin `12px 0 8px`, `overflow-wrap:anywhere` (also on nested `a, code`). Feed descriptions are plain text, but they are rendered as HTML (so `\n` collapses to spaces, `&` entities would be decoded).
  * `<ion-button expand="block" (click)="openUrl(external_url)">` with `globe-outline` start icon, text "Visit Website" — only if `external_url` (never in current feed).
* `<ion-card class="jobs-card">` (margin `0 16px`, radius 16) if `jobListings.length > 0`: header `ion-card-title` "Open Positions" (1.1 rem); content: for each listing `<ion-list lines="none">`, for each role `<ion-item class="role-item" [button]="!!role.url" [detail]="!!role.url" (click)="openUrl(role.url)">` with `ion-icon briefcase-outline color="primary" slot="start"` and `<ion-label class="ion-text-wrap">{{role.title}}</ion-label>`; items have `--padding-start:0; --background:transparent`.
* 80 px spacer.
* No "not found" state: an unknown slug renders the hero with an empty white card and an empty `<h1>`.

**Navigation out.** Booth chip → `/app/tabs/expo-hall?booth=<n>` (root nav). Role rows → external URL. Back → previous page in stack or `/app/tabs/sponsors`.

**Complexity: 3** — HTML description rendering, role parsing from HTML, cross-tab deep link with query param and instance-reuse pitfalls.

---

## 4. JobListingsPage — `/app/tabs/job-listings`

**Route / reach.** Side menu → "Job Listings".

**Data / lifecycle.**
* `ngOnInit()` → `loadListings()`: `getJobListings().subscribe(listings => { if (listings.length > 0 || this.allListings.length === 0) { allListings = processListings(listings); filterListings(); detectChanges(); } })` — guards against a later empty emission wiping a populated list.
* `processListings(raw)`: per listing, `structured = Array.isArray(listing.postings) ? listing.postings : []`; if non-empty → roles = postings filtered on non-blank `title` **and** `url`, mapped to `{title, location, url}` (trimmed); else roles = `parseRoles(description_html)` (3-field variant with `location:''`). Spread `{...listing, roles}`.
* Pull-to-refresh `<ion-refresher slot="fixed" (ionRefresh)="doRefresh($event)">` with default `ion-refresher-content`: `confData.invalidateCache()` then `getJobListings().subscribe({ next: rebuild+filter+detectChanges, complete: () => event.target.complete() })`. Because the cache was just removed, this goes straight to network; spinner completes when the observable completes (success or after cache-less error → the error path never calls `complete`, so on a failed refresh the spinner would hang until the user navigates… note: `error` is not handled here).
* Search: `searchText` (ngModel), `filterListings()`: if blank → `listings = allListings`; else `words = searchText.toLowerCase().replace(/,|\.|-/g,' ').split(' ').filter(nonblank)`; keep listing if **every** word is a substring of `haystack = "${sponsor_name} ${description_html} ${roleText}".toLowerCase()` where `roleText = roles.map(r => "${r.title} ${r.location||''}").join(' ')`. **Note the haystack includes raw HTML** (tags, hrefs, `class="external"` …), so searching e.g. `avature` or `nofollow` matches Bloomberg.
* `resetSearch()` → clears text and restores all.
* `openJobFairFloorPlan()` → `ModalController.create({ component: FloorPlanModalComponent, componentProps: { title: 'Job Fair & Community Showcase', imageSrc: 'assets/img/floor-plans/job-fair.jpg', altText: 'Job Fair & Community Showcase floor plan' } })` (no pin).
* `openUrl(url)` → `window.open(url,'_system','location=yes')`.

**UI structure.**
* Branded header identical to Sponsors (solid `#3B3EA9`, hidden title "Job Listings" that fades in after 100 px scroll, white menu button).
* Content (`scrollEvents`) begins with the refresher, then `.page-hero` (same gradient/padding as Sponsors) with `ion-icon briefcase` 40 px **`#25C8EB`**, `<h1>Job Listings</h1>`, `<p>Opportunities from PyCon US sponsors</p>`.
* `<ion-toolbar class="search-toolbar">` (margin-top 12) **only if `allListings.length > 0`**: `<ion-searchbar [(ngModel)]="searchText" [debounce]="250" showCancelButton="focus" inputmode="search" placeholder="Search sponsors" (ionClear)/(ionCancel)="resetSearch()" (ionChange)="filterListings()">`. The toolbar inherits the page's `ion-toolbar { --background: transparent; --color:#fff }` rule (it sits over normal content background).
* `.job-fair-floor-plan-wrapper` (padding `12px 16px 0`) → `<button class="job-fair-floor-plan-card">` (always rendered): flex row, gap 12, width 100 %, height 80, padding `10px 14px 10px 10px`, margin-bottom 16, bg `rgba(59,62,169,.08)`, border `1px solid rgba(59,62,169,.18)`, radius 12, `:active` bg `rgba(59,62,169,.16)`; children: `<img src="assets/img/floor-plans/job-fair-thumb.jpg" alt="">` 60×60 radius 8 `object-fit:cover` shadow; `<span>` "View Job Fair Floor Plan" (flex 1, .95 rem, 600, `#3B3EA9`, lh 1.3); `ion-icon chevron-forward` 1.1 rem `#3B3EA9`. Dark theme (`:host-context(.dark-theme)`): bg `rgba(139,143,212,.12)`, border `rgba(139,143,212,.28)`, active `.22`, label/chevron `#b4b7e8`. High contrast: bg `var(--ion-card-background)`, `2px solid var(--ion-color-primary)` border, label/chevron primary.
* Empty state `*ngIf="allListings.length === 0"` (`ion-padding-horizontal`): `<p>No job listings have been posted yet. Check back closer to the conference!</p>`. There is **no "no search results" state** — a non-matching search shows just the hero/search/floor-plan card.
* `.listings-container` (padding `0 16px`) → `*ngFor listing of listings` `.listing-card` (padding `16px 0`, bottom border `1px solid var(--ion-color-step-100, rgba(255,255,255,.1))`, none on last):
  * `<a class="sponsor-header" routerLink="/app/tabs/sponsors/sponsor-detail/<slug(sponsor_name)>">` flex row gap 12, margin-bottom 12, `:active` opacity .6: `<img class="sponsor-logo">` if `sponsor_logo_url` (40×40, contain, radius 8, white bg, padding 3); `.sponsor-info` (flex, wrap, gap 8): `<h2 class="sponsor-name">` 1.1 rem/600 and `.level-badge` if `sponsor_level` (0.65 rem uppercase, letter-spacing .5px, padding `2px 8px`, radius 4, bg step-100, color step-600, 500 — **a different, greyer badge than Sponsor Detail's purple pill**); trailing `ion-icon chevron-forward aria-hidden` 18 px step-400, `margin-left:auto`.
  * `<ion-list class="roles-list" lines="none">` if `roles.length > 0`: items (`--min-height:40px`, `--padding-start/end:0`, transparent) `[button]="!!role.url" [detail]="!!role.url" (click)="openUrl(role.url)"`: `ion-icon briefcase-outline color="medium" class="role-icon"` (16 px, margin-right 8), `<ion-label class="role-label">` with `<span class="role-title">` (0.9 rem, **`-webkit-line-clamp:2`**, overflow hidden) and `<span class="role-location">` (block, 0.75 rem, opacity .6) if location.
* 80 px spacer.

**What the parser actually produces for the live feed** (simulated with a faithful Python port of `parseRoles`): only listings whose anchor **text** is the URL itself split into multiple rows (Hudson River Trading → 5 linked roles; Anaconda → "Careers"; Capital One → "Python jobs"; Qube → "Careers"). Listings whose links are `<a href="…">Title</a>` (Bloomberg 15 links, Sentry 5, Temporal 9, NVIDIA 2, Old Mission 1, marimo 3) collapse to **one unlinked row whose title is the entire stripped text**, which the 2-line clamp then truncates (e.g. Bloomberg shows "Trade Automation & Execution, New York Network Testing Platforms, New York Infrastructure Automation…" with no tap target). SerpApi/Tower (no visible URLs) → one unlinked text row; OpenEDG → row titled `N/A`. See §10.1 for the algorithm; a port that "fixes" this will diverge from the current app, so flag it as a product decision.

**Navigation out.** Sponsor header → sponsor detail (slug of `sponsor_name`; note `OpenEDG Python Institute` listing links to slug `openedg-python-institute`, which matches the feed sponsor name). Role → external URL. Floor plan card → modal.

**Complexity: 3** — searchbar+debounce, pull-to-refresh with cache invalidation, HTML→roles heuristic, modal.

---

## 5. ConferenceMapPage — `/app/tabs/conference-map` and `/app/tabs/expo-hall[?booth=ID]`

**Route / reach.** Tab bar "Map"; menu "Conference Maps"; Venue & Hours → "Conference Maps" item; Help → "Full Conference Maps" item. The `/expo-hall` alias: menu "Expo Hall"; Sponsor Detail booth chip (`?booth=`).

**State.** `type MapView = 'floor-plans' | '3d-tour' | 'expo-hall' | 'job-fair'`; `mapView` (default `'floor-plans'`), `pageTitle` (default `'Conference Center'`), `floorPlans: FloorPlan[]` (static, below), `@ViewChild('expoMap') expoMap?: ExpoHallMapComponent`.

**Lifecycle.**
* `ngOnInit()`: walk `ActivatedRoute` and all parents; if any `snapshot.data.initialView` → `mapView`; if `data.pageTitle` → `pageTitle`. (Only the `expo-hall` route sets them.)
* `ionViewWillEnter()` (fires on *every* entry incl. cached re-entry/tab switch): `boothId = snapshot.queryParamMap.get('booth')`; if set → `mapView = 'expo-hall'` (forces the segment even if the user had switched away) then `setTimeout(() => this.expoMap?.zoomToBoothId(boothId), 0)` (defer one macrotask so the `*ngIf`'d child exists; the child queues the request if pinch-zoom is not ready).
* `toggleExpoSearch()` → `expoMap?.toggleSearch()`.
* `openFloorPlan(plan)` → `FloorPlanModalComponent` with `{ title: plan.title, imageSrc: plan.full, altText: '<title> floor plan' }` (no pin).

**Static floor plan list (order matters).**

| id | title | subtitle | thumb | full |
|---|---|---|---|---|
| `campus` | Campus Overview | Convention center, hotels, halls, and entrances | `assets/img/floor-plans/campus-map-thumb.jpg` | `…/campus-map.jpg` |
| `concourse` | Concourse Level | Tutorials, Talk Track, Registration, Expo entry | `floor-plan-1-thumb.jpg` | `floor-plan-1.jpg` |
| `upper` | Upper Level | Talk Track, Sponsor Presentations, Speaker Ready, Summits | `floor-plan-2-thumb.jpg` | `floor-plan-2.jpg` |
| `arena` | Arena & Exhibit Halls | Keynotes, Lightning Talks, Expo Hall, Job Fair | `floor-plan-3-thumb.jpg` | `floor-plan-3.jpg` |
| `seaside` | Seaside Meeting Rooms | Sprints, Open Spaces, PyLadies Auction, Web Assembly Summit | `floor-plan-4-thumb.jpg` | `floor-plan-4.jpg` |

**UI structure.**
* **Un-branded** header (default Ionic toolbar colours — this page does *not* paint `#3B3EA9`): toolbar 1: start `ion-menu-button color="medium"`, `ion-title {{pageTitle}}` (always visible), end buttons (only when `mapView === 'expo-hall'`): `<ion-button aria-label="Search booths"><ion-icon slot="icon-only" name="search">`. Toolbar 2: `<ion-segment [(ngModel)]="mapView" value="floor-plans">` with buttons `Floor Plans`/`3D Tour`/`Expo Hall`/`Job Fair` (values `floor-plans`, `3d-tour`, `expo-hall`, `job-fair`), default Ionic segment styling.
* `<ion-content fullscreen="true" [scrollY]="mapView === 'floor-plans'" scrollEvents="true">` — content scrolling is **disabled** on the three map views so pinch/pan gestures are not stolen.
* `floor-plans`: `.floor-plan-list` column, gap 12, padding 12; each `<button class="floor-plan-card" aria-label="Open <title> floor plan">`: column, width 100 %, bg `var(--ion-card-background, var(--ion-item-background, #fff))`, border `1px solid var(--ion-color-step-150, rgba(0,0,0,.08))`, radius 14, overflow hidden, shadow `0 1px 2px rgba(0,0,0,.04)`, `:active` `scale(.99)`; `.floor-plan-thumb-wrap` (relative, white bg) with `<ion-img class="floor-plan-thumb" [src]=thumb [alt]="title + ' thumbnail'">` (full width, lazy-loaded) and `.floor-plan-zoom-hint` (absolute bottom 8 / right 8, 32 px circle, bg `rgba(0,0,0,.55)`, white `ion-icon expand-outline` 18 px, `pointer-events:none`, aria-hidden); `.floor-plan-meta` padding `10px 14px 12px`: `.floor-plan-title` 15 px/600 text colour, `.floor-plan-subtitle` 13 px medium.
* `3d-tour`: `<iframe id="map_frame" width="100%" height="100%" src="https://map.concept3d.com/?id=1802" frameborder="0" scrolling="no" allow="geolocation" title="PyCon US Venue 3D Map" style="border:0;min-height:100%">` — third-party Concept3D web map. Looks hard to port: needs an embedded web view.
* `expo-hall`: `<app-expo-hall-map #expoMap>` (§6).
* `job-fair`: `<pinch-zoom class="job-fair-zoom" [autoZoomOut]="false" [doubleTap]="true" [wheel]="true" [draggableImage]="false" [limitZoom]="'original image size'" backgroundColor="#ffffff">` wrapping `.job-fair-canvas` (relative, width 100 %) → `<img src="assets/img/floor-plans/job-fair.jpg" alt="Job Fair & Community Showcase floor plan" decoding="async">` width 100 %, `user-select:none`, `-webkit-user-drag:none`. Host `.job-fair-zoom` 100 %×100 % white.
* Segment panes are `*ngIf`, so switching segments **destroys and recreates** the pane (Expo Hall search text, selected booth, zoom/pan position are lost on switch; sponsors are re-read from the in-memory provider cache).

**Navigation out.** Floor plan card → modal. Everything else stays in page.

**Complexity: 3** — segment shell is simple, but it carries the deep-link choreography and a third-party iframe (web view) plus a pinch-zoom pane.

---

## 6. ExpoHallMapComponent (`<app-expo-hall-map>`)

Hosted only inside ConferenceMapPage's `expo-hall` segment. Public API used by the host: `zoomToBoothId(id)`, `toggleSearch()`.

### 6.1 Booth geometry — how coordinates are stored

`BoothData { id, name, top, left, width, height, imgW, imgH, logoUrl?, level?, description? }`. The component ships a **hard-coded array of 61 booths**, each a pixel rectangle `{top,left,width,height}` measured in a **9931 × 7021** reference raster (`imgW`/`imgH` are repeated on every row). The shipped image `assets/img/pycon-us-2026-floorplan-nologo.jpg` is actually **4966 × 3511** (exactly half the reference in each axis; aspect 1.4144 vs 1.4145), which is harmless because rendering only ever uses ratios:

```
getBoothStyle(b) = { top: calc(b.top/b.imgH*100%), left: calc(b.left/b.imgW*100%),
                     width: calc(b.width/b.imgW*100%), height: calc(b.height/b.imgH*100%) }
```
applied as `[ngStyle]` to an absolutely-positioned `.boothgroup` inside `.map-inner` (`position:relative; display:inline-block; width:100%`) whose only other child is the `<img>` at `width:100%; height:auto`. So booth boxes are **percentages of the rendered image box** and scale with it (and with the pinch-zoom CSS transform, since they are inside the transformed element).

Full table (id → seed name; top, left, width, height in 9931×7021 px):

| id | seed name | top | left | w | h |
|---|---|---|---|---|---|
| 245 | Lerner Python Training | 809 | 3906 | 480 | 330 |
| 344 | Zyte | 809 | 4393 | 390 | 330 |
| 243 | Analog Devices | 1145 | 3906 | 480 | 330 |
| 342 | marimo | 1144 | 4392 | 390 | 330 |
| 539 | Posit, PBC | 1203 | 6867 | 458 | 651 |
| 638 | AlphaSense | 1201 | 7330 | 415 | 660 |
| 639 | Snowflake | 1168 | 7858 | 460 | 700 |
| 140 | Chonkie | 1470 | 2372 | 428 | 332 |
| 141 | Tetrix | 1466 | 2932 | 380 | 335 |
| 240 | Old Mission | 1468 | 3318 | 475 | 335 |
| 138 | Sublimage | 1807 | 2371 | 429 | 330 |
| 238 | Jinja.App | 1810 | 3319 | 475 | 330 |
| 136 | Capisclo | 2144 | 2370 | 430 | 330 |
| 137 | Arcjet | 2143 | 2922 | 391 | 325 |
| 236 | Minimus | 2146 | 3319 | 477 | 322 |
| 237 | Tower Research Capital | 2144 | 3893 | 502 | 335 |
| 134 | PixelTable | 2479 | 2372 | 427 | 332 |
| 135 | TimeCopilot | 2474 | 2922 | 390 | 344 |
| 234 | Python Institute | 2474 | 3318 | 440 | 345 |
| 235 | Elastic | 2483 | 3977 | 410 | 316 |
| 334 | Apify | 2475 | 4392 | 400 | 340 |
| 335 | Pydantic | 2157 | 4938 | 442 | 650 |
| 434 | Red Hat | 2155 | 5386 | 420 | 650 |
| 126 | Cloudflare | 2877 | 2356 | 460 | 640 |
| 127 | Hudson River Trading | 2873 | 2826 | 486 | 648 |
| 226 | Kraken Tech | 2871 | 3317 | 430 | 660 |
| 122 | Sentry | 3526 | 2358 | 465 | 645 |
| 116 | Cubist Systematic Strategies | 4230 | 2278 | 545 | 654 |
| 112 | Jane Street | 4890 | 2349 | 470 | 640 |
| 119 | AWS | 3955 | 2980 | 650 | 740 |
| 113 | Capital One | 4789 | 2981 | 650 | 740 |
| 427 | SerpApi | 2850 | 6130 | 730 | 765 |
| 531 | Chainguard | 2629 | 6906 | 425 | 665 |
| 630 | Hex | 2627 | 7336 | 415 | 667 |
| 421 | JetBrains | 3676 | 6126 | 730 | 730 |
| 621 | Codespeed | 3732 | 7845 | 425 | 685 |
| 720 | QUBE Research & Technologies | 3726 | 8275 | 480 | 690 |
| 635 | ClickHouse | 1970 | 7880 | 400 | 330 |
| 734 | Djangonauts / DSF | 1970 | 8282 | 440 | 328 |
| 735 | Python en Español | 1976 | 9132 | 430 | 320 |
| 633 | Reflex | 2306 | 7876 | 400 | 330 |
| 732 | Black Python Devs | 2302 | 8281 | 440 | 330 |
| 733 | EuroPython Society | 2302 | 9133 | 430 | 330 |
| 631 | Auth0 | 2641 | 7861 | 415 | 330 |
| 730 | CodeDay | 2642 | 8283 | 440 | 331 |
| 731 | PyLadies | 2635 | 9137 | 425 | 336 |
| 629 | Temporal | 2976 | 7859 | 420 | 330 |
| 728 | SCaLE / Data Con LA / San Diego Python / Inland Empire PUG | 2976 | 8283 | 440 | 330 |
| 729 | Python Asia Organization | 2976 | 9133 | 430 | 330 |
| 627 | ReversingLabs | 3311 | 7861 | 417 | 368 |
| 726 | Pybeach / SoCal Python | 3310 | 8285 | 523 | 370 |
| 727 | PyCon Africa / Seneg. / Mozambique | 3310 | 9072 | 490 | 400 |
| 213 | Microsoft | 4477 | 4042 | 660 | 1060 |
| 313 | Anaconda | 4803 | 4957 | 680 | 730 |
| 413 | Meta | 4485 | 6151 | 700 | 1070 |
| 513 | Vercel | 4799 | 6988 | 700 | 753 |
| 613 | Bloomberg | 4488 | 7913 | 700 | 1070 |
| 407 | PSF | 5727 | 6172 | 640 | 740 |
| 606 | Attendee Lounge | 5724 | 6818 | 960 | 740 |
| 709 | CesiumAstro | 5788 | 8883 | 390 | 390 |
| 713 | Codeflash | 4857 | 8840 | 437 | 670 |

Static logo fallbacks `STATIC_BOOTH_LOGOS`: `'407' → 'assets/img/python-logo.png'`, `'606' → 'assets/img/pycon-us-2026-logo.svg'` (seeded before the API merge, only when `logoUrl` is still unset).

**Feed ↔ geometry reconciliation (current feed):** 61 sponsors have a `booth_number`; 59 match a geometry row. Feed booths **without geometry** (cannot be found on the map; `?booth=` deep link silently no-ops): `139` (Phemeral, Startup Row) and `336` (Astral, Partner). Geometry rows **without a feed sponsor**: `407` (PSF) and `606` (Attendee Lounge) — they keep their seed names, get the static logos and have no `level`, so their popup is *not* a link. 13 seed names are overwritten by the feed on load (e.g. `Sublimage` → `SubImage`, `Codespeed` → `CodSpeed`, `Anaconda` → `Anaconda, Inc`, `Pybeach / SoCal Python` → `San Diego Python`, `SCaLE / …` → `SCaLE`), which matters because the popup's sponsor-detail link is built from `getSponsorSlug(booth.name)` — it only resolves because the name is replaced by the exact feed name.

### 6.2 Data flow

`ngOnInit()` → `loadSponsors()` (no loader): seed static logos; `confData.getSponsors().subscribe(apply)`; `apply(sponsors)`: for every sponsor in every level array with `booth_number != null`, find `booths.find(b => b.id === String(sponsor.booth_number))` and set `logoUrl = sponsor.logo_url`, `level = sponsor.level`, `description = sponsor.description`, and `name = sponsor.name` if truthy. (`loadSponsors(true)` with a `'Fetching latest...'` loader exists but is never invoked.) Booth objects are mutated in place; both emissions of `load()` re-apply.

### 6.3 Zoom / pan (`@ciag/ngx-pinch-zoom`)

Template: `<pinch-zoom #pinchZoom class="expo-hall-map" [autoZoomOut]="false" [doubleTap]="true" [wheel]="true" [draggableImage]="false">` → `.map-inner` → `<img src="assets/img/pycon-us-2026-floorplan-nologo.jpg" alt="PyCon US 2026 Expo Hall Floor Plan" decoding="async">` + 61 `.boothgroup` overlays. No `limitZoom`, no `backgroundColor` are passed, so library defaults apply: `backgroundColor "rgba(0,0,0,0.85)"` (the landscape image fits the width and leaves the rest of the tall host **near-black**), `limitZoom "original image size"`, `transitionDuration 200`, `doubleTapScale 2`, `minScale 0`, `minPanScale 1.0001`, `limitPan false`, `overflow hidden`, `wheelZoomFactor 0.2`, `listeners "mouse and touch"`, `disableZoomControl "auto"` (a floating zoom button is shown on **non-touch** devices only).

Hack 1 — max scale: the library hard-codes `defaultMaxScale = 3` unless its first descendant is an `<img>` and `limitZoom === 'original image size'`; here the first child is a `<div>`, and a numeric `limitZoom` is ignored. So `ngAfterViewInit()` polls every **50 ms for up to 2000 ms** for the inner IvyPinch instance (`pinchZoomCmp.pinchZoom`), then sets **`maxScale = 25`**, flags `pinchReady = true`, and flushes a `pendingBoothId` if one was queued.

Hack 2 — programmatic zoom-to-booth bypasses `setZoom()` because `setZoom → centeringImage → limitPanY` assumes the image fills the host and would clamp the booth to the top of the viewport. Algorithm (`zoomToBooth`):
1. Guard: need IvyPinch instance, host element with `offsetWidth`. If the `<img>` is not `complete`/has `naturalWidth 0`/`offsetHeight 0`, `await` its `load` event with a **5 s** safety timeout. Abort if a newer request (`zoomToken`) superseded this one.
2. Constants: `DEEPLINK_ZOOM_SCALE S = 6`, `DEEPLINK_POPUP_OFFSET_PX = 60` (popup ≈110 px tall on 390×844; lift target by half).
3. `W = host.offsetWidth`, `H = host.offsetHeight`, `imgDisplayH = W * imgH/imgW`; `mapInnerTop/Left = .map-inner.offsetTop/offsetLeft` (non-zero because `inline-block` baseline alignment shifts it); `fracX = (left + width/2)/imgW`, `fracY = (top + height/2)/imgH`; `boothPx = mapInnerLeft + fracX*W`, `boothPy = mapInnerTop + fracY*imgDisplayH`;
   `moveX = W/2 − S·boothPx`, `moveY = (H/2 − 60) − S·boothPy`.
4. `inner.scale = S; inner.moveX = moveX; inner.moveY = moveY; inner.transformElement(inner.properties.transitionDuration ?? 200); inner.updateInitialValues();`
5. After **250 ms**: `selectedBooth = booth; highlightedBoothId = booth.id` (popup + ring appear once the zoom animation has landed).
`zoomToBoothId(id)`: no-op if falsy; if `!pinchReady` → store as `pendingBoothId`; else find booth (no-op if unknown id), bump `zoomToken`, `requestAnimationFrame(() => zoomToBooth(booth, token))`. **There is deliberately no "already zoomed to this id" guard** — the same id twice re-centres (user may have panned away).

### 6.4 Search / selection / popup

* `toggleSearch()`: flips `showSearchbar`; closing → `clearSearch()`; opening → `setTimeout(() => searchBar.setFocus(), 150)`.
* Search toolbar (`*ngIf="showSearchbar"`, `.expo-hall-search-toolbar` `position:sticky; top:0; z-index:110`): `<ion-searchbar #searchBar [debounce]="250" showCancelButton="always" [(ngModel)]="searchQuery" (ionChange)="onSearch()" (ionClear)="clearSearch()" (ionCancel)="clearSearch()" placeholder="Search sponsors...">`.
* `onSearch()`: `q = searchQuery.toLowerCase().trim()`; empty → `[]`; else `booths.filter(b => b.name.toLowerCase().includes(q) || b.id.includes(q))` (matches current/overwritten names and booth numbers).
* Results `.search-results` (absolute top/left/right 0, `z-index:100`, bg `var(--ion-background-color,#fff)`, bottom border `--ion-color-light`, `max-height:40vh`, scroll) → `.search-result-item` rows (flex space-between, padding `12px 16px`, bottom border, `:active` bg light): `.booth-name` (clamp(.8rem,2.5vw,1rem), 600) and `.booth-number` "Booth {{id}}" (clamp(.7rem,2vw,.85rem), medium).
* `selectBooth(b)`: clear results/query/hide searchbar; `highlightedBoothId = b.id; selectedBooth = b`; after 100 ms `document.getElementById('boothgroup-'+id)?.scrollIntoView({behavior:'smooth', block:'center', inline:'center'})` — best-effort centring **without changing zoom**; the booth lives inside a CSS-transformed, overflow-hidden container with `ion-content` scrolling disabled, so in practice this may barely move anything.
* `clearSearch()`: query `''`, results `[]`, `showSearchbar=false`, `highlightedBoothId=null` (keeps `selectedBooth`).
* `onBoothTap(b)` (click on `.boothgroup`): `selectedBooth = b; highlightedBoothId = b.id` (no zoom).
* `closePopup()`: both `null`.
* Booth visuals: `.booth` fills its group (`inset:0`, radius 4, `transition: background .15s`); `:hover/:active` → bg `rgba(240,192,64,.28)` + `outline 2px solid rgba(240,192,64,.85)`; `.highlighted .booth` → bg `rgba(240,192,64,.35)`, `outline 3px solid #f0c040`, `animation: pulse 1.2s ease-in-out 2` (bg .15 → .45 → .15). Booth boxes are **invisible until hovered/selected** (logos and numbers are printed in the raster). `.booth-img` CSS exists but no `<img>` is rendered inside booths (comment: it duplicated the printed mark).
* Popup `.booth-popup` (`*ngIf="selectedBooth"`, `position:fixed; bottom:0; left:0; right:0; z-index:200; padding:0 16px 16px`; outer `(click)="closePopup()"`; inner `stopPropagation`): `.booth-popup-inner` flex row, gap 12, bg `var(--ion-background-color,#fff)`, **border `2px solid #DD04D2`**, radius 12, padding `14px 16px`, shadow `0 -4px 24px rgba(221,4,210,.25)`:
  * `<img class="booth-popup-logo">` if `logoUrl` (48×48 contain, radius 6).
  * if `selectedBooth.level`: `<a class="booth-popup-content" routerLink="/app/tabs/sponsors/sponsor-detail/<slug(name)>">` with `.booth-popup-name` (clamp(.9rem,3vw,1.1rem), 700) and `.booth-popup-number` "Booth {{id}} · {{level}}" (clamp(.75rem,2.5vw,.9rem), medium) and absolutely-positioned `ion-icon chevron-forward-outline` at right (link gets `padding-right:24px`).
  * else plain `<div class="booth-popup-content">` name + "Booth {{id}}" (no link).
  * `<ion-button fill="clear" size="small" class="close-btn" aria-label="Close booth details"><ion-icon slot="icon-only" name="close-outline">`.

**Native plugins:** none. Uses DOM APIs (`document.getElementById`, `scrollIntoView`, `requestAnimationFrame`, image `load` event).

**Complexity: 5** — pinch/pan/zoom surface with percentage-anchored hit targets that must track the transform, programmatic zoom-to-rect math with layout measurement, async readiness/queuing, search overlay and fixed popup.

---

## 7. FloorPlanModalComponent (`<app-floor-plan-modal>`, presented via `ModalController`)

**Inputs (componentProps):** `title: string`, `imageSrc: string`, `altText?: string`, `pinXPct?: number`, `pinYPct?: number`, `pinLabel?: string`. `hasPin = pinXPct != null && pinYPct != null`. `close()` → `modalCtrl.dismiss()`.

**Presented from:** ConferenceMapPage (5 floor plans, no pin), JobListingsPage (job fair, no pin), SessionDetail (job fair, no pin — only when the session name/`content_override` contains "job fair"), LocationMapComponent (with pin), HelpPage `openInfoDesk()` (Concourse plan with Info Desk pin 55 %/53 %). Default Ionic modal presentation (full-screen sheet on Android, card on iOS); dismissal only via the close button (no `presentingElement`, so no swipe-to-close; hardware back on Android closes it via Ionic).

**UI.** Header `ion-no-border`: start `<ion-button aria-label="Close floor plan"><ion-icon slot="icon-only" name="close-outline">`, `ion-title {{title}}`. `<ion-content fullscreen class="floor-plan-modal-content">` with `--background:#ffffff`; `<pinch-zoom class="floor-plan-zoom" [autoZoomOut]="false" [doubleTap]="true" [wheel]="true" [draggableImage]="false" [limitZoom]="'original image size'" backgroundColor="#ffffff">` (100 %×100 %, white) → `.floor-plan-canvas` (relative, width 100 %) → `<img [src]=imageSrc [alt]="altText || title" decoding="async">` (width 100 %, auto height, no drag/select) + optional `.floor-plan-pin` (`position:absolute; left: pinXPct%; top: pinYPct%; width:0; height:0; pointer-events:none; z-index:2; aria-label = pinLabel || 'Location'`) containing `.floor-plan-pin-pulse` (10 px `#DD04D2`, opacity .5, `animation: floor-plan-pin-pulse 1.8s ease-out infinite` scaling 1→3 and fading .45→0) and `.floor-plan-pin-dot` (10 px `#DD04D2`, `1.5px solid #fff` border, shadow `0 0 0 1.5px rgba(0,0,0,.18), 0 1px 3px rgba(0,0,0,.45)`), both centred with `translate(-50%,-50%)`.

Because the pin is a child of the transformed canvas, it moves with pan/zoom but its 10 px dot **also scales up** with the zoom (no counter-scaling). With `limitZoom 'original image size'` and a 2200-px-wide plan on a ~390-px viewport, max zoom ≈ 5.6×; for the 1700-px portrait plans ≈ 4.4×.

**Complexity: 3** — zoomable image is easy; a percentage-anchored, animated pin that must stay registered under pinch/pan is the work.

---

## 8. LocationMapComponent (`<app-location-map>`) + `ROOM_LOCATIONS` / `VENUE_LOCATIONS`

**Inputs:** `label!`, `sublabel?`, `floorTitle!`, `thumbSrc!`, `fullSrc!`, `pinXPct!`, `pinYPct!`. One action: `openFull()` → `FloorPlanModalComponent` with `{ title: floorTitle, imageSrc: fullSrc, altText: '<floorTitle> floor plan with <label> highlighted', pinXPct, pinYPct, pinLabel: label }`.

**UI (a single `<button class="location-map">`, aria-label `"Show <label> on the <floorTitle> floor plan"`).** Horizontal card: width 100 %, bg `var(--ion-card-background,#fff)`, border `1px solid var(--ion-color-step-150, rgba(0,0,0,.08))`, radius 14, overflow hidden, `:active` `scale(.985)` + shadow.
* Left `.location-map-thumb`: fixed **144 px** wide, white, right border, `font-size:0`; `<img [src]=thumbSrc [alt]="floorTitle + ' floor plan'">` full width/auto height; `.location-map-pin` at `left:pinXPct%; top:pinYPct%` (aria-hidden) with 8 px dot (`#DD04D2`, 1.5 px white border, shadow) and 8 px pulse (`opacity .55`, `location-map-pin-pulse 1.8s ease-out infinite`, scale 1→2.6, opacity .5→0); `.location-map-zoom-hint` 24 px circle bottom-right 6 px, bg `rgba(0,0,0,.55)`, white `expand-outline` 14 px.
* Right `.location-map-meta` (flex 1, padding `12px 14px`, column, centred): `.location-map-label` 16 px/600 text colour; `.location-map-sublabel` 13 px step-650 (if any); `.location-map-floor` 12 px medium, uppercase, letter-spacing .04em.

Pins are percentages of the image box, so the same (x,y) works on thumb and full image (thumbs are exact aspect-ratio reductions: 800×618 ↔ 2200×1700, 618×800 ↔ 1700×2200).

**Where it is rendered.**
* `pages/room-detail` (outside slice): `roomLocation = getRoomLocation(room.name)`; `<div class="room-location-map">` (padding `16px 16px 0`) with the card, under the room hero.
* `pages/venues-hours`: one card under each HTML section that matched a venue location (§9).
* `pages/help`: `VENUE_LOCATIONS['infoDesk']` card inside the "At the Conference" list (`.help-info-desk-map` padding `8px 16px 12px`).

**`venue-locations.ts`** — `VenueLocation { key, label, sublabel?, floorTitle, thumbSrc, fullSrc, pinXPct, pinYPct }`; `VENUE_LOCATIONS`:

| key | label | sublabel | floor | pin x,y % |
|---|---|---|---|---|
| `infoDesk` | Information Desk | Promenade Lobby (Main Entrance) | Concourse Level (plan 1) | 55, 53 |
| `registration` | Registration | Promenade Lobby (Main Entrance) | Concourse Level | 67, 58 |
| `quietRoom` | Attendee Quiet Room | VIP Room A & B | Concourse Level | 58, 36 |
| `swagPickup` | Swag Pickup | Expo Hall A & B | Arena & Exhibit Halls (plan 3) | 42, 68 |
| `lostAndFound` | Lost & Found | Info Desk during open hours; Staff Office overnight | Upper Level (plan 2) | 40, 58 |
| `staffOffice` | Staff Office | Room 203 A & B | Upper Level | 40, 58 |

**`room-locations.ts`** — `ROOM_LOCATIONS_RAW` (51 entries) built with helpers `concourse(label,x,y,sublabel)`, `upper(...)`, `arena(...)`, `seaside(...)` that fill `floorTitle/thumbSrc/fullSrc` (Concourse Level=plan-1, Upper Level=plan-2, Arena & Exhibit Halls=plan-3 [portrait 1700×2200], Seaside Meeting Rooms=plan-4). `key` = normalized name; `label` is the display name. Lookup: `normalizeRoomKey(name) = name.toLowerCase().replace(/^room\s+/i,'').replace(/[^a-z0-9]+/g,'')` (so `Room 102A`, `102A`, `room 102a` → `102a`); `getRoomLocation(name)` returns the entry or `null`. `export const ROOM_LOCATIONS = ROOM_LOCATIONS_RAW`.

| key | label | x,y | sublabel |
|---|---|---|---|
| `101a` | Room 101A | 14,50 | Tutorials / PSF Members Lunch / PyLadies Lunch |
| `101b` | Room 101B | 19,50 | same |
| `101ab` | Room 101AB | 17,50 | same |
| `102a` / `102b` / `102c` | Room 102A/B/C | 23,50 / 27,50 / 31,50 | Tutorials / Open Spaces |
| `103a` / `103b` / `103c` | Room 103A/B/C | 39,50 / 43,50 / 46,50 | Talk Track / Security Track |
| `103abc` | Room 103 | 43,50 | Talk Track / Security Track |
| `104a` / `104b` | Room 104A/B | 72,38 / 80,35 | Talk Track |
| `104c` | Room 104C | 84,27 | Education Summit / Charlas / Open Spaces |
| `104ab` | Room 104AB | 76,37 | Talk Track |
| `104abc` | Room 104 | 78,33 | Talk Track / Education Summit |
| `201a` | Room 201A | 7,59 | Summits / Open Spaces |
| `201b` | Room 201B | 14,59 | Sponsor Presentations / Open Spaces |
| `202a` / `202b` / `202c` | Room 202A/B/C | 19,59 / 23,59 / 27,59 | Sponsor Presentations / Open Spaces |
| `203a` / `203b` | Room 203A/B | 36,59 / 41,59 | Staff Office |
| `203c` | Room 203C | 45,59 | Green Room / Speaker Ready Room |
| `204` | Room 204 | 60,48 | AV Room |
| `grandballrooma` | Grand Ballroom A | 76,36 | AI Track / Talk Track |
| `grandballroomb` | Grand Ballroom B | 84,50 | Talk Track |
| `grandballroom` | Grand Ballroom | 80,43 | Talk Tracks |
| `pacificballroomarena` | Pacific Ballroom — Arena | 60,16 | Keynotes, Lightning Talks, General Sessions |
| `arena` | Arena | 60,16 | same |
| `halla` / `hallb` / `hallc` | Hall A/B/C | 18,72 / 43,63 / 58,55 | Exhibit Hall |
| `hallab` | Hall AB | 32,67 | Expo Hall — Booths, Job Fair, Community Showcase |
| `expohallab` | Expo Hall AB | 32,67 | Booths, Job Fair, Community Showcase |
| `expohallc` | Expo Hall C | 58,55 | Posters, Open Spaces |
| `expohall` | Expo Hall | 38,64 | Booths, Job Fair, Community Showcase |
| `s1` | S-1 | 85,63 | Sprints |
| `s2` | S-2 | 53,57 | Sprints |
| `s3` / `s3a` / `s3b` | S-3 / S-3A / S-3B | 58,68 / 60,68 / 55,68 | Open Spaces / Sprints |
| `s4` | S-4 | 46,68 | Web Assembly Summit / Open Spaces / Sprints |
| `s4a` | S-4A | 49,68 | Open Spaces / Sprints |
| `s4b` | S-4B | 44,68 | Web Assembly Summit / Open Spaces / Sprints |
| `s5` / `s5b` | S-5 / S-5B | 45,24 / 43,24 | Open Spaces / Sprints |
| `s5a` | S-5A | 47,24 | Sprints |
| `s6` | S-6 | 53,24 | Sprints |
| `s7` | S-7 | 80,27 | Satellite Staff Office |
| `seasidelobby` | Seaside Lobby | 33,44 | Sprints |
| `seasideballrooma` / `b` | Seaside Ballroom A / B | 55,44 / 44,44 | PyLadies Auction / Sprints |
| `seasideballroom` | Seaside Ballroom | 50,44 | PyLadies Auction / Sprints |

Side effect outside the UI: `ConferenceData.processData()` iterates `ROOM_LOCATIONS` and **seeds an empty room** (`{name: loc.label, slug: slugifyRoom(label), sessions: []}`) for every entry whose `sublabel` matches `/sprints/i`, so sprint-only Seaside rooms appear in the Rooms list even though no schedule slot references them (PYMOBIL-120). Note `slugifyRoom` (`[^a-z0-9]+ → '-'`, trim dashes) differs from `normalizeRoomKey` and from `getSponsorSlug`.

**Complexity: 2** (card) — but the data tables are the real asset to carry over verbatim.

---

## 9. VenuesHoursPage — `/app/tabs/venues-hours`

**Route / reach.** Side menu → "Venue & Hours".

**Data / lifecycle.** `ngOnInit()`: `forkJoin({ content: getContent(), sponsors: getSponsors() }).subscribe(({content, sponsors}) => { this.content = content; sections = buildSections(content?.['venues-hours'] || '', flattenSponsors(sponsors)); detectChanges(); })`. **`forkJoin` emits only when both complete**, and `load()` completes only after the network response (or after the network error when a cache was served). Consequence: this page shows **no sections until the HTTP fetch finishes or times out (10 s)**, even with a warm cache — unlike other pages that render the cached emission immediately. If `load()` errors with no cache, `forkJoin` errors and the page shows only hero + the two static list items.

`buildSections(html, sponsors)`: `DOMParser.parseFromString('<div id="root">'+html+'</div>','text/html')`; iterate `root.childNodes`; every `H1|H2|H3` element starts a new section (`flush()` the previous); each section = `{ html: sanitizer.bypassSecurityTrustHtml(innerHTML), location: matchLocation(firstHeadingText.toLowerCase()), sponsor? }` where the heading is the first `h1…h6` inside the chunk; if heading text includes `'quiet room'` → `sponsor = findSponsorByName(sponsors,'google')` (first sponsor whose lower-cased name *includes* `google` → `{name, logo_url, slug}`). If DOMParser yields no root → single section with the whole HTML.
`matchLocation(text)` (first match wins): includes `'information desk'` or `'info desk'` → `infoDesk`; includes `'registration'` → `registration`; includes `'swag pickup'` or `'t-shirt'` → `swagPickup`; includes `'quiet room'` → `quietRoom`; includes `'lost'` **and** `'found'` → `lostAndFound`; else none (`staffOffice` is never matched here).
With the current feed this yields 7 sections: (1) `Dates, Times, Locations` + address + "All times US/Pacific" (no map); (2) Registration (pin); (3) Information Desk (pin); (4) Swag Pickup (pin, Arena plan); (5) Attendee Quiet Room (pin + "Sponsored by Google" card); (6) Lost & Found (Room 203AB) (pin, Upper plan); (7) Luggage Check (no map).

`openDirections()`: constants `PINE_AVE_LAT = 33.764444`, `PINE_AVE_LNG = -118.191722`, `PINE_AVE_LABEL = 'Long Beach Convention Center (Pine Ave Entrance)'`;
* `platform.is('ios')` → `https://maps.apple.com/?q=<encodeURIComponent(label)>&ll=<lat>,<lng>&dirflg=w` (walking);
* `platform.is('android')` → `geo:<lat>,<lng>?q=<lat>,<lng>(<encodeURIComponent(label)>)`;
* else (PWA/web) → `https://www.google.com/maps/search/?api=1&query=<lat>,<lng>`;
then `window.open(url,'_system','location=yes')`.
`openUrl(url)` helper exists (unused in template).

**UI structure.**
* Branded header as in Sponsors (solid `#3B3EA9`, hidden title "Venue & Hours" fades in after 100 px, white menu button).
* `.venues-hero` (gradient, white, centred, padding `16px 24px 32px`): `.venues-hero-title` row (gap 12) with `ion-icon location` 36 px `#DD04D2` and `<h1>Venue & Hours</h1>` (1.6 rem/700); `<p>Long Beach Convention &amp; Entertainment Center</p>` (.95 rem, opacity .9); `<p class="venues-address">300 E Ocean Blvd, Long Beach, CA 90802</p>` (.8 rem, opacity .65).
* `.venues-content.ion-padding` (`*ngIf="sections.length"`): per section `<div class="venues-section" [innerHTML]="section.html">`, then `.venues-section-map` (margin `8px 0 16px`) with `<app-location-map …>` if `section.location`, then `<a class="venues-section-sponsor" routerLink="/app/tabs/sponsors/sponsor-detail/<slug>">` if `section.sponsor`: flex row gap 12, margin `-4px 0 20px`, padding `10px 12px`, radius 10, bg `rgba(88,51,233,.06)`; logo 44×44 contain white radius 8 padding 4; text column with eyebrow "Sponsored by" (.7 rem uppercase, letter-spacing .05em, medium) and name (.95 rem/700 `#5833E9`); `ion-icon chevron-forward` medium 1 rem.
  Inner HTML typography: `h2` 1.15 rem/700 `#5833E9` margin `24px 0 4px`; `h3` 1 rem/600 margin `16px 0 4px`; `p` margin `4px 0`, lh 1.5; `ul` padding-left 20, margin `8px 0`; `li` margin `4px 0`, lh 1.5.
* `<ion-list lines="full">`: item 1 `button detail (click)="openDirections()"`: `ion-icon navigate-outline color="primary" slot="start"`, label `<h2>Get Directions</h2><p>Pine Ave entrance · Open in Maps</p>`; item 2 `button detail routerLink="/app/tabs/conference-map"`: `ion-icon map-outline color="primary"`, `<h2>Conference Maps</h2><p>Indoor venue layout</p>`.
* 80 px spacer.

**Native/platform:** Ionic `Platform.is('ios'|'android')`; `window.open(... '_system')`; `DomSanitizer.bypassSecurityTrustHtml`; browser `DOMParser`.

**Complexity: 3** — CMS HTML must be split on headings and rendered as rich text with interleaved native cards; platform-specific maps URL.

---

## 10. Shared logic in this slice

### 10.1 Copy-pasted helpers (identical bodies, no shared module)

| Helper | Copies | Body |
|---|---|---|
| `getSponsorSlug(name)` | sponsors, sponsor-detail, job-listings (null-safe `(name||'')`), expo-hall-map, venues-hours (private), tabs-page `goToSponsor`, wifi page | `name.toLowerCase().replace(/\s+/g,'-').replace(/[^a-z0-9-]/g,'')` |
| `parseRoles(html)` | sponsor-detail (`{title,url}`), job-listings (`{title,location:'',url}`) | 1) `text` = html with tags → space, `&amp;/&lt;/&gt;` decoded, whitespace collapsed, trimmed. 2) `urls = html.match(/https?:\/\/[^\s<>"]+/g)` (**searches the raw HTML, so `href` values are found**). 3) no urls → `[{title:text,url:''}]` if text else `[]`. 4) for each url: `idx = remaining.indexOf(url)` **in the stripped text** — only ≥0 when the URL is visible anchor text; `before = remaining[0:idx]` with trailing `[-|–,]` stripped; title = last non-empty line of `before` with leading `[-|–]` stripped, accepted if `0 < len < 200`, else `shortenUrl(url)`; if `before` empty → `shortenUrl(url)`; `remaining` = rest after the url with leading `[-|–,]` stripped. 5) if nothing parsed and text non-empty → `[{title:text,url:''}]`. |
| `shortenUrl(url)` | sponsor-detail, job-listings | `new URL(url)`; last non-empty path segment with `-`→space and first letter upper-cased; else hostname; on parse error return url. |
| `openUrl(url)` | sponsor-detail, job-listings, venues-hours (+ many other pages) | `if (url) window.open(url, '_system', 'location=yes')` |
| `onScroll(e)` / `showTitle` | sponsors, job-listings, venues-hours (and other branded pages) | `showTitle = e.detail.scrollTop > 100` toggles `.title-visible` on the toolbar title |
| Loader pattern | sponsors (`reloadSponsors`), expo-hall-map (`loadSponsors(true)`, unused) | `LoadingController.create({message:'Fetching latest...', duration:10000})`, dismiss via `setTimeout(…,100)` after first emission |
| Branded header + hero | sponsors, job-listings, venues-hours (sponsor-detail hero variant) | header `#3B3EA9`, hero gradient `180deg #3B3EA9 23.5% → #101136 53.29%`, white centred text, 80 px bottom spacer |

### 10.2 Constants / magic numbers

| Where | Name | Value |
|---|---|---|
| expo-hall-map | reference raster | 9931 × 7021 px (image file is 4966 × 3511) |
| expo-hall-map | `DEEPLINK_ZOOM_SCALE` | 6 |
| expo-hall-map | `DEEPLINK_POPUP_OFFSET_PX` | 60 |
| expo-hall-map | IvyPinch `maxScale` override | 25 (library default 3) |
| expo-hall-map | readiness poll | every 50 ms, up to 2000 ms |
| expo-hall-map | image-load wait cap | 5000 ms |
| expo-hall-map | popup/highlight delay after zoom | 250 ms; after search select 100 ms; searchbar focus 150 ms |
| expo-hall-map | highlight colour | `#f0c040`, `rgba(240,192,64,.28/.35/.85)`, pulse 1.2 s × 2 |
| expo-hall-map / floor-plan-modal / location-map | accent magenta | `#DD04D2` |
| floor-plan-modal / location-map | pin pulse | 1.8 s ease-out infinite; dot 10 px (modal) / 8 px (card); pulse scale 3 (modal) / 2.6 (card) |
| conference-map | 3D tour URL | `https://map.concept3d.com/?id=1802` |
| venues-hours | Pine Ave entrance | 33.764444, −118.191722; label `Long Beach Convention Center (Pine Ave Entrance)` |
| venues-hours | address strings | `Long Beach Convention & Entertainment Center`, `300 E Ocean Blvd, Long Beach, CA 90802` |
| venues-hours | sponsor match needle | `'google'` for the Quiet Room |
| job-listings / expo search | searchbar debounce | 250 ms |
| all list pages | title reveal threshold | `scrollTop > 100` |
| provider | HTTP timeout | 10 000 ms; storage key `schedule-cache`; DB `__pycon_us_mobile_2026` |
| sponsor detail | level badge bg | `#5833E9` |
| job listings | hero icon colour | `#25C8EB` |

### 10.3 Pipes / enums
* Angular `keyvalue` pipe with custom comparator (Sponsors). `lowercase` pipe is not used in this slice.
* `MapView` union type (`'floor-plans' | '3d-tour' | 'expo-hall' | 'job-fair'`); `FloorPlan` interface; `BoothData`; `VenueLocation`; `RoomLocation = VenueLocation with optional sublabel`; `VenueSection { html, location?, sponsor? }`.

---

## 11. Assets referenced

| File | Bytes | Pixels | Used by |
|---|---|---|---|
| `assets/img/floor-plans/campus-map-thumb.jpg` | 86 266 | 800×618 | ConferenceMap card |
| `assets/img/floor-plans/campus-map.jpg` | 369 109 | 2200×1700 | FloorPlanModal (Campus Overview) |
| `assets/img/floor-plans/floor-plan-1-thumb.jpg` | 76 186 | 800×618 | ConferenceMap card; LocationMap thumbs (Concourse) |
| `assets/img/floor-plans/floor-plan-1.jpg` | 376 953 | 2200×1700 | FloorPlanModal (Concourse Level) |
| `assets/img/floor-plans/floor-plan-2-thumb.jpg` | 54 048 | 800×618 | card; LocationMap (Upper) |
| `assets/img/floor-plans/floor-plan-2.jpg` | 271 217 | 2200×1700 | modal (Upper Level) |
| `assets/img/floor-plans/floor-plan-3-thumb.jpg` | 88 605 | 618×800 (portrait) | card; LocationMap (Arena) |
| `assets/img/floor-plans/floor-plan-3.jpg` | 427 658 | 1700×2200 (portrait) | modal (Arena & Exhibit Halls) |
| `assets/img/floor-plans/floor-plan-4-thumb.jpg` | 76 062 | 800×618 | card; LocationMap (Seaside) |
| `assets/img/floor-plans/floor-plan-4.jpg` | 351 222 | 2200×1700 | modal (Seaside Meeting Rooms) |
| `assets/img/floor-plans/job-fair-thumb.jpg` | 72 460 | 618×787 | Job Listings card; SessionDetail job-fair card |
| `assets/img/floor-plans/job-fair.jpg` | 348 136 | 1700×2164 | ConferenceMap "Job Fair" segment; modal from Job Listings / SessionDetail |
| `assets/img/pycon-us-2026-floorplan-nologo.jpg` | 1 305 507 | 4966×3511 | ExpoHallMap base image |
| `assets/img/pycon-us-2025-floorplan.png` | 1 602 176 | 4096×2885 | **unreferenced** (last year's map; drop) |
| `assets/img/python-logo.png` | 83 564 | — | static logo for booth 407 (PSF) |
| `assets/img/pycon-us-2026-logo.svg` | 51 261 | — | static logo for booth 606 (Attendee Lounge) |
| Remote sponsor logos | — | — | `https://s3.dualstack.us-east-2.amazonaws.com/pythondotorg-assets/media/sponsor_web_logos/*.png` (not cached by the app beyond HTTP cache) |
| Ionicons used | — | — | `heart`, `briefcase`, `briefcase-outline`, `location`, `location-outline`, `storefront-outline`, `people-outline`, `globe-outline`, `chevron-forward`, `chevron-forward-outline`, `expand-outline`, `search`, `close-outline`, `navigate-outline`, `map-outline`, `map`, `business-outline` |

Total floor-plan JPEG payload ≈ 2.6 MB + 1.3 MB expo raster.

---

## 12. Deep-link chains (how a highlighted room/booth is reached)

1. **Sponsor → booth on Expo Hall map:** SponsorDetail chip `Expo Booth N` → `navigateRoot('/app/tabs/expo-hall', {booth:'N'})` → ConferenceMapPage (`initialView: 'expo-hall'`, title "Expo Hall") → `ionViewWillEnter` reads `?booth` → forces segment `expo-hall` → `setTimeout 0` → `ExpoHallMapComponent.zoomToBoothId('N')` → (queue until IvyPinch ready; wait for image) → scale 6 centred on booth centre lifted 60 px → after 250 ms popup + yellow ring. Unknown/missing id (e.g. `139`, `336`) → nothing happens, page just shows the map. Re-entering with the same id re-centres. Also honoured on cold-start deep links to `/app/tabs/expo-hall?booth=N`.
2. **Session → room → floor plan pin:** SessionDetail `session.roomLinks[]` (`{name, slug}` computed in the provider by splitting `session.location`) → `routerLink ['/app/tabs/rooms/room-detail', slug]` with `queryParams {prevUrl, session: id}` → RoomDetailPage `getRoom(slug)` → `getRoomLocation(room.name)` (normalised key lookup in `ROOM_LOCATIONS`) → `<app-location-map>` card with pulsing pin on the floor thumb → tap → FloorPlanModal with the same pin on the full plan. Rooms with no entry (unknown names) show no card. Rooms list (`/app/tabs/rooms`) → room-detail uses the same path.
3. **Session "Job Fair" → floor plan:** SessionDetail shows the "View Job Fair Floor Plan" card when `(name + content_override).toLowerCase()` contains `'job fair'` → FloorPlanModal (no pin).
4. **Venue & Hours section → pin:** heading-keyword → `VENUE_LOCATIONS` entry → card → modal with pin.
5. **Help → Information Desk:** `VENUE_LOCATIONS.infoDesk` card (and `openInfoDesk()` helper) → modal with pin; "Full Conference Maps" item → `/app/tabs/conference-map`.
6. **Expo popup → sponsor:** `routerLink /app/tabs/sponsors/sponsor-detail/<slug(booth.name)>` only when `booth.level` is set (i.e., the booth was matched to a feed sponsor).
7. **Job listing → sponsor:** sponsor header → sponsor detail by slug of `sponsor_name`.
8. **Back behaviour:** SponsorDetail's back button falls back to `/app/tabs/sponsors`; RoomDetail's to `/app/tabs/rooms`; ConferenceMap/ExpoHall have no back button (menu button), so after chain 1 there is no in-page way back to the sponsor.

---

## 13. Gotchas / non-obvious behaviour (a port would silently get these wrong)

1. **Two emissions per load.** Every `getX()` can emit twice (cache, then network). Sponsors dismisses its loader on the first; JobListings guards against an empty second emission; ExpoHallMap re-applies names/logos on both. VenuesHours uses `forkJoin` and therefore renders **nothing until completion** (network success or failure), i.e. up to the 10 s timeout on a flaky connection even with a warm cache.
2. **Slug-based identity.** Sponsors have no id; routing, popup links and job-listing cross-links all depend on `getSponsorSlug(name)` being computed identically everywhere (`\s+`→`-`, then strip non `[a-z0-9-]`; punctuation like `,` `.` `&` `—` is deleted, producing double dashes e.g. `qube-research--technologies`). Any normalisation change breaks deep links from the banner/wifi/expo pages.
3. **Booth geometry is hard-coded** and already drifts from the feed (`139` Phemeral and `336` Astral have no rectangles; `407`/`606` have no sponsor). Seed names are placeholders overwritten by the feed, and the popup link is only shown when `level` arrived from the feed.
4. **Reference raster ≠ image file** (9931×7021 vs 4966×3511). Everything is ratio-based; a port must not treat the numbers as pixels of the shipped JPEG.
5. **Zoom-to-booth math depends on layout measurement** (host size, image display height, `.map-inner` offset) and on bypassing the library's pan clamp; the result is "booth centre at (W/2, H/2 − 60 px) at 6×", with max zoom 25×. The library's own `setZoom` would clamp the view to the top because the landscape image occupies only the top part of a tall host.
6. **Default dark letterbox** on the Expo Hall pane (pinch-zoom's default `backgroundColor rgba(0,0,0,0.85)` is not overridden there, whereas the floor-plan and job-fair instances pass `#ffffff`). Verify visually if fidelity matters.
7. **Segment panes are destroyed on switch**, and `/conference-map` vs `/expo-hall` are two separate page instances; `?booth=` always forces the Expo Hall segment on entry.
8. **`navigateRoot` for the booth chip** was chosen specifically to defeat Ionic's path-only page cache; there is no back-stack from Expo Hall to the sponsor.
9. **`parseRoles` splits on URLs visible in the anchor *text***, not on `href`s; with the live feed most listings collapse to one unlinked, 2-line-clamped paragraph (§4). Sponsor Detail uses the same heuristic for "Open Positions". Preserving vs. fixing this is a product call.
10. **Search haystacks include raw HTML** (job listings) and overwritten names + booth ids (expo), with multi-word AND semantics in job listings and plain substring in expo.
11. **Hidden-until-scroll titles** (`opacity 0 → 1` after 100 px) and the 80 px bottom spacer are part of the branded-page pattern; the Conference Map page deliberately uses the plain (non-branded) header with a `color="medium"` menu button.
12. **Pins and booth boxes are percentage-anchored children of the zoomed element**: they pan/zoom with the image, and their stroke/dot sizes scale with it (no counter-scaling).
13. **Infinite pin pulse** is suppressed by the global `prefers-reduced-motion` rule (animation ≈ 0 ms, 1 iteration). Booth highlight pulses exactly twice.
14. **External links** go through `window.open(url, '_system', 'location=yes')`; in Capacitor this is handled by the WebView's new-window hook (system browser on iOS/Android), in the PWA it opens a new tab. No Capacitor Browser/InAppBrowser plugin is used in this slice (SessionDetail uses `@capacitor/inappbrowser` for other links).
15. **`external_url`, `hide`, `postings`** are modelled in templates/code but absent from the live feed; "Visit Website" never appears today.
16. **Chip colours are Ionic defaults** (`primary #3880ff`, `tertiary #5260ff`), not the brand indigo; level badges differ between Sponsor Detail (purple pill `#5833E9`) and Job Listings (grey step-100 tag).
17. **ion-img lazy loading** for floor-plan thumbnails (intersection-observer based); plain `<img>` elsewhere.
18. **Accessibility strings to keep:** `aria-label="Show booth N on the Expo Hall map"`, `"Search booths"`, `"Close booth details"`, `"Close floor plan"`, `"Open <title> floor plan"`, `"Show <label> on the <floorTitle> floor plan"`, pin `aria-label = pinLabel || 'Location'`; decorative chevrons/zoom hints/pins are `aria-hidden`; image `alt`s as listed per component.
19. **No analytics events** are emitted anywhere in this slice.
20. **Unreferenced asset** `pycon-us-2025-floorplan.png` (1.6 MB) still ships.

---

## 14. Complexity summary

| Page / component | Route | Complexity | Reason |
|---|---|---|---|
| SponsorsPage | `/app/tabs/sponsors` | 2 | Grouped list ordered by `level_order`; loader + double emission |
| SponsorDetailPage | `/app/tabs/sponsors/sponsor-detail/:slug` | 3 | HTML description, role parsing, cross-tab `?booth=` deep link, instance-reuse reset |
| JobListingsPage | `/app/tabs/job-listings` | 3 | Debounced multi-word search over HTML, pull-to-refresh with cache invalidation, modal, parser quirks |
| ConferenceMapPage | `/app/tabs/conference-map`, `/app/tabs/expo-hall` | 3 | Segment shell with iframe (3D tour), pinch-zoom pane, deep-link orchestration, two live instances |
| ExpoHallMapComponent | (child of above) | 5 | Zoom/pan with 61 percentage-anchored hit targets, programmatic zoom-to-rect math, readiness queue, search overlay, fixed popup |
| FloorPlanModalComponent | modal | 3 | Zoomable full-size plan with animated percentage pin |
| LocationMapComponent (+ data tables) | embedded | 2 | Static card with pin; 51 + 6 coordinate entries to carry over |
| VenuesHoursPage | `/app/tabs/venues-hours` | 3 | Split CMS HTML on headings, interleave map cards/sponsor card, platform-specific directions URL, forkJoin timing |
