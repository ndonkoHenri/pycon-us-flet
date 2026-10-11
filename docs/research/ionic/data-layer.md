# PyCon US mobile (Ionic/Angular) — Data-layer inventory for the Flet port

Slice covered (every line read):

| File | Lines | Role |
|---|---|---|
| `src/app/providers/conference-data.ts` | 1169 | Feed loader + cache + `processData` normaliser + all schedule/speaker/sponsor/room queries |
| `src/app/providers/pycon-api.ts` | 438 | Signed REST client for `us.pycon.org` + offline lead-retrieval queue |
| `src/app/providers/user-data.ts` | 332 | Favorites, login state, features, theme, schedule filters (Ionic Storage) |
| `src/environments/environment.ts` / `.dev.ts` / `.prod.ts` | 20 / 15 / 8 | Base URL, storage DB name, timezone constants |
| `src/app/pipes/track-name.pipe.ts`, `date-ago.pipe.ts`, `session-order.pipe.ts`, `pipes.module.ts` | 38 / 24 / 14 / 8 | Display helpers |
| `src/app/location-map/room-locations.ts`, `venue-locations.ts` | 165 / 85 | Static floor-plan pin registry |
| `src/app/location-map/location-map.component.{ts,html,scss}` | 36 / 24 / ~120 | Thumbnail-with-pin button (opens floor-plan modal) |
| Also skimmed for context (not my slice): `check-tutorial.service.ts`, `live-update.service.ts`, `notifications.service.ts` (storage key only), `login.ts`, `app.module.ts`, `app.component.ts`, `schedule-list.page.ts`, `schedule-filter.ts`, `schedule.ts`, `now.page.ts`, `map.ts`, `door-check.page.ts` | | Needed to document storage keys, consumers of derived fields, and the auth response |

Feed analysed: local copy of `https://us.pycon.org/2026/schedule/conference.json` (824 009 bytes) using `python3 -I` scripts kept in `scratchpad/analysis/` (`feed_overview.py`, `feed_schedule.py`, `feed_other.py`, `feed_misc.py`, `simulate_process.py`; full simulation output in `scratchpad/analysis/simulation_output.txt`).

Conventions below: "slot" = raw record in `conference.json#/schedule`; "session" = processed object in `data.sessions`; "PDT" = `America/Los_Angeles` during the conference (UTC-7).

---

## 1. Environments (`src/environments/*`)

Angular `fileReplacements` (angular.json): the `production` build swaps `environment.ts` → `environment.prod.ts`; the `development` configuration swaps it → `environment.dev.ts`. Plain `ng serve`/default uses `environment.ts`.

| Field | `environment.ts` (default/"base") | `environment.dev.ts` | `environment.prod.ts` |
|---|---|---|---|
| `name` | `'base'` | `'development'` | `'production'` |
| `production` | `false` | `false` | `true` |
| `baseUrl` | `'https://us.pycon.org'` | `` `http://${devHost}:8000` `` where `devHost = Capacitor.getPlatform() === 'android' ? '10.0.2.2' : '127.0.0.1'` | `'https://us.pycon.org'` |
| `storageKey` (Ionic Storage DB name) | `'__pycon_us_mobile_base_2026'` | `'__pycon_us_mobile_development_2026'` | `'__pycon_us_mobile_2026'` |
| `timezone` | `'America/Los_Angeles'` | same | same |
| `utcOffset` | `-7` (hours, hard-coded PDT) | same | same |

Uses of `environment.*` in this slice: `baseUrl` (feed URL, API base, relative image resolution, open-space `siteUrl`), `timezone` (every `toLocale*` call), `utcOffset` (day-bucket key), `storageKey` (`IonicStorageModule.forRoot({ name: environment.storageKey })` in `app.module.ts`), `production` (service worker on/off, `isDev` flag in app component).

Other hard-coded year/paths: every path contains `/2026/` literally (feed, API, site deep links). No `@ionic/storage` SQLite driver is installed, so Ionic Storage falls back to localforage (IndexedDB → WebSQL → localStorage) on both web and Capacitor; values are JSON-serialisable objects stored by key.

---

## 2. Persistent storage — complete key inventory

All through `@ionic/storage-angular` `Storage` (`storage.create()` is called in every provider constructor). Keys are flat strings. Where a key is prefixed (`pending-scan-<code>`), `<code>` is the attendee access code scanned from a badge.

| Key | Value shape | Written by | Read by | Cleared on logout? |
|---|---|---|---|---|
| `schedule-cache` | raw `conference.json` object (unprocessed) | `ConferenceData.processData` (every call) | `ConferenceData.load` | no (only `invalidateCache()`) |
| `favorite_sessions` | `string[]` of session ids (always `String(id)`) | `UserData.addFavorite/addFavorites/removeFavorite/fetchPreferences` | `UserData` constructor, `hasFavorite`, add/remove | **yes** |
| `hasLoggedIn` | `true` | `UserData.login` | `UserData.isLoggedIn` (`=== true`) | yes (removed) |
| `email` | string | `UserData.setEmail` (from auth response) | `getEmail`, about-pycon page | yes |
| `nickname` | string | `setNickname` | `getNickname` | yes |
| `key` | API key string | `setAuthKey` | `PyConAPI.buildRequestAuthHeaders`, about-pycon | yes |
| `secret` | API secret string | `setSecret` | `PyConAPI.buildRequestAuthHeaders`, about-pycon | yes |
| `hasLeadRetrieval` | boolean (may be `undefined` if feature absent) | `setHasLeadRetrieval` (login + `fetchFeatures`) | `checkHasLeadRetrieval`, `CheckTutorial.canLoad`, app/tabs pages | yes |
| `hasDoorCheck` | boolean | `setHasDoorCheck` | `checkHasDoorCheck` | yes |
| `hasMaskViolation` | boolean | `setHasMaskViolation` | `checkHasMaskViolation` | yes |
| `isSpeaker` | boolean | `setIsSpeaker` (login only) | `checkIsSpeaker` | yes |
| `hasScannerConsent` | boolean | `setScannerConsent` | `checkScannerConsent` (`=== true`) | yes |
| `hasSeenTutorial` | (never written) | — | `checkHasSeenTutorial` (dead: no callers) | — |
| `ion_did_tutorial` | boolean | tutorial page (`true`), app component `openTutorial()` (`false`) | `CheckTutorial.canLoad` | no |
| `theme` | `'light' \| 'dark' \| 'high-contrast-light' \| 'high-contrast-dark'` (legacy `'high-contrast'` migrated) | `UserData.setTheme`, `getTheme` (migration) | `getTheme` | no |
| `darkTheme` | legacy boolean | — (removed by migration) | `getTheme` | no |
| `scheduleFilters` | `string[]` of **excluded** track display names (e.g. `['Open Space']`); `[]` is a valid explicit value | `UserData.setScheduleFilters` (schedule-filter modal) | `getScheduleFilters` | no |
| `notification_prefs` | `{lightning, openSpace, emergency, announcements, scheduleChanges, dailyDigest: boolean}` | `NotificationsService` (not my slice) | same | no |
| `staff-sponsor-id` | string sponsor id | `PyConAPI.setStaffSponsorId` (map page) | `PyConAPI.syncScan/syncNote/storeScan`, map page | no (`clearStaffSponsorId` exists, unused) |
| `staff-sponsor-name` | string \| null | map page | `PyConAPI.storeScan`, map page | no |
| `staff-sponsor-logo` | string \| null | map page | map page | no |
| `pending-scan-<code>` | `{scanData: string, scannedAt: ISO string, sponsorId: string\|null, sponsorName: string\|null, tries?: number, note?: true}` | `PyConAPI.storeScan`, `syncScan` (retry count), `storeNote` (`note:true`) | `syncScan`, `storeScan`, `storeNote`, `fetchScan` | no |
| `synced-scan-<code>` | `{...serverResponse, ...pendingRecord, note?: true}` — server response includes `data: {first_name, captured, captured_date, ...}` | `PyConAPI.syncScan`, map page (simulated scans) | `syncScan`, `storeScan`, `storeNote`, `fetchScan` | no |
| `failed-scan-<code>` | same as pending (after >10 failed tries) | `syncScan` | nobody (dead-letter) | no |
| `note-<code>` | `{accessCode: string, note: string}` | `PyConAPI.storeNote` | `getNote` | no |
| `pending-note-<code>` | `{accessCode, note}` | `storeNote` | `syncNote` | no |
| `pending-door-check-<code>` | `{scanData: {productQuantities, scannedCode}, scannedAt}` | door-check page (not my slice) | door-check | no |
| `synced-door-check-<code>` | `{...redemptionResponse, ...pending}` | door-check page | door-check | no |

Dev-tools page enumerates `storage.keys()` and can remove arbitrary keys.

---

## 3. `ConferenceData` provider (`conference-data.ts`)

Injected: `HttpClient`, `UserData`, `Storage`, `ToastController`. Imports `markdownToTxt` from `markdown-to-txt` (renders markdown with `marked`, strips tags, unescapes entities — net effect used here: `[label](url)` → `label`, `**x**` → `x`, `&amp;` → `&`), and `ROOM_LOCATIONS`.

### 3.1 Constants

`slotColors` (Ionic colour name per **raw kind**; kinds not listed get `color: undefined`):

| kind | color | Ionic light value |
|---|---|---|
| `plenary` | `primary` | `#3880ff` |
| `poster` | `tertiary` | `#5260ff` |
| `event` | `light` | `#f4f5f8` |
| `summit` | `light` | |
| `break` | `light` | |
| `informational` | `medium` | `#92949c` |
| `openSpace` | `light` | (key never matches; open-space sessions hard-code `'light'`) |

`trackIcons` (ionicons name per **track display key**), `getTrackIcon(name)` falls back to `'mic-outline'`:

| Track key | Icon |
|---|---|
| `Break` | `cafe-outline` |
| `Lightning-talks` | `flash-outline` |
| `Tutorial` | `book-outline` |
| `Plenary` | `megaphone-outline` |
| `Keynote` | `star-outline` |
| `Sponsor Presentation` | `briefcase-outline` |
| `Poster` | `easel-outline` |
| `Talk` | `mic-outline` |
| `Security` | `shield-checkmark-outline` |
| `Charla` | `chatbubbles-outline` |
| `Ai` | `hardware-chip-outline` |
| `Open Space` | `people-circle-outline` |
| (`Informational`, `Summit`, `Event`, `Tutorial`…) | default `mic-outline` except Tutorial |

### 3.2 Helpers

| Method | Behaviour |
|---|---|
| `resolveSpeakerPhoto(photo)` | falsy (`null`/`''`) → `'assets/img/person-circle-outline.png'`; `^https?://` → as is; otherwise `environment.baseUrl + photo` |
| `resolveOpenSpaceImage(image)` | falsy → `null`; absolute → as is; relative → `baseUrl + image` |
| `slugifyRoom(name)` | lowercase, replace runs of `[^a-z0-9]` with `-`, trim leading/trailing `-`. `'Room 103ABC'`→`room-103abc`, `'Pacific Ballroom - Arena'`→`pacific-ballroom-arena`, `'Expo Hall AB'`→`expo-hall-ab`, `''`→`''` |
| `isPlaceholderSlot(slot)` | returns `true` (drop) when: `kind` is a string, not `poster`/`break`, `name.trim().lower() === kind.lower()`, description empty/whitespace, and both `contact` and `authors` arrays empty/missing. Catches cancelled pretalx talks whose slot stays in the feed as name `"talk"`, `"ai"`, … |
| `presentMessage(msg)` | Ionic toast: `duration: 3000`, `position: 'top'`, `icon: 'exclamation'` |
| `invalidateCache()` | `this.data = null; storage.remove('schedule-cache')` (called from 3 pull-to-refresh handlers outside this slice) |

### 3.3 `load()` — cache-then-network

```
if this.data already processed -> of(this.data)            (sync, single emission)
else Observable:
  storage.get('schedule-cache')
    .then(cached =>
       if cached: processData(cached); emit(this.data)      <- 1st emission (instant render)
       GET `${baseUrl}/2026/schedule/conference.json`  timeout 10 000 ms
         next:  this.data = null; processData(fresh); emit(this.data); complete   <- 2nd emission
         error: console.log; if this.data (cache served) -> complete
                else toast 'Unable to load schedule, no offline cache available'; observer.error(err)
    .catch(() => same GET; on error always toast + observer.error)
```

Consequences a port must reproduce: every query method is `load().pipe(map(...))`, so on cold start subscribers get **two** emissions (cached then fresh); subsequent calls get one synchronous emission. `processData` writes `schedule-cache` **every** time it runs (including when fed the cache itself). There is no TTL, ETag, or background refresh; a fresh fetch happens only when `this.data` is null (app start or after `invalidateCache()`). No request headers (no auth) on the feed.

### 3.4 `processData(raw)` — step by step

Output skeleton (`this.data`):

```
schedule:      [ {date:'YYYY-MM-DD', groups:[{time:'9:00 am', sessions:[...], startTime?:Date, hide?:bool, dayLabel?:str}], shownSessions?:int} ]
speakers:      [ Speaker ]
tracks:        [ 'open-spaces', {name, icon}, ... ]      <-- first element is a bare STRING (legacy slug, kept so /tracks/open-spaces matches)
sessions:      [ Session ]
conference:    raw.conference                              (content + sponsors, untouched)
'open-spaces': []                                          (always empty; never filled)
sprints:       raw.sprints || []
'job-listings': raw['job-listings'] || []
posters:       raw.posters with speakers[].photo resolved (+ sessionId added later)
rooms:         [ Room ]                                    (added at the end)
```

**Step 0** `storage.set('schedule-cache', raw)`.

**Step 1 — poster speakers → global speakers.** For each poster speaker not yet present by `id`: push `{id, name, profilePic: photo (already resolved), about: bio || ''}`.

**Step 2 — Open Space track registration.** If `raw['open-spaces'].length`, push `{name:'Open Space', icon:'people-circle-outline'}` (so the filter modal can re-enable it even though it is hidden by default).

**Step 3 — open-spaces loop** (runs **before** the schedule loop, so it seeds `data.schedule` days/groups first). Skip entries with missing/unparseable `start`/`end` or blank `room_display || room`. Build:

| field | value |
|---|---|
| `name` | `title` |
| `color` | `'light'` |
| `preRegistered` | `false` |
| `listRender` | `false` (deliberately, so tap → session detail) |
| `section` | `'open-spaces'` |
| `location` | `room_display` (note: guard used `room_display || room`, value uses `room_display` only) |
| `description` | raw `description` (markdown, not HTML) |
| `speakers` / `speakerNames` | `[]` / `[]` |
| `timeStart` / `timeEnd` | `start/end` formatted `h:mm am` in PDT (see 3.5) |
| `startUtc` / `endUtc` | raw ISO strings |
| `track` / `tracks` | `'Open Space'` / `['Open Space']` |
| `id` | `conf_key + 9000` (number; avoids collision with schedule `conf_key`) |
| `day` | weekday short `'Fri'` |
| `imageUrl` | `resolveOpenSpaceImage(image_url)` |
| `siteUrl` | `` `${baseUrl}/2026/schedule/open-spaces/#OpenSpace-${conf_key}` `` |

Push to `sessions`, then into `schedule[day].groups[time]` (creating day/group with `startTime: start`). No dedupe by title (feed has 5 repeated titles = recurring sessions).

**Step 4 — schedule filter** (`raw.schedule = raw.schedule.filter(...)`, mutates the raw array that was just cached by reference — harmless because the cache write already happened):
1. drop `kind.startsWith('available-open-space')` (`available-open-space`, `available-open-space-slot`) — 484 records in the live feed;
2. drop `kind === 'open-space'` (duplicates of `open-spaces[]`) — 7;
3. drop `isPlaceholderSlot(slot)` — 4 in the live feed (`sponsor-workshop` 130, `security` 34, `ai` 1136, `talk` 32);
4. for `kind === 'plenary'`: `markdownToTxt(name)`, strip trailing `(...)`, drop if `/^posters?$/i` — 1 (`[Posters (Hall AB)](/2026/schedule/posters/list/)`).

**Step 5 — collapse `poster` and `break` slots** into one row per key.
- `day = weekday short of start`; `slotName = markdownToTxt(name)`; `isLunch = /^lunch\b/i`.
- `key = \`${kind}-${day}-${slotName}${kind==='break' && !isLunch ? '-'+start : ''}\`` → all posters of a day fold into one; lunches fold per day regardless of staggered start; other breaks fold per (day, name, exact start).
- First slot of a key: `name = kind==='poster' ? 'Posters' : slotName`; if `kind==='break'` and name is exactly `Break`/`break` and day ∈ {Fri,Sat,Sun} and PDT hour ∈ [12,14) → rename `'Lunch'` (0 hits in live feed). Extract trailing `(Room)` from name into `room` and strip it from name; `^Hall\s` → prefix `Expo ` (`Hall AB` → `Expo Hall AB`, `Hall C` → `Expo Hall C`). Store `{...slot, name, room, endSlot: slot}`.
- Later slots of same key: extend `end` to the latest, `start` to the earliest; if group room empty, adopt a parenthesised room from this slot's name.

**Step 6 — main slot loop** (skips `kind==='blank'`, `name==='Slot'`, and collapse kinds; note the `else if (slot.kind === 'break')` branch inside is therefore dead code):
1. `sponsor-workshop` → `kind = 'Sponsor Presentation'`.
2. Register `slot.speakers[]` into `data.speakers` by id: `{id, name, profilePic: resolveSpeakerPhoto(photo), about: bio}`.
3. `name = markdownToTxt(name)`.
4. `preRegistered = name.includes('pre-registration') || kind==='tutorial' || (kind==='summit' && !/typing/i.test(name))`; if true `name = name.split(', pre-registration')[0]`.
5. `sessionLocation = room`, `displayLocationOverride = null`. For `kind ∈ {plenary, keynote, lightning-talks, event}`: trailing `(X)` → `sessionLocation = X` and strip from name; `lightning-talks` → `displayLocationOverride = 'Pacific Ballroom - Arena'`; `^Hall\s` → `Expo ` prefix; strip track prefix `new RegExp('^' + kind.replace(/-/g,'[- ]') + '\\s*[—:\\-–]\\s*','i')` (e.g. `Keynote — Lin Qiao` → `Lin Qiao`).
6. `isSpanish = kind==='charla' || /en espa[ñn]ol/i.test(name)`; strip `/,?\s*en espa[ñn]ol/i` from name.
7. `DISPLAY_TIME_OVERRIDES = [{match: /^\s*job\s*fair\s*&\s*community\s*showcase\s*$/i, startOffsetMinutes: -30}]` → `displayStart` used **only** for `timeStart`; grouping/sorting still use canonical `start` (live result: the Sunday "Job Fair & Community Showcase" plenary sits in the **10:00 am** group but is labelled **9:30 am**).
8. Session object:

| field | value |
|---|---|
| `name` | cleaned name |
| `color` | `slotColors[kind]` (often `undefined`) |
| `preRegistered`, `isSpanish` | as computed |
| `listRender` | raw `list_render` (all `false` after filtering) |
| `section` | raw `section` (`talks`, `tutorials`, `events`, `posters`, `sponsor-presentations`) |
| `location` | `sessionLocation` (may be comma-joined multi-room string) |
| `displayLocationOverride` | string \| null |
| `description` | raw HTML string |
| `speakers` | `[]` then filled with Speaker refs **matched by name** from `authors` |
| `speakerNames` | raw `authors` (undefined for slots without speakers) |
| `timeStart` / `timeEnd` | `h:mm am` PDT (display start / end) |
| `startUtc` / `endUtc` | raw ISO strings (with `-07:00` offset, despite the name) |
| `track` | `Cap(kind)` = first char upper-cased, rest untouched: `Talk`, `Tutorial`, `Keynote`, `Plenary`, `Lightning-talks`, `Charla`, `Ai`, `Security`, `Summit`, `Event`, `Informational`, `Sponsor Presentation` |
| `tracks` | `[track]` |
| `id` | `conf_key` (number) |
| `day` | weekday short |

9. Register track `{name: track, icon: getTrackIcon(track)}` if absent.
10. For each `speakerNames` entry, find speaker **by name** → push into `session.speakers` and `speaker.sessions`.
11. If `slot.sessions` is absent (always, in this feed) push session to `data.sessions`; else the "shared session" branch builds one session per sub-session (`{name, location: slot.room, description, speakers, speakerNames, timeStart, timeEnd, startUtc, endUtc, trackSlug: kind+'s', track, tracks, id: shared.conf_key, day}` — no `color`/`preRegistered`/`isSpanish`/`listRender`/`section`) and pushes each (the parent is not pushed).
12. Insert into `schedule[dayKey].groups[timeStart]`. **Bug to be aware of:** when this branch has to create a *new day*, the first group is created **without `startTime`** (`{"time", "sessions"}` only); only the open-space loop and the collapsed loop set it. Live effect: Wed 5/13 and Thu 5/14 "7:30 am · Registration Desk Opens" groups have no `startTime`.

**Step 7 — append collapsed rows** (posters/breaks) as sessions:
`{name, color: slotColors[kind], preRegistered:false, listRender:false, section:'', location: room, description:'', speakers:[], speakerNames:[], timeStart, timeEnd, startUtc, endUtc, track: Cap(kind) ('Break'|'Poster'), tracks:[track], id: \`${kind}-${room}-${start}\`, day}`; register track; push; insert into schedule groups (with `startTime`). Example ids: `poster-Expo Hall AB-2026-05-17T09:30:00-07:00`, `break--2026-05-13T12:30:00-07:00` (empty room).

**Step 8 — sort groups in each day** by `startTime` (comparator returns `0` when either is missing → those groups float wherever the engine's sort leaves them).

**Step 9 — synthetic poster sessions.** `collapsedPostersSession = sessions.find(track==='Poster' && name==='Posters')`. For each poster: speakers → `{id, name, profilePic: photo, about: bio||''}`; session `{name: title, color:'tertiary', preRegistered:false, listRender:false, section:'', location: collapsed?.location || 'Expo Hall AB', description: description_html, speakers, speakerNames, timeStart/timeEnd: collapsed?. || '', startUtc/endUtc: collapsed?. (may be undefined), track:'Poster', tracks:['Poster'], id: \`poster-detail-${conf_key}\`, day: collapsed?.day || 'Sun'}`; push to `sessions` (**not** into the timeline); `poster.sessionId = id`; append to each author's `speaker.sessions` (dedupe by id). The collapsed "Posters" row is deliberately not added to speakers.

**Step 10 — `speaker.tracks`**: distinct `session.track` values in encounter order (drives multi-badge pills on speaker list).

**Step 11 — rooms index.** For every session, split `location` on `,`, trim, drop blanks; per room: `slug = slugifyRoom(name)`; `roomMap[slug] = {name, slug, sessions[]}`; `session.roomLinks = [{name, slug}, …]` (unique by slug, in order). `session.displayLocation = displayLocationOverride || roomLinks[0].name || location || ''`; then if `track==='Break' && name==='Break'` → `displayLocation = ''`.

**Step 12 — seed sprint rooms** from `ROOM_LOCATIONS` entries whose `sublabel` matches `/sprints/i` (16 entries: S-1, S-2, S-3, S-3A, S-3B, S-4, S-4A, S-4B, S-5, S-5A, S-5B, S-6, Seaside Lobby, Seaside Ballroom A/B, Seaside Ballroom) so they appear in the Rooms list with 0 sessions.

**Step 13** — each room's sessions sorted by `startUtc` (missing → epoch 0); `data.rooms = rooms sorted by name.localeCompare(undefined, {numeric:true, sensitivity:'base'})`.

Returns `this.data`.

### 3.5 Time & timezone handling (every call, exact format)

| Purpose | Expression | Output example | Notes |
|---|---|---|---|
| `timeStart`, group key | `d.toLocaleTimeString([], {timeZone, hour:'numeric', minute:'2-digit'}).toLowerCase()` | `'9:00 am'`, `'12:30 pm'`, `'1:45 pm'` | **Locale `[]` = device default.** Only en-US devices yield this exact format; `parseTime` and group keys assume it. |
| `timeEnd` | `d.toLocaleString([], {timeZone, hour:'numeric', minute:'2-digit'}).toLowerCase()` | same shape | `toLocaleString` with only time parts prints only the time |
| `day` (session) / collapse day key | `d.toLocaleDateString('en-us', {timeZone, weekday:'short'})` | `'Wed'`…`'Sun'` | locale pinned |
| schedule day bucket `date` | `new Date(start.getTime() + utcOffset*3600*1000).toISOString().split('T')[0]` | `'2026-05-15'` | fixed −7 h shift (not DST-aware; correct in May) |
| `getDays` label | `new Date(day.date + 'T00:00:00.000-12:00').toLocaleDateString('en-us', {timeZone, weekday:'short'})` | `'Fri'` | 12:00Z = 05:00 PDT same date |
| `getAllDaysTimeline` `dayLabel` | same expression | | |
| lunch-rename hour | `parseInt(d.toLocaleTimeString([], {timeZone, hour12:false, hour:'numeric'}))` | `13` | device locale again |
| Display override | `new Date(start.getTime() + (-30)*60_000)` | | only affects `timeStart` |

The feed itself carries explicit `-07:00` offsets on every `start`/`end`, so parsing is unambiguous; "Utc" in `startUtc` is a misnomer (it is the raw offset string).

### 3.6 Query API (all return `Observable` via `load().pipe(map)`)

| Method | Params | Returns | Side effects / details |
|---|---|---|---|
| `getDays(excludeTracks=[], segment='all')` | both params **ignored** | `[{index:'0', date:'2026-05-13', day:'Wed'}, …]` sorted by date asc | sorts `data.schedule` in place |
| `getTimeline(dayIndex:string, queryText='', excludeTracks=[], segment='all')` | `dayIndex` is the string index into date-sorted schedule | the day object with `groups[]`; sets `day.shownSessions`, `group.hide`, `session.hide`, `session.favorite` | **mutates shared objects**; `queryText` normalised: lowercase, `/,|\.|-/g` → space, split on space, drop empties |
| `getAllDaysTimeline(queryText, excludeTracks, segment)` | | `{shownSessions, groups:[non-hidden groups across all days, each with dayLabel]}` | used by schedule "all days" mode |
| `getSessions(queryText, excludeTracks)` | | flat array of non-hidden sessions sorted by `startUtc` (fallback `parseTime(timeStart)`) | segment always `'all'`; includes poster-detail sessions |
| `filterSession(session, queryWords, excludeTracks, segment)` | | sets `session.hide`, `session.favorite` | text match = **any** word is substring of `name`, or of raw HTML `description`, or of any linked `speaker.name` (case-insensitive); tracks pass if **any** of `session.tracks` is not excluded; `segment==='favorites'` requires `user.hasFavorite(id)` |
| `parseTime('1:45 pm')` | `'h:mm am/pm'` | minutes since midnight (`12 am`→0, `12 pm`→720) | splits on `/([ap]m)/` |
| `getSponsors()` | | `data.conference.sponsors` (dict level → list) | |
| `querySponsors(queryText)` | | flat list of sponsors whose `name` matches any query word **and** `booth_number !== null` | leftover `console.log(sponsor.name)` |
| `filterSponsors(sponsor, words)` | | boolean | |
| `getContent()` | | `data.conference.content` (dict of 6 HTML strings) | |
| `getSprints()` / `getPosters()` / `getJobListings()` | | arrays | posters have `sessionId` |
| `getSpeakers(queryText)` | | **all** speakers (hidden ones flagged `speaker.hide`) sorted by last word of name (`name.split(' ').pop().localeCompare`) | sorts in place |
| `filterSpeaker` | | sets `speaker.hide` (name substring match only) | |
| `getTracks()` | | `data.tracks.sort()` — default JS sort: objects (`"[object Object]"`) keep insertion order, the bare string `'open-spaces'` sorts **last** | mutates |
| `getRooms()` | | `data.rooms` | |
| `getRoom(slug)` | | room or `undefined` | |

### 3.7 Concrete results on the live feed (from `simulate_process.py`)

- Sessions: **345** → Open Space 123, Talk 60, Informational 28, Poster 26 (1 collapsed + 25 detail), Tutorial 20, Sponsor Presentation 17, Charla 16, Break 13, Plenary 10, Ai 8, Security 7, Summit 5, Lightning-talks 4, Keynote 4, Event 4.
- Speakers: **170** (144 from slots + poster-only authors), 12 with ≥2 tracks (e.g. Trey Hunner `['Tutorial','Talk']`, Fay Shaw `['Talk','Poster']`).
- Tracks registration order: `['open-spaces', 'Open Space', 'Informational', 'Lightning-talks', 'Plenary', 'Tutorial', 'Summit', 'Keynote', 'Sponsor Presentation', 'Event', 'Talk', 'Charla', 'Ai', 'Security', 'Break', 'Poster']` (after `getTracks()` the string moves to the end).
- Days: `2026-05-13` (5 groups / 13 sessions), `05-14` (11/31), `05-15` (26/111), `05-16` (28/107), `05-17` (18/58).
- Group times — Fri: 7:30 am, 8:00, 9:00, 9:25, 9:45, 10:00, 10:30, 11:00, 11:30, 11:45, 12:00 pm, 12:30, 1:00, 1:30, 1:45, 2:00, 2:45, 3:00, 3:30, 4:00, 4:30, 5:00, 5:15, 6:00, 7:00, 8:00 pm. Sat: 7:00 am … 8:00 pm (28 groups incl. 10:05 am, 3:45 pm). Sun: 8:00 am, 9:00, 9:30, 9:45, 10:00, 11:00, 12:00 pm, 1:00, 1:45, 2:00, 2:30, 3:00, 3:15, 4:00, 4:35, 5:00, 5:05, 8:00 pm.
- Collapsed rows (14): Coffee @Expo Hall AB 8–9 am Fri/Sat/Sun; Posters @Expo Hall AB Sun 9:30 am–1:00 pm; Lunch @Expo Hall C Thu 12:30–1:30; Lunch @Expo Hall AB Fri 12:30–2:00, Sat 12:30–1:45, Sun 12:00–1:00; generic "Break" rows Wed 12:30–1:30 (room ''), Fri 10:30–11:00 & 4:00–4:30, Sat 10:05–10:30 & 3:45–4:15, Sun 10:00 am–12:00 pm (room '') — all with `displayLocation ''`.
- Keynote titles after cleaning: `amanda casari`, `Pablo Galindo Salgado` (isSpanish=true), `Lin Qiao`, `Rachell Calhoun & Tim Schilling`; location `Pacific Ballroom - Arena`.
- Rooms (38): Elsewhere 8, Expo Hall AB 35, Expo Hall C 1, Grand Ballroom A 26, Grand Ballroom B 26, Lobby 1, Out Front of Hyatt Regency 1, Pacific Ballroom - Arena 13, Room 101A 5, 101AB 1, 101B 5, 102A 23, 102B 18, 102C 22, 103ABC 26, 104AB 25, 104C 24, 201A 6, 201B 13, 202A 21, 202B 11, 202C 11, S-1 2, S-2 0, S-3 11, S-3A 0, S-3B 0, S-4 8, S-4A 0, S-4B 0, S-5 3, S-5A 0, S-5B 0, S-6 0, Seaside Ballroom 0, Seaside Ballroom A 1, Seaside Ballroom B 1, Seaside Lobby 0.
- Wednesday timeline (complete): 9:00 am → 5 Tutorials (`{P}`), 12:30 pm → Break (no location), 1:30 pm → 5 Tutorials, 6:00 pm → "Registration Desk Closes" (Informational, 0-minute), plus the 7:30 am "Registration Desk Opens" group lacking `startTime`.
- Sunday sample group (10:00 am): 4 Open Spaces, Plenary "Job Fair & Community Showcase" (labelled 9:30 am–1:00 pm), Informational "Swag Pickup Opens", Break 10:00 am–12:00 pm.

### 3.8 Consumers of derived fields (so the port knows what matters)

| Field | Used by |
|---|---|
| `session.hide`, `group.hide`, `day.shownSessions` | schedule, schedule-list, now, speaker-list, sponsors |
| `favorite` | schedule, schedule-list |
| `preRegistered` | schedule, schedule-list, room-detail, session-detail ("pre-registration required" badge) |
| `isSpanish` | schedule, schedule-list, now, session-detail |
| `displayLocation` | schedule, schedule-list, now, keynote-speakers |
| `roomLinks` | session-detail (tappable room pills → `/app/tabs/rooms/room-detail/:roomSlug`) |
| `siteUrl`, `imageUrl` | schedule-list (open-spaces view), session-detail |
| `speakerNames` | schedule, schedule-list, now, room-detail |
| `timeStart/timeEnd` | schedule, schedule-list, now, room-detail, session-detail, speaker-detail, keynote-speakers |
| `startUtc/endUtc` | session-detail (add-to-calendar `.ics`, live/upcoming state), now page (`group.startTime`) |
| `track`/`tracks` + `trackName` pipe | badges everywhere (`data-track` attr = lowercase track → CSS colour) |
| `listRender`, `section` | schedule template branching |
| `id` | routes `session/:sessionId` (schedule, speakers, rooms stacks), `speaker-details/:speakerId`, `sponsor-detail/:sponsorId`, `room-detail/:roomSlug`, `tracks/:trackSlug` |
| `poster.sessionId` | session-detail / room-detail navigation |
| `speaker.tracks` | speaker-list badge row |
| `trackSlug` | only on the (unused) shared-session branch; the `/tracks/:trackSlug` page instead matches `slugify(track.name + 's')` against the slug (`ais`, `securitys`, `lightning-talkss`, `sponsor-presentations`, `open-spaces`) |

Provider call counts across pages: `getSponsors` 7, `load` 4, `getTimeline` 4, `getContent` 4, `invalidateCache` 3, `getSpeakers` 3, `getSessions` 3, `getDays` 3, `getTracks` 2, `getSprints` 2, `getJobListings` 2, `getRooms` 1, `getRoom` 1, `getAllDaysTimeline` 1. `querySponsors` has no page caller (dead).

---

## 4. `PyConAPI` provider (`pycon-api.ts`)

`base = environment.baseUrl`. Injected `HttpClient`, `Storage`. Uses `createHash` from `sha1-uint8array` and `Network` from `@capacitor/network`.

### 4.1 Request signing (`buildRequestAuthHeaders(method, url, body)`)

```
apiKey    = storage.get('key')
secret    = storage.get('secret')
timestamp = Math.round(Date.now() / 1000)                      # integer seconds
baseString = secret + timestamp + method + url + body         # plain string concatenation, no separators
headers = {
  'X-API-Key':       apiKey,
  'X-API-Signature': sha1_hex(utf8(baseString)),
  'X-API-Timestamp': String(timestamp),
}
```

- `method` is upper-case (`'GET'`, `'POST'`, `'PATCH'`).
- `url` is the **path + query string only**, exactly as appended to `base` (e.g. `/2026/api/v1/user/mobile_state/`, `/2026/api/v1/check_in/fetch_products/?attendee_access_code=X&category_pk_list=1,2&mode=m`), including any `encodeURIComponent` encoding.
- `body` is `''` for GET, otherwise the **exact string** sent (`JSON.stringify(payload)` — compact, no spaces, insertion key order, non-ASCII unescaped). A Python port must sign `json.dumps(payload, separators=(',', ':'), ensure_ascii=False)` and send that same string.
- Missing key/secret produce `'X-API-Key': null` and a signature over `"null…"` (string concat of `null`) — i.e. unauthenticated calls still go out; the server rejects them.
- Content-Type `application/json` added for POST/PATCH only.

### 4.2 Endpoints (all relative to `baseUrl`, all signed unless noted)

| Method name | HTTP | Path | Body | Timeout | Response as consumed | Caller |
|---|---|---|---|---|---|---|
| (login page, not this file) | POST | `/2026/api/v1/authenticate/` | `{email, password}` (unsigned) | 3000 | `{nickname, email, key, secret, features:{lead_retrieval, door_check_in, mask_violation, is_speaker}}`; error body `{message}` → toast `Invalid Auth: <message>`; success toast `Success! Welcome, <nickname>.` | login |
| `fetchFeatures()` | GET | `/2026/api/v1/user/check_features/` | — | 2000 | `{features:{lead_retrieval?, door_check_in?, mask_violation?}}` | `UserData.fetchFeatures` |
| `fetchPreferences()` | GET | `/2026/api/v1/user/mobile_state/` | — | 2000 | `{favorites?: string[]}` | `UserData.fetchPreferences` |
| `patchUserData(payload)` | PATCH | `/2026/api/v1/user/mobile_state/` | `JSON {favorites:[...]}` | 2000 | ignored (subscribes internally, swallows errors) | `UserData` add/remove favorite |
| `fetchCheckInProducts()` | GET | `/2026/api/v1/check_in/redeemable/` | — | 2000 | product list (door-check / t-shirt pages) | door-check, t-shirt |
| `fetchAttendeesByProduct(productId)` | GET | `/2026/api/v1/check_in/attendees_by_product/<id>/` | — | 2000 | — (no caller) | none |
| `fetchAttendeesByProductWithQuantity(productId)` | GET | `/2026/api/v1/check_in/attendees_by_product_with_quantity/<id>/` | — | **20000** | attendee list | door-check |
| `fetchAttendeeProducts(code, categoryIds[], mode)` | GET | `/2026/api/v1/check_in/fetch_products/?attendee_access_code=<code>&category_pk_list=<a,b>&mode=<mode>` (unencoded) | — | 10000 | products for attendee | t-shirt |
| `fetchAttendeeProductsForProducts(code, productIds[], mode)` | GET | `…/fetch_products/?attendee_access_code=<code>&product_pk_list=<a,b>&mode=<mode>` | — | 10000 | | door-check |
| `redeemProducts(payload)` | POST | `/2026/api/v1/check_in/redeem_products/` | JSON payload (page-defined) | 10000 | redemption result | door-check, t-shirt |
| `fetchCocAttendees()` | GET | `/2026/api/v1/mask_violations/attendees/` | — | 15000 | attendee list | mask-violation |
| `captureMaskViolation(code, {notes?, force?})` | GET if no notes/force: `/2026/api/v1/mask_violations/capture/?attendee_access_code=<enc>`; else POST `/2026/api/v1/mask_violations/capture/` | POST JSON `{attendee_access_code, notes?, force?: true}` | 5000 | result | mask-violation |
| `fetchLeadRetrievalSponsors()` | GET | `/2026/api/v1/lead_retrieval/sponsors/` | — | 5000 | **returns a Promise of the body** (`.toPromise()`), unlike the others which return `Promise<Observable>` | map (staff sponsor picker) |
| `syncScan(code)` | GET | `/2026/api/v1/lead_retrieval/capture/?attendee_access_code=<enc>&badge_validator=<enc>[&sponsor_id=<enc>]` | — | 2000 | body with `data` (lead info: `first_name`, `captured`, `captured_date`, …) merged into `synced-scan-<code>` | map, storeScan |
| `syncNote(code)` | POST | `/2026/api/v1/lead_retrieval/<code>/note/` | JSON `{accessCode, note[, sponsor_id]}` | 2000 | ignored | map, storeNote |

Every method is `async` and (except `fetchLeadRetrievalSponsors`, `patchUserData`, `syncScan`, `syncNote`) resolves to an RxJS Observable that the caller must subscribe to (`pycon.fetchX().then(obs => obs.subscribe(...))`). All `catchError` handlers just `console.log('Unable to fetch mobile state, ' + error)` (copy-pasted message) and rethrow.

### 4.3 Lead-retrieval offline queue (state machine)

```
storeScan(code, scanData)                      # scanData = raw badge QR string "ACCESSCODE:...:VALIDATOR"
  synced-scan-<code> exists  -> log 'Already captured', return
  pending-scan-<code> exists -> syncScan(code), return
  else write pending-scan-<code> = {scanData, scannedAt: now ISO, sponsorId: storage['staff-sponsor-id'], sponsorName: storage['staff-sponsor-name']}
       then syncScan(code)

syncScan(code)
  pending = pending-scan-<code>; (if null only logs, then CRASHES on pending.scanData -> unhandled rejection)
  Network.getStatus(); if !connected -> return (stays pending)
  validator = last ':'-segment of pending.scanData; sponsorId = storage['staff-sponsor-id']
  GET capture?attendee_access_code&badge_validator[&sponsor_id]   timeout 2000
    success -> synced-scan-<code> = {...response, ...pending}; remove pending-scan-<code>
    error   -> pending.tries = (tries||0)+1; if tries > 10: failed-scan-<code> = pending; remove pending
                                            else: rewrite pending-scan-<code>

storeNote(code, note)
  note-<code> = {accessCode, note}; pending-note-<code> = {accessCode, note} -> syncNote(code)
  if synced-scan exists: merge {note:true}; if pending-scan exists: merge {note:true}

syncNote(code)   (no network check, no retry counter)
  POST /lead_retrieval/<code>/note/ {accessCode, note, sponsor_id?}  timeout 2000
    success -> remove pending-note-<code>

fetchScan(code) -> synced ?? pending ?? undefined ;  getNote(code) -> note-<code>
```

The map (lead-retrieval) page drives retries by calling `syncScan`/`syncNote` again (e.g. on refresh / network regain). There is no global queue index: records are discovered by key prefix (`storage.keys()` in the page).

---

## 5. `UserData` provider (`user-data.ts`)

Exports: `DEFAULT_EXCLUDED_TRACKS = ['Open Space']`; `isCustomScheduleFilter(excluded)` → true unless `excluded` has exactly the default entries; `type ThemeMode = 'light'|'dark'|'high-contrast-light'|'high-contrast-dark'`; `THEME_MODES` array in that order.

Constants (storage keys): `HAS_LOGGED_IN='hasLoggedIn'`, `HAS_SEEN_TUTORIAL='hasSeenTutorial'`, `HAS_LEAD_RETRIEVAL='hasLeadRetrieval'`, `HAS_DOOR_CHECK='hasDoorCheck'`, `HAS_MASK_VIOLATION='hasMaskViolation'`, `IS_SPEAKER='isSpeaker'`, `HAS_SCANNER_CONSENT='hasScannerConsent'`.

State: `favorites: string[]` (in-memory mirror, loaded asynchronously in constructor from `favorite_sessions`), `favoritesChanged$` (RxJS `Subject<void>`, emitted after every local favorites write and after a server pull).

| Method | Behaviour |
|---|---|
| `hasFavorite(id)` | **synchronous** `favorites.indexOf(String(id)) > -1`; also fires an async re-read of `favorite_sessions` (called once per session per filter pass → hundreds of storage reads) |
| `addFavorite(id)` | re-read storage → if absent push `String(id)` → if logged in `PATCH mobile_state {favorites}` → write storage → emit |
| `addFavorites(ids[])` | batch variant (used by "Favorite all <track>" button); emits once |
| `removeFavorite(id)` | re-read → splice → write → if logged in PATCH → emit |
| `fetchPreferences()` | if logged in: `GET mobile_state`; if `userPrefs?.favorites` is truthy (an **empty array is truthy**) replace local favorites + storage, emit |
| `fetchFeatures()` | if logged in: `GET check_features` → `setHasLeadRetrieval/DoorCheck/MaskViolation(data.features?.x)` (writes `undefined` when absent) |
| `login(data)` | `hasLoggedIn=true` → `fetchPreferences()` (kicked off *before* key/secret are stored — benign race in practice) → set nickname, email, key, secret, 3 features, isSpeaker → `window.dispatchEvent(new CustomEvent('user:login'))` |
| `logout()` | remove `hasLoggedIn`, `favorite_sessions`, `email`, `nickname`, `key`, `secret`, 4 feature flags, `hasScannerConsent` → dispatch `'user:logout'`. Leaves theme, filters, caches, scan queue, staff sponsor, tutorial flag |
| `getTheme()` | `'high-contrast'` → migrate to `'high-contrast-dark'`; valid stored value → return; legacy `darkTheme===true` → store `'dark'`, remove legacy; `darkTheme===false` → remove legacy; default `'light'` |
| `setTheme(t)` | store |
| `getScheduleFilters()` | `null/undefined` → copy of `['Open Space']`; otherwise stored array (may be `[]`) |
| `setScheduleFilters(arr)` | store (not awaited) |
| `isLoggedIn()` | `storage.get('hasLoggedIn') === true` |
| `checkHasSeenTutorial()` | reads `hasSeenTutorial` (never written; dead) |
| `set/checkHasLeadRetrieval`, `…DoorCheck`, `…MaskViolation`, `set/checkIsSpeaker` | plain get/set (returned value may be `undefined`) |
| `setScannerConsent` / `checkScannerConsent` | set / `=== true` |
| `get/setEmail`, `get/setNickname`, `get/setAuthKey`, `get/setSecret` | plain get/set |

Global window events: `user:login` / `user:logout` are listened to by `app.component.ts` (menu state, nickname, feature flags via `updateLoggedInStatus` with a 300 ms `setTimeout`), `tabs-page.ts` (tab visibility), `sprints.page.ts`, `schedule-list.page.ts` (login-gated buttons). `favoritesChanged$` is subscribed by `schedule.ts` (re-run `updateSchedule()` + `detectChanges()`).

App start sequence relevant to this slice (`app.component.ts`): constructor → `confData.load()` (hide splash on first emission or error); `ngOnInit` → `getTheme`, `isLoggedIn` → `fetchPreferences`, `fetchFeatures`; after 5 s → push/live-update/notification work. `CheckTutorial.canLoad` (route guard for `/tutorial`): if `ion_did_tutorial` → navigate to `/app/tabs/lead-retrieval` when `hasLeadRetrieval` else `/app/tabs/schedule`.

---

## 6. Pipes (`src/app/pipes/*`)

`PipesModule` declares/exports only `TrackNamePipe`. `SessionOrderPipe` is declared directly in `schedule.module.ts`; `DateAgoPipe` directly in `map.module.ts`.

### `trackName` (`TrackNamePipe.transform(value, format='short')`)

Order of resolution: `format==='long'` and in LONG → LONG; `format==='plural'` and in PLURAL → PLURAL; in DISPLAY → DISPLAY; else `value.replace(/-/g,' ')` then title-case each word (`\b\w` → upper).

| Track key | short (DISPLAY) | plural | long |
|---|---|---|---|
| `Ai` | `AI` | `Future of AI with Python` | `The Future of AI with Python` |
| `Security` | `Security` (fallback) | `Trailblazing Python Security` | `Trailblazing Python Security` |
| `Talk` | `Talk` | `Talks` | — |
| `Keynote` | `Keynote` | `Keynotes` | — |
| `Tutorial` | `Tutorial` | `Tutorials` | — |
| `Charla` | `Charla` | `Charlas` | — |
| `Poster` | `Poster` | `Posters` | — |
| `Lightning-talks` | `Lightning Talks` | `Lightning Talks` | — |
| `Plenary` | `Plenary` | `Plenaries` | — |
| `Break` | `Break` | `Breaks` | — |
| `Sponsor Presentation` | `Sponsor Presentation` | `Sponsor Presentations` | — |
| `Open Space`, `Summit`, `Event`, `Informational` | fallback (unchanged) | fallback | — |

Used in: schedule, schedule-list (title uses `'plural'`), now, speaker-list, speaker-detail, schedule-filter, session-detail (`'long'`).

### `dateAgo` (`DateAgoPipe`)

`!value` → `'a long time ago'`; `t = (now - Date.parse(value))/1000`; `t<10` → `'just now'`; `t<60` → `'a moment ago'`; else divide successively by `[60, 60, 24, 30, 12]` while `floor(t/div) > 0`, label from `[' second',' minute',' hour',' day',' month',' year']` at the stopping index, plural `s` when `floor(t) > 1`, suffix `' ago'` (e.g. `'3 hours ago'`, `'1 day ago'`). Used on lead-retrieval list (`scan.scanned_at`).

### `sessionOrder` (`SessionOrderPipe`)

`value.sort((a,b) => a.track < b.track ? -1 : a.track > b.track ? 1 : 0)` — sorts a group's sessions **in place** alphabetically by `track` string (ASCII order: `Ai` < `Break` < `Charla` < `Event` < `Informational` < `Keynote` < `Lightning-talks` < `Open Space` < `Plenary` < `Poster` < `Security` < `Sponsor Presentation` < `Summit` < `Talk` < `Tutorial`). Impure pipe applied in `schedule.html` per time group.

---

## 7. Location data (`src/app/location-map/*`)

### 7.1 `VenueLocation` interface

`{key: string; label: string; sublabel?: string; floorTitle: string; thumbSrc: string; fullSrc: string; pinXPct: number; pinYPct: number}` — pin coordinates are percentages of the image box.

Floor-plan assets (all exist under `src/assets/img/floor-plans/`):

| Floor | title | thumb | full |
|---|---|---|---|
| 1 | `Concourse Level` | `floor-plan-1-thumb.jpg` | `floor-plan-1.jpg` |
| 2 | `Upper Level` | `floor-plan-2-thumb.jpg` | `floor-plan-2.jpg` |
| 3 | `Arena & Exhibit Halls` (portrait 1700×2200) | `floor-plan-3-thumb.jpg` | `floor-plan-3.jpg` |
| 4 | `Seaside Meeting Rooms` | `floor-plan-4-thumb.jpg` | `floor-plan-4.jpg` |

### 7.2 `VENUE_LOCATIONS` (venue-locations.ts)

| key | label | sublabel | floor | pin x,y % |
|---|---|---|---|---|
| `infoDesk` | Information Desk | Promenade Lobby (Main Entrance) | Concourse | 55, 53 |
| `registration` | Registration | Promenade Lobby (Main Entrance) | Concourse | 67, 58 |
| `quietRoom` | Attendee Quiet Room | VIP Room A & B | Concourse | 58, 36 |
| `swagPickup` | Swag Pickup | Expo Hall A & B | Arena | 42, 68 |
| `lostAndFound` | Lost & Found | Info Desk during open hours; Staff Office overnight | Upper | 40, 58 |
| `staffOffice` | Staff Office | Room 203 A & B | Upper | 40, 58 |

Used by `venues-hours.page.ts` (infoDesk, registration, swagPickup, quietRoom, lostAndFound) and `help.page.ts` (infoDesk).

### 7.3 `ROOM_LOCATIONS` (room-locations.ts) — key → (label, x, y, sublabel)

Concourse Level: `101a` Room 101A (14,50) "Tutorials / PSF Members Lunch / PyLadies Lunch"; `101b` Room 101B (19,50) same; `101ab` Room 101AB (17,50) same; `102a` Room 102A (23,50) "Tutorials / Open Spaces"; `102b` Room 102B (27,50) same; `102c` Room 102C (31,50) same; `103a` Room 103A (39,50) "Talk Track / Security Track"; `103b` Room 103B (43,50); `103c` Room 103C (46,50); `103abc` **Room 103** (43,50); `104a` Room 104A (72,38) "Talk Track"; `104b` Room 104B (80,35); `104c` Room 104C (84,27) "Education Summit / Charlas / Open Spaces"; `104ab` Room 104AB (76,37) "Talk Track"; `104abc` Room 104 (78,33) "Talk Track / Education Summit".

Upper Level: `201a` Room 201A (7,59) "Summits / Open Spaces"; `201b` Room 201B (14,59) "Sponsor Presentations / Open Spaces"; `202a` (19,59), `202b` (23,59), `202c` (27,59) "Sponsor Presentations / Open Spaces"; `203a` Room 203A (36,59) "Staff Office"; `203b` (41,59) "Staff Office"; `203c` Room 203C (45,59) "Green Room / Speaker Ready Room"; `204` Room 204 (60,48) "AV Room"; `grandballrooma` Grand Ballroom A (76,36) "AI Track / Talk Track"; `grandballroomb` Grand Ballroom B (84,50) "Talk Track"; `grandballroom` Grand Ballroom (80,43) "Talk Tracks".

Arena & Exhibit Halls: `pacificballroomarena` "Pacific Ballroom — Arena" (60,16) "Keynotes, Lightning Talks, General Sessions"; `arena` Arena (60,16) same; `halla` Hall A (18,72) "Exhibit Hall"; `hallb` Hall B (43,63); `hallc` Hall C (58,55); `hallab` Hall AB (32,67) "Expo Hall — Booths, Job Fair, Community Showcase"; `expohallab` Expo Hall AB (32,67) "Booths, Job Fair, Community Showcase"; `expohallc` Expo Hall C (58,55) "Posters, Open Spaces"; `expohall` Expo Hall (38,64).

Seaside Meeting Rooms: `s1` S-1 (85,63) "Sprints"; `s2` S-2 (53,57) "Sprints"; `s3` S-3 (58,68) "Open Spaces / Sprints"; `s3a` (60,68); `s3b` (55,68); `s4` S-4 (46,68) "Web Assembly Summit / Open Spaces / Sprints"; `s4a` (49,68) "Open Spaces / Sprints"; `s4b` (44,68) "Web Assembly Summit / Open Spaces / Sprints"; `s5` S-5 (45,24) "Open Spaces / Sprints"; `s5a` (47,24) "Sprints"; `s5b` (43,24) "Open Spaces / Sprints"; `s6` S-6 (53,24) "Sprints"; `s7` S-7 (80,27) "Satellite Staff Office"; `seasidelobby` Seaside Lobby (33,44) "Sprints"; `seasideballrooma` (55,44), `seasideballroomb` (44,44), `seasideballroom` (50,44) "PyLadies Auction / Sprints".

`normalizeRoomKey(name)`: lowercase → strip leading `room\s+` → strip all non `[a-z0-9]`. `getRoomLocation(name)` → entry or `null`. Coverage against the 38 derived rooms: all match except `Elsewhere`, `Lobby`, `Out Front of Hyatt Regency` (room-detail then shows no map card). `'Pacific Ballroom - Arena'` (hyphen) matches `pacificballroomarena` whose label uses an em dash.

### 7.4 `LocationMapComponent` (`<app-location-map>`)

Applying the page template:
1. **Route/reach**: not routed; embedded in `room-detail` (when `getRoomLocation(room.name)` is non-null), `venues-hours` (per hours section) and `help` (info desk).
2. **Purpose/flows**: one tappable card; tap → `ModalController` opens `FloorPlanModalComponent` with `{title: floorTitle, imageSrc: fullSrc, altText: \`${floorTitle} floor plan with ${label} highlighted\`, pinXPct, pinYPct, pinLabel: label}` (modal implementation is outside this slice).
3. **Data**: inputs only (`label, sublabel?, floorTitle, thumbSrc, fullSrc, pinXPct, pinYPct`). No storage/API.
4. **Native plugins**: none.
5. **UI**: `<button class="location-map">` full-width flex row, radius 14 px, 1 px border `var(--ion-color-step-150)`, card background; left 144 px thumbnail (`<img>` of thumb, white bg, right border) with an absolutely positioned pin at `left:pinXPct%; top:pinYPct%` made of an 8 px magenta dot `#DD04D2` with 1.5 px white border + shadow and a pulsing ring (same colour, opacity .55 → 0, scale 1 → 2.6, 1.8 s ease-out infinite); bottom-right 24 px dark circle (`rgba(0,0,0,.55)`) containing ionicon `expand-outline` 14 px; right meta column padding 12/14 px: label 16 px/600, sublabel 13 px step-650, floor title 12 px medium uppercase letter-spacing .04em. `:active` scales to .985.
6. **State**: stateless.
7. **Navigation out**: modal only.
8. **A11y**: `aria-label="Show <label> on the <floorTitle> floor plan"`; pin and zoom hint `aria-hidden`; img alt `<floorTitle> floor plan`; `decoding="async"`.
9. **Complexity 2** — simple card, but needs a percent-anchored overlay pin + pulse animation on an image.

---

## 8. Other providers in `src/app/providers` (context only)

- `check-tutorial.service.ts` — route guard described in §5.
- `live-update.service.ts` — Appflow OTA (`@capacitor/live-updates` `sync()/reload()`, `@capacitor/app` `getInfo()`/`appStateChange`), adds body class `has-pending-update`, loader text `Installing the latest build...` (60 s). Not portable; no data role.
- `notifications.service.ts` — stores `notification_prefs`; local notifications ids incl. `8999`; FCM topics `emergency`, `announcements`, `schedule-changes`, `daily-digest`. Out of scope here.

---

## 9. Feed analysis — `conference.json` (live copy)

Top-level keys: `conference` (object), `schedule` (728), `open-spaces` (123), `job-listings` (13), `sprints` (24), `posters` (25).

### 9.1 `schedule[]` — slot records

| field | type | presence | values / notes |
|---|---|---|---|
| `room` | str | 728 | 38 distinct strings; 30 blank `''`; multi-room strings are `', '`-joined and always equal `', '.join(rooms)` |
| `rooms` | list[str] | 728 | lengths 1 (698), 2 (5), 4 (7), 5 (6), 7 (11), 9 (1); 27 distinct names: `''`, `Elsewhere`, `Expo Hall AB`, `Grand Ballroom A/B`, `Lobby`, `Out Front of Hyatt Regency`, `Room 101A/101AB/101B/102A/102B/102C/103ABC/104AB/104C/201A/201B/202A/202B/202C`, `S-1/S-3/S-4/S-5`, `Seaside Ballroom A/B` |
| `start`, `end` | str ISO 8601 with offset | 728 | all `-07:00`; range `2026-05-13T07:30:00-07:00` → `2026-05-17T23:00:00-07:00`; per day 13/33/212/224/246 |
| `duration` | int **minutes** | 728 | 0 (28 informational), 5 (25 posters), 15–45, 60 (483), 210 (22 tutorials), 450, 720 (37), 1020 (3) |
| `kind` | str enum | 728 | `available-open-space-slot` 444, `talk` 61, `available-open-space` 40, `informational` 28, `poster` 26, `break` 23, `tutorial` 20, `sponsor-workshop` 18, `charla` 16, `plenary` 11, `ai` 9, `security` 8, `open-space` 7, `summit` 5, `lightning-talks` 4, `keynote` 4, `event` 4 |
| `section` | str enum | 728 | `open-spaces` 491, `talks` 130, `events` 37, `posters` 26, `tutorials` 24, `sponsor-presentations` 20. Breaks appear under `talks` (19), `tutorials` (2), `sponsor-presentations` (2); plenary under `talks` (9) and `tutorials` (2) |
| `conf_key` | int | 728 | unique, 1–1147 |
| `list_render` | bool | 728 | `true` only for the 491 open-space-family kinds; `false` for everything that survives filtering |
| `license` | str | 728 | always `'CC BY'` |
| `tags` | str | 728 | always `''` |
| `released` | bool | 728 | always `true` |
| `contact` | list[str] | 728 | `[]` (597) or `['redacted']` (131) |
| `name` | str | 728 | may contain **markdown links** `[Title (Room)](/2026/...)` (plenary 6, keynote 4, lightning-talks 1, event 1) and trailing `(Room)` / `(Sponsor: X)` parentheses (break 17, sponsor-workshop 17, plenary 11, keynote 4, ai 2, talk 1, lightning-talks 1, event 1); placeholder names equal to kind |
| `description` | str HTML | 728 | `<p>…</p>` HTML (entities like `&amp;`); empty for placeholders/posters; 7 open-space entries also HTML here |
| `authors` | list[str] | 131 | speaker display names (same length as `speakers`) |
| `speakers` | list[{id:int, name:str, photo:str, bio:str HTML}] | 131 | 156 entries / 144 distinct ids; `photo` absolute `https://pycon-assets.s3.amazonaws.com/2026/media/speaker_photos/<id>.webp.256x256_q85.jpg` (146) or `''` (10, e.g. "Hosted by Abigail, Chris, Cristián, and Lorena"); `bio` HTML (153) or `''` |
| `conf_url` | str | 131 | `https://us.pycon.org/2026/schedule/presentation/<conf_key>/` |
| `cancelled` | bool | 131 | always `false` (cancellations manifest as placeholder slots instead) |

Notable name values: break names `Lunch (Hall AB)` ×12, `Break` ×6, `Coffee (Hall AB)` ×3, `Lunch (Hall C)` ×2; poster names all `poster`; events `Job Fair & Community Showcase & Poster Sessions`, `PSF Members Lunch, pre-registration required`, `PyLadies Lunch, pre-registration required`, `[PyLadies Auction, pre-registration required](/2026/events/pyladies-auction/)`; summits `Maintainers Summit`, `Packaging Summit, pre-registration required`, `Python Education Summit, pre-registration required`, `Typing Summit`, `WebAssembly Summit, pre-registration required`; keynotes `[Keynote — <name> (Pacific Ballroom - Arena)](/2026/about/keynote-speakers/#keynote-…)` (one with `, En Español`); informational names are 0-duration markers: `Registration Desk Opens/Closes`, `Expo Hall Opens/Closes`, `Open Spaces Rooms Open/Close`, `Swag Pickup Opens/Closes`, `Extra T-shirts Available`, `Donations for T-shirt Close` (all with `room: ''`).

### 9.2 `open-spaces[]`

| field | type | notes |
|---|---|---|
| `room` | str | 14 distinct; `Elsewhere` used as bucket |
| `rooms` | list[str] | always `[room]` |
| `room_display` | str | human label; differs from `room` for `Elsewhere` → `Out Front of Hyatt Regency`, `Lobby` |
| `room_order` | int | 10,20,…,230 (sort key per room) |
| `start`, `end` | ISO `-07:00` | Fri 50, Sat 48, Sun 25; none missing |
| `duration` | int **seconds** (3600 ×120, 2700, 10800, 1800) | unit differs from `schedule.duration` |
| `kind` / `section` / `list_render` | `'open-space'` / `'open-spaces'` / `true` | constant |
| `conf_key` | int 25–177 (unique) | **overlaps schedule conf_keys** → app offsets by +9000 |
| `title` | str | 5 titles repeat (recurring sessions) |
| `description` | str **markdown/plain** (7 contain `[x](url)` links; no HTML) | |
| `image_url` | str absolute (67) or `null` (56) | `https://pycon-assets.s3.amazonaws.com/2026/media/open_spaces_images/…` |

The 7 `kind='open-space'` slots inside `schedule[]` match these by title, not by `conf_key`.

### 9.3 `posters[]`

`{id:int, conf_key:int (== id), title:str, description_html:str HTML, speakers:[{id, name, photo, bio}]}` — 25 records; 1–2 speakers each (29 total, 1 with `photo: ''`); **all 25 `conf_key` values collide with schedule `conf_key`s** (hence the `poster-detail-` id prefix); 3 poster authors are also talk speakers.

### 9.4 `sprints[]`

`{id:int, name:str, url:str (external project site), description_html:str (HTML in 9, plain text in 15), logo_url:str|null (2 null) absolute `…/2026/media/sprint_project_logos/…`, submitter:str}` — 24 records.

### 9.5 `job-listings[]`

`{id:int, sponsor_name:str, sponsor_logo_url:str absolute (`https://s3.dualstack.us-east-2.amazonaws.com/pythondotorg-assets/media/sponsor_web_logos/…`), sponsor_level: 'Visionary'|'Maintaining'|'Partner'|'Supporting'|'Contributing', description_html:str HTML (`<ul><li><p><a target=_blank …>` lists of roles)}` — 13 records.

### 9.6 `conference.sponsors` — `{level_name: Sponsor[]}`

Levels in `level_order`: `Visionary` 0 (7), `Sustainability` 1 (1), `Maintaining` 2 (6), `Contributing` 3 (4), `Supporting` 4 (16), `Partner` 5 (19), `Participating` 6 (12), `Associate` 7 (10), `Standalone Only` 8 (1), `AV Partner` 9 (1), `Media` 10 (2), `Startup Row` 11 (9), `Community` 12 (17) — 105 sponsors.

Sponsor: `{name:str, level:str, level_order:int, mobile_banner:bool (14 true: all Visionary + Sustainability + Maintaining), logo_url:str absolute, description:str plain text (3 empty), booth_number:str|null (68 set, e.g. '613'), job_fair_table_number:str|null (19 set, 'T1'…'T20')}`. Pages sort levels by `value[0].level_order`.

### 9.7 `conference.content` — `{key: HTML string}`

`about` (394 chars), `about-psf` (1115), `social-media` (736; `<h2>` + nested `<ul>` with links to Mastodon/Bluesky/… and `<code>` handles), `code-of-conduct` (577), `venues-hours` (1394; `<h2>`, `<h3>`, `<ul>` of day/hours lines, venue address "Long Beach Convention Center, 300 E Ocean Blvd"), `wifi` (118; `<ul>` with `<code>` SSID and password).

### 9.8 Cross-cutting quirks

- Mixed markup: schedule descriptions/bios = HTML; open-space descriptions = markdown; sponsor descriptions = plain text; slot names may be markdown links.
- Relative URLs exist only inside HTML/markdown bodies (`/2026/about/keynote-speakers/#…`, `/2026/events/…`); every `photo`, `logo_url`, `image_url` is absolute in this snapshot, but the app still guards for relative ones.
- Three separate id spaces collide numerically (schedule `conf_key`, open-space `conf_key`, poster `conf_key`).
- Durations: minutes in `schedule`, seconds in `open-spaces`.
- 30 slots with empty `room` (28 informational + 2 breaks) → sessions with `location ''`, no `roomLinks`, `displayLocation ''`.
- One `available-open-space-slot` has an HTML description (irrelevant, dropped).
- Speakers are linked to sessions by **name string** equality between `authors[i]` and `speakers[j].name`, not by id.

---

## 10. Proposed Python dataclass field lists

Raw feed (1:1 with JSON; keep names so the cache stays a plain dict):

```python
@dataclass class FeedSpeaker:   id: int; name: str; photo: str; bio: str                      # photo may be ''
@dataclass class FeedSlot:      room: str; rooms: list[str]; start: str; end: str; duration: int; kind: str;
                                section: str; conf_key: int; list_render: bool; license: str; tags: str;
                                released: bool; contact: list[str]; name: str; description: str;
                                authors: list[str] | None = None; speakers: list[FeedSpeaker] | None = None;
                                conf_url: str | None = None; cancelled: bool | None = None
@dataclass class FeedOpenSpace: room: str; rooms: list[str]; room_display: str; room_order: int; start: str; end: str;
                                duration: int  # seconds
                                kind: str; section: str; conf_key: int; list_render: bool; title: str;
                                description: str; image_url: str | None
@dataclass class FeedPoster:    id: int; conf_key: int; title: str; description_html: str; speakers: list[FeedSpeaker]
@dataclass class FeedSprint:    id: int; name: str; url: str; description_html: str; logo_url: str | None; submitter: str
@dataclass class FeedJobListing: id: int; sponsor_name: str; sponsor_logo_url: str; sponsor_level: str; description_html: str
@dataclass class FeedSponsor:   name: str; level: str; level_order: int; mobile_banner: bool; logo_url: str;
                                description: str; booth_number: str | None; job_fair_table_number: str | None
@dataclass class FeedConference: content: dict[str, str]; sponsors: dict[str, list[FeedSponsor]]
@dataclass class ConferenceFeed: conference: FeedConference; schedule: list[FeedSlot]; open_spaces: list[FeedOpenSpace];
                                job_listings: list[FeedJobListing]; sprints: list[FeedSprint]; posters: list[FeedPoster]
```

Processed model (mirrors `processData` output):

```python
@dataclass class Speaker:  id: int; name: str; profile_pic: str; about: str;
                           sessions: list["Session"] = field(default_factory=list); tracks: list[str] = ...;
                           hide: bool = False
@dataclass class RoomLink: name: str; slug: str
@dataclass class Session:  id: int | str                     # conf_key | conf_key+9000 | 'poster-detail-N' | 'break-<room>-<start>'
                           name: str; track: str; tracks: list[str]; color: str | None; pre_registered: bool;
                           is_spanish: bool; list_render: bool; section: str; location: str;
                           display_location_override: str | None; display_location: str; room_links: list[RoomLink];
                           description: str; speakers: list[Speaker]; speaker_names: list[str];
                           time_start: str; time_end: str; start_utc: str | None; end_utc: str | None; day: str;
                           image_url: str | None = None; site_url: str | None = None; track_slug: str | None = None;
                           favorite: bool = False; hide: bool = False
@dataclass class Track:    name: str; icon: str
@dataclass class TimeGroup: time: str; sessions: list[Session]; start_time: datetime | None; hide: bool = False; day_label: str = ''
@dataclass class ScheduleDay: date: str; groups: list[TimeGroup]; shown_sessions: int = 0
@dataclass class DayTab:   index: str; date: str; day: str
@dataclass class Room:     name: str; slug: str; sessions: list[Session]
@dataclass class ProcessedData: schedule: list[ScheduleDay]; speakers: list[Speaker]; tracks: list[Track];
                           sessions: list[Session]; conference: FeedConference; sprints: list[FeedSprint];
                           job_listings: list[FeedJobListing]; posters: list[FeedPoster]  # + session_id per poster
                           rooms: list[Room]
```

Storage / API records:

```python
@dataclass class AuthResponse:  nickname: str; email: str; key: str; secret: str; features: Features
@dataclass class Features:      lead_retrieval: bool = False; door_check_in: bool = False; mask_violation: bool = False; is_speaker: bool = False
@dataclass class MobileState:   favorites: list[str]
@dataclass class PendingScan:   scan_data: str; scanned_at: str; sponsor_id: str | None; sponsor_name: str | None; tries: int = 0; note: bool = False
@dataclass class SyncedScan(PendingScan): data: dict                # server lead payload merged in
@dataclass class LeadNote:      access_code: str; note: str
@dataclass class RoomLocation:  key: str; label: str; sublabel: str | None; floor_title: str; thumb_src: str; full_src: str; pin_x_pct: float; pin_y_pct: float
@dataclass class NotificationPrefs: lightning: bool = True; open_space: bool = True; emergency: bool = True; announcements: bool = True; schedule_changes: bool = True; daily_digest: bool = True
ThemeMode = Literal['light', 'dark', 'high-contrast-light', 'high-contrast-dark']
```

---

## 11. Shared logic in this slice (constants, regexes, hard-coded values)

- URLs: feed `${baseUrl}/2026/schedule/conference.json`; open-space deep link `${baseUrl}/2026/schedule/open-spaces/#OpenSpace-<conf_key>`; API prefix `/2026/api/v1/`; fallback avatar `assets/img/person-circle-outline.png`.
- Regexes: trailing room `/\s*\(([^)]+)\)\s*$/`; Hall normalisation `/^Hall\s/i` → `Expo ` prefix; lunch `/^lunch\b/i`; posters plenary `/^posters?$/i`; Spanish `/en espa[ñn]ol/i` and strip `/,?\s*en espa[ñn]ol/i`; typing summit exclusion `/typing/i`; track prefix `^<kind with '-'→'[- ]'>\s*[—:\-–]\s*` (i); job fair override `/^\s*job\s*fair\s*&\s*community\s*showcase\s*$/i`; query tokeniser `/,|\.|-/g`; slug `/[^a-z0-9]+/g`; room key `/^room\s+/i` + `/[^a-z0-9]+/g`; sprint seed `/sprints/i`; `parseTime` splitter `/([ap]m)/`.
- Numbers: `+9000` open-space id offset; `-30` min job-fair display shift; lunch window hours `[12,14)` on `Fri/Sat/Sun`; retry cap `tries > 10`; timeouts 2 000 / 3 000 / 5 000 / 10 000 / 15 000 / 20 000 ms; toast 3 000 ms; `utcOffset -7`.
- Strings carrying meaning: track keys (`Talk`, `Tutorial`, `Keynote`, `Plenary`, `Lightning-talks`, `Charla`, `Ai`, `Security`, `Summit`, `Event`, `Informational`, `Sponsor Presentation`, `Break`, `Poster`, `Open Space`), the legacy `'open-spaces'` string in `tracks`, collapsed names `Posters`/`Lunch`/`Coffee`/`Break`, forced location `Pacific Ballroom - Arena`, default poster room `Expo Hall AB`, default poster day `Sun`.
- Track slug mapping used by `/app/tabs/tracks/:trackSlug` (schedule-list): `slugify(name + 's')` with `slugify = lower, trim, remove [^\w\s-], collapse [\s_-]+ → '-'` → `talks`, `keynotes`, `ais`, `securitys`, `charlas`, `lightning-talkss`, `tutorials`, `posters`, `sponsor-presentations`, `open-spaces` (both the string `'open-spaces'` and `'Open Space'+'s'` resolve to it).
- Default schedule filter `['Open Space']`; `isCustomScheduleFilter`.
- Sidebar/menu routes referencing data (app.component): `/app/tabs/schedule`, `/speakers`, `/keynote-speakers`, `/rooms`, `/tracks/<slug>`, `/lightning-talks`, `/sprints`, `/sponsors`, `/expo-hall`, `/job-listings`, `/about-pycon`, `/coc`, `/wifi`, `/venues-hours`, `/session-types`, `/about-psf`, `/social-media`, `/conference-map`, `/help`.

---

## 12. Assets referenced by this slice

- `assets/img/person-circle-outline.png` (speaker fallback avatar).
- `assets/img/floor-plans/floor-plan-{1,2,3,4}.jpg` and `…-thumb.jpg` (also present but unreferenced here: `campus-map(.jpg|-thumb.jpg)`, `job-fair(.jpg|-thumb.jpg)`).
- Ionicons: track icons (`cafe-outline`, `flash-outline`, `book-outline`, `megaphone-outline`, `star-outline`, `briefcase-outline`, `easel-outline`, `mic-outline`, `shield-checkmark-outline`, `chatbubbles-outline`, `hardware-chip-outline`, `people-circle-outline`), `expand-outline` (location card), toast icons `exclamation` (feed error), `alert` / `check` (login).
- Remote: speaker photos & open-space images on `pycon-assets.s3.amazonaws.com`, sponsor logos on `s3.dualstack.us-east-2.amazonaws.com/pythondotorg-assets`.
- Colour: pin magenta `#DD04D2`; Ionic palette `primary #3880ff`, `tertiary #5260ff`, `light #f4f5f8`, `medium #92949c` (light theme; dark/high-contrast override them).

---

## 13. Gotchas / non-obvious behaviour (things a port would silently get wrong)

1. **Two emissions on cold start** (cache → network) for every query; pages re-render twice. A port that awaits a single result will show stale data until next launch, or never show cached data offline.
2. **Processing mutates shared state**: `filterSession` sets `hide`/`favorite` on the one shared Session object; `getTracks()`, `getDays()`, `getSpeakers()` sort arrays in place; `SessionOrderPipe` sorts group arrays in place. Two views filtering concurrently (schedule + now page) overwrite each other's `hide` flags.
3. **Locale-dependent time strings**: `toLocaleTimeString([])` uses the device locale; group keys, `parseTime`, and the `'9:00 am'` labels silently change on non-en-US phones. Pin to en-US-style `h:mm am`.
4. **Grouping uses canonical start, label uses display start** (Job Fair appears under 10:00 am labelled 9:30 am).
5. **Missing `startTime` on the first group of a day created by the main loop** → unstable sort and the Now page (`new Date(undefined)`) never treats that group as current/upcoming. Always set `startTime`.
6. **`tracks` contains a bare string `'open-spaces'`** alongside objects; consumers must tolerate `typeof track === 'string'`; filter modal drops it via `track.name &&`.
7. **Speaker linking by name**, not id; a speaker whose `authors` string differs from `speakers[].name` would get no session; duplicate names would merge.
8. **Three colliding id spaces** (schedule/open-space/poster `conf_key`) resolved by `+9000` and `poster-detail-` prefixes; session lookups compare `String(s.id) === String(param)`.
9. `color` is `undefined` for most tracks (talks, tutorials, keynotes…); only plenary/poster/event/summit/break/informational carry a colour. Track pills are coloured by CSS `data-track` (lowercased track) instead.
10. **Posters**: 26 raw 5-minute slots → one `Posters` timeline row; 25 synthetic `poster-detail-*` sessions exist only in `data.sessions` (track page, search, speaker pages, room list — `Expo Hall AB` shows 35 sessions mostly posters) and inherit the collapsed row's time/day.
11. **Breaks**: generic `Break` rows keep the comma-joined multi-room `location` (so each room's agenda lists them) but display an empty location; `Coffee`/`Lunch` display `Expo Hall AB`/`Expo Hall C`. Lunch rows span earliest start → latest end across staggered room slots.
12. The `else if (slot.kind === 'break')` block in the main loop is unreachable (breaks are collapsed earlier).
13. **`isPlaceholderSlot` must exempt `poster`/`break`**, otherwise the Poster track never registers and posters leak onto every track page (documented regression).
14. `fetchPreferences` overwrites local favorites whenever the server returns a `favorites` key — including `[]` — so pre-login favorites are discarded at login (unless the server merges). `addFavorite` PATCHes the full list, not a delta.
15. **Favorites ids are strings**; if the server returns numbers, `hasFavorite` never matches.
16. `hasFavorite` is synchronous but schedules a storage re-read every call; port with an in-memory set.
17. `logout()` keeps `theme`, `scheduleFilters`, `schedule-cache`, lead-retrieval scan records, `staff-sponsor-*`, `ion_did_tutorial`; feature flags are removed (not set false) so `checkHas*` returns `undefined`.
18. `getScheduleFilters` distinguishes "never set" (→ default `['Open Space']`) from explicit `[]`.
19. **Signature base string** has no separators and the body must be byte-identical to what is sent; timestamps are integer seconds (`Math.round`). URL in the signature includes the query string and `encodeURIComponent` encoding exactly as built (note `fetchAttendeeProducts*` do **not** encode their params while `syncScan`/`captureMaskViolation` do).
20. `syncScan` with no pending record throws inside an async function (unhandled rejection) instead of returning.
21. `fetchLeadRetrievalSponsors` resolves to the body; every other fetch resolves to an Observable.
22. `Network.getStatus()` gates only `syncScan`; `syncNote` and all other calls simply time out offline (2 s) and are retried only when a page calls them again.
23. Feed `open-spaces.duration` is in **seconds**, `schedule.duration` in minutes (app never uses either — it recomputes from `start`/`end`).
24. `environment.utcOffset -7` is hard-coded; day bucketing would break for a non-PDT event, while `timezone` string is used for labels.
25. `getDays()` ignores its arguments; day tabs are not filtered by track/favorites.
26. `markdownToTxt` is applied to slot names only (not descriptions); descriptions remain HTML and are rendered with `[innerHTML]` elsewhere — search matches inside tag names/attributes.
27. Room-detail map lookup normalises `Room 103ABC` → `103abc` (own entry), but `Elsewhere`, `Lobby`, `Out Front of Hyatt Regency` have no floor-plan entry.
28. The Rooms list is seeded with 16 sprint rooms from static data even when the feed has no sessions for them; S-7 (staff office) is excluded by its sublabel.
29. `tracks` registration order (feed order) is the order shown in the filter modal — Informational first, Poster last — not alphabetical.
30. Angular `HttpClient` auto-parses JSON and treats non-2xx as errors; `error.error?.message` is the parsed body — reproduce for login toast text.

---

## 14. Complexity estimates

| Unit | Complexity (1–5) | Reason |
|---|---|---|
| `ConferenceData.processData` | 5 | ~700 lines of order-dependent normalisation with many regex special cases, three id spaces, collapse/merge rules and shared-state side effects; must be reproduced exactly for parity |
| `ConferenceData.load` + cache | 3 | cache-then-network double emission, toast on total failure, in-memory memo |
| `ConferenceData` query/filter methods | 3 | mutating filters, OR-word search, locale-formatted time parsing, multiple sorts |
| `PyConAPI` signing + endpoints | 2 | simple SHA-1 scheme but byte-exact body/URL requirements and per-endpoint timeouts |
| `PyConAPI` lead-retrieval offline queue | 4 | multi-key state machine with retries, dead-letter, note merging, network gating; no tests |
| `UserData` | 3 | async storage mirror, server sync semantics, theme migration, window events |
| Pipes | 1 | pure functions |
| `room-locations` / `venue-locations` | 1 | static tables + key normaliser |
| `LocationMapComponent` | 2 | image + percent-positioned pulsing pin + modal hand-off |
| Feed parsing / dataclasses | 2 | regular JSON but mixed markup and colliding ids |

---

## 15. Open questions for the port

1. Does `GET /user/mobile_state/` return favorites as strings or ints, and does PATCH replace or merge? (affects favorite matching and login behaviour)
2. Exact response bodies of `check_in/*`, `mask_violations/*`, `lead_retrieval/capture` and `/note/` — only `data.first_name/captured/captured_date` is observable here; other slices (door-check, t-shirt, map, mask-violation) define the rest.
3. Is the `markdown-to-txt` behaviour on slot names needed beyond link/emphasis stripping and entity unescaping (no other markdown appears in the live feed)?
4. Should the port keep the device-locale time formatting bug-for-bug or pin en-US (recommended)?
5. Should "shared sessions" (`slot.sessions`) be supported at all? The live feed never emits them.
6. Is `querySponsors` (no callers) and `fetchAttendeesByProduct` (no callers) dead code to drop?
7. Does the Flet target need the dev-environment host switch (`10.0.2.2` vs `127.0.0.1`) and the three separate storage DB names?
