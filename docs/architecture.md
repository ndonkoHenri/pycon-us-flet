# Architecture

**Status:** v2, plan of record, 2026-10-11. Replaces the PSF-oriented v1 (kept in git history, not binding).
**For:** whoever implements a module, screen or service. **Companion to** [`PLAN.md`](../PLAN.md) §5 and [`decisions.md`](decisions.md), which is binding; §19 lists where this file departs from it.

**Conventions**
- `D-nn` are decisions, `F1`..`F31` the verified Flet facts (decisions §N), `S1`..`S9` the spikes (PLAN §8), `E*`/`U*` upstream items. Feature ids (`SCHED-16`, `NEW-03`) are rows of [`feature-matrix.md`](feature-matrix.md).
- Every Flet API named here was introspected in the local monorepo (flet-dev/flet `9fbe52a61`, unreleased 1.1.0). An API that does **not exist yet** is marked *(not in Flet yet: Ux/Ex)* and has an interim; §18 is the ledger.
- Code blocks are sketches: they parse and use only verified APIs, but leave out obvious imports, copy and styling.
- Each module says when it arrives (P0..P4). Build only what the current phase needs (D-66).

---

## 1. Shape of the app

```
 src/main.py   page.on_view_pop (parent_of), then page.render_views(App, MEMORY)
 app.py        App: Services + stores (once) → boot gate → providers → ft.Router(ROUTES)
 routes.py     tab roots · More pages · search · recursive drill (session/speaker/room/sponsor/plan)
 locations.py  drill_href · parent_of · use_query: what screens import to link and go back (D-164)
 screens/      one @ft.component per screen, returns an ft.View        ui/  shared components
 state.py      Conference     feed_refresh.py  Source · Status · fetch     memory.py  ViewMemory (plain)
 prefs.py      Prefs         favorites.py  Favorites   (P3 account.py, staff.py)
 services/     storage · api · reminders · sync · scanner · errors      (Flet services, httpx)
 core/         pure Python, no Flet: feed rules, models, queries, search, time, slugs, html→md,
               diff, ics, signing, badges, admission, outbox
 data/<year>/  conference.toml · content.toml · map.toml · conference.json (snapshot)
```

**Dependencies point down only.** `core/` imports the standard library and nothing else (a unit test scans its imports, D-68). `services/` may use `core/` and Flet services. Store methods take the services they use explicitly (`Conference`: `storage` and `year`, D-145). Screens never import an extension; only the one capability module per gap does (§13).

**Data flow.** The app renders the cached feed (else the bundled snapshot) before the first frame; a single-flight background refresh replaces the cache only after a good parse. Screens are pure queries over frozen models, memoised on `Conference.version`. User state lives in small observable stores. Private-API features (P3) talk only to the local mock.

---

## 2. Rules the code follows

**Zen, made concrete** (D-66, D-74): no single-implementation protocols, registries, code generation or service locator; stores are provided one by one; capabilities are constants; `screens/` and More are flat; one drill route serves every detail. Expected failures become visible state (§16). Docstrings on every module and public function (Google style), type hints, modules split at about 400 lines, `ruff` and `pyright` clean.

**Flet rules** (D-70; facts F1..F5):
1. Await coroutine APIs (`push_route`, `scroll_to`, `zoom/pan/reset`, `confirm_pop`, service methods) only in `async def` handlers or effects; `page.navigate`, `show_dialog`, `pop_dialog`, `run_task` are sync (F1).
2. A `use_effect` setup is an `async def` or a plain function, never a lambda returning a coroutine: that coroutine never runs (F2).
3. Long-running work runs in an `async def` setup: Flet cancels its task when the effect re-runs and when the component unmounts, with or without a cleanup (F2). A cleanup undoes only what the setup started outside its task; a sync setup may return it or pass `cleanup=`, and it may be `async`, since Flet finishes it before the next setup (D-387).
4. Hooks are unconditional: call every `use_*`, `is_route_active` and `use_dialog` before any branch.
5. One context per observable store: `use_context` subscribes only to an `Observable` value, and nested observables do not propagate (F3).
6. Large store values are `@dataclass(frozen=True, eq=False)` without cycles: assignment compares `old == new` (F5), which `eq=False` makes an identity check.
7. No store writes from other threads; `asyncio.to_thread` may compute a value that the loop assigns.
8. Never `adaptive=True`, no Cupertino controls (D-10).
9. Handlers are named functions; lambdas only bind arguments (`lambda _, sid=s.id: open_session(sid)`).

---

## 3. Module layout (D-67; names in decisions §M)

About 40 modules at the P1 exit (D-67), most of them screens.

| Module | Responsibility | Phase |
|---|---|---|
| `src/main.py` | `ft.run(main, before_main=prepare_first_page)` (the default View in the boot purple and no theme animation until the gate opens, F35, D-161): `setup_logging()` at import and one `ViewMemory` per process (D-163, D-143); `page.on_view_pop` (navigates to `parent_of(e.route)`, D-19) set **before** `page.render_views(App, memory)` | P0 |
| `pycon_us/__init__.py` | `__version__`, tested equal to `[project].version` (D-83); `APP_NAME`; `FLET_VERSION` (D-271); `SOURCE_URL`, None until the repo is public (D-292) | P0 |
| `app.py` | `App`, `bootstrap()`, lifecycle handler, theme effect, boot View (§4) | P0 |
| `routes.py` | `ROUTES`, `Drill`, `Start`, `NotFound`, `UNKNOWN` (§5) | P0 |
| `locations.py` | `drill_href()`, `parent_of()`, `start_target()`, `query_of()`, `is_top_view()`, `use_query()`, `TAB_ROOTS`, `DRILL_KINDS`, `PAGES`: what screens import to link and go back, without the table (§5.3, D-164) | P0 |
| `state.py` | `Conference`, `ConferenceCtx`, `use_conference()` (§6.2) | P0 |
| `feed_refresh.py` | the feed refresh without its store: `Source`, `Problem`, `Status`, `STALE_ON_CONFERENCE_DAYS`, `STALE_OTHERWISE`, `REFRESH_EVERY`, `stale()`, `due()` (D-301), `fetch()`, `feed_digest()`, `log_unexpected()` (§6.2, D-231) | P0 |
| `change_log.py` | `ChangeLog`, `ChangeLogCtx`, `use_change_log()`, `Published`: the change log's store, which `Conference` hands each new feed to (§7.9, D-301) | P2 |
| `memory.py` | `ViewMemory` (§6.3, D-231) | P0 |
| `layout.py` | `Layout` (the window's width class: the bar or, from 600 dp, the rail; and the body's room over 720 dp, D-305), `LayoutCtx`, `use_layout()`, `layout_for()`, `follow_width()`, `side_insets()`, `is_wide()`, `WIDE_DP`, `READING_DP`, `LIST_DP` (§5.5, §6.1, D-277) | P2 |
| `prefs.py`, `favorites.py`, `account.py`, `staff.py` | one store each, with its context and `use_*()` hook (§6, D-160) | P0, P1, P3 |
| `dev_options.py` | the keys of `Prefs.dev` (`DEV_UNLOCKED`, `DEV_FAKE_NOW`, `DEV_FEED_URL`, `DEV_MOCK_API_URL`), `with_dev_options()`, `parse_feed_url()` (D-187; split from `prefs.py`, #737) | P1 |
| `accessibility.py` | `read_accessibility()`: the OS's accessibility flags into `Prefs` (§4, D-356; split from `prefs.py`, #737) | P2 |
| `account_profile.py` | what the `Account` store reads and saves: `FLAGS`, `REFRESHED`, `Profile`, `secrets_of()`, `refreshed_flags()`, `log_unexpected()` (§6.1, D-403) | P3 |
| `config.py`, `year_schema.py`, `year_tracks.py`, `year_pages.py`, `year_keynotes.py`, `year_moments.py`, `year_info.py`, `year_links.py`, `theme.py`, `theme_markdown.py`, `capabilities.py`, `clock.py` | year data (§8; `year_schema.py` its TOML-to-dataclass half, §8.2; `year_tracks.py` the track registry with `HUB_PAGES`, the Tracks hub's pages of their own (D-207), and its checks, D-228; `year_pages.py` the Open spaces and Lightning talks pages' tables and their checks, D-205; `year_keynotes.py` the keynotes' entries and their checks, D-217; `year_moments.py` the conference moments, hand-written and derived, D-274; `year_info.py` the info pages' tables and their checks, `check_info()`, D-263, so far the venue hours', D-282; `year_links.py` About the PSF's and Social's, the pages of links, D-283, D-284, split from `year_info.py` in #532); theme (§15; `theme_markdown.py` the feed texts' `MARKDOWN_STYLE`, D-116); capabilities (§13); `now()` (§7.6) | P0 |
| `core/` | `feed`, `records`, `rules`, `names`, `models`, `timefmt`, `slugs`, `html_md` (with `markdown_inline`, D-201), `queries` (`days`; P0, the rest P1), `search`, `row_views` (with the rows' spoken phrases, D-200), `speakers`, `sprints` (P1, D-202); `sponsors` (D-261), `jobs` and `links` (D-278), `expo` (D-254), `hours` (the venue hours and the open-now rule, D-282), `diff`, `change_batches` (D-255), `change_views` (#432), `ics` (P2); `signing`, `badges`, `admission`, `outbox`, `favorites_sync`, `conduct` (the CoC directory, search and count words, D-430), `check_in` (the check-in API's payloads, #763) and `door_sessions` (Door check's sessions, with the date in a product's name: `product_sort_key()`, `session_parts()`, moved from `check_in` at D-66's ~400 lines, #777) (P3) | P0+ |
| `services/` | `Services` bundle, `storage` (its files, `data_dir()` and `write_atomic()`, in `data_files`; its key table, `Pref` and the keys, in `pref_keys`, split at D-66's ~400 lines, #777), `changes_file` (the change log's file, P2, D-255), `outbox_db` (the staff outbox's sqlite, P3, #691) and `outbox_schema` (its tables, migrations, queries, row mapping and the revision-checked row write, split from `outbox_db` at D-66's ~400 lines, #732, #755), `api` (feed fetch P0, signed client P3) and `endpoints` (its call table and query builders, split from `api` at D-66's ~400 lines, #693), `private_api` and `credentials` (the mock account's key and secret, P3, #684), `favorites_sync` (P3, D-406), `errors` (P0); `reminders` (with its pure plan, `reminder_plan`), `calendar` (P2, D-272); `diagnostics` (P2, D-271), `build` (the version and build number, P2, D-386); `sync`, `scanner` (P3) | P0+ |
| `ui/` | grouped by role (decisions §M): `scaffold.py` (`AppScaffold`, `SectionHeader`, `search_button()`), `page_title.py` (`PageTitle`, D-328), `day_tabs.py` (`day_tab()`, `TAB_HEIGHT`, `TAB_MS`; D-192), `status_strip.py` (`StatusStrip`, which is `use_strip()` and its `Strip` drawn by `strip_view()` (D-345, F150), `strip_line()`, `schedule_line()` (D-292) and the minute tick: `use_minute()`, `TICK_SECONDS`, `current_minute()`; D-200), `navigation.py` (`TABS`, `navigation_bar()`, `use_scroll_to_top()`; D-166; `navigation_rail()` and `RAIL_WIDTH`, D-277), `rows.py` (`SpeakerRow`, `SpeakerTile`, `speaker_avatar()`, `LinkTile`), `location_card.py` (`LocationCard`, with its plan-only form; #389), `session_rows.py` (`SessionRow`, `NoticeRow`, `use_session_views()`, `is_notice()`; D-184), `row_lines.py` (the lines under a row's title: `meta()`, `secondary()`, `overlap_line()`, `elapsed_bar()` and its `TRACK`; D-227), `time_gutter.py` (`TimeGutter`, `TimeSlot`; D-200; `TimeAbove`, `slot_layout()`, `time_above()`, `slot_width()` (less the rail from 600 dp, D-277) and `GutterProbe`, which `AppScaffold` puts under every body, 0 dp high, and `BootView` holds too; D-216), `links.py` (the link rule: `LinkKind`, `link_kind()`, `open_link()`, `copy_contact()`; D-182; and feed texts: `open_feed_link()`, `feed_markdown()`, over `core/links.py`'s `feed_link()`; D-197, D-278; `copy_text()`, the one copy with its one confirmation; D-263), `widths.py` (`READING`, `LIST`, `FULL`, `use_margin()`, `sides()`, `capped()`; D-305), `info_page.py` (`InfoBody`, the info pages' body, and `FeedBlock`, its fallback to the feed's block, with `GUTTER`; D-263), `badges.py` (`TrackBadge`, `badge_specs()`, `session_badges()`, `badge_row()`, `NEW_TRACK`; D-174), `favorite.py` (the star and what a favourites edit says: `FavoriteButton`, `use_favorite_toggle()`, `use_add_all()` (a track page's Add all, D-209), `selection_click()`; D-267), `snack_bars.py` (`SNACK_BAR_MS` and `keep_while_screen_reader()`, which closes a SnackBar a screen reader keeps once none is on; D-356), `states.py` (`EmptyState`, `SkeletonList`), `when_where.py` (session detail's `WhenAndWhere` card and `StatusLine`; D-186), `fold.py` (`FoldTile`, `expand_style()`, the app's own controlled fold, a `ListTile` header and not `ExpansionTile`; D-191, D-354), `fields.py` (`SearchField`, the pill of search and the Speakers and Sprints filters, D-193; `use_field_query()`, its text, `Ref` and refocusing Clear, and `found_count()`, the live count line; D-226), `scrolling.py` (`jump_to_key()`, `FULL_LIST_EXTENT`, `JUMP_MS`, `SCROLL_EVENT_MS`; D-154, D-192), `semantics.py` (`named()`, an identifier merged into its control's node; D-190, D-198; `semantics_key()`, an id as an identifier's key, re-exported from `core/slugs.py`; D-200, D-283), `day_groups.py` (`DayGroup`, a memoised day of session rows under its heading, for search, the track pages and speaker detail; D-199, D-203), `share.py` (the share sheet: `centre()`, where it points from on a tablet, `share_text()`; D-206; and a bug report, `share_console_log()`; D-297), `actions.py` (`action_row()`, `outcome_line()`, `padded()`, `Outcome`, an action and how it ended said in place; D-297; and `refreshed()`, Refresh now's words, shared by Developer's and Settings' Data sections; D-198, D-210, #422), `menus.py` (`overflow_menu()` and `menu_item()`, the app bar's overflow and its items, whose labels wrap at 200 % text, D-233; `view_source_items()` and `source_menu()`, View source behind `SOURCE_URL`, D-461), `logos.py` (`logo_tile()`, a logo on a white tile or the initials, for the Sprints cards and the sponsor screens; D-262), `brands.py` (`brand_icon()`, a brand's mark beside a link to it, and `BRANDS`, each mark's tint; D-264), `buttons.py` (`LABEL_PADDING`, `ICON_PADDING`: a filled, tonal or outlined button's padding at every text size; D-344), `zoom.py` (a floor plan's zoom layer: the hook `use_zoom()` and its `Zoom` (with `restore()`, a pane's zoom put back, #402), `zoom_layer()`, `zoom_buttons()` with `zoom_button()`; D-312, #388), `zoom_geometry.py` (its maths: `fitted()`, `max_scale()`, `centred_on()`, `refocus()` and `into_bounds()`; #588); for the staff tools (P3), `scan_screen.py` (`ScanScreen`, `ResultPanel`, `NotAvailable`, `use_tool_allowed`; D-416), `scan_result.py` (the result panel, and `Shown`, `Posted` and `post()`, moved from `scan_screen.py` at D-66's ~400 lines, #777), `staff_picker.py` (the pickers' parts and `Reading`; D-433) and `tool_controls.py` (`context_chip()`, `tool_button()`, split from `staff_picker.py`, #777) | P0+ |
| `screens/` | one `@ft.component` per screen, named after its route (`now.py`, …, `staff_<tool>.py`); `developer_clock.py` holds the Developer screen's fake-clock pickers (D-187), `now_header.py` Now's status header and its words, `now_sections.py` its sections by season (#568), `now_card.py` its next-session card (D-190), `now_fold.py` how long its Happening now and Up next are at peak times (D-327), `now_spotlight.py` its sponsor spotlight (D-298), `now_quick.py` its quick info buttons (D-338), `now_changes.py` its Schedule changes card (#438), `search_results.py` search's result list (D-193), `search_scopes.py` its scope chips, kept in sight (#794), `schedule_days.py` the Schedule's day lists, slots and "Now" button (D-192), `schedule_slots.py` what its day lists hold and their put-back (`use_day_slots()`, `slot_keys()`, `use_put_back()`; D-331, D-371), `venue_cards.py` Venue & hours' cards (D-313), `schedule_now.py` its now line, when a jump to now runs by itself, what the handlers tell it and what it left in view (D-204), `schedule_place.py` the place each day list keeps across a text-size or filter change (`PlaceKeeper`'s put-backs, D-331, D-371), `schedule_layout.py` what it measures and records (`LayoutRecord`, which `PlaceKeeper` extends, and `layout_probe()`; #631), `room_days.py` room detail's day lists and the lit row (D-194), `schedule_head.py` the Schedule's head, the filter summary, the strip and the zone note, fixed under the day tabs or, at the largest text, at the top of each day list (D-345), `schedule_filter.py` the Schedule's track filter (`use_track_filter()`: the `TUNE` action, the summary's words and line, and the edits) and `schedule_sheet.py` its filter sheet (`filter_sheet()`, `filter_groups()`; D-195); `/more/tracks` and `/more/tracks/<slug>` are `tracks.py` (the hub) and `track.py` (a track's page; D-199); `/more/sprints` is `sprints.py`, its project card `sprint_card.py` (D-202); `/more/open-spaces` and `/more/lightning-talks` are `open_spaces.py` and `lightning_talks.py` (D-205); `session_extras.py` holds session detail's Share, a Posters row's posters and an open space's image and site link (D-206); `my_schedule_extras.py` holds My schedule's overflow (Export to calendar) and its all-over notice (D-289); `schedule_changes_seen.py` holds Schedule changes' seen marks: the unseen dot, the 2 s timer and Mark all as seen (#436); `changes_review.py` the Review SnackBar of a schedule update and the Schedule's overflow (D-335); `/more/keynotes` is `keynotes.py`, its card `keynote_card.py`, and `keynote_people.py` holds a keynote's people for the card and session detail's keynote sections (D-217); `/more/help` is `help.py` (D-281); `/more/app/licences` and its texts are `licences.py` (D-296) | P0+ |
| `licences.py`, `licence_texts/` | what each build ships under whose licence: `GROUPS`, `COMPONENTS`, `read_text()`, `paragraphs()`, and the texts it opens offline (D-296) | P2 |
| `data/<year>/`, `src/assets/` | year data (§8); `fonts/`, `icons/`, `maps/<year>/` | P0 |
| `tools/` | `mock_api/` (P3), `update_snapshot.py`, `check_feed.py`, `feed_invariants.py` with `sponsor_invariants.py`, `capture_ionic_reference/`, `check_matrix.py`; the local checks `check.sh` and the merge gate `gate.sh` (D-273) | P0+ |

---

## 4. App, services and bootstrap

### 4.1 `App`

```python
# src/pycon_us/app.py (excerpt)
@ft.component
def App(memory: ViewMemory):
    """Build services and stores once, wait for the settings and the feed, then route."""
    page = ft.context.page
    svc = ft.use_memo(lambda: Services.create(memory), [])   # in the page context: Flet registers each service
    conference = ft.use_memo(Conference, [])      # App does not subscribe to it
    favorites = ft.use_memo(Favorites, [])        # nor to this one (D-172)
    layout = ft.use_memo(lambda: Layout(wide=is_wide(page.width)), [])  # nor this (D-277)
    prefs, _ = ft.use_state(Prefs)                # use_state subscribes App to Prefs only

    async def start():
        await bootstrap(page, svc, conference, prefs, favorites)

    def follow_theme():
        apply_theme(page, prefs)

    ft.use_effect(start, [])
    ft.use_effect(follow_theme, [prefs.theme, prefs.high_contrast_on])

    if not prefs.loaded:                          # boot gate: no theme or filter flash
        return [BootView()]

    tokens = build_tokens(dark=prefs.dark, high_contrast=prefs.high_contrast_on)   # D-150

    def router():
        return ft.Router(ROUTES, manage_views=True)

    return ServicesCtx(svc, lambda: ConferenceCtx(conference, lambda: PrefsCtx(
        prefs, lambda: FavoritesCtx(favorites, lambda: LayoutCtx(layout,      # D-277
            lambda: TokensCtx(tokens, router))))))
```

`App` re-renders only on `Prefs` changes; screens subscribe to what they read through `use_conference()`, `use_prefs()`, `use_favorites()` (only in the component that owns a list, D-172) and `use_services()` (one-line `ft.use_context(...)` hooks); `use_tokens()` reads the current scheme's `Tokens`, a plain value that `App` re-provides on every render (D-150). `Favorites` (P1, D-172) is built with `ft.use_memo(Favorites, [])` and loaded in `bootstrap()` after the theme; `Layout` (P2, D-277) is built from `page.width`, and an effect of `App`'s sets the app's one `page.on_resize` (`follow_width()`), so a rotation re-renders the screens that read it, never `App`; P3 adds `AccountCtx` (#684: `Account` is built first, so `Services.create(memory, account.credentials)` hands the private-API client its key and secret; provided between `FavoritesCtx` and `ChangeLogCtx`) and `StaffCtx`. `ROUTES` comes from `routes.py` and ends with its catch-all `UNKNOWN`, whose component is `NotFound`, so `App` passes no `not_found` (§5.3, D-270); in P0 every route renders a stub screen in `AppScaffold` (`screens/stub.py`'s `stub_body()` lists its rows, D-165), and the Schedule stub shows the status strip, the data source, fetch time and each day's session count.

`BootView` is a full-bleed `View` in the splash's purple `#680579`, like the native splash and Flet's boot screen shown while Python starts (both set in `pyproject.toml`: `[tool.flet.splash]`, `[tool.flet.boot_screen.flet]`; development.md §3), so nothing flashes (SHELL-01). It shows a white `ProgressRing` only after 1 s (`loop.call_later` from a sync effect whose cleanup cancels it), and the app icon once O-4 has one (D-161).

### 4.2 `Services`

`Services` (`services/__init__.py`, with `ServicesCtx` and `use_services()`) is a `@dataclass(frozen=True, eq=False)` built once by `Services.create(memory)` in App's first render: `year` (the bundled `YearData`, §8), `storage` (`Storage(ft.SharedPreferences(), data_dir(), year)`, §9), `memory` (the process's one `ViewMemory`, created in `main.py` and passed to `App`, §5.3, §6.3), `semantics` (`ft.SemanticsService()`, for the accessibility flags), `launcher` (`ft.UrlLauncher()`) and `clipboard` (`ft.Clipboard()`), which `ui/links.py`'s link rule uses (D-182), `share` (`ft.Share()`) and `paths` (`ft.StoragePaths()`), for the Developer screen's Share log (D-198), `closed` (an `asyncio.Event` that `close()` sets when the session is replaced, D-147) `foreground` (an `asyncio.Event`, set while the app is in the foreground: the lifecycle handler clears it on `pause` and sets it on `resume`, D-175) and `presence` (`services/presence.py`'s `Presence`: `inactive` leaves and `resume` comes back, so `ui/focus_back.py`'s `focus_back()` can give a button the focus again after the browser or the share sheet it opened, D-372). `run_every(seconds, action)` is the one loop for D-40's ticks: it calls `action` at once and then every `seconds` while `foreground` is set, waits without work in the background (catching up at once on resume when a call fell due), and returns when `closed` is set; an effect's cleanup stops it sooner by cancelling its task. A Flet `Service` registers with the page when constructed, so screens never construct one. Each phase adds the services its screens use: P1 also `ft.HapticFeedback()` (`haptics`) and session detail's Share (#92); P2 `permissions: PermissionHandler | None` (the `flet_permission_handler` instance, built only when `capabilities.PERMISSIONS`; the capability-owning modules use it, e.g. `await svc.permissions.request(Permission.CAMERA)`) and `file_picker` (`ft.FilePicker()`, Android's save in `services/calendar.py`, D-272); P3 `api: ApiClient | None` (None unless a mock URL is set, D-51; #668: a property over `private_api`, `services/private_api.py`'s `PrivateApi`, a mutable holder in the frozen `Services`, which `bootstrap()`'s `start_developer_options()`, Developer's Mock API section and Reset app `connect()` to the URL or to none, closing the client they replace; every client signs with `Account.credentials`, #684), `credentials` (`services/credentials.py`'s `CredentialStorage`: the keystore through `flet-secure-storage` when `capabilities.SECURE_STORAGE`, else memory for the session; #684), `outbox` (`services/outbox_db.py`'s `OutboxDb`, §12.1: built by `create()` on the data directory but opened on first use, so an install whose staff tools never run, hidden without a mock URL, never creates `outbox-<year>.db`; `close()` closes it, and a late write is then refused and logged, D-120), `sync_wake` (an `asyncio.Event`; `kick_sync()` sets it, and so do `close()` and `on_resume()`) and `connectivity` (`ft.Connectivity(on_change=kick_on_reconnect(sync_wake))`, built by `create()` with its handler, F257: a change to anything but `NONE` sets `sync_wake`; #692, D-407), then `wakelock` (`ft.Wakelock()`, for the scan screen).

### 4.3 Bootstrap (DATA-35)

```python
# src/pycon_us/app.py (excerpt)
async def bootstrap(page: ft.Page, svc: Services, conference: Conference, prefs: Prefs,
                    favorites: Favorites, change_log: ChangeLog, account: Account) -> None:
    """Start in the order that avoids flashes and never waits on the network."""
    page.on_close = svc.close                 # 0. before any await: a replaced session stops (D-147)
    try:
        await prefs.load(svc.storage)             # 1. settings, OS flags, theme: under the boot view
        start_developer_options(prefs, conference)   # fake clock, feed URL, error details (D-187)
        await read_accessibility(svc.semantics, prefs)
        prefs.os_dark = page.platform_brightness == ft.Brightness.DARK
        apply_theme(page, prefs)                  # no animation yet: main.prepare_first_page (D-161)
        await favorites.load(svc.storage)         # 2. this year's favourites (D-48, D-172)
        await change_log.load(svc.storage, svc.year.conference.zone)   # and its change log (D-301)
        await account.restore(svc.storage, svc.credentials)   # local reads only (STORE-03, D-398)
        account.refresh_flags(svc.api, svc.storage, closed=svc.closed)   # not awaited (D-403)
        await conference.load_local(svc.storage, svc.year)   # 3. cache or bundled snapshot
    except Exception:
        if not svc.closed.is_set():               # a closed session's store write fails (F30)
            logger.exception("Start failed; opening the app with what has loaded")
    if svc.closed.is_set():                       # replaced during steps 1-3: stop here
        return
    prefs.loaded = True                           # 4. opens the boot gate
    page.theme_animation_style = None             # crossfade again, under reduced motion too (D-173)
    conference.start_refresh(svc.storage, svc.year, closed=svc.closed)   # 5. background, not awaited

    def on_brightness(e: ft.Event[ft.Page]):     # not e.brightness: a plain event at the pin (F36, U25)
        prefs.os_dark = page.platform_brightness == ft.Brightness.DARK

    async def on_lifecycle(e: ft.AppLifecycleStateChangeEvent):
        if e.state == ft.AppLifecycleState.INACTIVE:
            svc.presence.leave()                  # another window in front (D-372)
        elif e.state == ft.AppLifecycleState.PAUSE:
            svc.foreground.clear()                # the 60 s ticks wait (D-40)
        elif e.state == ft.AppLifecycleState.RESUME:
            await on_resume(svc, conference, prefs, account)

    page.on_platform_brightness_change = on_brightness   # 6. handlers write stores only (D-147)
    page.on_app_lifecycle_state_change = on_lifecycle


async def on_resume(svc: Services, conference: Conference, prefs: Prefs,
                    account: Account) -> None:
    """The one place for what a resume does; each consumer is one line (D-173, D-175)."""
    svc.foreground.set()                                                 # ticks again
    svc.presence.come_back()                                             # D-372
    conference.start_refresh_if_due(svc.storage, svc.year, closed=svc.closed)   # D-40
    if svc.reminders is not None:
        svc.reminders.request()                                          # D-389
    account.refresh_flags(svc.api, svc.storage, closed=svc.closed)       # D-403
    svc.kick_sync()                                                      # D-407
    await read_accessibility(svc.semantics, prefs)                       # a snapshot (F13, U17)
```

- `read_accessibility()` (`accessibility.py`, so `ui/snack_bars.py` reads with it too, D-356) copies `high_contrast` and `reduce_motion or disable_animations` from `get_accessibility_features()` into `Prefs`, and logs "Reduced motion is on/off" when that flag changes; a failed read is logged and keeps the previous values. The theme crossfade stays under reduced motion: it changes colour, not position (D-173). An unexpected error in steps 1-3 is logged and the gate opens with whatever loaded, so a start never hangs on the boot view (D-161). `apply_theme(page, prefs)` runs before the gate opens, with Flutter's 200 ms theme crossfade off, so the first screen has its stored theme and is never shown mid-fade; `App`'s theme effect follows later changes, which crossfade. `main.py` passes `before_main=prepare_first_page`, which gives the page's default View the boot purple (Flet shows that View for a frame before `main()`'s first patch, F35) and sets `page.theme_animation_style` to zero duration in that first page, so every theme change before the gate lands at once, including the default settings that `App`'s theme effect applies on mount, before `bootstrap()` has read the stored ones.
- P1 inserted `await favorites.load(svc.storage)` as step 2 (D-172), and P2 the change log's `load()` after it (D-301), and, with the Developer screen, `start_developer_options()` after the settings (D-187): `clock.start_fake_clock(prefs.fake_now)`, `await conference.set_feed_url(prefs.feed_url, svc.storage)` (D-244) and `errors.show_details(prefs.developer_unlocked)`; #84 added `on_resume()` (D-173), and #82 its refresh when due and the pause handling (D-175). P3 inserted after the change log `await account.restore(svc.storage, svc.credentials)` (#684: local reads only, whether or not a mock URL is set, D-398), then `account.refresh_flags()`, one `check_features` in the background, not awaited, which `on_resume()` repeats (#686, D-403); it inserts one favourites sync after it (D-55); start the sync worker when a mock URL is set. S4 confirmed that the page handlers fire and re-render through store writes without `page.update()`, and the lifecycle sequences the app relies on (D-147): background `inactive, hide, pause`; return `restart, show, resume`; Back on Now on Android adds `detach` and ends the session (F29).
- **A replaced session (D-147, F30):** on Android a new session can start in the same process (F26, F29). Flet closes the old one (`page.on_close`) but does not unmount it, so its effect tasks keep running. `bootstrap()` sets `page.on_close` before its first await, so a session replaced during the boot view is closed too, and it then stops before it opens the gate or starts a refresh. `svc.close()` sets `svc.closed`; the 60 s ticks, the sync worker and a refresh (`start_refresh(..., closed=svc.closed)`, which then stops before its next write) check it, as well as their own effect's stop event, before they write a store. Only `page.on_close` sets `svc.closed`: a screen unmounts on every tab switch, and its cleanup stops only its own effect. U24 would make this unnecessary.

**Refresh triggers (D-40, D-175):** all but Refresh and pull-to-refresh are automatic, so quiet: they show only the strip's bar (D-181). Start (always); resume, when `Conference.refresh_due()`; the status strip's 60 s tick on Now and Schedule (`StatusStrip(auto_refresh=True)`), while it is mounted and the app is in the foreground, when `refresh_due()`; "Refresh" in the status strip; pull-to-refresh with `RefreshIndicator` (U1, in the pin since `22a6dcb16`; adoption in #806). `refresh_due()` is true when no refresh has started in the session, or the last one *began* 15 min ago or more by `clock.now()` (a clock set back counts as due): the interval counts from the last attempt, not the data's age, so an offline phone retries every 15 min rather than every minute. Every strip, My schedule's too, re-renders on its tick when the minute has changed, so its age keeps up and it appears when the data turns stale.

---

## 5. Routing and navigation

### 5.1 Router facts we rely on (F6; `components/router.py`)

- With `manage_views=True`, each matched route with a component is one `View`; children are tried before the parent's exact match.
- A `recursive=True` route matches its own pattern once per level, trying its non-recursive children first, and **each level gets its own params** (checked: `/schedule/session/42/speaker/17/session/99` gives three drill levels, `session/42`, `speaker/17`, `session/99`). Params are raw, percent-encoded segments: always `unquote`.
- Default pop navigates to the previous view entry's resolved path and drops the query (what #313 needs).
- **Confirmed in S4** (`docs/spikes/04-router-back.md`): per-level params with quoted ids on both platforms (D-141); every Back key and committed predictive gesture reaches our `page.on_view_pop` (D-141); `can_pop=False` + `on_confirm_pop` on a one-View stack (D-142); roots sharing one `View.route` key switch without a transition (D-142). Back on Now finishes the Android activity, and a relaunch is a new session in the same process (F29).
- **Modal caveat:** with the stock pop handler, when the matched chain contains a `modal=True` route, *every* pop navigates to the modal's base URL, including a pop from a view pushed on top of the modal. An app's own `page.on_view_pop`, set before the Router mounts, receives every pop instead (`router.py` delegates before its modal branch; `e.route` is the popped view's route). We use that for search (§5.4, D-19) until U18 lands.
- `not_found()` output is wrapped in a View that sets neither `can_pop` nor `on_confirm_pop`, so the app does not use it: the table ends with a catch-all splat route whose component returns its own View (F89, D-270). `use_route_location()` is the pathname only (no `use_route_search`, *not in Flet yet: U9*).
- `View.can_pop=False` with `on_confirm_pop` intercepts system Back even on a one-View stack (Dart `view.dart` wraps the View in `PopScope`); the handler must `await view.confirm_pop(...)`, or the pop waits for a timeout.
- **Back with a dialog open (F46, D-208):** Flet takes a system pop (the Android Back, and VoiceOver's escape on iOS, both `popRoute`) before Flutter's Navigator and pops a top View that can pop and has no `on_confirm_pop` by itself, with the dialog, picker, sheet or menu open over it. So every pushed View declares an `on_confirm_pop` (`AppScaffold`, §5.5): Flet then leaves Back to `Navigator.maybePop()`, which closes the topmost route first, and the View's own pop still reaches `on_view_pop`. The handler goes once U33 is in the pinned Flet.

### 5.2 Route table (D-13..D-21, decisions §M)

The bar has five fixed destinations, the same for every user: **Now · Schedule · My schedule · Map · More** (D-13). `/` opens Welcome until its Get started (D-14, D-287), then Now or where the user was (D-143).

| Path | Screen | Kind | Phase | Features |
|---|---|---|---|---|
| `/` | `Start`: boot View, then `/welcome` until Get started (D-287), else the last location of this process (D-143), `/now` on a cold start, or `/more/staff/lead` for a lead-retrieval account (D-16, #689) | index | P0 | SHELL-03 |
| `/welcome` | `Welcome` (`screens/welcome.py`): a one-View root without a bar or the drill (ux.md §6.8) | root, no bar | P2 | SHELL-02, STORE-07 |
| `/now`, `/schedule`, `/my-schedule`, `/map`, `/more` | tab roots (`Map` shows Rooms in P1, floors/expo/jobs in P2, `?tab=`) | root | P0–P2 | SCHED-25, SCHED-01..20, NEW-01, MAP-01, SHELL-09 |
| `/search` | `Search` (`?scope=`), opened from Now, Schedule, Map and More | global modal | P1 | NEW-02 |
| `/more/speakers`, `tracks`, `tracks/sprints`, `tracks/lightning-talks`, `tracks/open-spaces`, `tracks/keynotes` (the hub's pages of their own, More's pages again, listed before `:slug` so Back returns to the hub; `year_tracks.HUB_PAGES`, D-207, D-217, D-228), `tracks/<slug>`, `keynotes`, `open-spaces`, `lightning-talks`, `sprints` | programme screens (`tracks` doubles as the session-types legend) | child | P1 | SPKR, SCHED-21..24, EVT |
| `/more/app`, `/more/developer` | About this app (minimal in P1, D-73; complete in P2), Developer | child | P1 | DEV-01, DEV-04, DEV-05 (P1); INFO-03 (P2) |
| `/more/settings` | Settings (`screens/settings.py`): Appearance and High contrast (#421, D-286), then Data (`screens/settings_data.py`: Refresh now with the schedule's source and age, and the zone row; #422); Reminders between them (`screens/settings_reminders.py`: live with E3, else D-60's interim; D-401) | child | P2 | THEME-01, STORE-08, NOTIF-01 |
| `/my-schedule/settings` | Settings again, from My schedule's Reminder settings: under My schedule, so Back returns there (D-207's pattern, D-401) | child | P2 | NEW-01, NOTIF-01 |
| `/now/staff/<tool>` (`lead`) | a staff tool again, from Now's Scan badges card: under Now, so Back returns there (D-207's pattern, D-421); each tool's PR adds its route under More and Now | child | P3 | SHELL-06, SHELL-07 |
| `/more/app/licences`, `/more/app/licences/<key>` | `Licences`, `LicencePage` (`screens/licences.py`): the list, under About this app, and one text, under the list (D-296) | child | P2 | INFO-03 |
| `/more/sponsors`, `jobs`, `venue`, `wifi`, `help`, `about`, `psf`, `social` | sponsors and info screens | child | P2 | SPON, MAP-09..11, INFO |
| `/more/sign-in`, `account`, `staff/<tool>` (`lead`, `door`, `swag`, `coc`) | account and staff tools (guarded, §12.4): `/more/sign-in` is `SignInPage` (`screens/sign_in.py`, #685), its form only while a mock URL is set; `/more/account` is `AccountPage` (`screens/account.py`, its Sign out in `screens/account_sign_out.py`, #688), with its "Sign in again" at `/more/account/sign-in`; `/more/staff/lead` is `LeadScanner` (`screens/staff_lead.py`, #723, D-416), the shared scan screen, capturing leads through the outbox (D-426), behind the account's consent page (`screens/lead_consent.py`, #739, D-423); `/more/staff/coc` is `CocScanner` (`screens/staff_coc.py`, #759, D-432), the scan screen headed by the attendee directory's status; `/more/staff/swag` (and `/now/staff/swag`) is `SwagPickup` (`screens/staff_swag.py`, #768); `/more/staff/door` (and `/now/staff/door`) is `DoorCheck` (`screens/staff_door.py`, #764), with its session picker at `…/staff/door/session` (`screens/door_session.py`, D-433) | child | P3 | AUTH, LEAD, DOOR, SHIRT, MASK |
| `<any of the above>/<kind>/<id>` | `Drill` → detail screen | recursive child | P1 | SESS-12, #279 |

**Drill kinds:** `session/<id>` (P1; ids URL-quoted, e.g. `break--2026-05-13T12%3A30%3A00-07%3A00`), `speaker/<id>` (P1), `room/<slug>` (P1; `?highlight=<session id>`), `sponsor/<slug>` (P2), `plan/<plan id>` (P2; floor plans, expo, job fair; `?pin=<room key>`, `?booth=<n>`), `changes/<year>` (P2; Schedule changes, the year's change log, pushed on the View that opens it: Now's card, the Schedule's overflow, Settings › Data, or the "Schedule updated" SnackBar over any View, D-255).

Example: `/schedule/session/42/speaker/17/session/99/room/room-102a?highlight=99` is five Views; Back pops one at a time and, the query being dropped, never re-applies the highlight. Query parameters carry view options only, read once at mount; anything that must survive Back lives in `ViewMemory` (§6.3).

### 5.3 `routes.py` and `locations.py`

`routes.py` imports every screen to build `ROUTES`, and screens build links, so the helpers screens import live in `locations.py` (D-164): `drill_href()`, `parent_of()`, `start_target()`, `lands_on_lead()`, `query_of()`, `is_top_view()`, `use_query()` and the constants `TAB_ROOTS`, `WELCOME`, `LEAD_SCANNER`, `DRILL_KINDS` and `PAGES`. `start_target(last_location, search_base, *, onboarded, lead=False)` returns Welcome until Get started (D-287), then the last location of a new session in the same process (D-143), then, on a cold start, `/now`, or `/more/staff/lead` when `lead` (#689, D-16). `Start` passes `lead=lands_on_lead(prefs, account)`: a mock URL is set and `starts_on_lead(account.role_flags, prefs.start_screen)` (`core/staff_tools.py`: `lead_retrieval` and a Start screen other than `now`). The boot gate has restored the account and loaded the setting before `Start` mounts (§4.3), so there is no landing race and no flash; a link, a reminder tap or a `--route` start opens its own target. Sign in uses the same rule for its landing. `PAGES` lists every page path without a parameter, `/welcome` included, the one page without the drill; a test keeps it equal to the table's. `PAGES` takes the hub's pages from `year_tracks.HUB_PAGES` (D-228), which names the Tracks hub's pages of their own by their segment under `/more/tracks`, with the track each one is the page of (D-207); the year loader refuses a track slug that names one of them unless it is that track's page.

```python
# src/pycon_us/routes.py (excerpt)
DRILL = ft.Route(path=f":kind({'|'.join(DRILL_KINDS)})/:ident", recursive=True, component=Drill)


def pushed(path: str, component, *children: ft.Route) -> ft.Route:
    """A screen that can open details on top of itself (tab roots, More pages, search)."""
    return ft.Route(path=path, component=component, children=[*children, DRILL])


ROUTES = [
    ft.Route(index=True, component=Start),
    ft.Route(path="welcome", component=Welcome),                                 # no drill (D-287)
    ft.Route(path="search", component=Search, modal=True, children=[DRILL]),    # global modal (D-19)
    pushed("now", Now),
    pushed("schedule", Schedule),
    pushed("my-schedule", MySchedule),
    pushed("map", Map),
    pushed("more", More, pushed("speakers", Speakers),
           pushed("tracks", Tracks,  # the hub's pages of their own first (year_tracks.HUB_PAGES, D-207)
                  pushed("sprints", Sprints), pushed("lightning-talks", LightningTalks),
                  pushed("open-spaces", OpenSpaces), pushed("keynotes", Keynotes),
                  pushed(":slug", TrackPage)),
           pushed("keynotes", Keynotes), pushed("open-spaces", OpenSpaces), pushed("sprints", Sprints),
           pushed("lightning-talks", LightningTalks), pushed("app", AboutApp), pushed("developer", Developer)),
    UNKNOWN,                                  # last: ft.Route(path=":unknown*", component=NotFound) (D-270)
]


@ft.component
def Drill():
    """One detail level of the drill: dispatch on the kind segment (D-17)."""
    params = ft.use_route_params()
    ident = unquote(params["ident"])
    match params["kind"]:
        case "session":
            return SessionDetail(session_id=ident)
        case "speaker":
            return SpeakerDetail(speaker_id=ident)
        case "room":
            return RoomDetail(room_slug=ident)
        case "sponsor":
            return SponsorDetail(sponsor_slug=ident)
        case "plan":
            return PlanViewer(plan_id=ident)
        case "changes":                      # the year's change log (D-255)
            return ScheduleChanges(year=ident)
        case kind:  # DRILL only matches DRILL_KINDS
            raise ValueError(f"no screen for the drill kind {kind!r}")
```

```python
# src/pycon_us/locations.py (excerpt)
PAGES = frozenset({*TAB_ROOTS, "/search", "/more/speakers", "/more/tracks", ...})   # no parameter; a test keeps it = ROUTES'


def drill_href(view_path: str, kind: str, ident: str) -> str:
    """The location that pushes one detail level on top of the View at `view_path`."""
    return f"{view_path.rstrip('/')}/{kind}/{quote(ident, safe='')}"


def parent_of(location: str, search_base: str = "/now") -> str:
    """Where Back goes (D-19): drop the last drill pair, else walk up to the nearest page.

    `/more/staff/lead` returns `/more`, because `/more/staff` is not a page. `/search` itself returns
    to `search_base`, the location (query included) it was opened from.
    """
    parts = urlparse(location).path.strip("/").split("/")
    if parts == ["search"]:
        return search_base
    if len(parts) >= 3 and parts[-2] in DRILL_KINDS:
        return "/" + "/".join(parts[:-2])
    parent = parts[:-1]
    while parent and "/" + "/".join(parent) not in PAGES:
        parent.pop()
    return "/" + "/".join(parent)
```

```python
# src/main.py (excerpt)
setup_logging()                               # once per process, at import (D-163)
MEMORY = ViewMemory()                         # one per process: a new session reuses it (D-143, F29)


def main(page: ft.Page):
    @report_errors                            # a page handler too (§16.3, D-163)
    def on_view_pop(e: ft.ViewPopEvent):
        page.navigate(parent_of(e.route, MEMORY.search_base))

    page.on_view_pop = on_view_pop            # before render_views: the Router hands it every pop (F6)
    page.render_views(App, MEMORY)            # App passes memory on to Services.create()
```

`Start` (the index route `/`) navigates to `start_target(memory.last_location, memory.search_base, onboarded=prefs.onboarded)`: `/welcome` while Welcome's Get started has not been tapped (D-287), else the last location when it is set, else `/now`, so a new session after an activity recreation rebuilds the stack the user was on (D-143). Only a plain start comes to `/`: a deep link or a `--route` start opens its own target, and Welcome waits for the next plain start. Reset app, which clears `onboarded`, navigates to `start_target()` too, so it lands on Welcome (D-198). `AppScaffold` records the top View's `page.route` there. A location under `/search` restores its `search_base` instead: the Router builds a global modal over its last non-modal location, which in a fresh Router is `/`. For the same reason a direct `/search` entry mounts `Start` below the modal, so `Start` navigates only when it is the top View (`is_top_view()`).

`use_query()` (U9 interim) parses `ft.context.page.route`'s query once, when its View mounts, and only for the top View (`is_top_view(page.route, view_path)`, never `use_route_location()`, which under a global modal is the opener's location for the Views below): a deep entry builds the Views below too, and the query is not theirs (D-164). Each screen reads `view_path = ft.use_view_path()` at the top of its render (rule 4); its handlers call `page.navigate(drill_href(view_path, "speaker", sid))`, never an absolute path, so details work under every root and under search. `parent_of()` is unit-tested against every route shape; the app's `on_view_pop` and the pushed views' back arrow (§5.5) both use it. The handler goes once U18 is in the pinned Flet; the back arrow stays (D-10). `Drill` returns a component, as route components compose (S4 confirmed, D-141). An unknown location matches only the table's last route, `UNKNOWN` (`:unknown*`), and shows `NotFound`, a one-View stack built with `AppScaffold(unknown=True)`: "This page isn't in the app" with "Go to Now", never the path, and Back, the predictive gesture and its arrow go to Now, as on a non-Now root (D-142, D-270), while `last_location` keeps the last real page (D-143); an unknown id shows its detail's not-found state on its own level under the back arrow, with its list as the way out, never a redirect (D-186, ux.md §4.1).

### 5.4 Search (D-19)

One `Search` component on the global modal route `/search`, opened from Now, Schedule, Map and More with a preset scope (`/search?scope=sessions`, `/search?scope=places`, D-351); the opener first records its own location, query included, in `ViewMemory.search_base`. Results push details with `drill_href()` (`/search/session/42`), and our `page.on_view_pop` sends Back to `parent_of()`: from a result to the results, from search to `search_base` (§5.3). Query and scope live in `ViewMemory`. S4 confirmed search → result → detail → Back → Back to the results with the query kept (D-141). Each opening starts an empty search: the opener clears `search_query`. The field updates per keystroke; the search runs after a 250 ms pause (an effect each keystroke restarts), at once on the action key, a scope chip or Clear (D-193). The result list renders each type's first rows (`core.search.first_results()`: 50 sessions, 20 speakers, every place, 20 sponsors) and a "Show all" row that renders the rest on request, so a one-letter query that finds most of the feed renders about as fast as a narrow one (D-218). On return Flutter gives the search field its focus back only when it had it as the result opened, so the first Android Back then closes the keyboard; D-193 keeps that.

### 5.5 Scaffold, tabs and Back (D-15..D-18)

```python
# src/pycon_us/ui/scaffold.py (excerpt; D-165)
def AppScaffold(*, title: str, body: ft.Control, actions: list[ft.Control] | None = None,
                on_retap: Retap | None = None) -> ft.View:
    """A screen's View: the app bar, the bottom bar on roots, the Back rules and the body (D-10, D-17, D-144).

    A plain builder that each screen calls unconditionally, so its hooks are safe (rule 4).
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    wide = use_layout().wide                                       # the rail from 600 dp (D-277)
    is_root = view_path in TAB_ROOTS
    back_to_now = is_root and view_path != "/now"
    if is_top_view(page.route, view_path):                         # the top View, not one under a modal (D-164)
        svc.memory.last_location = page.route                      # where a new session returns (D-143)

    @report_errors
    def go_back():
        page.navigate(parent_of(view_path, svc.memory.search_base))  # /search → its opener (D-19)

    @report_errors
    async def leave_for_now(e: ft.Event[ft.View]):
        page.navigate("/now")
        await e.control.confirm_pop(False)

    @report_errors
    async def let_pop(e: ft.Event[ft.View]):                         # asked only if can_pop refused
        await e.control.confirm_pop(True)

    @report_errors
    async def switch_tab(index: int):                                   # bar or rail; a re-tap too (S4, F95)
        root = TAB_ROOTS[index]
        if root != view_path:
            page.navigate(root)                                        # one shared root key: a swap, not a push
        elif on_retap is not None:
            await on_retap()                                           # e.g. use_scroll_to_top()'s action

    on_confirm_pop = None                                              # Now keeps none: the system exits (D-142)
    if back_to_now:
        on_confirm_pop = leave_for_now
    elif not is_root:
        on_confirm_pop = let_pop                                       # Back closes a dialog first (F46, D-208)
    return ft.View(
        route="/" if is_root else view_path,                       # roots share a key: no transition (D-142)
        padding=0,
        appbar=ft.AppBar(
            title=ft.Text(title),                                      # on a root, in Semantics(identifier="<tab>.title") (D-170)
            center_title=False, automatically_imply_leading=False,
            leading=None if is_root else merged(ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Back", on_click=go_back)),
            actions=actions or [],
        ),
        navigation_bar=navigation_bar(view_path, switch_tab) if is_root and not wide else None,  # D-144, D-277
        can_pop=not back_to_now,
        on_confirm_pop=on_confirm_pop,
        # A root's body sits beside its rail, shown from 600 dp: one tree for both classes (D-277).
        controls=[ft.SafeArea(expand=True, content=beside_rail(view_path, switch_tab, wide, Shown(body))
                              if is_root else Shown(body)), GutterProbe()],
    )


@ft.component
def Shown(body: ft.Control) -> ft.Control:
    """Return body unchanged; log D-112's mark once per feed version per session.

    Its own component, so only this leaf reads Conference: a refresh re-renders it, and
    it hands back the same body (Flet keeps a retained child as is), not the screen.
    """
    svc = use_services()
    conference = use_conference()
    version, source = conference.version, conference.source

    @report_errors
    async def log_shown():
        if version in svc.shown_versions:                          # another screen showed it first
            return
        svc.shown_versions.add(version)
        # A newer version re-runs the effect and Flet cancels this run; this version was rendered.
        await asyncio.shield(log_when_shown(svc.storage, source, version))

    ft.use_effect(log_shown, [version])
    return body


@report_errors
async def log_when_shown(storage: Storage, source: Source, version: int) -> None:
    await storage.get(THEME)                                       # the patch has reached Flutter
    logger.info("Content shown: %s feed, version %d", source, version)
```

- A **tab switch** leaves that root alone on the stack (D-17); roots restore day, filters and scroll from `ViewMemory`/`Prefs` and never scroll by themselves (D-18, #313). **Back** on a root other than Now goes to Now; on Now it exits (Android).
- **The bar is on tab roots only** (D-144, #149): on pushed Views it travelled with the page (iOS) or doubled (Android) in every transition. Re-tapping the active tab scrolls its root to the top; from a pushed View, Back leads to the root. U23 (a shell bar outside the `Navigator`) would let it return to every View.
- **Back arrow (D-10):** Flutter's implied back button shows `arrow_back_ios_new_rounded` on iOS (Flet's theme has no `platform`, F8), so pushed views always show the Material back arrow, which navigates to `parent_of(view_path, memory.search_base)` (D-19), so Search's arrow returns to its opener with no parameter (D-165). S4 showed the Material arrow and a left-aligned title on the iOS simulator.
- **The bottom bar (#75, D-166):** `ui/navigation.py`'s `navigation_bar(root, on_change)` is a `NavigationBar(selected_index=TAB_ROOTS.index(root), label_behavior=ALWAYS_SHOW, destinations=..., on_change=...)`, never adaptive, on tab roots only (D-144). A re-tap of the active tab fires `on_change` too (S4), and the scaffold hands it to the screen's `on_retap`; any other tab navigates to its root. A root gets its action from `use_scroll_to_top()`: a ref for its list and an action that awaits `scroll_to(offset=0, duration=300)` (0 under reduced motion, D-34). A `NavigationBarDestination` has no `Semantics` of its own, so each icon is wrapped in an unlabelled `Semantics(identifier="app.nav.<tab>")`, which Flutter merges into the destination's node (D-166). The destinations, in `TAB_ROOTS`' order:

  ```python
  TABS = (
      Tab("/now", "Now", ft.Icons.SENSORS_OUTLINED, ft.Icons.SENSORS),
      Tab("/schedule", "Schedule", ft.Icons.CALENDAR_MONTH_OUTLINED, ft.Icons.CALENDAR_MONTH),
      Tab("/my-schedule", "My schedule", ft.Icons.STAR_BORDER, ft.Icons.STAR),
      Tab("/map", "Map", ft.Icons.MAP_OUTLINED, ft.Icons.MAP),
      Tab("/more", "More", ft.Icons.MORE_HORIZ, ft.Icons.MORE_HORIZ),
  )  # Tab.identifier: "app.nav." + the root, "-" as "_" (app.nav.my_schedule)
  ```
- **Status strip (D-32, D-165, D-175, D-181, D-200):** `StatusStrip(auto_refresh=False)`, in `ui/status_strip.py` with the minute tick, is a component the screens that show the feed's state put first in their body (Now, Schedule, My schedule); hidden when fresh, otherwise an icon, `strip_line()`'s text and Refresh, one live region (`app.status`); its bar shows any refresh (`Conference.refreshing`), its line only the user's (D-181). It ticks every 60 s through `Services.run_every` (re-rendering when the minute has changed), and on Now and Schedule (`auto_refresh=True`) the tick also starts a due refresh (§4.3). It is `use_strip()` (the store, the tick and Refresh, returning a frozen `Strip`) with `strip_view()` (a pure builder): the Schedule calls the two itself, so at the largest text sizes its memoised day lists get only the `Strip` value in their head (D-345, F150). `use_minute()` is the same tick for any other time-dependent view: it re-renders its component when the minute of `clock.now()` changes (the Map's "Now:" lines, D-188). `SectionHeader(text)` heads a group of rows.
- **Tablets and landscape (P2, D-09, D-277):** the `Layout` store (`layout.py`) holds one bool, `wide` (600 dp and wider, M3's medium window class), built from `page.width` and set by the app's one `page.on_resize` (`follow_width()`, from an effect of `App`'s); assigning the same value notifies nothing (F5), so only a crossing re-renders the screens, through `AppScaffold`'s `use_layout()`. On a tab root the body sits in a `Row` inside the `SafeArea`, beside `navigation_rail()` (`View.navigation_bar` takes a `NavigationBar`, or a `CupertinoNavigationBar`, which D-10 rules out, but not a `NavigationRail`), which is `visible` only when `wide`; then the View has no `navigation_bar`. The tree is the same in both classes, so a rotation or a resize swaps the bar and the rail without rebuilding the body (D-18), and under 600 dp the hidden rail is no widget at all, so the phone layout is unchanged pixel for pixel. The rail is built from `TABS` (`label_type=ALL`, `group_alignment=-1`, `min_width=80`, `scrollable=True`), and taps reach the bar's handler, re-tap included. Its destinations carry no identifier (#163, F95). Content is centred at 720 dp on reading screens and 840 dp on lists (P2-80, D-305): `Layout.room` holds the body's width (the window less its side insets, from `page.media.padding` and `page.on_media_change`) once it is over 720 dp, and each screen's `use_margin(READING | LIST)` (`ui/widths.py`) turns it into side margins, less the rail on a root, which the screen puts in its list's padding (`sides()`) and around its fixed chrome (`capped()`).
- **Insets and system bars (#311, D-12):** `SafeArea` bodies, `use_safe_area=True` sheets, and `Theme.system_overlay_style` per colour scheme (§15, D-113); S1 checked 3-button and gesture navigation, in light and dark. The `SafeArea` also keeps landscape content clear of the side navigation bar.

### 5.6 Deep links (D-21, NEW-07, P2)

One common `[tool.flet.deep_linking]` table sets `scheme` and `host`, `confcompanion` and `app` (D-452); the pin resolves it for Android and iOS (`flet-dev/flet#6953`, D-269), and the build template registers nothing when either is missing. Android matches scheme and host; iOS registers the scheme alone, and the host never reaches `page.route` on either platform. Link paths are internal routes: `<scheme>://<host>/schedule/session/42` arrives as `page.route == "/schedule/session/42"` and builds `[Schedule, Session]`, so Back never exits. Cold, the path is the start route, which the Router reads as it mounts after the boot gate (a link during the gate included); warm, it is a route change; after Back on Now (F29) it starts a new session at its own route, never through `Start`. A reminder tap is the same route (D-396): before the boot gate opens, the `Scheduler` holds it, the start waits for E3's first answer so the tap that launched the app is in by then (F246), and `Start` navigates to `locations.launch_target()`, the tap before `start_target()`; once the gate is open (`reminder_schedule.use_reminder_taps()`), a tap navigates at once. Before the Router sees a change, `ui/modals.py` closes the open dialogs and sheets and waits for their dismissal (at most 1 s), since Flet draws them in the new top View without their route (F109); SnackBars and Banners stay, and pickers and popup menus stay until U89 (D-291). `Search` records where a link to it landed (`record_opening()`), so its Back returns there. `tests/test_deep_links.py` and `tests/test_modals.py` render the real route table in a Flet session for all of it (D-291). Reminder taps use the same paths. "Share" uses the public `presentation_url` (`conference.toml`), never the scheme; synthetic ids share no URL.

---

## 6. State model

### 6.1 Stores (D-69)

All are `@ft.observable @dataclass(eq=False)`, each in its own module with its context and hook: `Conference` in `state.py`, `Prefs` in `prefs.py`, then `favorites.py` (P1), `change_log.py` (P2, D-301), `layout.py` (P2, D-277), `account.py` and `staff.py` (P3) (D-160); `ViewMemory`, which is no store, is `memory.py`'s (§6.3, D-231). Fields starting with `_` never notify. A method that persists assigns the field even when the write fails, and says so (`False`, or `Change.saved`) so the caller can say the change was not saved (D-120). `Prefs.save` writes before it assigns; `Favorites` assigns first and writes after, so a star changes at once and two quick taps never lose one another (D-172). Each store and `ViewMemory` has a `reset()` back to what a fresh install has, which only the Developer screen's Reset app calls, after `Storage.clear_prefs()` (D-198); `Layout`, which holds a device fact and nothing the user chose, has none (D-277).

| Store | Fields | Methods | Phase |
|---|---|---|---|
| `Conference` | `data: ConferenceData \| None` (frozen, `eq=False`); `source: "none"\|"bundled"\|"cache"\|"network"`; `fetched_at: datetime \| None` (aware, D-145); `refreshing`; `problem: None\|"offline"\|"server"`; `version` (memo key; not incremented by a refresh that brings the same feed, D-224); `_task`; `_started_at` (D-175); `_asked` (D-181); `_feed_url` (D-187); `_digest`, the published feed's SHA-256 (D-224); `_shown_url`, the feed URL the published feed counts as, and `_change_log`, the session's `ChangeLog` (P2, D-301) | `load_local`, `start_refresh`, `refresh`, `age`, `status` (D-146); `refresh_due`, `start_refresh_if_due` (D-175); `async set_feed_url(url, storage)`, which deletes the cache and the change log on any change after the load (D-187, D-244, D-255); `async reset(storage, year) -> bool` (D-198) | P0 |
| `ChangeLog` | `batches` (newest first, the last 14 days; the one public field, so a batch notifies once); `_favorites`; `_fetched` (`pycon.<year>.fetched`); `_announce`; `_saves` and `_writing` (the log's writes, kept until they land and run one at a time, each saving the log as it is when its turn comes); `_generation` (counts deletions and resets: `delete()` lets a write under way land, and a write asked for before a deletion or a reset that has not started is dropped, so it never brings the old feed URL's file back) | `load(storage, zone)`; `record(storage, before, after, current)`, the hand-off; `recent(now)` (id → the kinds of its time, room and title changes, 24 h; D-315); `take_announcement()`; `has_unseen`; `unseen_saved(saved, now)` (Now's card and Settings › Data); `mark_seen(storage, batches=None)`, sync, its write a kept task (ux.md §6.4, #436); `delete(storage, reason)`; `reset()` (§7.9, D-255, D-301) | P2 |
| `Prefs` | persisted: `theme`, `high_contrast`, `excluded_tracks` (a tuple), `onboarded`, `reminders` (a frozen `ReminderSettings`: `session_lead`, `lightning`, `open_space`, `keynote`, `primer`; `reminder_settings.py`, D-275), `dev`; device, not persisted: `os_high_contrast`, `os_dark`, `reduce_motion`, `time_above` and `time_measured` (measured by `GutterProbe`; the boot gate waits for it, D-216); `loaded` | `load(storage)`, `save(storage, *, theme=..., high_contrast=..., ...) -> bool` (D-160); properties `high_contrast_on`, `dark`; `motion_ms(ms)`, 0 under reduced motion (D-173); the Developer options read from `dev`: `developer_unlocked`, `developer`, `fake_now`, `feed_url` (D-187); `reset()` (D-198) | P0 |
| `Favorites` | `ids: frozenset[str]` (saved sorted as `list[str]`, F12; D-172); `loaded: bool` (read; until then edits are not saved) | `load(storage)`; `toggle`, `add_many`, `remove_many` and `undo`, each taking `storage` and returning a `Change(added, removed, saved)` for its Undo; `replace(storage, ids) -> bool`, the account's list taken in without an Undo (P3, D-406); `reset()`, without a write (D-198) | P1 |
| `Layout` | `wide: bool` (the window is 600 dp wide or wider: the rail; D-277) | `set_width(width)`, which notifies only on a crossing of 600 dp (F5); `follow_width(page, layout)` sets `page.on_resize` | P2 |
| `Account` | `restored`, `signed_in`, `signing_in` (the single flight), `email`, `nickname`, `lead_retrieval`, `door_check` (the API's `door_check_in`), `mask_violation`, `is_speaker` (absent flags False, STORE-05), `error` (the last sign-in's failure, a `SignIn`); `expired` (the server refused the key: still signed in as the owner, no private call until a sign-in clears it; not stored, D-403); `_secrets`, the key and secret (#684); `favorites_dirty` (this device's favourites have not reached the account: an edit or the first sync is waiting; written by `services.favorites_sync`, D-406) (the scanner consent is in no store: the Lead scanner reads `pycon.staff_scanner_consent` as it opens, D-423) | `async restore(storage, credentials)`, strict: signed in only with `pycon.account` and both secrets, any part without the rest removed, a failed read removing nothing (STORE-03); `async sign_in(api, storage, credentials, email, password) -> SignIn` (`SIGNED_IN`, `BUSY`, `WRONG_CREDENTIALS`, `OFFLINE`, `TIMEOUT`, `SERVER_ERROR`, `NOT_SAVED`), which removes the old `pycon.account` and then writes the key, the secret and the new one before `signed_in` turns True (STORE-04), so a kill between the writes never pairs one account's profile with another's secrets; `async sign_out(storage, credentials) -> bool`, every removal before it notifies, favourites kept (D-48); `async reset(storage, credentials) -> bool`, a sign-out for Reset app (D-198); sign-in, sign-out and reset take turns on one `asyncio.Lock`, so a late sign-in reply never undoes a sign-out or reset; `credentials()`, what `ApiClient` signs with, Nones signed out; `owner`, the lower-cased email; `refresh_flags(api, storage, *, closed) -> Task \| None`, one `check_features` at a time in a kept task (`_refresh`), at start, on resume and on the Account screen's mount: an absent flag False, `is_speaker` untouched, a change saved to `pycon.account` and notified, no answer keeping the flags, a refused key setting `expired`, and nothing written for a closed session or once the account changed meanwhile (#686, D-403). Kept when the mock URL is cleared or changed (D-398) | P3 |
| `Staff` | `pending`, `failed`, `synced` (the signed-in account's rows by status); `syncing` (a pass under way, and what keeps a second from starting); `last_sync_at` (the end of the last pass the server answered throughout, epoch seconds); `last_error` (why the last pass stopped or a row was refused); `offline` (the last pass ended on a `NetworkError`: the sync chip's "Offline · 3 queued", #694); `revision` (bumped whenever the rows change, so a list re-reads); later `sponsor` (#39); the memory-only PII, the door's attendee list and the CoC directory, live in their screens' state instead (#765, D-432) | `update_counts(counts)`, called after every change of the rows (a `None` from a failed read keeps the counts shown, D-120); `clear()`, signed out (#692); `retry_failed(db, owner, now)`, the queue sheet's Retry failed, which saves each failed row as `outbox.retry_failed()` makes it and recounts (#694); later `select_sponsor` | P3 |

Year data is a frozen value in `Services.year`, and capabilities are constants: neither is a store.

### 6.2 `Conference`

```python
# src/pycon_us/state.py (excerpt)
@ft.observable
@dataclass(eq=False)                      # a store compares by identity
class Conference:
    """This year's processed feed, where it came from and how fresh it is (D-38, D-39)."""

    data: ConferenceData | None = None
    source: Literal["none", "bundled", "cache", "network"] = "none"
    fetched_at: datetime | None = None    # aware (D-145)
    refreshing: bool = False
    problem: Literal["offline", "server"] | None = None
    version: int = 0
    _task: asyncio.Task[None] | None = field(default=None, repr=False)
    _asked: bool = field(default=False, repr=False)   # the user's refresh; automatic ones are quiet (D-181)
    _digest: bytes | None = field(default=None, repr=False)   # SHA-256 of the published raw feed (D-224)
    _feed_url: str | None = field(default=None, repr=False)   # the Developer feed URL (D-187)

    async def set_feed_url(self, url: str | None, storage: Storage) -> None:
        """Refresh from `url` from the next refresh on; None is the year's feed (D-187, D-244, D-255)."""
        if url == self._feed_url:
            return
        self._feed_url = url                  # first: a refresh from the old URL sees the change
        if self.data is not None:             # after the load, the cache and the log are the old URL's
            # Each deletion waits for every queued write of either file (D-255).
            await storage.delete_feed("the feed URL changed")
            await self._change_log.delete(storage, "the feed URL changed")   # file and memory

    async def load_local(self, storage: Storage, year: YearData) -> None:
        """Publish the persistent cache, or the bundled snapshot when there is no usable cache."""
        cached = await storage.read_feed()
        if cached is not None:
            try:
                data = feed.process(cached.raw, year.feed_settings)
            except feed.FeedError as error:
                await storage.delete_feed(f"it does not parse: {error}")   # logs (D-39)
            else:
                self._publish(data, feed_digest(cached.raw), "cache", datetime.fromtimestamp(cached.saved_at, UTC))
                return
        snapshot = year.read_snapshot()                      # bundled with the app (D-135)
        data = feed.process(snapshot.raw, year.feed_settings)
        self._publish(data, feed_digest(snapshot.raw), "bundled", snapshot.captured_at)

    def start_refresh(self, storage: Storage, year: YearData, *, transport=None, closed=None) -> asyncio.Task[None]:
        """Start a background refresh unless one is in flight; return the one that runs (D-145).

        `closed` is `Services.closed`: a refresh that ends after it is set writes nothing (D-147).
        """
        if self._task is None or self._task.done():
            url = self._feed_url or year.conference.feed_url
            self._task = asyncio.create_task(self._refresh(url, storage, year, transport, closed))
        return self._task

    async def refresh(self, storage: Storage, year: YearData, *, transport=None, closed=None) -> None:
        """The user's refresh: shared with any running one, and shown as "refreshing" (D-181)."""
        task = self.start_refresh(storage, year, transport=transport, closed=closed)
        if not self._asked:
            self._asked = True
            if self.refreshing:               # joined a quiet refresh: the strip changes now
                cast(ft.Observable, self).notify()
        await asyncio.shield(task)

    async def _refresh(self, url: str, storage: Storage, year: YearData, transport) -> None:
        # After the fetch and again after the cache write: a refresh whose session closed
        # (F30) or whose `url` is no longer the one in effect writes nothing (D-244).
        self.refreshing = True
        try:
            raw = await api.fetch_feed(url, transport=transport)
            digest = feed_digest(raw)
            # The published feed's bytes: the same data, so neither processed nor published (D-224).
            data = None if digest == self._digest else feed.process(raw, year.feed_settings)
        except api.NetworkError:
            self.problem = "offline"                              # D-146
        except (api.ApiError, feed.FeedError):
            logger.warning("Feed refresh failed; keeping the current data", exc_info=True)
            self.problem = "server"
        else:
            await storage.write_feed(raw)                          # atomic, after a good parse (D-39)
            if data is None:
                self._confirm()               # fetched_at, problem, source: the freshness only (D-224)
                return
            before = Published(self.data, self.source, self._shown_url)
            self._publish(data, digest, "network", clock.now(), url)
            # The hand-off (D-301): diffed only against a feed from the URL fetched; over the
            # bundled snapshot only for saved sessions, before `pycon.<year>.fetched` is set.
            # It checks `discarded()` again just before it writes the log (D-255).
            await self._change_log.record(storage, before, Published(data, "network", url), current)
        finally:
            self._asked = False               # the next refresh starts quiet (D-181)
            self.refreshing = False

    def _publish(self, data: ConferenceData, digest: bytes, source: Source, fetched_at: datetime, url: str) -> None:
        self._shown_url = url             # the cache's: the URL in effect; the snapshot's: the year's (D-301)
        self.data, self._digest = data, digest   # eq=False: always notifies (F5)
        self.source, self.fetched_at, self.problem = source, fetched_at, None
        self.version += 1                 # writes in one block give one re-render


ConferenceCtx: ft.ContextProvider[Conference | None] = ft.create_context(None)


def use_conference() -> Conference:       # raises RuntimeError without a provider
    ...
```

- What the store needs that reads or writes none of its fields is `feed_refresh.py`'s, imported by name (D-231): the types `Source`, `Problem` and `Status`, the stale limits and `REFRESH_EVERY`, `feed_digest()`, `fetch()` (the `try` above: one network attempt that returns the bytes, their digest and the processed feed, or the `Problem`) and `log_unexpected()`, `start_refresh`'s done callback.
- `age()` is the `timedelta` since `fetched_at` by `clock.now()`, never negative; `status(info)` is what the strip says: `refreshing` (only while a refresh the user asked for runs: an automatic one is quiet, D-181), `offline`, `problem`, `stale` (over 6 h on conference days, else 24 h) or `fresh` (D-146). `start_refresh()` records when it starts a refresh (`_started_at`), and `refresh_due()` / `start_refresh_if_due()` are the automatic triggers' rule (§4.3, D-175). One shared `_task` makes refresh single-flight, and it never deletes the cache first (fixes EVT-07, SPON-08). `transport` is for tests (`httpx.MockTransport`); the app leaves it None.
- With `closed` set (the session was replaced, D-147), `_refresh` returns after the fetch, or after the cache write, without another write, and leaves `refreshing` as it is: every store write would reach the destroyed session (F30). Without `closed` (tests, tools) it never stops early.
- A refresh that fails with an unexpected exception is logged by `start_refresh`'s done callback as soon as it ends (D-71), and `refresh()` callers also get the exception raised; asyncio's default handler, which logs through `logging`, covers anything else once its task is released (F37, D-163). Expected failures never raise.
- A refresh that brings the published feed's bytes again (most of them: the feed changes a few times a day) publishes nothing: `data` and `version` stay, so no memo is rebuilt and no list re-renders or remounts, and the Schedule's "Now" button stays hidden; `_confirm()` updates `fetched_at`, `problem` and `source` only, and the bytes are still cached, so the next start's age is the refresh's (D-224). A changed feed publishes a new version, and the P2 diff runs only then.
- `feed.process` is pure and runs on the loop (D-109: S1 measured 3-4 ms for `json.loads` plus a processing stand-in on the emulator). If the logged time exceeds 150 ms on the iPhone, revisit it per D-109; `asyncio.to_thread` does not shorten a GIL-bound stall. No diff against the bundled snapshot (first install) unless sessions are saved, and then only of theirs; none against a feed from another feed URL (D-255); parser changes cannot cause false diffs, since the cache keeps raw bytes.

### 6.3 `ViewMemory` (D-18)

```python
# src/pycon_us/memory.py (D-231)
@dataclass
class ViewMemory:
    """Where the user left each screen, for this app process (D-143).

    Plain, not observable: a screen reads it once to seed its own state and writes it back from its
    handlers, so remembering a scroll offset never re-renders another screen.
    """

    schedule_day: date | None = None     # the Schedule's day; None opens on today (D-192)
    schedule_offsets: dict[date, float] = field(default_factory=dict)  # each day's scroll end
    schedule_places: dict[date, Place] = field(default_factory=dict)  # each day's top item and how far in (D-331)
    schedule_basis: tuple[float, float, bool] | None = None  # the widths and time position they were measured at (D-331)
    jumped_on: date | None = None        # the conference day of the last jump, asked or not (D-204)
    search_query: str = ""
    search_scope: str = "all"
    search_base: str = "/now"            # where search was opened from; Back returns there (D-19)
    map_tab: str = "rooms"               # the Map's pane, a PANES slug; ?tab= seeds it (#391)
    map_offsets: dict[str, float] = field(default_factory=dict)  # each Map pane's scroll end, by slug (#391)
    map_zooms: dict[str, tuple[float, float, float]] = field(default_factory=dict)  # a plan pane's last transform (D-312, #402)
    expo_booth: str = ""                 # the selected expo booth, for the pane and plan/expo (#402)
    expo_view: str = ""                  # "map" or "list"; empty opens the List under a screen reader (#404)
    expo_by_name: bool = False           # the expo List's Sort by name (#404)
    expo_query: str = ""                 # the expo List's filter text (#404)
    expo_offset: float = 0.0             # the expo List's scroll end (#404)
    last_location: str = ""              # the top View's route; Start returns a new session there (D-143)
    room_highlights: dict[str, str] = field(default_factory=dict)  # room View path -> the session it lit up (D-194)
    plan_pins: dict[str, str] = field(default_factory=dict)  # floor viewer View path -> the pin it shows, pulsed once (#388)
    plan_tables: dict[str, str] = field(default_factory=dict)  # floor viewer View path -> the job fair table selected (#464)
    spotlight: str = ""                  # the sponsor slug Now's spotlight thanks, picked once per process (D-298)
    rng: Random = field(default_factory=Random, compare=False)  # the pick's source; seeded in tests
```

Filters are preferences (persisted in `Prefs`); positions are process memory (here). `reset()` returns every field to its default, as after a fresh install (Reset app, D-198). One `ViewMemory` lives as long as the Python process, so a new session after an activity recreation or a Back exit on Android (F26, F29) finds the positions and the last location as the user left them (D-143).

### 6.4 Screen pattern

A screen reads its stores through hooks, memoises its view model with `ft.use_memo(lambda: queries.x(conference.data, ...), [conference.version, favorites.ids, ...])` (lists passed as tuples; `favorites.ids` is a frozenset already, D-172), builds handlers and effects as named functions, each wrapped in `report_errors` (sync or async, D-163), and returns `AppScaffold(...)`. A list of sessions gets its row views from `use_session_views(conference, ids, use_24h=...)` and its one star handler from `use_favorite_toggle(favorites)` (`ui/session_rows.py`, `ui/badges.py`; D-184): the handler toggles, gives the selection click on an add, and shows the one SnackBar of ux.md §4.4 with `page.show_dialog`, whose `SnackBarAction("Undo")` awaits `favorites.undo(svc.storage, change)` with the `Change` the edit returned (D-172). Lists memoise the whole path (D-153): `ft.memo` day lists or sections given only the favourites under them, memoised group items (slots), and `SessionRow` / `NoticeRow`, memoised components keyed by session id on `(row view, is_favorite, on_toggle, tokens)`; props are frozen values built once per feed version and stable callbacks (`use_callback`), since `ft.memo` compares by identity first and only skips its own body (F34). Text fields are controlled (D-157). A list whose keyed items `scroll_to(scroll_key=...)` must reach gets `cache_extent=FULL_LIST_EXTENT` so every item is built; other lists stay lazy (D-154).

---

## 7. Data pipeline

### 7.1 Sources (D-38, D-39) and the status strip (D-32)

| Source | Where | Used |
|---|---|---|
| Network | `fetch_feed(conference.feed_url)`: `httpx.AsyncClient`, 10 s timeout | background refresh |
| Persistent cache | `<data dir>/feed-<year>.json`, raw bytes; `saved_at` = file mtime | every start when present |
| Bundled snapshot | `data/<year>/conference.json`, read by `YearData.read_snapshot()` and refreshed by `tools/update_snapshot.py`, which refuses a feed that does not parse cleanly and also writes `conference.toml`'s `snapshot_captured_at` (D-135) | first launch, or a corrupt cache |

The strip (`StatusStrip`, D-165) is hidden when fresh; shows "Updating the schedule…" with an indeterminate `ProgressBar` while a refresh the user asked for runs; during an automatic refresh it keeps its line, icon and button and shows only the bar (hidden over fresh data, D-181); "Updated 9 hours ago · Refresh" when stale (6 h on conference days, else 24 h), "Offline · schedule from Tue, May 12, 10:42 AM · Refresh" when `problem == "offline"`, and "Couldn't update · schedule from … · Refresh" when `problem == "server"`; without data the last two say "Offline · no schedule yet" and "Couldn't update · no schedule yet", and a stale status "No schedule yet". Skeletons only when `data is None` (impossible after bootstrap). A failed refresh leaves data and cache untouched.

### 7.2 Feed shape (2026; `docs/research/ionic/data-layer.md` §9)

Top level: `conference` (`sponsors` by level, `content` HTML blocks), `schedule` (728 slots), `open-spaces` (123), `posters` (25), `sprints` (24), `job-listings` (13). Gotchas: three `conf_key` spaces collide (hence `+9000` and `poster-detail-` ids); durations are minutes in `schedule` and seconds in `open-spaces` (always use `start`/`end`); markup is mixed per field (HTML descriptions and bios, Markdown open spaces, plain sponsor text, Markdown links in slot names); speakers are linked **by name**; `cancelled` is always false (cancellations arrive as placeholder slots).

### 7.3 Processing rules (`core/feed.py`, `core/records.py`, `core/rules.py`, `core/names.py`, `core/slugs.py`; D-41, each rule has a named test)

`process(raw: bytes, settings: FeedSettings) -> ConferenceData`, where `FeedSettings` (frozen, `YearData.feed_settings`) holds the time zone, the site URL, the hall prefix (D-122), the lightning talks' location (D-124), the display-time overrides and the sprint rooms (`sprint_rooms`, the labels of `map.toml`'s pins marked `sprint`; MAP-08, #392). It lives in `core/rules.py` with `DisplayTimeOverride`. A structurally wrong feed raises `FeedError`: not JSON, not an object, no `schedule` list, an optional section (`open-spaces`, `posters`, `sprints`, `job-listings`; the 2025 feed has no posters, sprints or job listings) that is not a list, or no readable slot at all. So does a feed that nests too deep to read: `process()` catches `RecursionError` once, around the whole pipeline, because it isn't a `ValueError` and can come from the parser, from printing a bad record's value (which takes more stack than parsing it) or from walking a description's HTML, at a depth that depends on the stack (#891). A single bad record (a missing or mistyped field, a time without a UTC offset, an end before its start, a duplicate id) is skipped, recorded in `ConferenceData.skipped` as `schedule[5]: <problem>`, logged once at WARNING, and never blanks the schedule. Unknown fields are ignored.

**Decoding (P0-10, built).** Every id becomes a `str` (D-42); every time an aware datetime converted to the conference zone; each session's `day` is `timefmt.local_date(start)`. A lone surrogate in a record's string (JSON's escape `\ud800`, which `json.loads` keeps but strict UTF-8, and so Flet, cannot send) becomes U+FFFD; an emoji, a pair of escapes, decodes as one character and stays (#150), and so does a pair sent as CESU-8 bytes, which `json.loads` leaves as two code points. The `conference.content` blocks and their keys get the same replacement (#152). Slots and open spaces decode into plain records (`records.Slot`, `records.OpenSpace`) that the rules turn into sessions. Days are sorted by date; each day's `TimeGroup`s are keyed by their aware start (so every group has one, DATA-13) and sorted by it; within a group, sessions are ordered by location, then name. Only sessions with `in_timeline` are grouped. The sponsors (`conference.sponsors`, sponsor lists keyed by level) decode through `records.sponsor_levels()` into `ConferenceData.sponsor_levels`, which `process()` sorts by order once (DATA-22, D-261): a missing section gives no levels; a section that is not an object, a level that is not a list or a sponsor that cannot be read is a skipped record (`conference.sponsors['Visionary'][2]: …`), and a level left empty is not listed.

**Rules (`core/rules.py`; P0-11 and P0-12 built).** `process()` applies them between decoding and grouping, in Ionic's order: `drop_rule` per slot, `register_speakers`, `collapse` for poster and break slots, `slot_session` for the rest (titles cleaned by `core/names.py`, one regex table), `open_space_session`, `poster_details`, then `rooms`. Every record that does not become a session of its own is listed by rule in `ConferenceData.dropped` and counted in one INFO log line (D-123). Speakers are registered once by id, the first record winning: the posters' authors first, then the sessions' slots, in Ionic's order; pseudo-speakers stay text (D-125).

| # | Rule | Behaviour | Features |
|---|---|---|---|
| 1 | Poster speakers | become `Speaker(id=str(id))`, bio as Markdown | DATA-07, 15 |
| 2 | Open spaces | sessions with `id = str(conf_key + 9000)`, track `Open Space`, location `room_display` (else `room`), Markdown description, the site's `open-spaces/#OpenSpace-<k>` page, an absolute image; dropped as `unscheduled-open-space` without start, end or room (D-123) | DATA-05 |
| 3 | Non-sessions | drop `available-open-space*`, `open-space` duplicates, placeholders, a `plenary` whose cleaned name minus a trailing `(…)` matches `^posters?$` (case-insensitive; a duplicate of the collapsed Posters row), and slots with `kind == "blank"` or `name == "Slot"`. **Placeholder**: name equals kind, empty description, no contact or authors, and kind is **not** `poster` or `break` | DATA-04 |
| 4 | Collapse | key `kind-day-name` (+`-start` for non-lunch breaks); Fri–Sun breaks named exactly `Break` that start 12:00–13:59 (conference time) renamed `Lunch`; posters named `Posters`; `(Room)` suffix → room; `^Hall ` → the year's `hall_prefix` (`Expo ` in 2026, D-122); earliest start to latest end | DATA-06, SCHED-19 |
| 5 | Collapsed ids | Ionic's `{kind}-{room}-{start}` (e.g. `break--2026-05-13T12:30:00-07:00`), not the collapse key; the start in ISO 8601 at the conference's offset (D-123) | DATA-06, 26 |
| 6 | Kinds | `sponsor-workshop` → `Sponsor Presentation`; `track` = capitalised kind | DATA-08, 14 |
| 7 | Names | Markdown link → text, tags stripped keeping their text (D-114, D-125), `html.unescape`; plenary, keynote, lightning-talks and event only: `(X)` → location, `^Hall ` → `hall_prefix`, strip `^<kind>\s*[—:\-–]\s*`; lightning talks display the year's `lightning_talks_location` (D-124) | DATA-08 |
| 8 | Pre-registration | `, pre-registration` phrase (cut from the name), tutorials, summits except Typing | DATA-09 |
| 9 | Spanish | `kind == "charla"` or `en espa[nñ]ol`, case-insensitive; suffix stripped | DATA-10 |
| 10 | Job Fair | `display_start = start - 30 min` from `display_time_overrides` (each `match` anchored at both ends and case-insensitive, as in Ionic, so the events-track "Job Fair & Community Showcase & Poster Sessions" row does not shift); grouping uses the canonical start (10:00 group, labelled 9:30) | DATA-11 |
| 11 | Speakers | linked by name, each person once; all authors kept as text in `speaker_names`; pseudo-speakers (`^hosted by\b`) are plain text, not directory entries (D-125); poster details link their authors by id | DATA-15 |
| 12 | Time groups | every group has an aware `start`; sorted by `(start, label)`; day = conference-local date | DATA-12, 13 |
| 13 | Poster details | `poster-detail-<conf_key>` sessions inherit the first Posters row's time and place; none without a Posters row (D-123); `in_timeline=False`. 2025's posters are nested in its poster slot and decode as posters (D-121) | DATA-07 |
| 14 | Rooms | split `location` on `,`, one name per `slugify_room` slug (`core/slugs.py`); multi-room fan-out into `ConferenceData.rooms` (by slug, natural order of name, each room's sessions by start then name, D-125); `display_location` = override, first room, else location; a generic `Break` shows no location | DATA-16, ROOM-06 |
| 15 | Sprint rooms | seeded from `map.toml` pins with `sprint = true` (`FeedSettings.sprint_rooms`) by `rooms.seed_sprint_rooms()`, the last step: empty, keyed by `slugify_room`, so a room the feed has keeps its sessions; rooms natural-sorted. In `core/rooms.py`, not `rules.py`, which is past 400 lines (D-66; #392) | MAP-08 |
| 16 | Markup | HTML → Markdown once per feed version, last, after the rules above (§7.7, D-130, D-140; built by #134): `description_md`, `bio_md`, `content_md` beside the raw HTML, and `Session.search_text` from `to_text`; open-space Markdown passed through with its links as written, its search text without link destinations or markers; sponsor text kept plain | DATA-23..25 |
| 17 | `slot.sessions` | a poster slot's are posters (D-121); any other kind's are logged and ignored | DATA-27 (drop) |

**Invariants** (D-77, in `tools/feed_invariants.py`: tested on the 2025 and 2026 fixtures by `tests/test_feed_invariants.py`, and run weekly on the live feed by `tools/check_feed.py`; testing-and-quality.md §3.3): no session lost beyond the documented drops and collapses; ids stable across runs; no placeholder survives; Job Fair grouped at 10:00, labelled 9:30; one Posters row, per-day Lunch rows and a break row when the feed has breaks; every speaker with sessions linked; every group has a start; `start <= end`; all datetimes aware; rooms and slugs consistent; sponsor slugs unique and each its name's; sponsor levels sorted and never empty (D-261); the sponsor and job-listing invariants live in `tools/sponsor_invariants.py` (#492). The reviewed outline is `tools/feed_outline.py`'s `outline()`. `process()` logs `Feed processed in N ms` at INFO (D-109). A reviewed snapshot of the processed model and the one-off Ionic outputs (`tests/fixtures/ionic/<year>/`, no Node in CI, compared in `tests/test_ionic_reference.py`) settle ambiguous rules; intended differences are listed by feature id or D-number.

### 7.4 Models (`core/models.py`)

Built in P0-10..P0-12: `Speaker` (`id`, `name`, `photo_url`, `bio`), `Session` (`id`, `name`, `kind`, `track`, `location`, `display_location`, `rooms`, `description`, aware `start`/`display_start`/`end`, `day`, `speaker_ids`, `speaker_names`, `pre_registered`, `spanish`, `url`, `image_url`, `in_timeline`), `Room` (`slug`, `name`, `session_ids`), `TimeGroup` (`start`, `session_ids`), `Day` (`date`, `groups`), `Poster`, `Sprint`, `JobListing` and `ConferenceData` (`sessions` and `speakers` by id, `days`, `rooms` by slug, `posters`, `sprints`, `job_listings`, `dropped`, `skipped`), all `@dataclass(frozen=True, eq=False)`. #134 added the converted markup (D-140): `Session.description_md` and `search_text`, `Speaker.bio_md`, `description_md` on `Poster`, `Sprint` and `JobListing`, and `ConferenceData.content` (the raw `conference.content` blocks) with `content_md`. #106 gave `Sprint` its `description_text` (`to_text`) and a folded `search_text` (name, submitter and that text; D-202). #373 added `Sponsor` (`name`, `slug`, `level`, `level_order`, `logo_url`, plain `description`, `booth` and `job_fair_table` as text or None, `mobile_banner`, `external_url` or None) and `SponsorLevel` (`name`, `order`, `sponsors`), with `ConferenceData.sponsor_levels` sorted by order (D-261). #394 added `Role` (`title`, `url`; frozen, with value equality) and gave `JobListing` its `roles` and a folded `search_text` (D-278). The rules add the rest of the target shape:

`Session` (`id: str`, name, track, kind, flags, `location`, `display_location`, `rooms`, `description_md`, `search_text` = folded title + description text + speaker names, speaker ids and names, aware `start`/`end`/`display_start`, `day`, URLs, `in_timeline`), `Speaker`, `Room`, `TimeGroup`, and `ConferenceData` (frozen, `eq=False`: `sessions: dict[str, Session]`, speakers, rooms, days, sponsors by level, sprints, job listings, `content_md`, `skipped`). Objects refer to each other by id only; queries return fresh view models and never mutate the model (Ionic wrote `hide` flags onto shared objects, SCHED-17).

### 7.5 Queries (`core/queries.py`, `timeline.py`, `agenda.py`, `search.py`)

One module per family (D-185): `queries.py` holds `days()`, `fold()` and `speaker_order()`; `timeline.py` the schedule queries, the one `Slot`, `DaySessions` and `schedule_order`; `agenda.py` Now & Next and My schedule; `search.py` the index and the matching; `rooms.py` the Map's rooms list (D-188); `speakers.py` the Speakers list (D-189); `sprints.py` the Sprints page (D-202); `sponsors.py` a sponsor by its slug (D-261); `jobs.py` a job listing's roles and a sponsor's listings (D-278); `expo.py` the expo's booths and the job fair's tables (D-254). Every query that returns sessions returns the model's own `Session` objects, which compare by identity, never ids.

| Query | Rule | Features |
|---|---|---|
| `session_view(session, zone, use_24h=...)`, `session_views(data, ids, zone, use_24h=...)` | a row's frozen `SessionView`: the displayed start to the end in conference time ("9:25–10:10 AM", and "9:25 to 10:10 AM" for screen readers), the display location, the authors' names; built once per feed version (D-153, D-184); `by_day(views, zone)` groups them by conference-local day, and `by_slot(views)` one day's into time slots by their time group's start (room detail and the open spaces, D-205). In `core/row_views.py`, beside this module. Built in P1 (#81) | SCHED-03 |
| `days(data, first_day, last_day)` | every date from the conference's first day to its last (sprint days included), widened to any schedule day outside them; an immutable tuple, so a day index never moves (D-126); ignores filters. Built in P0 | DATA-17 |
| `timeline(data, day, excluded)` | a tuple of `Slot(start, sessions)`, one per time slot; its `key`, derived from the start (D-185), is `"slot-<iso>"`, the slot item's `ScrollKey`; rows in `schedule_order`: shown start as an instant (#535), then shown room in natural order (D-31), then name and id, rows without a place first; a track passes unless excluded, and a slot the filter empties is left out. The only query that takes `excluded`, called only by the Schedule (a test checks both). Memoised (below). Built in P1 (#85, D-178) | DATA-18, DATA-30, SCHED-02 |
| `day_slots(data, day)` | a day's slots, unfiltered and memoised: what `now_next` reads, and what `timeline` filters (D-185) | SCHED-25 |
| `search(index, query, scope)` | in `core/search.py` (below): folded, **all** words must match, each anywhere in the text (D-46); grouped by type, sessions by day (`DaySessions`) in `(day, schedule_order)`, as the track pages (D-185); ignores filters (D-180). Built in P1 | NEW-02, DATA-18, DATA-19, SPKR-02 |
| `now_next(data, now)` | a frozen `NowNext`: the `Phase` (`before`, `before_day`, `day`, `after_day`, `after`; a day runs from its first start to its last end, and between days the conference-local date tells the evening from the morning), `happening` = `start <= now < end` over the timeline (`data.days`), and `up_next`, the first time slot after `now` on any day: the Schedule's own unfiltered `Slot` (D-185), or None (its `key` has an item only while the filter keeps the slot on the shown day; else scroll to `now_place()`'s target over that day's filtered slots, D-155, D-204); sessions, each slot in `schedule_order`, ignores filters (D-179) | SCHED-25 |
| `next_for_me(data, favorites, now)` | the `Session`: the first saved session that starts within 3 h (`NEXT_SESSION_WINDOW`), else the saved session that is on and started last, else None (D-179) | SCHED-25 |
| `elapsed_percent(session, now)` | how much of a session has passed, in whole percent from the start its row shows (`display_start`) to its end, rounded down: 0 before it, 100 from its end; Now's elapsed bars (D-190) | SCHED-25 |
| `my_schedule(data, favorites)` | a frozen `Agenda`: saved sessions by day and slot (`AgendaDay(day, slots)` of `Slot`s, D-185), each slot in `schedule_order`, plus `overlaps: Mapping[Session, tuple[Session, ...]]` from one sorted sweep; back-to-back sessions, and sessions with the same location, start and end (posters), don't overlap (D-179) | NEW-01 |
| `fold_ended(agenda, now, zone)` | a frozen `FoldedAgenda(earlier_days, earlier_today, ahead, overlaps)`: the days before the conference-local today whole, today's sessions with `end <= now` by slot, what is still to come, and its clashes with sessions that have not ended; equal from minute to minute until a session ends (D-191) | NEW-01 |
| `now_place(slots, now)` | in `core/timeline.py`, over the shown slots (`timeline(data, day, excluded)`, so the target always has an item to scroll to, D-155, D-178): a frozen `NowPlace` with `line`, how many slots have started (the now line goes before `slots[line]`), and `on`, the key of the last of them while one of its sessions has not ended, else None; `target` is `on`, else `NOW_KEY`, the now line's `ScrollKey` (D-204). Built in P1 (#86 as `current_slot_key()`, #89) | SCHED-16 |
| `directory(data)`, `letter_groups(entries)`, `filter_directory(entries, index, query)` | in `core/speakers.py` (D-189): one frozen `SpeakerEntry(speaker, letter, first_session, more)` per directory speaker, by `speaker_order` (folded displayed name, then id; D-46, D-180), its letter the folded name's first character, its first session the earliest in the Schedule's order with the day first; `LetterGroup`s by letter; the filter keeps the entries whose name holds every word, through `search(index, query, "speakers")`, and a blank one returns the entries themselves. Built in P1 (#98) | SPKR-01, SPKR-02, DATA-21 |
| `speaker_sessions(data, speaker_id)`, `has_bio(speaker)` | in `core/speakers.py`: a speaker's sessions as `DaySessions`, every session that links them (poster details included), in the order `directory()` takes the first session from (the day first, then `schedule_order`), so the list and the page agree; their rows come from `use_session_views(..., of_speaker=speaker.name)`, whose speakers line names only the co-speakers; `has_bio()` is False for the feed's placeholder "-", so the page shows no "About". Built in P1 (#99, D-203) | SPKR-03 |
| `track_sessions(data, track)` | a tuple of `DaySessions(day, sessions)`, each day in `schedule_order`; the Posters track lists its poster details instead of the Posters row (the row itself until the feed publishes posters); ignores filters. Memoised (below). Built in P1 (#85, D-178) | DATA-20, SCHED-22 |
| `posters(data, session)` | in `core/timeline.py`: the posters a Posters row stands for, its poster details (the sessions outside the timeline at its start and location), in `schedule_order` as the Posters track lists them; `()` for any other session and before the feed publishes posters. Memoised per feed and row. Built in P1 (#92, D-206) | SESS-09 |
| `room_list(data, now, other_locations, floors=())` | in `core/rooms.py`: a frozen `RoomList(floors, other_locations)`: `Floor(title, rooms)`s of `RoomEntry(room, on_now)`, one per plan with rooms in `MapData.floors()`'s order (a room on its pin's plan), the rooms on no plan last as "Other rooms" ("Rooms" without plans; #392), each group in the model's natural order; `other_locations` are `content.toml`'s names, matched by room slug; `on_now` holds the sessions on in the room by `now_next`'s rule (timeline only, `start <= now < end`; a multi-room session in each room), the one that started last first. Built in P1 (#100, D-188) | ROOM-01 |
| `room_now(data, slug, now)` | in `core/rooms.py`: the sessions on in one room at `now`, the same ones in the same order as its `RoomEntry.on_now` (room detail's "Now in this room"); the room's list itself is `Room.session_ids` (by start, then name; poster details included) through `use_session_views(..., in_room=slug)`, grouped by `row_views.by_day()`. Built in P1 (#101, D-194) | ROOM-02 |
| `projects(data)`, `filter_projects(listed, query)`, `cut_short(sprint)` | in `core/sprints.py` (D-202): the sprint projects by folded name, then id; a filter keeps those whose `search_text` (folded name, submitter and description text, never markup) holds every word, and returns `listed` itself for a filter with no word; a card cuts a description at four lines with "More" when it is over `PREVIEW_CHARS` (160) or its Markdown has a line break or a link. Built in P1 (#106) | EVT-05, EVT-06 |
| `sponsor_by_slug(data, slug)` | in `core/sponsors.py`: the sponsor whose `slug` is `slug`, scanning `data.sponsor_levels` (already in level order), or None; on a collision the first wins, as in Ionic. Built in P2 (#373, D-261) | SPON-02, SPON-03 |
| `parse_roles(html, site_url)`, `listings_of(data, sponsor)` | in `core/jobs.py` (D-278): a listing's roles in its order, each a `Role(title, url)`: every `<a href>`, titled by its text, and every `p` or `li` without an anchor that holds one bare `http(s)` URL, titled by the text before it, else by the URL's last segment ("Careers"); a listing with a heading is long form and has none; links by `core/links.py`'s `feed_link()`, `http(s)` only. `feed.process()` fills `JobListing.roles` and `search_text` (the sponsor, the titles and the text, folded) once; a placeholder (`N/A`) has no roles and no Markdown. `listings_of` matches `sponsor_name` to the sponsor's name exactly. Built in P2 (#394) | SPON-05, SPON-09 |
| `jobs(query)` | all words over `JobListing.search_text`: the sponsor, role titles and text (never raw HTML) | SPON-07 |

**Memo (D-178).** The schedule queries keep their results per processed feed, in a `WeakKeyDictionary` keyed by the `ConferenceData` (one object per `Conference.version`, so a replaced feed's results go with it), then by day and the excluded set (order-free). The same arguments return the same objects; a slot the filter leaves alone is the same object filtered or not, and a filter that hides nothing on a day returns the whole day's tuple. That is what lets the Schedule's memoised day lists and slot items skip their bodies (D-153, F34); `Slot` and `DaySessions` are also frozen values, so equal ones compare equal, and their sessions are the model's own objects, compared by identity. A screen still wraps the call in `use_memo` on `conference.version` (§6.4); the query's memo keeps the objects stable across a filter change and a remount.

```python
# src/pycon_us/core/queries.py (excerpt)
def fold(text: str) -> str:
    """Case, accents and typography folded: 'Cristián' → 'cristian', 'don’t' → 'dont'."""
    folded = unicodedata.normalize("NFKD", text.replace("´", "")).casefold()  # ´ as apostrophe
    folded = unicodedata.normalize("NFKD", folded).translate(_FOLD_TABLE)  # ' ’ go; “ —, ł, æ
    return _NON_ASCII.sub(_without_marks, folded)  # marks and format characters go (D-180)
```

**Search (`core/search.py`; D-46, D-180).** `search_index(data, spots, booths)` pairs each session's `search_text`, each directory speaker's folded name, each room's folded name, each venue spot's folded label and sublabel (D-351), each exhibitor at its booth as "booth", the number and the name (`core.expo.booth_entries()`: the List's rows and the sponsors off the plan, #406) and each sponsor's folded name and level (#397) with what it finds, already in result order (sessions by day in the Schedule's order: shown start, then place in natural order, name and id, D-31; speakers by `queries.speaker_order`; rooms in natural order; spots in `map.toml`'s order; booths by number in natural order; sponsors by level, then feed order), and logs `Search index built in N ms`. It is built once per feed version (`use_memo` on `Conference.version` in #97's `Search`), never per keystroke. `search(index, query, scope)` folds the query, keeps the entries that hold every word as a substring, and returns a frozen `SearchResults(sessions: tuple[DaySessions, ...], speakers, rooms, spots, booths, sponsors)`; an empty or blank query finds nothing, and `scope` is one of `SCOPES` (`all`, `sessions`, `speakers`, `places`, `sponsors`).

```python
# src/pycon_us/core/search.py (excerpt)
def search(index: SearchIndex, query: str, scope: str = "all") -> SearchResults:
    words = fold(query).split()
    ...  # per type in scope: [item for text, item in entries if all(w in text for w in words)]
```

### 7.6 Time (`clock.py`, `core/timefmt.py`; D-35, D-43)

```python
# src/pycon_us/clock.py (excerpt)
"""The one source of "now" (D-43, DATA-12)."""
_test_now: datetime | None = None
_fake_offset: timedelta | None = None


def now() -> datetime:
    """Return the current instant as an aware UTC datetime."""
    if _test_now is not None:
        return _test_now
    real = datetime.now(UTC)
    return real if _fake_offset is None else real + _fake_offset


def start_fake_clock(at: datetime | None) -> None:
    """Make now() run forward from `at` (Developer screen); None returns to real time."""
    global _fake_offset
    _fake_offset = None if at is None else _aware(at) - datetime.now(UTC)
```

`set_test_now(at)` sets the override; both setters refuse naive datetimes. The conference zone and its display name come from `conference.toml` (`time_zone`, `time_zone_name`; `ZoneInfo` with the `tzdata` wheel, which S1 checked on devices). `core` functions take `now` and the zone as parameters; only screens and stores call `clock.now()`. `core/timefmt.py` holds:

| Function | Result |
|---|---|
| `instant(moment)` | the moment in UTC: every comparison, subtraction, sort key and grouping key of session or reminder times goes through it (the Schedule's time groups, `schedule_order`, slots, the change log's diff), since two datetimes in one `ZoneInfo` compare and hash by wall clock and ignore `fold`, which is wrong on the night summer time ends (#535); a group or slot still keeps its start in the conference zone |
| `local_date(moment, zone)`, `today(now, zone)` | the conference-local date: the day bucket, and the one "today" |
| `time_label(moment, zone, use_24h=...)` | `9:25 AM`, or `09:25` when `page.media.always_use_24_hour_format` is set (F23) |
| `time_range_label(start, end, zone, use_24h=...)` | `9:25–10:10 AM`, `11:30 AM–12:15 PM`, one time when start equals end |
| `day_label(day)`, `day_heading(day)` | `Fri, May 15`, `Friday, May 15` |
| `zone_note(now, zone, zone_name, device_offset)` | `Times are Pacific Time (PDT)` when the device's offset at `now` differs, else None; the UI passes `now.astimezone().utcoffset()` |
| `time_status(start, end, now, zone)` | a `TimeStatus(label, spoken, happening)`: `Starts in 25 min` / `Starts in 25 minutes` on the session's own day, `Happening now` for `start <= now < end`, `Ended` from the end; None on an earlier day, and for a notice from its time on (D-186) |

Weekday and month names come from fixed tuples, never locale `strftime`, and naive datetimes raise `ValueError`. Tests run under `TZ=America/Los_Angeles` and `Pacific/Kiritimati` (the `machine_tz` fixture), and cover both DST changes and midnight.

### 7.7 HTML → Markdown (`core/html_md.py`; D-44)

Stdlib `html.parser`, once per feed version inside `feed.process()` (D-130), into a small tree that is then rendered; S3 settled the details (D-114, D-115; `docs/spikes/03-html-markdown.md`, whose `html_md_proto.py` was the reference) and #67 the boundaries (D-131). Two public functions: `to_markdown(value, site_url) -> str` and `to_text(value) -> str`. The HTML side (the tree, blocks and lists, the walk over inline elements) is `html_md.py`; the Markdown inline layer (escaping, emphasis tokens and their flanking check, links, code spans, paragraphs) is `core/markdown_inline.py`, which only `html_md.py` imports (D-201).
- **Tags** (the 2025 and 2026 census): `p` → paragraph; `br` → `"  \n"`; `hr` → `---`; `h1`–`h6` → `#`–`######`; `ul`/`ol`/`li` → `- `/`N. `, continuation lines indented by the marker's width (three spaces under `1. `); `blockquote` → `> `; `strong`/`b`, `em`/`i`, `s`/`del`/`strike` → `**x**`, `*x*`, `~~x~~` with edge whitespace kept outside; `code` → a code span fenced with one backtick more than the longest run inside; `a` → `[text](url)`, the `href` joined to `site_url`, only `http`, `https` and `mailto` linked, the destination percent-encoded; bare `http(s)` URLs in text become explicit links; edge whitespace stays outside links and emphasis; emphasis that could not flank loses its markers.
- **Anything else is unwrapped** (its text stays in place); `script` and `style` are dropped. Whitespace collapses as in a browser; only `br` breaks a line.
- **A value with no tag is plain text:** entities decoded, blank lines make paragraphs, single newlines hard breaks (sprint descriptions).
- **Escaping** (D-115): in text, `` \ ` * _ [ ] ( < > | ~ $ & : `` and a block marker at the start of a line become numeric character references (`&#36;`), because `ft.Markdown` always enables LaTeX (F27) and GFM emoji; code spans stay raw.
- **A text-only form** (`to_text`, no markup) feeds search (D-46): the visible text, with blocks, list items and breaks as spaces so words never join; link targets, `script` and `style` left out; not yet folded.
- **Emphasis** is rendered as tokens and checked against CommonMark's flanking rules before it is joined into a paragraph; a pair that could not open or close loses its markers (D-114, D-131).

Rendered with `ft.Markdown(value, selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB, on_tap_link=..., md_style_sheet=...)`, with the one style sheet from `theme.py` whose text styles all name their colour (D-116, F28); one builder, `ui.links.feed_markdown()`, makes it for every screen, and a tapped link opens by `core/links.py`'s `feed_link()` (only `http`, `https` and `mailto`; a site path joined to the year's site URL; a scheme-less web address given `https://`) and the link rule, web pages in the in-app browser (SESS-06, D-197). Job roles are read from the same HTML by `core/jobs.py`'s own `html.parser` pass (§7.5, D-278), not from the Markdown; Venue & hours sections (MAP-09) arrive with their screen in P2.

### 7.8 Names and slugs (`core/slugs.py`)

Track display names (`short`, `plural`, `long`) and clean URL slugs (`ai`, `lightning-talks`; not Ionic's `ais`) come from the `[[tracks]]` table of `conference.toml`, with a humanised fallback (DATA-28, DATA-29). Three normalisers are copied exactly from Ionic because data keys depend on them: `slugify_room` (lower-case, `[^a-z0-9]+` → `-`, strip `-`), `normalize_room_key` (drop `room\s+`, keep `[a-z0-9]`; keys the pins) and `sponsor_slug` (lower-case, `\s+` → `-`, drop `[^a-z0-9-]`; JavaScript's `\s` spelled out, nothing trimmed, so `Qube Research & Technologies` is `qube-research--technologies`; built in #373, D-261). Beside them, `semantics_key()` makes a semantics identifier's key the same way as `slugify_room` (decisions §M); it lives here, with no Flet, so the year-data loader can check that two PSF labels give two identifiers (D-283).

### 7.9 Change log (`core/diff.py`; D-47, NEW-04, P2)

`diff(old, new) -> list[Change]` compares sessions by id, skipping collapsed `break` and `poster` rows (their ids embed their start): `added`, `removed`, `time` (start or end), `room` (location) and `title`, each with old and new values. Batches are kept in `<data dir>/changes-<year>.json` (`[{"detected_at": ..., "changes": [...]}]`, trimmed to 14 days). The `ChangeLog` store (`change_log.py`, D-301) holds them and gives the last 24 h for the "Changed" badge (`recent()`, D-315), and session detail a badge per kind with the old value (`ChangeLog.recent_of()`, ux.md §5.5); a batch shows "Schedule updated · Review" (SnackBar) and a Now card; Schedule changes (the drill pair `changes/<year>`, D-255) lists saved sessions first. Wording: "Removed from the latest schedule", never "cancelled". A change also re-runs `reminder_plan.plan()`.

The rules (D-255):

- **What is diffed:** only a refresh that publishes (D-224), and only against a feed from the feed URL it fetched from: the cache or an earlier network feed. The bundled snapshot counts as the year's feed URL's, and over it a refresh is diffed only when sessions are saved, the batch holding only their changes (never an addition), and only until the install's first network publish for the year saves `pycon.<year>.fetched`; after it, a start that fell back to the snapshot (Clear cached feed, a cache that does not parse, a feed URL change) is not diffed, since the snapshot is not what the user last saw. After a feed URL change the next refresh publishes without a diff, in the session and after a relaunch. A refresh that writes nothing (a closed session, D-147; a URL left, D-244) records nothing.
- **The feed URL rule:** any change of the feed URL once the feed has loaded deletes the cache and `changes-<year>.json` (amends D-244); the start restores the stored URL before `load_local()` and deletes nothing. So the cache is always the feed of the URL in effect, and the log never mixes two feeds: the log's writes are kept in `Storage._writes` with the feed's, the deletion waits for them all, and `_record_changes` checks `discarded()` again just before it writes (D-255, as D-244 orders the cache). Reset app deletes the log too (D-198).
- **The route:** `changes` is a drill kind whose id is the year; every opener pushes it on its own View (`drill_href(view_path, "changes", str(YEAR))`), the SnackBar's Review on whatever View is on top, so Back returns to the opener (§5.2).
- **Who hears:** one SnackBar per batch that changes something, saved sessions first ("2 saved sessions changed", else "Schedule updated · 3 changes"); a batch of additions only is recorded silently; Now's card only for unseen changes to saved sessions from the last 24 h (seen 2 s after the list shows them, or by Mark all as seen); showing the list closes the Review SnackBar, and Review on the list only closes it; the Changed badge only for time, room and title changes, by detection time, for 24 h.
- **A removed session** is listed with its last title, time and room, kept in the batch, as no link (its id would open the not-found state, D-186), with its star.

**The log file (#430, built).** `core/change_batches.py` is pure: a frozen `Batch(detected_at, changes, seen)` (`changes` a tuple of `Change`, `seen` one mark per batch, `False` until the list has shown it, ux.md §6.4), `encode_batches()` and `decode_batches(raw, zone)`, and `trim(batches, now)`, which keeps the batches detected in the 14 days up to `now` (`KEPT_FOR`; exactly 14 days old is kept) in their order. The file is a JSON list, UTF-8: each batch `{"detected_at", "seen", "changes"}`, each change `{"id", "kind", "old", "new"}` and each side `{"title", "start", "end", "location"}` or `null` (an addition's old side, a removal's new one), times in ISO 8601 with their offset. Decoding reads every time back in the year's zone, so 2025's Eastern and 2026's Pacific rows show as before, and reads what it can: a batch with a field missing or of the wrong type, an unknown kind, a time without an offset or sides that do not match its kind is skipped and logged, the rest kept; bytes that are not a JSON list give no batches (logged). `services/changes_file.py` is the I/O, in a module of its own since `storage.py` was at 400 lines: `read_batches(storage, zone)` (no file or an unreadable one: no batches), `write_batches(storage, batches)` and `delete_batches(storage, reason)`, which return `False` on a failure (logged; a failed write keeps the old file, D-120). They go through `Storage.write_file()` and `Storage.delete_file()`, which `write_feed()` and `delete_feed()` now call too: every write of either file is a task in `Storage._writes`, and every deletion waits for all of them, so the log keeps the cache's order (D-244). `Conference.set_feed_url()` deletes both files on any change once the feed has loaded (`data` set; the start's restore runs before `load_local()`), and `reset_app()` deletes the log after `Conference.reset()` has cancelled a running refresh, listing "Schedule changes" among what is lost (D-198). The caller trims before it writes; `ChangeLog.record()` writes each batch (#431, below).

**The store and the hand-off (#431, built; D-301).** `change_log.py`'s `ChangeLog`, with `ChangeLogCtx` and `use_change_log()`, is a store of its own, so `state.py` stays the feed's (D-231) and a batch re-renders only what reads the log. `App` builds `ChangeLog(_favorites=favorites)` and `Conference(_change_log=change_log)`; `bootstrap()` awaits `change_log.load(storage, zone)` after the favourites, which reads the file (trimmed to 14 days, newest first) and the `pycon.<year>.fetched` marker. After a refresh publishes a new feed, `Conference._refresh` awaits `record(storage, before, after, current)`: `before` and `after` are `Published(data, source, url)`, where `url` is the feed URL the feed counts as (`Conference._shown_url`: the URL in effect when the cache loaded, the year's for the snapshot, the one fetched for a refresh), and `current` is the refresh's `discarded()` check negated. `record()` saves the marker on the year's first network publish; diffs with the marker as it was, by D-255's rules (a feed from another URL is not diffed; over the snapshot, only before the marker, only when sessions are saved, and only their changes without additions); logs the diff's time and count; and, after its last await, calls `current()`: a URL left or a session closed by then records nothing, though the feed is published. Otherwise the batch goes first in `batches`, whose one assignment is the store's one notification per batch, after the batch to announce is set (none for additions only; `take_announcement()` hands it out once), and the file is written. `recent(now)` maps each session id to the kinds of its time, room and title changes detected less than 24 h before `now` (`RECENT_FOR`; D-315). `Conference.set_feed_url()` calls `ChangeLog.delete()` (memory and file), and `Conference.reset()` calls `ChangeLog.reset()`, which clears the marker in memory as `Storage.clear_prefs()` does on the device (Reset app). The same bytes, a failed refresh and a closed session record nothing. `tests/test_change_log.py` and `tests/test_change_log_snapshot.py` run each rule through a real refresh over `httpx.MockTransport`.

**The words (#432, built).** `core/change_views.py` is pure and says a change one way for the list, the badge, the SnackBar and Now's card. `change_view(change, zone, *, use_24h)` returns a frozen `ChangeView` (identity equality, D-70 rule 6): `old` and `new` for the line "old → new", and `sentence` for a screen reader, which starts with the newest title. A room change names both rooms ("No room" for an empty side); a time change on one conference day shows the two ranges, "10:30–11:00 AM" → "11:30 AM–12:15 PM", and one to another day puts the day before each ("Sat, May 16, 10:30–11:00 AM"); a rename is listed under the new title, "renamed from “…”"; an addition's `new` and a removal's `old` are its day, time and room ("Sat, May 16, 10:30–11:00 AM · Room 104A"), and a removal's `new` is empty, its item saying `REMOVED_NOTE`. Spoken ranges say "to" for the dash and spoken days are in full: "Python for Humans: time changed. Was 10:30 to 11:00 AM, now 11:30 AM to 12:15 PM." `item_phrase(view, saved=...)` adds "In My schedule.". `sections(batches, saved, zone, now, *, use_24h)` gives "Affects My schedule" then "All changes", each change once (a saved session's under the first, the rest under the second), a section without changes left out, its groups one per batch, newest first, headed by `detected_label()` ("Today, 10:42 AM", "Yesterday, 4:15 PM", "Thu, May 14, 4:15 PM"). `changed_phrase(kinds)` is the Changed badge's spoken part ("Room changed", "Time and room changed"; empty for an addition or a removal). `snackbar_text(changes, saved)` and `now_card_text(batches, saved, now)` count as D-255 says: saved sessions once each, else changes, never additions; the card only unseen batches of the last 24 h (`RECENT`). Times are conference time (D-35) in 24-hour form when the device asks (F23); no string says "cancel" (D-47).

**The badge (#433, built; D-315).** A list owner calls `use_recent_changes()` (`ui/session_rows.py`), which subscribes to `ChangeLog` and returns `recent(clock.now())`; it hands each memoised list, day, slot or `DayGroup` only its sessions' marks (`changes_of()`), and each `SessionRow` its own `frozenset` (`changed=`), so a batch re-renders only the lists and rows it touches (§6.4). The row adds "Changed", outlined in `Tokens.changed` (`warning`), after its other badges, and its phrase says `changed_phrase()` in the label's place. A mark ends 24 h after its batch's detection: the hook checks on the strip's 60 s loop and re-renders its owner only when a mark ended, so the badge goes within a minute of its end while the list shows, and at once on a resume or the list's next mount.

**The diff (#378, built).** `core/diff.py` is pure (D-68; `tests/test_core_is_pure.py`). A `Change(id, kind, old, new)` holds the session's `Listing` (`title`, `start`, `end`, `location`) from each feed: `old` is None for an addition and `new` for a removal, so a removal keeps the last title, time and room that its item shows (D-255), and `Change.title` is the newest title. `ChangeKind` is a `StrEnum`: `added`, `removed`, `time`, `room`, `title`. A session in both feeds gives one change per kind that differs (a talk retimed and moved gives two); the title compared is the cleaned name (`Session.name`), so markup the parser strips changes nothing. The start compared and kept is the one rows show (`display_start`): it moves with `start`, and the Job Fair's is 30 minutes earlier (DATA-11). The sessions skipped are those of `rules.COLLAPSED_KINDS`: the collapsed `break` and `poster` rows, and the poster details too, which copy their Posters row's time and place and have no row of their own (DATA-07), so a moved Posters row would otherwise read as 25 changes, and a missing one as 25 removals. Changes come by the new start (a removal's old start), then id, then kind in `ChangeKind`'s order; ids compare as text, not numbers ("1142" < "142" < "51"). `tests/test_diff.py` builds each pair from a recorded feed with the named edits of `tests/feeds.py` (`pair()`, with `move()`, `retime()`, `rename()`, `add()` and `remove()`), and a hypothesis property checks that swapping the sides swaps additions and removals and every other change's values. On the owner's Mac (M4, Python 3.14) a diff of either recorded feed against a retimed copy takes about 0.35 ms.

---

## 8. Per-year bundled content (D-45)

| File | Holds | Replaces |
|---|---|---|
| `conference.toml` | name, dates, zone, venue, URLs (the feed, registration, the sprints' page and project form), snapshot time, tracks | `/2026/` literals |
| `content.toml` | links, Wi-Fi, safety contacts, keynotes, event reminders, venue hours, overrides, sponsor credits | hard-coded copy; `'temporal'`/`'google'` matching |
| `map.toml` | floor plans, pins, booths, sprint rooms | `ROOM_LOCATIONS`, booth tables |
| `conference.json` | the feed snapshot (NEW-03) | the first-launch spinner |

`config.YEAR = 2026` until the 2027 feed exists; rolling over = add `data/2027/` and its maps, then set `YEAR`: `src/pycon_us/data/README.md` has the steps, what a new year must supply and what an update does to an install (#842). A content fix needs a new build (accepted); no remote config.

### 8.1 Schemas, by example (values illustrative)

```toml
# data/2026/conference.toml
year = 2026
name = "PyCon US 2026"
time_zone = "America/Los_Angeles"
first_day = 2026-05-13
last_talk_day = 2026-05-17
last_day = 2026-05-19
venue = "Long Beach Convention Center"
city = "Long Beach, CA"
address = "300 E Ocean Blvd, Long Beach, CA 90802"   # optional: Venue & hours shows and copies it (D-313)
site_url = "https://us.pycon.org/2026/"
feed_url = "https://us.pycon.org/2026/schedule/conference.json"
presentation_url = "https://us.pycon.org/2026/schedule/presentation/{id}/"   # P1 (NEW-06)
snapshot_captured_at = 2026-10-11T09:00:00-07:00     # written by tools/update_snapshot.py; only the active year (D-135)

[directions]                # optional: where Venue & hours' Directions opens a maps app (D-313)
label = "Long Beach Convention Center (Pine Ave Entrance)"
latitude = 33.764444        # floats, checked to lie on the globe
longitude = -118.191722

[[tracks]]
key = "Ai"                  # as produced by feed processing: the kind, first letter upper-cased
short = "AI"
plural = "Future of AI with Python"
long = "The Future of AI with Python"
icon = "MEMORY_OUTLINED"    # an outlined ft.Icons name (D-27); colours stay in the theme tokens (D-24, D-25)
group = "talks"             # filter-sheet group: talks | hands-on | community | logistics
slug = "ai"                 # its page, /more/tracks/ai: written out, never derived (DATA-29, D-199)
legend = "A dedicated track on AI: machine learning, LLMs and more"   # the hub's legend line (EVT-04)
new = true                  # optional: the "New track" badge (SCHED-21)
```

Every field without a phase note exists today (P0-08); the others arrive with their features. An unknown track key falls back to its humanised form (`Hallway-track` → "Hallway track"), so a new kind in next year's feed still reads well.

```toml
# data/2026/content.toml
[links]                             # P2 (INFO-03): the app's own links
report_app_issue = "https://github.com/OWNER/pycon-us/issues"

[open_spaces]                       # optional: the Open spaces page (EVT-01, EVT-02; D-205)
intro = "Open spaces are hour-long sessions that attendees organize during the conference, ..."
propose_url = "https://us.pycon.org/2027/signup/open-space/"   # optional: "Propose an open space"; 2026 has none (#824)

[lightning_talks]                   # optional: the Lightning talks page (EVT-03; D-205)
heading = "What's a lightning talk?"
intro = ["Five minutes at most, ...", "..."]   # the copy card's paragraphs
signup_url = "https://us.pycon.org/2027/signup/lightning-talk/"   # optional: "Sign up for a lightning talk"; 2026 has none (#824)
info_url = "https://us.pycon.org/2026/events/lightning-talks/"

[[lightning_talks.doubts]]          # "Think you can't do one?", in order
doubt = "“Everyone already knows that”"
answer = "They don't, and those who think they do still learn from the way you explain it."

[wifi]                              # optional: the Wi-Fi page (INFO-08; D-280), no blank value
network = "PyCon2026"
password = "illustrative"
sponsor = "example-sponsor"         # P2 (#417): sponsor_slug() of the credited sponsor (INFO-09)

[psf]                               # optional: About the PSF (INFO-06; D-283)
mission = "The mission of the Python Software Foundation is to promote, ..."
donate_url = "https://www.python.org/psf/donations/"   # https only, like every link below

[[psf.links]]                       # the page's rows, in order within their section
section = "follow"                  # get_involved | python_resources | follow
label = "Mastodon"                  # unique on the page: the row's identifier, psf.link.mastodon
url = "https://fosstodon.org/@ThePSF"
brand = "mastodon"                  # optional: a ui/brands.py mark; or icon = "LANGUAGE" (an ft.Icons name), not both
app = true                          # optional: a profile opens in its own app (INFO-14)

[[safety_contacts]]                 # Help & safety's Report a concern card (D-281)
label = "Email the Code of Conduct team"   # what a tap does
kind = "mailto"                     # tel | mailto | https, at most one of each
value = "pycon-us-report@python.org"   # tel: E.164, "+15625550100"
source = "https://policies.python.org/us.pycon.org/code-of-conduct/Procedures-for-Reporting-Incidents/"   # the public page that shows it
checked = 2026-10-20                # when it was last checked there (D-45)

[help]                              # Help & safety's other lines and links (D-281)
in_person = "If someone is in danger, contact local emergency services first: …"   # then staff in person
info_desk = "In the Promenade Lobby, at the main entrance."
lost_and_found = "Room 203AB. …"
quiet_room = "VIP Room A & B, Thursday to Sunday, …"
coc_summary = "PyCon US is for everyone. …"
coc_url = "https://policies.python.org/us.pycon.org/code-of-conduct/"
procedures_url = "https://policies.python.org/us.pycon.org/code-of-conduct/Procedures-for-Reporting-Incidents/"

[[keynotes]]                        # one per session (D-217); also: title, abstract (Markdown)
session_id = "153"                  # the feed's id; the tests check it against the snapshot
kind = "keynote"                    # keynote | panel

[[keynotes.speakers]]               # also: photo_url (https), bio
name = "Lin Qiao"
role = "CEO and co-founder, Fireworks AI"

[[event_reminders]]                 # sign-ups only: the keynotes' moments are derived (D-274)
id = 8001                           # 8000-8049, unique; 8050-8099 are the derived ones
category = "lightning"              # lightning | open_space
at = 2026-05-15T10:00:00-07:00      # aware, in the conference year
title = "Lightning talk sign-ups"   # no clock time in the text: the pages give none
body = "Give a five-minute talk: sign up before lunch, when speakers are picked and told by email."
route = "/more/lightning-talks"     # what a tap opens
source = "https://us.pycon.org/2026/events/lightning-talks/"   # the public page
checked = 2026-10-20

hall_prefix = "Expo "                # "Hall AB" in a name is "Expo Hall AB" (D-122)
lightning_talks_location = "Pacific Ballroom - Arena"   # D-124
other_locations = ["Elsewhere", "Lobby", "Out Front of Hyatt Regency"]   # the Map's "Other locations" (D-188)

[[display_time_overrides]]          # also: [sponsor_credits]
match = '\s*job\s*fair\s*&\s*community\s*showcase\s*'   # regex, case-insensitive, fullmatch on the cleaned name
minutes = -30

[social]                            # optional: the Social media page (INFO-10; D-284)
hashtags = ["#PyConUS", "#PyConUS2026"]   # each a chip that copies it; "#" then letters, digits, _

[[social.links]]                    # in the page's order within each section
section = "pycon"                   # pycon | psf (a profile: opens in its app) | blogs (in-app browser)
label = "Mastodon"                  # the row's title
handle = "@pycon@fosstodon.org"     # its second line
url = "https://fosstodon.org/@pycon"   # https only
brand = "mastodon"                  # optional: a mark of ui/brands.py (D-264); none: a feed icon

[[venue_hours]]                     # D-282: core.hours.ServiceHours; hours_status() reads it
service = "Registration"            # unique; optional: location, pin (a map.toml key), note
location = "Promenade Lobby (Main Entrance)"
open = [                            # local times on conference days; closes after opens; no overlaps
    { date = 2026-05-13, opens = 07:30:00, closes = 18:00:00 },
]
```

```toml
# data/2026/map.toml (built in #372; a year without the file has no plans or pins)
tour_url = "https://map.concept3d.com/?id=1802"   # optional: the 3D tour, a link (MAP-03)

[[plans]]                           # in the Map's order (MAP-02)
id = "concourse"                    # unique: the route's plan/<id>
title = "Concourse level"
subtitle = "Tutorials, talk tracks, registration, expo entry"   # optional
image = "maps/2026/concourse.webp"  # under src/assets: tools/encode_plans.py, 2048 px, WebP 80 (D-312)
thumb = "maps/2026/concourse-thumb.webp"   # the same, fitted to 800 px: pins land on it too
width = 2048                        # the image's, as the script prints them
height = 1583

[[pins]]                            # rooms and venue spots in one table
key = "104c"                        # a room: normalize_room_key(feed name); a venue spot: "info-desk"
label = "Room 104C"
sublabel = "Education Summit / Charlas / Open spaces"   # optional
plan = "concourse"
x = 84.0                            # percent of the image, 0-100, a decimal point
y = 27.0
sprint = false                      # optional: the sprints use it (MAP-08)

[[plans]]
id = "job-fair"
title = "Job fair & community showcase"
image = "maps/2026/job-fair.webp"   # cropped to the floor, without the print's header (D-254)
thumb = "maps/2026/job-fair-thumb.webp"
width = 1700
height = 1438
note = "The printed plan shows some tables with other sponsors. This list follows the conference's sponsor data."   # optional (D-254)

[[booths]]
number = "613"
x = 0.412                           # ratios of the expo image; also y, w, h

[[booths]]
number = "407"
label = "Python Software Foundation"   # only for a booth the feed gives no exhibitor (D-254)
x = 0.621
```

**As built (#372).** `year_map.py` holds `Plan`, `Pin` and `MapData` (`plans`, `pins`, `tour_url`), with `plan(id)`, `pin(key)` and `room_pin(name)`, which finds a feed room's pin by `normalize_room_key()` (§7.8), so `Room 102A` and `102A` share one; `YearData.map` holds it, empty for a year without `map.toml` (2025). `check_map()` refuses a repeated plan id or pin key, a pin key that is not `a-z0-9` words joined by `-`, a blank title or label, a size that is not positive, an image or thumbnail missing under `src/assets/`, a pin on a plan that does not exist or outside 0–100 %, and a tour that is not `https`; errors read `2026/map.toml: pins[3].x: 120.0 is not between 0 and 100`. A venue spot's key has a `-` (`info-desk`), which no room key has, and `content.toml`'s `venue_hours` name their pins by it (`check_hours_pins()`). 2026 has Ionic's five plans (Campus, Concourse, Upper, Arena & exhibit halls, Seaside), its 53 room pins (`ROOM_LOCATIONS`, aliases such as `103abc` and `arena` included) and six venue spots (`VENUE_LOCATIONS`: information desk, registration, quiet room, lost & found, swag pickup, staff office), at Ionic's percentages; 16 rooms are marked for the sprints, those whose sublabel names them, as MAP-08 seeds them. `tools/encode_plans.py` makes the plans and thumbnails, and paints over the marks a plan carries (`--cover`: the campus plan's PyCon wordmark and the venue's logo, D-36). Tests (`tests/test_year_map.py`) check the images (WebP, 2048 px, the size in `map.toml`, within S7's budget), that every room of the snapshot and of the recorded feed has a pin or is under `other_locations` (naming any that is not), and that `normalize_room_key()` and `slugify_room()` agree on every feed room name of both years.

A booth lists every sponsor whose `booth_number` is its number, so a shared booth keeps all its exhibitors (2026: 726, 727, 728, 734); `label` names a booth without one, and a test over the bundled snapshot fails when a labelled booth also has an exhibitor (D-254). Job fair tables come from the feed (`job_fair_table_number`), not from `map.toml`; #464 adds their rectangles on the `job-fair` plan. **As built (#464).** `[[tables]]` holds a rectangle per printed table T1 to T20, measured once on the cropped plan (the white square and its record), as `year_map.Table(number, x, y, w, h)` in `MapData.tables`, with `MapData.table(number)`; `check_map()` gives them the booths' rules (`_check_areas()`: a `job-fair` plan to be on, unique numbers that are not blank, a rectangle inside the plan), and a test over the bundled snapshot and the recorded feed fails when a feed table has no rectangle. Who is at a table still comes from the feed. **As built (#407):** the `job-fair` plan is Ionic's `floor-plans/job-fair.jpg` cropped to the floor by `tools/encode_plans.py --crop` (1700 × 1438 px, kept at its size, since the script never scales up), with `Plan.note`, refused when blank; `core/expo.py`'s `job_fair_tables(data)` returns a `JobFairTable(table, sponsor, roles)` per sponsor with a table, tables in natural order (`room_sort_key`) and a shared table's sponsors by folded name, `roles` the count of its listings' roles, built once per feed version (D-153).

**As built (#401).** The `expo` plan is Ionic's `pycon-us-2026-floorplan-nologo.jpg` through `tools/encode_plans.py`, its sun-and-palms mark painted over (`--cover`, D-36). `[[booths]]` holds Ionic's 61 booth rectangles, turned once from pixels of its 9931 × 7021 reference into ratios, as `year_map.Booth(number, x, y, w, h, label="")` in `MapData.booths`. `check_map()` refuses booths without an `expo` plan, a blank or repeated number, a blank label, a ratio outside 0–1, a size that is not positive and a rectangle past the plan's edge (`x + w` or `y + h` over 1), naming the file, the entry and the field. `core/expo.py`'s pure `expo_booths(data, booths)` returns an `Expo`: each booth by number in natural order as an `ExpoBooth(booth, sponsors)` with every sponsor of its number in folded-name order, numbers compared as text, and `unplaced`, the sponsors whose booth has no rectangle; a year without booths has an empty `Expo`. It is built once per feed version (D-153; a `WeakKeyDictionary` on the feed, like `timeline.py`'s). `tests/test_expo.py` pins 2026's gaps over the snapshot and the recorded feed: sponsors at 139 and 336 without a rectangle, 407 and 606 without a sponsor.

### 8.2 Loader (`config.py`, `year_schema.py`, `year_tracks.py`, `year_pages.py`, `year_keynotes.py`, `year_moments.py`, `year_info.py`, `year_links.py`, `year_map.py`)

`tomllib` loads each file into frozen dataclasses (`Track`, `WifiInfo`, `SafetyContact`, `Keynote`, `EventReminder`, `Plan`, `Pin`, `Booth`, …) gathered in `YearData`. The loader is the schema:

```python
# src/pycon_us/config.py (excerpt)
class YearDataError(ValueError):
    """A year data file is invalid; the message names the file, the entry and the field."""


def checked(raw: dict, cls: type, where: str) -> dict:
    """Return `raw` if it has exactly the fields of dataclass `cls`, with matching simple types."""
    hints = typing.get_type_hints(cls)
    fields = {f.name: f for f in dataclasses.fields(cls)}
    if unknown := raw.keys() - fields.keys():
        raise YearDataError(f"{where}: unknown field(s) {sorted(unknown)}")
    required = {name for name, f in fields.items() if f.default is dataclasses.MISSING}
    if missing := required - raw.keys():
        raise YearDataError(f"{where}: missing field(s) {sorted(missing)}")
    for name, value in raw.items():
        expected = hints[name]
        if expected is float and isinstance(value, int):
            continue                                  # TOML writes 41 for 41.0
        if expected in (str, int, float, bool) and not isinstance(value, expected):
            raise YearDataError(f"{where}.{name}: expected {expected.__name__}, got {value!r}")
    return raw
```

As built (P0-08), one recursive `build(cls, raw, file)` in `year_schema.py` (with `read_table()` and `YearDataError`; split from `config.py` at D-66's ~400 lines in #102) applies this check to every table, builds a table of its own (`[lightning_talks]`, an optional `X | None` field) as its dataclass and turns arrays of tables into tuples of their dataclass (D-205); errors read `2026/conference.toml: tracks[8].group: 'workshops' is not one of (...)`. Entries are then checked by rule (a unit test loads every year): a valid zone; ordered dates; `https://` URLs; unique hand-written moment ids in 8000–8049, with aware times in the conference year, a known category, a route, a source and a check date (`check_moments()` in `year_moments.py`, D-274); pins 0–100 %, booths 0–1; referenced plans, pins and sponsor slugs exist (`check_map()` and `check_hours_pins()` in `year_map.py`, #372); keynote session ids and sponsor credits' slugs exist in the year's bundled snapshot (`load_year(check_sessions=True)`, which the tests and `tools/update_snapshot.py` use and the app's start does not, D-217; 2025, which bundles none, is checked against its recorded feed, D-274); safety contacts carry `source` and `checked`; every feed room has a pin or is under "Other locations". The Open spaces and Lightning talks pages' tables and their checks (`check_pages()`) are in `year_pages.py`, split from `config.py` at D-66's ~400 lines in #248 (D-205); the keynotes' (`Keynote`, `KeynoteSpeaker`, `check_keynotes()`, `check_keynote_sessions()`, `keynote_of()`) in `year_keynotes.py` (D-217); the track registry (`Track`, `TRACK_GROUPS`, `HUB_PAGES`, `KEYNOTE_TRACKS`) and its checks (`check_tracks()`, which `_check_conference()` calls last) in `year_tracks.py`, split from `config.py` at D-66's ~400 lines in #275 (D-228); the info pages' tables (Wi-Fi, Help & safety, Venue & hours, About, the PSF, Social), each a field of `Content` added with its page, and their checks, `check_info(content, conference, file)`, which `_check_content()` calls, in `year_info.py` (D-263; so far Wi-Fi's `WifiInfo`, whose `check_info()` rule refuses a blank network or password, D-280, Help & safety's `SafetyContact` and `HelpInfo`, whose contacts must name an `https` source and a checked date, a tel value in E.164 and one contact per kind, D-281, `venue_hours`, whose dataclasses are `core/hours.py`'s and whose rules, `check_venue_hours()`, keep each opening on a day of the conference, before its close and clear of the service's others, D-282; the sponsor credits' `SponsorCredits` and `SponsorCredit`, each with a slug, an `https` source and a checked date, whose slugs `check_credit_sponsors()` checks against a feed, D-337); the pages of links have theirs in `year_links.py`, whose checks `check_info()` calls, split from `year_info.py` at D-66's ~400 lines in #532 (About the PSF's `PsfInfo` and `PsfLink`, with `PSF_SECTIONS`, whose `check_psf()` refuses a blank text, a non-https URL, an unknown section, two labels with one identifier and a brand with an icon, D-283, and Social's `SocialInfo` and `SocialLink`, whose `check_social()` refuses a malformed or repeated hashtag, an unknown section, a non-https URL, a blank label or handle and two rows with one identifier, D-284). `config.py` keeps `load_year()`, the conference facts (`ConferenceInfo`, `Content`, `Snapshot`, `YearData`) and the conference and content rules.

---

## 9. Storage (D-48, D-49)

| What | Where | Key or file | Cleared by sign-out |
|---|---|---|---|
| Theme, high contrast | SharedPreferences | `pycon.theme` (`system`/`light`/`dark`), `pycon.high_contrast` (`system`/`on`/`off`) | no |
| Welcome seen | SharedPreferences | `pycon.onboarded` | no |
| Excluded tracks | SharedPreferences | `pycon.excluded_tracks` (`list[str]` of track keys; absent → `["Open Space"]`, an explicit `[]` kept) | no |
| Reminder settings, developer options | SharedPreferences | `pycon.reminders` (a JSON object of every `ReminderSettings` field, merged over the defaults: a missing or badly typed key reads as its default, an unknown one is dropped, D-275), `pycon.dev` (JSON) | no |
| Favourites | SharedPreferences | `pycon.<year>.favorites` (`list[str]`) | **no** (D-48) |
| Account, staff keys, start screen, sync flag (P3) | SharedPreferences | `pycon.account` (JSON: `email`, `nickname`, `features` by their API names; #684), the staff keys under `STAFF_PREFIX` = `pycon.staff_` (per year, D-466: `pycon.staff_<year>_sponsor` (JSON `{id, name, logo_url}`, #740, D-425), `pycon.staff_<year>_door_session` (JSON `{category_id, product_ids, label, all}`, #764, D-433), `pycon.staff_scanner_consent` (bool, D-423) and `pycon.staff_<year>_swag_categories` (a string list of category ids, #768); removed by `Storage.clear_prefs(STAFF_PREFIX)` at a sign-out, a sign-in as another account and Clear staff data, so a staff key added later goes with them, D-414), `pycon.start_screen` (`auto`/`now`/`lead`, D-16, #689; outside the staff prefix, so kept), `pycon.<year>.favorites_sync` (`merge`, `dirty`, `clean`; D-406) | yes, except start screen |
| API key and secret (P3) | `flet_secure_storage.SecureStorage` (`KeychainAccessibility.FIRST_UNLOCK_THIS_DEVICE`), through `services/credentials.py`; memory for the session without the extension (D-63) | `pycon.api_key`, `pycon.api_secret` | yes |
| Feed cache, change log | data dir | `feed-<year>.json` (raw bytes), `changes-<year>.json` | no |
| Staff outbox (P3) | sqlite in data dir | `outbox-<year>.db` (D-466) | see §12.1 |
| Inventories, CoC directory (P3) | memory only | `Staff` fields | yes |

SharedPreferences takes only `str`, `int`, `float`, `bool` and `list[str]` (F12): dicts are JSON strings, and the feed never goes there. All keys are constants in one table in `services/pref_keys.py` (split from `services/storage.py`, #777): each is a `Pref(key, default)` whose default's type is the value's type (`favorites(year)` builds the per-year key). `Storage.get()` reads a key, giving its default when the key is absent, unreadable or SharedPreferences fails (D-120); `Storage.read()` raises that failure instead, for the favourites, which must not take a failed read for an empty list (D-172), and the account, which must not clear the keystore after one (#684). `Storage.remove(pref)` removes one key and returns whether it is gone, an absent one included (#684).

```python
# src/pycon_us/services/pref_keys.py (excerpt)
THEME: Pref[str] = Pref("pycon.theme", "system")
EXCLUDED_TRACKS: Pref[list[str]] = Pref("pycon.excluded_tracks", ["Open Space"])
DEV: Pref[dict[str, Any]] = Pref("pycon.dev", {})           # a dict default: stored as JSON


# src/pycon_us/services/data_files.py (excerpt; split from storage.py in #708)
def data_dir() -> Path:
    """The durable data directory, read from the environment on every start (D-108)."""
    configured = os.environ.get("FLET_APP_STORAGE_DATA")
    path = Path(configured) if configured else Path.cwd() / ".flet/storage/data"
    path.mkdir(parents=True, exist_ok=True)
    return path.absolute()


def write_atomic(path: Path, data: bytes) -> None:
    """Write so that readers see the old file or the new one, never a partial file."""
    tmp = path.with_name(path.name + ".tmp")
    with write_lock:                       # writers share the temp file (D-120)
        try:
            with open(tmp, "wb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp, path)
        except OSError:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            raise
```

- `Storage(prefs, directory, year)` is built once in `Services.create()` as `Storage(ft.SharedPreferences(), data_dir(), year)`.
- Preferences: `await storage.get(THEME)` returns the stored value, or a copy of the default when the key is absent (an explicit `[]` is kept) or its value is not of the pref's type (logged). `await storage.set(pref, value)` JSON-encodes dicts.
- Feed cache: `read_feed()` returns a `CachedFeed(raw, saved_at)` (bytes and mtime) or `None`; it does not judge the bytes. `write_feed(raw)` runs `data_files.write_atomic` in `asyncio.to_thread` and is called only after `raw` parsed (D-39). `delete_feed(reason)` removes a cache that no longer parses (or that the Developer screen clears, or that a Developer feed URL may have filled when it is left, D-244) and logs why.
- Failures are logged and returned, never raised (D-120): `set` (also on a SharedPreferences timeout or client error) and `write_feed` return `False`, `get` returns the default, `read_feed` returns `None`, and the previous file stays. A store that saves what the user chose shows a `False` to the user. Only `data_dir()` raises, when the directory cannot be created (a broken install).
- `write_atomic` holds a module lock while it writes, because a cancelled refresh's `to_thread` write keeps running and the writers share the temp file. The lock gives the threads turns, not order, so `delete_feed()` first waits for every `write_feed()` asked for before it, a cancelled caller's too (each write is a task of its own, kept in `Storage._writes`): a write still queued for the lock would otherwise land after the deletion and bring the file back (D-244).
- The OS may purge `FLET_APP_STORAGE_CACHE`, so nothing durable goes there; the data directory survives updates (F14, D-108). Read it from `FLET_APP_STORAGE_DATA` on every start; never persist its absolute path, because iOS moves the container on an update. Without the variable (not `flet run`, not a packaged build: pytest, or a plain `python`), it is `.flet/storage/data` under the working directory, the layout `flet run` uses.
- **sqlite (P3, outbox only; `services/outbox_db.py`, #691):** one connection to the year's `outbox-<year>.db` in the data directory, opened lazily by the first use and used **only from the asyncio loop thread** (statements take milliseconds; never `to_thread`, and sqlite's default `check_same_thread` raises on any other thread), `PRAGMA journal_mode=WAL`, migrations by `PRAGMA user_version` (`outbox_schema.MIGRATIONS`: a file at version n runs the scripts after n, each in one transaction with its version). A failure to open, read or write is logged and returned (D-120): writes return `False`, `enqueue()` and the reads `None` (never zeros a sign-out would trust), `due_rows()` an empty list. S1 ran `sqlite3` in the embedded Python on Android and iOS, and the database survived update installs (D-108).

---

## 10. Private API: boundary, client and signing (P3; D-50..D-55)

### 10.1 Boundary (D-51)

Private-API features (sign-in, account, favourites sync, staff tools) stay hidden unless a mock base URL is set in the Developer screen (`prefs.dev.mock_api_url`, read as `Prefs.mock_api_url`; the Android emulator reaches the laptop at `10.0.2.2`). They ask `Prefs.private_api_enabled`, which re-renders them when the URL changes, and send through `Services.api`, which is None while no URL is set, so with none no code path holds a client (#668). The Developer field refuses a `pycon.org` host with the client's own guard (`private_api.parse_mock_api_url()`), and a PSF URL that reached the pref anyway still sends nothing: the client refuses it before the transport. Developer's **Check mock connection** (`private_api.check_connection()`) sends one signed `check_features`; signed out, the mock's 401 "Unknown API key." means it is there on the right year (signed in, its 200 `{"features": {...}}`), and it says "Connected to the local mock server."; any other answer (another 401 or another body included), or none, is said as the error. Save and Clear change the client and the stored URL one at a time, under `PrivateApi`'s lock, so pressed together they end as the last one says. Neither touches the account (D-398): with no URL nothing private shows or is sent, and set again, or changed, the same account signs. The client refuses any `/api/v1` request to a `pycon.org` host whatever the configuration (unit test `test_client_refuses_psf_hosts`). Sign-in and Account say "Connected to the local mock server".

### 10.2 Client (`services/api.py`; built in #665)

```python
# src/pycon_us/services/api.py (excerpt; docstrings in the module)
def refuse_private_psf(url: httpx.URL) -> None:
    """Make calling the PSF's private API impossible, even by misconfiguration (D-51)."""
    host = url.host.rstrip(".").lower()
    psf = host == "pycon.org" or host.endswith(".pycon.org")
    if psf and "/api/v1" in url.path.lower():
        raise PermissionError(f"Refusing a private PSF endpoint: {host}{url.path}")


class ApiClient:
    def __init__(self, base_url, year, credentials, *, transport=None, now=time.time): ...

    async def request(self, endpoint: Endpoint, *args: str | int, query: str = "", payload: object = None) -> object:
        path = endpoint.path.format(*(enc(str(arg)) for arg in args))      # a segment encoded (API-11)
        target = f"/{self._year}/api/v1/{path}" + (f"?{query}" if query else "")
        body = b"" if payload is None else canonical_body(payload)          # serialised once
        response, skewed = await self._attempt(endpoint, target, body)
        if endpoint.signed and response.status_code == 403 and skewed:
            response, _ = await self._attempt(endpoint, target, body)        # one retry, clock corrected
        return unwrap(response, endpoint.enveloped)    # 2xx → body, or its "data"; else ApiError

    async def _attempt(self, endpoint, target, body) -> tuple[httpx.Response, bool]:
        request = self._http.build_request(endpoint.method, target, content=body or None,
                                           timeout=endpoint.timeout)
        refuse_private_psf(request.url)                   # before credentials are read or anything is sent
        if body:
            request.headers["Content-Type"] = "application/json"
        stamp = js_round(self._now() + self.skew)
        if endpoint.signed:
            self._sign(request, stamp, body)              # over request.url.raw_path: the bytes on the wire
        response = await self._send(request)              # httpx.TransportError → NetworkError
        server = server_time(response.headers.get("Date"))
        if server is None:
            return response, False
        self.skew = server - self._now()
        return response, abs(server - stamp) > SKEW_LIMIT  # 300 s
```

- Two errors only (D-53): `NetworkError` (no answer: connection, DNS or timeout; never counted in the outbox) and `ApiError(status, message)` with `.is_auth` for 401/403. `message` is the server's own `error` (signed calls) or `message` (`authenticate`), else the reason phrase; a `{code, error}` envelope (whatever the status) is a refusal too, while a bare endpoint's JSON `null` is a success (returned as `None`). A 2xx that is not JSON, nests deeper than `MAX_NESTING` (32 levels, far more than any reply and far less than any stack overflows at: what the parser takes could still overflow when printed or dumped into an outbox row, #891), or an enveloped reply without `data`, says nothing about the call: it is `ApiError(None, ...)`, as is a reply a caller can't parse or an undecodable body, and `.unreadable` (`status is None`) tells it from a refusal, because the server may have applied it (#874). So a write treats `.unreadable` as `NetworkError.maybe_sent`: "Not confirmed" or flagged, never "not recorded" (D-410, D-434). `refuse_private_psf`'s `PermissionError` is neither: it is a refused misconfiguration, not an answer (the Developer screen can run the guard on a base URL before it builds the client).
- `self._http` is one `httpx.AsyncClient(base_url=..., transport=...)`, redirects not followed (a redirected request would need a new signature); tests pass `tools/mock_api/transport.py`'s `mock_transport`. `credentials()` returns the key and secret: `Account.credentials`, which `PrivateApi` hands every client it builds (#684); signed out, the request goes without `X-API-Key` and the server answers 401. `NetworkError.timed_out` says whether no answer was a timeout (`httpx.TimeoutException`), which sign-in says apart from being offline (D-54, #684). `NetworkError.maybe_sent` says whether the request may have reached the server (D-410, #693): False only for the errors raised before a connection existed (`NOT_SENT`: `ConnectError`, DNS failures included, `ConnectTimeout`, `PoolTimeout`, `ProxyError`, `UnsupportedProtocol`), True for the rest (a read or write error or timeout, a protocol error), after which the server may have applied it; the outbox flags such a row (§12.2).
- Signing `url.raw_path` (exactly what httpx sends) rules out "re-encoded after signing" bugs; queries are still built the Ionic way by `services/endpoints.py`'s `fetch_products_query`, `coc_capture_query` and `lead_capture_query` (§10.4), never `params=`. The skew is learned from every reply's `Date` (`server_time`, `email.utils.parsedate_to_datetime`) and kept; a signed call refused with 403 while the timestamp it sent was more than `SKEW_LIMIT` from that `Date` is sent once more, and a refused retry is final. Callers trust these errors, not `ft.Connectivity`. `fetch_feed(url)` (P0) is an unsigned 10 s GET with the same errors.

### 10.3 Signing (`core/signing.py`; D-52; built in #662)

```python
# src/pycon_us/core/signing.py (signatures; docstrings and bodies in the module)
JS_COMPONENT_SAFE = "!*'()~"         # encodeURIComponent keeps these besides A-Z a-z 0-9 - _ .

def canonical_body(payload: object) -> bytes: ...
    # JSON.stringify: json.dumps(separators=(",", ":"), ensure_ascii=False), UTF-8. Serialise once, send these bytes.
def js_round(x: float) -> int: ...
    # Math.round: halves go up, never to even. floor(x), plus 1 when x - floor(x) >= 0.5 (exact for any float,
    # where floor(x + 0.5) is wrong just below a half).
def sign(secret: str, timestamp: int, method: str, path_with_query: str, body: bytes = b"") -> str: ...
    # hex SHA-1 (not HMAC) of secret + timestamp + METHOD + path_with_query + body, with no separators.
def auth_headers(key: str, secret: str, now: float, method: str, path_with_query: str, body: bytes = b"") -> dict[str, str]: ...
    # buildRequestAuthHeaders: X-API-Key, X-API-Signature, X-API-Timestamp (str(js_round(now))).
def enc(value: str) -> str: ...
    # encodeURIComponent: urllib.parse.quote(value, safe=JS_COMPONENT_SAFE).
```

Headers `X-API-Key`, `X-API-Signature`, `X-API-Timestamp` (`str(ts)`; Ionic uses `Math.round(Date.now() / 1000)`). Only `hashlib`, `json`, `math` and `urllib` (D-75). Ionic's `[secret, ts, method, url, body].join("")` renders a null part (a signed-out secret) as `''`. **Vectors:** `tests/test_signing.py` checks the four below (secret `s3cr3t`, ts `1747324800`, recomputed with `hashlib`) and the 14 cases of `tests/fixtures/ionic/signing.json`, produced once by Ionic's own `buildRequestAuthHeaders` under Node (`tools/capture_ionic_reference/README.md`, testing-and-quality §4.1). The first two and the fourth below are also Ionic vectors there. `sha1-uint8array` 0.10.7 hashes a string as UTF-8, characters outside the BMP included, as `str.encode()` does.

| Method | Path with query | Body | Signature |
|---|---|---|---|
| GET | `/2027/api/v1/user/mobile_state/` | — | `77946e44677e7f97445336dd9de5f0a0b58dc016` |
| PATCH | `/2027/api/v1/user/mobile_state/` | `{"favorites":["123","poster-detail-7"]}` | `59b274bd80705949c06a5fd31abfe5f54307dc26` |
| POST | `/2027/api/v1/lead_retrieval/ABC123/note/` | `{"accessCode":"ABC123","note":"Interest: hot\nNotes: café"}` | `798ff969a24a536d3df9f504dcb16987f73dbd41` |
| GET | `/2027/api/v1/check_in/fetch_products/?attendee_access_code=ABC123&category_pk_list=1,2&mode=redemption_mode` | — | `3b49566459ec1ee2a43bdae2a2d87835c9aada52` |

### 10.4 Endpoints (data in `services/endpoints.py`; under `/{year}/api/v1/`; the contract is `tools/mock_api/README.md`)

| Name | Method and path | Body | Timeout | Reply | Notes |
|---|---|---|---|---|---|
| `authenticate` | POST `authenticate/` (**unsigned**) | `{email, password}` | 3 s | bare | single flight |
| `check_features` | GET `user/check_features/` | — | 2 s | bare | absent flag = False |
| `mobile_state` | GET / PATCH `user/mobile_state/` | — / `{favorites}` | 2 s | bare / ignored | §10.5 |
| `redeemable` | GET `check_in/redeemable/` | — | 2 s | bare | categories split by `/shirt\|swag/i` |
| `inventory` | GET `check_in/attendees_by_product_with_quantity/<id>/` | — | 20 s | bare list | per product, gathered |
| `fetch_products` | GET `check_in/fetch_products/?…` | — | 10 s | bare | query **not encoded** (Ionic); swag `category_pk_list` + `redemption_mode`, door `product_pk_list` + `door_check_mode` |
| `redeem` | POST `check_in/redeem_products/` | `{attendee_access_code, badge_validator, scanned_at, "product-redeem-<id>", "product-<id>-quantity"}` | 10 s | bare | door omits a missing validator, swag sends `""` |
| `coc_attendees` | GET `mask_violations/attendees/` | — | 15 s | `{code, data}` | memory only |
| `coc_capture` | GET `mask_violations/capture/?attendee_access_code=<enc>` / POST `mask_violations/capture/` | — / `{attendee_access_code, notes?, force: true}` | 5 s | `{code, data}` | Ionic: POST when there are notes or `force`. The app sends only the POST, with `force` (D-430); the GET is not called |
| `lead_sponsors` | GET `lead_retrieval/sponsors/` | — | 5 s | bare | strip quotes from names |
| `lead_capture` | GET `lead_retrieval/capture/?attendee_access_code=<enc>&badge_validator=<enc>[&sponsor_id=<enc>]` | — | 2 s | `{code, data}` | outbox only |
| `lead_note` | POST `lead_retrieval/<code>/note/` | `{accessCode, note[, sponsor_id]}` | 2 s | ignored | outbox only, after its capture |

Each row is an `Endpoint(name, method, path, timeout, signed=True, enveloped=False)` constant (`AUTHENTICATE` … `LEAD_NOTE`, all in `ENDPOINTS`; `coc_capture` is two, `COC_SCAN`, kept as the contract but never called, and `COC_REPORT` (D-430), and `mobile_state` is `READ_MOBILE_STATE` and `WRITE_MOBILE_STATE`); `tests/test_api_endpoints.py` checks the table against the README's rows and the mock's routes. The timeout applies to connect, each read, the write and the pool. Ionic reads most replies bare and only three inside a `data` member (`{code, data}`, the 2019 envelope), so `Endpoint.enveloped` says which. Signed errors are `{code, error}` and `authenticate`'s carries `message`; the README cites each by line and lists what is unknown. Ionic also defines `check_in/attendees_by_product/<id>/` (2 s) but never calls it, so it is not ported (API-05).

### 10.5 Account and favourites sync (D-54, D-55)

- **Sign-in:** `AutofillGroup` with hints, an in-flight guard, distinct errors for a wrong password (`is_auth`) and for offline or timeout. Credentials reach SecureStorage *before* `signed_in` flips; then the first sync. Sign-in's reply carries the flags, `is_speaker` among them.
- **Role flags (D-54, D-403):** `Account.refresh_flags()` asks `check_features` at start (not awaited), on resume and on the Account screen's mount, one call at a time; absent flags read False and `is_speaker` stays as sign-in gave it. No answer keeps the stored flags. A refused key (`ApiError.is_auth`, the mock's `revoked`) sets `Account.expired`: the account stays signed in, so unsynced rows keep their owner and nothing is deleted, and More's profile row says "Sign in again" (`more.sign_in_again`), which opens Sign in with the email filled in; a sign-in clears it.
- **Favourites (D-55, D-406):** `services/favorites_sync.py`'s `FavoritesSync` is `Services.favorites_sync`; `App` runs it once the start has loaded (`use_favorites_sync()`), and `on_resume()` asks it for a pull. One loop, one request at a time: a pull asked for during a PATCH runs after it. It pulls at start, on resume and at sign-in, and `core/favorites_sync.py`'s pure `reconcile()` decides by the saved state, `pycon.<year>.favorites_sync`: `merge` (the first sync after a sign-in, absent by default) keeps the **union**, `dirty` keeps the local list, `clean` adopts the server's, `[]` included (a removal made elsewhere); whatever differs from the server's list is pushed (ints from the server become strings). Each local edit makes `clean` `dirty`, saved before any request, and schedules a debounced (1 s), idempotent full-list PATCH, which makes it `clean` unless the list or the account changed meanwhile; a failure keeps it for the next start or resume. `Account.favorites_dirty` says whether it is waiting, on the Account page (#688); `flush()` sends it at once before a sign-out (D-411). Nothing is sent signed out, `expired`, with no client or with favourites that could not be read; a sign-in or a sign-out sets `merge` (the key removed), and the local list stays (D-48).
- **Sign-out (#688, D-411):** the Account page's Sign out first awaits `FavoritesSync.flush()`, one try to send My schedule's unsent changes (it waits for a request the loop has out, on one `_sending` lock, then sends the PATCH, or a first sync's pull and PATCH), then asks in an `AlertDialog`, which names the changes only when that try failed. `Account.sign_out()` then awaits every removal: the key, the secret and `pycon.account`; the sync forgets its state (`merge`); favourites, theme, filters, reminders, onboarding and the start screen stay. With the account's unsynced staff rows (pending or failed, read from the outbox when the dialog opens, then `Staff`'s counts after each pass) the dialog asks "3 scans haven't synced. Sign out anyway?" with Sync now (it retries the failed rows, makes the pending ones due now with `OutboxDb.due_now()`, then `kick_once()`, or a plain kick when a pass is under way) and "Sign out anyway (3 unsynced)"; `Account.sign_out()` also removes the staff keys (`STAFF_PREFIX`), and never a row: they stay under their owner (#695, D-414).

---

## 11. Mock server (`tools/mock_api/`; D-50, D-57, NEW-08)

| Part | What it is |
|---|---|
| `handlers.py` | the pure `handle(state, method, raw_path, headers, body) -> (status, headers, body)`: routing (one table, `{}` for a path segment), envelopes, the signature check and the account endpoints |
| `state.py` | `MockState` (in-memory accounts, sponsors, products, attendees, faults, injectable `now`, `capture="idempotent" \| "non_idempotent"`, and the leads, notes, redemptions and incidents it recorded, so tests count applications), loaded from the seed; `Call`, a checked request; `Refused`, an error reply |
| `check_in.py`, `conduct.py`, `leads.py` | the staff endpoints (door and swag, Code of Conduct, lead retrieval), each gated by its role flag (403 otherwise); `parse.py` reads their bodies and queries the way Ionic builds them |
| `server.py` | stdlib `ThreadingHTTPServer` over `handle` (`python -m tools.mock_api.server [--host 0.0.0.0] [--port 8000] [--capture ...]`, loopback by default; development.md §6), a lock around `handle`, the target and body passed as received, a banner with each device's base URL and the fake accounts, one log line per request without its query or body; `--fault NAME [--every-request]` and `--skew SECONDS` (D-57) |
| `crowd.py` | `crowd(count, first_id)`: made-up attendees in the seed's shape, which `MockState.from_seed(attendees=N)` and `--attendees N` add after the seeded four (`MOCK0005` onwards), for a large CoC directory (#758) |
| `faults.py` | `Faults`: the D-57 faults switched on (`connect`, `timeout`, `lost_response`, `revoked`), each one-shot or kept until cleared |
| `transport.py` | `handle_with_faults`, the transport faults around `handle` for both front ends, and `mock_transport(state)`: `httpx.MockTransport` over it, for client tests |
| `badges.py` | writes a printable HTML sheet of mock-badge QR codes (`code:validator`, inline SVG from `segno`, a dev-only dependency; D-391) for the P3 exit test |
| `README.md` | the contract: endpoints, envelopes and fields citing `pycon-api.ts` by line, plus what is **unknown** (server idempotency, the timestamp window) and how the mock models it |
| `tests/fixtures/mock/` | seed data (`seed.json`): one account per role, sponsors (one JSON-quoted), door and swag categories and products, attendees with badges and prior Code of Conduct incidents (the Ionic signing vectors are in `tests/fixtures/ionic/signing.json`) |

`handle` checks the route, then for signed routes: unknown key → 401; timestamp outside the window (600 s per the 2019 API docs, UNCONFIRMED) or wrong signature (`hmac.compare_digest` against `sign(secret, ts, method, raw_path, body)`) → 403; then the endpoint: an account without its role flag → 403, an unknown access code or a wrong validator → 404. The mock never proxies or points at PSF hosts, and nothing test-only lives in the app.

`transport.py` wraps `handle` in `httpx.MockTransport`: a `connect` fault raises `httpx.ConnectError` and a `timeout` fault `httpx.ReadTimeout` before `handle` runs; a `lost_response` fault runs `handle` (the server commits) and then raises `httpx.ReadError`. The server drops the connection for the same faults (holding it unanswered for `timeout`). `handle` itself answers 401 under `revoked`, and dates its replies and checks the window with `MockState.skew` added to its clock. Signatures are checked against `request.url.raw_path`, exactly as sent. The scenarios through the real client are `tests/test_api_faults.py` (#667).

**Scenarios (D-57):** connection refused (tries not counted, nothing flagged); committed-but-lost response (no duplicate lead under idempotent semantics; under non-idempotent ones the resend is a second record, and its row is flagged "may be recorded twice", D-410; `tests/test_sync_faults.py`); revoked key (sign-in prompt, rows wait); clock skewed by 900 s (one corrected retry); account or sponsor switch mid-queue (rows keep their snapshot); `MockState(capture="idempotent" | "non_idempotent")`, since client dedupe cannot prove server exactly-once.

---

## 12. Staff tools: outbox, sync and scanning (P3; D-56, D-65)

### 12.1 Outbox (`OUTBOX_V1` and `OUTBOX_V2` in `services/outbox_schema.py`)

```sql
CREATE TABLE IF NOT EXISTS outbox (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL CHECK (kind IN ('lead', 'note', 'door')),
    key          TEXT NOT NULL,                 -- attendee access code
    payload_json TEXT NOT NULL,                 -- the request; on success also {"result": ...}
    owner        TEXT NOT NULL,                 -- lower-cased account email at enqueue
    sponsor_id   TEXT,                          -- snapshot at enqueue (STORE-11)
    sponsor_name TEXT,
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'synced', 'failed')),
    tries        INTEGER NOT NULL DEFAULT 0,    -- counted failures only
    next_at      REAL NOT NULL,
    created_at   REAL NOT NULL,                 -- = scanned_at
    last_error   TEXT,
    idem_key     TEXT,                          -- door: code|sorted product ids|scan session
    revision     INTEGER NOT NULL DEFAULT 0     -- +1 on each enqueue edit; a send saves only over its own
);
CREATE INDEX IF NOT EXISTS outbox_due ON outbox (owner, status, next_at);
CREATE INDEX IF NOT EXISTS outbox_key ON outbox (owner, kind, key);
CREATE UNIQUE INDEX IF NOT EXISTS outbox_idem ON outbox (idem_key) WHERE idem_key IS NOT NULL;

-- OUTBOX_V2 (#693, D-410): a send got no answer after the server may have had it; never cleared
ALTER TABLE outbox ADD COLUMN maybe_sent INTEGER NOT NULL DEFAULT 0;

-- due rows: a note waits until its lead, the same sponsor's, is synced (D-459)
SELECT o.* FROM outbox o
WHERE o.owner = :owner AND o.status = 'pending' AND o.next_at <= :now
  AND (o.kind <> 'note' OR EXISTS (SELECT 1 FROM outbox l WHERE l.owner = o.owner AND l.kind = 'lead'
                                   AND l.key = o.key AND l.sponsor_id IS o.sponsor_id AND l.status = 'synced'))
ORDER BY CASE o.kind WHEN 'lead' THEN 0 WHEN 'door' THEN 1 ELSE 2 END, o.created_at, o.id;
```

`OutboxDb` (#691) is the only way to the rows: `enqueue(code, decide)` runs a `core/outbox.py` decision (`scan_lead`, `save_note` or `admit` as a `functools.partial`) over every row of the access code and stores what it decides, in one transaction; `save(row)` writes a send's outcome or "Retry failed" over a stored row, but only while the record is still at the `revision` the row was read at: an enqueue's edit (`UPDATED`) counts a new revision, so a note edited while `SyncWorker` sends its old text keeps the new text, pending, and the stale outcome is dropped (`save()` returns `False`, logged) for the next pass to send the edit (D-56); `due_rows(owner, now)` is the query above, tested equal to `outbox.due()` on random row sets; `counts(owner)` (pending, failed, synced), `rows(owner, statuses)` for the queue sheet (oldest first), `owners_with_unsynced()`, `delete_synced(owner)` (`forget_synced()` in SQL, tested equal to it) and `clear(owner=None)`. The schema lives beside its one user (`services/outbox_schema.py`, with `MIGRATIONS`, the due and delete-synced queries, the row mapping and `update()`, the write that lands only at the row's revision) rather than in `services/storage.py`.

Synced rows are kept: lead dedupe and door "Already checked in" read them. On an account switch, the previous owner's synced rows are deleted (`outbox.forget_synced()`, `OutboxDb.delete_synced()`), except a synced lead whose note, the same sponsor's, hasn't synced, which the note waits for; their pending or failed rows stay (visible in Developer: the Staff queue row's sheet lists them under "Other accounts", D-412) until synced or cleared with confirmation. The purge runs as each signed-in account's sync starts (`services/sync.py`'s `_start()`: `OutboxDb.forget_other_accounts(owner)`, every other owner's `delete_synced()`), so it needs no record of the previous owner and a purge cut short by a kill runs at the next start; a sign-in as another account (not the same one after `expired`) removes the staff keys too (`Account._sign_in`, D-414). **Clear staff data** (Developer › Data, DEV-03) and Reset app delete every owner's rows (`staff_data.clear_staff_data()`: `OutboxDb.clear()`, `clear_prefs(STAFF_PREFIX)`, `Staff`'s counts to zero) after a confirmation that names the unsynced count (`OutboxDb.counts(None)`, every owner's); rows that can't be counted are not deleted, and a never-created `outbox-<year>.db` is not opened (D-51).

### 12.2 Transitions (`core/outbox.py`, pure; hypothesis state-machine tests)

Each enqueue (`scan_lead()`, `save_note()`, `admit()`) returns an `Enqueued(outcome, row, others)`: `queued` (insert the new row), `updated` (save the changed row), `already` (nothing to store; the row is the one that made it so) or `ignored`. The send transitions (`after_success()`, `after_network_error()`, `after_error()`) refuse a row that isn't pending, `retry_failed()` one that isn't failed. `due(rows, owner, now)` is the Python twin of §12.1's query, so the db's SQL is tested against it. `status_text(row)` is a row's status in the queue sheet's words (`STATUS_WORDS`: Queued, Confirmed, Failed), followed by " · may be recorded twice" (`MAYBE_TWICE`) once the row is flagged (`Row.maybe_sent`): a send that ended in a `NetworkError` with `maybe_sent` sets it, and no later outcome, edit or "Retry failed" clears it, so a row that then syncs reads "Confirmed · may be recorded twice" (D-57, D-410). The client cannot see the server's records, so this is how a duplicate is detected and shown; the queue sheet and the tools' lists (#694, #39, #40) show it with an icon beside the words.

| From | Event | To | Effect |
|---|---|---|---|
| — | lead scan; a synced row exists for (owner, code, sponsor) | — | `already`: "Already in your leads", no new row |
| — | lead scan; that sponsor's pending row exists | pending | `next_at = now`, kick; its payload stays |
| failed | lead scan for that row's sponsor | pending | as "Retry failed": `tries = 0`, `next_at = now` |
| — | lead scan otherwise, another sponsor's row included (D-459) | pending | `queued`: snapshot sponsor, kick; another sponsor's row isn't touched, and `Enqueued.others` names it for the result |
| — | note saved, empty or blank | — | `ignored` |
| — | note saved (non-empty) | pending | `queued`: one note per (owner, code, sponsor), body `{"accessCode", "note"}`, the sponsor snapshot of the lead it is for, which the caller gives from that lead's result or row, never the sponsor chosen now (D-459) |
| any | note saved again (non-empty) | pending | `updated`: the new text, `tries = 0`, `next_at = now` (a synced note was edited, so it is sent again) |
| — | door scan; one of the account's door rows for the code covers a product of the session | — | nothing enqueued: "Already checked in" (`core/admission.decide()`, STORE-12) |
| — | door admit; its `idem_key` exists | — | `already`: the queued check-in |
| — | door admit otherwise | pending | `queued`: unique `idem_key` (code, sorted product ids and scan session, joined by `\|`); one row per check-in |
| pending | sent | synced | result merged into the payload under `"result"`; `last_error` cleared; a door row's reply with `errors` (already redeemed, not bought, over quantity) syncs it too, and the queue sheet says "Confirmed · Already redeemed" (D-441) |
| pending | `NetworkError` | pending | tries unchanged, `next_at = now + 60` (`NETWORK_BACKOFF`), end the pass; when `maybe_sent`, `maybe_sent = 1` for good, by id (`OutboxDb.flag_maybe_sent()`), so an edit while it was sent keeps it (D-410) |
| pending | `ApiError` | pending → failed | `tries += 1`, `last_error`, `next_at = now + 60`; failed at 10 (`RETRY_CAP`) counted failures; when `.unreadable` (the server may have applied it), `maybe_sent = 1` for good, by id, as above (D-410, #874) |
| failed | "Retry failed" | pending | `tries = 0`, `next_at = now`, `last_error` cleared |

Invariants (`tests/test_outbox_machine.py`, a `RuleBasedStateMachine` with scans, notes, door admits, sends that succeed or fail either way (a `NetworkError` before the request left, or after it: a lost answer; an `ApiError`, a refusal or an answer that can't be read), streaks of refusals, "Retry failed", sponsor and account switches and time passing): no unsynced row lost; owner, sponsor snapshot, kind, code, `idem_key` and `created_at` fixed at enqueue; only sent rows are synced, and a synced row is never due; a note is never due before its lead, the same sponsor's, is synced, keeps that lead's sponsor, and that lead's row is never forgotten while it waits; `tries` counts only `ApiError`s, and a row is failed exactly at 10; a row is flagged `maybe_sent` exactly from its first lost or unreadable answer on (D-410); one lead and one note row per (owner, code, sponsor), one door row per `idem_key`. The table's rows are `tests/test_outbox.py`. Swag pickup and CoC capture are **online-only** and say so before scanning.

### 12.3 `SyncWorker` (`services/sync.py`; #692, D-407)

```python
# src/pycon_us/services/sync.py (excerpt; docstrings in the module)
class SyncWorker:
    """Sends the signed-in account's due rows: the only sender of the outbox."""

    def __init__(self, db, api, account, staff, *, wake=None, foreground=None,
                 closed=None, on_refused=lambda: None, now=time.time): ...

    def kick(self) -> None:
        self._wake.set()

    async def drain(self) -> None:
        staff, owner = self._staff, self._account.owner
        if staff.syncing or not self._may_send(owner):  # one pass at a time
            return
        staff.syncing = True
        outcome = (None, False, False)
        try:
            outcome = await self._send_due(owner)  # (last error, reached, offline)
        finally:
            if not self._closed.is_set():
                self._report(owner, *outcome)  # counts, last_error, last_sync_at, offline

    async def _send_due(self, owner):
        error, tried = None, set()
        while rows := [r for r in self._db.due_rows(owner, self._now())
                       if (r.id, r.revision) not in tried]:
            for row in rows:
                if not self._may_send(owner):  # signed out, switched, expired, closed
                    return error, False, False
                tried.add((row.id, row.revision))
                try:
                    result = await send(self._api, row)
                except asyncio.CancelledError:  # the server may have it (D-410)
                    self._db.flag_maybe_sent(row.id)
                    raise
                except NetworkError as failure:  # flags the row when maybe_sent (D-410)
                    if failure.maybe_sent:  # by id: an edit since keeps the flag
                        self._db.flag_maybe_sent(row.id)
                    self._db.save(outbox.after_network_error(
                        row, self._now(), maybe_sent=failure.maybe_sent))
                    return str(failure), False, True  # offline (#694)
                except ApiError as failure:
                    if failure.status == REFUSED_KEY:  # 401: not counted
                        self._db.save(outbox.after_network_error(row, self._now()))
                        self._on_refused()  # Account.refresh_flags() sets expired
                        return str(failure), False, False
                    error = str(failure)
                    if failure.unreadable:  # it may have been applied (D-410)
                        self._db.flag_maybe_sent(row.id)
                    self._db.save(outbox.after_error(
                        row, failure.message, self._now(), maybe_sent=failure.unreadable))
                else:
                    self._db.save(outbox.after_success(row, result))
        return error, True, False
```

`due_rows()` gives each row its `revision`, so the worker needs nothing more: a `save()` refused because the row was edited during its send leaves the edit due (§12.1), and the pass reads the due rows again until none is left, so the edit, and a note whose lead synced in the pass, go at once. `send(api, row)` is a `match row.kind` over `lead_capture` (query from the payload's `badge_validator` and the row's `sponsor_id`), `lead_note` (the payload plus the row's `sponsor_id`) and `redeem` (the payload as it is): always the row's snapshot, never the sponsor picked now (STORE-11). `run(tick=60)` waits for `foreground`, returns once `closed` is set, clears the wake, drains (wrapped in `report_errors`), then waits for the wake or the tick. Outbox times are real epoch seconds (`time.time()`), like the signatures.

`supervise(svc, account, staff, prefs)` keeps the one worker: it subscribes to `Account` and `Prefs` (where the mock URL is) and, on each change, compares `sync_target()` (the client and the owner while `Services.api` exists and the account is signed in and not `expired`, else None) with the running worker's; a different one cancels the old task before starting the next, so two never send at once, and None clears `Staff` when signed out. `use_sync_worker()`, called by `App` before the boot gate, runs it in one effect keyed on `prefs.loaded`, so unmount cancels it (F2) and `close()` ends it (D-147). `Services.sync_wake` is the worker's wake: `kick_sync()` (every enqueue and "Sync now"), `on_resume()`, `close()` and `ft.Connectivity`'s change to anything but `NONE` set it. Tests: `tests/test_sync.py` (order, a note after its lead, faults, the cap, D-57's exactly-once under `lost_response`, connection errors and skew, owners and sponsors, one pass at a time, cancellation), `tests/test_sync_faults.py` (D-57's duplicates: a lost answer flags exactly its row under both semantics, every duplicate the mock records is a flagged row, also after a rescan while it was sent or a cancel after the mock committed, and a failure before the request left flags none; D-410) and `tests/test_sync_loop.py` (the loop, the supervisor, the triggers).

### 12.4 Staff gating (D-16, D-54; exhaustive truth-table test)

`staff_entries(flags)` (pure, `core/staff_tools.py`, #722) drives the More "Staff tools" section and the Now card: the `StaffTool`s (key `lead`, `door`, `swag` or `coc`, title, `ft.Icons` name, route `/more/staff/<key>`) an account may open, in O-7's order. `flags` maps the `Account` attribute names `lead_retrieval`, `door_check` and `mask_violation` to booleans; an absent flag, or anything but `True`, is off (SHELL-11). `may_open(key, flags)` is a screen's re-check and `scans_for_sponsor(flags)` the picker's rule: the picker is `screens/lead_sponsor.py`'s `SponsorPicker`, a child route of each Lead scanner route (`…/staff/lead/sponsor`), and the scanner reads the choice (`pref_keys.staff_sponsor()`, `staff_sponsor.read_sponsor()`) from storage at each change of location (#740, D-425). Door check's session picker is the same pattern (`screens/door_session.py`'s `SessionPicker` under each Door check route, `…/staff/door/session`; `may_open(DOOR)`; the choice `pref_keys.staff_door_session()`, `door_choice.read_door_session()`; #764, D-433), and both pickers are built from `ui/staff_picker.py`'s parts. The entry points list `built_entries(flags)`: the entries whose screen is in the route table (`BUILT_TOOLS`, which each tool's PR extends, D-169); `card_tool(entries, last)` picks the Now card's tool (the last opened in this process, `ViewMemory.staff_tool`, else the first; D-421), and `queue_words(pending, failed)` says the `Staff` counts on the tools of `QUEUED_TOOLS` (the Lead scanner and Door check, #766; Swag pickup, built since #769, has no rows). `screens/staff_entry.py` renders both (#725): More's section under the profile row and Now's `ScanCard`, only while a mock URL is set and the account is signed in. Swag pickup (`screens/staff_swag.py`'s `SwagPickup`, #768) re-checks `may_open(SWAG)` the same way, reads its categories (`pref_keys.staff_swag_categories()`) from storage as it opens, as the sponsor is read, and pauses its scan screen while `ui/online.py`'s `use_online(watch=True)` says offline (D-56); its handler is `swag.look_up()`, nothing queued.

| Entry | Rule |
|---|---|
| Lead scanner | `lead_retrieval or door_check` |
| Door check, Swag pickup | `door_check` |
| CoC capture | `mask_violation` |
| "Scan on behalf of" sponsor picker | `door_check and not lead_retrieval` |
| Default start screen "Lead scanner" (applied after the account is restored; `starts_on_lead(flags, start_screen)`, #689) | `lead_retrieval`, unless Settings' Start screen is `now` |
| Staff section and Now card | any entry above |

Each staff screen re-checks its rule on every render ("Not available for this account", `ui/scan_screen.py`'s `NotAvailable`, `staff.not_available`), also when signed out or with no mock URL (D-51), so deep links cannot bypass it. The three terms are one hook, `use_tool_allowed(tool)` beside `NotAvailable` (#900); the Lead scanner's sponsor picker adds `scans_for_sponsor`. The hook reads the flags as `Account.role_flags`.

### 12.5 Badges, admission and the scan surface

- `parse_badge(raw)` (`core/badges.py`, #722) returns a `Badge` (`code`, `door_validator`, `lead_validator`), or None for no `:` or an empty code after stripping whitespace ("Not a badge code"): code = segment 0; validator = segment 1 for door and swag, the **last** segment for lead; CoC sends the code only (LEAD-03). `decide(inventory, code, product_ids, kept)` admits optimistically; an unknown badge falls back to `fetch_products` online, "Can't check this badge" offline (DOOR-04, #766).
- One `ScanScreen` for all four tools (D-65): the E1 preview when `capabilities.SCANNER`; a manual `TextField(on_submit=...)` for the `code:validator` payload, which HID scanners also type; one accepted result per code every 4 s (`core/badges.py`'s `Cooldown`, whose `accept(code, now)` takes the time in); outcomes as colour, icon and word, with haptics and a `Semantics(live_region=True)` panel; the screen stays awake while mounted (an `async def` effect awaits `svc.wakelock.enable()`; its `async` cleanup awaits `svc.wakelock.disable()`, rule 3 and D-387); camera permission via `await svc.permissions.request(Permission.CAMERA)` after a primer.
- **As built (#723, D-416):** `ui/scan_screen.py`'s `ScanScreen(title=, on_badge=, context=, actions=, paused=)` (later `result_actions=`, #742, and `posted=`, #761); `on_badge(badge)` is async and returns a `ScanResult` (`core/badges.py`: a `ScanOutcome` of accepted, duplicate, denied, queued or invalid, the word, the name or code, the details), so a tool returns data only. A submit parses; junk shows `NOT_A_BADGE` and keeps its text; a valid code clears the field (`use_field_query().clear()`, which puts the focus back) before the cooldown, so a held code is cleared without a word; one handler runs at a time (a second submit is dropped, its text kept); `paused` drops submits. The panel is `ui/scan_result.py`'s, in a `ResultPanel` component that ticks its age each second (`Services.run_every`) outside the live region. The time is `scan_screen.clock()`, `time.monotonic()`.
- **As built (#741, D-426):** the Lead scanner's handler is `lead_capture.capture(db, staff, kick, badge, owner=, sponsor=, clock=)`, given to `ScanScreen` as a `functools.partial` of all but the badge. It enqueues `functools.partial(scan_lead, …)` with `{"badge_validator": badge.lead_validator}` and the sponsor chosen now (None for a sponsor's own account); `ALREADY` returns the duplicate at once. Otherwise `Staff.update_counts()`, a `Staff` subscription, `kick_sync()`, and `OutboxDb.row(id)` re-read at each `Staff` change until `moved()` (synced, failed, `tries` or `next_at` changed) or `WAIT_SECONDS` (3 s); `result_of(before, after)` maps the row to the `ScanResult` (ux.md §7.3). The `SyncWorker` stays the only sender (D-407). `ScanScreen` drops a result that arrives after unmount or while its View is not on top (`is_top_view()`).
- **As built (#742):** a lead note. `core/lead_notes.py` is pure: `LeadNote(interest, follow_ups, text)`, `compose()` writes Ionic's lines (`Interest: warm`, `Follow-up: Demo, Hiring`, `Notes: …`, each only when set; nothing set is `""`, which `save_note()` ignores), and `parse()` reads them back with Ionic's patterns, case-insensitively, Interest and Follow-up only before `Notes:` (so the text may mention them), anything else being a legacy free-text note. `lead_note.py`: `saved_note(db, owner, code)` (the account's note row for the lead, from `OutboxDb.rows()`; None when that read fails, so the sheet stays closed rather than prefill a blank note over the saved one), `store()` (enqueues `functools.partial(save_note, …)` with the composed text and the sponsor chosen now, which the row replaces by its lead's snapshot, §12.2) and `confirm()` (`Staff.update_counts()`, then, when the lead is synced, `lead_capture.sent()`'s wait on the note row; otherwise a kick and "Will sync." at once, since the note is not due before its lead). `ScanResult` carries the access code (`code`), and `ScanScreen(result_actions=)` builds the tool's buttons for the result shown; the Lead scanner's `LeadTool` calls `use_note_sheet(owner=, sponsor=)` on every render (D-70), which keeps the sheet's lead and draft and shows it through `ft.use_dialog`; its Notes field is built from what Flutter last reported, through a `Ref` made for each opening (D-243), and its handlers keep the draft in a `use_ref` beside the state, which Save reads, since `use_state` only schedules a render and two events can come before it, and the scan screen's `paused` is its reason while it is open. A SnackBar after Save is dropped once the screen has gone or is not on top.
- **As built (#743, D-428):** the leads list. `lead_list.leads(db, owner)` reads `OutboxDb.rows(owner, every status)` and keeps its `lead` rows newest first, each paired with whether the owner has a `note` row for its code (None on a failed read, D-120); `lead_count()` is the scanner's "Leads (42)". `core/lead_views.py` (pure): `LeadView` (code, name, status, words, flagged, ago, sponsor id and name, has_note) from `lead_view(row, has_note, now)`, `phrase()` for its one node, `filter_leads(views, query, sponsor_id)` (each folded word in the name or code; the sponsor by id). `screens/staff_leads.py`'s `LeadsPage` is a child route of both scanner routes, reads the rows in `use_memo` on `Staff.revision` (D-69) and ticks with `use_minute()` (D-175); its rows are memoised components keyed by code (D-153) in a `ListView` Flutter builds on demand. The scanner's tool buttons carry keys: "Leads (42)" is built by `LeadTool` and kept across `ScanScreen`'s own re-renders, so without one a result's "Add note" landing in its slot took its control id (U163, #622).
- **As built (#829, D-459):** a lead belongs to a sponsor. `scan_lead()` and `save_note()` key by (owner, code, `sponsor_id`), so a scan for a second sponsor is `queued` with its own snapshot, and a repeat for one sponsor stays that row's. `Enqueued.others` carries the names of the account's other sponsors on the attendee. `lead_capture.attributed()` puts "For Beta Corp" and "Also in your leads for Acme" first in a staff result's details and sets `ScanResult.sponsor` (`snapshot()`, `core/lead_sponsors.py`). `use_note_sheet()` takes no sponsor: `NoteSheet.open(code, name, sponsor)` gets it from the result, or from the row on the leads list, so a note goes with its lead whatever is chosen since, and `lead_note.saved_note(db, owner, code, sponsor_id)` prefills that sponsor's note. `lead_list.leads()` flags a note per (code, sponsor); `LeadView.key` is the row's component key and the end of its identifier; `queue_rows.row_tile()` adds the sponsor. No schema change: every row already on a device fits the new key (`tests/test_outbox_existing_rows.py`).
- **As built (#758, D-430):** the CoC tool's data and calls, before its screens. `core/conduct.py` is pure: `Attendee(code, full_name, nickname, badge_name, incidents)`, its three names folded once (`folded`); `parse_directory(data)` leaves out an entry without an access code, keeps a repeated code once, reads a missing or non-integer `violations` as 0 and sorts by the folded `display_name()` (full name, else nickname, badge name, code); `search(attendees, query, limit=25)` returns `Matches(rows, more)`, every folded word in the three names (D-46), nothing for an empty query, `more` when rows were cut ("Refine your search"); `count_words(n)` ("No incidents on record", "1 incident on record", "3 incidents on record") and `count_level(n)` (`Level.NONE` for 0, `NOTICE` for 1 or 2, `HIGH` for 3 or more), one set for the list and the result, which the screens show as a colour and an icon; `parse_capture(data)` returns `Recorded(name, badge_name, email, incidents)`, the count None when the reply has none. `conduct.py` holds the calls: `fetch_directory(api)` (`COC_ATTENDEES`, 15 s) and `record(api, code, notes)` (`COC_REPORT`, 5 s, always with `force: true`, notes only when not blank); an unreadable reply is an `ApiError`, and neither logs anything (D-72). The directory is kept by the caller, in memory only (D-56). The mock's `--attendees N` (`MockState.from_seed(attendees=N)`, `tools/mock_api/crowd.py`) adds N made-up attendees, `MOCK0005` onwards.
- **As built (#759, D-432):** `screens/staff_coc.py`. `CocScanner` (at `/more/staff/coc` and `/now/staff/coc`) re-checks `use_tool_allowed(COC)` on every render, else `NotAvailable`, and sets `ViewMemory.staff_tool`. `CocTool` fetches the directory on mount and on Retry or Reload, in a coroutine effect that Flet cancels on unmount, and keeps it in `use_state` as `Directory(owner, status, by_code)` (loading, loaded, failed, or refused on a 403): no store, no storage, no log line. It goes when the screen unmounts and is fetched again on the next visit. `status_line()` is the scan screen's `context`; `use_online(svc, watch=True)` pauses scanning offline ("CoC capture needs a connection") and disables Retry and Reload, and a 403 pauses it too. The interim `on_badge` returned `neutral_result(code, directory)` and sent nothing until #760.
- **As built (#760, D-434):** `ui/coc_review.py`. `use_review(on_recorded=)` keeps the open `Review(code, name, badge_name, incidents, sending, problem, maybe_sent)` in `use_state` with a `latest` ref the handlers read (#756) and shows `review_dialog()` (`ui/coc_review_dialog.py`, the look alone) through `ft.use_dialog`; its `open(code, attendee)` sets the review and awaits a future that Record's reply (`recorded_result()`), Cancel or Back (`closed_result()`) or the unmount resolves. `CocTool`'s `on_badge` is `review_badge()` over that `open()`, so `ScanScreen`'s single flight holds while the dialog is open, and `paused` is "Paused while the review is open". Record reads the notes from the field's `Ref` (D-243), calls `conduct.record()` once, and on a reply calls `on_recorded(code, count)`, which `CocTool` applies to its directory with `with_count()`; `problem_of()` maps an `ApiError` (the server's message; an unreadable reply may have landed) or a `NetworkError` (`maybe_sent`, D-410) to the dialog's line. The new `ScanOutcome.RECORDED` and `NOT_RECORDED` are neutral (no fill of their own), with `TASK_ALT` and `REMOVE_CIRCLE_OUTLINE`, a light haptic and none. `BUILT_TOOLS` gains `COC`.
- **As built (#761, D-439):** the CoC name search. `ui/coc_search.py`'s `use_find(attendees=, on_pick=)` keeps `Finding(typed, query, clears, opening)` in `use_state` with a `latest` ref (#756); a coroutine effect on `[opening, typed]` sets `query` after `DEBOUNCE_SECONDS` (0.25); `ft.use_memo` runs `conduct.search()` over the directory's rows on `[opening, query, attendees]`; the field's `Ref` is made per opening and per Clear (D-243); a dismissal carrying another opening's token is ignored. `ui/coc_search_sheet.py` is the look: `find_sheet()`, `attendee_row()` (one node, `coc.search.row.<index>`, the count from `coc_review_dialog.count_row()`), `results()` and `find_button()`. `CocTool` gives `ScanScreen` `actions=[find_button(find_reason(...), finder.open)]`, pauses with `SEARCH_OPEN` while it is open, and its `picked(attendee)` awaits `use_review().open()` and sets `posted`. **`ScanScreen(posted=)`** is new: a `Posted(result, serial)` that a tool bumps (`scan_result.post(last, result)`) for a result it got outside `on_badge`; an effect on it shows the result as a scan's (haptics, announcement) while the screen is mounted and on top. Door check and Swag pickup can use it too.
- **As built (#762, D-440):** clearing a result. `ScanScreen(clear_after=, clear_in_background=)` (`ui/scan_clear.py`): `use_clear_after(serial, after, clear)` is a coroutine effect on `[serial, after]` that sleeps `after` seconds from the render that shows a result (when the reply arrived, never when the request left) and then drops that serial's `Shown` from state; `use_on_background(action)` runs one loop per mounted screen that calls the latest action (a ref, #756) each time `Services.background` is set, then waits for `Services.foreground`; Flet cancels both on unmount. Serials come from a ref, so none is reused after a clear. The panel is a live region only while a result shows, so a clear ("Ready to scan") is not said; the age line counts down in words ("Read 3 seconds ago. Clears in 12 seconds"). `result_actions` now takes the `Shown` (result and serial), and `result_note(shown)` puts a tool's line under the panel, outside its live region. `Posted` is handed over once (`take()`), so the tool keeps no copy. The CoC tool passes `clear_after=15` and `clear_in_background=True`, closes the name search on the same `pause` (`Finder.close`), and leaves an open review dialog with its notes. `ScanResult.email` (kept out of `spoken` and the repr) carries the reply's email; `ui/coc_email.py`'s "Show email" (`coc.show_email`) sets the revealed serial and `email_note()` shows it (`coc.email`). The camera area moved to `ui/scan_camera.py`.
- **What stays on the device (CoC, #762, D-56, D-72, O-7):** nothing on disk. The attendee directory stays in `CocTool`'s memory while the tool's screen is mounted (#759). A result, with the email the reply carried, stays in the scan screen's state until it clears: 15 s after it shows, when the app goes to the background, at the next result, or when the tool is left. The notes stay only in the review dialog's field until it closes. None of it is logged. The clear on `pause` may land after the OS has taken its app-switcher snapshot: a secure-screen flag is upstream ([#786](https://github.com/ndonkoHenri/pycon-us-flet/issues/786), U270).
- **As built (#724, D-420):** `ui/scan_feedback.py`. `buzz(haptics, outcome)` plays `HAPTICS[outcome]` (`HapticFeedback` methods, 150 ms apart). `announce(semantics, result)` runs only where `Prefs.announcements` is set, and the panel is then no live region, so a result is said once. `use_wake_lock()` runs `keep_awake(svc)` as the effect's `async` setup: it enables `Services.wakelock` while `Services.foreground` is set and disables it once `Services.background` is set. `Services.background` is new: the lifecycle handler sets it on `pause` and clears it on `resume`, and `close()` sets it. The effect's `async` cleanup disables the lock on unmount. `ScanScreen` calls `use_queue_sheet()` (now `QueueSheet(open, is_open)`) and puts `SyncChip` in its app bar. `paused: str | None` is the tool's reason; the screen's own is `PAUSED_SHEET` while the sheet is open. Either one drops submits and shows as the field's `helper`, and an effect on the pause's end puts the focus back in the field.
- **As built (#763):** the check-in API's payloads, shared by Door check and Swag pickup. `core/check_in.py` is pure: `parse_catalog()` reads `redeemable` into a `Catalog` of `Category` and `Product` (ids as integers; bad entries and products of an unknown category left out), which `door_catalog()` and `swag_catalog()` split with `is_swag()`, Ionic's `/shirt|swag/i`; `product_sort_key(name, year)` sorts sessions by the date in their names in `config.YEAR`, undated names last, and `session_parts()` splits a session's title from its day and time (both in `core/door_sessions.py` since #777); `parse_attendee_products()` reads `fetch_products` into `AttendeeProducts` (`Item`s by category name, alphabetically; the door's dietary fields); `redeem_payload(..., swag=)` builds the `redeem` body in its signed key order (the door's ids as numbers and a missing validator left out, swag's ids as strings and `""`), and `parse_redeem_reply()` reads `RedeemReply(errors, redeemed)`. A reply that isn't the documented object is a `TypeError`, which `check_in_api.py`'s thin fetches (`fetch_catalog()`, `fetch_attendee_products()`, `redeem()`) raise as an `ApiError` (D-120). `redeem()` is Swag pickup's online hand-out; the door's bodies are outbox rows (`core/outbox.admit()`, D-56, D-407).
- **As built (#769):** Swag pickup's hand-out. `swag.look_up(api, badge, *, categories, offer)` stamps the scan's time and, when items are left, hands an `Offer` (badge, `scanned_at`, `AttendeeProducts`) to `offer` and awaits it: the scan screen's handler stays in flight while the sheet is open, so its result is the hand-out's, or the lookup's when the sheet was cancelled (`None`), and `ScanScreen` needs no new parameter. `ui/swag_sheet.py`'s `use_swag_sheet()` is that `offer`: it keeps the sheet's state (`Handing`: the offer, the ticks, `sending`) in a `use_state` mirrored in a ref the handlers read (#756), shows it through `ft.use_dialog`, and resolves an `asyncio.Future` when it closes; an unmount resolves it with None, so a submit never hangs. `swag.hand_out(api, offer, quantities)` sends `redeem_payload(..., swag=True)` once and maps the reply or the error to a `ScanResult` (`NetworkError.maybe_sent` is "Not confirmed", never a resend, D-57, D-410).
- **As built (#764, D-433):** Door check's route and session picker. `core/door_sessions.py` is pure: `door_sessions(catalog, category, year)` turns a category's products into `DoorSession(id, title, when, day, time)` in `product_sort_key()`'s order (an undated one keeps its whole name, no day), `by_day()` groups them under their day with the undated ones last under None, `filter_sessions()` keeps those whose folded title or day and time hold every word (D-46), and `choose_session()` and `choose_all()` make the `DoorChoice(category_id, product_ids, label, all_sessions)` that `to_stored()` and `from_stored()` keep in `staff_door_session()`'s key. `door_choice.py` fetches the catalog's door part (`fetch_door_catalog()`) and reads and saves the choice. `ui/staff_picker.py` holds what the sponsor and session pickers share: `use_fetch(fetch, what=)` (a spinner, then the value, or failed, with Retry), `use_pick(save)` (`Picking(pick, cancel)`: a save then a go-back while mounted and on top, `say_if_unsaved` otherwise), `picker_page()`, `choice_row()`, `spinner()`, `not_loaded()`, `no_match()`, and for the scan screens `Reading` and `use_arrival(owner)` (a token new at each change of location, which a read carries so the tool can pause until the read for this arrival lands; #873, #887); their `context_chip()` and `tool_button()` are `ui/tool_controls.py`'s (#777). `screens/staff_door.py`'s `DoorTool` reads the choice for the owner at each change of location, opens the picker once per visit without one, and keeps `ScanScreen` paused, with its chip once one is chosen, until #765 loads the attendee list.
- **As built (#765):** the door's attendee list. `core/admission.py` is pure: `Attendee(code, name, dietary, has_allergy, allergy)` and `Inventory(quantities, attendees)` (each code's quantity bought per product id, and its details); `merge(inventory, product_id, reply)` returns a new inventory with one `INVENTORY` reply folded in, summing quantities per code and product, details sticky (a missing or empty one keeps the earlier row's), a row without a non-empty code or a positive integer quantity left out, and a reply that isn't a list a `TypeError`; `attendee_count()`. `door_inventory.load_inventory(api, product_ids, on_progress)` sends one call per product with `asyncio.gather` (a repeated id once), tells `on_progress(done, total)` as each finishes and returns `Loaded(inventory, failed)`: a product whose call raised `NetworkError` or `ApiError`, or whose reply isn't a list, is in `failed` and the others are kept (D-120); it logs nothing. `screens/door_preload.py`'s `use_preload(owner, choice)`, which `DoorTool` calls on every render (D-70), loads it in a coroutine effect on `[owner, product_ids, tries]`, so Flet cancels the load on unmount and when the session changes; it holds `Preload(key, done, total, loaded)` in `use_state`, keyed by the account, the ids and the try, so a late result for another key never shows, and a mounted ref drops one after unmount; Retry bumps the try with a functional update. While loading, `ScanScreen` is paused with `status_words()`; `status_line()` under the chip is one live region (`door.preload`; announced once where `Prefs.announcements`, iOS). The list is never in a store, storage, the outbox or a log (D-56).
- **As built (#766, D-441):** door admission. `core/admission.py` adds `Admission(known, quantities, already)` and `decide(inventory, code, product_ids, kept)`: `known` when the code bought one of the session's products (`quantities`, in the session's order), `already` when one of `kept` (the account's door rows for the code, every status, from `OutboxDb.door_rows(owner, code)` on the `outbox_key` index) covers one of them (`admitted(row)` reads a row's `product-redeem-<id>` keys); `redeem_errors(row)` reads a synced door row's reply errors. `door_check.check_in(db, staff, kick, api, badge, *, owner, session, product_ids, inventory, clock)`, given to `ScanScreen` as a `functools.partial` built on each render of `DoorTool` (the latest list and choice), reads the kept rows (None: "Not checked in", D-120), decides, looks an unknown badge up (`look_up()`: `fetch_attendee_products(door=True)`, the items left to redeem of the session, a 404 "Not registered", a `NetworkError` "Can't check this badge"), then enqueues `functools.partial(admit, …)` with `redeem_payload(code, badge.door_validator, now, quantities, swag=False)`, the visit's uuid (`use_memo` on mount) as the session and no sponsor, calls `Staff.update_counts()` and `kick_sync()` and returns at once (D-441). A duplicate only reads, so it bumps no revision. `ScanScreen` drops a result after unmount or off the top View. `ui/queue_rows.row_tile()` shows a refused reply as "Confirmed · Already redeemed" with `WARNING_AMBER` and the messages.
- **As built (#767, D-442):** door tags and headcount. `core/badges.py` adds `Tag(text, warning=False)` and `ScanResult.tags` (empty by default, so the other tools are unchanged; `spoken` says them after the title, one line, "Allergy: peanuts. Vegetarian."). `core/admission.tags(attendee)` gives the allergy as a warning ("Allergy: x", or "Allergy") then the diet with a capital; `door_check.check_in()` attaches them to "Checked in" and every "Already checked in", from the inventory's `Attendee` or, for a badge off the list, one built from the lookup's `AttendeeProducts` (`look_up()` returns `(quantities, Attendee)`). `ui/scan_result.tag_row()` draws them under the name (`tag_colors()`: a warning swaps the card's label and fill, a plain chip keeps them; every chip has a 1 dp edge in the label's colour). `core/admission.headcount(rows, product_ids)` counts the distinct `key`s among door rows whose `admitted()` products overlap the session's; `screens/door_headcount.py`'s `use_headcount(owner, product_ids)` memoises `read_headcount()` (`OutboxDb.rows(owner, every status)`; 0 without products, None on a failed read) on `[owner, ids, Staff.revision]`, called on every render of `DoorTool` (D-70), and `headcount_line()` draws it under the session chip (`door.headcount`).

---

## 13. Capability gating (D-63, D-64)

```python
# src/pycon_us/capabilities.py
"""Which optional native pieces this build can use (D-63).

An extension counts only in a packaged build that bundles it. The `flet run` companion app runs Python
on the laptop and is never embedded, so it always gets the interim and never receives a control it
lacks. Core Flet gaps are not detected at runtime: a PR that bumps the pinned Flet swaps the interim (D-64).
"""
from importlib.util import find_spec

from flet.utils import is_embedded


def available(module: str) -> bool:
    return is_embedded() and find_spec(module) is not None


SECURE_STORAGE = available("flet_secure_storage")
PERMISSIONS = available("flet_permission_handler")
REMINDERS = available("flet_notifications")          # E3: the monorepo's flet-notifications (flet-dev/flet#6999)
SCANNER = available("flet_barcode_scanner")          # E1, not published yet: module name is a placeholder

ALL = (                                              # each with its display name (D-271)
    ("Secure storage", SECURE_STORAGE),
    ("Permissions", PERMISSIONS),
    ("Reminders", REMINDERS),
    ("Badge scanner", SCANNER),
)
```

| Constant | Owner module | Interim |
|---|---|---|
| `REMINDERS` (E3) | `services/reminders.py` | "Not available in this build", Now's next-session card, in-app Banner, `.ics` with an alarm on iOS only (D-60, D-272) |
| `SCANNER` (E1) | `services/scanner.py` | manual and HID entry (always available anyway) |
| `SECURE_STORAGE` | `services/credentials.py` (`secure_storage()`, `CredentialStorage`; in the build since #684) | credentials kept in memory for the session, so a restart signs out (the companion app, D-63) |
| `PERMISSIONS` | `services/__init__.py` builds `Services.permissions`; reminders and the scanner use it | `Services.permissions` is `None`, and its users keep their own interim (the companion app, D-63) |

`is_embedded()` is `FLET_PLATFORM is not None`, set by the build template, not by `flet run` (F14). The Developer screen shows these constants read-only through `ALL`, which the diagnostics text also lists (D-73, D-271); interims are exercised through `flet run` and the companion app, which is never embedded. `tests/test_capabilities.py` reloads the module with `FLET_PLATFORM` unset and every extension findable, and gets all four `False`; a unit test per owner module checks its interim when not embedded.

---

## 14. Notifications and reminders (P2; D-58..D-62)

### 14.1 Plan, then apply

```python
# src/pycon_us/services/reminder_plan.py (excerpt; Scheduler is services/reminders.py's)
MAX_PENDING = 60                         # iOS keeps 64 pending and drops the soonest beyond (D-222)


@dataclass(frozen=True)
class Reminder:
    """One local notification to schedule."""

    id: int
    at: datetime
    title: str
    body: str
    route: str                           # opened on tap, e.g. "/my-schedule/session/42"


def plan(data: ConferenceData, favorites: Iterable[str], settings: ReminderSettings,
         moments: Iterable[EventReminder], now: datetime, *, zone: tzinfo,
         use_24h: bool) -> list[Reminder]:
    """Every future reminder the user asked for, soonest first, at most MAX_PENDING (pure)."""
    # moments: content.toml's sign-ups and year_moments.keynote_moments(data, ...) (D-274)
    wanted = [m for m in moments if settings.wants(m.category) and m.at > now]
    # One per saved session still in the feed, session_lead min before its shown start,
    # "Starts at 10:30 AM · Room 103ABC", route /my-schedule/session/<quoted id>.
    saved = _session_reminders(data, favorites, settings, now, zone, use_24h=use_24h)
    ...  # a saved keynote keeps the earlier of its reminder and its moment (the moment on a tie)
    return sorted(reminders, key=lambda r: (r.at, r.id))[:MAX_PENDING]
```

`Scheduler.apply(plan, *, exact)` calls `cancel_all_pending()` (never `cancel_all()`, which clears the shown ones too) and then `Notifications.schedule(id, when=at, title, body, payload=route, schedule_mode=...)` for each reminder, `EXACT_ALLOW_WHILE_IDLE` when Android allows exact alarms and `INEXACT_ALLOW_WHILE_IDLE` otherwise (D-221, D-222, D-389). It is idempotent, logs its failures and never raises them (an exact alarm refused is scheduled inexact; D-120). The extension (`flet_notifications`, in the build since #446) is imported only in `services/reminders.py`: `start(permissions)` builds the session's `Scheduler` in `Services.create()` (`Services.reminders`), or returns `None` without E3, as in the companion app, where the interim applies.

```python
# src/pycon_us/reminder_schedule.py (excerpt)
def use_reminder_schedule(svc, conference, favorites, change_log, prefs) -> None:
    """App's hook: apply at start, then at each watched change, until the session closes."""
    ...  # subscribes to the four stores: WATCHED = {"version", "ids", "reminders", "batches"}
    scheduler.request()                  # the start's apply, once prefs.loaded
    await scheduler.keep_applied(planned, svc.closed)   # one apply at a time; the newest wins
```

`on_resume()` calls `svc.reminders.request()` too, which brings back what a force-stop or the OS cleared. `keep_applied()` re-reads `can_schedule_exact_alarms()` before each apply (on Android it warns when `flet_permission_handler`'s `SCHEDULE_EXACT_ALARM` disagrees, D-220) and plans at `clock.real_now()`, never the fake clock: the OS fires at real instants (D-389). `reminder_id()` is the numeric session id, or `1_000_000 + crc32(id) % 1_000_000` for synthetic ids; a test checks a year's plan for collisions with the 8000–8099 event ids (8000–8049 the hand-written sign-ups, 8050–8099 the keynotes' moments, derived from the feed at each plan so a moved keynote moves its moment, D-274). Each moment opens its own page: a sign-up its page (`/more/lightning-talks`), a keynote its session (`/schedule/session/<id>`). Taps open `route` (§5.6), cold start included: `start()` gives `Notifications` its `on_tap` in the constructor (F246), and `keep_applied()` also re-reads `are_notifications_enabled()` into `Scheduler.enabled` before each apply, for the Banner's rule (D-396). Spike S6 ([verdict](spikes/06-reminders.md)) showed killed-app delivery, reboot and taps working through the extension's own receivers and iOS delegate (D-220).

### 14.2 Interim while the app is open

`App` owns one `ft.use_dialog` slot for an in-app reminder `Banner` ("Dismiss", "Open") through `ui/reminder_banner.py`'s `use_reminder_banner()`, called before the boot gate and shown once it opens (#428). Its state is the module's pure `due_session(data, favorites, now, dismissed)`, asked only while `os_reminds(scheduler, settings)` is false: E3 schedules, the OS shows the app's notifications and session reminders are on hide it, since the OS reminds then (D-396): the soonest saved session still in the feed whose shown start is within `BANNER_LEAD` (10 min) and not yet reached, with its minutes rounded up ("Typing deep dive starts in 9 min · Room 103ABC"). It is asked again by a foreground-only 60 s loop (`svc.run_every`, D-175), and at once when `Favorites`, `Conference` or `Prefs` notify in the foreground (`Observable.subscribe`, held by the loop's task), so an unsaved or removed session goes without waiting for the tick; an equal answer sets no state, so `App` re-renders at most once a minute while a Banner shows. Open navigates to `/my-schedule/session/<id>`, which the Router builds over My schedule, so Back returns there; Dismiss and Open remember the id until the app restarts, and the Banner closes by re-render, never by `page.pop_dialog()` (which could close a newer dialog). Flutter's `ScaffoldMessenger` sits above the Views, so navigating keeps it (F118).

### 14.3 Permissions (D-61) and calendar (D-62, D-272)

Permissions are asked in context after a one-sentence primer: notifications on the first favourite or the first reminder switch, the camera on the first staff scan, never at launch. After a denial, Settings › Reminders shows a card with "Open settings" (`await svc.permissions.open_app_settings()`), and nothing else in the app prompts (D-401). Notification permission is requested through E3's `request_permissions()` on both platforms; `flet-permission-handler` checks status, opens settings and handles the camera (D-61, F17). The notification status is `Scheduler.access()`'s: the handler's on Android, E3's `are_notifications_enabled()` on iOS, where the handler always says denied (F245); `request_permission()` asks. `ui/reminder_primer.py`'s `ask()` is the primer flow: the star handler (`ui/favorite.py`) calls it after a saved add while `ReminderSettings.primer` is `unasked`, and it shows the sheet only while the OS can still ask; Allow, once granted, sets the session lead to 10 minutes when it was off, which the scheduler applies (D-395). Settings' live section (`screens/settings_reminders.py`, D-401) reuses `ask()` for its session switch while the primer is not `accepted`, picks its card with `card_for()`, and re-reads the status whenever `Scheduler.watch()` reports that a read before an apply (so on every resume) changed `enabled` or `exact`; its Alarms & reminders card calls `Scheduler.request_exact()`.

`core/ics.py`'s `calendar_file(sessions, *, year, now, alarm=ALARM)` builds `.ics` bytes (UTC times from the start the app shows, a `UID` of `<year>-<id>@CALENDAR_DOMAIN` stable across refreshes, escaping, 75-octet folding between characters, a `VALARM` at the lead time: `ReminderSettings.calendar_alarm`, the session reminders' lead while they are on, else 10 min; D-268, D-401) for one session or all of My schedule in the Schedule's order (D-62). The share sheet reaches no calendar on either platform (P2-04, [`spikes/10-ics-share.md`](spikes/10-ics-share.md)), so `services/calendar.py`'s `add_to_calendar(svc, slug, data)` hands the bytes to the calendar by platform (D-272): on iOS a stdlib `ThreadingHTTPServer` on `127.0.0.1`, port 0, serves `/<slug>.ics` as `text/calendar` while `await svc.launcher.launch_url(url, mode=ft.LaunchMode.IN_APP_BROWSER_VIEW)` brings up iOS's calendar sheet (the call raises although the sheet shows, so a `threading.Event` set by the server's GET, read once the call returns or raises, is the success, F91; the server stops then, 60 s at most, off the event loop); on Android `await svc.file_picker.save_file(file_name=f"{slug}.ics", src_bytes=data)` saves it where the user picks and a SnackBar says to open it from the Files app, where Google Calendar imports it without the alarm. It says every outcome itself, on the View the user is on (D-210), and returns nothing, as `open_link()` and `share_text()` do; the server logs each request's method, path and status. Opening a local file in the app that handles its type *(not in Flet yet: U71)* makes Android one tap; native add-to-calendar *(not in Flet yet: E4)* comes later.

---

## 15. Theming (D-22..D-28, D-33, D-34)

```python
# src/pycon_us/theme.py (excerpt); the HC schemes are theme_hc.py's (D-265)
SEED = "#3B3EA9"
LIGHT_SCHEME = ft.ColorScheme(primary="#3B3EA9", on_primary="#FFFFFF", secondary="#680579", on_secondary="#FFFFFF",
                              tertiary="#A1009A", on_tertiary="#FFFFFF", ...)   # + containers and surface text roles
DARK_SCHEME = ft.ColorScheme(primary="#BFC1FF", on_primary="#1F2189", secondary="#F4AEFF", on_secondary="#52005E",
                             tertiary="#FFACEB", on_tertiary="#5E0058", ...)
# theme_hc.py: every one of the 46 roles, by hand (ux.md §3.2)
HC_LIGHT = ft.ColorScheme(primary="#4A0072", on_primary="#FFFFFF", surface="#FBFAF6", on_surface="#1A1D24", ...)
HC_DARK = ft.ColorScheme(primary="#FFD60A", on_primary="#0B0F17", surface="#0B0F17", on_surface="#F5F5F0", ...)
THEME_MODES = {"system": ft.ThemeMode.SYSTEM, "light": ft.ThemeMode.LIGHT, "dark": ft.ThemeMode.DARK}


def build_theme(*, dark: bool, high_contrast: bool) -> ft.Theme:
    """The one Material 3 theme, identical on Android and iOS (D-10, D-22)."""
    if high_contrast:                                   # THEME-04, THEME-05
        scheme = HC_DARK if dark else HC_LIGHT
    else:
        scheme = DARK_SCHEME if dark else LIGHT_SCHEME
    return ft.Theme(
        color_scheme_seed=SEED,
        surfaces=ft.ThemeSurfaces.NEUTRAL,
        color_scheme=scheme,
        font_family="packages/roboto_fonts/Roboto",         # D-26, D-105: the bundled font package
        appbar_theme=ft.AppBarTheme(center_title=False),
        page_transitions=ft.PageTransitionsTheme(
            android=ft.PageTransitionTheme.PREDICTIVE,        # D-11, D-148
            ios=ft.PageTransitionTheme.CUPERTINO,             # keeps the iOS edge swipe
        ),
        system_overlay_style=overlay_style(dark=dark, high_contrast=high_contrast),  # D-12, D-113, D-265
    )
```

- `high_contrast=True` returns the HC scheme with everything else unchanged: font, transitions, tiles and the bars' icon brightness (THEME-04, THEME-05, D-265). It also adds `card_theme` (`theme_hc.py`'s `hc_card_theme()`): elevation 0 and a 1 dp side in the scheme's `outline`, named as a hex (U64), so every card is flat with a border (THEME-06). `build_tokens(dark=..., high_contrast=True)` returns `HC_LIGHT_TOKENS` or `HC_DARK_TOKENS`, whose `high_contrast` flag tells components to draw lines where the standard schemes draw fills or shadows: `AppScaffold` puts a 1 dp `OUTLINE` divider above a tab root's `NavigationBar` (D-285).
- `overlay_style(*, dark, high_contrast)` returns the `Theme.system_overlay_style` (D-12): light status- and navigation-bar icons on dark schemes, dark icons on light ones, a transparent status bar, a navigation bar in the `NavigationBar`'s colour (`SURFACE_CONTAINER`, D-151) and navigation-bar contrast **not** enforced (D-113), so Android's 3-button icons sit on the `NavigationBar`'s colour and never on a dark scrim (#311), also below Android 15, where the app is not drawn under the bar. Flet resolves a role in the style against the seeded, neutralised scheme, before `color_scheme` applies (`parseTheme` in `utils/theme.dart`), so the HC style names its scheme's `surface_container` as a hex instead (`#FBFAF6` / `#0B0F17`; D-265). For the same reason `build_theme()` names `scaffold_bgcolor`, `canvas_color`, `card_bgcolor` (`surface`) and `divider_color` (`outline`) from the scheme it shows: Flet builds `ThemeData` from the seeded scheme and applies the overrides with `copyWith`, which re-derives none of them (U64, #483). S1 checked it with 3-button and gesture navigation, in light and dark; #71 again on Android 14 and 16, including a dark-mode switch while the app runs.
- `apply_theme(page, prefs)` sets `page.theme` and `page.dark_theme` from `build_theme()`, `page.theme_mode` from `THEME_MODES[prefs.theme]`, then `page.update()`.
- Flet builds `ColorScheme.fromSeed`, neutralises surfaces, then applies our overrides (F9): light and dark set the brand roles and their containers, each with its `on_*` partner, plus `surface`, `on_surface` and `on_surface_variant`, which repeat Flet's neutral ramp so the contrast test sees them; HC overrides every role (`theme_hc.py`), with `surface_container*` = `surface`; `tests/test_high_contrast.py` checks that none is unset and that Flet's `parseColorScheme` reads each one. `Prefs.high_contrast_on` is `"on"`, or `"system"` with the OS flag (iOS, Android 34+; re-read on resume, F13); `Prefs.dark` resolves `"system"` with `os_dark`.
- **Values** come from `docs/ux.md` and are mirrored in `theme.py`: full HC schemes (P2); `Tokens` (D-24: `live`, `warning`, `success`, `favorite`; `build_tokens(*, dark, high_contrast)` picks them, `App` provides them through `TokensCtx` and screens read them with `use_tokens()`, D-150); track badges (#80, D-25, D-174: `Tokens.tracks` maps each track key of the registry to a `BadgeColors(text, fill)`, read through `Tokens.track_badge(key)`, which gives a key the palette lacks the neutral grey; `Tokens.spanish` is the tonal pair `#FFD7F3` / `#5E0058` in light, inverted in dark; `Tokens.registration` has no fill: an outline and label in `error`, which both schemes therefore declare with the seed's own values; `Tokens.new_track` has none either, an outline and label in `primary` (D-199); in HC every badge is outlined 1.5 dp, `BadgeColors.border_width`, in `on_surface` but for those two, D-285; `BadgeColors` and the palette are `theme_badges.py`'s). `ui/badges.py`'s `TrackBadge(label, colors)`, `session_badges(session, info, tokens)` and `badge_row()` are plain builders given the colours, so a memoised row draws the scheme it receives as a prop (D-150). `tests/test_theme.py` checks every text/background pair in light and dark, and `tests/test_high_contrast.py` in HC at 7:1 (with text on every surface at 7:1 and both outlines at 3:1), the text roles and text tokens on every surface of Flet's neutral ramp, each tonal badge's label on its fill and the outlined badge's label on every surface; in HC, every text token and outlined label at 7:1 on every surface.
- **Markdown:** `MARKDOWN_STYLE` is the one `ft.MarkdownStyleSheet` of D-116, passed to every `ft.Markdown(md_style_sheet=...)`. Its colours are scheme roles (`PRIMARY`, `ON_SURFACE`, `SURFACE_CONTAINER_HIGHEST`, `OUTLINE`), resolved against the theme on screen, so one constant serves every scheme; every text style in it names its colour (F28), its font family and, for links and strike-through, its decoration colour (D-152).
- **Type** (D-26, D-33): only the M3 scale (`ft.Text(theme_style=ft.TextThemeStyle.TITLE_MEDIUM)`), no fixed heights around text, reflow at 200 %. **Roboto:** `page.fonts` takes one static file per family, so 500/700 would be synthetic; declare the family's 400/500/700 files through `[tool.flet.flutter.pubspec]` (F18), verified in S5 (D-26).
- **Icons** (D-27): Material Icons only, outlined unless selected; icon-only buttons have a tooltip (their accessible name), merged into the button's node (`merged()`, D-234). **Motion** (D-34, D-173): M3 durations, each passed through `prefs.motion_ms(ms)`, which gives 0 under reduced motion; pulses are static then. The theme crossfade stays: a colour fade, not motion (D-173). Route transitions stay the platform's (D-173). **iOS pins** (D-10): bundled font, `center_title=False`, Material back arrow, never `adaptive=True`; the Cupertino transition and bounce scrolling stay native.

---

## 16. Errors, logging and diagnostics (D-71, D-72)

### 16.1 Expected failures at explicit boundaries

| Failure | Boundary | Becomes |
|---|---|---|
| Feed: offline or timeout | `Conference._refresh` | `problem = "offline"`; data kept |
| Feed: HTTP error, bad JSON, nested too deep, `FeedError` | `Conference._refresh` | `problem = "server"`; data kept; logged |
| Corrupt cache | `Conference.load_local` | cache deleted, snapshot shown, logged |
| Storage read or write fails | `services/storage.py` | logged; `False` or `None` returned; the previous file and the data in memory kept (D-120) |
| Unreadable preference | `Prefs.load` | its default; logged (bad year data is a build bug: the loader test fails) |
| Share, URL, clipboard failure | the handler (`ui/links.py`'s `open_link()` for links, D-182, and `copy_text()` for every copy, `copy_contact()`'s included, D-263; `ui/share.py`'s `share_text()` for a text, D-206) | SnackBar "Couldn't open the link" / "Couldn't copy the phone number" ("…the password": the caller's words) / "Couldn't open the share sheet"; logged with the link's kind (a copy: the same words) and the error's class, never its target or value nor the error's text |
| Permission denied | permission flows | `Banner` with "Open settings"; the task continues |
| `NetworkError`, `ApiError` (P3) | `Account`, `SyncWorker`, staff screens | inline errors, queued rows, "Retry failed" |

### 16.2 Unexpected exceptions: `report_errors`

An exception in an event handler (or a sync effect) ends the session; one in an async effect reaches only asyncio (F4). Until Flet makes handler errors non-fatal *(not in Flet yet: U15)*, handlers and effects are wrapped:

```python
# src/pycon_us/services/errors.py (excerpt)
def report_errors(fn):
    """Log an unexpected exception from a handler or effect and tell the user, instead of ending the session."""
    if inspect.isgeneratorfunction(fn) or inspect.isasyncgenfunction(fn):
        raise TypeError(...)                  # Flet would never iterate it through a wrapper
    where = f"{fn.__module__}.{fn.__qualname__}"
    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)                  # Flet reads iscoroutinefunction and the parameter count
        async def run_async(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except Exception as error:        # CancelledError is a BaseException: it propagates
                logger.exception("Unexpected error in %s", where)
                _tell_user(error)
                return None

        return run_async

    @functools.wraps(fn)
    def run(*args, **kwargs):
        ...                                   # the same, without await


def _tell_user(error: Exception) -> None:
    detailed = _details or not is_embedded()   # _details: show_details(), Developer unlocked (D-187)
    text = f"{MESSAGE}: {type(error).__name__}: {error}" if detailed else MESSAGE
    try:
        say(ft.context.page, text)            # the floating SnackBar of every plain message
    except Exception:                         # no page, or a replaced session (F30): log only
        logger.warning("Could not show the error message", exc_info=True)
```

A last-resort net, not error handling (§16.1). Every handler and effect setup is wrapped, sync or async; `bootstrap()`'s loading steps keep their own `try` so the gate opens anyway (D-161, D-163). Details show when not embedded, and in a packaged build once Developer is unlocked (`show_details()`, set by `bootstrap()` from the stored unlock and by About this app when it unlocks; D-187); an AST test (`tests/test_errors.py`) checks that every function nested in `main.py`, `routes.py`, `screens/` and `ui/` is wrapped; review checks the rest (`app.py`; D-71). An async effect needs the wrapper most: its exception otherwise reaches asyncio only when its task is released, which for a mounted effect with `[]` dependencies is never (F37).

### 16.3 Logging

`setup_logging()`, called once when `main.py` is imported (a second call returns at once), puts one stderr handler on the root logger (`HH:MM:SS.mmm LEVEL logger: message`) at INFO, or at `FLET_LOG_LEVEL` (`flet run -vv`), with `httpx` and `httpcore` at WARNING because their INFO line is the request URL; packaged apps tee stderr to logcat or the unified log and to `console.log` (F14). There is no asyncio exception handler of our own: the default one already logs through `logging` (D-163). Feed processing logs its duration (D-80). **Never log** secrets, keys, signatures, emails or badge codes. `report_errors` logs an exception's message verbatim, so the P3 API layer raises exceptions whose messages hold no URL, token or badge code, and never lets httpx's `HTTPStatusError` (its message is the full URL, query included) escape (D-163). "Share log" shares `ft.ShareFile.from_path(await svc.paths.get_console_log_filename())`. The plain diagnostics text that goes with a report is `services/diagnostics.py`'s (D-271): `gather_facts()` reads typed `Facts` from the page (`get_device_info()`, width, platform), the stores and the build, and the pure `diagnostics_text()` writes one `Name: value` line per fact, every value on one line with its emails and URLs replaced, as the log's formatter does (D-196). The facts hold a flag for the custom feed URL and a count of saved sessions, never the URL or the ids. No Sentry, no analytics.

---

## 17. Developer screen (D-73)

`/more/developer` (`screens/developer.py`, its fake-clock pickers in `screens/developer_clock.py`, its option fields in `screens/developer_ui.py`, D-232): always reachable when not embedded; in packaged builds, 7 taps on the version row in About this app (`screens/about_app.py`, `/more/app`), which set `dev.unlocked` for good (D-187). Fake clock (`dev.fake_now`, its start; it runs forward, and each start of the app begins there again), feed URL override (`dev.feed_url`, from the next refresh), mock API URL (`dev.mock_api_url`, `screens/developer_api.py`'s Mock API section: Save, Clear and Check mock connection; enables P3, D-51, #668), capability flags (read-only), and the Data section (`screens/developer_data.py`; its rows, outcome line and confirmations in `screens/developer_ui.py`; D-198): Refresh now, Clear cached feed, Share log and Reset app; then show Welcome again (P2); a Reminders section of test reminders, one per kind (`screens/developer_reminders.py`, scheduled by `Scheduler.schedule_test()`, D-402; P2), clear synced staff records (P3). Destructive actions are confirmed with what is lost. Reset app (`reset_app()`) removes every `pycon.` key, the feed cache and the change log (`changes-<year>.json`, D-255), cancels a running refresh, resets `Conference` (the bundled snapshot), `Prefs`, `Favorites` and `ViewMemory` in memory, starts a quiet refresh and goes where a fresh start goes (`start_target()`, D-143: Now; Welcome from P2): the app is as after a fresh install without a restart.

**How the options take effect (P1, D-187).** `Prefs` reads them from `dev` (`fake_now`, `feed_url`, `developer_unlocked`, `developer`). Process state follows them at two moments: `bootstrap()`'s `start_developer_options()` after the settings load, and the Developer screen's Apply or Reset, which set the clock (`clock.start_fake_clock()`) and the feed URL (`Conference.set_feed_url()`) **before** `prefs.save(dev=...)`. Any change of the feed URL once the feed has loaded deletes the cache and the change log there, since they hold the old URL's feed (D-255; at a start the stored URL is restored before the load and deletes nothing); a refresh still running from a URL left writes nothing, and a change starts no refresh: the next one, or Refresh now, uses the new URL (D-244). The save assigns `Prefs.dev`; `App` subscribes to `Prefs`, so the whole tree re-renders, as on a theme change (D-150), and every screen reads `clock.now()` again; the tab roots under the Developer stack mount afresh when the user switches to them (D-142), and the status strip's minute tick (D-175) keeps the age current. A memoised component that shows the time (P1's Schedule, D-153) takes the minute it shows as a prop, so a clock change reaches it too.

---

## 18. Spikes this design depends on, and the API ledger

| Spike | Confirms |
|---|---|
| S1 | **Done** (`docs/spikes/01-packaged-runtime.md`): data dir survives updates (D-108); `tzdata`, `httpx`, `sqlite3`, SecureStorage on device; parsing stays on the loop (D-109); overlay style and insets (D-113). Page handlers firing without `page.update()` moved to S4 |
| S2 | **Done** (`docs/spikes/02-day-list.md`): memoise the whole path, day list → slot → row (D-153); day lists stay lazy and today's builds every slot (`cache_extent`), since a `ListView` with or without `build_controls_on_demand` builds only near the viewport (D-154, F32); Jump to now is one keyed `scroll_to` (D-155); the shown day renders first (D-156); controlled text fields (D-157); a gutter that grows with the text (D-158); the interaction-latency baseline (D-159). iPhone release numbers in #121 |
| S3 | **Done** (`docs/spikes/03-html-markdown.md`): the converter covers both feeds' 17 tags with no text change; escaping (D-115) and the style sheet (D-116); E5 cut (D-117) |
| S4 | **Done** (`docs/spikes/04-router-back.md`): the drill shape and per-level params (D-141); every pop through our `on_view_pop` (D-141); D-17's root rule (D-142); one root View key (D-142); the bar on roots only (D-144); `ViewMemory` per process with the start route restoring the location (D-143); a replaced session stops its work from `page.on_close` (D-147); page handlers without `page.update()` (D-147); transitions (D-148). The iOS edge swipe is held for #121 |
| S5 | **Done** (`docs/spikes/05-build-and-ship.md`): the pinned Flet 1.1 build (D-104); Roboto weights through a font package (D-105). Deep links were not part of it: one common `[tool.flet.deep_linking]` table since D-269, checked by `tests/test_deep_linking.py` |
| S6, S7, S8 | E3 reminders; floor plans in `InteractiveViewer`; E1 scanning |

**Not in Flet yet, and the interim:** sticky headers (U2 → time gutter per slot); absolute `InteractiveViewer` transform (U3 → highlight plus `reset`/`zoom`/`pan`); `use_route_search` (U9 → `use_query()`); Router Back inside a modal sub-chain (U18 → our `page.on_view_pop` with `parent_of()`, D-19); Back that closes a dialog open over a View before the View (U33 → an `on_confirm_pop` on every pushed View, D-208); a shell bar outside the `Navigator` (U23 → the bar on roots only, D-144); unmounting a replaced session (U24 → `page.on_close` stops our loops, D-147); a typed brightness event and the boot screen kept until `main()`'s first patch (U25 → read `page.platform_brightness`, and `before_main` paints the default View, F35, F36); `AppBar.bottom` (U10 → day tabs as the first body row); non-fatal handler errors (U15 → `report_errors`); `PageMediaData.text_scale_factor` (U16 → fluid layouts); an accessibility change event (U17 → re-read on resume); barcode scanner (E1 → manual and HID entry); native calendar (E4 → `.ics` through the in-app browser on iOS and a saved file on Android, D-272; U71 → one tap on Android); HTML (`html_md`; E5 cut, D-117); LaTeX always on in `Markdown` (U21 → escaping, D-115); a style sheet that replaces the theme's styles (U22 → explicit colours, D-116); multi-weight families in `page.fonts` (→ pubspec fonts).

---

## 19. Discrepancies with PLAN.md and decisions.md

This file follows the right-hand column; each open row needs a `needs-decision` issue or an amendment in the implementing PR. Row numbers are stable ids (other docs cite them) and are never reused. Resolved in the decisions record on 2026-10-11, so retired: #1 search (D-19), #2 the `plan/<plan>` drill kind (§M), #3 the change-log path (§M; matrix NEW-04), #4 Roboto (D-26), #5 positions in `ViewMemory` (D-18), #7 the P3 storage keys (§M), #8 no parser-version key (D-47), #9 `services/api.py` from P0 (PLAN §5), #10 the mock's `transport.py` and `badges.py` and the QR library (D-50, D-75, §M). Resolved by S4 on 2026-10-12: #6 the bar on detail Views (D-144, #149: roots only).

No rows are open.
