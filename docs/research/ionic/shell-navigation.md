# PyCon US Mobile (Ionic 8 / Angular 17 / Capacitor 7) — Inventory: App Shell, Navigation & Theming

Source checkout: `/Users/ndonkohenri/PycharmProjects/flet-dev/others/pycon-us/excluded/pycon-us-mobile`
Upstream: `https://github.com/PyCon/pycon-us-mobile` (single squashed commit `2aa6df8 fix: Sprints link for correct url (#315)`).
README note from the maintainers: "This will be the last year this codebase exists as is. We are losing support of critical features needed from Ionic so we will be rewriting it for 2027."

This document is a *description of what exists*, not a Flet design. Where something looks hard to port it is flagged as such; no Flet solutions are proposed.

## 0. Files in this slice (all read in full)

| File | Role |
|---|---|
| `src/index.html` | HTML host; pre-bootstrap purple "app shell" splash |
| `src/main.ts`, `src/polyfills.ts`, `src/zone-flags.ts` | Angular bootstrap, zone.js |
| `src/manifest.json` | PWA manifest |
| `src/app/app.module.ts` | Root module: Ionic, Ionic Storage (DB name = `environment.storageKey`), ServiceWorker (prod only), declares `AutofillDirective`, `LeadNoteModalComponent`, `RedemptionModalComponent` |
| `src/app/app-routing.module.ts` | Root routes (`''`→`/tutorial`, `account`, `login`, `app`, `tutorial` w/ `canLoad: CheckTutorial`) |
| `src/app/app.component.{ts,html,scss}` | `<ion-app>` root: theme classes, skip link, global live-update banner, split-pane + side menu, router outlet, push-toast wiring |
| `src/app/app.scss` | one rule: `*[hidden] { display:none !important }` (imported by global.scss) |
| `src/app/autofill.directive.ts` | iOS-only autofill helper for `ion-input` (declared in AppModule) |
| `src/app/pages/tabs-page/*` | `<ion-tabs>` host: bottom tab bar, rotating sponsor banner, staff-tools bottom sheet, child routes for every `/app/tabs/<x>` page |
| `src/app/pages/tutorial/*` | One-screen "Welcome" page |
| `src/app/providers/check-tutorial.service.ts` | `canLoad` guard that redirects returning users |
| `src/app/providers/live-update.service.ts` | Appflow Live Updates (OTA) check/apply + banner state |
| `src/app/pages/dev-tools/*` | Developer-only diagnostics page |
| `src/theme/variables.scss`, `src/global.scss` | Four colour themes, track badge palette, global a11y rules |
| `capacitor.config.ts`, `ios/App/App/Info.plist`, `ios/.../LaunchScreen.storyboard`, `android/.../AndroidManifest.xml`, `styles.xml`, `strings.xml`, `ngsw-config.json`, `firebase.json` | Native/PWA shell config consulted for splash / launch behaviour |

Providers consulted (only the parts the shell calls): `user-data.ts` (fully read), `conference-data.ts` (`load()`, `getSponsors()`, `invalidateCache()`, `presentMessage()`), `notifications.service.ts` (`getPrefs`, `applyPrefs`, `shouldShowPushBanner`, `scheduleCategoryTestNotification`, `NotificationCategory`), `pycon-api.ts` (endpoint list).

---

## 1. Launch / bootstrap sequence (what the user sees from tap-to-first-screen)

### 1.1 Native splash (hybrid only)
* **Capacitor SplashScreen plugin config** (`capacitor.config.ts`): `launchAutoHide: false`, `backgroundColor: '#680579'`, `showSpinner: false`. The splash therefore stays up until JS calls `SplashScreen.hide()`.
* **iOS**: `UILaunchStoryboardName = LaunchScreen`; storyboard shows image asset `Splash` (`scaleAspectFill`, pinned to all four edges) over background `rgb(0.4078, 0.0196, 0.4706)` = `#680578`. `Assets.xcassets/Splash.imageset` contains 1x/2x/3x `Default@Nx~universal~anyany.png` and dark-appearance `-dark` variants plus `splash-2732x2732*.png`. `Info.plist`: display name "PyCon US", orientations Portrait + LandscapeLeft/Right (iPad adds upside-down), `UIViewControllerBasedStatusBarAppearance = true`, camera + calendar usage strings.
* **Android**: `MainActivity` theme `AppTheme.NoActionBarLaunch` (parent `Theme.SplashScreen`, `android:background=@drawable/splash`), with port/land + night drawables for every density. `launchMode="singleTask"`, `configChanges` includes `uiMode`, app label "PyCon US", `custom_url_scheme = org.pycon.us`, App Links `asset_statements` → `https://us.pycon.org/.well-known/assetlinks.json`. Firebase default notification icon = `@drawable/ic_launcher`. AD_ID permission explicitly stripped.
* `capacitor.config.ts` `appId: 'org.pycon.us.2023.onsite'`, `appName: 'PyCon US'`, `server.hostname: 'mobile.us.pycon.org'`, `androidScheme: 'https'`, `ios.scheme: 'PyCon US'`.

### 1.2 Web shell before Angular boots (`index.html`)
Inside `<app-root>` (replaced when Angular renders):
* full-viewport flex column, `background-color:#680579`
* `<img src="assets/img/splash.png" alt="PyCon US 2026">` at `max-width:60%; max-height:40%`
* a 32×32 CSS spinner (3px border `rgba(255,255,255,.3)`, top `#fff`, `spin 0.8s linear infinite`), `margin-top:2rem`.
* `<head>`: `<title>PyCon US 2026</title>`, viewport `viewport-fit=cover, width=device-width, initial-scale=1, min/max-scale=1, user-scalable=no`, `format-detection=telephone=no`, `theme-color=#387ef5`, `apple-mobile-web-app-capable=yes`, `apple-mobile-web-app-status-bar-style=black-translucent`, `<base href="/">`, favicon + apple-touch-icon = `assets/img/appicon.png`, `<link rel="manifest" href="manifest.json">`.
* `<noscript>Please enable JavaScript to continue using this application.</noscript>`

`main.ts`: `enableProdMode()` when `environment.production`, bootstraps `AppModule`. `polyfills.ts`: only `import 'zone.js'`. `zone-flags.ts` sets `__Zone_disable_customElements = true` (not imported by anything in this tree — likely dead).

### 1.3 Angular/Ionic boot (`AppComponent`)
Constructor: `storage.create()`, then `initializeApp()` → `confData.load().subscribe(...)`:
* `next` → if `platform.is('hybrid')` → `SplashScreen.hide()`.
* `error` → same hide (so user is never stuck on splash).
* `ConferenceData.load()` (see §9): serves `schedule-cache` from Ionic Storage immediately if present, then GETs `${baseUrl}/2026/schedule/conference.json` with a **10 s** timeout. So the splash hides at *first emission* (cache hit → almost instantly; no cache → after network or after ≤10 s failure). On total failure a toast `Unable to load schedule, no offline cache available` (3 s, top, icon `exclamation`) is shown.

`ngOnInit()` (synchronous kick-offs):
1. `loadTheme()` → `userData.getTheme()` → sets `theme`.
2. `checkLoginStatus()` → `userData.isLoggedIn()` → `updateLoggedInStatus(loggedIn)`; if logged in also `userData.fetchPreferences()`.
3. `listenForLoginEvents()` → `window.addEventListener('user:login' | 'user:logout')` → `updateLoggedInStatus(true|false)`.
4. `fetchFeatures()` → if logged in: `userData.fetchFeatures()` (GET `/2026/api/v1/user/check_features/`, 2 s timeout → writes `hasLeadRetrieval`, `hasDoorCheck`, `hasMaskViolation` to storage) and `updateLoggedInStatus(loggedIn)` **again**.
5. `setTimeout(5000)` ("defer non-critical work"): `checkNotifications()`, `liveUpdateService.checkForUpdate()`, `notifications.getPrefs().then(() => notifications.applyPrefs())`.

`updateLoggedInStatus(loggedIn)` — wrapped in `setTimeout(…, 300)`:
* `this.loggedIn = loggedIn`
* `userData.fetchPreferences()` (GET `/2026/api/v1/user/mobile_state/`, 2 s timeout → favorites)
* `checkHasLeadRetrieval()/checkHasDoorCheck()/checkHasMaskViolation()` → each sets its flag AND `hasApps = hasApps || flag` (**sticky OR**: `hasApps` only ever returns to `false` via `logout()`).
* `getNickname()` → `nickname`.

### 1.4 Routing at launch
`''` → `redirectTo: '/tutorial'` (pathMatch full). `/tutorial` has `canLoad: [CheckTutorial]`:
```
await storage.create();
didTutorial = await storage.get('ion_did_tutorial');
if (didTutorial) {
  hasLead = await userData.checkHasLeadRetrieval();   // storage key 'hasLeadRetrieval'
  router.navigate(hasLead ? ['/app','tabs','lead-retrieval'] : ['/app','tabs','schedule']);
  return false;
}
return true;   // first launch → show TutorialPage
```
Consequences: first launch → Tutorial; later launches → Schedule, **or the Lead Scanner page for sponsor users who have lead retrieval**. The login page also calls `nav.navigateRoot('/')` after a successful login, so it re-enters this guard and a freshly logged-in lead-retrieval user is dropped onto the scanner, not the schedule.

Top-level `/account` and `/login` routes also exist outside the tabs (no tab bar/menu chrome around them), but every in-app link uses `/app/tabs/account` and `/app/tabs/login`; the top-level ones appear to be legacy/deep-link only.

---

## 2. Route map (`app-routing.module.ts` + `tabs-page-routing.module.ts`)

All tab children live under `/app/tabs`. `''` under tabs → `redirectTo '/app/tabs/schedule'`.

| Path under `/app/tabs/` | Module/component | Notes |
|---|---|---|
| `schedule` | `SchedulePage` (eager — `ScheduleModule` is imported by `TabsModule`) | default tab |
| `schedule/session/:sessionId` | SessionDetail | |
| `tracks/:trackSlug` | ScheduleListPage | menu "Presentations" + Open Spaces; slugs: `talks`, `keynotes`, `ais`, `securitys`, `charlas`, `lightning-talkss`, `tutorials`, `posters`, `sponsor-presentations`, `open-spaces` |
| `speakers`, `speakers/session/:sessionId`, `speakers/speaker-details/:speakerId` | SpeakerList / SessionDetail / SpeakerDetail | |
| `sponsors`, `sponsors/sponsor-detail/:sponsorId` | Sponsors / SponsorDetail | sponsor banner taps land here |
| `expo-hall` | ConferenceMapPage with `data: { initialView: 'expo-hall', pageTitle: 'Expo Hall' }` | same module as conference-map |
| `conference-map` | ConferenceMapPage | the "Map" tab |
| `lead-retrieval` | `MapModule` (`pages/map`) — despite the name this is the **Lead Scanner** | |
| `door-check`, `t-shirt-redemption`, `mask-violation` | staff tools | |
| `coc`, `wifi`, `notifications` (NotificationSettings), `rooms`, `rooms/room-detail/:roomSlug`, `rooms/session/:sessionId`, `venues-hours`, `lightning-talks`, `session-types`, `about-pycon`, `about-psf`, `social-media`, `sprints`, `keynote-speakers`, `job-listings`, `now`, `help`, `account`, `login`, `dev-tools` | lazy modules | |

Every side-menu link uses `routerDirection="root"` → Ionic replaces the navigation stack (no back-button, no push animation). Detail pages (session/speaker/sponsor/room detail) are the only pages with `ion-back-button`; all other pages carry an `ion-menu-button` hamburger.

---

## 3. `AppComponent` — side menu, theme picker, update banner, push toast

### 3.1 Route / reach
Not a route; it is the always-present root. Side menu is `<ion-menu contentId="main-content">` inside `<ion-split-pane contentId="main-content">`. Defaults apply: menu side `start`, overlay type, edge-swipe enabled (except when disabled by the Tutorial page), split-pane `when="lg"` (≥ 992 px → menu becomes a permanent left column, hamburger buttons auto-hide).

### 3.2 `<ion-app>` host classes
```
[class.dark-theme]                = theme === 'dark'
[class.high-contrast-theme]       = theme is 'high-contrast-light' OR 'high-contrast-dark'
[class.high-contrast-light-theme] = theme === 'high-contrast-light'
[class.high-contrast-dark-theme]  = theme === 'high-contrast-dark'
[class.has-update-banner]         = liveUpdateService.needsUpdate   (no CSS rule uses this class)
```
Light = no class at all. Ionic also stamps `md`/`ios` mode classes on every component host, so the compound selectors `.dark-theme.md` / `.dark-theme.ios` in `variables.scss` match `<ion-app>`.

### 3.3 Top of `<ion-app>` (above the split pane, persists across all pages)
1. `<a href="#main-content" class="skip-link">Skip to main content</a>` — visually off-canvas (`top:-100px`) until focused; then anchored top-left, primary bg, 12×20 px padding, bold 0.9 rem, radius `0 0 8px 0`, 3 px primary outline. Targets `<ion-router-outlet id="main-content" tabindex="-1">`.
2. **Global live-update banner** `<button class="update-banner" *ngIf="liveUpdateService.needsUpdate" (click)="liveUpdateService.performAutomaticUpdate()">`
   * Layout: full-width flex row, `gap 12px`, `padding 10px 16px`, `padding-top: calc(10px + env(safe-area-inset-top))`, `position:relative; z-index:1000`, `box-shadow 0 2px 8px rgba(0,0,0,.18)`, `text-align:left`, `font-size .95rem`, `line-height 1.2`.
   * Background `linear-gradient(135deg, var(--ion-color-primary,#5294e2), var(--ion-color-primary-shade,#3b73c4))`, text `--ion-color-primary-contrast` (#fff).
   * Children: `ion-icon cloud-download-outline` (1.5 rem, aria-hidden), text column (`<strong>New version available</strong>` 700 weight; `<span class="update-banner-cta">Tap to update</span>` 0.8 rem, opacity .92, letter-spacing .02em), `ion-icon chevron-forward` (1.2 rem, opacity .85).
   * `:active` → `filter: brightness(0.92)`.
   * Animation `update-banner-pulse 2.4s ease-in-out infinite` (box-shadow pulses to `0 2px 14px rgba(82,148,226,.55)` at 50 %), disabled under `prefers-reduced-motion: reduce`.
   * Because ion-app is a flex column, the banner pushes the whole split-pane down (it does not overlay headers).

### 3.4 Side-menu content (`<ion-menu><ion-content>` with `--padding-top/bottom: 20px`, background `var(--ion-item-background, var(--ion-background-color, #fff))`)

Two `<ion-list lines="none">` blocks. First list:

| # | Element | Label / content | Icon (ionicons) | Route / action | Visible when | Extra |
|---|---|---|---|---|---|---|
| 1 | `ion-list-header` | **PyCon US 2026** | – | – | always | |
| 2 | `ion-menu-toggle autoHide="true"` > `ion-item.update-cta button lines=none detail=false` | h3 **Install Latest Update** / p "New content is ready — tap to refresh" | `cloud-download-outline` inside 36 px circle `.update-cta-icon`; trailing `chevron-forward` | `(click)="liveUpdateService.performAutomaticUpdate()"` | `liveUpdateService.needsUpdate` **and** the menu is toggleable (autoHide=true hides it in split-pane/desktop mode) | tinted card: bg `rgba(primary-rgb,.10)` (hover .16 / activated .20 / focused .18), color primary, radius 14 px, `margin 4px 14px 12px`, `--min-height 60px`, `box-shadow 0 1px 3px rgba(primary-rgb,.18)`; h3 15 px/600 primary; p 12 px `--ion-color-medium` |
| 3 | `ion-menu-toggle autoHide="false"` > `ion-item routerLink="/app/tabs/dev-tools" routerLinkActive="active" routerDirection="root" detail=false color="warning"` | **Dev Tools** | `construct-outline` | `/app/tabs/dev-tools` | `isDev` = `!environment.production` (true for `base` and `development` builds, false for prod) | yellow (`warning`) item background |
| 4 | `ion-item` (plain, non-clickable) | **Hello, {{nickname}}** | – | – | `loggedIn` | nickname from storage key `nickname` |
| 5 | `ion-list-header` | **Apps** | – | – | `hasApps` | |
| 6 | item | **CoC Incident** | `shield-checkmark-outline` | `/app/tabs/mask-violation` | `hasMaskViolation` | routerLinkActive="active" |
| 7 | item | **Door Check** | `checkbox-outline` | `/app/tabs/door-check` | `hasDoorCheck` | |
| 8 | item | **Swag Pickup** | `shirt-outline` | `/app/tabs/t-shirt-redemption` | `hasDoorCheck` | |
| 9 | item | **Lead Scanner** | `qr-code` | `/app/tabs/lead-retrieval` | `hasLeadRetrieval \|\| hasDoorCheck` | |
| 10 | `ion-list-header` | **Schedule** | – | – | always | |
| 11 | `*ngFor schedulePages` items (`routerLinkActive="selected"`) | Schedule / Speakers / Keynote Speakers / Rooms | `calendar-outline` / `people-outline` / `star-outline` / `pin-outline` | `/app/tabs/schedule`, `/app/tabs/speakers`, `/app/tabs/keynote-speakers`, `/app/tabs/rooms` | always | `[class]="p.indent ? 'indent' : ''"` — no entry defines `indent`, never applied |
| 12 | `ion-accordion-group` > `ion-accordion value="first"`; header `ion-item slot="header" color="white"` | header **Presentations**; body = `*ngFor presentationPages` | header `newspaper`; children: `mic-outline` Talks, `star-outline` Keynotes, `hardware-chip-outline` AI, `shield-checkmark-outline` Security, `chatbubbles-outline` Charlas, `flash-outline` Lightning Talks, `book-outline` Tutorials, `easel-outline` Posters, `briefcase-outline` Sponsor Presentations | `/app/tabs/tracks/talks`, `/keynotes`, `/ais`, `/securitys`, `/charlas`, `/lightning-talkss`, `/tutorials`, `/posters`, `/sponsor-presentations` | always; **collapsed by default** (group has no `value`) | child items get `--padding-start: 40px`; `color="white"` is not a defined Ionic colour → effectively transparent/default |
| 13 | `ion-list-header` | **Events** | – | – | always | |
| 14 | `*ngFor conferencePages` | Open Spaces / Lightning Talks / Sprints | `people-circle-outline` / `flash-outline` / `rocket-outline` | `/app/tabs/tracks/open-spaces`, `/app/tabs/lightning-talks`, `/app/tabs/sprints` | always | |
| 15 | `ion-list-header` | **Expo & Sponsors** | – | – | always | |
| 16 | `*ngFor expoPages` | Sponsors / Expo Hall / Job Listings | `business-outline` / `storefront-outline` / `briefcase-outline` | `/app/tabs/sponsors`, `/app/tabs/expo-hall`, `/app/tabs/job-listings` | always | |
| 17 | `ion-list-header` | **Information** | – | – | always | |
| 18 | `ion-accordion-group` > `ion-accordion value="about"`; header item `color="white"` | header **About PyCon US**; body = `*ngFor aboutPages` | header `information-circle-outline`; children: `information-circle-outline` Conference Info, `shield-checkmark-outline` Code of Conduct, `wifi-outline` Wi-Fi, `location-outline` Venue & Hours, `pricetags-outline` Session Types | `/app/tabs/about-pycon`, `/coc`, `/wifi`, `/venues-hours`, `/session-types` | always; collapsed by default | |
| 19 | `*ngFor infoPages` | About The PSF / Social / Conference Maps / Help & Safety | `logo-python` / `chatbubbles-outline` / `map-outline` / `help-circle-outline` | `/app/tabs/about-psf`, `/app/tabs/social-media`, `/app/tabs/conference-map`, `/app/tabs/help` | always | |

Second list `<ion-list lines="none" class="account-list">` (top padding zeroed so the gap matches other sections; on MD the first list has a 1 px bottom border `--ion-color-step-150,#d7d8da`):

| # | Element | Label | Icon | Route / action | Visible when |
|---|---|---|---|---|---|
| 20 | `ion-list-header` | **Account** | – | – | always |
| 21 | item (`routerLinkActive="active"`) | **Account** | `person` | `/app/tabs/account` | `loggedIn` |
| 22 | item | **Login** | `log-in` | `/app/tabs/login` | `!loggedIn` |
| 23 | item | **Notifications** | `notifications-outline` | `/app/tabs/notifications` | always |
| 24 | `ion-item button` | **Logout** (label `color="danger"`) | `log-out-outline` `color="danger"` | `(click)="logout()"` | `loggedIn` |
| 25 | `ion-item lines="none" class="theme-picker-item"` (not a menu-toggle; menu stays open) | `ion-icon contrast-outline` (aria-hidden) + `<ion-select label="Theme" interface="action-sheet" [interfaceOptions]="{header:'Choose theme'}" aria-label="App theme" [value]="theme" (ionChange)="setTheme($event.detail.value)">` options: `light` "Light", `dark` "Dark", `high-contrast-light` "High Contrast (Light)", `high-contrast-dark` "High Contrast (Dark)" | always |

Menu item styling that matters:
* All items are wrapped in `ion-menu-toggle` → tapping closes the overlay menu (except theme picker & the plain "Hello" item).
* `ion-item.selected { --color: primary }`; MD: `--background: rgba(primary-rgb,.14)`, icon primary, pill shape `border-radius 0 50px 50px 0`, `margin-right 10px`, `--padding-start 18px`, font-weight 500; headers uppercase, `letter-spacing .1em`, weight 450, colour `--ion-color-step-650,#5f6368`; icons same grey. iOS: `--padding-start 16px`, `--min-height 50px`, icons 24 px `#73849a` (primary when selected), headers `margin-bottom 8px`.
* Only `routerLinkActive="selected"` items (the page groups) get the highlight; staff/account items use `routerLinkActive="active"`, and nothing styles `.active` → **no highlight** for Dev Tools / Apps / Account / Login / Notifications.
* `ion-menu ion-item { --transition: none }` to avoid colour animation when switching themes.

### 3.5 Theme picker behaviour
* `setTheme(theme)` → sets `this.theme` (class bindings re-evaluate instantly) and `userData.setTheme(theme)` → `storage.set('theme', theme)`.
* `userData.getTheme()` migration logic: stored `'high-contrast'` → rewritten to `'high-contrast-dark'`; any of the four valid values → returned; else legacy `darkTheme === true` → `theme='dark'` + remove `darkTheme`; `darkTheme === false` → remove key; default `'light'`. Theme is **not** derived from the OS setting (no `prefers-color-scheme` logic anywhere in app code).
* Picker presents a bottom action sheet titled "Choose theme" with the four options + Cancel.

### 3.6 Logout
`logout()` → `userData.logout()` (removes `hasLoggedIn`, `favorite_sessions`, `email`, `nickname`, `key`, `secret`, `hasLeadRetrieval`, `hasDoorCheck`, `hasMaskViolation`, `isSpeaker`, `hasScannerConsent`, then dispatches `user:logout`) → resets `hasApps/hasLeadRetrieval/hasDoorCheck/hasMaskViolation = false` → `router.navigateByUrl('/app/tabs/schedule')`. Note the `user:logout` listener also fires `updateLoggedInStatus(false)` 300 ms later. **No confirmation dialog.**

### 3.7 Push notifications wiring (`checkNotifications()`, run 5 s after init, hybrid *not* checked)
```
FirebaseMessaging.addListener('tokenReceived', e => console.info('Registration token: ', e.token));
FirebaseMessaging.requestPermissions().then(r => { if (r.receive !== 'granted') return;
  FirebaseMessaging.getToken().catch(err => console.warn('FirebaseMessaging.getToken failed', err)); });
FirebaseMessaging.addListener('notificationReceived', async (event) => {
  const showed = notifications.shouldShowPushBanner();   // any of emergency/announcements/scheduleChanges/dailyDigest prefs true
  FirebaseAnalytics.logEvent({ name: 'notification_received',
     params: { topic: event?.notification?.data?.['topic'] ?? 'unknown', banner_shown: showed } }).catch(()=>undefined);
  if (!showed) return;
  title = notification?.title ?? 'PyCon US'; body = notification?.body ?? '';
  toastCtrl.create({ message: body ? `${title}: ${body}` : title, position: 'top',
                     buttons: [{ icon: 'close', side: 'end', role: 'cancel' }] }).present();   // no duration → stays until closed
});
```
So a **foreground** push shows a persistent top toast "Title: body" with an ✕ button. Permission prompt appears ~5 s after first launch (after tutorial if tutorial is showing — the component is global).

### 3.8 Dead / unused members
`openTutorial()` (disables menu, sets `ion_did_tutorial=false`, navigates `/tutorial`), `openUrl(url)` (`window.open(url,'_system','location=yes')`), `updateAvailable`, `environmentUrl` — defined in `app.component.ts` but not referenced by its template.

### 3.9 Plugins used here
| Import | Calls |
|---|---|
| `@capacitor/splash-screen` `SplashScreen` | `hide()` (hybrid only) |
| `@capacitor-firebase/messaging` `FirebaseMessaging` | `addListener('tokenReceived')`, `requestPermissions()`, `getToken()`, `addListener('notificationReceived')` |
| `@capacitor-firebase/analytics` `FirebaseAnalytics` | `logEvent({name:'notification_received', params})` |
| `@ionic/storage-angular` `Storage` | `create()`, `set('ion_did_tutorial', false)` |

Web behaviour: SplashScreen skipped; the Firebase calls run on web too (the plugin has a web implementation that needs a Firebase web config — not present — so they reject; only `getToken` has a `.catch`).

### 3.10 Complexity: **4/5** — many conditional menu states, four live theme classes, persistent global banner, event-bus coupling (`user:login/logout`), async timing hacks (300 ms / 5 s), and plugin side effects.

---

## 4. `TabsPage` (`/app/tabs`) — tab bar, sponsor banner, staff-tools sheet

### 4.1 Structure (`tabs-page.html`)
```
<ion-tabs>
  <ion-tab-bar slot="bottom" class="bannerSponsor bannerSponsorHidden" *ngFor="let s of sponsors" (click)="goToSponsor(s)" role="button" [attr.aria-label]="'View ' + s.name + ' sponsor details'">
     <img class="bannerSponsor-logo" src="{{s.logo_url}}">
     <span class="bannerSponsor-text">{{s.name}} is a {{s.level}}<br> Sponsor of PyCon US 2026</span>
  </ion-tab-bar>
  <ion-tab-bar slot="bottom" class="pycon-tab-bar"> …tab buttons… </ion-tab-bar>
  <ion-modal #staffToolsModal [isOpen]="showStaffTools" (didDismiss)="showStaffTools=false" [breakpoints]="[0,0.35]" [initialBreakpoint]="0.35" [handle]="true"> …sheet… </ion-modal>
</ion-tabs>
```
Because both bars are `slot="bottom"` and the sponsor bars come first in DOM order, the **sponsor banner renders as a strip directly above the real tab bar**.

### 4.2 Sponsor banner rotation
* Data: `confData.getSponsors()` → `data.conference.sponsors`, an **object keyed by level name** (`Visionary`, `Sustainability`, `Maintaining`, `Contributing`, `Supporting`, `Partner`, `Participating`, `Associate`, `Standalone Only`, `AV Partner`, `Media`, `Startup Row`, `Community` in the current feed) → arrays of `{ name, level, level_order, logo_url, description, booth_number, job_fair_table_number, mobile_banner }`. `reloadSponsors()` flattens all levels and keeps those with truthy `mobile_banner` (14 in the local feed, e.g. NVIDIA, Anthropic PBC, Bloomberg, Google, Meta, Fastly — all level `Visionary`), stores in `sponsors`, then `setTimeout(showSponsorBanner, 100)`.
* Rotation: `setInterval(this.showSponsorBanner, 30000)` set in `ngOnInit` (never cleared). `showSponsorBanner()` is pure DOM: every element with class `bannerSponsorVisible` → swap to `bannerSponsorHidden`; pick `hidden.item(hidden.length * Math.random() | 0)` from the **currently hidden** set and show it. Result: one random banner visible at a time, changed every 30 s, never the same one twice in a row when ≥2 exist; nothing is shown until 100 ms after sponsors arrive. First choice also random.
* Styles: `.bannerSponsorHidden { display:none }`; `.bannerSponsor { padding-bottom:0; gap:1em; padding-left/right:1em; cursor:pointer }`; logo `background:white; border-radius:.25em; padding:.25em; max-width:110px; max-height:44px; object-fit:contain; flex-shrink:0`; text `font-size:smaller; flex:1; min-width:0`. The strip inherits ion-tab-bar height (~50 px MD / 50 px iOS) and `--ion-tab-bar-background`.
* Tap: `goToSponsor(sponsor)` → `slug = name.toLowerCase().replace(/\s+/g,'-').replace(/[^a-z0-9-]/g,'')` → `router.navigateByUrl('/app/tabs/sponsors/sponsor-detail/<slug>')` (e.g. `Anthropic, PBC` → `anthropic-pbc`). Returns early if no name.

### 4.3 Main tab bar (`.pycon-tab-bar`)
| Order | `tab=` | Icon | Label | Condition | Active when `activeTab ===` |
|---|---|---|---|---|---|
| 1 | `speakers` | `people` | Speakers | always | `'speakers'` |
| 2 | `conference-map` | `map` | Map | always | `'conference-map'` (note `/expo-hall` does **not** highlight it) |
| 3 | `schedule` | `calendar` | Schedule | always | `'schedule'` |
| 4 | `now` | `radio` | Now | always | `'now'` |
| 5a | *(no tab attr)* `(click)="openStaffTools($event)"` | `scan` | Scanner | `hasDoorCheck \|\| hasMaskViolation` | `'lead-retrieval'` |
| 5b | `lead-retrieval` | `qr-code` | Scanner | `hasLeadRetrieval && !hasDoorCheck && !hasMaskViolation` | `'lead-retrieval'` |
| 6 | `login` | `log-in` | Login | `!loggedIn` | `'login'` |

* Active styling: `.pycon-tab-bar ion-tab-button.pycon-active { --color: #DD04D2; ion-label { font-weight:700 } }` (magenta). `activeTab = url.match(/\/app\/tabs\/([^/?#]+)/)[1]` recomputed on every `NavigationEnd` (`urlAfterRedirects`) and once at init from `router.url`. Thus nested routes keep the parent tab lit (`/app/tabs/schedule/session/42` → schedule) and non-tab pages (`tracks`, `rooms`, `about-*`, …) light nothing. Ionic's own `tab-selected` colouring also applies underneath.
* `openStaffTools(event)`: `stopPropagation(); preventDefault(); showStaffTools = true` — the tab is **not** switched.
* Tab buttons with `tab="x"` navigate to `/app/tabs/x` through `ion-tabs` (Ionic preserves per-tab navigation stacks).

### 4.4 Staff Tools bottom sheet (`ion-modal`, sheet with breakpoints `[0, 0.35]`, initial `0.35`, drag handle, dismiss by drag/backdrop)
`<ion-content class="staff-tools-sheet">` (bg `--ion-background-color`), header div `padding 16px 20px 8px` with `<h2>Staff Tools</h2>` (1.1 rem, 700, `--ion-text-color`), then `<ion-list lines="full">`:

| Item | Icon (`color="primary"`, slot start) | Condition | `goToTool(path)` |
|---|---|---|---|
| Door Check | `checkbox-outline` | `hasDoorCheck` | `/app/tabs/door-check` |
| Swag Pickup | `shirt-outline` | `hasDoorCheck` | `/app/tabs/t-shirt-redemption` |
| Lead Scanner | `qr-code-outline` | `hasLeadRetrieval \|\| hasDoorCheck` | `/app/tabs/lead-retrieval` |
| CoC Incident | `shield-checkmark-outline` | `hasMaskViolation` | `/app/tabs/mask-violation` |

All items `button detail="true"` (chevron). `goToTool` sets `showStaffTools=false` then `router.navigateByUrl(path)`.

### 4.5 State & lifecycle
* `ngOnInit`: `reloadSponsors()`, `checkHasLeadRetrieval()`, `checkHasDoorCheck()`, `checkHasMaskViolation()`, `checkLoggedIn()`, `listenForLoginEvents()`, `setInterval(showSponsorBanner, 30000)`, activeTab wiring.
* Each `checkHas*` reads storage and applies the value inside `setTimeout(…, 200)` (change-detection workaround).
* `listenForLoginEvents`: on `user:login` **and** `user:logout` → `checkHasLeadRetrieval()`, `checkHasDoorCheck()`, `checkLoggedIn()` — **`checkHasMaskViolation()` is not re-run**, so the Scanner-vs-staff-sheet decision for a mask-violation-only staffer only updates after an app restart (or when a later `fetchFeatures` happens to run before the first check… it doesn't; so restart).
* `goTo(path)` helper unused by template.
* No teardown: interval and window listeners leak (component lives for the app's lifetime anyway).

### 4.6 Data / storage
Reads `hasLeadRetrieval`, `hasDoorCheck`, `hasMaskViolation`, `hasLoggedIn` via `UserData`; `conference.sponsors` via `ConferenceData.load()` (cached in memory + `schedule-cache`).

### 4.7 Accessibility
Sponsor strip: `role="button"`, `aria-label="View {name} sponsor details"`; logo `<img>` has **no alt**. Tab buttons use Ionic defaults (label text is the accessible name).

### 4.8 Complexity: **3/5** — conditional tab set, DOM-driven random rotation, bottom sheet; the hard part is the staff-permission matrix and keeping the tab highlight in sync with nested routes.

---

## 5. `TutorialPage` (`/tutorial`) + `CheckTutorial` guard

### 5.1 Reach
Root redirect `''` → `/tutorial`, gated by `canLoad: [CheckTutorial]` (see §1.4). Only shown when `ion_did_tutorial` is falsy (first run, or after `storage.clear()` from Dev Tools "Nuke"). `openTutorial()` in AppComponent would re-open it but is not wired to any UI.

### 5.2 UI
* `<ion-header no-border><ion-toolbar></ion-toolbar></ion-header>` — empty toolbar, `--background: transparent; --border-color: transparent` (acts as a safe-area spacer).
* `<ion-content fullscreen="true">` with host `--ion-background-color: #680579` (brand purple).
* `.slide-container`: flex column, 100 % × 100 %, centred both axes, `text-align:center`.
  * `<img src="assets/img/splash.png" class="slide-image">` — `max-height:50%; max-width:80%; object-fit:contain; margin:5vh 0; pointer-events:none`. (splash.png is 5559×6984, purple background with the retro sunset/palms "PYCON·US 2026 Long Beach" logo — so the image's own purple blends into the page.)
  * `<h2 class="slide-title">Welcome to <b>PyCon US 2026</b></h2>` — white, `margin-top: 2.8rem`, `b { font-weight: 500 }`, heading weight otherwise `--ion-headings-font-weight: 300`.
  * `<button class="continue-btn" (click)="startApp()">Continue <ion-icon name="arrow-forward"></ion-icon></button>` — inline-flex, `gap .5ch`, `padding .75em 1.5em`, `border 1.5px solid rgba(255,255,255,.4)`, `border-radius .5em`, bg `#ffffff`, text `#101136`, `font-size 1rem`, weight 600, `line-height 1`, `box-shadow 0 0 18px 0 rgba(255,192,203,.5)` (pink glow), `transition all .2s`, icon `1.1em`.
* Unused SCSS for `p` (14 px, `--ion-color-step-600`) — no `<p>` in the template.

### 5.3 Behaviour
* `startApp()` → `router.navigateByUrl('/app/tabs/schedule', { replaceUrl: true })` → then `storage.set('ion_did_tutorial', true)`.
* `ionViewWillEnter` → `menu.enable(false)` (no swipe-to-open menu on the tutorial); `ionViewDidLeave` → `menu.enable(true)`.
* `showSkip = true`, `onSlideChangeStart()` (calls `cd.detectChanges()`) are leftovers from the old multi-slide tutorial; no slides exist now.
* No swipe, no skip button, no pagination.

### 5.4 Storage keys
`ion_did_tutorial` (boolean). `UserData.HAS_SEEN_TUTORIAL = 'hasSeenTutorial'` exists but is **never written**; only read by `checkHasSeenTutorial()` which nothing calls.

### 5.5 Complexity: **1/5** — single static screen; the only subtlety is the guard's redirect target.

---

## 6. `LiveUpdateService` (`providers/live-update.service.ts`, `providedIn: 'root'`, also listed in `AppModule.providers`)

| Member | Behaviour |
|---|---|
| ctor | `App.addListener('appStateChange', ({isActive}) => isActive && this.checkForUpdate())` — every foreground resume re-checks |
| `updateAppInfo()` | `App.getInfo()` → `appVersion = info.version`, `build = info.build` |
| `checkForUpdate()` | `await updateAppInfo()`; `result = await LiveUpdates.sync()`; `updateAvailable = result`; `snapshot = result.snapshot` (`{id, buildId}` or null); `channel = result.liveUpdate?.channel ?? ''`; if `result.activeApplicationPathChanged` → `needsUpdate = true` and `document.body.classList.add('has-pending-update')` |
| `reload()` | `await LiveUpdates.reload()`; `needsUpdate = false` |
| `performAutomaticUpdate()` | `LoadingController.create({ message: 'Installing the latest build...', duration: 60000 })` → present; if `needsUpdate` → `reload()` (not awaited); `setTimeout(() => loader.dismiss(), 1000)` |
| fields read elsewhere | `about-pycon.page.html` shows `appVersion`, `build`, `snapshot.buildId` (as `#id`), `channel`; `schedule.ts` and `about-pycon.page.ts` also call `checkForUpdate()` |

Callers of `checkForUpdate()`: AppComponent (5 s after init), `appStateChange` resume, Schedule page, About PyCon page.

Appflow config (`capacitor.config.ts` → `plugins.LiveUpdates`): `appId 'e8e09c7a'`, `channel 'Production'`, `autoUpdateMethod 'none'` (manual sync/reload), `maxVersions 3`, `enabled true`. `Makefile appflow-ship` builds on Appflow and deploys to channel `Production`; new bundles are picked up "on next cold launch" per the Makefile note, but the service actually downloads on every `sync()` and only *applies* when the user taps.

Three UI affordances fed by `needsUpdate` / body class:
1. Global top banner (§3.3).
2. Side-menu "Install Latest Update" card (§3.4 #2).
3. `global.scss`: `body.has-pending-update ion-menu-button::after` — 9 px circle, `top:8px; right:6px`, bg `--ion-color-primary`, 2 px ring in `--ion-background-color`, `pointer-events:none` → a **primary-coloured dot on every hamburger button** app-wide. Note the body class is never removed (only `needsUpdate` flips to false; after `reload()` the page restarts anyway).

Web / dev behaviour: `@capacitor/live-updates` and `App.getInfo()` have no web implementation → `checkForUpdate()` rejects (unhandled promise, console noise), `needsUpdate` stays false, no banner. Looks hard to port because it is a Capacitor/Appflow-specific OTA mechanism with no equivalent concept outside Ionic.

Complexity: **2/5** for the UI, but the OTA semantics themselves are platform-bound.

---

## 7. `DevToolsPage` (`/app/tabs/dev-tools`)

### 7.1 Reach
Side-menu "Dev Tools" item (only when `!environment.production`). The route is **always registered**, so a prod build still serves it at `/app/tabs/dev-tools` (deep link / typed URL).

### 7.2 UI (`ion-header.ion-no-border` → `ion-toolbar color="warning"` with `ion-menu-button` (start) and `ion-title` "Dev Tools"; `ion-content` with four `ion-card`s + an 80 px spacer `<div>` at the bottom)

**Card 1 — "Environment"** (`ion-list lines="none"`, each `ion-item` → `ion-label` with `<p>` caption over `<h3>` value):
`Name` → `env.name`; `API Base URL` → `env.baseUrl` (h3 inline style `font-family: monospace; font-size: .85rem`); `Timezone` → `env.timezone`; `Production` → `env.production`.

**Card 2 — "Storage"**, subtitle `"{storageCount} keys | {scanCount} scans"`; one `ion-button expand="block" fill="outline" color="medium"` with `code-outline` icon: **Dump Storage to Console** → `dumpStorage()`.

**Card 3 — "Actions"** (`ion-list lines="none"`, `ion-item button detail="false"`, each with icon + `<h2>` + `<p>`):
| Label | Sub-label | Icon / colour | Handler |
|---|---|---|---|
| Clear Scan Data | Remove all scans, notes, consent, sponsor selection | `trash-outline` warning | `clearScanData()` |
| Invalidate Schedule Cache | Force re-fetch of conference.json on next load | `refresh-outline` warning | `invalidateCache()` |
| Nuke All Storage | Wipe everything and reload — you will be logged out | `nuclear-outline` danger | `nukeStorage()` |
| Refresh Stats | Update storage key counts | `analytics-outline` primary | `refreshStats()` |

**Card 4 — "Notification tests"**, subtitle: "Each button schedules a sample notification 5 seconds out — but only if the matching toggle on the Notifications settings page is ON. Flip a toggle off and re-tap to confirm gating works." Six `ion-item button` rows (`notifications-outline` primary icon, `<h2>{{label}}</h2>`, `<p>Test in 5s</p>`), order matching the Notifications settings page:
`lightning` "Lightning Talk sign-ups", `openSpace` "Open Space sign-ups", `announcements` "Announcements", `scheduleChanges` "Schedule changes", `dailyDigest` "Daily digest", `emergency` "Emergency & safety".

### 7.3 Logic
* `ionViewWillEnter` → `refreshStats()`: `storage.keys()` → `storageCount = keys.length`; `scanCount` = keys starting with `pending-scan-`, `synced-scan-`, `failed-scan-`.
* `clearScanData()`: removes keys starting with `pending-scan-`, `synced-scan-`, `failed-scan-`, `pending-note-`, `note-`, or equal to `staff-sponsor-id`, `staff-sponsor-name`, `hasScannerConsent`; toast `Cleared {n} scan entries`; refresh.
* `invalidateCache()`: `confData.invalidateCache()` (sets in-memory `data=null`, removes `schedule-cache`); toast `Schedule cache invalidated — pull to refresh`; refresh.
* `nukeStorage()`: `storage.clear()`; toast `All storage wiped — reloading...`; `setTimeout(() => window.location.reload(), 500)` (full page reload → tutorial shows again, user logged out, theme reset).
* `dumpStorage()`: `storage.forEach` → object of `key → (objects JSON-stringified and truncated to 100 chars | String(value))` → `console.table(dump)`; toast `Storage dumped to console (open DevTools)`.
* `testNotif(category, label)` → `notifications.scheduleCategoryTestNotification(category)` → toast (2500 ms, bottom) by outcome:
  * `fired` → `"{label}: firing at {fireAt.toLocaleTimeString()}."` colour `success`
  * `muted` → `"{label}: toggle is OFF — gating works, no notification scheduled."` colour `warning`
  * `denied` → `"{label}: OS notification permission denied."` colour `danger`
  * `web` → `"{label}: only fires on iOS / Android."` colour `medium`
  (service: web → `web`; pref off → `muted`; `LocalNotifications` permission not granted → `denied`; else cancels id `8999` and schedules id `8999` at `now+5000ms`, `allowWhileIdle: true`, using `TEST_NOTIFICATION_COPY[category]` title/body.)
* All other toasts: `duration 2000`, `position 'bottom'`, `color 'dark'`.
* **No confirmations** for any destructive action.

### 7.4 Complexity: **2/5** — simple cards/lists; depends on storage enumeration and the notification service.

---

## 8. Theming (`src/theme/variables.scss`, `src/global.scss`, `app.component.scss`)

### 8.1 Mode model
Four `ThemeMode`s: `light | dark | high-contrast-light | high-contrast-dark` (`THEME_MODES` in `user-data.ts`). Applied as classes on `<ion-app>` (§3.2). No automatic OS-follow. Native splash does honour OS dark mode (iOS `-dark` splash assets, Android `drawable-night`), independent of the in-app theme.

Platform mode (`md` vs `ios`) is Ionic's default detection (iOS devices → `ios`, everything else incl. desktop/Android/web → `md`). Dark theme has **different surface colours per platform**; HC themes do not.

### 8.2 Base palette (`:root`, i.e. Light theme). Each colour has `-rgb`, `-contrast`, `-contrast-rgb`, `-shade`, `-tint`.

| Token | Light (`:root`) | Dark (`.dark-theme`) | HC Light | HC Dark |
|---|---|---|---|---|
| primary | `#3880ff` (shade `#3171e0`, tint `#4c8dff`, contrast `#fff`) | `#428cff` (shade `#3a7be0`, tint `#5598ff`) | `#4a0072` (shade `#410064`, tint `#5c1a80`, contrast `#fff`) | `#ffd60a` (shade `#e0bc09`, tint `#ffda23`, **contrast `#0b0f17`**) |
| secondary | `#3dc2ff` (`#36abe0`/`#50c8ff`) | `#50c8ff` (`#46b0e0`/`#62ceff`) | `#003a99` (`#00337f`/`#1a4ea3`) | `#5ac8fa` (`#4fb0dc`/`#6bcefb`, contrast `#0b0f17`) |
| tertiary | `#5260ff` (`#4854e0`/`#6370ff`) | `#6a64ff` (`#5d58e0`/`#7974ff`) | `#7a1a8a` (`#6a1779`/`#863196`) | `#c084ff` (`#a974e0`/`#c690ff`, contrast `#0b0f17`) |
| success | `#2dd36f` (`#28ba62`/`#42d77d`, contrast `#fff`) | `#2fdf75` (`#29c467`/`#44e283`, contrast `#000`) | `#146c2e` (`#115f29`/`#2b7a44`) | `#30d158` (`#2ab84d`/`#45d669`, contrast `#0b0f17`) |
| warning | `#ffc409` (`#e0ac08`/`#ffca22`, contrast `#000`) | `#ffd534` (`#e0bb2e`/`#ffd948`, contrast `#000`) | `#7a4a00` (`#6b4100`/`#875c1a`, contrast `#fff`) | `#ffd60a` (same as primary, contrast `#0b0f17`) |
| danger | `#eb445a` (`#cf3c4f`/`#ed576b`) | `#ff4961` (`#e04055`/`#ff5b71`) | `#a30000` (`#8f0000`/`#ad1a1a`) | `#ff8a80` (`#e07971`/`#ff968d`, contrast `#0b0f17`) |
| dark | `#222428` (`#1e2023`/`#383a3e`, contrast `#fff`) | `#f4f5f8` (`#d7d8da`/`#f5f6f9`, contrast `#000`) | `#1a1d24` (`#171a20`/`#31343a`) | `#f5f5f0` (`#d8d8d3`/`#f6f6f2`, contrast `#0b0f17`) |
| medium | `#92949c` (`#808289`/`#9d9fa6`, contrast `#fff`) | `#989aa2` (`#86888f`/`#a2a4ab`, contrast `#000`) | `#4a4d54` (`#41444a`/`#5c5f65`) | `#b0b3ba` (`#9b9ea3`/`#b8bbc1`, contrast `#0b0f17`) |
| light | `#f4f5f8` (`#d7d8da`/`#f5f6f9`, contrast `#000`) | `#222428` (`#1e2023`/`#383a3e`, contrast `#fff`) | `#f0eee8` (`#d3d1cc`/`#f2f1eb`, contrast `#1a1d24`) | `#1a1d24` (`#171a20`/`#31343a`, contrast `#f5f5f0`) |
| favorite (custom) | `#69bb7b` (`#5ca56c`/`#78c288`, contrast `#fff`) | *(unchanged)* | `#4a0072` (= primary) | `#ffd60a` (= primary, contrast `#0b0f17`) |
| background | Ionic default `#ffffff` | iOS `#000000` / MD `#121212` | `#fbfaf6` (cream) | `#0b0f17` (ink) |
| text | Ionic default `#000000` | `#ffffff` | `#1a1d24` | `#f5f5f0` |
| border | default | MD `#222222` | `#1a1d24` | `#f5f5f0` |
| item background | default | iOS `#000000` / MD `#1e1e1e` | `#fbfaf6` (item colour `#1a1d24`, item border `#1a1d24`) | `#0b0f17` (item colour `#f5f5f0`, border `#f5f5f0`) |
| toolbar background | default | iOS `#0d0d0d` / MD `#1f1f1f` | `#fbfaf6` (colour `#1a1d24`, border `#1a1d24`) | `#0b0f17` (colour `#f5f5f0`, border `#f5f5f0`) |
| tab-bar background | default | MD `#1f1f1f` (iOS not set) | `#fbfaf6` (colour `#1a1d24`, selected `#4a0072`, border `#1a1d24`) | `#0b0f17` (colour `#f5f5f0`, selected `#ffd60a`, border `#f5f5f0`) |
| card background | default | not set | `#ffffff` (colour `#1a1d24`) | `#11151d` (colour `#f5f5f0`) |

Step colours (`--ion-color-step-50 … -950`, used by Ionic for secondary text/dividers):
* Dark iOS: `#0d0d0d, #1a1a1a, #262626, #333333, #404040, #4d4d4d, #595959, #666666, #737373, #808080, #8c8c8c, #999999, #a6a6a6, #b3b3b3, #bfbfbf, #cccccc, #d9d9d9, #e6e6e6, #f2f2f2`.
* Dark MD: `#1e1e1e, #2a2a2a, #363636, #414141, #4d4d4d, #595959, #656565, #717171, #7d7d7d, #898989, #949494, #a0a0a0, #acacac, #b8b8b8, #c4c4c4, #d0d0d0, #dbdbdb, #e7e7e7, #f3f3f3`.
* HC Light: `#f2f0eb, #e9e7e1, #e0ddd6, #d6d3cb, #cdc9c0, #b8b4ab, #a3a097, #8e8b83, #7a766f, #4a4d54, #41444a, #383b41, #2f3137, #26282d, #1f2126, #1a1d24, #15171c, #0d0e12, #050608` (note the jump at step-500 → text-grade greys from there up).
* HC Dark: `#11151d, #161a23, #1c2029, #21252f, #272b35, #2d313b, #393d47, #494d57, #595d67, #b0b3ba, #b9bcc2, #c1c4ca, #cacdd2, #d2d5da, #dbdde2, #e3e5ea, #ecedf0, #f0f1f3, #f5f5f0`.

Other `:root` tokens: `--ion-headings-font-weight: 300`; legacy Ionic-demo track colours `--ion-color-angular #ac282b`, `communication #8e8d93`, `tooling #fe4c52`, `services #fd8b2d`, `design #fed035`, `workshop #69bb7b`, `food #3bc7c4`, `documentation #b16be3`, `navigation #6600cc` (probably unused). Social colours with `.ion-color-*` classes: `twitter #1da1f4`, `instagram` (declared twice: `#5956d8` var then class override `#9537BC`), `vimeo #23b6ea`, `facebook #3b5998`, `github #211F1F`, `google` (class references undefined vars).

### 8.3 Cross-cutting HC rules (`.high-contrast-theme`, in both files)
* `ion-toolbar { --border-width: 0 0 1px 0; --border-color: var(--ion-border-color) }`; `ion-tab-bar { border-top: 1px solid var(--ion-border-color) }`; `ion-card { border: 1px solid var(--ion-border-color); box-shadow: none }`.
* Focus ring: `a, button, ion-button, ion-item, ion-tab-button, ion-segment-button, ion-select, [tabindex]` `:focus-visible { outline: 3px solid var(--ion-color-primary); outline-offset: 2px }`.
* `ion-label p, ion-label h3 + p, ion-note, ion-item ion-note[slot] { color: var(--ion-text-color); opacity: 1 }` — secondary text promoted to full text colour.
* Track badges lose their fills: `background: transparent; color: var(--ion-text-color); border: 1.5px solid var(--ion-text-color)`.

### 8.4 Global rules (`global.scss`) relevant to every screen
* Imports Ionic `core, normalize, structure, typography, padding, float-elements, text-alignment, text-transformation, flex-utils` CSS.
* Text selection enabled for `p, h1–h6, ion-text, ion-label` inside `ion-content`; `overflow-wrap:anywhere; word-break:break-word` for `p, li, ion-card-content, [innerHtml]`.
* `@media (prefers-reduced-motion: reduce)` → all animations/transitions `0.01ms`, single iteration, `scroll-behavior:auto`.
* `ion-header ion-toolbar ion-menu-button:not([color]), ion-back-button:not([color]) { --color: #ffffff }` — because ~20 pages paint a gradient header; pages that want a grey icon set `color="medium"` (schedule and 5 others).
* **Track badge palette** `.track-badge` (shared by schedule/speaker/session pages): inline pill, `padding 2px 8px`, `margin-right 6px`, `border-radius 99px`, `.7rem/600`, default bg `--ion-color-medium`, white text. Per `data-track`: `talk #5833E9`, `tutorial #A6049B`, `keynote #680579`, `plenary #630675`, `break #3A3A3A`, `lightning-talks #9C3F80`, `security #F19C0B` (text `#1a1a1a`), `ai #10B57F` (dark text), `charla #3D5F94`, `poster #D47454` (dark text), `sponsor presentation #B8860B` (dark text), `open space #6FCF97` (dark text). Modifiers: `.new-badge` bg `#680579` white; `.spanish-badge` bg `#DD04D2` white; `.prereg-badge` transparent with `--ion-color-danger` text + 1 px border.
* Live-update dot on hamburger (§6).

### 8.5 Fonts & icons
* No custom fonts, no Google Fonts; Ionic defaults (`ios`: `-apple-system, BlinkMacSystemFont, "Helvetica Neue", Roboto, sans-serif`; `md`: `Roboto, "Helvetica Neue", sans-serif`). Headings weight 300 globally.
* Icons: Ionicons (SVGs copied to `/svg` by `angular.json`). Full list used in this slice: `cloud-download-outline, chevron-forward, construct-outline, shield-checkmark-outline, checkbox-outline, shirt-outline, qr-code, qr-code-outline, calendar-outline, people-outline, star-outline, pin-outline, newspaper, mic-outline, hardware-chip-outline, chatbubbles-outline, flash-outline, book-outline, easel-outline, briefcase-outline, people-circle-outline, rocket-outline, business-outline, storefront-outline, information-circle-outline, wifi-outline, location-outline, pricetags-outline, logo-python, map-outline, help-circle-outline, person, log-in, notifications-outline, log-out-outline, contrast-outline, people, map, calendar, radio, scan, arrow-forward, code-outline, trash-outline, refresh-outline, nuclear-outline, analytics-outline, close, exclamation, alert`.
* Brand colours seen in this slice: purple `#680579` (splash/tutorial/keynote), magenta `#DD04D2` (active tab, Spanish badge), tutorial button text `#101136`, PWA/meta blue `#387ef5`.

### 8.6 Complexity: **4/5** — four complete palettes with platform-specific dark variants, step ramps, and HC structural overrides that touch every component type.

---

## 9. Shared logic in this slice

### 9.1 Environments (`src/environments`)
| file | `name` | `production` | `baseUrl` | `storageKey` | `timezone` | `utcOffset` |
|---|---|---|---|---|---|---|
| `environment.ts` (default `ng build` without config; `ionic serve`) | `base` | `false` | `https://us.pycon.org` | `__pycon_us_mobile_base_2026` | `America/Los_Angeles` | `-7` |
| `environment.dev.ts` (`--configuration=development`, `make serve`) | `development` | `false` | `http://127.0.0.1:8000` (or `http://10.0.2.2:8000` when `Capacitor.getPlatform()==='android'`) | `__pycon_us_mobile_development_2026` | same | same |
| `environment.prod.ts` (`--configuration=production`, default for `ng build`/`serve` per `angular.json`) | `production` | `true` | `https://us.pycon.org` | `__pycon_us_mobile_2026` | same | same |

`storageKey` is the Ionic Storage database name (localforage: IndexedDB → WebSQL → localStorage; no SQLite driver configured). Switching environment therefore switches to a *different* persisted store.

### 9.2 Endpoints touched from the shell
* `GET {baseUrl}/2026/schedule/conference.json` — 10 s timeout; cached under `schedule-cache` (raw JSON, stored on every successful processData).
* `GET {baseUrl}/2026/api/v1/user/check_features/` — 2 s timeout; response `features: { lead_retrieval, door_check_in, mask_violation, is_speaker }`.
* `GET {baseUrl}/2026/api/v1/user/mobile_state/` — 2 s; `favorites`.
* `PATCH {baseUrl}/2026/api/v1/user/mobile_state/` — favorites sync (via UserData).
* `POST {baseUrl}/2026/api/v1/authenticate/` — login page (dispatches `user:login`).
* FCM topics: `emergency`, `announcements`, `schedule-changes`, `daily-digest`.

### 9.3 Storage keys read/written by this slice
`ion_did_tutorial`, `theme` (+ legacy `darkTheme`, legacy value `'high-contrast'`), `hasLoggedIn`, `nickname`, `hasLeadRetrieval`, `hasDoorCheck`, `hasMaskViolation`, `schedule-cache`, `notification_prefs` (object of 6 booleans, defaults all `true`), Dev Tools: `pending-scan-*`, `synced-scan-*`, `failed-scan-*`, `pending-note-*`, `note-*`, `staff-sponsor-id`, `staff-sponsor-name`, `hasScannerConsent`, plus `storage.clear()`. Logout additionally removes `favorite_sessions`, `email`, `key`, `secret`, `isSpeaker`.

### 9.4 Global events
`window` CustomEvents `user:login` (dispatched by `UserData.login`) and `user:logout` (by `UserData.logout`). Listened to by AppComponent, TabsPage, SprintsPage, ScheduleListPage.

### 9.5 Constants / magic numbers
* Timers: 5000 ms deferred init; 300 ms (`updateLoggedInStatus`), 200 ms (`TabsPage.updateHas*`), 100 ms (first sponsor banner), 30000 ms (banner rotation), 60000 ms loader max / 1000 ms loader dismiss (live update), 500 ms before reload (nuke), 300 ms (autofill directive), 2000/2500/3000 ms toasts.
* Local-notification ids: reminders `8000–8099` (`REMINDER_ID_BASE`), test `8999`.
* Tab-active regex `/\/app\/tabs\/([^/?#]+)/`.
* Sponsor slug regex: lower-case, `\s+`→`-`, strip `[^a-z0-9-]`.
* Split-pane breakpoint: Ionic default `lg` (992 px).
* Conference dates referenced by the notifications table: Thu May 14 – Sun May 17 2026, PDT.

### 9.6 Helpers
* `AutofillDirective` (`[appAutofill]`): iOS only (`Capacitor.getPlatform()==='ios'`); 300 ms after init grabs the native `<input>` inside `ion-input` and on `change`/`input` copies the value into the Angular `NgControl` (`setValue`, `markAsDirty`) so iOS password autofill registers with reactive/template forms. Used by the login form (not in this slice).
* `ConferenceData.presentMessage(msg)`: toast 3000 ms, top, icon `exclamation`.

---

## 10. Assets referenced by this slice
| Asset | Where | Notes |
|---|---|---|
| `assets/img/splash.png` (5559×6984 PNG, 603 KB) | index.html shell, Tutorial page | purple `#680579` field with the retro "sunset + palms, blue wave, PYCON·US 2026, Long Beach" logo; also source `splash.ai` |
| `assets/img/appicon.png` (300×249) | favicon / apple-touch-icon | transparent-bg version of the logo (orange/pink sunset, blue wave, magenta outlined text) |
| `assets/icons/icon-{48,72,96,128,192,256,512}.webp` | manifest.json | declared as `image/png`, `purpose: any maskable` |
| `assets/img/person-circle-outline.png` (512²) | speaker photo fallback (`ConferenceData.resolveSpeakerPhoto`) | |
| `assets/img/pycon-us-2026-logo.svg` (51 KB), `python-logo.png`, `pypi-logo.png`, `icon-bluesky.svg`, `icon-x.svg`, `speaker-banner.png`, `speaker-background.png`, `pycon-us-2026-floorplan-nologo.jpg`, `pycon-us-2025-floorplan.png`, `floor-plans/*.jpg` | other slices | listed for completeness |
| Native: `ios/App/App/Assets.xcassets/Splash.imageset/*`, `AppIcon.appiconset`, `android/app/src/main/res/drawable*/splash.png`, `mipmap-*/ic_launcher*`, `resources/**` (cordova-res sources) | launch screens / icons | |
| Ionicons SVGs (`node_modules/ionicons/dist/ionicons/svg/*.svg` → `/svg`) | all icons | |
| Sponsor logos | remote `logo_url` (S3 `pythondotorg-assets/media/sponsor_web_logos/*.png`) | shown on white rounded chip in the banner |

PWA: `ngsw-config.json` prefetches `index.html`, `*.css`, `*.js`, `favicon.ico`; `assets/**` lazy with prefetch updates. `firebase.json` hosting rewrites everything to `/index.html`, `ngsw-worker.js` `Cache-Control: no-cache`, and a stale `Link: preload` header referencing files that no longer exist (`ica-slidebox-img-*.png`, hashed bundles).

---

## 11. Gotchas / non-obvious behaviour (things a port would silently get wrong)

1. **Launch target is not always Schedule.** `CheckTutorial` sends users with `hasLeadRetrieval` to `/app/tabs/lead-retrieval` on every launch, and the login page's `navigateRoot('/')` funnels through the same guard — so sponsor staff land on the Lead Scanner immediately after logging in.
2. **Tutorial flag key is `ion_did_tutorial`**, not `hasSeenTutorial` (the latter exists in `UserData` but is never written). Nuking storage re-shows the tutorial; logout does not.
3. **Theme is stored under `theme`** with migrations from `darkTheme:boolean` and `'high-contrast'`. Default is `light`; the OS colour scheme is ignored in-app (only the native splash follows it).
4. **Dark theme is platform-dependent** (iOS pure black `#000` surfaces, MD `#121212`/`#1e1e1e`/`#1f1f1f`); the HC themes are not. Light theme sets *no* background/text tokens (Ionic defaults white/black).
5. **HC themes change semantics, not just colours**: badges become outlined pills, secondary text becomes full-contrast, cards/toolbars/tab bars get 1 px borders, focus rings become 3 px primary. HC Dark primary is yellow with a **dark** contrast colour, so "primary" buttons have dark text.
6. **`hasApps` is a sticky OR** — once any staff flag is seen it stays true until `logout()`; the "Apps" header can remain visible after features are revoked server-side until logout.
7. **TabsPage never refreshes `hasMaskViolation` on login/logout** (only lead/door/loggedIn), unlike AppComponent. Mask-violation-only staff see the correct tab only after a restart.
8. **Scanner tab has two personalities**: with door-check or mask-violation rights it opens the Staff Tools sheet (and is highlighted only when on `lead-retrieval`); with lead-retrieval only it is a plain tab to `lead-retrieval`. Door-check staff get "Lead Scanner" even without the lead-retrieval flag (`hasLeadRetrieval || hasDoorCheck`).
9. **Active-tab highlight is derived from the URL's first segment after `/app/tabs/`**, so `expo-hall`, `tracks/*`, `rooms`, etc. light no tab, while `schedule/session/:id` keeps Schedule lit. Colour is `#DD04D2`, not the theme primary.
10. **Sponsor banner is random, not sequential**, sits *above* the tab bar, starts hidden until 100 ms after data, rotates every 30 s, and never repeats consecutively (when >1). Only sponsors with `mobile_banner: true` qualify; `level` text comes from the sponsor object, and the copy is "`{name} is a {level}` ⏎ `Sponsor of PyCon US 2026`". Tap target slug is derived from the *name*, not an id.
11. **Side-menu "selected" highlight only applies to the page groups**; staff/Dev/Account/Login/Notifications items never highlight. Both accordions start collapsed; the accordion header `color="white"` is effectively a no-op.
12. **Menu header is static "PyCon US 2026"**; "Hello, {nickname}" is a non-tappable row. Logout has no confirm and navigates to Schedule.
13. **Three separate update affordances** share one flag: top banner (everywhere, pushes content down, pulses), menu card (only when the menu is an overlay — hidden on ≥992 px split-pane), and a dot on every hamburger via a `<body>` class that is never removed.
14. **Update apply is manual** (`autoUpdateMethod: 'none'`): `sync()` downloads silently on launch/resume/schedule-visit; tapping shows "Installing the latest build..." for ~1 s and then the webview reloads into the new bundle. On web nothing happens (plugin rejects).
15. **Splash hides on the first `load()` emission**, which may be the *cached* copy — so the app can appear with stale data and silently refresh ~seconds later (lists re-render). With no cache and no network the splash can stay up ~10 s and then a toast appears.
16. **Push permission prompt is delayed 5 s** after boot and runs even on web; the foreground push toast is persistent (no duration) with an ✕ button and is suppressed when all four push categories are off.
17. **Dev Tools visibility is `!environment.production`**, so it shows for the default `base` build that points at production URLs; the route itself is always present.
18. **Environment also changes the storage DB name**, so dev/base/prod builds do not share login or preferences.
19. **`routerDirection="root"` everywhere in the menu** → no back navigation between top-level pages; only detail pages have back buttons. Each tab keeps its own stack via `ion-tabs`.
20. **Desktop/tablet ≥992 px**: menu becomes a permanent side column (split pane), hamburger buttons disappear, `ion-menu-toggle autoHide="true"` content (the update card) disappears too.
21. **Timing hacks**: nearly every flag is applied inside `setTimeout` (200/300 ms) to dodge change-detection ordering; a port that applies state synchronously will be *more* correct but may expose ordering assumptions (e.g. `fetchFeatures` writing storage after the first read).
22. **Hamburger icon colour is forced white** by a global rule unless the page sets `color="..."` — headers are mostly gradient-painted (other slices), so a plain white toolbar must opt out.
23. **`index.html` disables pinch zoom** (`user-scalable=no`, max-scale 1) and telephone auto-detection; status bar style `black-translucent` for the PWA.
24. **No i18n**; all strings hard-coded English. Year "2026" is hard-coded in the menu header, tutorial title, sponsor banner copy, routes/endpoints (`/2026/...`), storage DB names and PWA manifest.
25. **`zone-flags.ts` is orphaned** (not imported) and `config.xml` is a Cordova leftover ("MyApp"); neither affects runtime.

---

## 12. Per-page summary

| Page / component | Route | Reached via | Complexity | Native plugins |
|---|---|---|---|---|
| AppComponent shell (side menu, theme, update banner, push toast) | – (root) | always | 4 | `@capacitor/splash-screen`, `@capacitor-firebase/messaging`, `@capacitor-firebase/analytics`, `@ionic/storage-angular` |
| TabsPage (tab bar, sponsor banner, staff sheet) | `/app/tabs` | root redirect / guard | 3 | none directly (Storage via UserData) |
| TutorialPage | `/tutorial` | `''` redirect when `ion_did_tutorial` falsy | 1 | Storage |
| CheckTutorial guard | `/tutorial` canLoad | every cold start / `navigateRoot('/')` | 1 | Storage |
| LiveUpdateService (+ banner/menu card/dot) | – | boot (+5 s), resume, Schedule & About pages | 2 (UI) / hard to port semantically | `@capacitor/live-updates`, `@capacitor/app`, Ionic `LoadingController` |
| DevToolsPage | `/app/tabs/dev-tools` | side menu (non-prod) / URL | 2 | Storage, `@capacitor/local-notifications` (via NotificationsService) |
| Theming (variables.scss / global.scss) | – | – | 4 | – |
