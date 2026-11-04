# PyCon US Mobile (Ionic 8 / Angular 17 / Capacitor 7) — Inventory of the "Info pages, Notifications, Live Update & Native/Project Config" slice

Source checkout: `excluded/pycon-us-mobile` (shallow clone, single commit `2aa6df8 fix: Sprints link for correct url (#315)`, remote `https://github.com/PyCon/pycon-us-mobile`).

This document is a *description of what exists*, written for someone who will rebuild the slice in Flet without reading the HTML/TS. It does not propose Flet solutions; where something is likely to be painful to port it says "looks hard to port because …".

## 0. Files covered

| Area | Files read in full |
|---|---|
| Pages | `src/app/pages/about-pycon/*`, `about-psf/*`, `coc/*`, `wifi/*`, `social-media/*`, `help/*`, `notification-settings/*` (`.ts`, `.html`, `.scss`, routing + module files) |
| Components used by Help | `src/app/location-map/location-map.component.{ts,html,scss}`, `location-map.module.ts`, `location-map/venue-locations.ts`, `src/app/floor-plan-modal/floor-plan-modal.component.{ts,html,scss}` |
| Providers | `src/app/providers/notifications.service.ts` (441 lines), `src/app/providers/live-update.service.ts` (61 lines) |
| App shell (only the parts that drive this slice) | `src/app/app.component.{ts,html,scss}` (menu entries, push listeners, update banner), `src/app/app.module.ts`, `src/app/pages/tabs-page/tabs-page-routing.module.ts`, `src/app/pages/tabs-page/tabs-page.{html,ts}`, `src/global.scss` (pending-update dot), `src/theme/variables.scss` (token values) |
| Native / project config | `capacitor.config.ts`, `capacitor.config.json`, `config.xml`, `firebase.json`, `.firebaserc`, `ngsw-config.json`, `ionic.config.json`, `src/manifest.json`, `src/index.html`, `android/app/src/main/AndroidManifest.xml`, `android/app/build.gradle`, `android/build.gradle`, `android/variables.gradle`, `android/app/capacitor.build.gradle`, `android/capacitor.settings.gradle`, `android/settings.gradle`, `android/gradle.properties`, `android/app/src/main/res/**` (strings, styles, xml, launcher), `android/app/src/main/java/org/pycon/us/MainActivity.java`, `android/app/src/main/assets/capacitor.plugins.json`, `android/app/google-services.json` (identifiers only), `ios/App/App/Info.plist`, `ios/App/App/App.entitlements`, `ios/App/App.xcodeproj/project.pbxproj` (identity/version keys), `ios/App/Podfile`, `ios/App/App/AppDelegate.swift`, `ios/App/App/Base.lproj/LaunchScreen.storyboard`, `ios/App/App/UILaunchScreen.storyboard`, `ios/App/App/Assets.xcassets/**`, `ios/App/App/GoogleService-Info.plist` (identifiers only), `.well-known/funding-manifest-urls`, `patches/@capacitor-firebase+analytics+7.5.0.patch`, `generate-h2-push.js`, `resources/**` (listing), `Makefile`, `.github/workflows/CI.yml`, `.github/*`, `package.json`, `angular.json`, `.browserslistrc`, `src/environments/*` |
| Data feed | `conference.json` (local copy, inspected with `python3 -I`): `conference.content` HTML blobs and `conference.sponsors` shape |

---

## 1. Scaffold shared by all seven pages

Every page in this slice is built from the same template. Describe it once; each page section below only lists what differs.

### 1.1 Header
* `<ion-header class="ion-no-border">` with one `<ion-toolbar>`.
* Page SCSS (identical copy in each page) sets: `ion-header { background: linear-gradient(180deg, #3B3EA9 0%, #3B3EA9 100%); &::after { display:none } }` (so the header is a flat `#3B3EA9` indigo with no bottom border/shadow), `ion-toolbar { --background: transparent; --border-color: transparent; --color: #ffffff }`, `ion-toolbar ion-menu-button { --color: #ffffff }`.
* Start slot: `<ion-menu-button>` (hamburger; white). There is **no back button** — these pages are root pages inside the tab router outlet; they are opened from the side menu with `routerDirection="root"`.
* `<ion-title [class.title-visible]="showTitle">…</ion-title>` — CSS `ion-title { opacity: 0; transition: opacity 0.25s ease; &.title-visible { opacity: 1 } }`. `showTitle` is set by `onScroll(event) { this.showTitle = event.detail.scrollTop > 100; }` bound via `<ion-content scrollEvents="true" (ionScroll)="onScroll($event)">`. Net effect: the toolbar title is invisible while the hero (which repeats the title) is on screen and fades in once the user has scrolled >100px.
* Global rule (`src/global.scss`): when `LiveUpdateService.needsUpdate` is true the service adds class `has-pending-update` to `<body>`, and `body.has-pending-update ion-menu-button::after` draws a 9×9px dot (`border-radius:50%`, `background: var(--ion-color-primary, #3880ff)`, `box-shadow: 0 0 0 2px var(--ion-background-color,#fff)`, positioned `top:8px; right:6px`) on the hamburger of every page.

### 1.2 Hero block (first child of `ion-content`)
A full-width block (class name varies: `.about-hero`, `.page-hero`, `.coc-hero`, `.wifi-hero`, `.notif-hero`):
* `display:flex; flex-direction:column; align-items:center; color:#fff; text-align:center;`
* `background: linear-gradient(180deg, #3B3EA9 23.5%, #101136 53.29%)` (indigo → near-black navy). Because the header above is the same `#3B3EA9`, header + hero read as one continuous surface.
* Padding differs: `16px 24px 40px` (about-pycon), `16px 24px 32px` (about-psf, coc, social, help), `16px 16px 32px` (wifi), `16px 16px 40px` (notifications).
* An `<ion-icon>` sized 40px (about, psf, social, help), 36px (coc) or 72px (wifi, notifications), coloured `#FFD779` (gold) on every page except social-media where it is `#25C8EB` (cyan); `margin-bottom: 10px` (16px for the 72px icons).
* `<h1>` `margin:0; font-size:1.6rem; font-weight:700`.
* `<p>` `margin: 6px 0 0` (4px on wifi, 8px on coc, `6px 16px 0` on notifications); `font-size:0.9rem; opacity:0.8`.

### 1.3 Content below the hero
* First card/list usually **overlaps the hero** with a negative top margin (`-20px`, `-16px` or `-24px`), `border-radius:16px`, a soft shadow `0 8px 32px rgba(16,17,54,0.15)` (or `0 4px 16px rgba(16,17,54,0.1)`), `position:relative; z-index:1`.
* Lists are `<ion-list lines="full">` with `<ion-list-header><ion-label>Section</ion-label></ion-list-header>`; rows are `<ion-item button="true" (click)="openUrl(...)" detail="true">` → leading `<ion-icon slot="start" name="…" color="primary|danger|medium">`, `<ion-label class="ion-text-wrap"><h2>Title</h2><p>Subtitle</p></ion-label>`, trailing chevron from `detail="true"`. Rows that open `tel:`/`mailto:` omit `detail` (no chevron).
* Every page except notification-settings ends with `<div style="height: 80px"></div>` (clearance for the bottom tab bar + rotating sponsor banner).

### 1.4 `openUrl` helper (identical on about-psf, coc, social-media, help; app.component has the same)
```ts
openUrl(url: string) { window.open(url, '_system', 'location=yes'); }
```
No Capacitor plugin is used for this. In a Capacitor WebView the bridge hands a `window.open(...,'_system')` to the OS: `https://` → system browser, `tel:` → dialer, `mailto:` → mail client. In the PWA it opens a new tab/popup. **`@capacitor/inappbrowser` is NOT used anywhere in this slice** (it is used by speaker-detail, account, session-detail, schedule-list — other slices).

### 1.5 Theme classes that the page SCSS reacts to
`<ion-app>` carries `dark-theme`, `high-contrast-theme`, `high-contrast-light-theme`, `high-contrast-dark-theme` depending on the stored theme (`UserData.getTheme()`, storage key `theme`). Token values used by this slice (from `src/theme/variables.scss`): light `--ion-color-primary:#3880ff`, `--ion-color-danger:#eb445a`, `--ion-color-success:#2dd36f`, `--ion-color-medium:#92949c`, `--ion-color-light:#f4f5f8`; dark(md) `--ion-background-color:#121212`, `--ion-text-color:#fff`, `--ion-color-step-50:#1e1e1e`, `--ion-color-step-100:#2a2a2a`, `--ion-item-background:#1e1e1e`; HC-light `--ion-background-color:#fbfaf6`, `--ion-text-color:#1a1d24`, `--ion-border-color:#1a1d24`, `--ion-card-background:#ffffff`; HC-dark `--ion-background-color:#0b0f17`, `--ion-text-color:#f5f5f0`, `--ion-card-background:#11151d`.

### 1.6 How the pages are reached (side menu, `src/app/app.component.html`)
Side menu (`ion-menu`, `ion-split-pane`) sections → items (`routerDirection="root"`):
* Section **Information** → accordion "About PyCon US" (icon `information-circle-outline`) containing `aboutPages`: **Conference Info** → `/app/tabs/about-pycon` (`information-circle-outline`), **Code of Conduct** → `/app/tabs/coc` (`shield-checkmark-outline`), **Wi-Fi** → `/app/tabs/wifi` (`wifi-outline`), Venue & Hours (`/app/tabs/venues-hours`, other slice), Session Types (other slice).
* Directly under Information (`infoPages`): **About The PSF** → `/app/tabs/about-psf` (`logo-python`), **Social** → `/app/tabs/social-media` (`chatbubbles-outline`), Conference Maps (`/app/tabs/conference-map`, other slice), **Help & Safety** → `/app/tabs/help` (`help-circle-outline`).
* Section **Account**: Account/Login (other slice), **Notifications** → `/app/tabs/notifications` (`notifications-outline`) — shown to everyone, logged in or not; Logout; Theme picker (`ion-select` action-sheet: Light / Dark / High Contrast (Light) / High Contrast (Dark)).
* None of the seven pages is on the bottom tab bar (`tabs-page.html` tabs: speakers, conference-map, schedule, now, scanner, login). None has a deep link. The only in-app cross-links are CoC → Help (`routerLink="/app/tabs/help"`), Help → Conference Maps (`/app/tabs/conference-map`), Wi-Fi → sponsor detail.

Routing (`src/app/pages/tabs-page/tabs-page-routing.module.ts`): each page is `{ path: '<name>', children: [{ path: '', loadChildren: () => import(...) }] }` under `tabs`, which itself is under `/app`; the page's own routing module is `{ path: '', component: XPage }`. Route names: `about-pycon`, `about-psf`, `coc`, `wifi`, `social-media`, `help`, `notifications` (note: **`notifications`**, not `notification-settings`).

---

## 2. Page: About PyCon US (`src/app/pages/about-pycon/`)

| # | Item | Detail |
|---|---|---|
| 1 | Route / entry | `/app/tabs/about-pycon`; side menu → Information → About PyCon US ▸ **Conference Info**. Selector `app-about-pycon`. |
| 2 | Purpose | Short "what is PyCon US" blurb from the feed + a collapsible **Developer Info** panel (versions, OTA snapshot, API host) + a staff-only "share debug dump" action. |
| 9 | Complexity | **2** — static layout + one HTML blob, but the debug-share flow (encrypt whole KV store, write file, native share) and the LiveUpdate-dependent rows need native plumbing. |

**Toolbar title:** `About PyCon US`.

**Hero** (`.about-hero`, padding `16px 24px 40px`): icon `information-circle` (40px, `#FFD779`), `<h1>PyCon US 2026</h1>`, `<p>Long Beach, CA • May 13-19</p>` (hard-coded; the bullet is `&bull;`).

**Card `.about-card`** (`margin: -20px 16px 16px; border-radius:16px; box-shadow: 0 4px 16px rgba(16,17,54,0.1)`; `ion-card-content { padding:20px; font-size:0.95rem; line-height:1.6; color: var(--ion-text-color) }`; dark theme `--background:#1e1e1e`; HC theme `--background: var(--ion-card-background); border:1px solid var(--ion-border-color)`): `<ion-card-content [innerHtml]="content.about">`. Current feed value of `conference.content.about` (HTML):

```html
<p>PyCon US 2026 is the largest annual gathering for the community using and developing the open-source Python programming language. It is produced and underwritten by the Python Software Foundation, the 501(c)(3) nonprofit organization dedicated to advancing and promoting Python. Through PyCon US, the PSF advances its mission of growing the international community of Python programmers.</p>
```

**Accordion `.dev-accordion`** (`margin: 0 16px 16px`): `<ion-accordion-group>` → one `<ion-accordion value="dev-info">`; header `<ion-item slot="header" color="light">` with icon `code-slash-outline` (color `medium`) and label "Developer Info" (color `medium`); collapsed by default. Content `.dev-content` (`padding:16px 20px; background: var(--ion-color-step-50, #f7f7f7)`) contains `.dev-row`s (`display:flex; justify-content:space-between; align-items:center; padding:8px 0`, consecutive rows separated by `border-top:1px solid var(--ion-color-step-100,#eee)`): `.dev-label` (uppercase, `0.8rem`, 500, `--ion-color-medium`, `letter-spacing:.05em`) / `.dev-value` (`0.9rem`, 600, monospace `'Menlo','SF Mono','Courier New'`, `--ion-text-color`).

| Row label | Value expression | Shown when |
|---|---|---|
| `App Version` | `liveUpdateService.appVersion` (from `App.getInfo().version`, e.g. `26.2.1`) | always (empty string on web) |
| `Native Build` | `liveUpdateService.build` (from `App.getInfo().build`; initial `"base"`) | always |
| `Live Update Build` | `'#' + liveUpdateService.snapshot.buildId` | `snapshot?.buildId` truthy (an Appflow OTA bundle is active) |
| `Channel` | `liveUpdateService.channel` (e.g. `Production`) | truthy |
| `API` | `environmentUrl = environment.baseUrl` (`https://us.pycon.org` prod/base; `http://127.0.0.1:8000` or `http://10.0.2.2:8000` dev) | always |

Below the rows, **only when `loggedIn`**: `<ion-button expand="block" fill="outline" size="small" class="dev-btn">` (margin-top 12px) with icon `share-outline` and text **"Share Debug Info with PyCon Staff"** → `shareDebug()`.

**Data & lifecycle**
* `ngOnInit()` → `liveUpdateService.checkForUpdate()` then `reloadContent()`.
* `reloadContent()`: `LoadingController.create({ message: 'Fetching latest...', duration: 10000 })` → `present()`; `confData.getContent().subscribe(content => { this.content = content; changeDetection.detectChanges(); setTimeout(() => loader.dismiss(), 100) })`; in parallel `userData.isLoggedIn().then(r => this.loggedIn = r)` (storage key `hasLoggedIn`).
* `confData.getContent()` = `load().pipe(map(d => d.conference.content))`; `load()` serves Ionic-Storage key `schedule-cache` first (instant), then GETs `${environment.baseUrl}/2026/schedule/conference.json` with a 10 s timeout and re-emits; on network failure with no cache it shows a top toast `Unable to load schedule, no offline cache available` (3 s, icon `exclamation`) and errors. So on this page: with cache the loader shows ~100 ms; offline with no cache the loader stays up to 10 s and the card stays empty.
* `shareDebug()` (async):
  1. `storage.get('email')`, `storage.get('key')`, `storage.get('secret')` (set at login by UserData).
  2. `storage.forEach((value, key, index) => kvstore.push([index, key, value]))` — dumps **every** key in the Ionic Storage DB (favorites, prefs, tokens, `notification_prefs`, `schedule-cache`, …).
  3. `dbdump = JSON.stringify(kvstore)`; `state = base64( crypto.AES.encrypt(dbdump, secret).toString() )` (crypto-js AES with passphrase → OpenSSL-compatible `Salted__…` base64 ciphertext, then base64'd again by js-base64).
  4. `data = { email, key, state }`; `base64Data = base64(JSON.stringify(data))`.
  5. `Filesystem.writeFile({ path: 'pycon-db-dump-' + key + '.dat', data: base64Data, directory: Directory.Cache })` (no `encoding` ⇒ Capacitor decodes the base64, so the file on disk is the JSON text).
  6. `Filesystem.getUri({ directory: Directory.Cache, path: same })` → `Share.share({ title: 'Share Debug Records with PyCon Staff', text: 'pycon-db-dump.dat', url: uri })` (native share sheet). Android needs the FileProvider declared in the manifest (`cache-path`).
  * No platform guard: on web, `Filesystem` writes to IndexedDB and `Share` needs `navigator.share`; the flow would reject. Only reachable when logged in.
* `checkForUpdate()` method and `.update-btn` CSS exist but are unused by the template (dead code). `@ViewChild(IonContent) ionContent` unused.

**Native plugins:** `@capacitor/filesystem` (`Filesystem.writeFile`, `Filesystem.getUri`, `Directory.Cache`), `@capacitor/share` (`Share.share`), plus transitively `@capacitor/app` and `@capacitor/live-updates` via `LiveUpdateService`. Libraries: `crypto-js` (AES), `js-base64` (`encode`).

**Navigation out:** none in-app. **Analytics:** none. **Accessibility:** nothing beyond defaults.

---

## 3. Page: About the PSF (`src/app/pages/about-psf/`)

| # | Item | Detail |
|---|---|---|
| 1 | Route / entry | `/app/tabs/about-psf`; side menu → Information → **About The PSF** (icon `logo-python`). Selector `app-about-psf`. |
| 2 | Purpose | Static PSF mission + "what we do" + "get involved" link lists + resources + social, a Donate CTA, and the feed's `about-psf` HTML at the bottom. Every row is an external link. |
| 9 | Complexity | **2** — long static page; only dynamic bit is one HTML blob and the loader. |

**Toolbar title:** `Python Software Foundation`.

**Hero** (`.page-hero`, `16px 24px 32px`): icon `logo-python` 40px `#FFD779`; `<h1>Python Software Foundation</h1>`; `<p>The organization behind the Python language</p>`.

**Card 1** — `<ion-card-header><ion-card-title>Our Mission</ion-card-title>`; content `<p>` (SCSS: `ion-card ion-card-content p { font-size:.95rem; line-height:1.5; color: var(--ion-text-color) }`):
> The mission of the Python Software Foundation is to promote, protect, and advance the Python programming language, and to support and facilitate the growth of a diverse and international community of Python programmers.

(Cards here use default Ionic card margins — no negative overlap on this page.)

**Card 2** — title `We Support the Python Community Through...`; `<ion-list lines="none">` of four **non-tappable** items (icon `slot=start color=primary`; label `ion-text-wrap` with `<strong>` + `<p>`):

| Icon | Strong | p |
|---|---|---|
| `cash-outline` | Grants | The PSF awards hundreds of thousands of dollars annually to groups and individuals around the world. |
| `code-slash-outline` | CPython | We support CPython, the reference implementation of Python, and fund core developer work. |
| `server-outline` | Infrastructure | We support and maintain python.org, the Python Package Index (PyPI), Python Documentation, and many other services the Python community relies on. |
| `people-outline` | PyCon US | We produce and underwrite the PyCon US Conference, the largest annual gathering for the Python community. |

**Card 3** — title `Get Involved`; `<ion-list lines="none">`, items `button="true" detail="true"` → `openUrl(url)`:

| Icon (color) | Strong | p | URL |
|---|---|---|---|
| `person-add-outline` (primary) | Become a Member | Help the PSF promote, protect, and advance the Python programming language and community! | `https://psfmember.org` |
| `heart-outline` (**danger**) | Donate | Assist the foundation's goals with a donation. The PSF is a recognized 501(c)(3) non-profit. | `https://psfmember.org/civicrm/contribute/transact/?reset=1&id=2` |
| `hand-left-outline` (primary) | Volunteer | Learn how you can help the PSF and the greater Python community! | `https://www.python.org/psf/volunteer/` |
| `business-outline` (primary) | Sponsors | Without our sponsors we wouldn't be able to help the Python community grow and prosper. | `https://www.python.org/psf/sponsors/` |
| `document-text-outline` (primary) | PSF Grants Program | The PSF welcomes grant proposals for projects related to Python development, technology, and education. | `https://www.python.org/psf/grants/` |
| `globe-outline` (primary) | Community Partners | Organizations partnering with the PSF to support the Python community worldwide. | `https://www.python.org/psf/community-partners/` |
| `star-outline` (primary) | Volunteer at PyCon US | Help make PyCon US happen — sign up to volunteer at the conference! | `https://us.pycon.org/2026/volunteer/volunteering/` |
| `git-network-outline` (primary) | Work Groups | PSF work groups tackle specific areas like diversity, packaging, and documentation. | `https://www.python.org/psf/workgroups/` |

**List "Python Resources"** (`lines="full"`, items `button detail`; label uses `<h2>`/`<p>`):

| Leading | h2 | p | URL |
|---|---|---|---|
| icon `logo-python` primary | python.org | The official Python website | `https://www.python.org` |
| `<img src="assets/img/pypi-logo.png" class="resource-icon pypi" alt="PyPI">` (24×24, `object-fit:contain`, `margin-inline-end:32px`, `margin-block:12px`) | PyPI | The Python Package Index | `https://pypi.org` |
| icon `book-outline` primary | Python Docs | Official Python documentation | `https://docs.python.org` |

**List "PSF News & Social"**:

| Leading icon | h2 | p | URL |
|---|---|---|---|
| `newspaper-outline` | PSF Blog | News and updates from the PSF | `https://pyfound.blogspot.com` |
| `globe-outline` | @ThePSF@fosstodon.org | PSF on Mastodon | `https://fosstodon.org/@ThePSF` |
| `logo-twitter` | @ThePSF | PSF on X / Twitter | `https://x.com/ThePSF` |
| `logo-linkedin` | Python Software Foundation | PSF on LinkedIn | `https://www.linkedin.com/company/thepsf/` |

**Donate CTA**: `<div class="ion-padding ion-text-center"><ion-button expand="block" color="danger">` icon `heart` + **"Donate to the PSF"** → same CiviCRM donate URL.

**Feed HTML**: `<ion-row><ion-col [innerHtml]="content['about-psf']">` — rendered raw at the bottom (links inside are plain `<a href>`; they are *not* routed through `openUrl`, they rely on Capacitor's default handling of external navigations). Current feed value:

```html
<p>The Python Software Foundation is a 501(c)(3) nonprofit dedicated to advancing and promoting Python. The PSF supports and encourages Python events world-wide to advance its mission of growing the international community of Python programmers, and hosts the North American PyCon conference as its flagship annual event. As stated on the PSF’s web site:</p>
<p>The mission of the Python Software Foundation is to promote, protect, and advance the Python programming language, and to support and facilitate the growth of a diverse and international community of Python programmers.</p>
<p>You can learn more at the PSF web site by following these links:</p>
<ul>
<li><a href="https://www.python.org/psf-landing/">PSF home page</a></li>
<li><a href="https://www.python.org/psf/mission/">Mission</a></li>
<li><a href="https://www.python.org/psf/sponsorship/">Becoming a sponsor</a></li>
<li><a href="https://www.python.org/psf/donations/">How to donate</a></li>
<li><a href="https://www.python.org/psf/membership/">Becoming a member</a></li>
<li><a href="http://pyfound.blogspot.com/">Official PSF blog</a></li>
</ul>
```
(So the mission paragraph appears twice on the page: once in Card 1, once in this blob.)

**Data & lifecycle:** `ngOnInit()` → `reloadContent()` identical to About PyCon (loader `Fetching latest...`, 10 s cap, dismiss 100 ms after data). `liveUpdateService` injected but unused. No native plugins directly. **Navigation out:** external only. **Analytics:** none.

---

## 4. Page: Code of Conduct (`src/app/pages/coc/`)

| # | Item | Detail |
|---|---|---|
| 1 | Route / entry | `/app/tabs/coc`; menu → Information → About PyCon US ▸ **Code of Conduct**. Selector `app-coc`. |
| 2 | Purpose | One-paragraph CoC summary, link to the full policy, and "Report a Concern" actions (hotline, email, procedures, Help page). |
| 9 | Complexity | **1** — fully static. |

**Toolbar title:** `Code of Conduct`.

**Hero** (`.coc-hero`, `16px 24px 32px`, `text-align:center`): `.coc-hero-title` is a horizontal flex row (`align-items:center; justify-content:center; gap:12px`) containing icon `shield-checkmark` (36px, `#FFD779`) and `<h1>Code of Conduct</h1>` side by side; then `<p>Everyone deserves a safe, respectful experience</p>` (`margin:8px 0 0`).

**Card `.coc-card`** (`margin:-16px 20px 0; border-radius:16px; box-shadow:0 8px 32px rgba(16,17,54,.15)`; content `padding:24px`; `p { font-size:.95rem; line-height:1.5; margin-bottom:16px }`):
> PyCon US is a diverse conference dedicated to providing an enjoyable experience to everyone. Help us do this by following our Code of Conduct.

then `<ion-button expand="block" fill="outline" color="primary">` icon `document-text-outline` **"Read the Full Code of Conduct"** → `https://policies.python.org/us.pycon.org/code-of-conduct/`.

**List `.coc-actions`** (`margin-top:16px`, `lines="full"`, header **Report a Concern**):

| Icon (color) | h2 | p | Action | Chevron |
|---|---|---|---|---|
| `call` (danger) | CoC Hotline | (562) 662-4082 | `openUrl('tel:+15626624082')` | no |
| `mail` (danger) | Report via Email | pycon-us-report@python.org | `openUrl('mailto:pycon-us-report@python.org')` | no |
| `document-text-outline` (primary) | Reporting Procedures | How to report an incident | `https://policies.python.org/us.pycon.org/code-of-conduct/Procedures-for-Reporting-Incidents/` | yes |
| `help-circle-outline` (primary) | Help & Safety | Info desk, maps, and additional resources | `routerLink="/app/tabs/help"` (in-app) | yes |

**Footer:** `<div class="ion-padding ion-text-center"><ion-text color="medium"><p class="coc-footer">` (`0.85rem`, italic): *If you see something, say something. Staff are here to help.*

**Data & lifecycle:** `ngOnInit()` subscribes `confData.getContent()` into `content` and calls `detectChanges()` — **but the template never uses `content`** (dead fetch; no loader on this page). `liveUpdateService` injected, unused. The feed does contain `conference.content['code-of-conduct']` (HTML with the same email + two policy links) — ignored by the page.

---

## 5. Page: Wi-Fi (`src/app/pages/wifi/`)

| # | Item | Detail |
|---|---|---|
| 1 | Route / entry | `/app/tabs/wifi`; menu → Information → About PyCon US ▸ **Wi-Fi**. Selector `app-wifi`. |
| 2 | Purpose | Show SSID/password, one-tap copy of the password (toast), credit the Wi-Fi sponsor (tap → sponsor detail), venue note. |
| 9 | Complexity | **2** — clipboard + toast + a feed lookup for the sponsor card. |

**Toolbar title:** `Wi-Fi`.

**Hero** (`.wifi-hero`, `16px 16px 32px`, no `text-align` class but flex-centered): icon `wifi` **72px** `#FFD779` (`margin-bottom:16px`); `<h1>Connect to Wi-Fi</h1>`; `<p>Free for all attendees</p>` (`margin:4px 0 0`).

**Card `.wifi-card`** (`margin:-20px 20px 0; border-radius:16px; box-shadow:0 8px 32px rgba(16,17,54,.15)`; content `padding:28px 24px`): two `.wifi-field` rows (`display:flex; justify-content:space-between; align-items:center; padding:14px 0`) separated by `.wifi-divider` (`height:1px; background: var(--ion-color-step-100,#eee)`):
* `.wifi-label` (`0.8rem`, 600, `--ion-color-medium`, uppercase, `letter-spacing:.08em`) **Network** → `.wifi-value` (`1.3rem`, 700, monospace, color **`#5833E9`**) **`PyConUS26`**
* **Password** → **`pyconLB2026`**

**Actions `.wifi-actions`** (`ion-padding`, flex column `gap:8px; margin-top:16px`): `<ion-button expand="block">` icon `copy-outline` **"Copy Password"** → `copyPassword()`: `await navigator.clipboard.writeText('pyconLB2026')` then `ToastController.create({ message: 'Password copied!', duration: 1500, position: 'bottom', color: 'success' })`. (Web Clipboard API, no plugin; the value is hard-coded twice — template and TS.)

**Sponsor card** (`*ngIf="wifiSponsor"`, `.wifi-sponsor-card`, `button="true"`, `[routerLink]="'/app/tabs/sponsors/sponsor-detail/' + getSponsorSlug(wifiSponsor.name)"`; `margin:16px 20px 0; border-radius:12px; box-shadow:0 2px 8px rgba(16,17,54,.08)`): content is a flex row (`gap:14px; padding:12px 16px`): `.wifi-sponsor-logo` 44×44 box with `<img [src]="wifiSponsor.logo_url" [alt]="name + ' logo'">` (`max-width/height:100%; object-fit:contain`), then a column: `.wifi-sponsor-label` **"Wi-Fi sponsored by"** (`0.72rem`, 600, medium, uppercase, `letter-spacing:.06em`) and `.wifi-sponsor-name` `{{ wifiSponsor.name }}` (`1rem`, 700, `#5833E9`, `margin-top:2px`).

**Note `.wifi-note`** (`margin-top:24px`, `ion-padding ion-text-center`): inline icon `location-outline` (20px, medium, `vertical-align:middle; margin-right:4px`) + `<ion-text color="medium"><p>` (inline, `0.85rem`) *Available throughout the Long Beach Convention &amp; Entertainment Center*.

**Data & lifecycle:** `ngOnInit()` → `confData.getSponsors()` (= `load().pipe(map(d => d.conference.sponsors))`; shape: object keyed by level name → array of `{ name, level, level_order, mobile_banner, logo_url, description, booth_number, job_fair_table_number }`). Iterates `Object.keys(sponsors)` in insertion order, skips non-arrays, and takes the **first sponsor whose `name.toLowerCase().includes('temporal')`**. In the current feed that is `{ name: 'Temporal', level: 'Partner', logo_url: 'https://s3.dualstack.us-east-2.amazonaws.com/pythondotorg-assets/media/sponsor_web_logos/Temporal_LogoLockup_Horizontal_dark_1_2x_YjPyrlU.png' }`. If no match the sponsor card is simply absent. `getSponsorSlug(name) = name.toLowerCase().replace(/\s+/g,'-').replace(/[^a-z0-9-]/g,'')` → `temporal` (same slug rule as `tabs-page.goToSponsor`). `liveUpdateService` injected, unused. No native plugins.

**Navigation out:** sponsor card → `/app/tabs/sponsors/sponsor-detail/<slug>`.

---

## 6. Page: Social Media (`src/app/pages/social-media/`)

| # | Item | Detail |
|---|---|---|
| 1 | Route / entry | `/app/tabs/social-media`; menu → Information → **Social** (icon `chatbubbles-outline`). Selector `app-social-media`. |
| 2 | Purpose | Hashtag chips + three link lists (PyCon US accounts, PSF accounts, Blogs). All external. |
| 9 | Complexity | **1** — static list page; only wrinkle is two custom SVG icons and theme-aware icon colours. |

**Toolbar title:** `Social Media`.

**Hero** (`.page-hero`): icon `share-social` 40px **`#25C8EB`** (cyan — the only non-gold hero icon); `<h1>Social Media</h1>`; `<p>Connect with the Python community online</p>`.

**Hashtag banner `.hashtag-banner`** (`display:flex; justify-content:center; gap:8px; padding:16px 16px 8px`): two `<ion-chip color="primary" outline="true">`, each with icon `pricetag-outline` and `<ion-label><strong>#PyConUS</strong>` / `<strong>#PyConUS2026</strong>`. **Not tappable** (no handlers).

**List "PyCon US"** (`lines="full"`, all items `button detail` → `openUrl`):

| Leading | h2 | p | URL |
|---|---|---|---|
| icon `logo-mastodon` primary | Mastodon | @pycon@fosstodon.org | `https://fosstodon.org/@pycon` |
| `<ion-icon src="assets/img/icon-bluesky.svg" class="social-icon bluesky" aria-label="Bluesky">` (color `#0085ff`) | Bluesky | @pycon.us | `https://bsky.app/profile/pycon.us` |
| `<ion-icon src="assets/img/icon-x.svg" class="social-icon x-icon" aria-label="X">` (color `var(--ion-text-color,#000)`) | X | @pycon | `https://x.com/pycon` |
| icon `logo-youtube` **danger** | YouTube | PyCon US | `https://www.youtube.com/@PyConUS` |
| icon `logo-linkedin` primary | LinkedIn | Python Software Foundation | `https://www.linkedin.com/company/thepsf/` |

**List "Python Software Foundation"**:

| Leading | h2 | p | URL |
|---|---|---|---|
| `logo-mastodon` | Mastodon | @ThePSF@fosstodon.org | `https://fosstodon.org/@ThePSF` |
| bluesky svg | Bluesky | @python.org | `https://bsky.app/profile/python.org` |
| x svg | X | @ThePSF | `https://x.com/ThePSF` |

**List "Blogs"**:

| Leading | h2 | p | URL |
|---|---|---|---|
| `calendar-outline` | PyCon US Blog | Conference news and announcements | `https://pycon.blogspot.com` |
| `newspaper-outline` | PSF Blog | News and updates from the Python Software Foundation | `https://pyfound.blogspot.com` |
| `logo-python` | CPython Blog | Python insider — core development updates | `https://blog.python.org` |
| `<img src="assets/img/pypi-logo.png" class="social-icon pypi" alt="PyPI">` | PyPI Blog | News from the Python Package Index | `https://blog.pypi.org` |

**SCSS specifics:** `.social-icon { width:24px; height:24px; font-size:24px; margin-inline-end:16px; align-self:center; margin-block:12px }`; `ion-icon.social-icon { color: var(--ion-text-color,#000) }`; `ion-icon.social-icon.bluesky { color:#0085ff }`; under `.dark-theme` / `.high-contrast-dark-theme`: `.social-icon.pypi { filter:none }` and `img.social-icon:not(.pypi) { filter: invert(1) }` (no such img exists, so effectively dead). The SVGs are 24×24 `fill="currentColor"` single-path logos (Bluesky butterfly, X).

**Data & lifecycle:** none (`SocialMediaPage` has no `ngOnInit`). `liveUpdateService` injected, unused. The feed's `conference.content['social-media']` (HTML list with Mastodon/Bluesky/twitter/Blog/LinkedIn/YouTube links) is **not** used.

---

## 7. Page: Help & Safety (`src/app/pages/help/`)

| # | Item | Detail |
|---|---|---|
| 1 | Route / entry | `/app/tabs/help`; menu → Information → **Help & Safety** (`help-circle-outline`); also from CoC page row "Help & Safety". Selector `app-help`. |
| 2 | Purpose | Where to get help on site (Info Desk mini-map → full-screen zoomable floor plan), CoC quick actions, bug-report links. |
| 9 | Complexity | **3** — the embedded `LocationMap` thumbnail with a percentage-positioned pulsing pin and the pinch-zoom modal are the hard parts; everything else is static rows. |

**Toolbar title:** `Help & Safety`.

**Hero** (`.page-hero`): icon `help-buoy` 40px `#FFD779`; `<h1>Help & Safety</h1>`; `<p>Resources for a safe and welcoming conference</p>`.

**List "At the Conference"** (`lines="full"`):
1. `<div class="help-info-desk-map">` (`padding:8px 16px 12px`) wrapping `<app-location-map>` bound to `VENUE_LOCATIONS['infoDesk']`:
   `{ key:'infoDesk', label:'Information Desk', sublabel:'Promenade Lobby (Main Entrance)', floorTitle:'Concourse Level', thumbSrc:'assets/img/floor-plans/floor-plan-1-thumb.jpg' (800×618), fullSrc:'assets/img/floor-plans/floor-plan-1.jpg' (2200×1700), pinXPct:55, pinYPct:53 }`.
2. Row: icon `map-outline` primary, h2 **Full Conference Maps**, p *Browse all floor plans and the expo hall*, `routerLink="/app/tabs/conference-map"`, chevron.

**List "Code of Conduct"**:

| Icon (color) | h2 | p | Action | Chevron |
|---|---|---|---|---|
| `shield-checkmark-outline` (primary) | Read the Code of Conduct | PyCon US community guidelines | `https://policies.python.org/us.pycon.org/code-of-conduct/` | yes |
| `call-outline` (danger) | CoC Hotline | (562) 662-4082 | `tel:+15626624082` | no |
| `mail-outline` (danger) | Report via Email | pycon-us-report@python.org | `mailto:pycon-us-report@python.org` | no |

**List "App & Website"**:

| Icon (color) | h2 | p | URL |
|---|---|---|---|
| `bug-outline` (medium) | Report an App Issue | Bug reports and feature requests for the mobile app | `https://github.com/PyCon/pycon-us-mobile/issues/new` |
| `globe-outline` (medium) | Report a Website Issue | Issues with us.pycon.org | `https://github.com/PyCon/pycon-site-public/issues/new` |

### 7.1 `LocationMapComponent` (`src/app/location-map/`)
Rendered as a single `<button type="button" class="location-map" [attr.aria-label]="'Show ' + label + ' on the ' + floorTitle + ' floor plan'">`:
* Container: `display:flex; align-items:center; width:100%; background: var(--ion-card-background,#fff); border:1px solid var(--ion-color-step-150, rgba(0,0,0,.08)); border-radius:14px; overflow:hidden; text-align:left`; `:active { transform:scale(.985); box-shadow:0 2px 8px rgba(0,0,0,.08) }`.
* Left `.location-map-thumb`: fixed `144px` wide, white background, `border-right` 1px, `position:relative`; `<img [src]="thumbSrc" [alt]="floorTitle + ' floor plan'" decoding="async">` at 100% width (so height ≈ 144 × 618/800 ≈ 111px).
  * `.location-map-pin` absolutely positioned at `left: pinXPct%`, `top: pinYPct%` (zero-size anchor); inside: `.location-map-pin-dot` 8×8 circle `background:#DD04D2` (magenta), `border:1.5px solid #fff`, `box-shadow: 0 0 0 1.5px rgba(0,0,0,.18), 0 1px 2px rgba(0,0,0,.4)`; `.location-map-pin-pulse` 8×8 circle `#DD04D2` opacity .55 with `@keyframes location-map-pin-pulse` (scale 1→2.6, opacity .5→0, `1.8s ease-out infinite`).
  * `.location-map-zoom-hint`: 24×24 circle bottom-right (`bottom:6px; right:6px`), `background: rgba(0,0,0,.55)`, white icon `expand-outline` at 14px.
* Right `.location-map-meta` (`padding:12px 14px`, column, `min-width:0`): `.location-map-label` (16px, 600) = label; `.location-map-sublabel` (13px, `--ion-color-step-650,#555`, `margin-top:2px`) = sublabel (if any); `.location-map-floor` (12px, medium, uppercase, `letter-spacing:.04em`, `margin-top:4px`) = floorTitle.
* Tap → `ModalController.create({ component: FloorPlanModalComponent, componentProps: { title: floorTitle, imageSrc: fullSrc, altText: \`${floorTitle} floor plan with ${label} highlighted\`, pinXPct, pinYPct, pinLabel: label } })`.
* `venue-locations.ts` also defines `registration` (67/58, Concourse), `quietRoom` (58/36, Concourse, "VIP Room A & B"), `swagPickup` (42/68, Arena & Exhibit Halls, floor-plan-3), `lostAndFound` (40/58, Upper Level, floor-plan-2), `staffOffice` (40/58, Upper Level, "Room 203 A & B") — used by other pages (Venue & Hours), only `infoDesk` is used here.

### 7.2 `FloorPlanModalComponent` (`src/app/floor-plan-modal/`)
Full-screen Ionic modal: header (`ion-no-border`) with start button (`close-outline`, `aria-label="Close floor plan"`) → `modalCtrl.dismiss()`, title = `title`. Content `fullscreen` with `--background:#fff`. Body is `<pinch-zoom>` from `@ciag/ngx-pinch-zoom` (`[autoZoomOut]=false [doubleTap]=true [wheel]=true [draggableImage]=false [limitZoom]="'original image size'" backgroundColor="#ffffff"`) wrapping `.floor-plan-canvas` (`position:relative; width:100%`) containing the full image (100% width, non-draggable, non-selectable) and, when both pin pcts are set, `.floor-plan-pin` at `left/top %` with a 10×10 `#DD04D2` dot + pulse (scale 1→3, 1.8 s). `aria-label` = pinLabel or `Location`. Pin stays glued to the image because it is a child of the zoomed canvas.

**HelpPage extras:** `openInfoDesk()` builds the same modal directly — **never called from the template** (dead). `ModalController` injected only for that. No data loading; no loader; no storage.

**Native plugins:** none directly (modal + pinch-zoom are web). **Navigation out:** `/app/tabs/conference-map`; external URLs; tel/mailto.

---

## 8. Page: Notification Settings (`src/app/pages/notification-settings/`)

| # | Item | Detail |
|---|---|---|
| 1 | Route / entry | `/app/tabs/notifications`; side menu → **Account** section → **Notifications** (`notifications-outline`), visible whether or not logged in. Selector `app-notification-settings`. |
| 2 | Purpose | Six per-category opt-in/out toggles + a master toggle, a "please update the native app" banner when the web bundle is newer than the binary, a hint about OS permission (iOS button to open app settings), and a staff diagnostics card showing/copying the FCM token. |
| 9 | Complexity | **3** — UI is a list of toggles, but the state semantics (master/mixed), platform gating, toast feedback and the live token stream all have to be reproduced exactly. |

**Toolbar title:** `Notifications`.

**Hero** (`.notif-hero`, `16px 16px 40px`): icon `notifications-outline` **72px** `#FFD779` (`margin-bottom:16px`); `<h1>Notifications</h1>`; `<p>` (`margin:6px 16px 0`) *Choose which alerts you want from the PyCon US app.*

**Update-required banner** (`*ngIf="needsAppUpdate"`): an `<a [href]="storeUrl" target="_blank" rel="noopener" class="notif-update-banner">` — flex row `gap:12px`, `margin:-24px 16px 12px`, `padding:14px 16px`, `border-radius:12px`, `background: linear-gradient(135deg, #FFD779 0%, #F5B935 100%)`, `color:#101136`, `box-shadow:0 4px 16px rgba(245,185,53,.35)`, `z-index:2`, `:active{opacity:.85}`. Children: icon `cloud-download-outline` (1.6rem, `aria-hidden`), `.notif-update-text` column with `<strong>Update required</strong>` (0.95rem/700) and `<span>This page needs the latest PyCon US app to work. Tap to open the App Store / Play Store.</span>` (0.78rem, opacity .85, lh 1.3), trailing icon `open-outline` (1rem, opacity .7, `aria-hidden`).
* `storeUrl` defaults to `APP_STORE_URL = 'https://apps.apple.com/us/app/pycon-us-2023/id6446810296'`; on hybrid Android it becomes `PLAY_STORE_URL = 'https://play.google.com/store/apps/details?id=org.pycon.us'`.
* `needsAppUpdate` is computed in the constructor, hybrid only: `!Capacitor.isPluginAvailable('FirebaseMessaging') || !Capacitor.isPluginAvailable('LocalNotifications')` (i.e. an Appflow live-update web bundle is running on an older store binary that was compiled without those native plugins). Never true on web.

**Toggle list `.notif-list`** (`*ngIf="loaded"`, `lines="full"`; `margin:-24px 16px 0; border-radius:16px; background: var(--ion-card-background,#fff); box-shadow:0 8px 32px rgba(16,17,54,.15); overflow:hidden`; items `--background:transparent`; `.notif-label h2 { 1rem; 600; margin:0 0 .25rem; white-space:normal }`, `p { .8rem; --ion-color-medium; white-space:normal }`). When `needsAppUpdate` the list also gets `.notif-list-disabled { opacity:.55; pointer-events:none }`.

| Row | h2 | p | Toggle binding |
|---|---|---|---|
| Master `.notif-master` (`--background: var(--ion-color-step-50,#f7f8fb)`, inner padding 14px top/bottom, h2 weight 700) | All notifications | `allDisabled ? 'Everything muted.' : (allEnabled ? 'Everything on.' : 'Mixed — toggle to set them all at once.')` | `[checked]="allEnabled"` → `onMasterToggle($event.detail.checked)` |
| | Lightning Talk sign-ups | Friday & Saturday morning nudges to submit on the dashboard before lunchtime selections. | `prefs.lightning` → `onToggle('lightning', …)` |
| | Open Space sign-ups | Reminds you 15 min before each day's open-space signup window opens. | `prefs.openSpace` |
| | Announcements | General conference updates — "keynote starting now," "opening reception in 20 minutes," etc. | `prefs.announcements` |
| | Schedule changes | Push when a session is rescheduled, moved to a different room, or cancelled. | `prefs.scheduleChanges` |
| | Daily digest | One push per day with the day's highlights, linking to the recap on us.pycon.org. | `prefs.dailyDigest` |
| | Emergency & safety alerts | Push when staff send a safety or emergency notice. | `prefs.emergency` |

All toggles are `<ion-toggle slot="end">` and fire `(ionChange)` only on user interaction (Ionic 7+ semantics), so programmatic `checked` updates after the master flip do not re-trigger handlers.

**Permission note `.notif-note`** (`*ngIf="loaded"`; `margin:24px 16px 16px`, flex column centred `gap:8px`): icon `information-circle-outline` (1.1rem, medium); `<ion-text color="medium"><p>` (0.8rem) *If you previously denied notification permission for this app, enable it from your device settings to receive alerts.*; then, only when `canOpenAppSettings` (= `platform.is('hybrid') && platform.is('ios')`), `<ion-button fill="outline" size="small" class="notif-open-settings-btn">` (margin-top 12px, `--border-radius:8px`) icon `settings-outline` **"Open PyCon US Settings"** → `openAppSettings()`: `window.open('app-settings:', '_system')`; on exception → `console.warn` + toast `Open Settings → PyCon US to manage notification permission.` (2500 ms, bottom).

**Diagnostics card `.notif-token-card`** (`*ngIf="fcmToken"`, `lines="none"`; `margin:16px; border-radius:12px; background: var(--ion-card-background,#fff); box-shadow:0 2px 8px rgba(16,17,54,.08); overflow:hidden`): `<ion-item-divider sticky="false">` **Diagnostics** (`--background: var(--ion-color-step-50,#f4f4f4)`, 0.72rem, 600, uppercase, `letter-spacing:.06em`, medium, `min-height:32px`); item with h2 **FCM registration token** and `<p class="notif-token">{{ fcmToken }}</p>` (`font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size:.7rem; word-break:break-all; user-select:all; color: medium`); a second item (`lines="none"`) holding `<ion-button expand="block" fill="outline" size="small" slot="end">` icon `copy-outline` **"Copy token"** → `copyToken()`: no-op if no token; `navigator.clipboard.writeText(token)` → toast `FCM token copied` (1500 ms, bottom, `color:'success'`); on failure toast `Could not copy — long-press the token to select.` (2500 ms).

No 80px bottom spacer on this page.

**State & lifecycle**
* Fields: `prefs: NotificationPrefs` initialised to all-true; `loaded=false`; `showTitle=false`; `fcmToken: string|null = null`; `needsAppUpdate=false`; `storeUrl`; `tokenSub?: Subscription`.
* Constructor: the hybrid plugin-availability check above.
* `ngOnInit()` (async): `prefs = await notifications.getPrefs()`; `loaded = true`; `tokenSub = notifications.fcmToken$.subscribe(t => fcmToken = t)`.
* `ngOnDestroy()`: `tokenSub?.unsubscribe()`.
* `onToggle(key, value)`: `prefs = {...prefs, [key]: value}`; `await notifications.setPref(key, value)`; toast `Notifications enabled` / `Notifications disabled` (1500 ms, bottom, default colour).
* `get allEnabled` = AND of all six; `get allDisabled` = AND of all six negated. A mixed state therefore shows the master toggle **off** with the "Mixed — …" subtitle; flipping it turns everything **on**.
* `onMasterToggle(value)`: sets all six to `value`; `await notifications.setAllPrefs(value)`; toast `All notifications enabled` / `All notifications muted` (1500 ms, bottom).

**Native plugins (direct):** `@capacitor/core` `Capacitor.isPluginAvailable(...)`; everything else goes through `NotificationsService`. `window.open('app-settings:')` is an iOS-only URL scheme.

**Analytics:** emitted by the service (`toggle_notification`, `toggle_all_notifications`, user properties). **Accessibility:** banner icons `aria-hidden="true"`; token text `user-select:all` so it can be long-pressed; nothing else.

---

## 9. Provider: `NotificationsService` (`src/app/providers/notifications.service.ts`, `providedIn: 'root'`)

### 9.1 Types and constants
```ts
type NotificationCategory = 'lightning' | 'openSpace' | 'emergency' | 'announcements' | 'scheduleChanges' | 'dailyDigest';
interface NotificationPrefs { lightning; openSpace; emergency; announcements; scheduleChanges; dailyDigest: boolean }
interface ScheduledReminder { id: number; category: 'lightning'|'openSpace'|'announcements'; title; body: string; fireAt: Date }
const PREF_KEY = 'notification_prefs';                        // Ionic Storage key (DB name = environment.storageKey)
const DEFAULT_PREFS = { all six: true };                      // opt-IN by default
const TOPIC_BY_CATEGORY = { emergency: 'emergency', announcements: 'announcements', scheduleChanges: 'schedule-changes', dailyDigest: 'daily-digest' };
// lightning & openSpace have NO FCM topic — they are purely client-scheduled local notifications.
const REMINDER_ID_BASE = 8000;                                 // local-notification ids 8000..8010 (= 8000 + index in REMINDERS)
// test notification id = 8999 (outside the reminder range so applyPrefs never cancels it)
```

### 9.2 `REMINDERS` table (exact copy; all times `-07:00` = PDT; index → id = 8000+index)

| idx / id | category | title | body | fireAt |
|---|---|---|---|---|
| 0 / 8000 | lightning | Lightning Talk sign-ups are open | Submit on the PyCon US dashboard for Saturday morning's lightning talks. Speakers picked by 1 PM. | `2026-05-15T09:00:00-07:00` |
| 1 / 8001 | lightning | Last call: Lightning Talk sign-ups | Submit on the PyCon US dashboard for Sunday morning's lightning talks. Speakers picked by 1 PM. | `2026-05-16T09:00:00-07:00` |
| 2 / 8002 | openSpace | Open Space sign-ups open soon | Friday slots open Thursday at 5:00 PM PDT. | `2026-05-14T16:45:00-07:00` |
| 3 / 8003 | openSpace | Open Space sign-ups open soon | Saturday slots open at 8:00 AM PDT. | `2026-05-16T07:45:00-07:00` |
| 4 / 8004 | openSpace | Open Space sign-ups open soon | Sunday slots open at 8:00 AM PDT. | `2026-05-17T07:45:00-07:00` |
| 5 / 8005 | announcements | Keynote starting in 15 min | Lin Qiao — Pacific Ballroom (Arena). Starts 9:45 AM. | `2026-05-15T09:30:00-07:00` |
| 6 / 8006 | announcements | D&I Panel starting in 15 min | Diversity & Inclusion Panel — Pacific Ballroom (Arena). Starts 9:00 AM. | `2026-05-16T08:45:00-07:00` |
| 7 / 8007 | announcements | Keynote starting in 15 min | Pablo Galindo Salgado (En Español) — Pacific Ballroom (Arena). Starts 9:25 AM. | `2026-05-16T09:10:00-07:00` |
| 8 / 8008 | announcements | Keynote starting in 15 min | amanda casari — Pacific Ballroom (Arena). Starts 9:00 AM. | `2026-05-17T08:45:00-07:00` |
| 9 / 8009 | announcements | Keynote starting in 15 min | Rachell Calhoun & Tim Schilling — Pacific Ballroom (Arena). Starts 3:15 PM. | `2026-05-17T15:00:00-07:00` |
| 10 / 8010 | announcements | Steering Council Panel in 15 min | Python Steering Council Panel — Pacific Ballroom (Arena). Starts 4:00 PM. | `2026-05-17T15:45:00-07:00` |

Source-comment context baked into the file: PyCon US 2026 Thu = May 14, Fri = May 15, Sat = May 16, Sun = May 17; lightning-talk cycles 5 AM→9 AM and 9 AM→1 PM PDT; open-space signup opens Thu 5:00 PM (Fri slots), Sat 8:00 AM, Sun 8:00 AM; keynote times from `pycon-site/load-breaks-and-plenaries.py`. The keynote reminders are gated by the **announcements** toggle (no separate category).

### 9.3 `TEST_NOTIFICATION_COPY` (used by Dev Tools "Test in 5s")

| category | title | body |
|---|---|---|
| lightning | [TEST] Lightning Talk sign-ups are open | Submit on the dashboard. Speakers picked at lunch. |
| openSpace | [TEST] Open Space sign-ups open soon | Saturday slots open at 8:00 AM PDT. |
| announcements | [TEST] Keynote starting now | Head to the Plenary Hall — keynote begins in 5 minutes. |
| scheduleChanges | [TEST] Schedule change | A favorited session has moved rooms — tap for details. |
| dailyDigest | [TEST] Today at PyCon US | Today's highlights and recap — tap to read on us.pycon.org. |
| emergency | [TEST] Safety notice | This is a drill — staff would send real-time guidance here. |

### 9.4 Members and behaviour
* `private prefs = {...DEFAULT_PREFS}`; `private storageReady = storage.create()`; `readonly fcmToken$ = new BehaviorSubject<string|null>(null)`.
* **Constructor** → `attachTokenListener()`: hybrid only. `FirebaseMessaging.addListener('tokenReceived', e => { if (e?.token) fcmToken$.next(e.token) })` (errors swallowed) and an eager `FirebaseMessaging.getToken().then(res => fcmToken$.next(res.token))` because `tokenReceived` only fires on rotation.
* **`getPrefs()`**: await storageReady; `saved = storage.get('notification_prefs')`; if it is an object → `prefs = {...DEFAULT_PREFS, ...saved}` (unknown/new categories default **on**); returns a copy.
* **`setPref(key, value)`**: await storageReady; update `prefs`; `storage.set(PREF_KEY, prefs)`; if the category has a topic → `syncTopic(topic, value)`; `await applyPrefs()`; `logToggle(key, value)` → event `toggle_notification` `{ category: key, enabled: value }`; `setUserProperty(key, value)`.
* **`setAllPrefs(value)`**: await storageReady; set every key; persist once; `await applyPrefs()`; event `toggle_all_notifications` `{ enabled: value }`; `setUserProperty` for every key.
* **`snapshotPrefsToAnalytics()`** (private): `setUserProperty(k, prefs[k])` for all six — called at the start of every `applyPrefs()`.
* **`logEvent(name, params)`** (private): hybrid only; `FirebaseAnalytics.logEvent({ name, params })`, `console.warn` on failure.
* **`setUserProperty(key, value)`** (private): hybrid only; `FirebaseAnalytics.setUserProperty({ key: \`notif_${key}\`.slice(0,24), value: value ? 'on' : 'off' })` → keys `notif_lightning`, `notif_openSpace`, `notif_emergency`, `notif_announcements`, `notif_scheduleChanges`, `notif_dailyDigest`.
* **`syncTopic(topic, enabled)`** (private): hybrid only; `FirebaseMessaging.subscribeToTopic({ topic })` / `unsubscribeFromTopic({ topic })`; failures logged with `console.warn`, never thrown.
* **`scheduleCategoryTestNotification(category)`** → `{outcome:'web'}` if not hybrid; `{outcome:'muted'}` if `!prefs[category]`; `{outcome:'denied'}` if `!ensurePermission()`; otherwise `LocalNotifications.cancel({ notifications:[{id:8999}] })` then `LocalNotifications.schedule({ notifications:[{ id:8999, title, body, schedule:{ at: now+5000ms, allowWhileIdle:true } }] })` → `{outcome:'fired', fireAt}`.
* **`applyPrefs()`**: hybrid only (returns immediately on web). Steps: (1) `snapshotPrefsToAnalytics()`; (2) for each `(category, topic)` in `TOPIC_BY_CATEGORY` → `await syncTopic(topic, prefs[category])` — **re-asserts all four topic subscriptions on every call**; (3) `try { granted = await ensurePermission(); if (!granted) return; cancel ids 8000..8010; now = Date.now(); for each reminder: skip if pref off or fireAt <= now; else push {id: 8000+idx, title, body, schedule:{at: fireAt, allowWhileIdle:true}}; if any → LocalNotifications.schedule({notifications}) } catch → console.warn('NotificationsService: applyPrefs failed')`.
* **`shouldShowPushBanner()`** = `emergency || announcements || scheduleChanges || dailyDigest` (lightning/openSpace are irrelevant to pushes).
* **`ensurePermission()`** (private): `LocalNotifications.checkPermissions()` (exception → false); `display==='granted'` → true; `display==='denied'` → **false without prompting**; otherwise (`prompt`/`prompt-with-rationale`) `requestPermissions()` → `display==='granted'`.

### 9.5 Who calls it
* `AppComponent.ngOnInit` (deferred `setTimeout(..., 5000)` after first render): `notifications.getPrefs().then(() => notifications.applyPrefs())` — every cold start re-arms future reminders and cleans up past ones.
* `AppComponent.checkNotifications()` (same 5 s timer): `FirebaseMessaging.addListener('tokenReceived', e => console.info(...))`; `FirebaseMessaging.requestPermissions().then(r => { if (r.receive !== 'granted') return; FirebaseMessaging.getToken() })` — this is the **push permission prompt**; `FirebaseMessaging.addListener('notificationReceived', ...)` → `showed = notifications.shouldShowPushBanner()`; `FirebaseAnalytics.logEvent({ name:'notification_received', params:{ topic: event?.notification?.data?.['topic'] ?? 'unknown', banner_shown: showed } })`; if `showed`, `ToastController.create({ message: body ? \`${title}: ${body}\` : title, position:'top', buttons:[{ icon:'close', side:'end', role:'cancel' }] })` — no duration, so the foreground banner stays until dismissed; `title` defaults to `'PyCon US'`.
* `NotificationSettingsPage` (getPrefs/setPref/setAllPrefs/fcmToken$).
* `DevToolsPage` (dev builds only; menu item appears when `!environment.production`): card "Notification tests" with subtitle *Each button schedules a sample notification 5 seconds out — but only if the matching toggle on the Notifications settings page is ON. Flip a toggle off and re-tap to confirm gating works.*; rows (icon `notifications-outline`, h2 label, p "Test in 5s") for `lightning` "Lightning Talk sign-ups", `openSpace` "Open Space sign-ups", `announcements` "Announcements", `scheduleChanges` "Schedule changes", `dailyDigest` "Daily digest", `emergency` "Emergency & safety"; outcome toasts: fired → `${label}: firing at ${fireAt.toLocaleTimeString()}.` (success), muted → `${label}: toggle is OFF — gating works, no notification scheduled.` (warning), denied → `${label}: OS notification permission denied.` (danger), web → `${label}: only fires on iOS / Android.` (medium); 2500 ms bottom.

### 9.6 Native plugins & options
`@capacitor/local-notifications` (`checkPermissions`, `requestPermissions`, `cancel`, `schedule` with `{ id, title, body, schedule: { at: Date, allowWhileIdle: true } }` — no channel, sound, icon, actionTypeId, extra or group), `@capacitor-firebase/messaging` (`addListener('tokenReceived')`, `getToken`, `subscribeToTopic`, `unsubscribeFromTopic`; in AppComponent also `requestPermissions`, `addListener('notificationReceived')`), `@capacitor-firebase/analytics` (`logEvent`, `setUserProperty`). **Web:** every native call is guarded by `platform.is('hybrid')`; prefs still persist and toggles still "work" visually on the PWA.

Looks hard to port because: exact-time local notifications (`allowWhileIdle`), FCM topic subscription, and Firebase Analytics user properties all need platform code; the behaviour (deterministic ids, cancel-then-reschedule, past-time skipping, permission state machine) must be replicated precisely.

---

## 10. Provider: `LiveUpdateService` (`src/app/providers/live-update.service.ts`, `providedIn:'root'` and also listed in `AppModule.providers`)

Wraps Ionic **Appflow Live Updates** (OTA replacement of the web bundle inside the native shell).

* Fields: `updateAvailable:any=null`; `needsUpdate=false`; `build='base'`; `appVersion=''`; `snapshot:{id,buildId}|null=null`; `channel=''`.
* Constructor: `App.addListener('appStateChange', ({isActive}) => { if (isActive) this.checkForUpdate(); })` — re-checks on every foreground resume.
* `updateAppInfo()`: `info = await App.getInfo()`; `appVersion = info.version` (iOS `CFBundleShortVersionString` / Android `versionName` = `26.2.1`); `build = info.build` (iOS `CFBundleVersion` `1` / Android `versionCode` `26022`).
* `reload()`: `await LiveUpdates.reload()` (restarts the WebView on the downloaded snapshot); `needsUpdate=false`.
* `checkForUpdate()`: `await updateAppInfo()`; `result = await LiveUpdates.sync()`; `updateAvailable=result`; `snapshot=result.snapshot`; `channel = result.liveUpdate?.channel || ''`; if `result.activeApplicationPathChanged` → `needsUpdate=true` and `document.body.classList.add('has-pending-update')` (class is never removed except by the reload itself).
* `performAutomaticUpdate()`: `LoadingController` loader `message:'Installing the latest build...'`, `duration:60000`; present; if `needsUpdate` → `reload()`; `setTimeout(() => loader.dismiss(), 1000)`.
* Callers of `checkForUpdate()`: `AppComponent.ngOnInit` (+5 s), `AboutPyconPage.ngOnInit`, `SchedulePage` (line 140), and the resume listener. `performAutomaticUpdate()` is wired to two UI affordances in `app.component.html`: (a) a global `<button class="update-banner">` rendered as the first child of `<ion-app>` above the split pane (gradient `135deg var(--ion-color-primary) → var(--ion-color-primary-shade)`, white text, `padding-top: calc(10px + env(safe-area-inset-top))`, icon `cloud-download-outline`, `<strong>New version available</strong>` + `Tap to update`, chevron `chevron-forward`, pulsing box-shadow animation 2.4 s disabled under `prefers-reduced-motion`); (b) a side-menu item `.update-cta` "Install Latest Update" / "New content is ready — tap to refresh" (`autoHide="true"` menu toggle). `<ion-app>` also gets class `has-update-banner`.
* Config (capacitor.config.ts → `plugins.LiveUpdates`): `appId: 'e8e09c7a'`, `channel: 'Production'`, `autoUpdateMethod: 'none'`, `maxVersions: 3`, `enabled: true`. With `autoUpdateMethod:'none'`, `sync()` downloads the latest snapshot for the channel in the background and only reports it; nothing is applied until `reload()`.
* `snapshot.buildId` and `channel` surface only on the About PyCon "Developer Info" panel.
* Web behaviour: `App.getInfo()` and `LiveUpdates.sync()` are not implemented on web, so `checkForUpdate()` rejects (unhandled promise) before setting anything; `appVersion` stays `''` and `build` stays `'base'`; no banner ever appears.
* Native plugins: `@capacitor/live-updates` (`sync`, `reload`), `@capacitor/app` (`getInfo`, `addListener('appStateChange')`).
* Release side (Makefile): `appflow-ship` builds the web bundle on Appflow for app `e8e09c7a` and deploys it to channel `Production`; `capsync` runs `appflow live-update generate-manifest --build-dir=www` so the shipped binary carries a manifest for differential updates.

Looks hard to port because: there is no equivalent of an OTA web-bundle swap in a compiled Flet/Flutter app. The *observable* behaviours that would need an equivalent are only: showing app version/build on the About page and (optionally) a "new version available" banner.

---

## 11. Native & project configuration

### 11.1 Identity, versions, platform floors (single source table)

| Item | Value | Where |
|---|---|---|
| Display name | `PyCon US` | capacitor.config `appName`; Info.plist `CFBundleDisplayName`; `INFOPLIST_KEY_CFBundleDisplayName`; Android `strings.xml` `app_name` & `title_activity_main` |
| PWA name | `PyCon US 2026` (name & short_name); `<title>PyCon US 2026</title>` | `src/manifest.json`, `src/index.html` |
| Capacitor `appId` | `org.pycon.us.2023.onsite` | `capacitor.config.ts` |
| iOS bundle id | `org.pycon.us.2023.onsite` (`PRODUCT_BUNDLE_IDENTIFIER`, both Debug/Release) | `project.pbxproj`; matches `GoogleService-Info.plist` `BUNDLE_ID` |
| Android applicationId / namespace | `org.pycon.us` (also `strings.xml` `package_name` and `custom_url_scheme`) | `android/app/build.gradle`; matches `google-services.json` `package_name` |
| App Store listing | `https://apps.apple.com/us/app/pycon-us-2023/id6446810296` | notification-settings.page.ts |
| Play Store listing | `https://play.google.com/store/apps/details?id=org.pycon.us` | notification-settings.page.ts |
| Version | iOS `MARKETING_VERSION = 26.2.1`, `CURRENT_PROJECT_VERSION = 1`; Android `versionName "26.2.1"`, `versionCode 26022` | pbxproj / build.gradle |
| package.json version | `26.0.0` (name `ionic-conference-app`, unrelated to store versions) | package.json |
| iOS deployment target | `IPHONEOS_DEPLOYMENT_TARGET = 18.0` (Podfile says `platform :ios, '16.0'` but `assertDeploymentTarget` post-install aligns pods) | pbxproj / Podfile |
| Android SDKs | `minSdkVersion 34`, `compileSdkVersion 35`, `targetSdkVersion 35` (comment: intentional — only OS versions still receiving vendor security updates) | `android/variables.gradle` |
| Java | `VERSION_21` source/target | `capacitor.build.gradle` |
| AGP / google-services | `com.android.tools.build:gradle:8.8.2`, `com.google.gms:google-services:4.4.2` | `android/build.gradle` |
| Dev team | `DEVELOPMENT_TEAM = BMM5U3QVKW` | pbxproj |
| Device families | iPhone + iPad (`TARGETED_DEVICE_FAMILY = "1,2"`); orientations iPhone: Portrait, LandscapeLeft, LandscapeRight; iPad: + PortraitUpsideDown | pbxproj / Info.plist |
| App Store category | `public.app-category.utilities` | pbxproj |
| Xcode scheme | `PyCon US` (`ios/App/App.xcodeproj/xcshareddata/xcschemes/PyCon US.xcscheme`); Podfile target `'PyCon US'` | |
| Firebase project | `pycon-us-2023-mobile` (project number / GCM sender id `328295262241`, storage bucket `pycon-us-2023-mobile.firebasestorage.app`) | `google-services.json`, `GoogleService-Info.plist` |
| Appflow app | `e8e09c7a`, channel `Production` | capacitor.config.ts, Makefile |
| Web runtime origin | `server.hostname: 'mobile.us.pycon.org'`, `androidScheme: 'https'` → WebView origin `https://mobile.us.pycon.org` on Android, `capacitor://mobile.us.pycon.org` on iOS | capacitor.config.ts |
| Browserslist | Chrome ≥60, ChromeAndroid ≥60, Firefox ≥63 + ESR, Edge ≥79, Safari ≥13, iOS ≥13 | `.browserslistrc` |

### 11.2 `capacitor.config.ts` (verbatim semantics)
```ts
appId: 'org.pycon.us.2023.onsite', appName: 'PyCon US', webDir: 'www', bundledWebRuntime: false,
server: { hostname: 'mobile.us.pycon.org', androidScheme: 'https' },
ios: { scheme: 'PyCon US' },             // WebView content scheme setting, unusual value with a space
plugins: {
  SplashScreen: { launchAutoHide: false, backgroundColor: '#680579', showSpinner: false },
  LiveUpdates: { appId: 'e8e09c7a', channel: 'Production', autoUpdateMethod: 'none', maxVersions: 3, enabled: true }
}
```
**Gotcha:** the committed file is missing the commas after the `server` and `ios` object literals (a TypeScript syntax error). The generated per-platform `capacitor.config.json` files (`ios/App/App/capacitor.config.json`, `android/app/src/main/assets/capacitor.config.json`) are git-ignored, so the shipped values cannot be confirmed from the repo. `capacitor.config.json` at the root is `{}`. `SplashScreen.hide()` is called manually from `AppComponent.initializeApp()` once `confData.load()` emits or errors (hybrid only).

### 11.3 Android
**`AndroidManifest.xml`**
* `<application android:allowBackup="true" android:icon="@mipmap/ic_launcher" android:roundIcon="@mipmap/ic_launcher_round" android:label="@string/app_name" android:supportsRtl="true" android:theme="@style/AppTheme" android:hardwareAccelerated="true">`
* `<meta-data android:name="asset_statements" android:resource="@string/asset_statements"/>` → `[{"include": "https://us.pycon.org/.well-known/assetlinks.json"}]` (Digital Asset Links statement — enables credential sharing/autofill with us.pycon.org; there is **no** `VIEW` intent-filter, so this does **not** create App Links/deep links).
* `<meta-data android:name="com.google.firebase.messaging.default_notification_icon" android:resource="@drawable/ic_launcher"/>` (FCM small icon = launcher PNG; no default channel id, no default colour).
* `<meta-data android:name="google_analytics_adid_collection_enabled" android:value="false"/>` and `<uses-permission android:name="com.google.android.gms.permission.AD_ID" tools:node="remove"/>` — advertising-ID collection disabled and the auto-merged permission stripped (Play Console declaration).
* `MainActivity` (`org.pycon.us.MainActivity`): `launchMode="singleTask"`, `exported="true"`, theme `@style/AppTheme.NoActionBarLaunch`, `configChanges` = orientation|keyboardHidden|keyboard|screenSize|locale|smallestScreenSize|screenLayout|uiMode|navigation, intent-filter MAIN/LAUNCHER only.
* `FileProvider` `androidx.core.content.FileProvider`, authority `${applicationId}.fileprovider`, paths from `res/xml/file_paths.xml`: `<external-path name="my_images" path="."/>` and `<cache-path name="my_cache_images" path="."/>` (needed by `Share.share` of the About-page debug dump written to `Directory.Cache`).
* Permissions declared: `android.permission.INTERNET`, `android.permission.CAMERA` (badge QR scanning — other slice). `POST_NOTIFICATIONS` is not declared here; it is merged from the local-notifications / firebase-messaging plugin manifests (runtime prompt on API 33+, i.e. always on this minSdk).
* `<uses-sdk tools:overrideLibrary="com.google.zxing.client.android"/>`.

**`build.gradle` (app)**: `namespace "org.pycon.us"`, `applicationId "org.pycon.us"`, `versionCode 26022`, `versionName "26.2.1"`, `aaptOptions.ignoreAssetsPattern '!.svn:!.git:!.ds_store:!*.scc:.*:!CVS:!thumbs.db:!picasa.ini:!*~'`, release `minifyEnabled false`; deps `appcompat 1.7.0`, `coordinatorlayout 1.2.0`, `core-splashscreen 1.0.1`, `:capacitor-android`, `:capacitor-cordova-android-plugins`; applies `com.google.gms.google-services` only if `google-services.json` is non-empty. `variables.gradle` also pins CameraX `1.4.2` (16 KB page alignment for Play).

**Native plugin set (`capacitor.build.gradle` / `capacitor.plugins.json` / Podfile — identical lists):** `@capacitor-firebase/analytics`, `@capacitor-firebase/messaging`, `@capacitor-mlkit/barcode-scanning`, `@capacitor/app`, `@capacitor/device`, `@capacitor/filesystem`, `@capacitor/haptics`, `@capacitor/inappbrowser`, `@capacitor/keyboard`, `@capacitor/live-updates`, `@capacitor/local-notifications`, `@capacitor/network`, `@capacitor/share`, `@capacitor/splash-screen`, `@capacitor/status-bar`, `@ebarooni/capacitor-calendar`. (Versions in package.json: Capacitor core/android/ios `^7.0.0`, firebase plugins `^7.5.0`, local-notifications `^7.0.6`, live-updates `^0.4.0`, inappbrowser `^2.0.0`, mlkit barcode `^7.0.0`, calendar `^7.2.0`, `firebase` JS SDK `^11.10.0` (installed but unused in this slice), `@ionic/angular ^8.4.3`, `@ionic/storage-angular ^4.0.0`, `@ciag/ngx-pinch-zoom 13.3.0`, `crypto-js ^4.2.0`, `js-base64 ^3.7.7`.)

**Resources**: `strings.xml` (`app_name`, `title_activity_main` = `PyCon US`; `package_name`/`custom_url_scheme` = `org.pycon.us`; `asset_statements`); `styles.xml`: `AppTheme` (AppCompat Light DarkActionBar with `colorPrimary/Dark/Accent` referencing `@color/*` — **`values/colors.xml` does not exist in the repo**), `AppTheme.NoActionBar` (DayNight.NoActionBar), `AppTheme.NoActionBarLaunch` (`parent="Theme.SplashScreen"`, `android:background="@drawable/splash"`). Splash drawables: `drawable/splash.png` (320×480) plus `drawable-{port,land}-{ldpi…xxxhdpi}/splash.png` and `-night-` variants and `drawable-night/splash.png`. Launcher: `mipmap-anydpi-v26/ic_launcher.xml` adaptive icon = `@mipmap/ic_launcher_background` + `@mipmap/ic_launcher_foreground` PNGs inset 16.7%; `values/ic_launcher_background.xml` colour `#FFFFFF`; legacy `drawable-*/ic_launcher.png`; `ic_launcher-playstore.png` 512×512; `drawable/ic_launcher_background.xml` is the unused Android Studio default green grid. `MainActivity.java` extends `BridgeActivity` and sets `SYSTEM_UI_FLAG_LAYOUT_STABLE`. `res/xml/config.xml` is an empty Cordova stub (`<access origin="*"/>`). `gradle.properties`: `org.gradle.jvmargs=-Xmx1536m`, `android.useAndroidX=true`.

### 11.4 iOS
**`Info.plist`**: `CFBundleDevelopmentRegion en`; `CFBundleDisplayName PyCon US`; versions from build settings; `LSRequiresIPhoneOS`; **usage strings**: `NSCameraUsageDescription` = "Scanning Attendee badge QR codes", `NSCalendarsUsageDescription` and `NSCalendarsWriteOnlyAccessUsageDescription` = "Add PyCon US sessions to your calendar"; `UILaunchStoryboardName LaunchScreen`; `UIMainStoryboardFile Main`; `UIRequiredDeviceCapabilities [armv7]`; orientations as above; `UIViewControllerBasedStatusBarAppearance true`. **No** `CFBundleURLTypes` (no custom URL scheme), **no** `UIBackgroundModes`, **no** location/photo/microphone strings.

**`App.entitlements`**: `aps-environment = development` (push; Xcode switches to production for App Store builds), `com.apple.developer.associated-domains = [ "webcredentials:us.pycon.org" ]` (shared web credentials / password autofill with us.pycon.org). **No `applinks:`** → no Universal Links.

**`AppDelegate.swift`**: `FirebaseApp.configure()` in `didFinishLaunching` (DEBUG builds also enable WebView inspection after 5 s); `didRegisterForRemoteNotificationsWithDeviceToken` sets `Messaging.messaging().apnsToken`, fetches the FCM token and posts `.capacitorDidRegisterForRemoteNotifications` (or `…FailToRegister…`); `messaging(_:didReceiveRegistrationToken:)` posts `Notification.Name("FCMToken")`; `didFailToRegister…` forwards the error; `open url` and `continue userActivity` forward to `ApplicationDelegateProxy` (Capacitor App plugin).

**Launch screen**: `Base.lproj/LaunchScreen.storyboard` and `UILaunchScreen.storyboard`: a single `UIImageView` named `Splash`, `contentMode=scaleAspectFill`, pinned to all edges, view `backgroundColor` sRGB (0.40784, 0.01961, 0.47059) = **`#680579`** (same purple as the Capacitor splash and the PWA shell). `Assets.xcassets/Splash.imageset`: universal 1x/2x/3x `Default@{1,2,3}x~universal~anyany.png` plus `-dark` appearance variants (2732×2732), and three stray `splash-2732x2732*.png`. `AppIcon.appiconset`: single universal 1024 `AppIcon-512@2x.png`; a leftover `AppIcon 1.appiconset` (iPad 40@2x) is unused (`ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon`).

**`Podfile`**: `platform :ios, '16.0'`, `use_frameworks!`, `install! 'cocoapods', :disable_input_output_paths => true`, the Capacitor pods listed above, `post_install assertDeploymentTarget`. Comments explain that FirebaseMessaging comes transitively (plugin pins `~> 11.7.0`) and that the Analytics subspec is forced via patch-package.

**`GoogleService-Info.plist`** (identifiers only): `BUNDLE_ID org.pycon.us.2023.onsite`, `PROJECT_ID pycon-us-2023-mobile`, `GCM_SENDER_ID 328295262241`, `IS_GCM_ENABLED true`, **`IS_ANALYTICS_ENABLED false`** (note: analytics calls are still made from JS).

### 11.5 Firebase (hosting side) and `.firebaserc`
* `.firebaserc` → `{"projects": {"default": "ionic-ng-conf-app"}}` — a leftover from the Ionic conference-app template; **not** the mobile Firebase project.
* `firebase.json`: Hosting `public: www`, ignore `firebase.json`, dotfiles, `node_modules`; SPA rewrite `** → /index.html`; headers: `ngsw-worker.js` → `Cache-Control: no-cache`; `/` → a huge `Link:` HTTP/2-push preload header listing hashed bundle names (`25.1b3c099ae403f43312d0.js`, `main.d18c9fbebcc1ea7206dd.js`, `assets/img/ica-slidebox-img-1.png` …) that no longer exist — stale output of `generate-h2-push.js`.
* **`generate-h2-push.js`** (Node + puppeteer): loads `http://127.0.0.1:8080` (or argv[1]) with the service worker disabled, records every same-origin request on reload (excluding `.gz .map 3rdpartylicenses.txt ngsw-manifest.json ngsw.json worker-basic.min.js ngsw-worker.js favicon index.html manifest.webmanifest .svg`), builds `</path>;rel=preload;as=script|style,` entries and regex-replaces the `Link` header value inside `firebase.json`. Purely a PWA-hosting optimisation; irrelevant to a native port.

### 11.6 PWA bits
* **`src/manifest.json`**: `name`/`short_name` `PyCon US 2026`; `start_url index.html`; `display standalone`; icons `assets/icons/icon-{48,72,96,128,192,256,512}.webp` each declared `"type": "image/png"` (mismatch — files are WebP), `"purpose": "any maskable"`; `background_color` and `theme_color` **`#387ef5`** (Ionic-blue leftover, inconsistent with the purple splash and indigo headers).
* **`src/index.html`**: `<html lang="en" dir="ltr">`; `<title>PyCon US 2026</title>`; viewport `viewport-fit=cover, width=device-width, initial-scale=1.0, minimum-scale=1.0, maximum-scale=1.0, user-scalable=no`; `format-detection telephone=no`; `msapplication-tap-highlight no`; `theme-color #387ef5`; `apple-mobile-web-app-capable yes`; `apple-mobile-web-app-status-bar-style black-translucent`; `<base href="/">`; favicon and `apple-touch-icon` both → `assets/img/appicon.png` (300×249, non-square); `<link rel="manifest" href="manifest.json">`. Inside `<app-root>` an inline **app shell**: `.app-shell` full-viewport flex column centred, `background-color:#680579`, `<img src="assets/img/splash.png" alt="PyCon US 2026">` (max 60% w / 40% h; source is 5559×6984) and a 32px CSS ring spinner (`3px solid rgba(255,255,255,.3)`, white top, `spin .8s linear infinite`) — shown until Angular bootstraps. `<noscript>Please enable JavaScript to continue using this application.</noscript>`.
* **Service worker**: `AppModule` registers `ngsw-worker.js` with `enabled: environment.production`; `angular.json` production config sets `serviceWorker: true`. **`ngsw-config.json`**: `index /index.html`; assetGroup `app` (`installMode prefetch`): `/favicon.ico`, `/index.html`, `/*.css`, `/*.js`; assetGroup `assets` (`installMode lazy`, `updateMode prefetch`): `/assets/**`. **No `dataGroups`** → `conference.json` is never cached by the SW; offline data comes from Ionic Storage key `schedule-cache`.
* **Ionic Storage**: `IonicStorageModule.forRoot({ name: environment.storageKey })` → DB name `__pycon_us_mobile_2026` (prod), `__pycon_us_mobile_base_2026` (default `environment.ts`), `__pycon_us_mobile_development_2026` (dev). Default drivers (IndexedDB → localStorage). All keys in this slice: `notification_prefs`, and (read-only here) `hasLoggedIn`, `email`, `key`, `secret`, `schedule-cache`, `theme`.
* `angular.json` copies `src/assets/**` → `assets/`, ionicons SVGs → `./svg`, `src/manifest.json` → `/`; styles `src/theme/variables.scss` + `src/global.scss`; production: `outputHashing all`, budgets `initial` 2 MB warn / 5 MB error, `anyComponentStyle` 6 kB warn; `development` config swaps `environment.dev.ts`.

### 11.7 Environments (`src/environments/`)
| file | name | production | baseUrl | storageKey | timezone / utcOffset |
|---|---|---|---|---|---|
| `environment.ts` (default) | `base` | false | `https://us.pycon.org` | `__pycon_us_mobile_base_2026` | `America/Los_Angeles` / `-7` |
| `environment.prod.ts` | `production` | true | `https://us.pycon.org` | `__pycon_us_mobile_2026` | same |
| `environment.dev.ts` | `development` | false | `` `http://${devHost}:8000` `` with `devHost = Capacitor.getPlatform()==='android' ? '10.0.2.2' : '127.0.0.1'` | `__pycon_us_mobile_development_2026` | same |

Feed endpoint used by everything in this slice: `GET ${baseUrl}/2026/schedule/conference.json` (10 s timeout) → `conference.content.{about, about-psf, code-of-conduct, wifi, social-media, venues-hours}` (HTML strings) and `conference.sponsors` (level → array).

### 11.8 Legacy `config.xml` (root)
A stale Cordova template that Capacitor does not use: `id="io.ionic.starter"`, `version 0.0.1`, name `MyApp`, author Ionic; `<access origin="*"/>`; `allow-intent` for `http://*/*`, `https://*/*`, `tel:*`, `sms:*`, `mailto:*`, `geo:*`, Android `market:*`, iOS `itms:*`, `itms-apps:*`; preferences `ScrollEnabled false`, `BackupWebStorage none`, `SplashMaintainAspectRatio true`, `FadeSplashScreenDuration 300`, `SplashShowOnlyFirstTime false`, `SplashScreen screen`, `SplashScreenDelay 3000`; Android `Scheme http`, `networkSecurityConfig @xml/network_security_config` from `resources/android/xml/network_security_config.xml` (**file does not exist**); icon/splash tables pointing at `resources/{android,ios}/...` (cordova-res layout); cordova plugins `statusbar 2.4.2`, `device 2.0.2`, `splashscreen 5.0.2`, `ionic-webview ^5.0.0`, `ionic-keyboard ^2.0.5`. `ionic.config.json` (`name: pycon-us-2023`, `type: angular`) still lists both `capacitor` and `cordova` integrations. The only thing worth keeping from it is the *intent list* (tel/sms/mailto/geo/market/itms) as documentation of which external schemes the app expects to hand off.

### 11.9 `.well-known/`
Only `.well-known/funding-manifest-urls` containing `https://www.python.org/funding.json` — a FLOSS/fund "funding manifest" pointer served by the PWA host. **There is no `assetlinks.json` and no `apple-app-site-association` in the repo**; the Android `asset_statements` points at `https://us.pycon.org/.well-known/assetlinks.json` which is served by the website, not this app. Net: **no deep links / app links / universal links exist**; the associated-domain entries are for credential autofill only.

### 11.10 `patches/` (patch-package, run on `npm postinstall`)
`@capacitor-firebase+analytics+7.5.0.patch` edits `node_modules/@capacitor-firebase/analytics/CapacitorFirebaseAnalytics.podspec`: `s.default_subspec = 'Lite'` → `'Analytics'`, so the iOS pod actually links FirebaseAnalytics (the `Lite` subspec omits it and `logEvent`/`setUserProperty` would be no-ops on iOS). Patched at the podspec level because `cap sync` rewrites the Podfile.

### 11.11 `resources/`
cordova-res style inputs: `resources/icon.png` (2048×2048), `resources/splash.png` (2048×2048), `resources/app-resources.ai` (source artwork); generated `resources/ios/icon/*.png` (icon-20…icon-1024, AppIcon-*), `resources/ios/splash/Default*.png` (all legacy iPhone/iPad sizes), `resources/android/icon/drawable-*-icon.png`, `drawable-playstore-512-icon.png`, `mipmap-*/ic_launcher.png`, `resources/android/splash/drawable-{port,land}-*-screen.png`. `@capacitor/assets ^3.0.5` and `cordova-res 0.15.4` are in devDependencies. The native projects already contain their own copies (see 11.3/11.4); the real brand assets for a port are `resources/icon.png`, `resources/splash.png` (+ `.ai` sources), `src/assets/img/pycon-us-2026-logo.svg`, and the purple `#680579` splash background.

### 11.12 `Makefile` targets
| target | what it does |
|---|---|
| `install` | `npm install` |
| `serve` | `npx ionic serve --configuration=development` (dev env, local API) |
| `build` | `npx ng build` |
| `capsync` | `npm run capsync` = `ng build --configuration production && appflow live-update generate-manifest --build-dir=www && npx ionic cap sync --no-build`, then `check-no-dev-url` |
| `check-no-dev-url` | fails if `ios/App/App/capacitor.config.json` or `android/app/src/main/assets/capacitor.config.json` contains `"url"` (a live-reload `server.url` baked into a store build caused the **26.2.0 white-screen incident**) |
| `lint` / `test` / `e2e` / `check` | `npm run lint` / `npm run test` / `npm run e2e` / `test lint` |
| `pwa` | `npx ionic build --prod` |
| `android` / `ios` | `npx ionic cap run android|ios --prod` |
| `ios-live` / `android-live` | `npx ionic cap run <platform> --livereload --external` with a shell `trap` that re-runs `ionic cap sync <platform> --no-build` on exit to scrub the dev URL |
| `clean` | `rm -rf www/ .angular/ node_modules/` |
| `appflow-ship` | requires `appflow` CLI, `jq`, `IONIC_TOKEN`; refuses if HEAD is not on a remote branch; `appflow build web --app-id e8e09c7a --commit <sha> --json` → parse build id → `appflow deploy web --app-id e8e09c7a --build-id <id> --destination Production` |

README adds: bump versions in `android/app/build.gradle` and `ios/App/App.xcodeproj/project.pbxproj`, `make capsync`, archive in Xcode / Android Studio; and a banner note that this codebase is being rewritten for 2027 (contact `infrastructure@python.org`).

### 11.13 CI (`.github/workflows/CI.yml`)
Name "Install Dependencies, Lint, Build and Test"; trigger `on: [pull_request]`; matrix `node_version: [22]` × `os: [windows-latest, macOS-latest]`; steps `actions/checkout@v4`, `actions/setup-node@v4`, `npm ci`, `npm run lint`, `npm run build --prod`; the Test and E2E steps are commented out. Other `.github` files: `CODEOWNERS` (`* @JacobCoffee`), Ionic-template `ISSUE_TEMPLATE.md`, `CONTRIBUTING.md`, `ionic-issue-bot.yml` (all inherited from ionic-conference-app).

---

## 12. Shared logic in this slice

* **Pipes:** none. **Directives:** none of our own (`AutofillDirective` exists app-wide but is not used here).
* **Helpers duplicated per page:** `onScroll(event) → showTitle = event.detail.scrollTop > 100`; `openUrl(url) → window.open(url, '_system', 'location=yes')`; `reloadContent()` (about-pycon, about-psf) with loader text `Fetching latest...` / 10 000 ms / dismiss 100 ms after data.
* **Slug helper:** `getSponsorSlug(name)` = lowercase → whitespace→`-` → strip `[^a-z0-9-]` (same as `TabsPage.goToSponsor`).
* **Constants / enums:** `NotificationCategory` union (6 values, in declaration order `lightning, openSpace, emergency, announcements, scheduleChanges, dailyDigest`; UI order is `lightning, openSpace, announcements, scheduleChanges, dailyDigest, emergency`), `NotificationPrefs`, `PREF_KEY='notification_prefs'`, `DEFAULT_PREFS` (all true), `TOPIC_BY_CATEGORY`, `REMINDERS` (11 rows, §9.2), `TEST_NOTIFICATION_COPY`, `REMINDER_ID_BASE=8000`, test id `8999`, `APP_STORE_URL`, `PLAY_STORE_URL`, `VENUE_LOCATIONS` (`infoDesk` used here), floor-plan asset constants (`floor-plan-{1,2,3}{,-thumb}.jpg`, titles `Concourse Level`, `Upper Level`, `Arena & Exhibit Halls`).
* **Hard-coded dates/times:** conference days May 13–19 2026 (hero), reminder instants in §9.2 (all `-07:00`), `environment.timezone='America/Los_Angeles'`, `utcOffset=-7`.
* **Hard-coded strings that are really "content":** Wi-Fi SSID `PyConUS26` / password `pyconLB2026`; CoC hotline `(562) 662-4082` ↔ `tel:+15626624082`; report email `pycon-us-report@python.org`; hashtags `#PyConUS`, `#PyConUS2026`; venue "Long Beach Convention & Entertainment Center".
* **Analytics vocabulary:** events `toggle_notification{category,enabled}`, `toggle_all_notifications{enabled}`, `notification_received{topic,banner_shown}`; user properties `notif_<category>` = `on|off`.
* **Toast vocabulary:** `Password copied!` (1500, success), `Notifications enabled` / `Notifications disabled` (1500), `All notifications enabled` / `All notifications muted` (1500), `FCM token copied` (1500, success), `Could not copy — long-press the token to select.` (2500), `Open Settings → PyCon US to manage notification permission.` (2500), foreground push toast `${title}: ${body}` (top, persistent, close button), feed failure `Unable to load schedule, no offline cache available` (3000, top). Loader texts: `Fetching latest...` (10 s), `Installing the latest build...` (60 s).
* **Global window events** (`user:login`, `user:logout`) are *not* listened to by any page in this slice; only About PyCon reads login state once in `ngOnInit`. The notification token stream is an RxJS `BehaviorSubject`.

## 13. Every external URL / scheme opened from this slice

| Opened by | Mechanism | Target |
|---|---|---|
| CoC button, Help row | `window.open(…,'_system')` | `https://policies.python.org/us.pycon.org/code-of-conduct/` |
| CoC row | same | `https://policies.python.org/us.pycon.org/code-of-conduct/Procedures-for-Reporting-Incidents/` |
| CoC row, Help row | same | `tel:+15626624082` |
| CoC row, Help row | same | `mailto:pycon-us-report@python.org` |
| Help rows | same | `https://github.com/PyCon/pycon-us-mobile/issues/new`, `https://github.com/PyCon/pycon-site-public/issues/new` |
| About PSF | same | `https://psfmember.org`, `https://psfmember.org/civicrm/contribute/transact/?reset=1&id=2` (×2), `https://www.python.org/psf/volunteer/`, `https://www.python.org/psf/sponsors/`, `https://www.python.org/psf/grants/`, `https://www.python.org/psf/community-partners/`, `https://us.pycon.org/2026/volunteer/volunteering/`, `https://www.python.org/psf/workgroups/`, `https://www.python.org`, `https://pypi.org`, `https://docs.python.org`, `https://pyfound.blogspot.com`, `https://fosstodon.org/@ThePSF`, `https://x.com/ThePSF`, `https://www.linkedin.com/company/thepsf/` |
| About PSF feed HTML | raw `<a href>` inside `innerHtml` | `https://www.python.org/psf-landing/`, `/psf/mission/`, `/psf/sponsorship/`, `/psf/donations/`, `/psf/membership/`, `http://pyfound.blogspot.com/` |
| Social | `window.open` | `https://fosstodon.org/@pycon`, `https://bsky.app/profile/pycon.us`, `https://x.com/pycon`, `https://www.youtube.com/@PyConUS`, `https://www.linkedin.com/company/thepsf/`, `https://fosstodon.org/@ThePSF`, `https://bsky.app/profile/python.org`, `https://x.com/ThePSF`, `https://pycon.blogspot.com`, `https://pyfound.blogspot.com`, `https://blog.python.org`, `https://blog.pypi.org` |
| Notifications banner | `<a target="_blank" rel="noopener">` | `https://apps.apple.com/us/app/pycon-us-2023/id6446810296` or `https://play.google.com/store/apps/details?id=org.pycon.us` |
| Notifications iOS button | `window.open('app-settings:','_system')` | iOS Settings → PyCon US |
| Data | `HttpClient.get` | `${baseUrl}/2026/schedule/conference.json` |
| Wi-Fi sponsor logo | `<img src>` | `wifiSponsor.logo_url` (S3 URL from feed) |

`@capacitor/inappbrowser` is **not** used in this slice.

## 14. Assets referenced

| Asset | Size | Used by |
|---|---|---|
| `assets/img/pypi-logo.png` | 100×88 | About PSF (Python Resources › PyPI), Social (Blogs › PyPI Blog), rendered 24×24 contain |
| `assets/img/icon-bluesky.svg` | 24×24, `fill=currentColor` | Social (×2), tinted `#0085ff` |
| `assets/img/icon-x.svg` | 24×24, `fill=currentColor` | Social (×2), tinted `--ion-text-color` |
| `assets/img/floor-plans/floor-plan-1-thumb.jpg` | 800×618 | Help › LocationMap thumbnail |
| `assets/img/floor-plans/floor-plan-1.jpg` | 2200×1700 | Help › FloorPlanModal |
| (other floor plans `floor-plan-{2,3,4}{,-thumb}.jpg`, `campus-map*.jpg`, `job-fair*.jpg`) | — | other slices via `VENUE_LOCATIONS` / conference-map |
| `assets/img/splash.png` | 5559×6984 | PWA app shell in `index.html` |
| `assets/img/appicon.png` | 300×249 | favicon + apple-touch-icon |
| `assets/icons/icon-{48,72,96,128,192,256,512}.webp` | — | PWA manifest |
| `assets/img/pycon-us-2026-logo.svg`, `python-logo.png`, `speaker-*.png`, `person-circle-outline.png`, `pycon-us-2025-floorplan.png`, `pycon-us-2026-floorplan-nologo.jpg` | — | other slices (listed for completeness) |
| Ionicons used here | — | `information-circle`, `code-slash-outline`, `share-outline`, `logo-python`, `cash-outline`, `server-outline`, `people-outline`, `person-add-outline`, `heart-outline`, `heart`, `hand-left-outline`, `business-outline`, `document-text-outline`, `globe-outline`, `star-outline`, `git-network-outline`, `book-outline`, `newspaper-outline`, `logo-twitter`, `logo-linkedin`, `shield-checkmark`, `shield-checkmark-outline`, `call`, `call-outline`, `mail`, `mail-outline`, `help-circle-outline`, `wifi`, `copy-outline`, `location-outline`, `share-social`, `pricetag-outline`, `logo-mastodon`, `logo-youtube`, `calendar-outline`, `help-buoy`, `map-outline`, `bug-outline`, `expand-outline`, `close-outline`, `notifications-outline`, `cloud-download-outline`, `open-outline`, `information-circle-outline`, `settings-outline`, `chevron-forward`, `close` |
| Native | | `resources/icon.png` 2048², `resources/splash.png` 2048², iOS `Splash.imageset` 2732² (+dark), `AppIcon-512@2x.png` 1024², Android `mipmap-*/ic_launcher*`, `drawable*/splash.png`, `ic_launcher-playstore.png` 512² |

## 15. Gotchas / non-obvious behaviour (things a port would silently get wrong)

1. **Header colour is not the theme primary.** All seven pages paint the toolbar `#3B3EA9` with white controls and no bottom border, and the hero continues that colour into a `#3B3EA9 → #101136` gradient; the Ionic primary (`#3880ff`) is only used for list icons/buttons. Hero icons are gold `#FFD779` everywhere except Social (`#25C8EB`).
2. **Title fade-in on scroll** (>100 px) — the toolbar title is *invisible* at rest.
3. **Cards overlap the hero** via negative top margins (−16/−20/−24 px) with elevated shadows; the notifications list is itself the "card".
4. **Feed HTML is rendered raw** (`innerHtml`) on About PyCon (`content.about`) and About PSF (`content['about-psf']`, which repeats the mission paragraph and contains a `<ul>` of links). CoC fetches content but never shows it; Wi-Fi/Social ignore `content.wifi` / `content['social-media']` and hard-code the same values. Decide a single source of truth.
5. **Blocking loader on every visit** to About PyCon / About PSF (`Fetching latest...`), even when served from cache; auto-dismisses after 10 s if the feed never answers.
6. **`shareDebug` dumps the whole KV store** (including the user's API `secret`) AES-encrypted with that secret (crypto-js passphrase mode = OpenSSL `Salted__` format, base64), wrapped in `{email,key,state}` JSON, written to the cache directory as `pycon-db-dump-<key>.dat` and handed to the native share sheet with title `Share Debug Records with PyCon Staff`. Only visible when logged in. Staff tooling presumably decrypts this exact format.
7. **Developer Info rows depend on native APIs**; on web they show blank / `base`. `Live Update Build` and `Channel` only appear when an Appflow snapshot is active — concepts that disappear in a compiled port.
8. **Wi-Fi sponsor is found by substring `'temporal'`** across all sponsor levels (first match), and the link slug is derived from the sponsor *name*, not an id. Password is duplicated in template and code.
9. **Clipboard** uses `navigator.clipboard` (secure-context requirement); success is assumed on Wi-Fi (no catch) but handled on the token copy.
10. **Notification prefs default to ALL ON** and are merged over defaults when loaded, so a newly added category is on for existing users. Stored as one object under `notification_prefs` in the Ionic Storage DB named `__pycon_us_mobile_2026`.
11. **Master toggle semantics:** checked only when all six are on; mixed → shown off with "Mixed — toggle to set them all at once."; toggling it sets all six to the new value (so from mixed it turns everything *on*). Per-row toggles also persist + reschedule + emit analytics individually.
12. **`applyPrefs` is idempotent and heavy:** every call re-asserts four topic subscriptions, snapshots six user properties, cancels ids 8000–8010 and reschedules only future reminders whose category is on. It runs on cold start (+5 s), after every toggle, and after the master toggle. `announcements` governs *both* the FCM topic and the five local keynote reminders; `lightning`/`openSpace` are local-only; `emergency`/`scheduleChanges`/`dailyDigest` are push-only.
13. **Permission state machine:** `denied` → silently do nothing (no prompt); `prompt` → ask. Push permission (`FirebaseMessaging.requestPermissions`) is requested separately 5 s after launch regardless of prefs. The "Open PyCon US Settings" button exists only on iOS hybrid (`app-settings:` scheme).
14. **Foreground push banner** is a top toast with no timeout and a close button, suppressed only when all four push categories are off; every received push logs `notification_received` with `topic` from the message `data.topic` (server-side) or `'unknown'`.
15. **`tokenReceived` is subscribed twice** (service + AppComponent); the Diagnostics card is hidden until a token arrives and never appears on web.
16. **"Update required" banner** exists because web bundles can be hot-swapped onto older binaries; detection is `Capacitor.isPluginAvailable(...)`. It greys out and disables the toggles (`pointer-events:none`). A compiled port has no such state but should keep the store URLs.
17. **App identity is split:** iOS bundle `org.pycon.us.2023.onsite` vs Android `org.pycon.us`; both at version `26.2.1` (Android `versionCode 26022`, iOS build `1`); Capacitor `appId` equals the iOS one. Keep these to stay on the existing store listings (App Store id `6446810296`, Play id `org.pycon.us`).
18. **Platform floors are deliberately high:** Android `minSdk 34` (Android 14+) and iOS `18.0`; the comment says this is a conscious support decision.
19. **Push stack:** single plugin `@capacitor-firebase/messaging` (the older `@capacitor/push-notifications` was removed because the two conflict); Firebase project `pycon-us-2023-mobile` (sender `328295262241`); topics `emergency`, `announcements`, `schedule-changes`, `daily-digest`; APNs entitlement committed as `development`; Android FCM small icon = launcher drawable, no channel/colour; iOS `IS_ANALYTICS_ENABLED=false` in the plist while JS still logs analytics, and the Analytics pod is force-linked by a patch-package patch — verify what analytics actually records on iOS.
20. **No deep links of any kind.** `webcredentials:us.pycon.org` and the Android `asset_statements` are for shared credentials/autofill; no `applinks:`, no `VIEW` intent-filter, no `CFBundleURLTypes`. `.well-known/funding-manifest-urls` is unrelated to app linking.
21. **`capacitor.config.ts` as committed is syntactically invalid** (missing commas); the effective synced JSON is git-ignored. Treat the values as intent and confirm with the maintainers.
22. **Splash/brand colour is purple `#680579`** (Capacitor SplashScreen `backgroundColor`, iOS launch storyboard background, PWA shell) while `manifest.json`/`theme-color` are Ionic-blue `#387ef5` and page headers are indigo `#3B3EA9`. Splash is hidden manually after the first feed load (or error), not on a timer; no spinner.
23. **Root `config.xml` is dead Cordova config** (wrong id/name, missing network-security file, references cordova-res paths); `ionic.config.json` still advertises the cordova integration.
24. **PWA caching:** the Angular SW caches shell + assets only; the conference feed is cached by the app in Ionic Storage. Firebase Hosting config (`.firebaserc` project `ionic-ng-conf-app`, stale HTTP/2 push header) is template debris.
25. **Dead code to not port:** `HelpPage.openInfoDesk()`, `AboutPyconPage.checkForUpdate()`, `.update-btn` CSS, CoC `content` fetch, `img.social-icon:not(.pypi)` invert rule, unused `LiveUpdateService` injections in About PSF / CoC / Wi-Fi / Social, `AppIcon 1.appiconset`, `drawable/ic_launcher_background.xml`.
26. **Chevron convention:** `https://` rows show the trailing chevron (`detail="true"`), `tel:`/`mailto:` rows do not; "danger"-coloured icons mark call/mail/report actions; "medium" marks bug-report rows.
27. **Bottom clearance:** 80 px spacer at the end of every page except Notifications (tab bar + rotating sponsor banner from `tabs-page`).
28. **Accessibility details present:** `aria-label` on the two SVG social icons (`Bluesky`, `X`), on the LocationMap button (`Show Information Desk on the Concourse Level floor plan`), on the modal close button (`Close floor plan`); `aria-hidden` on decorative banner icons; `ion-text-wrap` on every multi-line label; `alt` text on sponsor logo (`<name> logo`) and floor plans; `user-select:all` on the FCM token.
29. **All reminder instants are fixed-offset `-07:00` (PDT)**; the app otherwise treats `America/Los_Angeles` as the conference zone. Reminders in the past are skipped at scheduling time, so a rebuild after the conference schedules nothing.

## 16. Complexity summary

| Page / unit | Route | Complexity | Reason |
|---|---|---|---|
| About PyCon US | `/app/tabs/about-pycon` | 2 | HTML blob + Developer Info rows from native app info + encrypted debug-dump share |
| About the PSF | `/app/tabs/about-psf` | 2 | Long static link lists + one HTML blob + loader |
| Code of Conduct | `/app/tabs/coc` | 1 | Static |
| Wi-Fi | `/app/tabs/wifi` | 2 | Clipboard + toast + sponsor lookup from feed |
| Social Media | `/app/tabs/social-media` | 1 | Static lists, two custom SVG icons |
| Help & Safety | `/app/tabs/help` | 3 | Floor-plan thumbnail with %-positioned pulsing pin + pinch-zoom full-screen modal |
| Notification Settings | `/app/tabs/notifications` | 3 | Master/mixed toggle semantics, platform-gated banner/button, token stream, toasts |
| `NotificationsService` | — | 5 | Local notifications with exact times, FCM topics, Analytics user properties, permission state machine, storage merge |
| `LiveUpdateService` + banners | — | 4 (or 1 if OTA is dropped) | Appflow OTA has no native-app equivalent; only version display remains |
| Native/project config | — | 3 | Many identifiers/permissions to carry over; Firebase/APNs wiring; splash/icon assets; high OS floors |
