# PyCon US mobile (Ionic 8 / Angular 17 / Capacitor 7) — inventory of the **Staff tools & auth** slice

Source checkout: `excluded/pycon-us-mobile`, single squashed commit `2aa6df8` ("fix: Sprints link for correct url (#315)", 2026-05-18). There is no older history to consult.

Files read completely for this report:

| Area | Files |
|---|---|
| Providers | `src/app/providers/pycon-api.ts` (438 lines), `src/app/providers/user-data.ts` (332), `src/app/providers/live-update.service.ts`, `src/app/providers/check-tutorial.service.ts` |
| Auth | `src/app/pages/login/{login.ts,login.html,login.scss,login.module.ts,login-routing.module.ts}`, `src/app/pages/account/{account.ts,account.html,account.scss,account.module.ts,account-routing.module.ts}`, `src/app/autofill.directive.ts`, `src/app/interfaces/user-options.ts` |
| Door check | `src/app/pages/door-check/door-check.page.{ts,html,scss}` + modules |
| Swag pickup | `src/app/pages/t-shirt-redemption/t-shirt-redemption.page.{ts,html,scss}` + modules, `src/app/redemption-modal/redemption-modal.component.{ts,html,scss}` |
| CoC incident | `src/app/pages/mask-violation/mask-violation.page.{ts,html,scss}` + modules |
| Lead scanner | `src/app/pages/map/{map.ts,map.html,map.scss,map.module.ts,map-routing.module.ts}`, `src/app/pages/map/map-dark-style.js` (unreferenced), `src/app/lead-note-modal/lead-note-modal.component.{ts,html,css}`, `src/app/pipes/date-ago.pipe.ts` |
| Context | `src/app/app.component.{ts,html,scss}`, `src/app/app.module.ts`, `src/app/app-routing.module.ts`, `src/app/pages/tabs-page/{tabs-page.ts,tabs-page.html,tabs-page.scss}`, `src/environments/*`, `src/theme/variables.scss`, `src/global.scss`, `capacitor.config.ts`, `package.json`/`package-lock.json`, `ios/App/App/Info.plist`, `android/app/src/main/AndroidManifest.xml`, `android/variables.gradle`, `src/app/pages/dev-tools/dev-tools.page.{ts,html}` (only the parts touching this slice) |

> **Discrepancies versus the task brief.** (1) Nothing in this slice uses `@capacitor/filesystem`, `@capacitor/share`, or any CSV/export code; those two plugins are imported only by `session-detail.ts` and `about-pycon.page.ts` (other slices). (2) No page touches the torch/flashlight, zoom, or the single-shot `scan()` API; only `startScan`/`stopScan`/listeners are used. (3) `map-dark-style.js` is a leftover Google-Maps style from the Ionic conference template and is referenced nowhere. (4) `conference.json` is **not** consumed by any page in this slice (`MapPage` injects `ConferenceData` but never calls it). The report below documents what the code actually does.

---

## 0. Cross-cutting facts shared by the whole slice

### 0.1 Environment / constants

| Constant | Value | Where |
|---|---|---|
| `environment.baseUrl` | `https://us.pycon.org` (dev and prod) | `src/environments/environment*.ts` |
| `environment.storageKey` (Ionic Storage DB name) | prod `__pycon_us_mobile_2026`, dev `__pycon_us_mobile_base_2026` | same; used by `IonicStorageModule.forRoot({name})` in `app.module.ts` |
| `environment.production` | prod `true` / dev `false` → drives `isDev` (Simulate Scan button, Dev Tools menu) | |
| `environment.timezone` / `utcOffset` | `America/Los_Angeles` / `-7` (unused in this slice) | |
| Capacitor `appId` / `appName` | `org.pycon.us.2023.onsite` / `PyCon US` | `capacitor.config.ts` |
| Capacitor `server.hostname` | `mobile.us.pycon.org` with `androidScheme: https` (WebView origin for HTTP requests) | |
| iOS `NSCameraUsageDescription` | "Scanning Attendee badge QR codes" | `ios/App/App/Info.plist` |
| Android | `<uses-permission android:name="android.permission.CAMERA" />`; CameraX forced to 1.4.2 for 16 KB page alignment | `AndroidManifest.xml`, `variables.gradle` |
| Barcode plugin | `@capacitor-mlkit/barcode-scanning` **7.5.0** (lockfile) | `package-lock.json` |
| Other plugins used in slice | `@capacitor/network` (lead sync only), `@capacitor/inappbrowser` 2.x (Account → Speaker Discord), `@capacitor/core` (`Capacitor.getPlatform()` in autofill directive), `sha1-uint8array` 0.10.5 (request signing) | |

### 0.2 Storage

`@ionic/storage-angular` 4.x (`Storage` service) — key/value with default drivers (IndexedDB, then localStorage; `Drivers` is imported in `app.module.ts` but never passed, so **no SQLite**). Every provider calls `storage.create()` in its constructor. Values are stored as JS objects (structured clone in IndexedDB — see Gotcha about a `Map` being stored by door-check).

Full key table for this slice:

| Key | Type / shape | Written by | Read by | Removed by |
|---|---|---|---|---|
| `hasLoggedIn` | `true` | `UserData.login` | `isLoggedIn()` (everywhere) | `logout` |
| `nickname`, `email`, `key`, `secret` | strings from `/authenticate/` response | `login` | `getNickname/getEmail` (menu, account, toasts); `key`/`secret` read on **every** signed request | `logout` |
| `hasLeadRetrieval`, `hasDoorCheck`, `hasMaskViolation` | boolean (may be `undefined` if feature missing) | `login`, `fetchFeatures` | AppComponent menu, TabsPage tab bar, CheckTutorial, MapPage staff detection | `logout` |
| `isSpeaker` | boolean | `login` only (not refreshed by `check_features`) | AccountPage | `logout` |
| `hasScannerConsent` | `true` | `MapPage` consent alert ("I Agree") | `MapPage.showConsentDialog` on every `ionViewWillEnter` | `logout`, Dev Tools "Clear Scan Data" |
| `favorite_sessions` | string[] | `fetchPreferences` after login | schedule slice | `logout` |
| `ion_did_tutorial` | boolean | tutorial page | `CheckTutorial.canLoad` | AppComponent `openTutorial` sets false |
| `staff-sponsor-id` | string (sponsor id) | `PyConAPI.setStaffSponsorId` (MapPage sponsor selector) | `syncScan`, `syncNote`, `storeScan`, MapPage | `clearStaffSponsorId` (never called in slice), Dev Tools |
| `staff-sponsor-name`, `staff-sponsor-logo` | string / url or `null` | MapPage sponsor selector | `storeScan`, MapPage banner | Dev Tools (name only; logo key is **not** in the Dev Tools clear list) |
| `pending-scan-<accessCode>` | `{scanData: "<raw QR>", scannedAt: ISO, sponsorId, sponsorName, tries?: n, note?: true}` | `PyConAPI.storeScan` | `syncScan`, `fetchScan`, `storeNote`, MapPage list | `syncScan` on success (→ synced) or after >10 tries (→ failed) |
| `synced-scan-<accessCode>` | `{...captureHttpResponse, ...pendingRecord, note?: true}` — display name at `.data.first_name` | `syncScan`, `simulateScan` | `fetchScan`, `storeScan` (dedupe), MapPage list | Dev Tools only |
| `failed-scan-<accessCode>` | copy of pending record (with `tries` 11) | `syncScan` | MapPage list (status "failed") | Dev Tools only; **never retried** |
| `note-<accessCode>` | `{accessCode, note}` | `storeNote` | `getNote` (note modal prefill) | Dev Tools |
| `pending-note-<accessCode>` | `{accessCode, note}` | `storeNote` | `syncNote`, MapPage 60 s sync loop | `syncNote` on success |
| `pending-door-check-<accessCode>` | `{scanData: {productQuantities: Map<productId, qty>, scannedCode: "<raw QR>"}, scannedAt: ISO}` | DoorCheckPage `storeScan` | DoorCheck `syncScan`, 60 s loop | `syncScan` on success |
| `synced-door-check-<accessCode>` | `{...redeemProductsResponse, ...pendingRecord}` (`redeemable_products_by_category` used for "already" detection) | DoorCheck `syncScan` | DoorCheck `displayLastScan` | never |

`logout()` removes only the first five rows plus `favorite_sessions`, feature flags, `isSpeaker` and `hasScannerConsent`. **All scan / note / sponsor data survives logout and is shared by whoever logs in next on the device.**

### 0.3 Request signing (`PyConAPI.buildRequestAuthHeaders(method, url, body)`)

```
apiKey    = storage.get('key');  secret = storage.get('secret')
timestamp = Math.round(Date.now() / 1000)                   // integer seconds
baseString = secret + timestamp + method + url + body        // plain string concat; null → ''
headers = {
  'X-API-Key':       apiKey,
  'X-API-Signature': sha1_hex(utf8(baseString)),            // sha1-uint8array createHash().update().digest('hex')
  'X-API-Timestamp': String(timestamp),
}
```
* `method` is the upper-case verb (`GET`, `POST`, `PATCH`).
* `url` is the **path including the query string**, starting at `/2026/...` (no scheme/host). Query values are built with `encodeURIComponent` for lead/CoC endpoints but **not** for the check-in `fetch_products` query (raw access code and comma-joined ids).
* `body` is `''` for GET and the exact `JSON.stringify(payload)` string for POST/PATCH; the very same string is sent as the HTTP body with `Content-Type: application/json`. A port must sign the exact bytes it sends (key order matters).
* `/authenticate/` is the only unsigned call.
* All requests use Angular `HttpClient` with an RxJS `timeout(ms)` (see table) and `catchError` that logs `'Unable to fetch mobile state, ' + error` (copy-pasted message) and rethrows. Errors are therefore surfaced as observable errors.

### 0.4 API endpoints used by this slice (base `https://us.pycon.org`)

| # | Method & path | Timeout | Caller | Request | Response fields the UI actually uses |
|---|---|---|---|---|---|
| A1 | `POST /2026/api/v1/authenticate/` | 3000 ms | LoginPage | JSON `{email, password}` (unsigned) | `nickname`, `email`, `key`, `secret`, `features.{lead_retrieval, door_check_in, mask_violation, is_speaker}`; error body `message` |
| A2 | `GET /2026/api/v1/user/check_features/` | 2000 | `UserData.fetchFeatures` (AppComponent init, AccountPage init) | — | `features.lead_retrieval`, `features.door_check_in`, `features.mask_violation` |
| A3 | `GET /2026/api/v1/user/mobile_state/` | 2000 | `UserData.fetchPreferences` (after login, app start, every `updateLoggedInStatus`) | — | `favorites` |
| A4 | `PATCH /2026/api/v1/user/mobile_state/` | 2000 | `patchUserData` (favorites; fire-and-forget) | `{favorites: [...]}` | ignored |
| C1 | `GET /2026/api/v1/check_in/redeemable/` | 2000 | DoorCheck & Swag `ngOnInit` | — | `redeemable_categories: [{id, name}]`, `redeemable_products: [{id, name, category}]` |
| C2 | `GET /2026/api/v1/check_in/attendees_by_product/{productId}/` | 2000 | **defined, never called** | | |
| C3 | `GET /2026/api/v1/check_in/attendees_by_product_with_quantity/{productId}/` | **20000** | DoorCheck `startScan` (one call per product being scanned) | — | array of `{id (= attendee access code), quantity, name?, dietary?, has_allergy?, allergy?}` |
| C4 | `GET /2026/api/v1/check_in/fetch_products/?attendee_access_code=<code>&category_pk_list=<a,b>&mode=redemption_mode` | 10000 | Swag `handleScan` | — | `attendee_access_code`, `attendee_name`, `attendee_id`, `has_items_to_redeem`, `redeemable_products_by_category: {"<Category name>": [{product_id, product_name, redeemable, purchased}]}` |
| C5 | `GET /2026/api/v1/check_in/fetch_products/?attendee_access_code=<code>&product_pk_list=<a,b>&mode=door_check_mode` | 10000 | DoorCheck fallback when badge not in preloaded inventory | — | same as C4 plus `attendee_name`, `dietary`, `has_allergy`, `allergy` |
| C6 | `POST /2026/api/v1/check_in/redeem_products/` | 10000 | DoorCheck `syncScan`, Swag after modal | JSON `{attendee_access_code, badge_validator, scanned_at(ISO), "product-redeem-<id>": <id>, "product-<id>-quantity": <qty>, ...}` | `errors: [{message}]`, `redeemable_products_by_category` (counted / stored) |
| M1 | `GET /2026/api/v1/mask_violations/attendees/` | 15000 | CoC page `loadAttendees` | — | `data: [{access_code, full_name, nickname, badge_name, violations}]` |
| M2 | `GET /2026/api/v1/mask_violations/capture/?attendee_access_code=<enc>` | 5000 | CoC page, badge-scan path (no notes, no force) | — | `data.{nickname, full_name, badge_name, email, violations}` |
| M3 | `POST /2026/api/v1/mask_violations/capture/` | 5000 | CoC page, name-search path | JSON `{attendee_access_code, notes?: string, force?: true}` | same as M2 |
| L1 | `GET /2026/api/v1/lead_retrieval/sponsors/` | 5000 (`toPromise`) | MapPage `showSponsorSelector` (staff only) | — | `sponsors: [{id, name, booth_number?, logo_url?}]` |
| L2 | `GET /2026/api/v1/lead_retrieval/capture/?attendee_access_code=<enc>&badge_validator=<enc>[&sponsor_id=<enc>]` | 2000 | `PyConAPI.syncScan` | — | `data.first_name` (whole response stored) |
| L3 | `POST /2026/api/v1/lead_retrieval/<accessCode>/note/` | 2000 | `PyConAPI.syncNote` | JSON `{accessCode, note, sponsor_id?}` | ignored |
| X1 | `GET /2026/speaker/join_discord/` | n/a | AccountPage via `InAppBrowser.openInWebView` | browser page | |

### 0.5 Global window events / login state propagation

* `UserData.login()` dispatches `window.dispatchEvent(new CustomEvent('user:login'))`; `logout()` dispatches `'user:logout'`.
* Listeners: `AppComponent.listenForLoginEvents` → `updateLoggedInStatus(bool)` (inside a **300 ms `setTimeout`** re-reads nickname + the three feature flags, sets `hasApps`, and calls `fetchPreferences`); `TabsPage.listenForLoginEvents` → re-checks `hasLeadRetrieval`, `hasDoorCheck`, `loggedIn` (each applied inside a **200 ms `setTimeout`**) — **not** `hasMaskViolation` (see Gotchas).
* Feature flags are refreshed from `check_features` on app start (`AppComponent.ngOnInit → fetchFeatures`) and whenever the Account page is opened.

### 0.6 How the staff pages are reached

Routes (all lazy modules, children of `/app/tabs` in `tabs-page-routing.module.ts`): `login`, `account`, `door-check`, `t-shirt-redemption`, `mask-violation`, `lead-retrieval` (→ `MapModule`). `login` and `account` also exist at top level (`/login`, `/account`) in `app-routing.module.ts` but nothing links there.

Entry points:

| Entry | Condition | Target |
|---|---|---|
| Side menu section **"Apps"** (header only when `hasApps`) | `hasMaskViolation` → item "CoC Incident" icon `shield-checkmark-outline`; `hasDoorCheck` → "Door Check" `checkbox-outline` and "Swag Pickup" `shirt-outline`; `hasLeadRetrieval || hasDoorCheck` → "Lead Scanner" `qr-code` | `routerDirection="root"` navigation to the routes above |
| Side menu **"Account"** section | `loggedIn` → "Account" (`person`), "Logout" (`log-out-outline`, danger, calls `AppComponent.logout()` → `userData.logout()` then `/app/tabs/schedule`); `!loggedIn` → "Login" (`log-in`); always "Notifications"; "Hello, {{nickname}}" item when logged in | |
| Bottom tab bar (`tabs-page.html`) | `hasDoorCheck || hasMaskViolation` → tab button "Scanner" (icon `scan`) that **opens a bottom sheet** instead of navigating; `hasLeadRetrieval && !hasDoorCheck && !hasMaskViolation` → direct tab "Scanner" (icon `qr-code`) to `lead-retrieval`; `!loggedIn` → tab "Login" (icon `log-in`) | |
| **Staff Tools sheet** (`ion-modal` `breakpoints=[0, 0.35]`, `initialBreakpoint=0.35`, handle shown, `.staff-tools-sheet` bg = page bg) | header h2 "Staff Tools" (1.1rem/700); list `lines="full"` with chevron items: "Door Check" (`checkbox-outline`, primary) if `hasDoorCheck`; "Swag Pickup" (`shirt-outline`) if `hasDoorCheck`; "Lead Scanner" (`qr-code-outline`) if `hasLeadRetrieval || hasDoorCheck`; "CoC Incident" (`shield-checkmark-outline`) if `hasMaskViolation` | `goToTool(path)` closes sheet and `router.navigateByUrl(path)` |
| App launch (`CheckTutorial.canLoad` on `/` → `/tutorial`) | if `ion_did_tutorial` and `hasLeadRetrieval` → `/app/tabs/lead-retrieval`, else `/app/tabs/schedule` | lead-retrieval users land on the scanner at cold start |
| Account page | no nickname **and** not logged in → `router.navigate(['/app/tabs/login'], {replaceUrl: true})` | |

Active-tab highlighting: `TabsPage.activeTab` is parsed from the URL (`/app/tabs/<name>`); the "Scanner" buttons get class `pycon-active` only when the active route is `lead-retrieval` (door-check etc. do not highlight any tab).

### 0.7 Barcode scanning pattern common to the four scanner pages

Import: `import { BarcodeScanner, BarcodeFormat, LensFacing, ScanResult, StartScanOptions } from '@capacitor-mlkit/barcode-scanning';`

| Call | Options / behaviour |
|---|---|
| `BarcodeScanner.checkPermissions()` | returns `{camera: 'granted' \| 'denied' \| 'prompt' \| 'prompt-with-rationale' \| 'limited'}`. Every page does `if (status) return true;` — the object is **always truthy**, so on native the "permission error" branch is unreachable; the OS prompt is triggered by `startScan` itself. On **web** the plugin throws `unimplemented` → the `try/catch` swallows it and returns `undefined` → the pages show the permission card. |
| `BarcodeScanner.requestPermissions()` | only in CoC page, on the unreachable branch |
| `BarcodeScanner.addListener('barcodesScanned', cb)` | `cb(result)` with `result.barcodes: [{rawValue, format, ...}]`; pages only read `result.barcodes[0].rawValue` |
| `BarcodeScanner.removeAllListeners()` | used to pause between scans |
| `BarcodeScanner.startScan({formats: [BarcodeFormat.QrCode], lensFacing: LensFacing.Back})` | continuous scanning; camera preview is rendered **natively behind the WebView**. The plugin's documented `body.barcode-scanner-active` CSS hook is **not** used; instead each page binds `[style.visibility]="scanning ? 'hidden' : ''"` on `<ion-content>` so the page body disappears and the header toolbar + footer (Stop button, last-scan card) stay visible on top of the camera. |
| `BarcodeScanner.stopScan()` | in every `stopScan`, `ionViewWillLeave`, `ngOnDestroy` |
| Not used | torch, zoom, `scan()` single-shot, `isSupported()`, `isGoogleBarcodeScannerModuleAvailable()` / `installGoogleBarcodeScannerModule()` (Android module presence is never checked) |

QR payload: a badge QR decodes to `"<accessCode>:<validator>"` (colon-separated; possibly more segments). Rules per page: access code is always segment 0; Door Check / Swag use segment **1** as `badge_validator`; Lead Scanner uses the **last** segment; CoC uses only segment 0. Dev simulation writes `"SIM12345:SIMULATED"`.

Platform checks: `this.config.get('mode') === 'ios'` (Ionic *mode*, not Capacitor platform) selects the settings-path text in the permission card; `Capacitor.getPlatform() !== 'ios'` early-returns in the autofill directive; nothing in the slice checks `platform.is('hybrid')`.

### 0.8 Theme tokens that carry meaning in this slice (`src/theme/variables.scss`, light)

`primary #3880ff`, `success #2dd36f` (contrast #fff), `warning #ffc409` (contrast #000), `danger #eb445a`, `medium #92949c`, `light #f4f5f8`, `tertiary #5260ff`. Dark theme variants: primary `#428cff`, success `#2fdf75` (contrast #000), warning `#ffd534`, danger `#ff4961`, medium `#989aa2`, background `#000` (iOS) / `#121212` (MD). Brand colors hard-coded in the slice SCSS: header/banner purple `#3B3EA9`, hero gradient end `#101136`, accent gold `#FFD779`, link/selection violet `#5833E9`, warning banner gradient `#e6a817 → #c48800`. Four theme classes exist on `<ion-app>`: `dark-theme`, `high-contrast-theme` (+ `-light-theme` / `-dark-theme`); high-contrast adds a 1 px border to `ion-card` and removes box shadows.

---

## 1. Login page (`src/app/pages/login/`)

**1. Route / entry.** `/app/tabs/login` (lazy `LoginModule`); also `/login`. Reached from the side-menu "Login" item (when logged out), the tab-bar "Login" tab (when logged out), and the Account page redirect. Selector `page-login`.

**2. Purpose & flows.** Email + password form that exchanges credentials for an API key/secret.
* Tap **Login** (or implicit form submit via Enter — the button is `type="submit"` inside the `<form novalidate>`) → `onLogin(form)`: sets `submitted = true`; if `form.valid` (both fields `required`; that is the only validation — no email-format validator) → `POST /2026/api/v1/authenticate/` with `{email, password}`.
* Success → `userData.login(data)` (not awaited), `nav.navigateRoot('/')`, toast `"Success! Welcome, " + data.nickname + "."` (duration **1000 ms**, position `top`, icon `check`).
* Error → if `error.error?.message` exists → toast `"Invalid Auth: " + message` (1000 ms, top, icon `alert`). **Timeouts (3 s) and network errors produce no UI feedback at all** (only `console.log`).
* Inline validation messages (red `ion-text color="danger"`, class `ion-padding-start`): "Email address is required" when `!email.valid && submitted`, "Password is required" likewise. Hidden until first submit.

**3. Data.** Endpoint A1 (unsigned). `UserData.login(data)` then writes `hasLoggedIn=true` → (not awaited, in parallel) `fetchPreferences()` (A3), `nickname`, `email`, `key`, `secret`, `hasLeadRetrieval`, `hasDoorCheck`, `hasMaskViolation`, `isSpeaker` → dispatches `user:login`. No caching/offline behaviour.

**4. Native plugins.** None directly. (`appAutofill` attribute is present on both inputs but the directive is not in this module's scope — see §3.)

**5. UI structure.**
* `ion-header > ion-toolbar`: start slot `ion-menu-button color="medium"`; `ion-title` "Login". Default (non-gradient) toolbar.
* `ion-content`:
  * `div.login-logo` (padding `20px 0`, `min-height 200px`, centered) → `<img src="assets/img/appicon.png" alt="PyCon US 2026 Logo">` max-width 150 px.
  * `form` → `ion-list`:
    * `ion-item` with floating label "Email address" + `ion-input` (`type=email inputmode=email autocomplete=email spellcheck=false autocapitalize=off required`, `[(ngModel)]="login.email"`).
    * error paragraph (see above).
    * `ion-item` floating label "Password" + `ion-input type=password autocomplete=current-password required`.
    * error paragraph.
  * `ion-row > ion-col > ion-button expand="block" type="submit"` "Login".
  * `ion-card > ion-card-content`: "Log in using the email address and password for your us.pycon.org/2026 account."
* SCSS: only the logo block and `.list {margin-bottom:0}`.

**6. State & lifecycle.** Component fields: `authUrl`, `login = {email:'', password:''}`, `submitted=false`. No lifecycle hooks. Ionic caches the page; fields persist while the page stays in the stack.

**7. Navigation out.** `navigateRoot('/')` → `/tutorial` route guard (`CheckTutorial`) → `/app/tabs/lead-retrieval` if `hasLeadRetrieval` else `/app/tabs/schedule` (if tutorial already done; otherwise the tutorial). Because `login()` is not awaited, the guard may read a stale `hasLeadRetrieval`.

**8. Edge cases / a11y.** `novalidate` disables browser validation UI. `alt` text on logo. Toasts are 1 s (very short). Pressing Login twice fires two POSTs (no in-flight guard). No "show password" toggle, no forgot-password link, no logout-elsewhere.

**9. Complexity: 2** — trivial form, but the port must reproduce the exact credential → key/secret storage handoff and the post-login routing/race semantics.

---

## 2. Account page (`src/app/pages/account/`)

**1. Route / entry.** `/app/tabs/account` (and `/account`). Side menu → "Account" (only when logged in). Selector `page-account`.

**2. Purpose & flows.**
* Shows who is logged in and offers: **Speaker Discord** (only if `isSpeaker`) → `InAppBrowser.openInWebView({url: baseUrl + '/2026/speaker/join_discord/', options: DefaultWebViewOptions})`; **Logout** → `userData.logout()` then `nav.navigateRoot('/')`.
* "Report an Issue" list (always shown, even logged out): "Mobile App Issue" → `window.open('https://github.com/PyCon/pycon-us-mobile/issues/new', '_system', 'location=yes')`; "Website Issue" → `https://github.com/PyCon/pycon-site-public/issues/new` (same call → system browser).
* Scroll behaviour: `ion-content scrollEvents="true" (ionScroll)` → `showTitle = scrollTop > 100`; the toolbar title fades in (opacity transition 0.25 s) only after scrolling past the hero.

**3. Data.** `ngOnInit` → `this.app.fetchFeatures()` (the **`AppComponent` instance is injected** into the page) → `UserData.fetchFeatures()` (A2) refreshing the three flags and `AppComponent.updateLoggedInStatus`. `ngAfterViewInit` → `getEmail()`, `getNickname()` (if no nickname and `!isLoggedIn()` → redirect to login), `checkIsSpeaker()`, `isLoggedIn()` → `loggedIn`. Storage reads: `email`, `nickname`, `isSpeaker`, `hasLoggedIn`.

**4. Native plugins.** `@capacitor/inappbrowser` (`InAppBrowser.openInWebView`, `DefaultWebViewOptions`). `window.open(..., '_system')` → Capacitor opens the system browser on native; a new tab on web.

**5. UI structure.**
* Header `class="ion-no-border"`, background gradient `#3B3EA9` (flat), toolbar transparent with white text & white menu button; title "Account" (opacity 0 → 1 via `.title-visible`).
* `div.account-hero` (`*ngIf="loggedIn"`): column, centered, padding `16px 24px 32px`, gradient `180deg #3B3EA9 23.5% → #101136 53.29%`, white text. `ion-icon name="person-circle"` 64 px color `#FFD779`; `h1` = `nickname || email || 'Account'` (1.5 rem, 700); `p > code` email (0.85 rem, opacity .7) when both nickname and email exist.
* `div.account-actions` (`*ngIf="loggedIn"`, column, gap 8, padding `16px 20px`): `ion-button expand=block color=tertiary` with `logo-discord` icon "Speaker Discord" (`*ngIf="isSpeaker"`); `ion-button expand=block fill=outline color=danger` with `log-out-outline` "Logout".
* `ion-list lines="full"`: `ion-list-header` "Report an Issue"; two `ion-item button detail=true` rows with start icon (`phone-portrait-outline` / `globe-outline`, color primary), `h2` title + `p` subtitle ("Report a bug or suggest a feature for the app" / "Report an issue with us.pycon.org").
* 80 px spacer div at the bottom.
* Logged-out state: hero and actions absent; only the header + issue list (and the page immediately redirects to login if nickname missing).

**6. State & lifecycle.** As above; `@ViewChild(IonContent)` unused. No subscriptions.

**7. Navigation out.** Logout → `/` (→ tutorial guard → schedule). Redirect to `/app/tabs/login` with `replaceUrl`.

**8. Edge cases.** `logout()` is not awaited before navigating. Logout keeps scan/sponsor data (see §0.2). Nothing prevents tapping Speaker Discord offline.

**9. Complexity: 1** — static page; only the in-app browser and the hero/scroll-title effect are non-trivial.

---

## 3. `AutofillDirective` (`src/app/autofill.directive.ts`)

* Selector `[appAutofill]`; injects `ElementRef`, `NgControl`. **Declared only in `AppModule`** and not exported; `LoginModule` (where the attribute is used) does not import it, so the attribute is inert in the current build — effectively dead code. Its *intent* matters for the port:
* On iOS only (`Capacitor.getPlatform() === 'ios'`), after a 300 ms `setTimeout`, get the native `<input>` from the `ion-input` shadow DOM (`getInputElement()` or `querySelector('input')`), and on `change` **and** `input` events push `nativeInput.value` into the Angular control (`setValue`, `markAsDirty`). Reason: iOS Keychain/password autofill fills the native input and fires `change` without `input`, so `ngModel` stays empty and the form reports "required" even though fields look filled.
* Port note: read the real field values at submit time (or bind to on-change) so OS autofill is not lost.

---

## 4. Door Check (`src/app/pages/door-check/`)

**1. Route / entry.** `/app/tabs/door-check` (lazy `DoorCheckPageModule`, selector `app-door-check`). Side menu "Door Check" (`hasDoorCheck`), Staff Tools sheet "Door Check".

**2. Purpose & flows.** Door staff pick a session (product) and scan badges to admit attendees, with a live headcount and dietary/allergy hints.

Flow in order:
1. Page loads categories/products (C1), keeping only categories whose name does **not** match `/shirt|swag/i`, and products belonging to those categories.
2. **Category chips** (`ion-chip`, outline unless selected, color `primary` when selected else `medium`, `checkmark-outline` icon when selected). Tap → `selectCategory(id)`: tapping the selected chip again **clears** everything (category, product list, product, search, count); tapping another sets `category`, resets `check_in_count` and `counted_codes`, and calls `refreshProducts()`.
3. `refreshProducts()` → products of the category sorted **chronologically** by `productSortKey(name)` (regex `^(?:\w{3,9}\s+)?(Jan|Feb|…|Dec)\s+(\d{1,2})\s+(\d{1,2}):(\d{2})\s+(AM|PM)\b`, case-insensitive → `Date.UTC(2026, month, day, hour24, minute)`; non-matching names sort last via `Number.MAX_SAFE_INTEGER`, ties by `localeCompare`). Example product name: `"Wed May 13 9:00 AM - All about decorators"`. Search is cleared, `product = null`.
4. **Search bar** (`ion-searchbar`, placeholder "Search sessions...", `debounce=150`, shown once a category is chosen) → `filterProductList()` case-insensitive substring on `name`.
5. **Product list** (`ion-list lines=full`): first row "**All sessions in this category**" (value `'all'`), then one row per filtered product (`ion-label.ion-text-wrap`). Selected row gets `color="primary"` and a trailing `checkmark` icon. `selectProduct(id)` resets count/set when the product changes.
6. **"Scanning for" card** (when `category && product`): kicker "Scanning for"; primary line `getProductName(product) || 'All sessions'`; secondary line = category name (only when a single product is selected); pill "`{{check_in_count}} checked in`" with `people-outline` (primary bg, shown when count > 0). Hint "Select a session to start scanning." when a category but no product is selected; hint "Tap a category to choose a session." when no category.
7. **Start Scanner** (footer button; disabled while `!scanning && product === null`):
   * `scanningProducts` = all displayed product ids if `'all'`, else `[product]`.
   * Resets `product_attendees`, `inventory`, `dietary`; for each product id fires C3 (20 s timeout) and merges results: `product_attendees[code] += quantity`, `inventory[code][productId] += quantity`, `dietary[code] = {name, dietary, has_allergy, allergy}` (sticky merge; only when the row has a non-empty `dietary`, `has_allergy`, or a `name`). These requests are **not awaited** before scanning starts.
   * `checkPermission()` → if falsy, show permission card and stop. Else `show_permissions_error=false`, `scanning=true` (content hidden), add listener, `startScan` (QR, back lens).
8. **On each scan** (`handleScan`): remove listeners; if `result.barcodes` and `!ignore_scans` (never true on this page) → clear the 5 s last-scan timer, `updateLastScan(rawValue)`, and re-add the listener after **250 ms** (so a badge held in view re-fires every ~250 ms).
9. `updateLastScan(raw)`: `accessCode = raw.split(':')[0]`. For each scanning product, if `inventory[code][product] > 0` → `access=true`, `quantity += qty`, `productQuantities[product] = qty`.
   * If `access` → `displayLastScan(...)`.
   * Else → fallback C5 (`product_pk_list`, `mode=door_check_mode`): if `has_items_to_redeem` → `access=true`, `quantity` = Σ `redeemable` over every category, `productQuantities[product_id] = redeemable`; cache `dietary[code]` from `attendee_name/dietary/has_allergy/allergy`; then `displayLastScan`. On HTTP error → `displayLastScan` with `access=false` (shows "Entry not permitted").
10. `displayLastScan(code, access, quantity, productQuantities, raw)`:
    * `alreadySynced = counted_codes.has(code)`; if not, read `synced-door-check-<code>` and set `alreadySynced` if any of the products currently being scanned appears in that record's `redeemable_products_by_category[*][].product_id`.
    * If `access && quantity > 0` → `storeScan(...)` (below).
    * If additionally `!alreadySynced` → `check_in_count++`, add code to `counted_codes`.
    * `last_scan = {status: quantity, code, already: access && alreadySynced, count: check_in_count, name, dietary, has_allergy, allergy}` (`name` is **never rendered**); `detectChanges()`; auto-clear after **5000 ms**.
11. `storeScan(code, access, productQuantities, raw)`: no-op if `last_scan?.code == code` (same badge within the 5 s window); if `pending-door-check-<code>` exists → `syncScan(code)`; else write `{scanData: {productQuantities (a `Map`), scannedCode: raw}, scannedAt: ISO}` then `syncScan(code)`.
12. `syncScan(code)`: builds C6 payload `{attendee_access_code: raw.split(':')[0], badge_validator: raw.split(':')[1], scanned_at: pending.scannedAt, 'product-redeem-<id>': id, 'product-<id>-quantity': qty}` → POST; success → write `synced-door-check-<code> = {...response, ...pending}` and delete pending; failure → `console.warn` and leave pending for the **60 s retry loop** (`syncAllPending` iterates `storage.forEach` for keys starting `pending-door-check-`, reschedules itself with `setTimeout(..., 60000)` forever; started in `ngOnInit`, never cancelled).
13. **Stop Scanner** → `last_scan=null`, remove listeners, `stopScan()`, `scanning=false`. Also on `ionViewWillLeave` and `ngOnDestroy`.

**3. Data summary.** Endpoints C1, C3 (per product), C5 (fallback), C6. Storage: `pending-door-check-*`, `synced-door-check-*`. Offline: admission decisions use the preloaded inventory, so scans of known badges work offline and are queued; unknown badges fall to C5, which fails offline → "Entry not permitted". Polling: 60 s sync loop. Timeouts: 20 s (C3), 10 s (C5/C6), 2 s (C1).

**4. Native plugins.** `@capacitor-mlkit/barcode-scanning` as in §0.7. `Config.get('mode')` for iOS/Android settings text. Web: permission card (see §0.7).

**5. UI structure.**
* Header: default toolbar, `ion-menu-button color="medium"`, title "Door Check".
* Content (`visibility:hidden` while scanning):
  * Permission card (`ion-card color="warning" .permission-card` margin 16): title "Camera permission required"; paragraphs "Looks like you didn't grant the app permission to access your camera." / "Re-enable it under:" / `<code>` `Settings › Privacy & Security › Camera › PyCon US 2026` (iOS) or `Settings › Apps › PyCon US 2026 › Permissions › Camera` (Android).
  * `section.category-section` (padding `16px 16px 0`): `h2.section-title` "Category" (0.75 rem, 700, uppercase, letter-spacing .06em, medium color); hint; `div.category-chips` flex-wrap gap 8, chips height 40 px / 0.95 rem.
  * `div.search-row` (padding `4px 8px 0`) with searchbar.
  * `ion-list.product-list` (transparent bg, flat; scrolls with page).
  * `ion-card.scanning-for-card` (margin 16) with `.kicker-stack` column gap 4: `.kicker` 0.7 rem/700 uppercase medium; `.primary` 1.2 rem/700 text color; `.secondary` 0.85 rem medium; `.check-in-count` pill (margin-top 8, padding `4px 10px`, radius 12, primary bg/contrast, 0.9 rem/600, icon 16 px).
  * `p.empty-hint.ion-text-center` (medium, margin `12px 16px`).
* Footer (`ion-footer`):
  * `ion-card.last-scan-card` (margin `8px 16px 0`) `*ngIf="last_scan"`, color `danger` if `!last_scan.status` (quantity 0), `warning` if `already`, else `success`. Row (flex, gap 12): icon 28 px `alert-circle-outline` / `time-outline` / `checkmark-circle-outline`; text column: `<strong>` "Checked in" / "Already checked in" / "Entry not permitted"; `<code>` access code (0.75 rem, opacity .85); `.last-scan-dietary` chips (`restaurant-outline` + `dietary | titlecase` on translucent white; `warning-outline` + "Allergy" or "Allergy: <allergy>" on warning bg/black text); right `.last-scan-count` pill (`people-outline` + count, bg `rgba(0,0,0,.22)`, 1.05 rem/700, `aria-label="Total checked in for this session"`) when `count > 0`.
  * `ion-toolbar.footer-toolbar` (padding 8/16) → `ion-button expand=block size=large .scan-toggle-button` (height 56, 700): color `danger` + `stop-circle-outline` "Stop Scanner" while scanning; `success` + `qr-code-outline` "Start Scanner" otherwise; disabled when `!scanning && product === null`.

**6. State & lifecycle.** `ngOnInit`: `ios`, `syncAllPending()`, C1. `ionViewWillLeave`/`ngOnDestroy`: `stopScan()`. Manual `detectorRef.detectChanges()` after every mutation (plugin callbacks run outside Angular zone). Timers: `last_scan_timeout` (5 s), listener re-attach (250 ms), 60 s sync loop; `scan_timeout` is cleared but never set. Unused fields: `scan_presentation`, `dirty`, `mode = "door_check"`, `ScanResult`, `platform`.

**7. Navigation out.** None (menu button only).

**8. Edge cases / errors / a11y.** All decorative icons `aria-hidden="true"`. C1 failure → page shows "Category" header with no chips and no error message. C3 failures are silent (badge falls back to C5 per scan). `syncScan` with a missing pending record logs then throws (`pending.scanData` on `null`). `storage.forEach` callbacks are async and not awaited. Entry decisions are optimistic: the attendee is admitted before the POST succeeds. `already` only compares product overlap (an attendee checked into a different session earlier is **not** flagged). `last_scan.status` is the numeric quantity used as a boolean.

**9. Complexity: 5** — continuous camera scanning overlay, bulk inventory preload with merged maps, two-tier admission logic with per-product "already" detection, offline queue with 60 s retry, headcount dedupe, chronological product sort, dietary chips.

---

## 5. Swag Pickup (`src/app/pages/t-shirt-redemption/`) + Redemption modal (`src/app/redemption-modal/`)

**1. Route / entry.** `/app/tabs/t-shirt-redemption` (lazy `TShirtRedemptionPageModule`, selector `app-t-shirt-redemption`, page title "Swag Pickup"). Side menu "Swag Pickup" (`hasDoorCheck`), Staff Tools sheet. `RedemptionModalComponent` is declared in `AppModule` and presented via `ModalController` from this page only.

**2. Purpose & flows.** Staff pick one or more swag categories, scan a badge, see what the attendee can still pick up, tick items, and redeem them.
1. C1 on init, keeping only categories whose name matches `/shirt|swag/i` (inverse of Door Check) and their products.
2. **Category chips** are multi-select (`toggleCategory(id)`; `category: number[] | null`; becomes `null` when emptied). Hint "Tap one or more categories below." while none selected. Card "Redeeming for" lists selected category names joined by `', '`.
3. **Start Scanner** (disabled until ≥1 category): permission check, `scanning=true`, `addListeners()` (which first `removeAllListeners()` to avoid double wiring), `startScan` QR/back.
4. **On scan** (`handleScan`): ignore if no barcodes, `ignore_scans`, or `processing_scan`; set `processing_scan=true` synchronously (hard lock); remove listeners; capture `rawValue` and `scannedAt = new Date().toISOString()`; call C4 with `rawValue.split(':')[0]`, `this.category`, `mode="redemption_mode"`; `setTimeout(clearError, 1000)` is scheduled immediately (see Gotchas).
   * Success with a body → `openRedemptionModal(data, rawValue, scannedAt)`; empty body → unlock & resume.
   * Error → `scanError=true` (footer card "Invalid QR code", danger), unlock, resume listeners if still scanning.
5. **Redemption modal** (`ignore_scans=true` while open):
   * Props: `accessCode`, `attendeeName`, `attendeeId`, `hasItemsToRedeem`, `redeemableProductsByCategory`.
   * Checkbox per product (`disabled` when `redeemable === 0`); `checkProduct` stores `toRedeem[productId] = redeemable` (always the **full** remaining quantity — no quantity picker) or deletes it; `canRedeem = keys > 0`.
   * **Cancel** → dismiss `{}` role `cancel`. **Redeem now** → latches `submitting=true` (label becomes "Redeeming…"), dismiss `{accessCode, toRedeem}` role `save`; if dismiss throws, un-latch.
6. After dismiss (`onWillDismiss`): `ignore_scans=false`.
   * `save` with empty `toRedeem` → toast "No items selected — nothing to redeem." (warning, 3 s), unlock, resume.
   * `save` with items → payload `{attendee_access_code: data.accessCode, badge_validator: rawValue.split(':')[1] ?? '', scanned_at: scannedAt ?? now, 'product-redeem-<id>': id, 'product-<id>-quantity': qty}` → C6.
     * Response: `errors.length > 0` → toast `"Partial redemption: " + messages.join('; ')` (fallback "Some items could not be redeemed.") warning **5 s**; else `redeemedCount` = Σ array lengths in `redeemable_products_by_category` → `"Redeemed N item(s)."` success 3 s; else "Nothing was redeemed. Items may already be picked up." warning 3 s.
     * HTTP error / thrown → toast "Redemption failed — check WiFi and try again." danger 5 s.
     * In all cases: `processing_scan=false` and re-add listeners if still scanning.
   * `cancel` → unlock, resume.
7. **Stop Scanner** → clear, remove listeners, `stopScan()`, `scanning=false` (also `ionViewWillLeave`, `ngOnDestroy`).

**3. Data.** Endpoints C1, C4, C6. **No local queue** — redemption requires connectivity; failures are only toasted. No storage keys written. Toasts all `position: 'top'` with `color` set.

**4. Native plugins.** Barcode scanning as §0.7; `ToastController`, `ModalController`.

**5. UI structure.**
* Header: default toolbar, menu button `color=medium`, title "Swag Pickup".
* Content (hidden while scanning): permission card identical to Door Check; `section.category-section` ("Category" title, hint, chips with checkmark when selected); `ion-card.redeeming-card` with kicker "Redeeming for" + primary text (same `.kicker-stack` styles as Door Check).
* Footer: `ion-card.last-scan-card color=danger` `*ngIf="scanError"` → row with `alert-circle-outline` (28 px) and `<strong>` "Invalid QR code"; `ion-toolbar.footer-toolbar` with the same 56 px toggle button (disabled when `!scanning && !hasSelectedCategories()`).
* **Modal** (`RedemptionModalComponent`): header `ion-no-border`, title "Redeem Products"; content `ion-padding`: `ion-card.attendee-card` (subtitle "Redeeming for", title `attendeeName`, body "No items to redeem." or "Select the items you're handing the attendee, then tap **Redeem now**."); `div.redeem-list` (column gap 16) → for each `category of redeemableProductsByCategory | keyvalue` (**alphabetical by category name**): `h2.category-title` (1.1 rem/600) + `ion-list lines=full` of `ion-item` (disabled when `redeemable===0`) containing `ion-checkbox slot=start labelPlacement=end justify=start` whose label is `<strong>{{redeemable}}x</strong> {{product_name}}` and, when `redeemable !== purchased`, a sub-line `{{purchased - redeemable}} already redeemed` (0.8 rem, opacity .6). Footer `ion-no-border` toolbar → `ion-grid.footer-grid` row: col size 5 "Cancel" (`color=medium fill=outline size=large`, disabled while submitting), col size 7 "Redeem now"/"Redeeming…" (`color=primary size=large`, disabled unless `canRedeem && !submitting`).

**6. State & lifecycle.** `ngOnInit`: `ios`, C1. Locks: `processing_scan`, `ignore_scans`, modal `submitting`. Dead code: `updateLastScan`/`last_scan`/`product_attendees` (would throw if ever called), `scan_presentation`, `dirty`, `storage` injection, `LiveUpdateService` import.

**7. Navigation out.** None.

**8. Edge cases.** The "Invalid QR code" card is cleared by a timer started at scan time, so it is visible for < 1 s or, if the request fails after 1 s, stays until the next scan. Categories map order in the modal is alphabetical regardless of API order. Only whole quantities can be redeemed. No dedupe of the same badge scanned twice (the server decides via `errors` / already-redeemed). All icons `aria-hidden`.

**9. Complexity: 4** (page) / **2** (modal) — scanner overlay plus a modal-driven transactional flow with a reentrancy lock and five toast outcomes.

---

## 6. CoC Incident (`src/app/pages/mask-violation/`)

**1. Route / entry.** `/app/tabs/mask-violation` (lazy `MaskViolationPageModule`, selector `app-mask-violation`, title "CoC Incident"; the "mask violation" name is legacy). Side menu "CoC Incident" (`hasMaskViolation`), Staff Tools sheet.

**2. Purpose & flows.** Record a Code-of-Conduct incident against an attendee either by scanning their badge or by name search with notes.
* **Badge path:** Start Scanner → permission → `scanning=true` → `addListener` (**no** removal of earlier listeners, and `handleScan` never removes/pauses the listener) → `startScan`. Every `barcodesScanned` event with barcodes → `clearTimeout(last_scan_timeout)` → `updateLastScan(raw.split(':')[0])` → **M2 GET** (no notes, no force). Holding a badge in view therefore fires repeated capture requests (server-side dedupe assumed; see open questions).
* **Name-search path:** `ion-searchbar` (placeholder "Search attendee by name", debounce 150) → `onSearchInput` trims the value → `applyFilter()`: empty query → no list; otherwise split on whitespace, keep attendees where **every** term is a substring of `full_name + ' ' + nickname + ' ' + badge_name` (lower-cased), **max 25 rows**. Tap a row (`selectAttendee`, ignored while `capturing` or without `access_code`) → `AlertController` dialog:
  * header "Record CoC Incident", subHeader = `full_name || nickname || badge_name || 'this attendee'`; message lines: `Badge: <badge_name>` (only if it differs from the display name), `Existing incidents: <violations ?? 0>`, blank line, "Add any context (location, what happened, witnesses). This is saved on the incident record."; `backdropDismiss: false`; `cssClass: 'coc-confirm-alert'` (message `white-space: pre-line; text-align: left`).
  * one input `{name:'notes', type:'textarea', placeholder:'Notes (optional)', attributes:{rows:4, maxlength:2000, autocapitalize:'sentences'}}`.
  * buttons: "Cancel" (role cancel) and "Record Incident" (role confirm) → `updateLastScan(access_code, {notes: trimmed, force: true})` → **M3 POST** with `{attendee_access_code, notes (if non-empty), force: true}`.
* **Force semantics (client side):** `force` is sent **only** from the name-search path and is always `true` there; the scan path never sends it. The provider switches to POST whenever `notes` or `force` is present so that free text never lands in URL/access logs; the raw-scan path stays a GET with the access code in the query string. What the server does with `force` (presumably bypass a duplicate/recent-capture guard) is not visible in the app.
* **Result card** (footer, `*ngIf="violationData"`): after the response, `violationData.data` drives: color `danger` if `violations > 2`, `warning` if `> 1`, else `success`; icon `alert-circle-outline` if `> 1` else `checkmark-circle-outline`; `<strong>` `nickname || full_name`; "Badge: <badge_name>"; email; "`<violations>` incident(s) on record". Auto-cleared **5 s after the request was sent** (timer starts before the response). In-memory directory row's `violations` is updated from the response and the filter re-applied.
* **Stop Scanner** → clear card, remove listeners, `stopScan()`.

**3. Data.** M1 on `ngOnInit` (15 s timeout; sorted by `(full_name || nickname || badge_name).toLowerCase()` with `localeCompare`), M2/M3 per capture (5 s). No storage, no offline queue, no retry (a "Retry" button reloads the directory).

**4. Native plugins.** Barcode scanning (§0.7) — this page also calls `requestPermissions()` (unreachable branch). `AlertController`.

**5. UI structure.**
* Header: default toolbar, menu button medium, title "CoC Incident".
* Content (hidden while scanning): permission card (same copy as Door Check); `section.intro-section` (`*ngIf="!violationData && !searchQuery"`, padding `24px 20px 12px`): title "Capture an Incident", hint 1 "Tap **Start Scanner**, point the camera at the attendee's badge QR code, and the app will record a CoC incident against their record. Their full name, badge name, email, and running incident count appear here after each scan.", hint 2 "Can't scan a badge? Search by name below and tap the attendee to record an incident the same way."
* `section.search-section` (padding `0 8px`): searchbar (`--background` light, radius 12); status rows: spinner `dots` + "Loading attendee directory…" while loading; `warning-outline` + "Couldn't load attendee list." + clear small "Retry" button on error (color warning-shade); results `ion-list.attendee-list lines=full` only when `searchQuery && !loading && !error`: empty row italic `No attendees match "<query>"`; rows: `h3` display name (600), `p` "Badge: <badge_name>" when it differs, `p` `"<nickname>"` when it differs from full name; trailing `ion-badge` color `danger` (>2) / `warning` (>0) / `medium` with text `<n> incident(s)`; rows disabled while `capturing`.
* Footer: `ion-card.last-scan-card` (margin `16px 16px 0`, radius 14, content padding `14px 16px`) with row (icon 2 rem, text column: strong 1.05 rem/700, badge/email 0.85 rem opacity .85, `.violation-count` with bold 1.15 rem/800 number); `ion-toolbar.footer-toolbar` (padding `8px 12px 12px`, page bg) with toggle button (radius 14) — **never disabled**.

**6. State & lifecycle.** `ngOnInit`: `ios`, `loadAttendees()`. `ionViewWillLeave`/`ngOnDestroy`: `stopScan()`. Flags: `scanning`, `capturing`, `attendeesLoading`, `attendeesError`. Unused: `scan_presentation`, `dirty`, `ignore_scans` (never set true), `storage`, `scan_timeout`, `.mycomponent-wider-popover` CSS.

**7. Navigation out.** None.

**8. Edge cases / errors.** Capture errors only reset `capturing` (no toast — nothing visible happens). The 5 s auto-clear can hide a slow response before it renders. The directory is loaded once per page instantiation (can be stale; counts updated locally after captures). Name search is client-side over the full attendee list (size unknown; held in memory). `aria-hidden` on icons; the alert's textarea has `maxlength 2000`.

**9. Complexity: 3** — scanner overlay plus a searchable directory and an alert-with-textarea confirmation; the per-frame capture behaviour must be deliberately reproduced or debounced.

---

## 7. Lead Scanner (`src/app/pages/map/`, class `MapPage`) + Lead Note modal (`src/app/lead-note-modal/`)

**1. Route / entry.** `/app/tabs/lead-retrieval` → `MapModule` (selector `page-map`, title "Lead Scanner"). Side menu "Lead Scanner" (`hasLeadRetrieval || hasDoorCheck`), tab bar "Scanner" (direct for pure lead-retrieval users; via Staff Tools sheet otherwise), cold-start redirect from `CheckTutorial` for `hasLeadRetrieval` users. `LeadNoteModalComponent` is declared in `AppModule` and opened only from here. `DateAgoPipe` is declared in `MapModule`.

**2. Purpose & flows.** Sponsors (and staff scanning on a sponsor's behalf) scan attendee badges to capture leads; scans are queued locally, synced to the server, listed with status, and annotated with structured notes.

* **Consent gate** (`ionViewWillEnter`, every time the page becomes active): `hasConsent=false` → `showConsentDialog()`: if `hasScannerConsent === true` in storage → ok; else alert header "Lead Scanner Consent", message "By using the lead scanner, you confirm that you will only scan badges of attendees who have given you explicit verbal permission. Scanning without consent violates the PyCon US Code of Conduct.", `backdropDismiss:false`, buttons "Cancel" (role cancel → `hasConsent=false`) and "I Agree" (→ `hasConsent=true`, `setScannerConsent(true)`). After dismiss, if not consented → `nav.navigateRoot('/app/tabs/schedule')` and the rest of `ionViewWillEnter` is skipped. `startScan()` and `simulateScan()` re-run the same check.
* **Staff mode detection** (after consent): `isStaffScanner = !hasLeadRetrieval && hasDoorCheck`. If staff: load `staff-sponsor-id/name/logo`; if id+name present → `selectedSponsor = {id, name (quotes stripped), logo_url}`; else → `showSponsorSelector()`.
* **Sponsor selector** (`showSponsorSelector`): L1 → `sponsorList`; on error alert "Unable to load sponsors" / "Could not fetch the sponsor list. Check your network connection or try again later." [OK]; if empty alert "No sponsors available" / "No sponsors with lead retrieval are configured yet." [OK]; else alert header "Scan on behalf of", message "Select which sponsor you are scanning for:", **radio** inputs (label `name` + ` (Booth <booth_number>)` when present, value `String(id)`), `backdropDismiss:false`, **single button "Select"** (no cancel) → `setStaffSponsorId(id)`, store `staff-sponsor-name`, `staff-sponsor-logo`, refresh list.
* **Sponsor banner** (staff only): selected → purple bar with logo (36 px, white rounded) or `business` icon, name + "Tap to change", chevron; tapping the main area reopens the selector; right-hand **filter toggle** (`funnel` / `funnel-outline`, gold `#FFD779` when active) sets `filterBySponsor` → list filtered to scans whose `sponsor_name` equals the selected sponsor's name. No sponsor → amber warning bar "No sponsor selected" / "Tap to select a sponsor" (`alert-circle`), and Start Scanner is **disabled**.
* **Scan list** (`refresh_presentation`): iterates **every** storage key; builds rows from `pending-scan-*` (status `pending`), `synced-scan-*` (`captured`, `first_name = value.data.first_name`), `failed-scan-*` (`failed`); each row `{status, scanned_at, access_code (= scanData.split(':')[0]), note, sponsor_name (surrounding quotes stripped), sponsor_id, first_name?}`. `sortScans()` (called from the template) applies the sponsor filter, sorts by `scanned_at` **descending**, and keeps the **50 most recent**.
* **Pull-to-refresh** (`ion-refresher`): re-sync all `pending-scan-*` via `pycon.syncScan`, then after 500 ms refresh the list and complete.
* **Start Scanner**: consent → permission → `content_visibility='hidden'`, hide Start, show Stop → `setupListeners()` → `startScan({formats:[QrCode], lensFacing: Back})`.
* **On scan** (`handleScan`): take `barcodes[0]`; `removeAllListeners()`; if `!ignore_scans`: clear last-scan timer; `updateLastScan(code, 0)`; `pycon.storeScan(code, rawValue)`; re-add listener after **500 ms**.
  * `PyConAPI.storeScan(code, raw)`: if `synced-scan-<code>` exists → log "Already captured", no-op (**no UI feedback**); if pending exists → `syncScan(code)`; else write pending `{scanData: raw, scannedAt: ISO, sponsorId: staff-sponsor-id, sponsorName: staff-sponsor-name}` and `syncScan(code)`.
  * `PyConAPI.syncScan(code)`: if `Network.getStatus().connected` is false → skip ("Skipping until network resumes"); validator = **last** `:` segment; L2 GET (2 s timeout) with `sponsor_id` when set; success → `synced-scan-<code> = {...response, ...pending}`, delete pending; error → `pending.tries++`; if `tries > 10` → move to `failed-scan-<code>`, else rewrite pending. (A `null` pending record logs then throws.)
  * `updateLastScan(code, n)`: polls `fetchScan(code)` (synced record preferred, else pending) every **100 ms up to 30 times (~3 s)**; shows `last_scan = {status: data.first_name ? 'captured' : 'pending', scanned_at, access_code, first_name, note}`; once captured (or after 30 polls) schedules `clearLastScan` after 5 s.
* **Last-scan bar** (footer): icon `checkmark-circle` (success) when captured else `ellipsis-horizontal-circle` (medium); name or access code + `dots` spinner while pending; small clear button with `document-text`/`document-outline` opening the note modal for that scan.
* **Notes** (`openNoteModal(accessCode, scan)`): `ignore_scans=true`; prefill from `note-<code>`; present `LeadNoteModalComponent`; on role `save` with a non-empty note → `pycon.storeNote(code, note)` → writes `note-<code>` and `pending-note-<code>`, triggers `syncNote` (L3 POST `{accessCode, note, sponsor_id?}`, 2 s timeout, deletes pending-note on success, no retry cap — retried by the 60 s loop), and sets `note: true` on the synced/pending scan record; then refresh. Saving an **empty** note is ignored (a note cannot be deleted from the app).
* **Background sync loop**: `ngOnInit` schedules `syncAllPending` after 60 s; it re-syncs all `pending-scan-*` and `pending-note-*` and reschedules itself every 60 s forever (never cancelled).
* **Stop Scanner** → `last_scan=null`, remove listeners, `stopScan()`, refresh list, swap buttons, show content. Also `ionViewWillLeave`, `ngOnDestroy`.
* **Simulate Scan** (dev builds only): consent check, then writes a fake `synced-scan-SIM<0-99999>` record with `scanData 'SIMnnnnn:SIMULATED'`, random name from a fixed list of 16 Python community names, current sponsor, `data: {first_name, captured: true, captured_date}`; refreshes.

**3. Data.** Endpoints L1, L2, L3. Storage keys: all `*-scan-*`, `note-*`, `pending-note-*`, `staff-sponsor-*`, `hasScannerConsent`, feature flags. Offline: scans always queue locally; sync skipped while offline; 10-try cap → failed; notes retried indefinitely. Polling: 100 ms status poll (≤30), 60 s sync loop. `@capacitor/network` used only inside `syncScan`.

**4. Native plugins.** Barcode scanning (§0.7), `@capacitor/network`, `AlertController`, `ModalController`. Web: permission card shown (danger color here).

**5. UI structure.**
* Header `ion-no-border`, flat `#3B3EA9` background, transparent toolbar, white title "Lead Scanner" and white menu button.
* Content (`[style.visibility]="content_visibility"`): refresher; sponsor banner(s) (`.sponsor-banner` bg `#3B3EA9`, white; `.sponsor-banner-main` padding `12px 8px 12px 16px` gap 12; `.sponsor-banner-filter` padding `12px 14px`, left border `rgba(255,255,255,.15)`, icon 20 px opacity .5 → 1/gold when active; `.sponsor-banner-warning` gradient `135deg #e6a817 → #c48800`); permission card `color="danger"` radius 12 with `h3` "Camera Permission Required" and `<code>Settings > Privacy > Camera > PyCon US</code>` / `<code>Settings > Apps > PyCon US > Camera</code>`; **empty state** (padding `64px 32px`, `scan-outline` 56 px step-300, `h3` "No scans yet", `p` 'Tap "Start Scanner" to begin scanning badges'); **list** `ion-list.scan-list lines=full`: `ion-item.scan-item button detail=false` (`--padding-start 12px`): start slot `div.scan-status-dot` 10 px circle (success/warning/danger/medium by status); `ion-label`: `h2.scan-name` (1 rem/600) = `first_name` if captured else access code; staff only: `p.scan-sponsor` (`business-outline` + sponsor name, 0.7 rem, `#5833E9`); `p.scan-time` (0.75 rem medium) = `scanned_at | dateAgo` plus uppercase mini badge "PENDING" (warning tint) or "FAILED" (danger tint); end icon `document-text` (primary) if note else `document-outline` (medium), 18 px.
* Footer: `.last-scan-bar` (flex space-between, padding `8px 16px`, bg step-50, top border step-100) as described; `.scanner-actions` (column, padding `4px 16px 8px`): dev-only "Simulate Scan" (`flask-outline`, clear, small, medium); **Start Scanner** (`color=success size=large`, `scan-outline`, radius 14, 700) and **Stop Scanner** (`color=danger`, `stop-circle-outline`) — both rendered, toggled with `visibility` (the hidden one still reserves its space).

**6. State & lifecycle.** `ngOnInit`: `removeAllListeners()`, `ios`, 60 s sync timer. `ionViewWillEnter`: consent → list → staff detection. `ionViewWillLeave`/`ngOnDestroy`: `stopScan()`. `sortScans()` is evaluated several times per change-detection pass (template calls it 3×). Unused injections: `ConferenceData`, `LiveUpdateService`, `Platform`. `toggleSponsorFilter()` only calls `detectChanges()`.

**7. Navigation out.** Consent declined → `/app/tabs/schedule`. Otherwise none.

**8. Edge cases.** Rows beyond 50 are invisible but still synced. Duplicate scan of an already-synced badge is silently ignored. Failed scans have no retry UI. Sponsor selector cannot be dismissed without choosing. `storeScan` stores `sponsorName` from storage even if the user is not staff (null). The quote-stripping regex `/^"|"$/g` suggests the API may return JSON-quoted names. Access code appears in list rows for pending scans (PII-light). No a11y attributes beyond Ionic defaults.

**9. Complexity: 5** — consent gate on every entry, staff/sponsor sub-flow with three alerts, local queue with status machine (pending → captured/failed), 100 ms status polling, 60 s background sync, pull-to-refresh, note modal with structured text format, dev simulation.

### 7a. Lead Note modal (`LeadNoteModalComponent`)

* Inputs: `scan` (row object: uses `status`, `first_name`, `access_code`, `sponsor_name`) and `note` (existing composed string or `null`).
* Header `ion-no-border`: start button "Cancel" (medium) → dismiss `{note: null}` role `cancel`; title "Lead Notes"; end button **Save** (bold, primary) → dismiss `{note: composed}` role `save`.
* Content `ion-padding`:
  * `.scan-header` centered: icon 32 px `checkmark-circle` (success) if captured else `ellipsis-horizontal-circle` (medium); `h2` (1.3 rem/700) = first name if captured else access code; `p.scan-header-sponsor` sponsor name (0.8 rem, `#5833E9`).
  * Field "INTEREST LEVEL" (label 0.7 rem/600 uppercase medium): three equal `button.interest-btn` (padding `12px 8px`, 2 px border step-200, radius 12): "🔥 Hot" (selected: `#ef4444` border/text, 8 % tint bg), "☀️ Warm" (`#f59e0b`), "❄️ Cold" (`#3b82f6`); tapping the selected one deselects.
  * Field "FOLLOW-UP": wrap of `button.followup-chip` (padding `8px 14px`, 1.5 px border, radius 20; selected `#5833E9` border/text, 8 % tint, 600): "📧 Send info", "🎯 Demo", "📰 Newsletter", "💼 Hiring", "🤝 Partner" (multi-toggle).
  * Field "NOTES": `ion-textarea` placeholder "Additional notes...", `maxlength 4000`, `counter`, `autoGrow`, `rows 3`, bg step-50, radius 12, 1.5 px border step-150.
* **Note text format** (`composeNote`): lines joined by `\n`, each optional: `Interest: hot|warm|cold`, `Follow-up: Send info, Demo, ...` (labels joined by `', '`), `Notes: <free text trimmed>`. `parseNote` regexes: `/Interest: (hot|warm|cold)/i`, `/Follow-up: (.+)/i` (split on `', '`, matched case-insensitively against labels), `/Notes: ([\s\S]*)$/` (multi-line); a note matching none of them is treated as legacy free text.
* Complexity: **2**.

---

## 8. Shared logic in this slice

| Item | Definition | Used by |
|---|---|---|
| `DateAgoPipe` (`dateAgo`) | `null` → "a long time ago"; `< 10 s` → "just now"; `< 60 s` → "a moment ago"; otherwise divides by `[60, 60, 24, 30, 12]` → `"<n> second|minute|hour|day|month|year(s) ago"` | Lead Scanner list |
| Angular `titlecase` pipe | capitalises each word of `dietary` | Door Check dietary chip |
| Angular `keyvalue` pipe | iterates an object **sorted by key** | Redemption modal categories |
| `productSortKey(name)` | chronological sort of tutorial names (regex in §4) | Door Check |
| Category discriminator | `/shirt|swag/i` on category name: Door Check keeps non-matching, Swag keeps matching | both check-in pages |
| Sponsor name sanitiser | `String(v).replace(/^"|"$/g, '')` | Lead Scanner |
| Mode strings | `"door_check_mode"`, `"redemption_mode"` (query `mode=`) | C4/C5 |
| Redeem payload keys | `product-redeem-<id>`, `product-<id>-quantity`, `badge_validator`, `scanned_at`, `attendee_access_code` | C6 |
| Feature flag names | API: `lead_retrieval`, `door_check_in`, `mask_violation`, `is_speaker`; storage: `hasLeadRetrieval`, `hasDoorCheck`, `hasMaskViolation`, `isSpeaker` | everywhere |
| `UserOptions` | `{email: string; password: string}` | Login |
| Timers | last-scan auto-clear 5000 ms (all scanners); listener re-attach 250 ms (door) / 500 ms (lead); status poll 100 ms × 30 (lead); sync loops 60 000 ms (door, lead); toast 1000 ms (login), 3000/5000 ms (swag); `AppComponent` 300 ms and `TabsPage` 200 ms flag refresh delays; autofill 300 ms | |
| HTTP timeouts | 2 s (auth-related, lead capture/note, redeemable list), 3 s (authenticate), 5 s (CoC capture, sponsors), 10 s (fetch_products, redeem), 15 s (CoC directory), 20 s (attendees_by_product_with_quantity) | |
| Hard-coded URLs | `https://github.com/PyCon/pycon-us-mobile/issues/new`, `https://github.com/PyCon/pycon-site-public/issues/new`, `/2026/speaker/join_discord/` | Account |
| Fake names list | 16 names (Guido van Rossum … Savannah Ostrowski) | dev `simulateScan` |
| Year | `2026` hard-coded in every API path and in `Date.UTC(2026, …)` | |

## 9. Assets referenced

* `assets/img/appicon.png` — login logo (alt "PyCon US 2026 Logo", max-width 150 px). Present in `src/assets/img/`.
* Sponsor `logo_url` (remote, from L1) — staff banner.
* Ionicons used: `alert`, `check` (toast icons), `person-circle`, `logo-discord`, `log-out-outline`, `phone-portrait-outline`, `globe-outline`, `checkmark-outline`, `checkmark`, `people-outline`, `restaurant-outline`, `warning-outline`, `alert-circle-outline`, `time-outline`, `checkmark-circle-outline`, `stop-circle-outline`, `qr-code-outline`, `qr-code`, `scan-outline`, `scan`, `business`, `business-outline`, `chevron-forward-outline`, `funnel`, `funnel-outline`, `alert-circle`, `document-text`, `document-outline`, `checkmark-circle`, `ellipsis-horizontal-circle`, `flask-outline`, `shield-checkmark-outline`, `checkbox-outline`, `shirt-outline`, `person`, `log-in`. Spinner `dots`.
* Emoji in note modal: 🔥 ☀️ ❄️ 📧 🎯 📰 💼 🤝.
* `map-dark-style.js` — unused.

## 10. Gotchas / non-obvious behaviour a port would silently get wrong

1. **Signature scheme**: SHA-1 (not HMAC) over `secret + unixSeconds + METHOD + pathWithQuery + exactBodyString`; the body string must be byte-identical to what is sent; GET body is empty string; path starts at `/2026/`.
2. **Permission check is a no-op on native**: `checkPermissions()` returns an object, so `if (status)` is always true; the OS prompt comes from `startScan`. On web the same code shows the permission card. Deciding when to show "Camera permission required" must be redone deliberately.
3. **Camera overlay model**: preview behind the UI with only `ion-content` hidden; header (with a working hamburger menu) and footer remain tappable over the camera.
4. **Continuous scanning cadence** differs per page: Door Check re-arms after 250 ms (and relies on `last_scan.code` + `counted_codes` to dedupe a held badge), Lead after 500 ms (dedupes via storage records), Swag pauses until the modal flow finishes, **CoC never pauses** (fires a capture per detected frame).
5. **QR validator segment**: Door/Swag take `split(':')[1]`, Lead takes the last segment — must match the server's `badge_validator` expectation.
6. **Logout does not clear scan, note, sponsor data**; a new user on the same device sees the previous sponsor's leads. Dev Tools "Clear Scan Data" removes `pending/synced/failed-scan-*`, `pending-note-*`, `note-*`, `staff-sponsor-id`, `staff-sponsor-name`, `hasScannerConsent` (but not `staff-sponsor-logo` or door-check keys).
7. **Consent must be re-asked on every entry** of the Lead Scanner until accepted (and after logout, since the flag is cleared); declining navigates away.
8. **Door-check pending record stores a JS `Map`** (survives IndexedDB structured clone; would break under a JSON/localStorage backend because `for (const [k,v] of obj)` throws). A port should store plain dicts.
9. **Redemption modal category order is alphabetical** (keyvalue pipe), not API order; quantities redeem all-or-nothing per product.
10. **`is_speaker` is only captured at login**, never refreshed by `check_features`; the other three flags are.
11. **Tab bar misses mask-violation refresh** on `user:login`; a user whose only feature is `mask_violation` sees the "Scanner" tab only after the tabs page is re-created. The side menu updates after 300 ms.
12. **Post-login routing race**: `login()` is not awaited, so the tutorial guard may send a lead-retrieval user to the schedule the first time; likewise the first `fetchPreferences` can run before `key`/`secret` are stored (fails silently).
13. **Login gives no feedback on timeout/network failure** (only when the server returns a `message`).
14. **Door-check "already checked in"** means "already redeemed one of the products currently being scanned" (per session), not "already scanned today"; and admission is granted optimistically before the POST completes; there is no cap on retries, so a POST that succeeded server-side but failed to respond is re-sent every 60 s (possible duplicate rows unless the server is idempotent).
15. **Lead sync has a 2 s timeout and a 10-try cap** → `failed` after ~10 minutes of flaky network, with no in-app retry; notes retry forever.
16. **60 s sync loops are never cancelled** on page destroy (both Door Check and Lead Scanner) → multiple loops after repeated navigation; a port should own one background sync task.
17. **Headcount reset rules**: `check_in_count` resets on category change, product change, and clearing the category — but **not** on Stop/Start Scanner (contrary to the code comment).
18. Door-check `last_scan.name` (attendee name) is computed but **not shown**; only the access code is displayed.
19. Swag "Invalid QR code" visibility is governed by a timer started at scan time (see §5.8).
20. Lead list shows at most **50** rows; `refresh_presentation` reads every storage key (O(total keys)).
21. Sponsor selector has **no cancel**; `backdropDismiss:false` on consent, sponsor, and CoC alerts.
22. Success toast in login uses `data.nickname`; the hero on Account falls back `nickname || email || 'Account'`.
23. `appAutofill` directive is dead in the current build but documents a real iOS autofill pitfall.
24. Door Check content hidden ⇒ the running count is only visible via the footer card while scanning; the "Scanning for" card is hidden.
25. Both Door Check and Swag Pickup filter the **same** `/check_in/redeemable/` response by category-name regex; a category named e.g. "Swag Bag" is swag, "T-Shirt" is swag, everything else is a session.
26. Dark/high-contrast themes: all cards/badges use Ionic color tokens except the hard-coded purples/gold listed in §0.8 and the note-modal interest colours; the Lead/Account headers stay purple in every theme.

## 11. Complexity summary

| Page / component | Route | Complexity | Native plugins |
|---|---|---|---|
| Login | `/app/tabs/login` | 2 | — (HTTP only) |
| Account | `/app/tabs/account` | 1 | `@capacitor/inappbrowser` |
| AutofillDirective | n/a | 1 | `@capacitor/core` (platform check) |
| Door Check | `/app/tabs/door-check` | 5 | `@capacitor-mlkit/barcode-scanning` |
| Swag Pickup | `/app/tabs/t-shirt-redemption` | 4 | `@capacitor-mlkit/barcode-scanning` |
| Redemption modal | (modal from Swag Pickup) | 2 | — |
| CoC Incident | `/app/tabs/mask-violation` | 3 | `@capacitor-mlkit/barcode-scanning` |
| Lead Scanner (`MapPage`) | `/app/tabs/lead-retrieval` | 5 | `@capacitor-mlkit/barcode-scanning`, `@capacitor/network` |
| Lead Note modal | (modal from Lead Scanner) | 2 | — |
| Providers (`PyConAPI`, `UserData` parts) | — | 3 | `@capacitor/network`, `sha1-uint8array` |

## 12. Open questions (not answerable from the client code)

1. Exact server semantics of `force` on `/mask_violations/capture/` and whether the GET scan path is de-duplicated server-side (the page sends one request per detected frame).
2. Full response schemas (only the fields listed in §0.4 are consumed); HTTP status codes used for auth failure vs. invalid badge; whether `/authenticate/` returns anything beyond nickname/email/key/secret/features.
3. Whether `redeem_products` is idempotent for a repeated door-check payload (affects the 60 s retry design) and whether `lead_retrieval/capture` is idempotent.
4. Whether the Android Google Barcode Scanner module (unbundled ML Kit) is guaranteed present on target devices — never checked by the app.
5. Whether a web/PWA build is a supported target for the staff tools (the camera plugin is unimplemented on web; the app ships a service worker).
6. The CSV export / share feature mentioned in the task brief does not exist in this checkout; confirm whether it is a planned feature or belonged to an older release.
7. Whether sponsor names really arrive JSON-quoted (the quote-stripping regex suggests a past bug).
