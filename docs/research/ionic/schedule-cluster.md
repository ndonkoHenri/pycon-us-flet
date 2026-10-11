# PyCon US Mobile (Ionic 8 / Angular 17 / Capacitor 7) — Schedule cluster inventory

Source root: `/Users/ndonkohenri/PycharmProjects/flet-dev/others/pycon-us/excluded/pycon-us-mobile/src/app`

Slice covered (every `.ts`, `.html`, `.scss` read in full):

| Page / component | Files | Route(s) |
|---|---|---|
| SchedulePage | `pages/schedule/schedule.{ts,html,scss}` | `/app/tabs/schedule` (default tab; `/app/tabs` redirects here) |
| ScheduleFilterPage (modal) | `pages/schedule-filter/schedule-filter.{ts,html,scss}` | no route; `ModalController` from SchedulePage |
| ScheduleListPage ("tracks") | `pages/schedule-list/schedule-list.page.{ts,html,scss}` | `/app/tabs/tracks/:trackSlug` |
| SessionDetailPage | `pages/session-detail/session-detail.{ts,html,scss}` | `/app/tabs/schedule/session/:sessionId`, `/app/tabs/speakers/session/:sessionId`, `/app/tabs/rooms/session/:sessionId` (same module mounted 3×; all in‑app links use the schedule mount) |
| NowPage | `pages/now/now.page.{ts,html,scss}` | `/app/tabs/now` |
| SpeakerListPage | `pages/speaker-list/speaker-list.{ts,html,scss}` | `/app/tabs/speakers` |
| SpeakerDetailPage | `pages/speaker-detail/speaker-detail.{ts,html,scss}` | `/app/tabs/speakers/speaker-details/:speakerId` |
| KeynoteSpeakersPage | `pages/keynote-speakers/keynote-speakers.page.{ts,html,scss}` | `/app/tabs/keynote-speakers` |
| LightningTalksPage | `pages/lightning-talks/lightning-talks.page.{ts,html,scss}` | `/app/tabs/lightning-talks` |
| SessionTypesPage | `pages/session-types/session-types.page.{ts,html,scss}` | `/app/tabs/session-types` |
| RoomsPage | `pages/rooms/rooms.page.{ts,html,scss}` | `/app/tabs/rooms` |
| RoomDetailPage | `pages/room-detail/room-detail.page.{ts,html,scss}` | `/app/tabs/rooms/room-detail/:roomSlug` |
| SprintsPage | `pages/sprints/sprints.page.{ts,html,scss}` | `/app/tabs/sprints` |
| Pipes | `pipes/track-name.pipe.ts`, `pipes/date-ago.pipe.ts`, `pipes/session-order.pipe.ts`, `pipes/pipes.module.ts` | — |
| Sub‑components used by the slice | `location-map/*` (room‑detail), `floor-plan-modal/*` (session‑detail job fair + location‑map) | — |

How pages are reached (side menu `app.component.html`, bottom tab bar `tabs-page.html`):

* Bottom tab bar (always visible): **Speakers** (icon `people`) → `/app/tabs/speakers`; **Map** (`map`) → conference‑map (other slice); **Schedule** (`calendar`) → `/app/tabs/schedule`; **Now** (`radio`) → `/app/tabs/now`; Scanner/Login tabs (other slice). A sponsor banner `ion-tab-bar` rotates above it every 30 s (other slice).
* Side menu, section "Schedule": Schedule (`calendar-outline`), Speakers (`people-outline`), Keynote Speakers (`star-outline`), Rooms (`pin-outline`).
* Side menu accordion "Presentations" (icon `newspaper`): Talks → `/app/tabs/tracks/talks` (`mic-outline`), Keynotes → `/tracks/keynotes` (`star-outline`), AI → `/tracks/ais` (`hardware-chip-outline`), Security → `/tracks/securitys` (`shield-checkmark-outline`), Charlas → `/tracks/charlas` (`chatbubbles-outline`), Lightning Talks → `/tracks/lightning-talkss` (`flash-outline`), Tutorials → `/tracks/tutorials` (`book-outline`), Posters → `/tracks/posters` (`easel-outline`), Sponsor Presentations → `/tracks/sponsor-presentations` (`briefcase-outline`).
* Side menu "Events": Open Spaces → `/app/tabs/tracks/open-spaces` (`people-circle-outline`), Lightning Talks → `/app/tabs/lightning-talks` (`flash-outline`), Sprints → `/app/tabs/sprints` (`rocket-outline`).
* Side menu "Information" → accordion "About PyCon US": … Session Types → `/app/tabs/session-types` (`pricetags-outline`).
* Deep links: session detail / room detail / speaker detail are plain router URLs (e.g. push‑notification handlers in `app.component.ts` navigate to `/app/tabs/schedule`).

Platform/environment facts used everywhere in the slice (`src/environments/environment*.ts`):

```
baseUrl:   'https://us.pycon.org'
timezone:  'America/Los_Angeles'
utcOffset: -7                      // fixed PDT offset, used for "which day is today" math
storageKey: '__pycon_us_mobile_2026' (prod) / '__pycon_us_mobile_base_2026' (dev)  (Ionic Storage DB name, set elsewhere)
```

---

## 0. Data model these pages consume (ConferenceData.processData output)

The provider (`providers/conference-data.ts`) is another agent's slice, but every page here renders its *derived* objects, so the shape and the semantics of the query helpers are documented here precisely. Raw feed: `GET https://us.pycon.org/2026/schedule/conference.json` (10 s timeout; raw JSON cached in Ionic Storage key `schedule-cache`; `load()` emits the cached copy first, then the fresh one; `data` is memoised in memory for the app lifetime; `invalidateCache()` clears both). Raw feed facts (2026 local copy): top keys `conference{content,sponsors}`, `schedule[728]`, `open-spaces[123]`, `job-listings[13]`, `sprints[24]`, `posters[25]`. `schedule[]` kinds: `available-open-space-slot`(444) `available-open-space`(40) `talk`(61) `informational`(28) `poster`(26) `break`(23) `tutorial`(20) `sponsor-workshop`(18) `charla`(16) `plenary`(11) `ai`(9) `security`(8) `open-space`(7) `summit`(5) `keynote`(4) `lightning-talks`(4) `event`(4). Days: 2026‑05‑13 (Wed) … 2026‑05‑17 (Sun). Field types: `conf_key:int`, `list_render:bool`, `start/end` ISO strings with `-07:00`, `room` comma‑joined string + `rooms[]`, `authors[]` (names), `speakers[{id:int,name,photo:url|"",bio:html}]`, `description` HTML, `name` may be Markdown link `[Keynote — X (Pacific Ballroom - Arena)](/2026/about/…)`. No slot in the 2026 feed has a nested `sessions` array (the provider's "shared session" branch is dead for 2026).

### 0.1 Derived `session` object (what every row/detail renders)

| Field | Meaning / how produced |
|---|---|
| `id` | `conf_key` (int) for schedule slots; `conf_key + 9000` (int) for open spaces; string `"<kind>-<room>-<startISO>"` for collapsed Posters/Break/Lunch rows; string `"poster-detail-<conf_key>"` for synthetic per‑poster sessions. Favorites store `String(id)`. |
| `name` | Markdown → text (`markdown-to-txt`), then: `", pre-registration"` suffix removed; for kinds `plenary/keynote/lightning-talks/event` a trailing `(Room)` is stripped and a leading `Keynote — ` / `Plenary: ` style track prefix removed; `, En Español` removed; collapsed poster rows named `Posters`; `Break` rows on Fri/Sat/Sun between 12:00–13:59 renamed `Lunch`; parenthesised room suffix stripped from break names. |
| `track` | `kind` with first letter upper‑cased: `Talk`, `Tutorial`, `Keynote`, `Plenary`, `Charla`, `Ai`, `Security`, `Lightning-talks`, `Poster`, `Break`, `Informational`, `Summit`, `Event`, `Sponsor Presentation` (kind `sponsor-workshop` is renamed), `Open Space`. |
| `tracks` | `[track]` (always exactly one element). Used by the exclude‑filter. |
| `preRegistered` | true when name contained `pre-registration`, or kind `tutorial`, or kind `summit` whose name does not match `/typing/i`. |
| `isSpanish` | kind `charla` or name matched `/en espa[ñn]ol/i`. (Undefined on open‑space / collapsed rows.) |
| `listRender`, `section` | raw `list_render` (bool) and `section` (`talks`, `events`, `posters`, `tutorials`, `sponsor-presentations`, `open-spaces`). Open‑space sessions force `listRender:false, section:'open-spaces'`. |
| `location` | raw comma‑joined room string (e.g. `"Room 103ABC, Room 104AB, Grand Ballroom A, Grand Ballroom B"`); for plenary kinds the `(…)` room from the title; bare `Hall AB` → `Expo Hall AB`. Informational slots: `""`. |
| `displayLocationOverride` | `'Pacific Ballroom - Arena'` for `lightning-talks`; parenthesised venue for breaks (`Coffee (Hall AB)` → `Expo Hall AB`); else null. |
| `displayLocation` | `displayLocationOverride` else first room of `roomLinks` else `location`; forced `''` for generic rows where `track==='Break' && name==='Break'`. **Timeline rows show `displayLocation`; detail shows `location`.** |
| `roomLinks` | `[{name, slug}]` one per comma‑separated room, `slug = lower, non[a-z0-9]→'-', trimmed` (e.g. `room-103abc`, `expo-hall-ab`, `grand-ballroom-a`). |
| `description` | raw HTML string (`<p>…</p>`, may include `<a href="/2026/…">`), open spaces: plain text; posters: `description_html`; collapsed rows: `""`. |
| `speakers` | array of speaker objects `{id, name, profilePic, about, sessions[], tracks[]}` (matched by *name* from `authors[]`); `speakerNames` = `authors[]` (strings). Open‑space/collapsed rows: `[]`. |
| `timeStart` / `timeEnd` | `toLocaleTimeString([], {timeZone:'America/Los_Angeles', hour:'numeric', minute:'2-digit'}).toLowerCase()` → `"9:25 am"`, `"1:30 pm"` (device‑locale `en` assumed). `timeStart` may be shifted by a display override: name exactly `Job Fair & Community Showcase` → −30 min. Informational slots have `timeStart === timeEnd` (templates then omit the dash part). |
| `startUtc` / `endUtc` | raw ISO strings (used for sorting, Now/Next, calendar). Poster‑detail sessions copy the collapsed Posters row's values. |
| `day` | `toLocaleDateString('en-us', {timeZone, weekday:'short'})` → `Wed/Thu/Fri/Sat/Sun`. |
| `imageUrl` | open spaces only (absolute URL or `baseUrl + path`). |
| `siteUrl` | open spaces only: `https://us.pycon.org/2026/schedule/open-spaces/#OpenSpace-<conf_key>`. |
| `color` | `slotColors[kind]` (`primary/tertiary/light/medium`) — **not used by any template in this slice.** |
| `hide`, `favorite` | **mutable flags written by `filterSession()`** on the shared object (see 0.4). |

Sessions removed before processing: kinds `available-open-space*`, `open-space` (duplicated in `open-spaces[]`), "placeholder" cancelled slots (name equals kind, empty description, no speakers — 2026 feed: 1 talk, 1 ai, 1 security, 1 sponsor‑workshop), `kind==='blank'`, `name==='Slot'`, and plenary rows whose cleaned name is `Posters`. Open spaces without `start`/`end`/room are skipped.

### 0.2 `data.schedule` (day → time‑slot groups)

```
schedule: [ { date: 'YYYY-MM-DD', groups: [ { time: '9:25 am', startTime: Date, sessions: [session…], hide?: bool, dayLabel?: 'Sat' } ] } ]
```
* Day key = `new Date(start.getTime() + utcOffset*3600*1000).toISOString().slice(0,10)` (fixed −7 h, i.e. PDT calendar date).
* Group key = the `timeStart`‑style string of the *canonical* start (`"9:25 am"`); `startTime` = JS Date of the first session that created the group. **Bug to be aware of:** when the main slot loop creates a *new day*, the first group is pushed **without** `startTime` (`{time, sessions}` only). The open‑space loop (runs first, Fri/Sat/Sun only) does set it, so in 2026 only Wed/Thu's first group lacks `startTime`.
* Groups are sorted by `startTime` ascending (comparator returns 0 if either lacks `startTime`). Days are sorted by `date` string on every query.
* `days` list from `getDays()`: `[{index:'0', date:'2026-05-13', day:'Wed'}, …]` (index is a **string**; `day` = weekday short of `date+"T00:00:00.000-12:00"` in LA tz).

### 0.3 Other derived collections

* `data.sessions` — flat list of every session (incl. collapsed rows and poster‑detail synthetics).
* `data.speakers` — `{id, name, profilePic, about(html), sessions[], tracks[]}`; `profilePic` = photo URL or `assets/img/person-circle-outline.png` when empty; de‑duplicated by `id` (ints in 2026); includes poster authors and pseudo‑speakers such as `"Hosted by Abigail, Chris, Cristián, and Lorena"`; `tracks` = distinct `session.track` values of their sessions; poster authors get the individual poster session, not the collapsed `Posters` row.
* `data.tracks` — `["open-spaces", {name:'Open Space', icon}, {name:'Informational', icon}, …]` — a legacy **string** entry first, then objects in first‑appearance order (2026: Open Space, Informational, Lightning-talks, Plenary, Tutorial, Summit, Keynote, Sponsor Presentation, Event, Talk, Charla, Security, Ai, then collapsed Poster, Break). `getTracks()` returns `data.tracks.sort()` (default sort: all objects stringify to `[object Object]`, so insertion order is kept and the string sorts last).
* `data.rooms` — `[{name, slug, sessions[] (sorted by startUtc)}]` sorted by name with `{numeric:true, sensitivity:'base'}`; fan‑out: a multi‑room session appears in every listed room; sprint‑only rooms from `ROOM_LOCATIONS` (sublabel contains "Sprints") are seeded with 0 sessions.
* `data.posters` — raw posters with `speakers[].photo` resolved and `sessionId = 'poster-detail-<conf_key>'`.
* `data.sprints`, `data['job-listings']`, `data.conference{content,sponsors}`.
* Track icons (`trackIcons`, shown only in the iOS filter modal): Break `cafe-outline`, Lightning-talks `flash-outline`, Tutorial `book-outline`, Plenary `megaphone-outline`, Keynote `star-outline`, Sponsor Presentation `briefcase-outline`, Poster `easel-outline`, Talk `mic-outline`, Security `shield-checkmark-outline`, Charla `chatbubbles-outline`, Ai `hardware-chip-outline`, Open Space `people-circle-outline`, default `mic-outline`.

### 0.4 Query helpers and filter semantics (shared by Schedule, Schedule‑list, Now)

`filterSession(session, queryWords, excludeTracks, segment)` **mutates** `session.hide` and `session.favorite`:
1. Query: `queryText.toLowerCase().replace(/,|\.|-/g,' ').split(' ')` non‑empty words; a session matches if **any** word is a substring of `name`, of `description` (raw HTML), or of any `speakers[].name`. No words → match.
2. Tracks: passes if any of `session.tracks` is **not** in `excludeTracks` (exact string compare against display names like `'Open Space'`, `'Ai'`, `'Lightning-talks'`).
3. Segment: `session.favorite = user.hasFavorite(session.id)` (string compare against in‑memory `favorites[]`); when `segment==='favorites'` only favorites pass.
4. `session.hide = !(all three)`.

* `getTimeline(dayIndex, queryText, excludeTracks, segment)` → returns the **day object itself** with `shownSessions` (a *count*) and each `group.hide` set (`true` when every session in it is hidden).
* `getAllDaysTimeline(queryText, excludeTracks, segment)` → `{shownSessions, groups:[visible groups across all days, each with dayLabel]}`.
* `getSessions(queryText, excludeTracks)` → all non‑hidden sessions sorted by `startUtc` (fallback `parseTime(timeStart)`), segment `'all'`.
* `getSpeakers(queryText)` → **all** speakers (hidden ones flagged via `speaker.hide`, matched on name words only) sorted by **last name** (`name.split(' ').pop().localeCompare`).
* `getDays()`, `getRooms()`, `getRoom(slug)`, `getSprints()`, `getTracks()`, `getPosters()` as above.

Because the flags live on shared objects, **the last filter applied anywhere leaks into other pages** (e.g. Now page filters `!s.hide`; if the Schedule tab was last on "favorites", Now shows only favorites).

### 0.5 UserData facts used here (`providers/user-data.ts`)

| Item | Detail |
|---|---|
| Storage key `favorite_sessions` | `string[]` of session ids. `addFavorite/removeFavorite` re‑read storage, mutate, write, then emit `favoritesChanged$` (RxJS `Subject<void>`); when logged in also `PyConAPI.patchUserData({favorites})` → `PATCH https://us.pycon.org/2026/api/v1/user/mobile_state/` (2 s timeout, signed headers `X-API-Key`, `X-API-Signature` = sha1(secret+timestamp+method+url+body), `X-API-Timestamp`). `addFavorites(ids[])` bulk variant (used by "Favorite all"). `hasFavorite(id)` is synchronous against the in‑memory array (and kicks off an async re‑read). |
| Storage key `scheduleFilters` | `string[]` of **excluded** track display names. `getScheduleFilters()` returns `['Open Space']` (`DEFAULT_EXCLUDED_TRACKS`) when the key is null/undefined; an explicitly saved `[]` is honoured. `isCustomScheduleFilter(list)` = list differs from the default set. |
| Storage key `hasLoggedIn` | `isLoggedIn()` → `=== true`. Login/logout dispatch `window` CustomEvents `user:login` / `user:logout`; logout also removes `favorite_sessions`. |
| `fetchPreferences()` (on login/app start) | may overwrite `favorite_sessions` from server and emit `favoritesChanged$`. |

---

## 1. SchedulePage — `/app/tabs/schedule`

**Purpose.** Day‑by‑day conference timeline with search, favorites‑only toggle, track filter modal, swipe‑to‑favorite, pull‑to‑refresh, "Jump to Now" button, offline/error state.

### 1.1 UI structure

**Header** (`ion-header translucent`, toolbar `.schedule-toolbar`, zero start/end padding):
* start: `ion-menu-button color="medium"` (hamburger).
* centre: `ion-segment.day-segment` bound to `dayIndex` (string). One `ion-segment-button` per `days[]` entry, `value=day.index`, text = `day.day` (`Wed Thu Fri Sat Sun`); today's button has class `today-tab` (bold 700, accent colour). Segment style: transparent background, indicator 3 px accent, unchecked text `--ion-color-step-500` (#808080), checked = accent, 0.85 rem / 500 / no uppercase. `(ionChange)` → `updateSchedule()`.
* end (`.header-action`, grey #808080, 1.1 rem): **favorites toggle** `ion-button` icon `star` when `segment==='favorites'` else `star-outline`, `aria-label` "Show all sessions" / "Show favorites" → `toggleFavorites()`; **filter button** icon `funnel-outline` (`.filter-button`), class `filters-active` when `excludeTracks.length>0` → 7 px dot top:8 right:8 filled with accent @55 % + 2 px ring in toolbar bg; class `filters-custom` when `hasCustomFilters` → icon tinted accent and dot solid accent; `aria-label` "Filter sessions (custom filters active)" / "Filter sessions (some tracks hidden)" / "Filter sessions" → `presentFilter()`.
* Accent token `--pycon-accent`: light `#680579`, dark theme `#DD04D2`, HC‑light `#4a0072`, HC‑dark `#ffd60a`.

**Content** (`ion-content fullscreen`):
1. `ion-refresher slot=fixed` → `handleRefresh($event)`.
2. `.search-toolbar` (transparent, padding 0 8px 4px) with `ion-searchbar` `[(ngModel)]=queryText`, `(ionChange)=updateSchedule()`, `showCancelButton="focus"`, `inputmode=search`, placeholder **"Search sessions"**; 36 px tall, radius 10, bg `--ion-color-step-50` (#f2f2f2), no shadow, 0.9 rem.
3. **Empty‑state list** (`[hidden]="shownSessions !== 0"`):
   * if `segment==='favorites'` → `.empty-favorites` centred block (padding‑top 60): icon `star-outline` 48 px grey #b0b0b0; if `!hasFavoritesOnOtherDays`: `<h2>No favorites yet</h2>` + `<p>Browse the schedule and tap the ☆(star-outline inline) on sessions you're interested in to build your personal schedule.</p>`; else `<h2>No favorites on {{days[dayIndex]?.day}}</h2>` + `<p>You have favorites on other days.</p>` + clear small button **"Show favorites on other days"** → `showAllFavorites()`. Always: clear small button **"Show all sessions"** → `toggleFavorites()`. h2 1.2 rem/600, p 0.9 rem grey max‑width 280.
   * else → `ion-item` with `ion-text color=medium` **"No sessions found that match your current filters"**; and, only when `queryText` non‑empty, an item (`lines=none`, centred) containing custom `<button class="search-all-btn">`: label **"Search all days"** + icon `calendar-outline`; after an exhaustive miss (`searchedAllDays`) it is `disabled`, class `exhausted`, label **"No results on any day"** + icon `close-circle-outline`. Style: primary bg (#3880ff) white 600 1 rem, padding .75em 1.5em, radius .5em, border 1.5px rgba(56,128,255,.3), glow shadow; exhausted → medium grey bg, opacity .7.
4. **Main list** (`[hidden]="shownSessions === 0"`), `ion-list > ion-item-group` per `groups[]` (`[hidden]=group.hide`):
   * `ion-item-divider sticky` with `ion-label` text **`{{allDaysMode ? group.dayLabel : days[dayIndex]?.day}} - {{group.time}}`** → e.g. `Sat - 9:25 am`. Label class `past` if `group.startTime < currentTime`, `future` if it has a startTime, else `non` — **no CSS exists for these classes** (visual no‑op).
   * sessions iterated through `| sessionOrder` (sorts the group's array **in place** alphabetically by `track`: `Ai, Break, Charla, Event, Informational, Keynote, Lightning-talks, Open Space, Plenary, Poster, Security, Sponsor Presentation, Summit, Talk, Tutorial`).
   * **Informational row** (`session.track === 'Informational'`): `<a class="informational-notice">` full‑width centred column, bg = `color-mix(accent 8%, item bg)` (14 % when active), padding 12 16, no underline. `<h3 class="notice-title">` = icon `information-circle-outline` (accent, aria‑hidden) + name (0.95 rem 600). `<p class="notice-meta">` (0.78 rem, opacity .72): `time-outline` + `timeStart` [+ ` – timeEnd` only if different] ; if `displayLocation`: `location-outline` + `displayLocation`. Focus ring 2 px accent inset.
   * **Regular row**: `ion-item-sliding #slidingItem [attr.track]=track|lowercase [hidden]=session.hide` containing `ion-item` with routerLink (see 1.6). `ion-label`: `<h3>` = (icon `star` if `session.favorite`) + name; `<span class="track-badge" data-track="<track lowercase>">{{track | trackName}}</span>`; `<span class="track-badge spanish-badge">En Español</span>` if `isSpanish`; `<span class="track-badge prereg-badge">Pre-registration required</span>` if `preRegistered`; `<p class="session-meta">` (flex wrap, gap .75em, 0.85em, text colour): `time-outline` + `timeStart`[` – timeEnd`]; `location-outline` + `displayLocation` if present; `<p class="session-speakers">` (0.8em): `person-outline` + `speakerNames.join(', ')` if any.
   * `ion-item-options` (revealed by swiping the row left): if not favorite → `ion-item-option color="favorite"` (custom colour `#69bb7b`) text **"Favorite"** → `addFavorite(slidingItem, session)`; if favorite → `color="danger"` text **"Remove"** → `removeFavorite(slidingItem, session)`.
5. **Error state** `.error-state` (`[hidden]="hasData"`; min‑height 50vh, centred, padding 48 32): `.error-graphic` = inline SVG Python logo (two paths, gradients `#3B3EA9→#5833E9` and `#FFD779→#D47454`, 100×100, opacity .15) with `cloud-offline-outline` icon 48 px `#3B3EA9` centred over it; `<h2 class="error-title">Couldn't load schedule</h2>` (1.3 rem 700); `<p class="error-message">Check your network connection and try again. The schedule needs an internet connection to load for the first time.</p>` (0.9 rem medium, max 300); `ion-button fill=outline .error-retry-btn` icon `refresh-outline` **"Try Again"** (border/colour `#3B3EA9`, radius 12, 600) → `reloadSchedule()`. Note it is simply the third block in the content, shown together with the (empty) list until data arrives.
6. **Jump‑to‑Now** (`*ngIf="todayIndex !== null"`, `.jump-now-wrapper` absolute bottom 16 right 16 z‑100): `<button class="jump-now-btn">` pill — bg `#680579`, white, 600 0.85 rem, padding 10 18, radius 999, shadow `0 4px 16px rgba(104,5,121,.4)`, icon `time-outline` + `<span class="jump-now-label">Jump to Now</span>`. Class `collapsed` (set 3 s after `ionViewDidEnter`) animates label `max-width 120px→0`, opacity 1→0, padding → 12 (0.5 s cubic‑bezier). Click → `jumpToNow()`.

Row/track colours come from the global `.track-badge` palette (see §14). There is **no** coloured side‑stripe per track (removed; comments in SCSS explain why).

### 1.2 Interactions

| Interaction | Handler | Behaviour |
|---|---|---|
| Tap day segment | `updateSchedule()` | reloads days + timeline for `dayIndex`. |
| Type in search (each `ionChange`, no debounce) | `updateSchedule()` | same; search is per‑day. |
| Tap "Search all days" | `searchAllDays()` | for `i` in `0..days.length-1` calls `getTimeline(String(i), queryText, excludeTracks, segment)`; the first callback with `shownSessions>0` wins: sets `dayIndex=String(i)` (segment follows), displays that day's groups; if all days checked and none found → `searchedAllDays=true` (button disabled, text swaps). |
| Tap star in header | `toggleFavorites()` | `segment` toggles `'favorites'`↔`'all'`, `updateSchedule()`. When favorites view is empty for the day, `checkFavoritesOnOtherDays()` probes every other day with `getTimeline(i,'',excludeTracks,'favorites')` to decide which empty copy to show. |
| Tap "Show favorites on other days" | `showAllFavorites()` | `allDaysMode=true`; `getAllDaysTimeline(queryText, excludeTracks,'favorites')`; dividers now show `group.dayLabel`. Any later `updateSchedule()` resets `allDaysMode=false`. |
| Tap funnel | `presentFilter()` | `modalCtrl.create({component: ScheduleFilterPage, presentingElement: routerOutlet.nativeEl, componentProps:{excludedTracks}})` (iOS card‑sheet). `onWillDismiss` → if `data` (array) → `excludeTracks=data; updateSchedule()`. Dismiss without data (swipe down) → nothing. Note the prop name `excludedTracks` is not an input of the modal; the modal reads storage itself. |
| Swipe row left → "Favorite" | `addFavorite(slidingItem, session)` | `user.addFavorite(session.id)`; `slidingItem.close()`; toast `{header: "<name> was successfully added as a favorite.", duration: 3000, buttons:[{text:'Close', role:'cancel'}]}` (bottom). The `favoritesChanged$` subscription then re‑runs `updateSchedule()` (row re‑renders with star; in favorites view list changes live). |
| Swipe row left → "Remove" | `removeFavorite(...)` | mirror; toast header `"<name> was successfully removed from favorites."`. |
| Pull to refresh | `handleRefresh(ev)` | `liveUpdateService.checkForUpdate()` (Appflow `LiveUpdates.sync()` + `App.getInfo()`); `reloadSchedule(true)` → `LoadingController` `{message:'Fetching latest schedule...', duration:10000}`; on timeline result `hasData=true`, loader dismissed; refresher completed after a further 250 ms. **Does not invalidate the cache**; it relies on `load()` fetching fresh data when `this.data` is null — but `data` is memoised, so in practice a pull‑to‑refresh re‑serves memory unless something else cleared it. |
| Tap row | routerLink | see 1.6. |
| Tap "Jump to Now" | `jumpToNow()` | `currentTime=new Date()`; if `dayIndex!==todayIndex` switch to today and `updateSchedule()`; after 300 ms `scrollToCurrentTime()`. |
| Tap "Try Again" | `reloadSchedule()` | no loader. |

`scrollToCurrentTime()` (also invoked from `ionViewDidEnter` when viewing today): after 500 ms, `targetIndex` = first group whose `startTime >= now` (else last group); grabs `document.querySelectorAll('ion-item-divider')[targetIndex]` (DOM order of *all* dividers, hidden or not — groups with `hide` are still in the DOM), computes `scrollTop + rect.top - 100` and `content.scrollToPoint(0, y, 500)`.

### 1.3 Data / storage / network

* `confData.getDays(excludeTracks, segment)` (args ignored by provider), `getTimeline`, `getAllDaysTimeline`.
* `user.getScheduleFilters()` (storage `scheduleFilters`), `user.favoritesChanged$`, `user.addFavorite/removeFavorite` (storage `favorite_sessions`, PATCH mobile_state when logged in).
* Network: only via `ConferenceData.load()`; offline → cached copy; no cache + no network → provider toast "Unable to load schedule, no offline cache available" (top, 3 s) and the page keeps `hasData=false` → error state.
* No polling. Timeouts: loader 10 s, toasts 3 s, UI `setTimeout`s 3000/500/300/250 ms.

### 1.4 Lifecycle & state

* `ngOnInit`: `ios = config.get('mode')==='ios'` (unused in template); `user.getScheduleFilters().then(f => excludeTracks = f)` (**async; races with the first `getDays/reloadSchedule`, so the very first render may ignore the stored filter until `ionViewWillEnter` re‑runs `updateSchedule()`**); subscribe `favoritesChanged$` → `updateSchedule(); detectChanges()`; `currentTime = new Date()`; `dayIndex="0"`; `getDays()` → compute `todayISO = new Date(now + utcOffset h).toISOString().slice(0,10)`; if a day matches, `dayIndex = todayIndex = that index` (string); then `reloadSchedule()`.
* `ionViewWillEnter`: `updateSchedule()` (so favorites toggled on the detail page are reflected when coming back).
* `ionViewDidEnter`: `detectChanges()`; `jumpBtnCollapsed=false` then `true` after 3 s; if viewing today → `scrollToCurrentTime()`.
* `ngOnDestroy`: unsubscribe.
* Fields: `hasData`, `dayIndex:'0'`, `queryText`, `segment:'all'|'favorites'`, `excludeTracks[]`, `shownSessions` (**count**, initialised to `[]`), `days[]`, `groups[]`, `currentTime`, `todayIndex|null`, `jumpBtnCollapsed`, `hasFavoritesOnOtherDays`, `allDaysMode`, `searchedAllDays`.
* Dead code: `openSocial()` (fab/social loading), `focusButton()`, `@ViewChild('search')`, `confDate`, `showSearchbar`, `ios`. Two lists share the `#scheduleList` template ref; `@ViewChild('scheduleList',{static:true})` resolves to the **empty‑state list**, so `closeSlidingItems()` is effectively a no‑op.

### 1.5 Native plugins
None directly. Pull‑to‑refresh triggers `LiveUpdateService.checkForUpdate()` → `@capacitor/live-updates` `LiveUpdates.sync()` and `@capacitor/app` `App.getInfo()` (no platform guard; on web these reject/no‑op inside the service).

### 1.6 Navigation out

* Row / notice tap: `session.listRender ? '/app/tabs/tracks/' + session.section : '/app/tabs/schedule/session/' + session.id`, with `queryParams {prevUrl:'/app/tabs/schedule'}` only for the detail case. In the 2026 feed every surviving session has `listRender=false`, so rows always open session detail.
* Funnel → filter modal (no route change).

### 1.7 Edge cases, a11y, analytics
* `aria-label`s on the two header icon buttons; `aria-hidden` on the notice icon. No analytics calls in this page.
* `days[dayIndex]?.day` relies on JS array indexing with a string index.
* `checkFavoritesOnOtherDays` and `searchAllDays` mutate shared `hide` flags for every day they probe (visible only via the Now page / other lists).

### 1.8 Complexity: **5** — many interacting modes (day/segment/search/filter/all‑days), swipe actions, programmatic scroll to current slot, offline/error states, and shared‑mutable filter semantics.

---

## 2. ScheduleFilterPage (modal) — opened from SchedulePage

**Header**: start `ion-button` **"Reset"** → `resetToDefault()` (every track checked except those in `DEFAULT_EXCLUDED_TRACKS = ['Open Space']`); title **"Filter Sessions"**; end `ion-button strong` **"Done"** → `applyFilters()`.
**Content**: `ion-list [lines]="ios ? 'inset' : 'full'"`, `ion-list-header` **"Tracks"**, then for each track `ion-item [attr.track]=name|lowercase`: (iOS only) `ion-icon slot=start [name]=track.icon color=medium`; `ion-label` `{{track.name | trackName}}` (short form: `AI`, `Lightning Talks`, `Sponsor Presentation`, `Open Space`, `Informational`, `Summit`, `Event`, `Break`, `Poster`…); `ion-checkbox [(ngModel)]=track.isChecked` (checked = *included*).
**Footer** (iOS only, translucent): start **"Deselect All"** → `selectAll(false)`; end **"Select All"** → `selectAll(true)`.
**MD styling**: toolbar buttons capitalised, checkbox borderless with primary checkmark, list bg inherit. **iOS**: list header margin‑top 10, labels coloured primary.

**Data**: `ionViewWillEnter`: `excluded = await userData.getScheduleFilters()`; `confData.getTracks()` → for each entry with a non‑empty `name` push `{name, icon, isChecked: excluded.indexOf(name) === -1}` (the legacy `"open-spaces"` string is dropped). `applyFilters()`: `excluded = tracks.filter(!isChecked).map(name)`; `modalCtrl.dismiss(excluded)`; `userData.setScheduleFilters(excluded)` (storage `scheduleFilters`). No cancel button; a swipe‑down dismiss returns `undefined` → caller ignores. Tracks array is only appended, never reset (safe because the modal is recreated each time).

**Complexity: 2**.

---

## 3. ScheduleListPage ("tracks") — `/app/tabs/tracks/:trackSlug`

**Purpose.** Flat list of all sessions of one track across all days (paged 25 at a time with infinite scroll), with search and "Favorite all"; a special **Open Spaces** mode renders cards with images and an external sign‑up button.

### 3.1 Slug → track resolution (`initSchedule(slug)`)
`slugify(str)` = lower, trim, strip `[^\w\s-]`, collapse `[\s_-]+`→`-`, trim dashes. For every entry of `getTracks()`: objects compare `slugify(name + 's')`, the legacy string compares `slugify('open-spaces')`. Matching entry → `trackName`; all others pushed into `excludeTracks`. Then `'Open Space'` is force‑excluded unless `slug === 'open-spaces'` (where it is force‑included). `isOpenSpaceView = slug === 'open-spaces'`. Resulting mapping: `talks→Talk`, `keynotes→Keynote`, `ais→Ai`, `securitys→Security`, `charlas→Charla`, `lightning-talkss→Lightning-talks`, `tutorials→Tutorial`, `posters→Poster`, `sponsor-presentations→Sponsor Presentation`, `open-spaces→'open-spaces'` (the string entry wins last; title pipe still renders "Open Spaces"); also reachable but unlinked: `breaks`, `plenaries`, `summits`, `events`, `informationals`. Unknown slug → everything excluded → empty list, title empty. On the open‑spaces page the result is additionally filtered to `track==='Open Space'`.

### 3.2 UI structure
**Header** (`ion-header.ion-no-border`, solid `#3B3EA9` background, white): start menu button; `ion-title` text `{{trackName | trackName:'plural'}}` (`Talks`, `Keynotes`, `Future of AI with Python`, `Trailblazing Python Security`, `Charlas`, `Lightning Talks`, `Tutorials`, `Posters`, `Sponsor Presentations`, `Open Spaces`) — opacity 0 until `showTitle` (content `scrollTop > 100`), 0.25 s fade; end: for `ai`/`security` a `<span class="track-badge new-badge toolbar-new-badge">New track!</span>` (bg `#680579`, 0.75 rem).
**Content** (`fullscreen`, `scrollEvents` → `onScroll`):
1. `.page-hero` (gradient `180deg #3B3EA9 23.5% → #101136 53.29%`, white, centred, padding 16 24 32): icon `chatbubbles` (open spaces) / `easel` (others) 40 px `#FFD779`; `<h1>` plural title (1.6 rem 700); `<p>` **"Browse presentations in this track"** or **"Attendee-organized sessions"** (0.9 rem, opacity .8).
2. `.search-toolbar` + `ion-searchbar` (`[(ngModel)]=sessionQueryText`, `debounce=250`, `showCancelButton=focus`, `inputmode=search`, placeholder **"Search"**, `(ionClear)`/`(ionCancel)` → `resetSessions()`, `(ionChange)` → `searchSessions()`); hidden when `isOpenSpaceView && sessions.length===0`. Same 36 px rounded style as Schedule.
3. (non‑open‑space, when `displaySessions.length>0`) block outline small button icon `star-outline` **"Favorite all {{plural title}}"** → `favoriteAll()`.
4. **Regular mode**: for each `visibleDays` (days that have sessions, ordered Mon…Sun): `ion-item-divider.day-header` (bg `--ion-color-step-150` #d7d8da, label 1.3em 600 centred) text = long day name (`Wednesday`…); `ion-list lines=full` of `ion-item.session-list-item detail=true [attr.track] [hidden]=session.hide`: `<h2 class="session-name">` (1 rem 600) = (icon `star color=warning` 0.85em if favorite) + name; `.session-badges` row: track‑badge (short pipe), spanish, prereg; `<p class="session-meta">`: `time-outline` `{{timeStart}} – {{timeEnd}}` (always with dash here), `location-outline` `displayLocation`; `.speaker-avatars` (if `speakers.length`): 28 px `ion-avatar` per speaker (`img src=profilePic alt=name`) + `.speaker-names` `speakerNames.join(', ')` (0.8 rem grey).
5. **Open‑space mode**: intro paragraph **"Open Spaces are informal, participant-driven sessions where anyone can host a discussion, demo, or collaboration on any topic."** + block outline button icon `add-circle-outline` **"Submit an Open Space"** → `submitOpenSpace()`; if `displaySessions.length===0 && !scrolling` → **"No open spaces have been posted yet. Check back closer to the conference!"**; then for each `dayOrder` day with sessions: `.day-header` label `Friday`/`Saturday`/else **"Sunday"** (only these three are mapped), `ion-grid` with `ion-col size-xs=12 size-sm/md/xl=6` per session: `ion-item.ion-no-padding lines=none` wrapping `ion-card.session-card`: header title (star icon if favorite + name), subtitle `{{timeStart}} — {{timeEnd}}: {{displayLocation || location}}`; content grid: col (8 if `imageUrl` else 12) of `ion-chip` per speaker (avatar + name) — always empty for open spaces; col 4 `img.open-space-image` (max‑h 80, cover, radius 4); row with `<a class="open-space-site-link" href=siteUrl target=_blank rel=noopener (click)=stopPropagation>` icon `open-outline` **"View on us.pycon.org"**.
6. `ion-infinite-scroll [disabled]="!scrolling"` → `onIonInfinite`.

### 3.3 Behaviour / state
* `ngOnInit`: `ios`; `userData.isLoggedIn()` → `loggedIn`; `window.addEventListener('user:login'|'user:logout')` → toggles `loggedIn` + `detectChanges()` (`loggedIn` is **not used in the template**); `route.params.subscribe` → `initSchedule(trackSlug)` (so navigating between track pages reuses the component).
* `initSchedule` → `confData.load()` → `getTracks()` → build excludes → `resetSessions()`.
* `resetSessions()`: `page=0; scrolling=true; sessionQueryText=''; sessions=[]; displaySessions=[]; sessionsByDay={}`; `reloadSessions()` → loader `{message:'Fetching latest sessions...', duration:10000}`, `getSessions(query, excludeTracks)` → `sessions`; `generateSessions()`; loader dismissed after 100 ms.
* `generateSessions()`: appends `sessions.slice(25*page, 25*page+25)` to `displaySessions`; if all shown → `page=-1; scrolling=false` else `page++; scrolling=true`; then `organizeSessionsByDay()` (buckets by `session.day`, unknown day codes kept in their own bucket; `visibleDays` sorted Mon..Sun, unknowns last alphabetically).
* `onIonInfinite(ev)`: `generateSessions()` then `ev.target.complete()` after 200 ms.
* `searchSessions()`: `scrolling=false; displaySessions=[]`; `getSessions(query, excludeTracks)` → **all** matches shown at once (no paging) and regrouped.
* `favoriteAll()`: `userData.addFavorites(displaySessions.filter(!hide && id).map(String))` then `detectChanges()`.
* `submitOpenSpace()`: `window.open('https://us.pycon.org/2026/signup/open-space/', '_system', 'location=yes')`.
* `onScroll`: `showTitle = scrollTop > 100`. `ionViewWillLeave` only `console.log('here')`.
* `@capacitor/inappbrowser` is imported but never called here. `isOpenSpaceView` guard filter comment references PYMOBIL bug history.

### 3.4 Navigation out
* Regular row → `['/app/tabs/schedule/session', session.id]` with `{prevUrl: '/app/tabs/tracks/' + trackSlug}`.
* Open‑space card → same detail route + prevUrl; the "View on us.pycon.org" anchor opens externally (`target=_blank`).
* External: open‑space sign‑up URL.

### 3.5 Notes
* "Posters" track list contains the collapsed `Posters` row **and** every synthetic `poster-detail-*` session (all with the same time), grouped under `Sunday`.
* Day headers in open‑space mode mislabel any non‑Fri/Sat/Sun day as "Sunday" (2026 open spaces are Fri 50 / Sat 48 / Sun 25 so it does not surface).
* No a11y attributes beyond `alt` on avatars; no analytics.

### 3.6 Complexity: **4**.

---

## 4. SessionDetailPage — `/app/tabs/schedule/session/:sessionId` (also mounted under `/speakers/session/…` and `/rooms/session/…`)

**Purpose.** Full detail for one session (talk, tutorial, keynote, panel, break, open space, collapsed Posters list, individual poster). Favourite toggle, add‑to‑calendar, room links, speaker links, HTML description with external‑link interception, job‑fair floor plan, keynote enrichment.

### 4.1 Load & derived flags (`ionViewWillEnter` subscribes to `route.paramMap`; `ionViewWillLeave`/`ngOnDestroy` unsubscribe)
`dataProvider.load()` → `session = data.sessions.find(String(s.id) === String(sessionId))`. Then:

| Flag | Rule |
|---|---|
| `isOpenSpace` | `track==='Open Space'` or `tracks.includes('Open Space')` |
| `isKeynote` | `tracks.includes('keynote')` or `track==='Keynote'` |
| `isPanel` (local) | name matches `/(?:diversity\s*(?:&|and)\s*inclusion\s+panel|steering\s+council\s+panel)/i` |
| `isPosters` | `track==='Poster' && name==='Posters'` (the collapsed row) → `posters = data.posters` |
| `isJobFair` | `(name + ' ' + content_override).toLowerCase()` contains `'job fair'` (`content_override` is never set by the provider) |
| `keynoteAbstract` | if `isKeynote || isPanel`: first entry of the hard‑coded `keynoteAbstracts[]` whose any `match[]` string is a case‑insensitive substring of the session name |
| `keynoteData` | if abstract has `panelists[]` → those names looked up in `keynoteSpeakers{}`; else every `keynoteSpeakers` key that is a substring of the session name |
| `isFavorite` | `userProvider.hasFavorite(String(id))` |

Hard‑coded content (verbatim in `session-detail.ts`, must be ported as data):
* `keynoteAbstracts`: Djangonaut Space (match `Djangonaut`, `Rachell Calhoun`, `Tim Schilling`; eyebrow "Joint keynote by Tim Schilling & Rachell Calhoun"; 5 paragraphs), Lin Qiao ("Your AI Product Doesn't Have a Moat… Yet", 3 paragraphs), Pablo Galindo ("Horizonte de sucesos / Event Horizon", 2 bilingual paragraphs), D&I Panel (title "D&I Panel: Python is for Everyone — Growing the Community Without Limits", eyebrow "Panel hosted by the PSF Diversity & Inclusion Workgroup", 1 paragraph, panelists Débora Azevedo, Alla Barbalat, Georgi Ker, Theresa Seyram Agbenyegah, Abhijeet Mote), Steering Council ("Python Steering Council Panel", eyebrow "Annual address from the Python Steering Council", panelists Barry Warsaw, Donghee Na, Pablo Galindo Salgado, Savannah Ostrowski, Thomas Wouters), amanda casari (no title, 1 paragraph).
* `keynoteSpeakers`: 15 entries `{photo (https://pycon-assets.s3.amazonaws.com/2026/media/images/…), bio}` for Lin Qiao, amanda casari, Tim Schilling, Rachell Calhoun, Pablo Galindo Salgado, the 5 panelists, Barry Warsaw, Donghee Na, Savannah Ostrowski, Thomas Wouters.
* After provider name‑cleaning the 2026 keynote session names are `Lin Qiao`, `Pablo Galindo Salgado`, `amanda casari`, `Rachell Calhoun & Tim Schilling`; panels are `Diversity & Inclusion Panel` and `Steering Council Panel` (kind plenary).

### 4.2 UI structure
**Header** (`ion-no-border`, `translucent=false`, solid `#3B3EA9`, all buttons white): start `ion-back-button [defaultHref]=defaultHref` (`defaultHref = queryParam prevUrl || '/app/tabs/schedule'`, set in `ionViewDidEnter`); end: `ion-button` icon `calendar-outline` → `addToCalendar()`; `ion-button` icon `star-outline` / `star` (inline `color:#fbbf24`) → `toggleFavorite()`.

**Content** (everything inside `*ngIf="session"`; nothing is rendered for an unknown id — blank page with back button):
1. `.session-hero` (gradient `#3B3EA9 23.5% → #101136 53.29%`, padding 0 20 40): `<h1 class="session-title">` name (1.5 rem 700 white); `.session-badges` (flex wrap gap 6): one `track-badge[data-track]` per `session.tracks` with `trackName:'long'` (`The Future of AI with Python`, `Trailblazing Python Security`, else short); for `ai`/`security` an extra `track-badge new-badge` **"New track!"**; `spanish-badge` **"En Español"**; `prereg-badge` **"Pre-registration required"**. Inside the hero the prereg/spanish/new badges are restyled translucent white (`rgba(255,255,255,.2)` bg, white text; prereg gets a 1 px `rgba(255,255,255,.5)` border).
2. `.session-meta-card` (white card, radius 16, padding 16 18, `margin:-20px 16px 0` overlapping the hero, shadow; dark theme bg `--ion-color-step-100`; HC bordered): `.meta-row` icon `time-outline` (#3B3EA9; dark `#8b8fd4`) + `{{day}} {{timeStart}}[ – {{timeEnd}}]`; if `session.location`: `.meta-row` icon `location-outline` + either `.room-links` (one underlined `<a class="room-link">` per `roomLinks` → `['/app/tabs/rooms/room-detail', slug]` with `{prevUrl: location.path(), session: session.id}`, comma‑separated) or plain `{{location}}`.
3. `.session-body` (padding 16 16 0):
   * `*ngIf="isJobFair"` `<button class="job-fair-floor-plan-card">` (80 px tall, bg `rgba(59,62,169,.08)`, border `rgba(59,62,169,.18)`, radius 12): thumb `assets/img/floor-plans/job-fair-thumb.jpg` 60×60 radius 8, label **"View Job Fair Floor Plan"** (600, #3B3EA9), icon `chevron-forward` → `openJobFairFloorPlan()`.
   * `.keynote-speaker-card` per `keynoteData` (photo 80×80 radius 12 + `.keynote-info` h3 name 1 rem 700 / p bio 0.85 rem medium); odd indexes get `keynote-speaker-card-flipped` (photo floats right).
   * `.session-speakers-section` (if `speakers.length`): `ion-item.speaker-item lines=none detail=true` per speaker → `['/app/tabs/speakers/speaker-details', speaker.id]` `{prevUrl: location.path()}`; `ion-avatar` 44 px (`profilePic`, alt name); label `<h2>` name (1 rem 600), `<p>` **"Speaker"** (0.8 rem grey).
   * `.session-image-container` (if `imageUrl`): `img.session-image` max‑w 100 %, max‑h 300, radius 12; open‑space variant `open-space-hero-image` max‑h 220, full width, cover.
   * If `keynoteAbstract`: `.session-description.keynote-abstract` with `<h2 class="keynote-abstract-title">` (1.15 rem 700), `<p class="keynote-abstract-eyebrow">` (0.85 rem italic medium), then one `<p>` per paragraph.
   * Else `.session-description [innerHtml]="session.description"` (0.95 rem, lh 1.65; `p` margin 0 0 12; links primary, no underline; open‑space variant `white-space: pre-line`), with `(click)="onDescriptionClick($event)"`.
   * `*ngIf="isOpenSpace && siteUrl"` `.open-space-site-link-row` `<a href=siteUrl target=_blank rel=noopener>` icon `open-outline` **"View this open space on us.pycon.org"**.
   * `*ngIf="isPosters && posters.length"` `.posters-list`: `<h2>Posters ({{posters.length}})</h2>` then `ion-item.poster-item lines=none detail button` per poster → `['/app/tabs/schedule/session', 'poster-detail-' + poster.conf_key]` `{prevUrl: location.path()}`; avatar 40 px of first speaker photo if any; label wrap `<h3>` title, `<p>` speaker names joined ", ".

### 4.3 Actions
* `toggleFavorite()`: if `hasFavorite(String(id))` → `removeFavorite`, `isFavorite=false`; else `addFavorite`, `isFavorite=true`. No toast here.
* `addToCalendar()`:
  1. Validate `startUtc`/`endUtc` parse to numbers; else toast **"Couldn't read this session's time"** (2.5 s, bottom) and stop.
  2. `description` = `Speakers: <names joined ', '>` (if any) + `\n\n` + `https://us.pycon.org/2026/schedule/presentation/<id>/`.
  3. **Hybrid (`platform.is('hybrid')`)**: `await CapacitorCalendar.requestWriteOnlyCalendarAccess()`; `await CapacitorCalendar.createEventWithPrompt({title: name, location: location || '', description, startDate: startMs, endDate: endMs, isAllDay: false, url: sessionUrl})` (`@ebarooni/capacitor-calendar` v7). On any error → fallback `shareIcs()`: `Filesystem.writeFile({path: '<slug>.ics', data: ics, directory: Directory.Cache, encoding: Encoding.UTF8})` then `Share.share({title: name, text: name, url: writeResult.uri, dialogTitle: 'Add to calendar'})`; if that throws → toast **"Couldn't open the calendar app"**.
  4. **Web/PWA**: `downloadIcs()` — `Blob([ics], {type:'text/calendar;charset=utf-8'})`, temporary `<a download="<slug>.ics">` click, revoke after 1 s.
  * ICS body (CRLF‑joined): `BEGIN:VCALENDAR`, `VERSION:2.0`, `PRODID:-//PyCon US//Mobile App//EN`, `CALSCALE:GREGORIAN`, `METHOD:PUBLISH`, `BEGIN:VEVENT`, `UID:pycon-2026-<id>@us.pycon.org`, `DTSTAMP:<nowUTC yyyymmddThhmmssZ>`, `DTSTART:`, `DTEND:`, `SUMMARY:`, `LOCATION:`, `DESCRIPTION:`, `URL:`, `END:VEVENT`, `END:VCALENDAR`. Text escaping: `\`→`\\`, newlines→`\n`, `,`→`\,`, `;`→`\;`. Filename slug: name lower, non‑alnum→`-`, trimmed, max 60 chars, default `pycon-session`.
* `onDescriptionClick(ev)`: finds closest `<a>`; `preventDefault`; `href` starting with `/` is prefixed with `https://us.pycon.org`; opens `InAppBrowser.openInWebView({url, options: DefaultWebViewOptions})` (`@capacitor/inappbrowser`) — no web fallback (on web the call is a no‑op/rejects, so description links do nothing).
* `openJobFairFloorPlan()`: `modalCtrl.create({component: FloorPlanModalComponent, componentProps:{title:'Job Fair & Community Showcase', imageSrc:'assets/img/floor-plans/job-fair.jpg', altText:'Job Fair & Community Showcase floor plan'}})`.
* `shareSession()` and `sessionClick()` only `console.log` — **there is no share button in the template**; `@capacitor/share` is used solely for the `.ics` fallback.

### 4.4 Data / plugins / platform
* Data: `ConferenceData.load()` (memoised), `UserData.hasFavorite/addFavorite/removeFavorite`, `data.posters`.
* Plugins: `@ebarooni/capacitor-calendar` (`CapacitorCalendar.requestWriteOnlyCalendarAccess`, `createEventWithPrompt`), `@capacitor/filesystem` (`Filesystem.writeFile`, `Directory.Cache`, `Encoding.UTF8`), `@capacitor/share` (`Share.share`), `@capacitor/inappbrowser` (`InAppBrowser.openInWebView`, `DefaultWebViewOptions`), Ionic `Platform.is('hybrid')`, `ToastController`, `ModalController`; floor‑plan modal uses `@ciag/ngx-pinch-zoom`.
* Platform split: calendar native prompt vs `.ics` download; everything else identical.

### 4.5 Navigation out
Back (prevUrl or schedule), room links → room detail (with `session` highlight param), speakers → speaker detail (prevUrl), posters → poster detail sessions (prevUrl), external: description links (in‑app browser), open‑space site link (`_blank`).

### 4.6 Edge cases
* Navigating poster → poster‑detail keeps the same component; the `paramMap` subscription re‑loads. `defaultHref` is only recomputed in `ionViewDidEnter`, so after an in‑place param change the back target is the *previous* prevUrl.
* Collapsed `Break`/`Lunch` rows have empty description → body is empty apart from the meta card. Informational rows reach this page too (`timeStart===timeEnd` → no dash; no location row).
* `session.location` for multi‑room plenaries shows **all** rooms as separate links (e.g. 4–7 rooms); the hero never shows `displayLocation`.
* `isFavorite` is not refreshed by `favoritesChanged$`; it is recomputed on each `loadSession`.
* Accessibility: `alt` on images; no `aria-label`s on the header icon buttons. No analytics.

### 4.7 Complexity: **5**.

---

## 5. NowPage — `/app/tabs/now` (bottom tab "Now")

**Purpose.** "Happening Now" and "Up Next" lists for today, refreshed every 60 s.

**Header** (solid `#3B3EA9`, white): menu button; `ion-title` **"Now & Next"** fades in when `scrollTop > 100`.
**Content** (`scrollEvents`): `ion-refresher` → `refresh(); $event.target.complete()` (completes immediately). `.page-hero`: icon `pulse` 40 px `#DD04D2`; `<h1>Now & Next</h1>`; `<p>What's happening at PyCon US right now</p>`.
* `noConference` → centred: icon `calendar-outline` 64 px medium; `<h2>No sessions today</h2>`; `<p>Check the schedule for upcoming conference days.</p>`.
* else: if `nowSessions.length` → `.section` with `<h2 class="section-header now-header">` (1.1 rem 700, colour `#10B57F`) icon `pulse` **"Happening Now"** + `ion-list` rows; if both lists empty → icon `moon-outline` 64 px, `<h2>Nothing happening right now</h2>`, `<p>Check back during conference hours.</p>`; if `nextSessions.length` → `<h2 class="section-header next-header">` (primary colour) icon `arrow-forward-circle` **"Up Next — {{nextTime}}"** + rows.
* Row (`ion-item [routerLink]="'/app/tabs/schedule/session/' + id" [attr.track]`): `<h3>` name; track‑badge (short pipe); spanish badge; `.session-meta`: `time-outline` `timeStart`[` – timeEnd`], `location-outline` `displayLocation || location`; `.session-speakers`: `person-outline` + names. **No prevUrl** → back from detail returns to the schedule tab root, not Now. No star/favorite indicator, no prereg badge.

**Logic (`refresh()`)**: `currentTime = new Date()`; `confData.load()`; `todayISO = currentTime.toLocaleDateString('en-CA', {timeZone: 'America/Los_Angeles'})` (DST‑correct, unlike Schedule's fixed offset); `scheduleDay = data.schedule.find(date === todayISO)`; none → `noConference=true`, lists emptied. Else `sortedGroups` = groups **with a `startTime`** sorted ascending; `currentGroup` = **last group whose `startTime <= now`** (no end‑time check — the last slot of the day stays "Happening Now" until midnight); `nowSessions = currentGroup.sessions.filter(!s.hide)`; `futureGroups` = groups with `startTime > now`; `nextTime = futureGroups[0].time`, `nextSessions = futureGroups[0].sessions.filter(!s.hide)`.
**Lifecycle**: `ngOnInit` → `refresh()` + `setInterval(refresh, 60000)`; `ionViewWillEnter` → `refresh()`; `ngOnDestroy` clears the interval (tabs keep the page alive, so the interval runs for the app lifetime once visited).
**Data**: `ConferenceData.load()` only. No plugins. Shares the mutable `hide` flags with the Schedule page (see 0.4) — sessions never filtered have `hide===undefined` and show.
**Complexity: 2**.

---

## 6. SpeakerListPage — `/app/tabs/speakers` (bottom tab "Speakers")

**Header** (solid `#3B3EA9`): menu button; title **"Speakers"** (fade on scroll > 100).
**Content** (`fullscreen`, `scrollEvents`): `.page-hero` icon `people` 40 px `#25C8EB`; `<h1>Speakers</h1>`; `<p>PyCon US 2026 presenters</p>`. `.search-toolbar` (bg page colour, margin‑top 8) `ion-searchbar` `[(ngModel)]=speakerQueryText`, `debounce=250`, `(ionClear)`/`(ionCancel)` → `resetSpeakers()`, `(ionChange)` → `searchSpeakers()`, placeholder **"Search speakers"**. `ion-list.speaker-list lines=full`: per `displaySpeakers` (`[hidden]=speaker.hide`) `ion-item button detail routerLink="/app/tabs/speakers/speaker-details/{{id}}"`: `ion-avatar slot=start` 44 px (`profilePic`, alt name); `ion-label.ion-text-wrap`: `<h2>` name (0.95 rem 600); `<p class="speaker-tracks">` one `track-badge[data-track]` per `speaker.tracks` (0.6 rem, padding 1 6) if any; `<p>` `speaker.sessions[0].name` **only when the speaker has exactly one session**. `ion-infinite-scroll [disabled]="!scrolling"`.

**Behaviour**: `ngOnInit` → `ios`; `reloadSpeakers()` → loader `{message:'Fetching latest speakers...', duration:10000}`, `getSpeakers(query)` → `speakers` (all, sorted by last name, with `hide` flags), `generateSpeakers()` (25 per page, same paging state machine as tracks; `detectChanges()` when more pages remain), loader dismissed after 100 ms. `searchSpeakers()` → `scrolling=false; displaySpeakers = getSpeakers(query)` (entire list, non‑matching rows hidden via `hide`). `resetSpeakers()` → `page=0; query=''; lists cleared; reloadSpeakers()`. `onIonInfinite` → `generateSpeakers()` then `complete()` after 200 ms. `ionViewDidEnter` empty; `focusButton()` dead.
**Data**: `ConferenceData.getSpeakers()`. No storage, no plugins. No prevUrl passed (speaker detail defaults back to `/app/tabs/speakers`).
**Complexity: 3**.

---

## 7. SpeakerDetailPage — `/app/tabs/speakers/speaker-details/:speakerId`

**Header** (`ion-no-border translucent=false`, bg `#5833E9`, white buttons): `ion-back-button [defaultHref]=backHref` (`backHref = prevUrl query param || '/app/tabs/speakers'`, set in `ionViewDidEnter`). No title.
**Content** (`.speaker-detail`):
1. `.speaker-background` (bg `#5833E9`, flex end‑aligned centred, MD/iOS shadow): `<img class="speaker-banner" src="/assets/img/speaker-banner.png">` full width; `<img class="speaker-image" [src]=profilePic [alt]=name>` absolutely positioned at the bottom, translated down 50 %, size `clamp(163px, 25vw, 300px)` circle, `border: 4px solid goldenrod`, cover.
2. `.speaker-name` (padding‑top `clamp(100px,14vw,180px)`, centred) `<h1>{{name}}</h1>`.
3. `.speaker-detail [innerHtml]="speaker?.about"` — raw HTML bio (`<p>`…); `p` margins 6 px, `hr` styled grey.
4. `.speaker-presentations`: `<h2>Presentations</h2>` + `ion-list lines=full` of `speaker.sessions`: `ion-item button detail routerLink="/app/tabs/schedule/session/{{id}}"` (no prevUrl); label `<h3>` name, `<p>` track‑badge (short pipe) + `{{day}} {{timeStart}} in {{location}}` (raw comma‑joined location).

**Data**: `ionViewWillEnter` → `dataProvider.load()` → `speaker = data.speakers.find(String(id) === speakerId)`. Unknown id → empty page with banner/default avatar. **Dead code**: `openExternalUrl()` (InAppBrowser), `openSpeakerShare()` (ActionSheet "Share <name>": Copy Link via cordova clipboard / "Share via …" / Cancel), `openContact()` (ActionSheet Email/Call) — none are referenced by the template. No plugins actually invoked.
**Complexity: 2**.

---

## 8. KeynoteSpeakersPage — `/app/tabs/keynote-speakers` (menu "Keynote Speakers")

Static content + session lookup. **Header**: menu button; title **"Keynote Speakers"** (fade > 100). **Content**: `.ks-hero` (same gradient, padding 16 24 48): icon `star` 56 px `#FFD779`; `<h1>Keynote Speakers</h1>`; `<p>PyCon US 2026</p>`.

Then `ion-card.ks-card` per `speakers[]` (margin 0 20 16, radius 16, shadow `0 8px 32px rgba(16,17,54,.15)`, content padding 24; the first card has `margin-top:-24px` overlapping the hero): centred `img.ks-speaker-photo` 120 px circle `border 3px solid #3B3EA9`; `<h2>` name (1.15 rem 700 centred); `<p>` bio; if `speaker.session`: `ion-item.ks-session-link button detail lines=none` (bg step‑50, radius 10) icon `calendar-outline color=primary`, `<h3>` session name (0.9 rem 600), `<p>` `{{day}} {{timeStart}} — {{displayLocation || location}}` → `'/app/tabs/schedule/session/' + id` (no prevUrl).
Hard‑coded `speakers[]` (name / photo URL / bio): Lin Qiao (`lin_qiao.original.jpg`), amanda casari (`amcasari-headshot.original.png`), Tim Schilling (`Tim_Schilling.original.jpg`), Rachell Calhoun (`rachell_calhoun.original.jpg`), Pablo Galindo Salgado (`Pablo_Galindo_Salgado.original.jpg`) — all under `https://pycon-assets.s3.amazonaws.com/2026/media/images/`.
`ion-card.ks-card.ks-card-council`: `<h2>Python Steering Council</h2>`; `.ks-council-grid` (flex wrap, gap 16) of 5 `.ks-council-cell` (110 px wide): `img.ks-council-photo-large` 100×100 radius 8 border 2px `#3B3EA9` + name 0.78 rem 600 (Barry Warsaw `Barry_PyCon.max-165x165.jpg`, Donghee Na `donghee_na.max-165x165.jpg`, Pablo Galindo Salgado `Pablo_Galindo_Salgado.max-165x165.jpg`, Savannah Ostrowski `savannah.max-165x165.jpg`, Thomas Wouters `Thomas_Wouters.max-165x165.jpg`); `<p>` council bio; session link item if found.
`ion-card.ks-card.ks-card-panel`: `<p class="ks-panel-eyebrow">Hosted by the PSF Diversity & Inclusion Workgroup</p>` (0.72 rem uppercase, letter‑spacing .08em); `<h2>D&I Panel: Python is for Everyone — Growing the Community Without Limits</h2>`; `<p class="ks-panel-intro">` intro; `.ks-panel-members` column (gap 14) of `.ks-panel-member` rows: `img.ks-panel-photo` 64×64 radius 6 (or `panelistFallback = 'assets/img/person-circle-outline.png'`), `<h3>` name, `<p>` bio (0.82 rem medium) — Débora Azevedo, Alla Barbalat, Georgi Ker, Theresa Seyram Agbenyegah (Stancy), Abhijeet Mote; session link item if found. Trailing 80 px spacer.

**Session lookup (`ngOnInit`, `confData.load()`)**: `keynoteSessions = sessions.filter(track==='Keynote' || tracks.includes('keynote'))`; each speaker gets the first keynote session whose lower‑cased name contains the speaker's lower‑cased name (Tim & Rachell both match the joint session). `diversityPanel.session = sessions.find(/diversity\s*(?:&|and)\s*inclusion\s+panel/i)`; `steeringCouncil.session = sessions.find(/steering\s+council/i)`. No plugins/storage. Unused SCSS classes (`.ks-council-photos`, `.ks-council-member`, `.ks-council-photo`, `.ks-council-name`) remain from an older layout.
**Complexity: 2**.

---

## 9. LightningTalksPage — `/app/tabs/lightning-talks` (menu Events → "Lightning Talks")

Fully static. **Header**: menu; title **"Lightning Talks"** (fade > 100). `.lt-hero`: icon `flash` 56 px `#FFD779`; `<h1>Lightning Talks</h1>`; `<p>5 minutes. Any topic. Your moment.</p>`.
`ion-card.lt-card` (margin `-16px 20px 16px`, radius 16, shadow, overlapping hero): `<h2>What's a Lightning Talk?</h2>`; paragraphs: "A maximum of 5 minutes on any topic of interest to other Python people. It doesn't have to be about something you wrote — it can be something you learned, or a technique you think other people will be interested in."; "You know that thing at work that everyone comes to you for help with? **Talk about that!**"; "You know that thing you just learned that helped you out? **Talk about that!**"; "You know that thing you always wish you understood, but haven't figured out yet? **Talk about that!**"; "Slides are encouraged but not required!"; `ion-button expand=block color=primary` icon `create-outline` **"Sign Up for a Lightning Talk"** → `signUp()`.
`ion-card.encourage-card` (margin 0 20, radius 16): header title **"Think you can't do one?"**; `ion-list lines=none` of 4 items (icon start, primary): `school-outline` **"Everyone already knows that"** / "No, they don't. Even if they do, it's interesting to hear your explanation."; `bulb-outline` **"I'm not an expert at anything"** / "You don't have to be an expert, just interested enough to talk for 5 minutes. You can even do 1 minute!"; `heart-outline` **"It's scary talking in front of people"** / "Folks at PyCon US are super-friendly and always welcoming of new speakers. Everyone is nervous — even people you think aren't."; `sparkles-outline` **"My idea isn't good enough"** / "It's a better idea than you think. Are there really any bad ideas for lightning talks? :)".
`ion-list lines=full` with header **"More Info"** and one `ion-item button detail` icon `globe-outline`: `<h2>Lightning Talks on pycon.org</h2>` `<p>Full details, schedule, and sign-up</p>` → `openUrl(...)`. 80 px spacer.
Both actions: `window.open('https://us.pycon.org/2026/events/lightning-talks/', '_system', 'location=yes')` (Capacitor/Cordova convention for system browser; on plain web opens a new window). No data, no storage.
**Complexity: 1**.

---

## 10. SessionTypesPage — `/app/tabs/session-types` (menu Information → About → "Session Types")

Fully static legend. **Header**: menu; title **"Session Types"** (fade > 100). `.types-hero` (gradient, centred): `.types-hero-title` row icon `pricetags` 36 px `#25C8EB` + `<h1>Session Types</h1>`; `<p>Sessions in the schedule are color-coded by type</p>`. `.types-grid` (column, gap 12, padding 20 16) of `.type-card` (row, gap 14, padding 14 16, card bg, radius 12, shadow `0 2px 8px rgba(0,0,0,.06)`): `track-badge[data-track]` + `.type-info` (`<strong>` 0.95 rem + `<p>` 0.82 rem medium):

| data-track | Badge | Strong | Description |
|---|---|---|---|
| `talk` | Talk | Standard Presentations | 30-45 minute talks on a wide range of Python topics |
| `tutorial` | Tutorial | Hands-on Sessions | 3-hour deep dives with separate registration required |
| `keynote` | Keynote | Keynote Speakers | Featured talks by invited speakers |
| `plenary` | Plenary | Full-Audience Sessions | Opening, closing, lightning talks, and community events |
| `charla` | Charla | Charlas en Español | Talks presented in Spanish |
| `lightning-talks` | Lightning Talks | Quick Fire | Short 5-minute presentations back to back |
| `ai` | AI | Future of AI with Python | Dedicated AI track — machine learning, LLMs, and more |
| `security` | Security | Trailblazing Python Security | Dedicated security track — AppSec, supply chain, and more |
| `poster` | Poster | Poster Sessions | Visual presentations and 1-on-1 discussions in the expo hall |
| `sponsor presentation` | Sponsor Presentation | Sponsor Talks | Presentations by conference sponsors |
| `open space` | Open Space | Unconference | Attendee-organized sessions — sign up on the digital board! |

80 px spacer. No data/plugins. **Complexity: 1**.

---

## 11. RoomsPage — `/app/tabs/rooms` (menu Schedule → "Rooms")

**Header**: menu; title **"Rooms"** (fade > 100). `.page-hero`: icon `map` 40 px `#4DD8E6`; `<h1>Rooms</h1>`; `<p>Browse sessions by location</p>`.
* `!rooms.length` → `.empty-state` (padding 64 24, medium): icon `pin-outline` 48 px opacity .5 + `<p>Loading rooms…</p>` (also what an empty result looks like forever).
* else `ion-list lines=none` of `ion-item.room-item button detail` (min‑height 64, padding‑start 18): icon `pin-outline color=medium` start (20 px); `<h2>` room.name (16 px 600); `<p>` `{{n}} session` / `sessions` (13 px medium) → `['/app/tabs/rooms/room-detail', room.slug]`. 60 px spacer.
**Data**: `ngOnInit` → `confData.getRooms()` (rooms sorted name‑numeric; includes sprint‑only rooms with 0 sessions and odd fan‑out rooms such as `Elsewhere`, `Lobby`, `Out Front of Hyatt Regency`). No plugins. **Complexity: 1**.

---

## 12. RoomDetailPage — `/app/tabs/rooms/room-detail/:roomSlug[?session=<id>&prevUrl=…]`

**Header**: `ion-back-button defaultHref="/app/tabs/rooms"` (the `prevUrl` query param passed by session‑detail is **ignored**; Ionic's nav stack back still works when pushed); title `{{room?.name || 'Room'}}` (fade > 100).
**Content** (`scrollEvents`):
* `loaded && !room` → `.empty-state` icon `alert-circle-outline` + **"Room not found."**
* `.page-hero` (if room): icon `pin` 40 px `#4DD8E6`; `<h1>{{room.name}}</h1>`; `<p>{{n}} session(s) scheduled</p>`.
* `.room-location-map` (padding 16 16 0, if `roomLocation`): `<app-location-map>` card (see 12.1).
* `.day-section` per `days[]` (margin‑top 24, first 16): `.day-header` pill — `margin 0 16px 12px`, padding 10 16, radius 999, bg `--pycon-accent` `#680579` (dark `#DD04D2`; HC: card bg + primary text + 1 px border), white 13 px 700 uppercase letter‑spacing .14em centred, shadow — text = short day (`Fri`). `ion-list lines=none` of `ion-item.session-item button detail` (`id="room-session-<id>"`, class `session-item-highlight` when `session.id === highlightSessionId`) → `['/app/tabs/schedule/session', id]` `{prevUrl: location.path()}`; label wrap: `<h3>` name (15 px 600); `<p class="session-time">` icon `time-outline` `timeStart`[` – timeEnd`] (12 px medium); `<p class="session-speakers">` names joined ", " (12 px); `track-badge[data-track]` with **raw `session.track`** (no pipe → shows `Lightning-talks`, `Ai`); `prereg-badge` if preRegistered. Highlight style: bg `rgba(104,5,121,.08)`, `box-shadow: inset 3px 0 0 #680579`, keyframe `room-session-pulse` 1.6 s × 2 (dark: `#DD04D2`; HC: outline 2 px primary, no animation). 60 px spacer.

**Logic**: `ngOnInit` → `combineLatest([paramMap, queryParamMap])` → `slug`, `highlightSessionId = query.get('session')` (string), `loadRoom(slug)` → `confData.getRoom(slug)` → `loaded=true; room; days = groupByDay(room.sessions)` (Map by `s.day || 'TBD'`, ordered Mon…Sun, unknown last), `roomLocation = getRoomLocation(room.name)`; if highlight → after 200 ms `document.getElementById('room-session-'+id).scrollIntoView({behavior:'smooth', block:'center'})`. `sessionRoute()` returns the same route for both branches (poster‑detail special‑case is vestigial). `ngOnDestroy` unsubscribes.
**Highlight gotcha**: `session.id === highlightSessionId` is a strict compare of **number vs string**, so the highlight style never applies for numeric ids (scroll still works because the DOM id is string‑concatenated); it only visibly highlights string ids (`poster-detail-*`, collapsed break/poster rows).

### 12.1 `app-location-map` + `FloorPlanModalComponent` (shared, used here)
`getRoomLocation(name)`: key = lower‑case, strip leading `room `, strip non‑alnum (`Room 103ABC`→`103abc`, `Expo Hall AB`→`expohallab`, `S-3`→`s3`); registry `ROOM_LOCATIONS_RAW` (~55 entries) gives `{label, sublabel, floorTitle, thumbSrc, fullSrc, pinXPct, pinYPct}` across four floor plans: Concourse Level (`floor-plan-1*.jpg`: 101A/B/AB, 102A/B/C, 103A/B/C/ABC, 104A/B/C/AB/ABC), Upper Level (`floor-plan-2*.jpg`: 201A/B, 202A/B/C, 203A/B/C, 204, Grand Ballroom A/B/combined), Arena & Exhibit Halls (`floor-plan-3*.jpg`: Pacific Ballroom — Arena, Arena, Hall A/B/C/AB, Expo Hall AB/C/combined), Seaside Meeting Rooms (`floor-plan-4*.jpg`: S‑1…S‑7 incl. A/B splits, Seaside Lobby, Seaside Ballroom A/B/combined). Pin coordinates are percentages of the image.
Card (`<button class="location-map">`, full width, card bg, 1 px border, radius 14, `aria-label="Show <label> on the <floorTitle> floor plan"`): left `.location-map-thumb` 144 px wide thumbnail with an absolutely positioned pulsing pin (8 px magenta `#DD04D2` dot with white border + 1.8 s infinite pulse ring) and a 24 px dark circular `expand-outline` zoom hint bottom‑right; right `.location-map-meta`: label (16 px 600), sublabel (13 px), floor title (12 px uppercase medium). Tap → `ModalController` with `FloorPlanModalComponent {title: floorTitle, imageSrc: fullSrc, altText, pinXPct, pinYPct, pinLabel: label}`.
Modal: header close button (icon `close-outline`, `aria-label="Close floor plan"`) + title; content = `<pinch-zoom>` (`@ciag/ngx-pinch-zoom` 13.3.0: `autoZoomOut=false`, `doubleTap`, `wheel`, `draggableImage=false`, `limitZoom='original image size'`, white bg) wrapping the full image and an optional 10 px pulsing pin at the same percentages. **Looks hard to port faithfully**: needs a pinch/double‑tap zoomable image with an overlay pin that stays anchored in image coordinates.

**Complexity: 3**.

---

## 13. SprintsPage — `/app/tabs/sprints` (menu Events → "Sprints")

**Header**: menu; title **"Sprints"** (fade > 100). `ion-refresher` → `doRefresh(ev)`. `.page-hero`: icon `rocket` 40 px `#D47454`; `<h1>Development Sprints</h1>`; `<p>Contribute to open source after the conference</p>`.
Body (`.ion-padding-horizontal`): `<p>Development Sprints are dedicated days for collaborative coding on open source projects. Join existing teams, work on your own project, or just hang out — everyone is welcome regardless of experience level.</p>`; `ion-button fill=outline expand=block` icon `open-outline` **"Visit Sprints Page"** → `openSprintsPage()`.
`.search-toolbar` (margin‑top 12, only when `allSprints.length>0`) `ion-searchbar` `[(ngModel)]=searchText`, `debounce=250`, `showCancelButton=focus`, placeholder **"Search"**, `(ionClear)`/`(ionCancel)` → `resetSearch()`, `(ionChange)` → `filterSprints()`.
`ion-grid`: row with `ion-button fill=outline expand=block` icon `add-circle-outline` **"Submit a Sprint Project"** → `submitSprint()`; if `allSprints.length===0` → `<p>No sprint projects have been posted yet. Check back closer to the conference!</p>`; row of `ion-col size-xs=12 size-sm/md/xl=6` per `sprints[]`: `ion-card.sprint-card` (cursor pointer, not clickable): header `ion-card-title` name (1.1 rem 600), `ion-card-subtitle` submitter if any; content grid: col (8 if `logo_url` else 12) `<div [innerHtml]="description_html">`, col 4 `img.sprint-logo` (max‑h 80, contain, radius 8, alt "<name> logo"); if `url`: `ion-button fill=outline size=small [href]=url target=_blank` icon `open-outline` **"Project Page"**. Trailing row with four `<br>`.

**Logic**: `loadSprints()` → `getSprints()`; keeps previous list if the new one is empty and the old one wasn't. `doRefresh` → `confData.invalidateCache()` (clears memory + `schedule-cache`) → `getSprints()` → complete refresher on `complete`. `filterSprints()`: words = `searchText.toLowerCase().replace(/,|\.|-/g,' ').split(' ')`; keep sprints where **every** word is a substring of `"<name> <submitter> <description_html>"` (HTML tags included in the haystack). `resetSearch()` → `searchText=''`, show all. `submitSprint()` → `window.open('https://us.pycon.org/2026/sprints/project/submit/', '_system', 'location=yes')`; `openSprintsPage()` → `window.open('https://us.pycon.org/2026/events/dev-sprints/', '_system', 'location=yes')`. `ngOnInit` also tracks `loggedIn` via `isLoggedIn()` + `user:login`/`user:logout` window events — **unused in the template**.
Sprint record: `{id, name, url, description_html, logo_url, submitter}`.
**Complexity: 2**.

---

## 14. Shared logic in this slice

### 14.1 Pipes (`src/app/pipes/`)
* **`trackName`** (`track-name.pipe.ts`, exported by `PipesModule`, used by Schedule, Schedule‑list, Filter, Session‑detail, Now, Speaker‑list, Speaker‑detail): `transform(value, format='short')`: empty → unchanged; `format==='long'` and in `TRACK_LONG_NAMES` → `{'Ai':'The Future of AI with Python','Security':'Trailblazing Python Security'}`; `format==='plural'` and in `TRACK_PLURAL_NAMES` → `{'Ai':'Future of AI with Python','Security':'Trailblazing Python Security','Talk':'Talks','Keynote':'Keynotes','Tutorial':'Tutorials','Charla':'Charlas','Poster':'Posters','Lightning-talks':'Lightning Talks','Plenary':'Plenaries','Break':'Breaks','Sponsor Presentation':'Sponsor Presentations'}`; else `TRACK_DISPLAY_NAMES` → `{'Ai':'AI','Lightning-talks':'Lightning Talks'}`; else `value.replace(/-/g,' ')` with every word's first letter upper‑cased (`open-spaces` → `Open Spaces`). Note `'long'`/`'plural'` fall through to the short rules when no entry exists (e.g. `Open Space | trackName:'plural'` → `Open Space`).
* **`sessionOrder`** (`session-order.pipe.ts`, declared in `ScheduleModule` only): in‑place `Array.sort` by `track` string (`<`/`>` comparison). Only used in `schedule.html`.
* **`dateAgo`** (`date-ago.pipe.ts`): relative time (`just now` <10 s, `a moment ago` <60 s, then `N second(s)/minute(s)/hour(s)/day(s)/month(s)/year(s) ago` with dividers 60,60,24,30,12; null → `a long time ago`). **Not used by any page in this slice** (only by `pages/map` lead‑retrieval scans); documented for completeness.

### 14.2 Constants / enums / hard‑coded values
* `DEFAULT_EXCLUDED_TRACKS = ['Open Space']`; `isCustomScheduleFilter()` (user‑data.ts).
* Day ordering arrays `['Mon','Tue','Wed','Thu','Fri','Sat','Sun']` (schedule‑list, room‑detail) and long labels map (schedule‑list).
* Page size **25** for infinite scroll (speakers, tracks); infinite‑scroll complete delay 200 ms; loader auto‑dismiss 10 000 ms; title fade threshold `scrollTop > 100`; Now refresh 60 000 ms; jump‑button collapse 3 000 ms; scroll‑to‑now offsets 500 ms/300 ms/−100 px/500 ms animation.
* URLs: `https://us.pycon.org/2026/schedule/conference.json`; `https://us.pycon.org/2026/schedule/presentation/<id>/`; `https://us.pycon.org/2026/schedule/open-spaces/#OpenSpace-<conf_key>`; `https://us.pycon.org/2026/signup/open-space/`; `https://us.pycon.org/2026/events/lightning-talks/`; `https://us.pycon.org/2026/events/dev-sprints/`; `https://us.pycon.org/2026/sprints/project/submit/`; `PATCH https://us.pycon.org/2026/api/v1/user/mobile_state/`; keynote photos under `https://pycon-assets.s3.amazonaws.com/2026/media/images/`.
* Dates: 2026 conference days Wed 05‑13 … Sun 05‑17 (from feed, not hard‑coded); Lunch renaming applies only to `Fri/Sat/Sun` 12:00–13:59.
* Timezone handling: display times always in `America/Los_Angeles`; "today" via fixed `-7` h offset (Schedule) vs `toLocaleDateString('en-CA',{timeZone})` (Now).

### 14.3 Visual system shared by the pages
* **Branded header pattern** (every page except Schedule): `ion-header.ion-no-border` with background `linear-gradient(180deg,#3B3EA9 0%,#3B3EA9 100%)` (solid), transparent toolbar, white title/menu/back icons; `ion-title` opacity 0 → 1 (`.title-visible`) when content scrolls past 100 px; followed by a `.page-hero` block `linear-gradient(180deg, #3B3EA9 23.5%, #101136 53.29%)`, white, centred, padding 16 24 32 (hero icon 40 px; keynote/lightning use 56 px and padding‑bottom 48), `h1` 1.6 rem 700, `p` 0.9 rem opacity .8. Hero icon colours: tracks `#FFD779`, now `#DD04D2`, speakers `#25C8EB`, session‑types `#25C8EB`, rooms/room‑detail `#4DD8E6`, sprints `#D47454`, keynote/lightning `#FFD779`. Speaker detail uses solid `#5833E9` instead.
* **Global `.track-badge`** (`global.scss`): inline pill, padding 2 8, margin‑right 6, radius 99, 0.7 rem 600, lh 1.4, default white on `--ion-color-medium` (#92949c). Per `data-track` (lower‑cased track): `talk #5833E9`, `tutorial #A6049B`, `keynote #680579`, `plenary #630675`, `break #3A3A3A`, `lightning-talks #9C3F80`, `security #F19C0B` (dark text #1a1a1a), `ai #10B57F` (dark text), `charla #3D5F94`, `poster #D47454` (dark text), `sponsor presentation #B8860B` (dark text), `open space #6FCF97` (dark text). No entry for `informational`, `summit`, `event` → grey. Modifiers: `.new-badge` bg `#680579` white; `.spanish-badge` bg `#DD04D2` white; `.prereg-badge` transparent, danger text + 1 px danger border (`#eb445a`). High‑contrast themes: transparent bg, text colour, 1.5 px text‑colour border for all badges.
* Theme classes on `<ion-app>`: `dark-theme`, `high-contrast-theme` (+ `high-contrast-light-theme` / `high-contrast-dark-theme`); several component SCSS files override accent colours per theme (listed per page). Ionic palette: primary `#3880ff` (dark `#428cff`, HC‑light `#4a0072`, HC‑dark `#ffd60a`), danger `#eb445a`, medium `#92949c`, warning `#ffc409`, custom `favorite #69bb7b`.
* **Row meta pattern** (schedule, now, tracks): `.session-meta` flex‑wrap gap .75em 0.85em with `time-outline`/`location-outline` icons; `.session-speakers` 0.8em with `person-outline`.
* `*[hidden] {display:none !important}` (app.scss) backs all `[hidden]` bindings.
* `ion-content p/h*/ion-label` are user‑selectable; long URLs wrap (`overflow-wrap:anywhere`).

### 14.4 Global events / cross‑page state
* `window` CustomEvents `user:login` / `user:logout` (listened to by Schedule‑list and Sprints to flip an unused `loggedIn`).
* `UserData.favoritesChanged$` (Schedule page re‑queries on every emit).
* `LiveUpdateService.needsUpdate` adds `body.has-pending-update` → blue dot on every `ion-menu-button` (global CSS); not page‑specific.
* Shared mutable `session.hide/favorite` and `group.hide` flags across Schedule / Schedule‑list / Now.

## 15. Assets referenced by this slice
* `assets/img/person-circle-outline.png` — default avatar (provider + keynote panel fallback).
* `assets/img/speaker-banner.png` — speaker detail banner (referenced as `/assets/img/speaker-banner.png`).
* `assets/img/floor-plans/floor-plan-{1,2,3,4}.jpg` + `-thumb.jpg` — Concourse, Upper, Arena & Exhibit Halls, Seaside (room‑detail map card/modal).
* `assets/img/floor-plans/job-fair.jpg`, `job-fair-thumb.jpg` — session detail job‑fair card/modal.
* Inline SVG Python logo in `schedule.html` error state (gradients `#3B3EA9→#5833E9`, `#FFD779→#D47454`).
* Remote: speaker photos (`https://pycon-assets.s3.amazonaws.com/2026/media/speaker_photos/<id>.webp.256x256_q85.jpg`), keynote/council/panel photos (`…/media/images/*.jpg|png`), open‑space images (`…/media/open_spaces_images/*`), sprint logos (`…/media/sprint_project_logos/*`).
* Ionicons used: `calendar`, `calendar-outline`, `star`, `star-outline`, `funnel-outline`, `time-outline`, `location-outline`, `person-outline`, `information-circle-outline`, `cloud-offline-outline`, `refresh-outline`, `close-circle-outline`, `chatbubbles`, `easel`, `add-circle-outline`, `open-outline`, `pulse`, `arrow-forward-circle`, `moon-outline`, `people`, `map`, `pin`, `pin-outline`, `alert-circle-outline`, `rocket`, `flash`, `create-outline`, `school-outline`, `bulb-outline`, `heart-outline`, `sparkles-outline`, `globe-outline`, `pricetags`, `chevron-forward`, `close-outline`, `expand-outline`, plus the filter‑modal track icons listed in §0.3.

## 16. Gotchas / non‑obvious behaviour (things a port would silently get wrong)
1. **Filter flags are shared mutable state.** `filterSession()` writes `hide`/`favorite` onto the singleton session objects; Now page and track lists read them. Reproduce by filtering immutably *per view* — do not try to reproduce the leak.
2. **`shownSessions` is a count**, initialised to `[]`; the lists' `[hidden]` expressions compare it with `0`.
3. **Day index is a string** (`'0'…'4'`); the segment and `days[dayIndex]` depend on string/number coercion.
4. **"Today" computed two different ways**: Schedule uses a fixed −7 h offset on the UTC epoch; Now uses `Intl` with the LA timezone. Outside PDT they can disagree. All time strings are LA‑local regardless of device zone, lower‑case `am/pm`, no leading zero, `toLocaleString` for `timeEnd` gives identical formatting.
5. **First group of a day created by the main loop has no `startTime`** (only Wed/Thu in 2026): it is skipped by jump‑to‑now and by Now/Next, and its divider gets class `non`.
6. **Divider classes `past/future/non` and `[attr.track]` have no CSS** — purely vestigial; `session.color` is unused.
7. **`sessionOrder` sorts within a slot by track name, not by room/title** and mutates the group array in place.
8. **Informational slots** render as a distinct tinted notice row on the Schedule page only; elsewhere they look like grey‑badge sessions. They have `location:''`, `timeStart===timeEnd`, and are *not* collapsed, so `Registration Desk Opens` appears on each day.
9. **Collapsed rows**: all 26 five‑minute `poster` slots fold into one `Posters` row (Sun 9:30 am – 1:00 pm, `Expo Hall AB`); breaks fold per name+start; lunches fold per day regardless of start (earliest start → latest end). Generic `Break` rows show **no location** although `location` lists every room.
10. **Duplicate "Job Fair" rows**: an `event` kind "Job Fair & Community Showcase & Poster Sessions" (9:30) and a plenary "Job Fair & Community Showcase" whose *display* start is shifted −30 min to 9:30 while `startUtc` stays 10:00 (so it sits in the 10:00 am group but prints 9:30 am). Both open the job‑fair floor plan card.
11. **Pre‑registration** flag is derived from name suffix / kind rules, and the suffix is stripped from the name.
12. **`listRender` routing branch** (`/app/tabs/tracks/<section>`) is dead for 2026 but present in two templates.
13. **Favorites**: ids stored as strings; `hasFavorite` is synchronous on an in‑memory array that is refreshed asynchronously; favorite toggles PATCH the server only when logged in and server prefs can overwrite local favorites on login/app start; logout wipes favorites.
14. **Filter modal returns excluded names, not included**, and saves even when identical; "Reset" means "back to app default (Open Space hidden)", not "show everything". Dismissing by swipe leaves filters untouched. The modal lists *every* track in the data including `Informational`, `Summit`, `Event`, `Break`, `Poster`.
15. **Track slugs** are `name + 's'` slugified (`ais`, `securitys`, `lightning-talkss`); the legacy `"open-spaces"` string in `data.tracks` makes the open‑spaces page title come from the fallback humaniser.
16. **"Favorite all" favourites the currently *displayed* (paged) sessions only** — on a long track list that is the first 25 (plus whatever infinite scroll has loaded), not the whole track.
17. **Search semantics differ per page**: Schedule/tracks = any word matches name/description‑HTML/speaker; Speakers = any word in name; Sprints = **all** words in name+submitter+description‑HTML. Schedule search has no debounce; others 250 ms.
18. **Room highlight never shows for numeric ids** (strict `===` between number and string); scroll‑into‑view still happens.
19. **Room links**: multi‑room plenaries list every audience room as a link; `Hall AB`→`Expo Hall AB` normalisation and `slugifyRoom` must match exactly for links to resolve; room‑detail ignores `prevUrl`.
20. **Back‑navigation contract**: session detail honours `?prevUrl=` (schedule, tracks, rooms, session→speaker→session chains); speaker list, keynote page, Now page and speaker‑detail's presentation list do **not** pass it, so "back" from those paths falls to `/app/tabs/schedule` or `/app/tabs/speakers` defaults.
21. **Keynote/panel enrichment is hard‑coded** (abstracts, bios, photos) and matched by substring on cleaned session names — brittle if titles change; the feed's own description for keynotes is just a link.
22. **Description is trusted HTML** rendered with `innerHtml` (Angular sanitises); link taps are intercepted and opened in an in‑app browser with relative URLs resolved against `us.pycon.org`. Open‑space descriptions are plain text with `pre-line`. Speaker bios and sprint descriptions are also HTML.
23. **Calendar**: native prompt (write‑only access) → `.ics` share‑sheet fallback → web `.ics` download; the event URL uses the numeric id even for synthetic ids (`poster-detail-60`, `break-…`), producing bogus URLs for those.
24. **No share button exists** despite `shareSession()`; `@capacitor/share` is only the `.ics` fallback. Speaker share/contact action sheets are dead code too.
25. **Pull‑to‑refresh on Schedule does not clear the cache**; Sprints' does (`invalidateCache()`), which also resets the schedule for every other page.
26. **Speaker identity**: speakers are linked to sessions by *name* (from `authors[]`), de‑duplicated by `id`; poster authors who also speak share ids (3 in 2026). The lightning‑talk host string is a pseudo‑speaker with the default avatar. Speaker list is sorted by last whitespace token of the name.
27. **Infinite scroll + search interplay**: typing a search replaces the paged list with the full filtered list and disables infinite scroll; clearing/cancelling re‑fetches with a blocking loader.
28. **Loaders** (`LoadingController`) are modal spinners with text, auto‑dismissing after 10 s; toasts for favorite add/remove use a `header` (bold) rather than `message`.
29. **Error state copy** on the Schedule page is only correct for a cold start without cache; with a stale cache the page silently shows old data.
30. **Theme variants** (light/dark/HC‑light/HC‑dark) change accent colours (`#680579`/`#DD04D2`/`#4a0072`/`#ffd60a`), badge rendering (bordered pills in HC), focus rings, and reduced‑motion disables the pulse animations.

## 17. Complexity summary

| Page | Complexity | Why |
|---|---|---|
| Schedule | 5 | day/segment/search/filter/all‑days modes, swipe actions, scroll‑to‑now, offline/error, shared filter flags |
| Schedule filter modal | 2 | checklist + reset/select‑all + storage |
| Schedule list (tracks) | 4 | slug→track mapping, paging + search modes, day grouping, favorite‑all, open‑space card layout + external link |
| Session detail | 5 | calendar (native/ICS/share/download), HTML description + link interception, keynote/panel enrichment, posters drill‑down, room links, floor‑plan modal, prevUrl back contract |
| Now | 2 | now/next slot math, 60 s refresh |
| Speaker list | 3 | paging + search + last‑name sort + track pills |
| Speaker detail | 2 | banner/avatar overlap layout, HTML bio, presentations list |
| Keynote speakers | 2 | static cards + regex/substring session linking |
| Lightning talks | 1 | static |
| Session types | 1 | static legend |
| Rooms | 1 | simple list |
| Room detail | 3 | day grouping, highlight/scroll, floor‑plan card + pinch‑zoom modal |
| Sprints | 2 | HTML cards, multi‑word search, refresh/invalidate, external links |
