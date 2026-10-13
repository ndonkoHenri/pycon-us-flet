# UX/UI specification (v2)

**Status:** plan of record, 2026-10-11. Consolidates the three v2 UX studies (foundations, attendee schedule, conference companion) under [`decisions.md`](decisions.md) sections C and D. Where this file and a decision disagree, the decision wins until a `needs-decision` issue changes it.
**Scope:** Android and iOS phones, with a tablet layout (§8). Material 3 only, identical on both platforms (D-10). Web, PWA, desktop and Cupertino or adaptive variants are out of scope (D-08).
**Related:** [`PLAN.md`](../PLAN.md), [`feature-matrix.md`](feature-matrix.md), [`flet-gaps-and-extensions.md`](flet-gaps-and-extensions.md), [`architecture.md`](architecture.md).

**Reading this file**
- `P0`..`P4` say when a piece lands. A screen's phase covers everything in it unless a line says otherwise. *(could)* marks optional polish.
- Feature ids (`SCHED-05`, `NEW-01`) are matrix rows; `D-nn` and `O-n` are in the decisions record; `UQ-n` are open UX questions (§10). Gap specs and status: [`flet-gaps-and-extensions.md`](flet-gaps-and-extensions.md); an interim is replaced only by a PR that bumps the pinned Flet (D-64).
- Every Flet control, field, enum and service named here was introspected in the local monorepo (flet-dev/flet `9fbe52a61`, 1.1.0-dev). Missing pieces are marked **GAP** with their interim. This is API evidence; spikes S1..S9 (PLAN §8) confirm behaviour on phones.

---

## 1. Design principles

1. **Answer the attendee's question first:** what is on now, what is next for me, where is it. Time and place come before descriptions.
2. **One obvious way:** one search, one place for saved sessions, one filter surface, one favourite control, one scaffold, one feedback rule.
3. **Offline from the first launch.** Render the best local copy, refresh in the background, show freshness honestly, never an error while data exists (D-32, D-38).
4. **Never move the user unasked.** Back pops exactly one step (#279); screens keep their day, filters, scroll and zoom (#313) (D-17, D-18).
5. **Quiet chrome.** Surface app bars with visible titles; brand colour only at identity moments (D-28).
6. **Identical visuals, native gestures** (D-10, D-11).
7. **Accessible by construction:** components carry semantics, 48 dp targets, checked contrast, 200 % text (D-33).
8. **No dead controls.** Anything that depends on a missing capability is hidden or says why (D-60, D-63).
9. **Content is data.** Year facts come from `data/<year>/*.toml`, never from widget code or name matching (D-45).

---

## 2. Information architecture and navigation

### 2.1 Bottom bar (D-13, prov. O-1)

| # | Label | Icon (off / on) | Root | Answers |
|---|---|---|---|---|
| 1 | Now | `SENSORS_OUTLINED` / `SENSORS` | `/now` | What is happening, what is next for me (start screen, D-14) |
| 2 | Schedule | `CALENDAR_MONTH_OUTLINED` / `CALENDAR_MONTH` | `/schedule` | The programme by day and time |
| 3 | My schedule | `STAR_BORDER` / `STAR` | `/my-schedule` | What I saved, and my conflicts |
| 4 | Map | `MAP_OUTLINED` / `MAP` | `/map` | Rooms, floor plans, expo, job fair |
| 5 | More | `MORE_HORIZ` | `/more` | Everything else, one flat list |

```python
ft.NavigationBar(
    destinations=[
        ft.NavigationBarDestination(
            icon=ft.Icons.SENSORS_OUTLINED, selected_icon=ft.Icons.SENSORS, label="Now"
        ),
        # ... the other four, in the order above
    ],
    selected_index=TAB_ROOTS.index(root),  # the bar is on roots only (D-144)
    label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
    on_change=switch_tab,  # another tab: its root; the active one: the root's re-tap
)
```

- Identical for every user; never changes with sign-in or role (SHELL-05). Never `adaptive=True`. The M3 indicator pill replaces Ionic's magenta label (4.18:1).
- Each destination's label is its accessible name; its node also carries the identifier `app.nav.<tab>` (`app.nav.now` … `app.nav.my_schedule`, decisions §M) for UI tests (D-166), and each root's app-bar title carries `<tab>.title` (`now.title` … `more.title`, D-170).
- The bar shows on tab roots only (D-144, #149); pushed Views show the back arrow and no bar. S4 found that a bar on pushed Views slid across with the page on iOS and doubled during Android transitions and predictive Back.
- The My schedule star is the favourite star, so tab and action read as one idea. Speakers live in More and search.

### 2.2 More (D-15)

One `ListView` of `ListTile`s under `SectionHeader`s; no drawer, no accordions. Trailing `CHEVRON_RIGHT` for in-app pages, `OPEN_IN_NEW` for web pages (§4.7). Every child is pushed, so Back works (Ionic's drawer replaced the root).

| Section | Items (routes under `/more/`) | Phase |
|---|---|---|
| Profile row | "Sign in" (`sign-in`) or avatar, nickname, email (`account`); only when a mock API URL is set (D-51) | P3 |
| Staff tools | Lead scanner, Door check, Swag pickup, CoC incident (`staff/<lead\|door\|swag\|coc>`), from `staff_entries(flags)`, "3 pending" badges | P3 |
| Programme | Speakers, Tracks & session types, Keynotes, Open spaces, Lightning talks, Sprints | P1 |
| Expo & sponsors | Sponsors, Expo hall (pushes the expo viewer), Job listings | P2 |
| At the venue | Venue & hours, Wi-Fi, Help & safety | P2 |
| About | About PyCon US, About the PSF, Social media | P2 |
| You | Settings (P2), About this app (P1) | P1 |

The Staff section and the profile row appear and disappear live with the account (SHELL-11, SHELL-15).

**How the list grows (D-169).** A section and its rows appear in the PR that brings their pages, so no row is dead (SHELL-09). P0 (#77) shows Programme, whose pages are stubs until their P1 screens, and You. Until Settings exists (P2), You starts with the **Appearance** control, three radio rows (System, Light, Dark) as §6.9 specifies them under an "Appearance" label marked as a heading (D-33), then About this app, then **Developer options** wherever it is available (always when not embedded; in packaged builds after the unlock, D-73). Rows are `LinkTile`s (§3.9) with the §3.7 icons: `PEOPLE_OUTLINE` Speakers, `SELL_OUTLINED` Tracks & session types, `CO_PRESENT_OUTLINED` Keynotes, `FORUM_OUTLINED` Open spaces, `BOLT_OUTLINED` Lightning talks, `ROCKET_LAUNCH_OUTLINED` Sprints, `PALETTE_OUTLINED` Appearance, `INFO_OUTLINE` About this app, `DEVELOPER_MODE_OUTLINED` Developer options. Each row carries the identifier `more.<page>` (`more.speakers`, `more.open_spaces`, `more.app`), the Appearance group `more.appearance` and its options `more.appearance.<value>`. "Not an official PSF app." is on About this app (D-36), so the list has no footnote (#88). Re-tapping More scrolls the list to the top (D-166).

### 2.3 Navigation map

```
/now          Now dashboard                       P1 (stub in P0)
/schedule     Day tabs, slots, filter sheet       P1
/my-schedule  Saved sessions by day               P1
/map          Rooms (P1) · Floor plans · Expo · Job fair (P2)
/more         Flat sectioned list                 P1+
  speakers  tracks[/<slug>]  keynotes  open-spaces  lightning-talks  sprints   P1
  sponsors  jobs  venue  wifi  help  about  psf  social  settings             P2
  app (About this app, P1)  developer (hidden, P1)
  sign-in  account  staff/<tool>                                             P3
/search?scope=   global search                    P1
/welcome         first run                        P2
Drill under every root, More page and search (one pushed View per hop):
  session/<id>  speaker/<id>  room/<slug>  sponsor/<slug>
  plan/<plan>   (P2; floor plans, expo, job fair; §2.5)
  e.g. /schedule/session/42/speaker/17/session/99
```

### 2.4 Back, tabs and position (D-17, D-18, D-11)

1. **Detail chains are a real stack.** Every cross-link pushes one View via the drill route, so session → speaker → session → room pops one hop at a time (SESS-12). The View below stays mounted and keeps its scroll.
2. **Tab switch** shows that tab's root. Root state lives outside screen state (D-18): filters in `Prefs`; the Schedule day and offset, the My schedule offset, and the Map sub-tab and zoom in `ViewMemory` (architecture §6.3). Offsets come back with `ListView.scroll_to(offset=...)`.
3. **Re-tapping the active destination** scrolls its root to the top: 300 ms, a jump under reduced motion (D-34, D-166). The bar is on roots only (D-144, settled in #149 after S4), so from a pushed View, Back leads to the root.
4. **Android Back** on a root other than Now goes to Now; on Now it exits (`View.can_pop=False` + `on_confirm_pop`, D-142) (SHELL-16).
5. **Transitions:** `ft.PageTransitionsTheme(android=ft.PageTransitionTheme.PREDICTIVE, ios=ft.PageTransitionTheme.CUPERTINO)` keeps iOS edge-swipe and Android predictive Back (D-148, settling O-2). Tab switches do not animate: root Views share one `View.route` key, `"/"`, a case the Router's pop handler explicitly supports (`components/router.py`) (D-142; with a key per root, S4 saw a tab switch slide in like a detail).
6. **Insets (#311, D-12).** System bars are never hidden. Bodies sit in `ft.SafeArea`; lists pad their end by `page.media.padding.bottom` plus FAB clearance; sheets use `use_safe_area=True`. Checked with 3-button and gesture navigation and on an iPhone with a home indicator.

### 2.5 Route shapes and Back targets (decisions §M, D-19; confirmed by S4, D-141, D-141)

- **Search returns to its results on Back** (D-19). Search is the global modal `/search?scope=` (decisions §M). The stock Router would pop every view of a modal chain to the modal's base (`components/router.py`: the `on_view_pop` handler, lines 672-711, modal branch 685-687; modal detection and the pop target, lines 744-797), but a `page.on_view_pop` installed before `page.render_views(App)` takes precedence (lines 676-679). So Back from a result returns to the results through the app's own `page.on_view_pop` and `parent_of()` (D-19, D-141); the handler goes once U18 lands.
- **Schedule changes** is `/schedule/changes` (decisions §M), opened from Now, a SnackBar or Settings. Returning to the opener on Back rather than to the Schedule root would need `parent_of()` to remember the opener, as it does for search (D-19); that is a proposal pending a `needs-decision` issue.
- **Floor plans push from anywhere** (rooms, sessions, Help, Venue, More, and sponsor "Find booth", SPON-04) through the fifth drill kind `plan/<plan>` (decisions §M, architecture §5.2): plan ids from `map.toml`, including `expo` and `job-fair`, with `?pin=<room key>` or `?booth=<n>`.

Query parameters carry only view options (`?scope=`, `?pin=`, `?highlight=`, `?booth=`), read with `use_query()` until U9.

### 2.6 Deep links (P2, NEW-07, D-21) and launch (SHELL-01, SHELL-03)

- A custom scheme and host named with the app identity (O-4); links have the form `<scheme>://<host>/<route path>`, e.g. `<scheme>://<host>/schedule/session/42`, and both per-platform deep-linking tables set `scheme` and `host` (D-21). A link opens its root with the target pushed, so Back never exits. An unknown id opens its detail's not-found state ("This session isn't in the current schedule") pushed on the root, so Back lands there (D-186). Reminder taps use the same paths. Shared links use the public us.pycon.org page (NEW-06).
- **Launch:** native splash `#680579` with the app icon (O-4), never the PyCon logo (D-36); Flet's boot screen, shown while Python starts, in the same purple (`[tool.flet.boot_screen.flet]`); a boot View (same purple) until `Prefs.loaded` and the cached or bundled feed are read, so theme and filters never flash; a `ProgressRing` only after 1 s. First run goes to `/welcome` (P2), otherwise Now; in P3 lead-retrieval accounts may open on the Lead scanner (D-16). Never a permission prompt at launch (D-61).

---

## 3. Design system

### 3.1 Brand palette

Indigo `#3B3EA9` is the seed, light `primary`, the Now status header and the About band. Purple `#680579` is light `secondary`, the splash, boot View and Welcome (white text 11.1:1). Magenta `#A1009A` is light `tertiary` (7.0:1) and the favourite star; Ionic's `#DD04D2` (4.18:1) is used for nothing. Gold `#FFD779` is for icons on indigo only (6.2:1). Navy, cyan, Ionic blue `#3880ff` and the iOS `#000` dark surface are dropped (THEME-02, THEME-03, THEME-10).

### 3.2 Colour schemes (D-22, D-23)

Flet builds `ColorScheme.fromSeed`, neutralises surfaces, then applies our overrides (F9), so we set the brand roles and their containers, each with its `on_*` partner, plus `surface`, `on_surface` and `on_surface_variant` (equal to Flet's neutral ramp, so the contrast test sees them); outline, error, inverse and the neutral `surface_container*` ramp come from the seed and Flet. WCAG ratios computed for this file.

| Role | Light | Dark | HC light (P2) | HC dark (P2) |
|---|---|---|---|---|
| `primary` / `on_primary` | `#3B3EA9` / `#FFFFFF` 8.6 | `#BFC1FF` / `#1F2189` 7.5 | `#4A0072` / `#FFFFFF` 13.7 | `#FFD60A` / `#0B0F17` 13.6 |
| `primary_container` / on | `#E1E0FF` / `#13126B` 12.3 | `#3B3EA9` / `#E1E0FF` 6.7 | = primary | = primary |
| `secondary` / on | `#680579` / `#FFFFFF` 11.1 | `#F4AEFF` / `#52005E` 8.1 | `#4A0072` / `#FFFFFF` | `#F5F5F0` / `#0B0F17` |
| `secondary_container` / on | `#FCD6FF` / `#36003F` 13.2 | `#680579` / `#FCD6FF` 8.6 | `#E9E7E1` / `#1A1D24` | `#21252F` / `#F5F5F0` |
| `tertiary` / on | `#A1009A` / `#FFFFFF` 7.0 | `#FFACEB` / `#5E0058` 7.6 | `#4A0072` / `#FFFFFF` | `#FFD60A` / `#0B0F17` |
| `tertiary_container` / on | `#FFD7F3` / `#3B0037` 13.1 | `#85007F` / `#FFD7F3` 7.1 | = secondary_container | = secondary_container |
| `surface` / `on_surface` | `#FFFFFF` / `#1B1B1B` 17.2 | `#121212` / `#E7E7E7` 15.2 | `#FBFAF6` / `#1A1D24` 16.2 | `#0B0F17` / `#F5F5F0` 17.5 |
| `on_surface_variant` | `#5E5E5E` 6.5 | `#ABABAB` 8.2 | `#1A1D24` | `#F5F5F0` |
| `outline`, `error` | seed | seed | `#1A1D24`, `#8C0009` 9.5 | `#F5F5F0`, `#FFB4AB` 11.3 |

- **High contrast** (P2) sets every role by hand: `surface_container*` equal `surface` so borders separate cards; all text 7:1. If HC stops fitting `ColorScheme` roles cleanly it moves to `later` (THEME-04). Settings › High contrast puts the HC themes in both slots.
- A unit test checks every text/background pair in all four schemes, the tokens and the badges (D-25).
- Each scheme sets `Theme.system_overlay_style` (`ft.SystemOverlayStyle`, D-12, D-113): status- and navigation-bar icon brightness follow the scheme, the status bar is transparent, the navigation bar has the `NavigationBar`'s colour (`surface_container`, D-151: below Android 15 the app is not drawn under it), and navigation-bar contrast is **not** enforced. Android's 3-button icons then sit on the `NavigationBar`'s colour; with the scrim, or with no style under an `AppBar`, they were grey on dark grey (2.3:1, #311; S1).

### 3.3 Tokens (D-24)

A frozen `Tokens` dataclass behind `use_tokens()` holds what M3 has no role for; `App` provides the current scheme's tokens (D-150). Each token reads at 4.5:1 or better on every surface of its scheme, containers included (the ratios below are on `surface`).

| Token | Light | Dark | HC light | HC dark | Used by |
|---|---|---|---|---|---|
| `live` | `#1B6E35` 6.3 | `#8BD89A` 11.1 | `#0F5A26` 8.0 | `#30D158` 9.5 | Happening now, Open now |
| `warning` | `#7A5900` 6.5 | `#F2C14E` 11.2 | `#7A4A00` 7.2 | `#FFD60A` 13.6 | Stale data, overlaps, pending scans |
| `success` | = live | = live | = live | = live | Scan accepted |
| `favorite` | `tertiary` | `tertiary` | `on_surface` | `on_surface` | Filled star |

Scan outcome colours (P3) are in §7.2; each passes 6.5:1 or better.

### 3.4 Track badges (D-25, THEME-08, SCHED-20)

Tonal pills: fill plus text colour, every pair at least 6.4:1 in both themes (D-25 requires 4.5:1; the lowest is Summit dark, 6.45:1). Badges always carry text. In HC they are outlined: 1.5 dp `on_surface` border and text on `surface`. The palette lives in `Tokens` (`theme.py`, D-174), keyed by the registry's track keys (below).

The fills are distinct colours, not shades of one (D-174): each sits at one CIELAB lightness (87 light, 29 dark) and chroma (22, a little less where sRGB runs out), about 30° of hue from its neighbours, and Summit is a quieter slate. So any two fills, En Español's pink and the Break grey included, differ by a CIE76 distance of 10 or more in each scheme (the closest: Tutorial and En Español, 10.2, light; Lightning talks and Sponsor presentation, 10.1, dark). Each label is its fill's hue at lightness 27 (light) or 90 (dark). A test checks both the contrast and the distance.

| Badge | Light fill / text | Dark fill / text |
|---|---|---|
| Talk | `#C7DBFE` / `#014271` | `#2C4666` / `#D9E3F5` |
| Tutorial | `#FFCDD8` / `#6C293E` | `#643743` / `#F6DCE1` |
| Keynote, Plenary | `#E0D4FD` / `#443869` | `#483F61` / `#E6E0F2` |
| Lightning talks | `#E9D9B0` / `#4B3F0A` | `#4E4422` / `#EAE2CF` |
| Security | `#FAD3B5` / `#5D3712` | `#5B3E26` / `#F2DFD1` |
| AI | `#AAE6D8` / `#01493E` | `#0F4D43` / `#CEE8E1` |
| Charla | `#ABE2FD` / `#03465A` | `#034B60` / `#CFE6F2` |
| Poster | `#FFCFC6` / `#6A2D25` | `#643932` / `#F7DDD8` |
| Sponsor presentation | `#D4DFB5` / `#354511` | `#3E4826` / `#E0E5D2` |
| Open space | `#BDE4C3` / `#134925` | `#2A4C32` / `#D6E7D8` |
| Summit | `#BED5E1` / `#1E4455` | `#3C515B` / `#CFE6F3` |
| Event | `#A2E6EC` / `#03474C` | `#024C52` / `#CBE8EB` |
| Break, Informational | `#E6E6E6` / `#383838` | `#404040` / `#E0E0E0` |
| En Español | `#FFD7F3` / `#5E0058` (10.1) | `#5E0058` / `#FFD7F3` |

A track the palette lacks (a new kind in next year's feed) gets the Break grey. Role-based badges: **Registration required** is outlined, its label and a 1 dp border in `error` on the surface (6.5:1 on `surface` in light, 11.0:1 in dark; 4.76:1 at worst, on `surface_dim`; D-174), not an `error_container` fill: an outline marks a requirement as a different kind of badge from a category, as Ionic's danger outline did; New track is outlined in `primary` (8.6:1 on `surface` in light, 11.0:1 in dark; 6.3:1 at worst, on the light `surface_dim`; D-199), a mark of status like Registration required rather than one more tonal fill: `secondary_container` sat 6.8 (CIE76) from the En Español pink in light and outshone every track in dark; Changed (24 h, P2) = `tertiary_container`. A session's badges are its track, then En Español, then Registration required (Ionic's set; a charla shows both "Charla" and "En Español"). Palette keys are the track registry's keys (`conference.toml`), spaces and capitals included (`"Open Space"`, `"Ai"`, `"Sponsor Presentation"`); labels come from one `track_name()` (DATA-28), so the AI badge reads "AI".

### 3.5 Theme construction

`build_theme(*, dark: bool, high_contrast: bool) -> ft.Theme` in `theme.py` is sketched once, in [architecture §15](architecture.md#15-theming-d-22d-28-d-33-d-34): the seed, neutral surfaces, each scheme's roles with their `on_*` partners, `system_overlay_style` (D-12), Roboto, left-aligned titles and the page transitions. The full override list per scheme is §3.2. `page.theme` and `page.dark_theme` get the light and dark results; `page.theme_mode` follows Appearance.

### 3.6 Typography, shape, spacing (D-26, THEME-11)

- **Font:** Roboto 400/500/700, declared in the local font-only Flutter package `flutter_packages/roboto_fonts/` (family `Roboto`, three assets with `weight: 400/500/700`), added through `[tool.flet.flutter.pubspec]` (D-26, D-105, F18) and selected with `Theme.font_family="packages/roboto_fonts/Roboto"`, so iOS does not fall back to SF Pro. `page.fonts` holds one file per family, so it cannot carry the three weights (a multi-weight `page.fonts` is U20). `flet run` falls back to the system font; S5 verified the packaged build on iOS and Android. Its digits are tabular, so times align (`TextStyle` has no `font_features`, F8). No weight-300 headings.
- **Scale:** only `ft.Text(theme_style=ft.TextThemeStyle.X)`. `HEADLINE_SMALL` detail titles and Welcome; `TITLE_LARGE` app bars; `TITLE_MEDIUM` row and card titles; `TITLE_SMALL` section headers and gutter times; `BODY_LARGE` descriptions; `BODY_MEDIUM` row meta; `BODY_SMALL` status strip; `LABEL_LARGE` buttons and chips; `LABEL_SMALL` badges.
- **Text scaling:** Flutter applies the OS scale and iOS Bold Text; Flet cannot read the factor (**GAP** U16), so layouts reflow by construction: no fixed heights around text, `Row(wrap=True)` for badges, row titles wrap to 3 lines (full on detail). Tested at 200 %. No in-app font-size setting. One exception: Flutter clamps `NavigationBar` labels at 1.3x, so "My schedule" wraps to two lines from 115 % (D-167; legible, never clipped).
- **Selectable:** descriptions and bios `Markdown(selectable=True)`; copyable values (rooms, Wi-Fi password, address) `Text(selectable=True)`.
- **Spacing** on a 4 dp grid: 16 dp gutters and card padding, 24 dp between sections, 8 dp within a group; `ListTile(min_height=56)`, 72 for two lines.
- **Shape:** 8 dp badges and chips, 12 dp cards, 16 dp the Now header and meta cards, 28 dp sheet and dialog tops, full radius for the search field and extended FAB.
- **Elevation** is tonal: rows sit on `surface` with no card per row; groups use `CardVariant.FILLED` or `OUTLINED`; app bars are flat with `elevation_on_scroll`; HC has no shadows and uses `OUTLINED` cards.
- **iOS pins (D-10):** Roboto; `AppBarTheme(center_title=False)`; pushed Views get `leading=ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Back")` instead of the iOS chevron; never `adaptive=True`. Accepted residual adaptations (D-10): overscroll physics (bounce on iOS, stretch on Android) and the text-selection toolbar and handles in selectable text (Markdown and text fields, see Selectable above). Intended difference: the Cupertino transition (D-11). Pinning the residual adaptations is **GAP** U19 (`Theme.platform` or a scroll-behaviour option).

### 3.7 Icons (D-27, THEME-12)

Material Icons only: `_OUTLINED` when unselected or decorative, filled when selected. Every icon named in this file exists in `ft.Icons`; the screen sections name the icon for each action. Brand logos (Python, PyPI, Mastodon, Bluesky, X, LinkedIn, YouTube, Discord) are bundled SVGs in `ft.Image`. Every icon-only button has a `tooltip`, which is also its accessible name. Fixed meanings: `CHEVRON_RIGHT` in-app, `OPEN_IN_NEW` external, `TUNE` filter, `SCHEDULE` time, `PLACE_OUTLINED` room, `WARNING_AMBER` overlap, `CHANGE_CIRCLE_OUTLINED` / `EVENT_BUSY_OUTLINED` / `NEW_RELEASES_OUTLINED` changed / removed / added, `CLOUD_OFF_OUTLINED` offline. Track icons (hub, §5.10), in the registry's order: `MIC_NONE_OUTLINED` talks, `CO_PRESENT_OUTLINED` keynotes, `CAMPAIGN_OUTLINED` plenaries, `BOLT_OUTLINED` lightning talks, `MEMORY_OUTLINED` AI, `SHIELD_OUTLINED` security, `TRANSLATE` charlas, `ARTICLE_OUTLINED` posters, `SCHOOL_OUTLINED` tutorials, `BUSINESS_CENTER_OUTLINED` sponsor presentations, `FORUM_OUTLINED` open spaces, `GROUPS_OUTLINED` summits, `CELEBRATION_OUTLINED` events (each track its own icon, D-199); the `logistics` tracks, `INFO_OUTLINE` notices and `COFFEE_OUTLINED` breaks, are not on the hub, and `ROCKET_LAUNCH_OUTLINED` is the Sprints row and the sprint-day state, not a track. More rows: `PEOPLE_OUTLINE` speakers, `SELL_OUTLINED` session types, `STOREFRONT_OUTLINED` sponsors, `WORK_OUTLINE` jobs, `BUSINESS_OUTLINED` venue, `WIFI`, `SUPPORT_OUTLINED` help, `INFO_OUTLINE` about, `LANGUAGE` social, `SETTINGS_OUTLINED`, `ACCOUNT_CIRCLE_OUTLINED`, `QR_CODE_SCANNER` staff.

### 3.8 Motion (D-34, THEME-09)

- 150 ms toggles, 250 ms fades and `AnimatedSwitcher` swaps, 400 ms scroll-to-slot; `AnimationCurve.EASE_IN_OUT_CUBIC_EMPHASIZED` entering, `EASE_OUT` small changes.
- No ambient motion: pins and highlights pulse at most twice; nothing rotates or auto-advances; FAB labels never collapse on a timer.
- **Reduced motion (D-173):** `await ft.SemanticsService().get_accessibility_features()` at start and in `app.on_resume()` (no change event, **GAP** U17), so a change in the OS settings applies on the next resume, without a restart (on Android a change made while the app is in the background can take one more resume until U17, D-183; until then, scrolls keep their full length). With `disable_animations` (Android's Remove animations) or `reduce_motion` (iOS Reduce Motion), durations are 0, `Shimmer` becomes static placeholders, scrolls jump, and pins are still. Scheme changes keep Flutter's 200 ms crossfade: an opacity change, not motion (D-173). Every custom animation asks `prefs.motion_ms(ms)`, which returns `ms` or 0 (the flag is `Prefs.reduce_motion`, not persisted). Page transitions stay the platform's: Android's setting already makes them instant in Flutter, and on iOS the slide keeps the edge swipe. Progress indicators keep moving while work runs.

### 3.9 Shared components (decisions §M names, grouped in `ui/`: `scaffold.py`, `status_strip.py`, `rows.py`, `session_rows.py`, `time_gutter.py`, `badges.py`, `states.py`)

| Component | Flet building blocks | Spec | Accessibility |
|---|---|---|---|
| `AppScaffold` | `View(appbar, navigation_bar` or rail`, floating_action_button, controls=[SafeArea(...)])` | `AppBar(title, actions, elevation_on_scroll)`, title always visible; bar or rail on roots; back arrow on pushed Views | Title is the page name |
| `SessionRow` | sketch below; a memoised component keyed by session id (D-153, D-184) | Badges; title ≤ 3 lines; meta "9:25–10:10 AM · Room 104A" and speakers in `on_surface_variant`; optional elapsed `ProgressBar(bar_height=3, year_2023=False)` in `live` under them, M3's gap and stop dot (`on_surface_variant`) at its end, on a track of `on_surface` at 16 % (`elapsed=`, Now's Happening now and next-session card; D-190); on My schedule an overlap line last (`WARNING_AMBER` and "Overlaps with “…”" in `warning`, ≤ 3 lines, then "and 2 more" on a line of its own, D-191). The meta's time and place are two texts in a wrapping row, so at large text the place moves down whole and the "·" ends a line; "AM" keeps to its time. A row says no day: a list that spans days (a speaker's) puts a `SectionHeader` per day above its rows (`row_views.by_day()`, or a `DayGroup` per day), and a room's has a tab per day (§5.9). On a room's page the meta leaves out the room the title names (`in_room`, D-194); on a speaker's page the speakers line names only the co-speakers, "With Ana Lima" (`of_speaker`, D-203) | One phrase, then its role: "Talk. Title. 9:25 to 10:10 AM, Room 104A. Ana Lima." and "button" (with an elapsed bar, "… 60 percent elapsed."); star is its own stop; identifiers `<screen>.session.<key>`, `<screen>.favorite.<key>`, the key from `semantics_key()` (lower case, `-` for spaces and colons) |
| `FavoriteButton` | sketch below | 48 dp; `selection_click()` on add; feedback per §4.4 from `use_favorite_toggle()` (D-184); tooltip "Add to My schedule" / "Remove from My schedule" (what a tap does) | One stable name and a state, said once: `Semantics(label="Save to My schedule", button=True, toggled=...)`, heard as "Save to My schedule, switch, on"; the tooltip is left out of the semantics and the icon swaps without `IconButton.selected` (D-184) |
| `NoticeRow` | `MergeSemantics(Container(bgcolor=surface_container, border_radius=12, Row[Icon(<track icon>), Column[Text(TITLE_SMALL), Text(meta)]]))`, memoised and keyed like `SessionRow` | Notices, breaks, meals (the `logistics` track group); no star; tappable only with a description (SCHED-04); the icon is the track's from `conference.toml` (`INFO_OUTLINE` notices, `COFFEE_OUTLINED` breaks); padding 12 × 8 and margin 16 × 4, so its title starts 12 dp down, on the gutter's line | "Notice. Registration opens, 7:00 AM."; its own node, a button when it opens (D-184); identifier `<screen>.notice.<key>` |
| `TrackBadge` | `Container(bgcolor, border=Border.all(1, fill or text), border_radius=8, padding=Padding.symmetric(horizontal=8, vertical=2), Text(LABEL_SMALL))`, a plain builder given its `BadgeColors` (D-174); `session_badges()` and `badge_row()` (`Row(wrap=True, spacing=8, run_spacing=4)`, §3.6's grid) beside it | §3.4; not a `Chip` (Chips are interactive); the label wraps inside the pill at large text, never clipped | Text carries the meaning |
| `TimeGutter` | `Column[Text("9:25", TITLE_SMALL), Text("AM", LABEL_SMALL)]` over an invisible "10:00" / "AM" in a `Stack`, padding 16 left and 8 right: no fixed width, so it grows with the text and is the same for every slot (D-158) | Left of each slot; replaces sticky headers (**GAP** U2) | `Semantics(header=True, label="9:25 AM", exclude_semantics=True)` |
| `SpeakerRow` | `MergeSemantics(Container(ink, on_click, Semantics(label, button, exclude_semantics, Row[CircleAvatar(foreground_image_src=photo, content=initials, bgcolor=primary_container, color=on_primary_container, radius=24), Column[Text(TITLE_MEDIUM), Text(BODY_MEDIUM)]])))`, a memoised component keyed by speaker id, built like `SessionRow` rather than a `ListTile`, so it reads as one phrase (D-189) | The feed's photo over the initials, which show while it loads, offline and when there is none; subtitle: the first session in the Schedule's order (the day first), at most two lines, in `on_surface_variant`, and "+1 more" on a line of its own when there are more, so a long title never cuts it (the phrase says the title whole) | "Ana Lima, speaking: Title, and 1 more session", a button; identifier `<screen>.speaker.<key>` |
| `SpeakerTile` | `MergeSemantics(Semantics(identifier, ListTile(leading=Semantics(exclude_semantics=True, speaker_avatar()), title=name, trailing=CHEVRON_RIGHT, on_click, title_alignment=TITLE_HEIGHT, min_height=64)))`, a plain function, not memoised: a session has a handful of speakers (D-197) | A speaker in a session's Speakers section: the Speakers list's 48 dp avatar (`speaker_avatar()`, shared with `SpeakerRow`: the photo over the initials), the name and no subtitle, 8 dp above and below the avatar; a tap pushes `…/speaker/<id>` (D-17) | One node, "Ana Lima, button", the initials excluded; identifier `<screen>.speaker.<key>` |
| `SectionHeader` | `Semantics(header=True, content=Container(Text(TITLE_SMALL, color=primary)))`; a heading over headings of its own takes `TITLE_MEDIUM` in `on_surface` (search's type headings, D-193) | Day, letter, floor, section titles; not sticky; `level=` for a page's outline, an optional decorative `leading=` mark before the text (Now's live dot, D-190) and `spoken=` for what a screen reader says instead of the text ("Up next, 11:30 AM" for "Up next · 11:30 AM", `now_header.spoken()`) | Heading navigation; reads `text`, or `spoken` |
| `StatusStrip` | `Row[Row[Icon(16), Text(BODY_SMALL)], TextButton("Refresh")]`, the inner row top-aligned so a wrapped line keeps the icon beside its first line, and centred against the 48 dp button + `ProgressBar(bar_height=2, value=None)` in a 2 dp slot that stays when the bar hides (nothing moves when a refresh starts or ends), on `surface_container_high`; padding 16 start, 8 end, 4 above and below (56 dp at 100 %, and room around the wrapped line at 200 %) | Hidden when fresh (§4.2); during an automatic refresh only the bar runs, the line, icon and button unchanged, and the strip stays hidden over fresh data (D-181); "Updating the schedule…" with Refresh disabled only for a refresh the user asked for, which a tap during a quiet one joins (D-165, D-181); re-reads the clock every 60 s, and on Now and Schedule starts the 15-min refresh (D-175) | `live_region=True`, identifier `app.status` |
| `EmptyState` | `Column[Icon(48), Text(TITLE_MEDIUM), Text(BODY_MEDIUM)?, FilledTonalButton?]`, centred, 32/48 dp padding, no fixed height (D-182) | One sentence, one way out: the button, or the sentence where no button can help (§4.6); a label and its handler come as a pair | The title is a heading node of its own (`container=True`); title and body are in one live region with the identifier, announced on first show; the icon is decorative; the button is its own stop, `disabled` (not removed) while its action runs |
| `SkeletonList` | `Shimmer(period=prefs.motion_ms(1500))` over 5 session-shaped placeholder rows in `surface_container_highest`, highlight `surface_container_low`; no `Shimmer` under reduced motion (D-173, D-182) | Only with no data at all: while the first fetch runs, before it has failed (§4.1) | One node, "Loading schedule"; the placeholders are excluded |
| `LocationCard` (P2) | `Card(OUTLINED, Row[Stack[Image(width=112), pin], Column[label, sublabel, floor]])` | Pin pulses twice; pushes the floor viewer | One button: "Show Room 104A on the Concourse level floor plan" |
| `LinkTile` | `MergeSemantics(ListTile(leading, title, subtitle, trailing, on_click, title_alignment=TITLE_HEIGHT))`, or with a subtitle `title_alignment=TOP, min_vertical_padding=14` (D-188), icons beside the title's first line at any text size, with an optional `Semantics(identifier=...)`; a phone or email row is `Row[that, IconButton(CONTENT_COPY_OUTLINED)]` | In-app (#77): trailing `CHEVRON_RIGHT`, pushes a location, M3 heights (56 dp, 72 with a subtitle). External (#83, D-182): the link rule §4.7; web pages and apps end in `OPEN_IN_NEW`, phone and email rows in Copy | One node read as its title and subtitle; external rows add `Semantics(link=True)`, and the `OPEN_IN_NEW` icon is read "Opens in browser" ("Opens in another app"); Copy is its own stop, `<identifier>.copy` |

```python
import flet as ft


def FavoriteButton(selected: bool, on_click, *, color: str, identifier: str) -> ft.Control:
    """The one favourite control (D-30): a 48 dp labelled star (ui/badges.py)."""
    return ft.MergeSemantics(  # one node: a stable name, a switch, on or off (D-184)
        content=ft.Semantics(
            label="Save to My schedule",
            button=True,
            toggled=selected,
            identifier=identifier,
            content=ft.IconButton(
                # Not IconButton.selected: its Semantics(selected:) would add "selected".
                icon=ft.Icons.STAR if selected else ft.Icons.STAR_BORDER,
                icon_color=color if selected else None,  # Tokens.favorite (D-150)
                tooltip=ft.Tooltip(  # what a tap does; iOS would read it after the name
                    message="Remove from My schedule" if selected else "Add to My schedule",
                    exclude_from_semantics=True,
                ),
                on_click=on_click,
            ),
        )
    )


def SessionRow(view, is_favorite, on_toggle, tokens, *, screen) -> ft.Control:
    """A session in any list: one spoken phrase, plus a separate star (ui/session_rows.py)."""
    return _SessionRow(view, is_favorite, on_toggle, tokens, screen=screen, key=view.session.id)


@ft.memo
@ft.component
def _SessionRow(view: SessionView, is_favorite, on_toggle, tokens: Tokens, *, screen):
    info = use_services().year.conference  # a plain context: subscribes to nothing
    specs = badge_specs(view.session, info, tokens)  # (label, colours), D-174
    text = ft.Semantics(
        label=spoken_phrase([label for label, _ in specs], view),
        identifier=f"{screen}.session.{semantics_key(view.session.id)}",
        button=True,  # it opens the session
        exclude_semantics=True,  # the phrase replaces the texts
        content=ft.Column(
            spacing=4,
            controls=[
                badge_row([TrackBadge(label, colors) for label, colors in specs]),
                ft.Text(view.session.name, theme_style=ft.TextThemeStyle.TITLE_MEDIUM, max_lines=3),
                _meta(view),  # Row(wrap=True)[Text("9:25–10:10 AM ·"), Text(place)]
                ft.Text(view.speakers, theme_style=ft.TextThemeStyle.BODY_MEDIUM),
            ],
        ),
    )
    return ft.Row(
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.START,
        controls=[
            ft.MergeSemantics(  # the phrase and the tap's action: one node
                expand=True,
                content=ft.Container(
                    text, ink=True, on_click=open_session,
                    padding=ft.Padding.only(left=16, top=12, right=4, bottom=12),
                ),
            ),
            FavoriteButton(is_favorite, star, color=tokens.favorite, identifier=...),
        ],
    )
```

`SessionView` is a frozen view model from a pure function in `core/row_views.py` (`session_view()`, `session_views()`); rows never format times themselves. A list owner gets its views from `use_session_views(conference, ids, use_24h=...)`, memoised on the feed version, the ids and the clock format, and its one star handler from `use_favorite_toggle(favorites)` (D-184). The Schedule memoises the whole path (D-153, S2): `ft.memo` day lists given only their day's favourites, `ft.memo` slot items given only their slot's favourites, and `ft.memo` rows keyed by session id on `(row view, is_favorite, on_toggle, tokens)` (D-184), with view models built once per feed version and `on_toggle` from `use_callback`. A star tap then re-renders one row; memoising the rows alone left the parents' rebuild (38 ms against 3 ms on the busiest day, F34).

---

## 4. Global patterns

### 4.1 Screen states (D-32)

| State | When | UI |
|---|---|---|
| Ready | Data present, fresh | Content, no strip |
| Refreshing | A refresh the user asked for (Refresh) | Content stays interactive; "Updating the schedule…" with an indeterminate 2 dp bar and Refresh disabled |
| Quiet refresh | An automatic refresh: start, resume, the 15-min tick (D-181) | Nothing changes but the 2 dp bar on a strip that already shows; no strip over fresh data. Only the outcome changes the line, so a screen reader hears nothing new while it runs |
| Stale | Older than 6 h on conference days, 24 h otherwise | "Updated 9 hours ago · Refresh" |
| Offline | The last refresh failed with a network error (`Conference.problem == "offline"`; no `ft.Connectivity` before P3) | "Offline · schedule from Tue, May 12, 10:42 AM"; Refresh still tries |
| Not updated | The last refresh got an answer it could not use (`problem == "server"`, D-146) | "Couldn't update · schedule from Tue, May 12, 10:42 AM"; Refresh |
| First load | No snapshot or cache, before the first fetch has failed (rare, NEW-03) | `SkeletonList` |
| No data | No snapshot or cache, fetch failed | `EmptyState` "Can't load the schedule" · "Try again", which stays during a retry with its button disabled (enabled during a quiet refresh, which a tap joins, D-181); the strip says "Offline · no schedule yet" or "Couldn't update · no schedule yet" |
| Empty | Nothing matches | `EmptyState` with a specific way out (§4.6) |
| Not found | Unknown id or slug | `EmptyState` naming the thing, button to its list, on the detail's own level under the back arrow (D-186) |
| Removed | Session left the latest feed while its detail is open (P1, D-186) | Content kept, inline note "Removed from the latest schedule" on `tertiary_container`, a live region |

No blocking loaders (SCHED-28 dropped); never a full-screen error while data exists (SCHED-14).

### 4.2 Freshness and refresh (D-32, D-39, D-40)

- Sources: bundled snapshot, then durable cache, then network; the best local copy renders at once.
- Refresh on start; on resume (from any screen) and every 15 min while Now or Schedule is visible, each once the last refresh began 15 min ago or more, whatever its outcome (so an offline phone retries every 15 min, D-175); on Refresh. The automatic ones are quiet: they never change the strip's line, icon or button; on a strip that already shows, only its 2 dp bar runs, and over fresh data nothing shows; Refresh shows "Updating the schedule…", also when it joins a quiet one (D-181). Time-dependent views recompute every 60 s while visible and in the foreground: the strip's age keeps up, and the strip appears when the data turns stale.
- **GAP** U1 (`RefreshIndicator`): no pull-to-refresh. Interim: the strip's Refresh plus automatic refresh. When U1 is in the pinned Flet, one PR wraps the main lists (D-64).
- A refresh never deletes the cache; a failure keeps the last good data (fixes EVT-07, SPON-08).
- *(P2)* A refresh that changed the schedule shows "Schedule updated · 3 changes" with **Review**; unchanged refreshes are silent.

### 4.3 Search (D-19, D-46, NEW-02, D-193)

- One screen, opened from `SEARCH` on Now, Schedule, Map and More with a preset scope; each opening starts an empty search (D-193).
- `AppBar` "Search" with the back arrow to the opener; under it, pinned above the results, the Speakers filter's pill (`ui/fields.py`'s `SearchField`, D-189, D-193): `prefix_icon=SEARCH`, `hint_text` by scope ("Search sessions, speakers, rooms" in All, "Search sessions", "Search speakers", "Search rooms"), so it agrees with the idle title under it and, shorter, is no longer cut at the largest text, `autofocus=True`, `keyboard_type=WEB_SEARCH`, autocorrect and suggestions off, controlled (D-157), and a Clear button (`CLOSE`, "Clear search") once there is text, which puts the focus back in the field. Not ~~`AppBar(title=ft.TextField(...))`~~: a field in the 56 dp toolbar cannot grow with the text (Flet cannot read the scale, U16), and the pill reflows (D-193). Then the scope `Chip`s All · Sessions · Speakers · Rooms (P1) · Sponsors · Places (P2), the current one selected with its check, in one row that scrolls sideways when it is wider than the screen (wrapped, they took three rows at the largest text and pushed the results under the keyboard). One scope is always on: the chips use `on_click` with `selected` set by the screen, never `on_select`, which toggles the chip on the Dart side (a tap on the selected one would show none selected); a scope change gives `selection_click()` (§4.5). Results in sections when more than one type matched, each under a level-2 type heading without a count ("Sessions", "Speakers", "Rooms": the count line already says "2 sessions, 2 speakers"), a step above the day headings: `TITLE_MEDIUM` in `on_surface`, a `Divider` before every type but the first, and the first day heading right under it (`top=0`); one type alone has no type heading and its day headings take level 2. Sessions are grouped by day (level-3 day headings) as `SessionRow`s with the star (notices as `NoticeRow`s), then `SpeakerRow`s, then rooms as `LinkTile`s with their session count, each pushing its detail. The field's hint wraps to two lines only while it shows. **GAP** U30 (`TextField.text_input_action`, [flet-dev/flet#6962](https://github.com/flet-dev/flet/issues/6962), #221): the keyboard's action key shows Done (Android ✓, read "Done") rather than Search; it still searches at once. When U30 is in the pinned Flet, `SearchField` passes `TextInputAction.SEARCH` whenever it has an `on_submit`.
- 250 ms debounce: the field changes at every keystroke, the search runs once the typing pauses, or at once on the keyboard's action key, a scope chip or Clear; D-180's fold; **all words must match**; over titles, description text (never HTML), speaker names, rooms, and in P2 sponsors, booths and venue places; all days.
- Result taps push details; Back returns to the results with the query intact (§2.5): the Search View stays mounted below the detail, and the query and scope are in `ViewMemory` too (D-18). Search ignores Schedule filters and says so before the first word and on a miss ("Search covers all days and ignores your filters."); a miss in one scope that All would answer offers "Show all results" (§4.6), which, like Clear, goes away when used and so puts the focus back in the field.
- A plain View rather than `ft.SearchBar`: simpler to test, normal Back.
- The field is named "Search" once it holds text (its hint names it while empty); the summary ("12 sessions, 3 speakers") is a polite `Semantics(live_region=True)` line under the chips (`search.count`). Focus on Back: the field gets the focus back only when it had it as the result opened, as Flutter restores a route's focus (D-193). *(could)* Recent queries before typing.

### 4.4 Filters (D-20) and favourites (D-30, D-48)

- **Filters:** only the Schedule has them, as a sheet of chips (§5.3). Whenever a track is hidden, including by default, a summary under the day tabs says so; `TUNE` shows a `Badge` dot only when filters differ from the default (D-20). They persist (the excluded list). My schedule, Now and Search ignore them.
- **Favourites:** one control, the `FavoriteButton` star, on every session row and in the session app bar; swipe-to-favourite is dropped (SCHED-11). Add fills the star with `HapticFeedback().selection_click()` and no SnackBar. Remove shows "Removed from My schedule · Undo", because the row may vanish. When an edit can't be saved (`Change.saved` is False, D-120), its one SnackBar says "Couldn't save your change" instead: it replaces the removal or count message, keeps Undo when there was one, and also shows for an add. Copy is "My schedule", never "favorite" or "successfully". Local, per conference year, no account; sign-out never clears it (D-55). *(P2)* The first favourite may trigger the reminders primer (§4.8).

### 4.5 Feedback (D-29) and haptics

- **Transient result, maybe undoable:** `SnackBar(behavior=SnackBarBehavior.FLOATING, duration=4000, action=SnackBarAction(...))`, one action: "Removed from My schedule · Undo", "Password copied". Flutter keeps a SnackBar with an action until it is used (`persist` defaults to true then), so ours set `persist` to `Prefs.screen_reader`: 4 s for everyone, until used or replaced while TalkBack or VoiceOver is on (D-184).
- **Persistent condition needing action:** `Banner(leading, content, actions)`: "Notifications are off · Open settings", "3 scans haven't synced · Sync now".
- **Data status:** `StatusStrip`. **A result the user waits for** (sign-in errors, scan outcomes): in place.
- **Choice in context:** `BottomSheet(show_drag_handle=True, use_safe_area=True)`: filters, permission primer, lead note.
- **Before something destructive:** `AlertDialog(modal=True)` naming the consequence: "Sign out? 3 scans haven't synced."
- **Unexpected error** (D-71): `@report_errors` shows "Something went wrong" (exception text in developer mode).

Overlays go through `ft.use_dialog(dialog)` or `page.show_dialog(...)`; never close "whatever is on top" with a timed `pop_dialog()`. SnackBars sit above the bar (M3); no top toasts (Flet has no top SnackBar, F11).

Haptics (`ft.HapticFeedback`, coroutines): `selection_click()` for star added, chip toggled, tab re-tap; P3 scans: `light_impact()` accepted or queued, `medium_impact()` twice 120 ms apart for duplicates, `heavy_impact()` then `vibrate()` for denied.

### 4.6 Errors and empty copy

| Case | Icon | Title / body | Action |
|---|---|---|---|
| My schedule empty | `STAR_BORDER` | "Nothing saved yet" / "Tap the star on any session to add it to My schedule. It works offline." | "Browse the schedule" |
| My schedule's saved sessions all gone from the feed (ids kept, D-172) | `EVENT_BUSY_OUTLINED` | "None of your saved sessions is in the schedule" / "The schedule has changed since you saved them. If it lists them again, they come back here." | "Browse the schedule" |
| My schedule unavailable (`Favorites.loaded` is False after the gate, D-172) | `ERROR_OUTLINE` | "Couldn't open My schedule" / "Your saved sessions are still on this device. Close and reopen the app to see them." | none |
| Filters hide a day | `FILTER_ALT_OFF_OUTLINED` | "No sessions on Thursday match your filters" | "Clear filters" |
| A sprint day on the Schedule | `ROCKET_LAUNCH_OUTLINED` | "Monday is a sprint day" / "No talks on sprint days: people work on open-source projects together, and anyone can join one." | "See the sprints" |
| Search miss | `SEARCH_OFF` | "No results for “pydanitc”" / "Search covers all days and ignores your filters." | none; in a narrower scope that All would answer, "Show all results" (D-193) |
| Search before a word | `SEARCH` | "Find sessions, speakers and rooms" ("Find sessions", … by scope) / "Search covers all days and ignores your filters." | none: the field is focused |
| No data, no network | `CLOUD_OFF_OUTLINED` | "Can't load the schedule" (the Map: "Can't load the rooms"; the Tracks hub: "Can't load the tracks", D-199) / "Connect to the internet and try again." | "Try again" |
| Session not found | `EVENT_BUSY_OUTLINED` (the same as "removed", §3.7: a session that left the schedule) | "This session isn't in the current schedule" | "Open schedule" |
| Speaker not found | `PERSON_OFF_OUTLINED` | "This speaker isn't in the current schedule" | "All speakers" |
| Speakers filter miss | `PERSON_SEARCH_OUTLINED` | "No speakers match “zz”" | "Clear filter" |
| Speakers not announced (a feed with no speakers) | `PERSON_OFF_OUTLINED` | "No speakers announced yet" / "They show here as soon as the programme is out." | none |
| Tracks: no sessions announced (a feed with no sessions, D-199) | `SELL_OUTLINED` | "No sessions announced yet" / "Tracks show here as soon as the programme is out." | none |
| Track page: no sessions (a registry track the feed doesn't list yet, D-199) | `EVENT_BUSY_OUTLINED` | "No sessions in this track yet" / "They show here as soon as the schedule lists them." | none |
| Speaker page: no sessions (a directory speaker whose sessions left the feed, D-203) | `EVENT_BUSY_OUTLINED` | "No sessions in the current schedule" / "They show here as soon as the schedule lists them." | none |
| Room not found | `WRONG_LOCATION_OUTLINED` | "This room isn't in the current schedule" | "All rooms" (the Map) |
| Track not found (an unknown slug, D-199) | `LABEL_OFF_OUTLINED` | "This track isn't in the current schedule" | "All tracks" |
| No rooms (the Map, D-188) | `MEETING_ROOM_OUTLINED` | "No rooms yet" / "Rooms appear here once the schedule lists them." | "Open schedule" |
| Page not found (the Router's `NotFound`) | `LINK_OFF_OUTLINED` | "Page not found" / "Nothing in the app is at /x." | "Go to Now" |
| Next year not published | (its screen) | "The {year} schedule isn't out yet" | "Visit us.pycon.org" |
| Sponsor not found (P2) | (its screen) | "We couldn't find this sponsor" | "All sponsors" |

Every empty state names a way out (D-182): its one button, or, where no button can help (the search miss: the query is right there; My schedule unavailable: only a relaunch helps; Speakers not announced, and a hub, track or speaker page without sessions: the app refreshes the feed on its own, D-175), its sentence. The "No data, no network" row reads by the failure (`Conference.problem`): offline, "Connect to the internet and try again."; an answer the app could not use, "The schedule couldn't be read. Try again in a few minutes." The icons are outlined (D-27) and decorative; a screen that shows one of these states reuses its icon, and a case marked "(its screen)" gets one, recorded here, with the PR that builds it. Until the P1 screens, the Schedule stub shows the no-data state and the skeleton, and the session, speaker and room stubs and the Router's `NotFound` show theirs.

### 4.7 Links (INFO-14)

One rule, in `ui/links.py` (D-182): `link_kind(target, *, app=False)` says what a target is, `LAUNCH_MODES` how it opens, and `open_link(svc, target, app=...)` opens it, for `LinkTile` and for `Markdown`'s `on_tap_link` alike.

| Target | Kind | Opens with | Row |
|---|---|---|---|
| An app location (`/more/speakers`, a drill href) | page | `page.navigate`, pushed | trailing `CHEVRON_RIGHT`; a button for screen readers |
| `http(s)` | web page | `svc.launcher.launch_url(url, mode=LaunchMode.IN_APP_BROWSER_VIEW)`, so the attendee stays in context | trailing `OPEN_IN_NEW`, read "Opens in browser"; a link |
| `http(s)` with `app=True` (a social profile, Apple Maps directions), or `geo:` | app | `LaunchMode.EXTERNAL_APPLICATION` | trailing `OPEN_IN_NEW`, read "Opens in another app"; a link |
| `tel:`, `mailto:` | phone, email | `LaunchMode.EXTERNAL_APPLICATION` | no trailing icon (the title is the verb: "Call the Code of Conduct hotline", the subtitle the number); a Copy `IconButton` beside it ("Copy phone number"), level with the leading icon |

- The caller marks a social profile or a map with `app=True`: a host cannot say it (Mastodon has many instances). Only a web address (or a `geo:` link, which opens its app anyway) can be marked; marking a page, a `tel:` or a `mailto:` link is refused with `ValueError`, as is any other scheme (`javascript:`, `file:`, `sms:`).
- There is no `can_launch_url` probe until U6: a simulator, an iPad or a phone without a mail account may do nothing on a `tel:` or `mailto:` tap, which is why Copy is always beside them. When the platform reports a failure, a SnackBar says "Couldn't open the link" (architecture §16.1); a failed copy says "Couldn't copy the phone number" ("…the email address"). Logs name the kind and the error's class, never the target nor the error's text, which repeats it (a `mailto:` holds an address, D-72).
- A copy is confirmed by a SnackBar, "Phone number copied" ("Email address copied"), except on Android 13 (API 33) and later: the system shows its own overlay for every copy, and Android's copy-and-paste guidance asks apps not to add a second one. Android 12 and earlier, and iOS, get the SnackBar.
- **Links in feed texts** (descriptions, bios; D-197): `feed_link(href, site_url)` says what a tapped link opens. `http`, `https` and `mailto` links open as written; a path from the site's root (`/2026/…`) joins the year's site URL; a web address written without its scheme (`pytest.org`, an open-space author's slip) gets `https://`; anything else (another scheme, `#top`, `../x`) opens nothing and says "Couldn't open the link" (not seen on a pushed View such as session detail until #197).
- External rows carry `Semantics(link=True)`. "Opens in browser" is the `OPEN_IN_NEW` icon's `semantics_label`, read after the title in the merged node, not `Semantics.hint_text`, which never reaches Flutter at the pin (#187).

### 4.8 Permissions (D-61)

Never at launch or on Welcome. Notifications (P2): on the first favourite or the first reminder switch, when the reminders capability is present. Camera (P3): on the first staff scan. Check with `await PermissionHandler().get_status(...)` (`flet-permission-handler`) and map its `PermissionStatus` (there is no "undetermined" member): `GRANTED`, `LIMITED`, `PROVISIONAL` → proceed; `DENIED` (never asked, or the OS may ask again) → a one-sentence primer `BottomSheet` ("Get a heads-up 10 minutes before your saved sessions start?", "Allow" / "Not now"), then the request: notifications through the E3 extension's `request_permission()` on both platforms (D-61, F17), the camera through `await PermissionHandler().request(...)`; `PERMANENTLY_DENIED` or `RESTRICTED` → no prompt, a `Banner` with "Open settings" (`await PermissionHandler().open_app_settings()`); `None` → treat the capability as unavailable. §6.9 and §7.2 use the same mapping. A denial never blocks a task.

### 4.9 Time, dates and copy (D-35, DATA-12)

- Times are always conference time (the year's IANA zone). When the device zone differs, Session detail, Now and Settings say "Pacific Time" and the Schedule shows a one-line note.
- 12/24 h follows `page.media.always_use_24_hour_format`; otherwise "9:25 AM". Dates "Fri, May 14"; day headers "Friday, May 14"; ranges "9:25–10:10 AM" (no dash when start equals end); relative "Starts in 25 min" (spoken "Starts in 25 minutes"), "Happening now", "Ended" (`timefmt.time_status()`, D-186).
- US English, sentence case, verbs on buttons, no "successfully", no exclamation marks except the Welcome headline. Years, dates, names and URLs come from data. Spellings: "My schedule", "Open spaces", "Lightning talks", "Help & safety", "Wi-Fi".

---

## 5. Screens: attendee core (P0, P1)

### 5.1 Now · `/now` (P1; SCHED-25, SCHED-26)

**Purpose:** "what should I do next?" in every season. **Entry:** start destination (D-14), tab 1, reminder taps and deep links (P2). Built in P1 (#95, D-190): `screens/now.py`, with the header's words in `screens/now_header.py` and the next-session card in `screens/now_card.py`.

**Layout**
1. `AppBar` "Now" with `SEARCH` (All).
2. **Status header**, a brand moment (D-28): an indigo card, `#3B3EA9` in both schemes (light `primary` with `on_primary`, 8.6:1; dark `primary_container` with `on_primary_container`, 6.7:1; HC uses `primary`/`on_primary`), 16 dp radius, 20 dp padding, 16 dp from the screen's sides: "PyCon US {year}" (`TITLE_SMALL`), a title (`HEADLINE_SMALL`, its weekday moving down whole at large text), a line (`BODY_LARGE`) and, when the device's clock differs, "Times are Pacific Time (PDT)" (`BODY_SMALL`, D-35), in the conference season only, the one whose screen shows times; a decorative 32 dp icon in gold (`#FFD779`, 6.2:1) on the name's line, so the title has the card's whole width, by season: `EVENT_OUTLINED`, `SENSORS`, `ROCKET_LAUNCH_OUTLINED`, `CELEBRATION_OUTLINED`. The words, by season (`now_header.season()`, from D-179's phase and the conference-local date):
   - **Countdown** (before the first day): "Starts in 23 days" ("Starts tomorrow", "Starts today") over "May 13–19 · Long Beach, CA" (`conference.toml`'s first and last days and city).
   - **Conference** (its days with sessions, the evenings and mornings between them, the first morning before its first start, and the last evening): "Day 3 of 5 · Friday" over "First up today at 7:30 AM" before the day's first start, the venue while the day runs, "That's a wrap for today" after its last end.
   - **Sprints** (after the last talk day, to the last day): "Sprints · Monday" over "The sprints run until Tuesday, May 19" ("The last day of the sprints").
   - **Over**: "See you next year" over "Thanks for coming."
3. `StatusStrip(auto_refresh=True)`, when needed (D-175).
4. *(P3)* Staff card: `Card(FILLED)` with `ListTile(QR_CODE_SCANNER, "Scan badges", "Lead scanner · 3 pending")`.
5. **Your next session** (on conference days; `agenda.next_for_me()`: the saved session that starts within 3 h, else the one that is on, D-179): a `Card(FILLED)` holding its `SessionRow` with the star, with its elapsed bar once it is on (from the start its row shows, as its status: the Job Fair's at 9:30, D-186), then its status line ("Starts in 1 h 30 min", then "Happening now" in `live`; session detail's `StatusLine`) and `TextButton("Show room")` (`PLACE_OUTLINED`), which pushes the room's detail with `?highlight=<id>`, in a wrapping row: at large text the button moves under the status whole. The card takes M3's filled colour (`surface_container_highest`), not `primary_container`: on the dark `primary_container` (`#3B3EA9`) the row's supporting lines (`on_surface_variant`) read at 3.7:1. With nothing to show, a `LinkTile` says why and where to look: "Nothing saved yet" / "Tap the star on a session, and your next one shows here" to the Schedule, or, with sessions saved for later, "Nothing saved for the next 3 hours" (in the evening after a day, "Nothing more saved for today") / "See your saved sessions in My schedule" to My schedule.
6. *(P2)* Schedule changes card: "2 saved sessions changed · Review".
7. **Happening now** (while a day runs): a `SectionHeader` after an 8 dp dot in `live` (decorative); the rows with start ≤ now < end except your next session, which the card shows (when it is all that is on, the section is left out: the card says "Happening now"), saved ones first, then in the slot's order, each with a 3 dp elapsed bar in `live`, its end marked by M3's stop dot (`agenda.elapsed_percent()`: from the start the row shows to its end, rounded down; a determinate bar, so it stays under reduced motion, D-173). Breaks and meals that are on are `NoticeRow`s, without a bar. Between two slots: "Nothing in session right now".
8. **Up next · 2:30 PM** ("Up next · tomorrow at 7:00 AM", "Up next · Wed, May 13 at 7:30 AM"): the next slot (`NowNext.up_next`), "Starts in 18 min" on its own day, then its rows except your next session, which the card shows (when it is all that is next, the section is left out: the card says when). The heading is read "Up next, 2:30 PM", as the header reads its "·".
9. `TextButton("See the rest of today in Schedule")` (`CALENDAR_MONTH_OUTLINED`; "Open the schedule" when the next slot is on a later day), on every conference day until the conference's last end, its last slot included, when there is no Up next: opens the Schedule tab, which shows today during the conference; scrolling it to the next slot is the Schedule's (D-155, #89), since the slot may have no item there (D-185).
10. *(P2)* Sponsor spotlight: one `mobile_banner` sponsor per app open, logo on a white tile, "Thanks to {name}, a {level} sponsor" (D-37).
11. *(P2)* Quick info `FilledTonalButton`s: Wi-Fi, Help & safety, Venue & hours.

**Seasons:** the countdown replaces items 5–9 with **Key dates** ("Tutorials and talks", "Wed, May 13 – Sun, May 17"; "Sprints", "Mon, May 18 – Tue, May 19"; the venue and city, from `conference.toml`) and `FilledTonalButton("Build your schedule")`; the last evening and the sprint days show a **Sprints** row ("Join a project · May 18–19") to the Sprints page instead, since the feed has no sessions for them; after the conference, "Look back at the schedule". Recordings join when the data links them.

**Interactions:** rows push the session and Back returns to Now (Ionic returned to the Schedule root). Recompute on the minute tick (`use_minute()`: every 60 s while Now is mounted and the app is in the foreground, and at once on resume, D-175), from `clock.now()`, so the Developer fake clock drives it (D-187). Schedule filters do not apply (D-20). Rows are the memoised session rows (D-184): a minute re-renders only the rows whose bar moved.

**States:** without data, the strip over `SkeletonList("Loading schedule")` until the first fetch has failed, then "Can't load the schedule" with Try again (§4.1, §4.6).

**Accessibility:** the header is the page's first heading (level 1), read as one phrase ("PyCon US 2026. Day 3 of 5, Friday. First up today at 7:30 AM."); the sections are level 2; the live dot and the header's icon are decorative; a row that is on ends its phrase with "60 percent elapsed.", and its bar has no semantics of its own (merged into the row, a bar's value is a bare "60", and Flet's `semantics_value` is a number, read "60.0"); the next-session card's row, status ("Starts in 1 hour 30 minutes"), star and "Show room" are four stops; a "·" is read as a pause and a range's dash as "to" (`now_header.spoken()`: the header, Up next's heading, the key dates, the Sprints row); the elapsed bar's fill reads 3:1 or more on its track and its stop dot 4.5:1 or more on every surface (WCAG 1.4.11), the track itself a hint. Identifiers: `now.header`, `now.next_session` (the tile that says nothing is saved or due), `now.next.session.<key>` and `now.next.favorite.<key>` (the card's row), `now.show_room`, `now.session.<key>`, `now.nothing_on`, `now.schedule`, `now.sprints`, `now.build_schedule`, `now.no_data`.

**Improves on Ionic:** end times respected (Ionic kept the last slot "now" until midnight), a personal next session, seasons, Back to Now (SCHED-25, -26, SESS-12).

### 5.2 Schedule · `/schedule` (P1; SCHED-01..04, -10, -13..17)

**Purpose:** browse the programme and build My schedule. **Entry:** tab 2, Now's link, deep links.

**Layout**
1. `AppBar` "Schedule" with `SEARCH` (Sessions), `TUNE` ("Filter sessions", `Badge(small_size=8)` dot only when filters differ from the default; §5.3) and an overflow (P2 "Schedule changes"; P4 "View source", NEW-09).
2. `ft.Tabs(length=n_days, selected_index=day, on_change=...)` whose `content` is a `Column` of:
   - A scrollable `TabBar` as the first body row (**GAP** U10, no `AppBar.bottom`), one tab per conference day, sprint days included: one-line labels, "Fri 15", in a 56 dp `Tab`, today marked by a 6 dp `primary` dot beside its label, centred on it, so it stays by the digits at every text size (D-192). Two lines ("Fri" / "May 15") clipped at 200 %, since the bar's height is fixed and Flet cannot read the text scale (U16, S2). The label's spoken form is the full date. A day without sessions (sprints) shows an empty state linking to Sprints.
   - Filter summary whenever a track the feed has is hidden, the default included (D-20, D-195): an outlined `FILTER_LIST` mark, "Hidden: Open space" in `BODY_MEDIUM` and `on_surface_variant` (up to three tracks by their badge names, as a list of labels and not a sentence, "Hidden: Talk, Open space", then "and 2 more"), and `TextButton("Show all")`, which hides nothing (`schedule.filter_summary`, `schedule.show_all`), in one wrapping row, so at large text the button moves under the words whole. While nothing is hidden an empty placeholder keeps the line's place, so the day pages below never shift (a shift rebuilt them at their tops, #313).
   - `StatusStrip`; a one-line note "Times are Pacific Time (PDT)" when the device zone differs.
   - `TabBarView(expand=True)`, one day list per day (`screens/schedule_days.py`). The first render fills only the shown day; the other days follow in a second render (D-156).
3. **Day list:** one item per slot (D-31): `Row[TimeGutter, Column[SessionRow...]]` under a 1 dp `Divider`, rows ordered by room; notices, breaks and meals are `NoticeRow`s. Each slot's `Row` sits in a box with `key=ft.ScrollKey(f"slot-{iso}")` (a plain str or int key is never registered for `scroll_to`); the divider stays outside that box, so a jump lands just below it and the tab bar's own line is the only one under the tabs. Each day list is a lazy `ListView`; today's also gets `cache_extent=FULL_LIST_EXTENT`, so Flutter builds all its slots and `scroll_to(scroll_key=...)` reaches any of them (D-154). A lazy list builds only near the viewport, with or without `build_controls_on_demand=False`, and the key then does nothing (F7, F32); building every day in full would cost each day switch about two frames. The busiest 2026 day has 26 slots and 111 rows; S2 measured it (`docs/spikes/02-day-list.md`).
4. Today only: a now line between the last started slot and the next (above the first slot before the day starts, after the last once it has started): "Now · 10:42 AM" in `LABEL_MEDIUM` and `primary` beside a 2 dp `primary` line to the right edge, 16 dp from the sides and 4 dp above and below, in place of the next slot's divider; updated every 60 s while the Schedule shows (`use_minute()`), with today's dot and the button (D-204).
5. Extended `FloatingActionButton(icon=SCHEDULE, content="Now", tooltip="Jump to the current time")` while today has slots, hidden while today's list is within half a screen of where the last jump left it, and while the first display's jump is on its way (a list already in place answers only after its tries, so the button would flash for seconds). A plain distance, since a scroll offset does not say where a keyed item sits: now may still show in the lower half when the button comes back, and a tap then moves it to the top. A scroll away, a slot's start, a refresh or a filter change brings it back. A scroll of the user's own while a jump is waiting ends it as its landing, since a scroll end does not say who scrolled (the pinned `ListView.scroll_to()` returns nothing about where it got to); the next half-screen scroll corrects the button. While TalkBack or VoiceOver is on the button stays, so a tap never removes the focused control and the announcement of where the list went is not cut off; on another day's tab it reads "Today", switches tab, waits for the switch to settle, then scrolls (D-192). After the day's last slot it still reads "Now" and goes to the now line at the list's end (D-204). The lists leave 88 dp under their last slot for it.

**Interactions:** swipe or tap to change day; rows push the session; the star toggles (§4.4). The day defaults to the remembered one, else today during the conference, else the first day. On the first display of each today in the app process (D-204): when the Schedule opens on today (the first render with data, when it opened before any data, NEW-03), or when it opened on another day and the user swipes or taps to today later, `jump_to_key()` (`ui/scrolling.py`) awaits `scroll_to(scroll_key=ft.ScrollKey(target), duration=400)` once the render that shows today's list has been applied, and confirms the landing by the list's scroll end (D-155, D-192; never a computed offset; 0 ms under reduced motion). The target is the slot that is on, else the now line, just above the next slot (`now_place()`, D-204). It never re-jumps on Back, tab return, refresh, filter change or a minute tick (#313), and never twice the same day. The day shown stays put across midnight: the dot moves to the new today and the button reads "Today". Each day keeps its offset (`ViewMemory`): a day that shows again is put back where it was; until U29 a swiped-back day slides in at its top and then jumps there. *(could)* Long-press sheet: Add to My schedule, Share, Open room.

**States:** §4.1; a day emptied by filters and the unpublished year as in §4.6.

**Accessibility:** tabs read "Tab 3 of 7, Friday, May 15, today" (Flutter's tab bar says the position first, D-192). After a "Now" or "Today" tap lands, or finds the list already on the slot, a screen reader hears where: `announce_message("Friday, May 15, 2:00 PM")`, since the day switch made from Python and the scroll are silent; only while a screen reader is on and the platform takes announcements (iOS; Flutter reports none on Android, F13, so TalkBack hears nothing until #223), and never for the first display's jump, which the user did not ask for. Gutter times are headings, so screen readers jump slot by slot; the now line is one node read "Current time 10:42 AM" (`schedule.now_line`), not a live region; after a tap that lands on it, the announcement says the same: "Friday, May 15, current time 2:35 PM".

**Improves on Ionic:** dated day tabs (SCHED-01); gutter for missing sticky headers (SCHED-02); labelled star, no swipe (SCHED-03, -11); global search (SCHED-05, -06); favourites move to My schedule (SCHED-07, -08); visible filters (SCHED-10); no blocking loaders (SCHED-13, -14, -28); scroll once, never on Back (SCHED-15, -16); per-view queries, so filters no longer leak (SCHED-17).

### 5.3 Filter sheet (P1; SCHED-09, SCHED-10, EVT-04)

`BottomSheet(show_drag_handle=True, scrollable=True, use_safe_area=True)` through `ft.use_dialog` from the Schedule's `use_track_filter()` (`screens/schedule_filter.py`; the sheet itself is `screens/schedule_sheet.py`, D-195); not a route. Not `draggable`: Flutter's drag handle is always draggable, and the chips' area scrolls without a drag competing for it. Its slide is off under reduced motion (`AnimationStyle.no_animation()`).
1. "Filter sessions" (`TITLE_LARGE`, the sheet's level-1 heading) with `TextButton("Reset")` (tooltip "Reset to the default: hide Open space", the names from the storage table's default; disabled while the filter is the default, where it would do nothing, and said so: its `Semantics` is disabled too, since Flet's sets `enabled` from its own `disabled`; `schedule.filter.reset`), scrolling with the chips.
2. Filter `Chip`s (`selected`, `show_checkmark=True`, `on_select`, `selection_click()` on a tap), one per track the feed's schedule holds on any day (a chip that changes nothing would be a dead control), labelled by `track_name()` as their badges are, under level-2 headings (`TITLE_SMALL`, `primary`) by `conference.toml`'s `group`, in `TRACK_GROUPS`' order and the registry's: **Talks and keynotes**, **Hands-on**, **Community**, **Breaks and notices** (not "Logistics": a word for organisers). In 2026: Talk, Keynote, Plenary, Lightning talks, AI, Security, Charla, Poster; Tutorial, Sponsor presentation; Open space, Summit, Event; Notice, Break. A key the registry lacks gets its humanised name, after its group's known tracks. Identifiers `schedule.filter.<key>` (`semantics_key()`). An unselected chip shows only its outline on the sheet (M3's filter chip): Flutter draws a chip on a canvas `Material`, which paints `surface` under any chip colour (white on the light sheet, a dark well on the dark one, even with a transparent chip), so the chip paints the sheet's `surface_container_low`. Chips are 8 dp apart across and between rows: at large text a chip outgrows its 48 dp target, and a 4 dp row gap let the rows touch. *(could)* "En Español only".
3. `TextButton("What do these mean?", icon=HELP_OUTLINE)` closes the sheet and opens Tracks & session types (`/more/tracks`; `schedule.filter.tracks`).
4. `FilledButton("Show 87 sessions")`, flat (`elevation=0`, as M3 asks: a styled Flet button gets elevation 1 in every state, and its shadow greyed the disabled button), full width and pinned under the chips, with a live count of the rows the Schedule shows on all days (notices included); closes the sheet (`schedule.filter.show`).

Only the button is pinned: the title, Reset and the chips scroll above it, so at 200 % text the way out stays on screen and the chips keep most of the sheet (pinned, the wrapped title and Reset took about half of it at the largest text); the title and Reset share a wrapping row, so at large text Reset moves under the title whole. The sheet takes the screen's height: no Flet scrollable can be as tall as its content (**GAP** U32, #238). Chips apply immediately to `Prefs`, one edit at a time, so a swipe-dismiss keeps them (Ionic discarded changes) and two quick taps both count (D-195). With all chips off: "Show 0 sessions", disabled, plus "Select at least one type". A chip reads as its name, a button, selected or not (Flutter's `InputChip`). The `TUNE` action's dot (`Badge(small_size=8)`) shows only when the hidden tracks differ from the default's, and its node then says "Changed" after "Filter sessions" (`schedule.filter`), so the dot is not the only signal. Changing the filter never scrolls a list (#313): the memoised path re-renders only the slots whose rows or divider changed (D-153, D-178). Neither the summary nor the count is a live region: on iOS a live region that changes takes VoiceOver's focus (F13), which would pull it out of the sheet at every tap.

### 5.4 Search · `/search` (P1; NEW-02, SCHED-05, SPKR-02, EXPO-04)

A global pattern: §4.3. Route shape per §2.5.

### 5.5 Session detail · `…/session/<id>` (P1; SESS-01..12, NEW-06)

**Purpose:** everything about one session, time and place first. **Entry:** every session row, Now, My schedule, search, speaker and room pages, reminder taps and deep links (P2).

**Layout** (the sections 24 dp apart, §3.6)
1. `AppBar`: back arrow; actions `FavoriteButton` (`session.favorite`), `IconButton(SHARE_OUTLINED, tooltip="Share session")` (#92), `PopupMenuButton(MORE_VERT, tooltip="More options")` ("Open on us.pycon.org", the session's public page, a link read "Opens in browser" (§4.7); P2 "Add to calendar"; P4 "View source"). A session without a public page has no overflow until P2 (D-60, D-186). The title stays empty: the heading below names the page.
2. **Header:** badges in `Row(wrap=True)`, leaving out one that repeats the title (a break's "Break"), 8 dp above the title in `HEADLINE_SMALL`, `selectable=True`, inside `Semantics(header=True, heading_level=1)`; *(P2)* a Changed chip with the old value ("Moved from Room 102A").
3. **When and where** (`ui/when_where.py`, D-186), `Card(OUTLINED)` of `ListTile`s: `SCHEDULE` "Friday, May 15" over "9:25–10:00 AM" (a line each, so the range never breaks in two) with "Starts in 25 min" (on its day only) / "Happening now" (in `live`) / "Ended", kept current by its own minute tick, and "Times are Pacific Time (PDT)" when the device's offset differs (no blank line when there is neither); `PLACE_OUTLINED` with the display location, pushing room detail with `?highlight=<id>`; the other rooms of a multi-room session in an `ExpansionTile` "+4 more rooms" ("In 5 rooms" for a break with no one place; SESS-02).
4. **Registration required** (tutorials, summits, some events): `Card(FILLED)` with `INFO_OUTLINE`, "Register separately" / "Your conference ticket doesn't sign you up for this session." (what to do: the badge above already says "Registration required"), and a `LinkTile` "Check your registration" to `conference.toml`'s `registration_url` (D-186).
5. **Speakers:** `SectionHeader(level=2, top=0)` + a `SpeakerTile` per speaker in the feed's author order (D-197): the Speakers list's 48 dp avatar (the photo over the initials) in a 64 dp row (8 dp above and below it), the name and `CHEVRON_RIGHT`, as the page's other rows that push, with no subtitle (the speaker's page has the bio and the sessions); pseudo-speakers ("Hosted by …") are plain text in `BODY_LARGE`, not tappable (DATA-15), each a node of its own (`session.name.<n>`, D-197).
6. **About:** `SectionHeader("About", level=2, top=0)` + `Markdown(selectable=True, extension_set=MarkdownExtensionSet.GITHUB_WEB, on_tap_link=..., md_style_sheet=...)` over HTML converted once per feed version (D-44, D-114), with the app's style sheet: underlined primary links, headings at 18/16/16/16 sp, below the screen title and under the section (D-116, D-197); one builder, `ui.links.feed_markdown()`, for every feed text. A tapped link opens by `feed_link()` and the link rule (§4.7, D-197). Keynotes and panels add an eyebrow, abstract and speaker cards from `content.toml` (SESS-08).
7. When relevant: the posters list "Posters (25)" (SESS-09); *(P2)* the job fair `LocationCard` (SESS-10); the open-space image and link (SESS-11). *(could)* "Also at this time".

**Interactions:** Share (NEW-06) uses `await ft.Share().share_text("<title>\n<day> <time> · <room>\n<url>", share_position_origin=origin)` (the origin anchors the sheet on tablets, D-09); the URL pattern comes from `conference.toml` and applies to numeric ids only. *(P2)* Add to calendar shares an `.ics` (UTC, stable UID, `VALARM` 10 min) with `await ft.Share().share_files([ft.ShareFile.from_bytes(data, mime_type="text/calendar", name=f"{slug}.ics")], share_position_origin=origin)` (D-62, SESS-05); the native prompt waits for E4 (SESS-04).

**States:** renders from cache instantly; not found per §4.6 on its own level (Ionic rendered a blank page); removed while open keeps the content under an inline note (§4.1, D-186).

**Accessibility:** title is heading level 1, sections level 2; each "When and where" tile is one phrase: the time tile "Saturday, May 16, 10:30 to 11:00 AM, Starts in 25 minutes", the room tile "Room 103ABC, button". Markdown links stay inline: on Android each is its own focusable node named by its text (S3, D-116). VoiceOver gets the link trait; Android's bridge turns a text link without a URL into a button, so TalkBack says "button" (F41, D-197); the P1 accessibility pass (#109) hears both.

**Improves on Ionic:** time and place first (SESS-01); one room tile (SESS-02); labelled synced star (SESS-03); keynote data, not hard-coded copies (SESS-08); a real back stack, not `prevUrl` (SESS-12); working Share (NEW-06).

### 5.6 My schedule · `/my-schedule` (P1; NEW-01, SCHED-07, -08, -12)

**Purpose:** the personal agenda, in time order, with conflicts. **Entry:** tab 3, Now's next-session card.

**Layout (D-191):** `AppBar` "My schedule" with an overflow (P2 "Export to calendar (.ics)" for all saved sessions and "Reminder settings"); `StatusStrip` (no automatic refresh, D-40); a lazy `ListView` where past days collapse into one `ExpansionTile` "Earlier days (6 sessions)" (`HISTORY` icon), then a `SectionHeader` per day and gutter slots (`TimeSlot`) holding only saved sessions. Today's ended sessions (`end <= now`) collapse into a second tile under today's header, "Earlier today (4 sessions)"; a slot whose sessions end apart splits, so a tutorial that is still on stays. The tiles' titles are `BODY_MEDIUM` in `on_surface_variant`, quieter than the day header above them, the count joined to its noun by a no-break space. Both tiles start collapsed (the "Earlier today" open state belongs to its date, so the next day's starts collapsed), open on `surface_container_low`, and re-fold every minute while the screen shows (`agenda.fold_ended()`, `use_minute()`). Overlapping rows still to come both end with `WARNING_AMBER` and "Overlaps with “Typing deep dive”" in `warning`, the name cut at three lines like a title, and "and 2 more" on a line of its own, so the cut never hides the count (as the Map's "Now:" line, D-188): a hint, not a blocker. Only a clash that can still change a plan shows: a folded row has no line, and a clash with a session that has ended is dropped. *(P2)* Changed chips. *(could)* "Free 11:00 AM–1:30 PM · See what's on".

**Interactions:** unstarring removes the row at once, with "Removed from My schedule · Undo", which puts it back (§4.4); a clash line on the other row goes and comes back with it. The list never scrolls to today on its own: with the past folded, today's header is already the second item (D-191 replaces the once-per-session `scroll_to` to `day-<iso>` and its `cache_extent`). The tab's offset in `ViewMemory` (§2.4) is a separate, open item. Schedule filters never apply: a saved open space always shows.

**States:** unavailable, no data and empty per §4.6, in that order; all past: a compact notice above the "Earlier days" tile, start-aligned on the tile's text column rather than the full-screen state, "All your saved sessions are over" (`TITLE_SMALL`, `EVENT_AVAILABLE_OUTLINED`) with "See what's on today" (to Now) while today is a conference day, and after the last day "<name> is over. Your saved sessions stay here." (the year data's name, "PyCon US 2026") with no button; saved sessions that the feed no longer lists at all: "None of your saved sessions is in the schedule" (§4.6), not "Nothing saved yet"; *(P3)* after the first mock sync a one-time "Synced with your account" (D-55).

**Accessibility:** the overlap is the last sentence of the row phrase, naming every clash ("Overlaps with “A”, “B” and “C”."); the all-over notice's title is a level-2 heading in a live region; day headers are marked as headers, and get their level with #205 (F40); the tiles are Flutter's `ExpansionTile`s (`FoldTile`, D-191), which say expanded or collapsed.

**Improves on Ionic:** a place instead of a toggle with a hidden all-days mode (SCHED-07, -08); conflicts; local-first (SCHED-12).

### 5.7 Speakers · `/more/speakers` and `…/speaker/<id>` (P1; SPKR-01..03)

- **List** (D-189): `AppBar` "Speakers"; a filter field pinned above the list, so it stays in reach in a long list: a controlled `TextField(prefix_icon=SEARCH, hint_text="Filter speakers", filled=True, fill_color=surface_container_high, border={DEFAULT: pill, FOCUSED: pill}, autocorrect=False, enable_suggestions=False)`, the pill an `OutlineInputBorder(border_radius=28)` without a line, at rest and focused, like Material's search bar, whose cursor and keyboard mark the focus (D-157; full radius, §3.6), with a Clear button (`CLOSE`, "Clear filter") once there is text, laid over the field's end in a `Stack` rather than as its suffix. The field sits in `MergeSemantics(Semantics(label="Filter speakers"))` once there is text: the hint, its only name, leaves the semantics tree then, a labelled `Semantics` alone would be a second node above the field, and the merge would swallow a Clear button inside the field. It narrows the list at every keystroke, with no debounce, by search's own matching: accents and case ignored, every word anywhere in the name (SPKR-02, D-180); a filter with no word to match (a lone `’`) keeps the whole list. While a filter finds someone, a `BODY_SMALL` line in `on_surface_variant` under the field says how many ("5 speakers"), a live region, so a screen reader hears what typing did (§9). Either Clear goes away when used, so clearing puts the focus back in the field, ready to type again (D-182's reason). Below it, a lazy `ListView` of letter sections, each one memoised item (a `SectionHeader` and its `SpeakerRow`s, D-153), sorted by displayed name, folded (D-46); a speaker's letter is the first character of the folded name, so `Élodie` is under E, `Łukasz` under L, and a letter without a Latin base under its own heading after Z (`Жанна` under Ж). No paging, no loader with data, no pseudo-speakers (D-125). No match: "No speakers match “zz”" + "Clear filter"; a feed with no speakers yet: "No speakers announced yet" (§4.6). *(could)* An A–Z index (**GAP**: no fast-scroll control).
- **Detail** (`screens/speaker.py`, #99, D-203): `AppBar` with an empty title, as session detail's (D-186), and Share only when a public speaker URL exists in the year data (none yet); centred, the speaker's photo over their initials (`speaker_avatar(radius=48)`, a 96 dp circle, decorative) and the name (`HEADLINE_SMALL`, the page's level-1 heading, selectable; `speaker.title`), which wraps where an app bar title was cut; no track badges, since every row shows its own. Then "when do they speak", before the bio: every session that links the speaker (`speakers.speaker_sessions()`, poster details included, in the Speakers list's order), under a level-2 heading per day, each day the memoised `DayGroup` of search and the track pages, as `SessionRow`s with their stars (`speaker.session.<key>`, `speaker.favorite.<key>`). The rows leave out the speaker the page names: the speakers line names only the co-speakers, "With Robert Masson", and is gone when the speaker is alone, in the row and its phrase alike (`session_view(of_speaker=...)`). Then **About** (level 2) and the bio through `feed_markdown()` (`speaker.bio`; D-116, D-197), left out when the feed has none or only its placeholder "-" (`has_bio()`). A row pushes its session, whose speaker tile pushes a speaker again, so session → speaker → session → room is a stack Back pops one step at a time (SESS-12). A speaker the feed links to no session: "No sessions in the current schedule" where the days would be, the bio still below (§4.6). An unknown id: "This speaker isn't in the current schedule" with "All speakers" (§4.6), under the back arrow; without data, the skeleton, then "Can't load the schedule" with Try again. Ionic's banner and gold ring are dropped (they ignore dark and HC).

### 5.8 Map · `/map` (Rooms P1, other panes P2; ROOM-01, MAP-01..03, MAP-07, MAP-08)

- **P1 (D-188):** `AppBar` "Map" with `SEARCH` (Rooms); the body is the Rooms list (`core/rooms.py`'s `room_list()`): a `SectionHeader` "Rooms" over the rooms in natural sort (`slugs.room_sort_key`; grouped by floor from `map.toml` in P2), then "Other locations" over the places that are not rooms (`content.toml`'s `other_locations`: Elsewhere, Lobby, Out Front of Hyatt Regency in 2026). Each row is a `LinkTile` (`PLACE_OUTLINED`, the room's name, trailing `CHEVRON_RIGHT`) whose subtitle is "26 sessions" ("1 session") and, only while something is on, a second line "Now: Building X" in `Tokens.live` (at most three lines, as a session row's title; when several are on, the one that started last is named and a line of its own, "and 1 more", follows, so the ellipsis never hides it). The count is every session listed under the room, poster details included (as ROOM-02's detail lists them; Expo Hall AB 35), and keeps its place under the name in every row; one node reads "Room 103ABC, 26 sessions, Now: Building X"; identifier `map.room.<slug>`; a tap pushes `…/room/<slug>`. "Now:" follows Now & Next's rule (D-179: `start <= now < end` over the timeline, so a poster detail stays inside its Posters row and a notice is never on) and `clock.now()`, recomputed on the minute tick (`use_minute()`, D-175). *(P2)* seeded sprint-only rooms read "Sprints" (MAP-08). States: without data, the status strip and `SkeletonList` "Loading rooms" until the first fetch has failed, then "Can't load the rooms" with Try again (kept, its button disabled, during a retry); data without rooms, "No rooms yet" with "Open schedule" (Ionic showed "Loading rooms…" forever). No control for the P2 panes.
- **P2:** the body becomes `Tabs` with **Rooms · Floor plans · Expo · Job fair** as the first row and a `TabBarView`. The selected pane and each pane's zoom live in `ViewMemory` (D-18; Ionic destroyed panes). Map panes never scroll the page, so pans are not stolen. Overflow "3D venue tour" opens Concept3D in the in-app browser (no iframe). Search scope becomes Places (rooms, booths, venue spots).
- **Floor plans:** `Card(OUTLINED)` per plan with a 16:10 thumbnail, title, subtitle and `OPEN_IN_FULL`, in Ionic's order; a tap pushes the floor viewer (§6.1).

### 5.9 Room detail · `…/room/<slug>` (P1; ROOM-02..04)

**P1 (#101, D-194):** `AppBar` with the room name (`screens/room.py`, its day lists in `screens/room_days.py`); *(P2)* `LocationCard`; then a scrollable day `TabBar` of the Schedule's tabs (`schedule_days.day_tab()`, §5.2), one per day the room has sessions ("Fri 15", read "Friday, May 15"; today's with its dot and ", today"; `room.day_tab.<n>`), opening on the highlighted session's day, else today, else the first day (ROOM-02); a `TabBarView` of day lists in time slots (D-31): `TimeGutter`, `SessionRow`s and `NoticeRow`s with display names (Ionic showed "Ai"), a divider between slots. Today's list starts, while something is on there, with **Now in this room**: a level-2 `SectionHeader` with Happening now's `live` dot (§5.1) over one `LinkTile` to the session that started last (`rooms.room_now()`, Now & Next's rule, as the Map's "Now:" line, D-179, D-188): its name cut at three lines, its time in `Tokens.live` (and its place only when it is given elsewhere, the lightning talks' Arena, the two in a wrapping row as a row's meta), "and 1 more" on a line of its own when several are on, and a divider that closes the section, so the first slot does not read as its second item; identifier `room.now`; a leaf component on the minute tick (`use_minute()`, D-175), so the fake clock drives it. It heads today's list rather than sitting above the tabs: at the largest text it filled half the screen there and left the slots a quarter (D-194); in the list it scrolls away with them. A pointer, not a `SessionRow`: the session's row, with its star, is below it. A room's rows leave out the room's own name, which the title already says: the meta shows the time alone and the phrase says no place (`session_view(..., in_room=slug)`); a place elsewhere stays (the lightning talks streamed to Grand Ballroom A say "Pacific Ballroom - Arena"). **Highlight:** with `?highlight=<id>` (`use_query()` until U9), an id of this room's sessions compared as a string (Ionic's number-vs-string compare never matched; any other id is ignored), that row's box carries `key=ft.ScrollKey(f"session-{id}")` and a `primary` tint at 16 %; when the row has its slot to itself the box is the whole slot, its time too, edge to edge as an M3 selected list item, with the slot's divider above it, as the Schedule's (§5.2), and only a row that shares its slot is lit alone (not `primary_container`, whose dark tone puts the rows' supporting text at 3.7:1; the tint keeps 5.0:1 in light and 5.9:1 in dark, D-194). After a round trip, the shown day's list, built in full (`FULL_LIST_EXTENT`, D-154; `build_controls_on_demand=False` would not register a far key, F32), scrolls the row to its top once with the Schedule's `jump_to_key()`: 400 ms, a jump under reduced motion, confirmed by the scroll's end (D-155). The row stays lit 2 s once in place, then the tint fades in 250 ms; under reduced motion it simply goes (D-173). Returning never re-scrolls: Back finds the View mounted and drops the query, and `ViewMemory.room_highlights` keeps a View rebuilt in a new session (D-143) from scrolling or lighting up again (D-18); leaving the room clears it, so the next room tile highlights again. An unknown slug: "This room isn't in the current schedule" with "All rooms" (§4.6), on its own level (D-186).

### 5.10 Tracks & session types · `/more/tracks[/<slug>]` (P1; SCHED-21, -22, -24, EVT-04)

- **Hub** (`screens/tracks.py`, #102, D-199): answers "what is a charla?" and "show me the charlas" in one place. Rows under level-2 `SectionHeader`s for the registry's groups (`conference.toml`'s `group`): Presentations (`talks`), Hands-on, Community; the `logistics` group (breaks, notices) is not a session type and is left out, and so is a track without sessions in the current feed. Each row, built like `SpeakerRow` so it reads as one phrase: a 40 dp circle in the track's badge colours (`Tokens.track_badge()`) holding its registry icon, so the hub is also the key to the badges' colours; the plural name (`TITLE_MEDIUM`); the legend line (`BODY_MEDIUM`, `on_surface_variant`; "Talks given in Spanish", year data); then, in one wrapping row, the track's badge as rows show it, "New track" (outlined in `primary`, §3.4) when `new = true`, and the count ("16 sessions", as the track page lists them: every poster, not the Posters row); a trailing `CHEVRON_RIGHT`. Read "Charlas. Talks given in Spanish. Charla, 16 sessions.", a button (a badge that repeats the name is not read twice: "Lightning talks. Five-minute talks, back to back. 4 sessions."), identifier `tracks.track.<slug>`; a tap pushes `/more/tracks/<slug>`. Every track row pushes its track page; the Keynotes, Lightning talks and Open spaces pages (#104, #105) point their rows at themselves when they land, and the Sprints page (#106) adds a Sprints row. States: without data the skeleton ("Loading tracks"), then "Can't load the tracks" with Try again; a feed without sessions, "No sessions announced yet".
- **Track page** (`screens/track.py`, #102, D-199): the app bar keeps an empty title, as session detail's does (D-186): the intro holds the badges every row would repeat, the track's and, on Charlas, where every session is in Spanish, "En Español", then "New track"; then the plural name as the page's heading (`HEADLINE_SMALL`, level 1, `track.title`), which wraps where an app bar title was cut at large text ("Trailblazing Python Se…"), and the legend line (`BODY_LARGE`, `on_surface_variant`). Then a lazy list of days, each a memoised item (`ui/day_groups.py`'s `DayGroup`, shared with search) under a level-2 day heading, of `SessionRow`s with the star (`track.session.<key>`, `track.favorite.<key>`), no paging. The rows leave out the badges the intro shows (`DayGroup(omit=...)`, D-199), as session detail leaves out a badge that repeats its title (D-186): a line per row, and a sentence per row for screen readers, saved; "Registration required" stays. The posters track lists the 25 posters, not the collapsed row (SCHED-22); the Schedule's filter never applies (open spaces show on their page). *(#103)* An overflow "Add all to My schedule" that covers every session of the track and goes straight to a SnackBar "Added 16 sessions · Undo" (no dialog: it is reversible, D-29; SCHED-24), "Added 1 session · Undo" for one, and "All of them are already in My schedule" with no Undo when nothing was new; not on open spaces. Clean slugs written in the year data (`charlas`), not Ionic's `ais`/`lightning-talkss` (DATA-29); an unknown slug shows the not-found state under the back arrow (§4.6). Without data the skeleton, then "Can't load the schedule" with Try again; a track without sessions in the feed, "No sessions in this track yet".

### 5.11 Keynotes, open spaces, lightning talks, sprints (P1; SPKR-04, EVT-01..08)

- **Keynotes** (`/more/keynotes`): one `Card(ELEVATED)` per keynote or panel from `content.toml` (shared with SESS-08; the loader fails loudly on unknown session ids): photo `Image(width=96, height=96, border_radius=48, fit=BoxFit.COVER, error_content=initials)`, name, role, a 4-line bio with "Read more", and a time-and-room `ListTile` with a star. Panels show a wrapping row of 64 dp avatars.
- **Open spaces** (`/more/open-spaces`): `IconButton(ADD, tooltip="Propose an open space")` opens the sign-up URL from data; an intro line; a day `TabBar` derived from the data (Ionic called every other day "Sunday"); gutter slots of saveable rows with an optional 56 dp thumbnail. None yet: "No open spaces yet" + "Propose one".
- **Lightning talks** (`/more/lightning-talks`): one page replacing Ionic's static page and track list: a `Card(FILLED)` with the year's copy and `FilledButton("Sign up for a lightning talk")`, a collapsed `ExpansionTile` "Think you can't do one?", the sessions with stars, and a "More info" `LinkTile`.
- **Sprints** (`/more/sprints`): overflow "Sprint info on us.pycon.org" and "Submit a sprint project"; intro with dates from data; an inline filter (all words over name, submitter and description text, EVT-06); `Card(OUTLINED)` per project with logo (`fit=BoxFit.CONTAIN`, initials fallback), name, "by <submitter>", a 4-line description with "More", and "Project page". None yet: "No sprint projects yet" + "Submit a project". Refresh never wipes the cache (EVT-07).

### 5.12 About this app · `/more/app` (P1 minimal, P2 full; INFO-03, INFO-04)

**P1 (#88, D-187):** an opening block on `surface` (no brand band, D-28): the app's name (`HEADLINE_SMALL`, a heading), "A companion for {conference}, built with Python and Flet." (`BODY_LARGE`) and "Not an official PSF app." (`BODY_MEDIUM`, `on_surface_variant`; D-36); then a **This build** `SectionHeader` over two-line `ListTile`s: **Version** (`pycon_us.__version__`; identifier `about_app.version`), **Python** (`platform.python_version()`) and **Flet** ("source build" while the app builds from the pinned checkout, development.md §2.2). No build number until U4 (**GAP**): a packaged app's Python cannot read it (D-187). Seven taps on the version row unlock Developer in a packaged build, for good (D-187): the 7th adds a **Developer options** row under Flet ("On"; identifier `about_app.developer`; a live region, so a screen reader says it), which opens Developer. It is said in place, not in a SnackBar, because a SnackBar from a pushed View shows on the tab root under it (#197). Once it is on (always when not embedded), the row is there and taps do nothing more.

**P2 (#30):** "Conference data updated 2 h ago" and its source; links to the repository (once public, D-88) and flet.dev; licences; "Report a problem with the app"; "Share log": `console.log` via `ShareFile.from_path` plus plain diagnostics, never secrets, emails or badge codes (D-72).

### 5.13 Developer · `/more/developer` (P1, grows by phase; DEV-01, DEV-04..06, D-73)

Always available when not embedded; in packaged builds after the unlock (before it, the page says how to unlock and links About this app). The title is "Developer options", and a `warning`-tone "Developer" chip (label and 1 dp outline in `Tokens.warning`, text only as §3.4's badges, not interactive) opens the page, above its intro line: in the app bar it pushed the title out at 200 % text (D-187). **P1 (#88, D-187),** from the top: one line on what it is for; **Clock**: the **fake clock** field (`developer.fake_clock`; ISO 8601, in conference time when it has no offset; "YYYY-MM-DD HH:MM, in Pacific Time. Empty for real time."), whose trailing `EDIT_CALENDAR_OUTLINED` button opens a Material `DatePicker`, then a `TimePicker` ("Fake clock time, Pacific Time"), which fill it and open on the first day at 09:00 while it is empty; a **Time zone** row (the conference's zone and this device's UTC offset); **Schedule feed**: the **feed URL** field (`developer.feed_url`; "Empty for the year's feed. Used from the next refresh."); both fields wrap their value to three lines at large text; **Reset** (`OutlinedButton`, `developer.reset`: real time and the year's feed again) and **Apply** (`FilledButton`, `developer.apply`), end-aligned and wrapping at large text; an error under a field that does not parse, and after Apply or Reset a start-aligned line under the buttons that says what is in effect ("Applied: a fake clock in Pacific Time and your feed URL."; `developer.outcome`, a live region; after a `CHECK_CIRCLE_OUTLINE` in `success`, or a `WARNING_AMBER` in `warning` when the save failed; in place for the reason above, #197), cleared by the next edit; **Data** (#107, D-198; `screens/developer_data.py`): four two-line action rows, a verb first and what it touches below, each one merged node, a disabled row's reason in `on_surface_variant` rather than the disabled 38 %, so it stays readable: **Refresh now** (`REFRESH`, `developer.refresh_now`; its second line where the schedule on screen came from and its age, "From the cache, updated 3 hours ago", which the minute tick (`use_minute()`) keeps current while the screen is open; disabled with "Updating the schedule…" and a small indeterminate `ProgressRing` at its end while a refresh the user asked for runs, D-181), **Clear cached feed** (`DELETE_OUTLINE`, `developer.clear_cache`; "The next start shows the bundled schedule", or disabled with "No cached schedule on this device"), **Share log** (`SHARE_OUTLINED`, `developer.share_log`; the share sheet with `console.log`, D-72, D-196; in a packaged build only, else disabled with why) and **Reset app** (`RESTART_ALT`, `developer.reset_app`; icon and title in `error`; "Deletes your settings, saved sessions, the cached schedule and the Developer options"); under them a line that says how the last one ended (`developer.data_outcome`, a live region, as Apply's; both lines put their icon in a 24 dp slot and their words 16 dp after it, in the tiles' text column). Clear cached feed and Reset app first show a modal, scrollable `AlertDialog` with the row's icon (Reset app's in `error`, as its row), a question for a title ("Clear the cached schedule?", "Reset the app?"), what is lost (Reset app: one line each, beside a decorative icon, with the saved sessions' count), then Cancel and the action in `error` (`<row>.cancel`, `<row>.confirm`); Back cancels (on Android it also leaves the page, #235). Reset app then clears every stored setting, the favourites and the cache, resets every store in memory without a restart and goes where a fresh start goes (Now; Welcome from P2), where a SnackBar says "App reset" (D-198); *(P2)* "Test reminder in 5 s" with the outcome inline (scheduled, muted, denied, not available in this build) and "Show welcome again"; *(P3)* the mock API base URL and "Clear staff data" (confirmed).

---

## 6. Screens: conference companion (P2)

### 6.1 Floor viewer · `…/plan/<plan>` (ROOM-05, MAP-05, INFO-13)

A pushed full-screen View with an `AppBar` (back arrow, plan title, overflow "Reset view") over a `Stack`:
1. `InteractiveViewer(min_scale=1, max_scale=natural_width / displayed_width, boundary_margin=...)` around `Stack[Image(fit=BoxFit.CONTAIN, semantics_label="Concourse level floor plan, Room 104C marked"), pin]`. The pin is placed from percentages once `on_size_change` reports the size. Flet's defaults (max 2.5, min 0.8) are overridden.
2. A label `Card` outside the zoom layer, bottom-left in `SafeArea`: "Room 104C · Concourse level · Talk track", readable at any zoom.
3. Zoom buttons bottom-right (`ZOOM_IN`, `ZOOM_OUT`, `CENTER_FOCUS_STRONG`), async handlers calling `await viewer.zoom(1.5)`, `zoom(1 / 1.5)`, `reset(animation_duration=250)`: the single-pointer alternative to pinch (WCAG 2.5.1).

Pinch, pan, and double-tap (`GestureDetector(on_double_tap=...)`) for 2× or reset. The pin pulses twice, then stays still. Plans are re-encoded to ≤ 2048 px (S7 checks memory and tap accuracy).

### 6.2 Expo hall · Map › Expo and `plan/expo?booth=<n>` (EXPO-01..05, SPON-04)

- **Map | List** `SegmentedButton`; List first when the OS reports `accessible_navigation`.
- **Map:** the viewer's zoom layer over the hall, with one hit area per booth: a `Container` placed from ratio geometry in `map.toml`, faintly outlined at all zooms, in `Semantics(button=True, label="Booth 613, Bloomberg")`. Background `surface` (Ionic letterboxed in near-black).
- **Tap a booth:** it is selected (amber `#F2C14E` with a dark 2 dp outline, passing 3:1; Ionic's highlight was 1.7:1) and a **BoothCard** appears, a `Card` positioned at the bottom of the outer `Stack` in `SafeArea` (a modal sheet would block the map): logo, name, "Booth 613 · Visionary", `FilledTonalButton("Sponsor details")`, `TextButton("3 open roles")` when hiring, a 48 dp close.
- **List:** booths by number with a `Chip("Sort by name")`; a row selects the booth on the map.
- **`?booth=<n>`:** that booth selected with its card, no camera move; animated zoom waits for **GAP** U3 (EXPO-05 `later`). An unknown booth opens the List with "Booth 139 isn't on the map yet". Sponsor "Find booth" pushes this view, so Back returns to the sponsor.

### 6.3 Job fair · Map › Job fair (MAP-04, SPON-10)

The viewer (no pins) above sponsors with a table number, sorted by table: "T2 · Sentry · 5 roles"; a row pushes the sponsor.

### 6.4 Schedule changes · `/schedule/changes` (NEW-04, D-47)

**Entry:** "Schedule updated · Review", the Now card, Schedule's overflow, Settings › Data. `AppBar` with overflow "Mark all as seen"; "Affects My schedule" first (when it does), then "All changes"; groups by detection time ("Today, 10:42 AM"). Items: `ListTile(leading=Icon(CHANGE_CIRCLE_OUTLINED | EVENT_BUSY_OUTLINED | NEW_RELEASES_OUTLINED), title=..., subtitle=Text(spans=[TextSpan(old, style=TextStyle(decoration=TextDecoration.LINE_THROUGH)), TextSpan(" → "), TextSpan(new, style=TextStyle(weight=FontWeight.W_600))]), trailing=FavoriteButton)`. Unseen items have a 6 dp `primary` dot, seen 2 s after opening. A tap pushes the session; a removed one shows its last data with "Removed from the latest schedule" (never "cancelled": the feed's flag is always false). Empty: `HISTORY`, "No changes yet". Items read as sentences ("Building X: room changed from 102A to 103ABC. In My schedule."); strikethrough is never the only cue.

### 6.5 Sponsors · `/more/sponsors` and `…/sponsor/<slug>` (SPON-01..05, SPON-09)

- **List:** intro "PyCon US is possible thanks to these organizations."; a `SectionHeader` per level in `level_order`; the top level as full-width `Card`s (logo on a white plate, name, booth), the next two as `GridView(max_extent=200)` logo cards, the rest as `ListTile`s with a 48 dp white plate and "Booth 613". White plates keep dark logos legible in dark mode; `Image(error_content=initials)` offline. One node each: "Bloomberg, Visionary sponsor, booth 613". *(could)* "Has a booth", "Hiring" chips.
- **Detail:** logo on a white plate (max 240 × 96) and a level `Chip`; a wrapping row of labelled actions, `FilledTonalButton(icon=STOREFRONT_OUTLINED, ...)` "Find booth 613", `OutlinedButton(icon=GROUPS_OUTLINED, ...)` "Job fair table T2", `OutlinedButton(icon=OPEN_IN_NEW, ...)` "Website"; **About** as selectable plain text keeping newlines; **Open roles** as `LinkTile`s parsed from real `<a href>` anchors (Ionic collapsed them into one unlinked paragraph). Slugs reproduce Ionic's exactly (SPON-02). Not found per §4.6.

### 6.6 Job listings · `/more/jobs` (SPON-06..08)

A job-fair `LocationCard` (pushes `plan/job-fair`); an inline search (250 ms, all words over company, role titles and plain text, never raw HTML); one `Card` per sponsor with a header row (logo, name, level chip, chevron to the sponsor) and role `LinkTile`s, "Show all 15 roles" past 5. No match: "No roles match "rust"" + "Clear search". Empty feed: "No job listings yet."

### 6.7 Info pages (INFO-01..14, MAP-09..11)

`AppScaffold`, title always visible, max 720 dp, content from `content.toml` (else converted feed HTML), rendered instantly with no modal loader (INFO-05).
- **About PyCon US** (`/more/about`): a compact indigo band (name, dates, city; the third brand moment, D-28), the about text as `Markdown`, links to Help & safety, Venue & hours and the website.
- **About the PSF** (`/more/psf`): the mission once (Ionic showed it twice); "Get involved", "Python resources", "Follow the PSF" `LinkTile`s with brand SVGs; `FilledButton("Donate to the PSF")`.
- **Help & safety** (`/more/help`; merges CoC and Help, INFO-07, INFO-11): first in reading order, a **Report a concern** `Card(OUTLINED)` with an `error` outline and two large rows, "Call the CoC hotline" (`tel:`) and "Email the CoC team" (`mailto:`), each with Copy and an explicit label ("Call the Code of Conduct hotline, 562 662 4082"); then Information desk, Lost & found and Quiet room `LocationCard`s, the CoC summary and full text link, "Report a problem with the app". Contacts only from a verified public source, re-checked yearly (D-45).
- **Wi-Fi** (`/more/wifi`): network and password as selectable `TITLE_LARGE` text with Copy; `FilledButton("Copy password")` → `ft.Clipboard().set(...)` → "Password copied"; "Wi-Fi by <sponsor>" from an explicit slug (Ionic matched "temporal").
- **Venue & hours** (`/more/venue`): address `Card` with "Directions" (by `page.platform`: Apple Maps on iOS, `geo:` on Android, `EXTERNAL_APPLICATION`) and "Copy address"; a `Card` per service (Registration, Information desk, Swag pickup, Quiet room, Lost & found, Luggage) with hours (today in bold), a status chip ("Open now" in `live`, "Opens 7:30 AM", "Closed today"), a `LocationCard` and "Sponsored by" from data.
- **Social media** (`/more/social`): hashtag `Chip`s that copy on tap (Ionic's did nothing); `LinkTile`s with brand SVGs, opened externally; the X logo follows the text colour.

### 6.8 Welcome · `/welcome` (SHELL-02, STORE-07)

No bar; full-bleed `#680579` in both themes, in `SafeArea`: the app icon (O-4; decorative, since the headline names the event), never the PyCon logo unless O-4 decides otherwise (D-36); "Welcome to PyCon US {year}" (`HEADLINE_SMALL`, white); "Long Beach, CA · May 12–18" (data); three icon rows ("Plan your schedule and save sessions", "Find rooms, booths and hours, even offline", "Get reminders before the talks you saved", the last only when reminders exist); a full-width `FilledButton("Get started")` that sets `pycon.onboarded` and replaces the route with Now; *(P3)* "Sponsor or staff? Sign in" when a mock URL is set; footnote "Built with Python and Flet by the community · Not an official PSF app". No permission prompt. After the conference: "Thanks for coming. See you next year."

### 6.9 Settings · `/more/settings` and reminders (THEME-01, NOTIF-01..10, NEW-05)

1. **Appearance:** a `RadioGroup` of `Radio` rows System (default) / Light / Dark; a `Switch` "High contrast" defaulting to the OS flag where reported (iOS, Android 34+), re-read on resume (D-23). Applied at once.
2. **Reminders** (D-58..D-60): a permission card only when needed, mapped as in §4.8 (`DENIED` → "Allow notifications"; `PERMANENTLY_DENIED` or `RESTRICTED` → "Notifications are off in system settings." + `OutlinedButton("Open settings")`). Timing is inexact (D-59); an exact-timing option is considered only if S6 shows inexact reminders are too late; "Remind me before sessions in My schedule" `Switch` with a 5 · 10 · 15 min `SegmentedButton`; "Conference moments" (keynotes and panels, lightning-talk and open-space sign-ups, times from `content.toml`); *(could)* the next 5 reminders. Push-only categories, the master toggle and the FCM card are not shown (NOTIF-02, -04, -08, -11 dropped).
3. *(P3)* **Start screen** for lead-retrieval staff: "Open the app on: Now / Lead scanner" (D-16).
4. **Data:** "Updated 9:12 AM · Refresh now", "Times are in Pacific Time", "Schedule changes". Then **About this app**.

Toggle rows are `ListTile(toggle_inputs=True)`: the whole row is the target and reads as one control. Toggles re-plan reminders silently, without a SnackBar each.

**Interim until E3 is in the pinned Flet** (D-60, always in the `flet run` companion app, D-63): the Reminders section says "Reminders aren't available in this build. Your next session appears on Now, and calendar exports include an alarm." and shows no switches. While the app is open, 10 min before a saved session, a `Banner` "Typing deep dive starts in 10 min · Room 103ABC" offers "Open" and "Dismiss".

---

## 7. Screens: accounts and staff tools (P3, mock only)

These exist only when a mock API base URL is set (D-51); the app never calls private PSF endpoints.

### 7.1 Sign in and Account (AUTH-01..12, SHELL-13)

- **Sign in** (`/more/sign-in`): "Only needed for sponsor and staff tools, and to sync My schedule." and "Connected to the local mock server". `AutofillGroup` with `TextField(label="Email", keyboard_type=KeyboardType.EMAIL, autofill_hints=[AutofillHint.EMAIL])` and `TextField(label="Password", password=True, can_reveal_password=True, autofill_hints=[AutofillHint.PASSWORD], on_submit=...)`. `FilledButton("Sign in")` is disabled with a `ProgressRing` while in flight. Distinct inline errors: "Email or password is incorrect.", "You're offline. Connect and try again.", "The server didn't answer. Try again." Afterwards, back to the origin; lead-retrieval accounts land on the Lead scanner (#310).
- **Account** (`/more/account`): initials avatar, nickname, email; read-only access chips; "My schedule sync: up to date / 2 changes waiting"; "Speaker Discord" for speakers; `OutlinedButton("Sign out")` → "Sign out? Your saved sessions stay on this device.", or "3 scans haven't synced. Sign out anyway?" with "Sync now".
- **Entry to tools** (SHELL-06, -07, -11): the More section and the Now card only; each tool is a pushed View; visibility from `staff_entries(flags)` with Ionic's gating.

### 7.2 Shared scan screen (LEAD-01, -02, -09, -12, -13, D-65)

1. `AppBar`: tool name and context ("Door check · Decorators, Wed 9:00 AM"); a **sync chip** ("All synced" / "3 pending" / "Offline · 3 queued") opening the queue sheet; a torch `IconButton(FLASHLIGHT_OFF, selected_icon=FLASHLIGHT_ON)` with E1; a `KEYBOARD` button focusing manual entry.
2. **Camera area** (`expand`): the E1 preview when `capabilities.SCANNER` is true, with a scan window, "Point the camera at the badge QR code" and a "Tap to resume" pause overlay. Without E1 (companion app, or before E1 is pinned): "Camera scanning isn't available in this build." and manual entry is primary.
3. **Result panel:** `AnimatedSwitcher` in `Semantics(live_region=True)`: icon, outcome word, name or code, details, "12 s ago"; stays until the next scan, dims after 5 s.
4. **Manual entry:** `TextField(label="Badge code", on_submit=...)` taking the full `code:validator` payload, which USB and Bluetooth HID scanners also type before Enter; focus returns to it, so hardware scanning is continuous.
5. Tool actions ("Add note", "Change session") in `SafeArea`.

| Outcome | Visual | Haptics | Spoken |
|---|---|---|---|
| Accepted | `CHECK_CIRCLE`, white on `#146C2E`, "Checked in · Ada Lovelace" | light | polite |
| Duplicate | `HISTORY`, `#1A1A1A` on `#F2C14E`, "Already checked in" | medium ×2 | assertive |
| Denied | `BLOCK`, white on `#B3261E`, "Not registered for this session" + reason | heavy + vibrate | assertive |
| Queued offline | `CLOUD_UPLOAD_OUTLINED`, neutral, "Saved. Will sync when online." | light | polite |

`announce_message` only when `supports_announcements`; the live region covers the rest. One accepted result per code every 4 s; scanning pauses under dialogs and sheets. `Wakelock().enable()` while mounted, `disable()` on unmount. Camera permission per §4.8 (`DENIED` → primer, then request; `PERMANENTLY_DENIED` or `RESTRICTED` → "Camera access is off", "Open settings", "Enter codes instead"). The **queue sheet** (`BottomSheet(scrollable=True)`) lists pending and failed rows with time, name or code and last error, "Sync now" and "Retry failed"; states are words and icons: Queued, Confirmed, Failed.

### 7.3 The four tools (O-7 order: lead → door → swag → CoC)

- **Lead scanner** (`staff/lead`; LEAD-04..08, -10, -11): `Tabs` Scan · Leads (42). A consent screen on first use per account (not an alert): `Checkbox("I'll only scan with consent")` enables Continue; asked again after sign-out. Staff scanning for a sponsor see `Chip("For: Bloomberg")` and pick from a full-screen searchable list with Cancel. Results: captured → name + "Add note"; queued → "Saved. Will sync."; duplicate → "Already in your leads" + "Open lead" (Ionic was silent). Note sheet: Interest `SegmentedButton(allow_empty_selection=True)` Hot · Warm · Cold with icons, not emoji; follow-up `Chip`s; `TextField(multiline=True, max_length=4000)`. Leads: filter, lazy list with status icon and word, no 50-row cap.
- **Door check** (`staff/door`; DOOR-01..07): category chips and a searchable, day-grouped session list → "Start check-in" → "Loading attendee list… 2 of 5" then "Ready, works offline" (or "Badges will be checked online" + Retry); scanning starts only then. "42 checked in" (`DISPLAY_SMALL`) stays visible above the result panel. Results show the name (O-7), dietary chips and a prominent allergy chip with `WARNING_AMBER`.
- **Swag pickup** (`staff/swag`; SHIRT-01..04): categories → scan → a hand-out `BottomSheet(scrollable=True)` with a `Checkbox` per item (picked-up items disabled with the reason; available items pre-checked, O-7) and `FilledButton("Hand out 2 items")`. Online only: offline, scanning is disabled up front with "Swag pickup needs a connection".
- **CoC incident** (`staff/coc`; MASK-01..05): "Scan a badge" or search the in-memory directory. Neither records directly: both open a review `AlertDialog(modal=True, scrollable=True)` with name, badge name, count in words and `TextField(label="What happened?", hint_text="What happened? Where? Witnesses?", multiline=True, max_length=2000, capitalization=ft.TextCapitalization.SENTENCES)` (the first positional parameter is `value`, so the prompt must not be passed positionally), then "Record incident". Neutral result ("Incident recorded. 3 on record."), cleared after 15 s and on backgrounding; email hidden until revealed (O-7); errors shown. Online only.

---

## 8. Tablets and landscape (D-09, SHELL-14, NATIVE-02)

- **≥ 600 dp** (`page.width`, re-checked in `page.on_resize`): root Views swap the bar for `ft.NavigationRail(destinations=..., selected_index=..., label_type=ft.NavigationRailLabelType.ALL, group_alignment=-1)` with the same destinations (P2).
- Reading screens max 720 dp and lists max 840 dp, centred on `surface`; floor plans use the full width.
- Phone landscape is allowed and reflows; side insets come from `page.media.padding`.
- *(could, later)* list-detail two-pane at ≥ 840 dp for Schedule and Speakers: it doubles the state paths, so it waits for need.

---

## 9. Accessibility checklist (every UI PR; D-33, D-93)

- [ ] Every control has a name, role and state; icon-only buttons have a `tooltip`; toggles announce state (`selected`, `Semantics(toggled=...)`).
- [ ] Rows read as one phrase (`MergeSemantics`); the star is its own stop.
- [ ] Titles, section, day and gutter headers are `Semantics(header=True)`; reading order follows visual order.
- [ ] Targets ≥ 48 × 48 dp; `visual_density` never reduced on rows.
- [ ] Contrast test green (AA light and dark, 7:1 text in HC); no hard-coded greys (Ionic's `#808080` was 3.9:1).
- [ ] At 200 % OS text and with iOS Bold Text, nothing clips or overlaps; no fixed heights around text.
- [ ] Colour is never the only signal (badges have text, outcomes have icon and word).
- [ ] Reduced motion honoured: every duration through `prefs.motion_ms()`, static `Shimmer`, instant scrolls, still pins (D-173).
- [ ] Every gesture has a button alternative (zoom buttons, expo List, manual scan entry).
- [ ] Dynamic results use `Semantics(live_region=True)`; `announce_message` only where that cannot work and `supports_announcements` is true.
- [ ] Images have `semantics_label`, or `exclude_from_semantics=True` when decorative.
- [ ] Key controls have `Semantics(identifier="<screen>.<element>[.<key>]")` for `flet test`.
- [ ] TalkBack and VoiceOver checked on the changed flow; the PR names the devices.

---

## 10. Open UX questions

Each default applies until the owner decides. Decision-level questions (O-1 tabs, O-2 transitions, O-3 font, O-7 staff details) are in the decisions record.

| # | Question | Default |
|---|---|---|
| UQ-1 | Bottom bar on pushed detail Views too? With one View per level each pushed View carries its own bar, which slides with the page | **Settled (#149, D-144):** roots only. S4 saw the bar slide across on iOS and double on Android; re-tap scrolls to top. U23 could bring it back |
| UQ-2 | The route shapes in §2.5 | Search: S4 confirmed D-19 (global modal plus our `page.on_view_pop`; D-141). The `plan/<plan>` drill kind is in §M. Schedule changes returning to its opener: a `needs-decision` issue to amend §M |
| UQ-3 | Breaks and meals on the Schedule: compact notices or hidden by default? | Shown as `NoticeRow`s |
| UQ-8 | 2027 booth geometry: hand-tag with a Developer overlay that prints tapped ratios, or derive from a PDF? | Developer overlay |

**Decided** (revisit only through a `needs-decision` issue): Open spaces hidden on the Schedule by default, shown as a filter state with the summary line (D-20); a one-sentence primer before asking for notifications on the first favourite or reminder switch (D-61); Speakers sorted by displayed name (D-46); no sponsor strip or carousel, a spotlight card instead (D-37); safety contacts, including any emergency number or first aid, only from a verified public source (D-45); "My schedule" with a star (D-13, D-30).
