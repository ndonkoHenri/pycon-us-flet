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
 src/main.py   page.on_view_pop (parent_of), then page.render_views(App)
 app.py        App: Services + stores (once) → boot gate → providers → ft.Router(ROUTES)
 routes.py     tab roots · More pages · search · recursive drill (session/speaker/room/sponsor/plan)
 screens/      one @ft.component per screen, returns an ft.View        ui/  shared components
 state.py      Conference · Prefs · Favorites (+ Account, Staff in P3) · ViewMemory (plain)
 services/     storage · api · reminders · sync · scanner · errors      (Flet services, httpx)
 core/         pure Python, no Flet: feed rules, models, queries, time, slugs, html→md,
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
3. Long-running async effects pass a plain **sync** `cleanup=` (set an Event, cancel a task, or `page.run_task(...)` a coroutine), never an `async def` cleanup: on a dependency change the next setup cancels it before it starts. The previous setup task is cancelled on every re-run, and on unmount only when a cleanup exists (F2).
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
| `src/main.py` | `ft.run(main)`: one `ViewMemory` per process (D-143); logging setup, `page.on_view_pop` (navigates to `parent_of(e.route)`, D-19) set **before** `page.render_views(App, memory)` | P0 |
| `pycon_us/__init__.py` | `__version__`, tested equal to `[project].version` (D-83) | P0 |
| `app.py` | `App`, `bootstrap()`, lifecycle handler, theme effect, boot View (§4) | P0 |
| `routes.py` | `ROUTES`, `Drill`, `Start`, `NotFound`, `drill_href()`, `parent_of()`, `use_query()` (§5) | P0 |
| `state.py` | stores, contexts and `use_*()` hooks; `ViewMemory` (§6) | P0 |
| `config.py`, `theme.py`, `capabilities.py`, `clock.py` | year data (§8); theme (§15); capabilities (§13); `now()` (§7.6) | P0 |
| `core/` | `feed`, `records`, `rules`, `names`, `models`, `timefmt`, `slugs`, `html_md`, `queries` (`days`; P0, the rest P1); `diff`, `ics` (P2); `signing`, `badges`, `admission`, `outbox` (P3) | P0+ |
| `services/` | `Services` bundle, `storage`, `api` (feed fetch P0, signed client P3), `errors` (P0); `reminders` (P2); `sync`, `scanner` (P3) | P0+ |
| `ui/` | grouped by role (decisions §M): `scaffold.py` (`AppScaffold`, `SectionHeader`, `StatusStrip`), `rows.py` (`SessionRow`, `NoticeRow`, `SpeakerRow`, `TimeGutter`, `LinkTile`, `LocationCard`), `badges.py` (`FavoriteButton`, `TrackBadge`), `states.py` (`EmptyState`, `SkeletonList`) | P0+ |
| `screens/` | one `@ft.component` per screen, named after its route (`now.py`, …, `staff_<tool>.py`) | P0+ |
| `data/<year>/`, `src/assets/` | year data (§8); `fonts/`, `icons/`, `maps/<year>/` | P0 |
| `tools/` | `mock_api/` (P3), `update_snapshot.py`, `check_feed.py`, `feed_invariants.py`, `capture_ionic_reference/`, `check_matrix.py` | P0+ |

---

## 4. App, services and bootstrap

### 4.1 `App`

```python
# src/pycon_us/app.py (excerpt)
@ft.component
def App(memory: ViewMemory):
    """Build services and stores once, wait for preferences, then mount the Router."""
    svc = ft.use_memo(lambda: Services.create(memory), [])   # in the page context: Flet registers each service
    conference = ft.use_memo(Conference, [])      # App does not subscribe to it
    favorites = ft.use_memo(Favorites, [])
    prefs, _ = ft.use_state(Prefs)                # use_state subscribes App to Prefs only

    @report_errors
    async def start():
        await bootstrap(svc, conference, prefs, favorites)

    def follow_theme():
        apply_theme(ft.context.page, prefs)

    ft.use_effect(start, [])
    ft.use_effect(follow_theme, [prefs.theme, prefs.high_contrast, prefs.os_high_contrast])

    if not prefs.loaded:                          # boot gate: no theme or filter flash
        return [BootView()]

    def router():
        return ft.Router(ROUTES, not_found=NotFound, manage_views=True)

    tokens = build_tokens(dark=prefs.dark, high_contrast=prefs.high_contrast_on)   # D-150

    return ServicesCtx(svc, lambda: ConferenceCtx(conference, lambda: PrefsCtx(
        prefs, lambda: FavoritesCtx(favorites, lambda: TokensCtx(tokens, router)))))
```

`App` re-renders only on `Prefs` changes; screens subscribe to what they read through `use_conference()`, `use_prefs()`, `use_favorites()` and `use_services()` (one-line `ft.use_context(...)` hooks); `use_tokens()` reads the current scheme's `Tokens`, a plain value that `App` re-provides on every render (D-150). `BootView` is purple `#680579` with the app icon, like the native splash and Flet's boot screen shown while Python starts; both are set in `pyproject.toml` (`[tool.flet.splash]`, `[tool.flet.boot_screen.flet]`; development.md §3), so nothing flashes (SHELL-01). P3 adds `AccountCtx` and `StaffCtx`.

### 4.2 `Services`

`Services` (`services/__init__.py`) is a `@dataclass(frozen=True, eq=False)` built once by `Services.create()` in App's first render: `year` (the bundled `YearData`, §8), `storage` (`Storage(ft.SharedPreferences(), data_dir(), year)`, §9), `memory` (the process's one `ViewMemory`, which `main()` uses for its `on_view_pop` and passes to `App`, §5.3, §6.3), `closed` (an `asyncio.Event` that `close()` sets when the session is replaced, D-147), and the Flet services `ft.UrlLauncher()`, `ft.Share()`, `ft.Clipboard()`, `ft.HapticFeedback()`, `ft.SemanticsService()` and `ft.StoragePaths()`. A Flet `Service` registers with the page when constructed, so screens never construct one. P2 adds `permissions: PermissionHandler | None` (the `flet_permission_handler` instance, built only when `capabilities.PERMISSIONS`; the capability-owning modules use it, e.g. `await svc.permissions.request(Permission.CAMERA)`). P3 adds `api: ApiClient | None` (None unless a mock URL is set, D-51), the outbox database, `wakelock` (`ft.Wakelock()`, for the scan screen) and `ft.Connectivity(on_change=...)`.

### 4.3 Bootstrap (DATA-35)

```python
# src/pycon_us/app.py (excerpt)
async def bootstrap(svc: Services, conference: Conference, prefs: Prefs, favorites: Favorites) -> None:
    """Start in the order that avoids flashes and never waits on the network."""
    page = ft.context.page
    await prefs.load(svc)                     # 1. preferences, accessibility, theme
    await read_accessibility(svc, prefs)
    prefs.os_dark = page.platform_brightness == ft.Brightness.DARK
    clock.start_fake_clock(prefs.dev.fake_now)
    apply_theme(page, prefs)
    await favorites.load(svc)                 # 2. user state
    await conference.load_local(svc.storage, svc.year)   # 3. cache or bundled snapshot, before the first frame
    prefs.loaded = True                       # 4. opens the boot gate
    conference.start_refresh(svc.storage, svc.year)      # 5. background, single flight, not awaited

    @report_errors
    async def on_lifecycle(e: ft.AppLifecycleStateChangeEvent):
        conference.set_foreground(e.state == ft.AppLifecycleState.RESUME)
        if e.state == ft.AppLifecycleState.RESUME:
            await read_accessibility(svc, prefs)              # OS flags are a snapshot (F13)
            age = conference.age()
            if age is None or age > timedelta(minutes=15):        # D-40; #82 owns the triggers
                conference.start_refresh(svc.storage, svc.year)

    def on_brightness(e: ft.PlatformBrightnessChangeEvent):
        prefs.os_dark = page.platform_brightness == ft.Brightness.DARK

    page.on_app_lifecycle_state_change = on_lifecycle
    page.on_platform_brightness_change = on_brightness
    page.on_close = svc.close                 # a new session replaced this one: stop our loops (D-147)
```

- `read_accessibility()` copies `high_contrast` and `reduce_motion or disable_animations` from `get_accessibility_features()` into `Prefs`. Each step has its own error boundary (§16), and `prefs.loaded` is always set.
- P3 inserts after step 2: restore the account, then (not awaited) one `check_features` and one favourites sync (D-54, D-55); start the sync worker when a mock URL is set. S4 confirmed that the page handlers fire and re-render through store writes without `page.update()`, and the lifecycle sequences the app relies on (D-147): background `inactive, hide, pause`; return `restart, show, resume`; Back on Now on Android adds `detach` and ends the session (F29).
- **A replaced session (D-147, F30):** on Android a new session can start in the same process (F26, F29). Flet closes the old one (`page.on_close`) but does not unmount it, so its effect tasks keep running. `svc.close()` sets `svc.closed`; the 60 s ticks, the sync worker and a refresh check it, as well as their own effect's stop event, before they write a store. Only `page.on_close` sets `svc.closed`: a screen unmounts on every tab switch, and its cleanup stops only its own effect. U24 would make this unnecessary.

**Refresh triggers (D-40):** start (always); resume (if older than 15 min); a 60 s ticking effect in Now and Schedule while the app is in the foreground (refresh when older than 15 min, recompute time-dependent views); "Refresh" in the status strip; pull-to-refresh once the pinned Flet has `RefreshIndicator` *(not in Flet yet: U1)*.

---

## 5. Routing and navigation

### 5.1 Router facts we rely on (F6; `components/router.py`)

- With `manage_views=True`, each matched route with a component is one `View`; children are tried before the parent's exact match.
- A `recursive=True` route matches its own pattern once per level, trying its non-recursive children first, and **each level gets its own params** (checked: `/schedule/session/42/speaker/17/session/99` gives three drill levels, `session/42`, `speaker/17`, `session/99`). Params are raw, percent-encoded segments: always `unquote`.
- Default pop navigates to the previous view entry's resolved path and drops the query (what #313 needs).
- **Confirmed in S4** (`docs/spikes/04-router-back.md`): per-level params with quoted ids on both platforms (D-141); every Back key and committed predictive gesture reaches our `page.on_view_pop` (D-141); `can_pop=False` + `on_confirm_pop` on a one-View stack (D-142); roots sharing one `View.route` key switch without a transition (D-142). Back on Now finishes the Android activity, and a relaunch is a new session in the same process (F29).
- **Modal caveat:** with the stock pop handler, when the matched chain contains a `modal=True` route, *every* pop navigates to the modal's base URL, including a pop from a view pushed on top of the modal. An app's own `page.on_view_pop`, set before the Router mounts, receives every pop instead (`router.py` delegates before its modal branch; `e.route` is the popped view's route). We use that for search (§5.4, D-19) until U18 lands.
- `not_found()` output is wrapped in a View. `use_route_location()` is the pathname only (no `use_route_search`, *not in Flet yet: U9*).
- `View.can_pop=False` with `on_confirm_pop` intercepts system Back even on a one-View stack (Dart `view.dart` wraps the View in `PopScope`); the handler must `await view.confirm_pop(...)`, or the pop waits for a timeout.

### 5.2 Route table (D-13..D-21, decisions §M)

The bar has five fixed destinations, the same for every user: **Now · Schedule · My schedule · Map · More** (D-13). `/` opens Now, or Welcome on first run (D-14).

| Path | Screen | Kind | Phase | Features |
|---|---|---|---|---|
| `/` | `Start`: boot View, then the last location of this process (D-143), `/welcome`, `/now` or (P3) the staff start screen | index | P0 | SHELL-03 |
| `/welcome` | `Welcome` | root, no bar | P2 | SHELL-02 |
| `/now`, `/schedule`, `/my-schedule`, `/map`, `/more` | tab roots (`Map` shows Rooms in P1, floors/expo/jobs in P2, `?tab=`) | root | P0–P2 | SCHED-25, SCHED-01..20, NEW-01, MAP-01, SHELL-09 |
| `/schedule/changes` | `ScheduleChanges` | child | P2 | NEW-04 |
| `/search` | `Search` (`?scope=`), opened from Now, Schedule, Map and More | global modal | P1 | NEW-02 |
| `/more/speakers`, `tracks`, `tracks/<slug>`, `keynotes`, `open-spaces`, `lightning-talks`, `sprints` | programme screens (`tracks` doubles as the session-types legend) | child | P1 | SPKR, SCHED-21..24, EVT |
| `/more/app`, `/more/developer` | About this app (minimal in P1, D-73; complete in P2), Developer | child | P1 | DEV-01, DEV-04, DEV-05 (P1); INFO-03 (P2) |
| `/more/sponsors`, `jobs`, `venue`, `wifi`, `help`, `about`, `psf`, `social`, `settings` | sponsors and info screens; Settings | child | P2 | SPON, MAP-09..11, INFO, THEME-01, NOTIF-01 |
| `/more/sign-in`, `account`, `staff/<tool>` (`lead`, `door`, `swag`, `coc`) | account and staff tools (guarded, §12.4) | child | P3 | AUTH, LEAD, DOOR, SHIRT, MASK |
| `<any of the above>/<kind>/<id>` | `Drill` → detail screen | recursive child | P1 | SESS-12, #279 |

**Drill kinds:** `session/<id>` (P1; ids URL-quoted, e.g. `break--2026-05-13T12%3A30%3A00-07%3A00`), `speaker/<id>` (P1), `room/<slug>` (P1; `?highlight=<session id>`), `sponsor/<slug>` (P2), `plan/<plan id>` (P2; floor plans, expo, job fair; `?pin=<room key>`, `?booth=<n>`).

Example: `/schedule/session/42/speaker/17/session/99/room/room-102a?highlight=99` is five Views; Back pops one at a time and, the query being dropped, never re-applies the highlight. Query parameters carry view options only, read once at mount; anything that must survive Back lives in `ViewMemory` (§6.3).

### 5.3 `routes.py`

```python
# src/pycon_us/routes.py (excerpt)
DRILL_KINDS = ("session", "speaker", "room", "sponsor", "plan")
DRILL = ft.Route(path=f":kind({'|'.join(DRILL_KINDS)})/:ident", recursive=True, component=Drill)


def pushed(path: str, component, *children: ft.Route) -> ft.Route:
    """A screen that can open details on top of itself (tab roots, More pages, search)."""
    return ft.Route(path=path, component=component, children=[*children, DRILL])


ROUTES = [
    ft.Route(index=True, component=Start),
    ft.Route(path="welcome", component=Welcome),
    ft.Route(path="search", component=Search, modal=True, children=[DRILL]),    # global modal (D-19)
    pushed("now", Now),
    pushed("schedule", Schedule, pushed("changes", ScheduleChanges)),
    pushed("my-schedule", MySchedule),
    pushed("map", Map),
    pushed("more", More, pushed("speakers", Speakers), pushed("tracks", Tracks), pushed("tracks/:slug", Track),
           pushed("keynotes", Keynotes), pushed("open-spaces", OpenSpaces), pushed("sprints", Sprints),
           pushed("lightning-talks", LightningTalks), pushed("app", AboutApp), pushed("developer", Developer)),
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
        case _:
            return PlanViewer(plan_id=ident)


def drill_href(view_path: str, kind: str, ident: str) -> str:
    """The URL that pushes one detail level on top of the current View."""
    return f"{view_path.rstrip('/')}/{kind}/{quote(ident, safe='')}"


def page_paths(routes: list[ft.Route], prefix: str = "") -> set[str]:
    """Every page path in the table (`/more/tracks`, `/more/tracks/:slug`, ...), drill excluded."""
    paths = set()
    for route in routes:
        if route is DRILL or route.path is None:
            continue
        path = f"{prefix}/{route.path}"
        paths |= {path, *page_paths(route.children or [], path)}
    return paths


PAGE_PATHS = page_paths(ROUTES)


def parent_of(route: str, search_base: str = "/now") -> str:
    """Where Back goes from `route` (D-19): drop the last drill pair, else walk up to the nearest page.

    `/more/staff/lead` returns `/more`, because `/more/staff` is not a page. `/search` itself returns
    to `search_base`, the location (query included) it was opened from.
    """
    parts = urlparse(route).path.strip("/").split("/")
    if parts == ["search"]:
        return search_base
    if len(parts) >= 3 and parts[-2] in DRILL_KINDS:
        return "/" + "/".join(parts[:-2])
    parent = parts[:-1]
    while parent and "/" + "/".join(parent) not in PAGE_PATHS:
        parent.pop()
    return "/" + "/".join(parent)
```

```python
# src/main.py (excerpt)
MEMORY = ViewMemory()                         # one per process: a new session reuses it (D-143, F29)


def main(page: ft.Page):
    setup_logging()

    def on_view_pop(e: ft.ViewPopEvent):
        page.navigate(parent_of(e.route, MEMORY.search_base))

    page.on_view_pop = on_view_pop            # before render_views: the Router hands it every pop (F6)
    page.render_views(App, MEMORY)            # App passes memory on to Services.create()
```

`Start` (the index route `/`) navigates to `memory.last_location` when it is set, else to `/now` (`/welcome` on first run, P2), so a new session after an activity recreation rebuilds the stack the user was on (D-143). `AppScaffold` records the top View's `page.route` there. A location under `/search` restores its `search_base` instead: the Router builds a global modal over its last non-modal location, which in a fresh Router is `/`.

`use_query()` (U9 interim) calls `ft.use_route_location()` for its hook slot and parses `urlparse(ft.context.page.route).query`, read once at mount. Each screen reads `view_path = ft.use_view_path()` at the top of its render (rule 4); its handlers call `page.navigate(drill_href(view_path, "speaker", sid))`, never an absolute path, so details work under every root and under search. `parent_of()` is unit-tested against every route shape; the app's `on_view_pop` and the pushed views' back arrow (§5.5) both use it. The handler goes once U18 is in the pinned Flet; the back arrow stays (D-10). `Drill` returns a component, as route components compose (S4 confirmed, D-141). An unknown id navigates to the parent path with a SnackBar.

### 5.4 Search (D-19)

One `Search` component on the global modal route `/search`, opened from Now, Schedule, Map and More with a preset scope (`/search?scope=sessions`, `/search?scope=rooms`); the opener first records its own location, query included, in `ViewMemory.search_base`. Results push details with `drill_href()` (`/search/session/42`), and our `page.on_view_pop` sends Back to `parent_of()`: from a result to the results, from search to `search_base` (§5.3). Query and scope live in `ViewMemory`. S4 confirmed search → result → detail → Back → Back to the results with the query kept (D-141). On return Flutter gives the search field its focus back, so the first Android Back only closes the keyboard; P1's search decides how to handle it.

### 5.5 Scaffold, tabs and Back (D-15..D-18)

```python
# src/pycon_us/ui/scaffold.py (excerpt)
TABS = (
    ("/now", "Now", ft.Icons.SENSORS_OUTLINED, ft.Icons.SENSORS),
    ("/schedule", "Schedule", ft.Icons.CALENDAR_MONTH_OUTLINED, ft.Icons.CALENDAR_MONTH),
    ("/my-schedule", "My schedule", ft.Icons.STAR_BORDER, ft.Icons.STAR),
    ("/map", "Map", ft.Icons.MAP_OUTLINED, ft.Icons.MAP),
    ("/more", "More", ft.Icons.MORE_HORIZ, ft.Icons.MORE_HORIZ),
)


def AppScaffold(*, view_path: str, title: str, controls: list[ft.Control],
                actions: list[ft.Control] | None = None, fab: ft.Control | None = None,
                back_to: str | None = None,
                on_retap: Callable[[], Awaitable[None]] | None = None) -> ft.View:
    """A View with the app bar, the bottom bar on tab roots and the Back rules (D-17, D-144).

    A plain builder that each screen calls unconditionally, so its two hooks are safe (rule 4).
    `back_to` overrides where the back arrow goes (Search passes its `search_base`);
    `on_retap` is a root's scroll-to-top, run when its active tab is tapped again.
    """
    page = ft.context.page
    memory = use_services().memory
    tab = next((i for i, t in enumerate(TABS) if view_path.startswith(t[0])), None)   # None under /search
    is_root = tab is not None and view_path == TABS[tab][0]
    intercept_back = is_root and view_path != "/now"
    if view_path == ft.use_route_location():                       # the top View of this render
        memory.last_location = page.route                          # where a new session returns (D-143)

    def on_tab(e: ft.Event[ft.NavigationBar]):
        index = e.control.selected_index
        if index == tab and on_retap is not None:                  # a re-tap fires on_change too (S4)
            page.run_task(on_retap)                                 # e.g. await list.scroll_to(offset=0)
        else:
            page.navigate(TABS[index][0])

    def go_back(e: ft.Event[ft.IconButton]):
        page.navigate(back_to or parent_of(view_path))

    async def back_to_now(e: ft.Event[ft.View]):
        page.navigate("/now")
        await e.control.confirm_pop(False)

    back_arrow = None if is_root else ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Back", on_click=go_back)
    return ft.View(
        route="/" if is_root else view_path,                       # roots share a key: no transition (D-142)
        padding=0,
        appbar=ft.AppBar(title=ft.Text(title), leading=back_arrow, actions=actions or [], center_title=False),
        navigation_bar=ft.NavigationBar(
            selected_index=tab,
            label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
            destinations=[ft.NavigationBarDestination(icon=i, selected_icon=s, label=label)
                          for _, label, i, s in TABS],
            on_change=on_tab,
        ) if is_root else None,                                    # roots only (D-144); search: none
        floating_action_button=fab,
        can_pop=not intercept_back,
        on_confirm_pop=back_to_now if intercept_back else None,
        controls=[ft.SafeArea(content=ft.Column(controls, expand=True), expand=True)],
    )
```

- A **tab switch** leaves that root alone on the stack (D-17); roots restore day, filters and scroll from `ViewMemory`/`Prefs` and never scroll by themselves (D-18, #313). **Back** on a root other than Now goes to Now; on Now it exits (Android).
- **The bar is on tab roots only** (D-144, #149): on pushed Views it travelled with the page (iOS) or doubled (Android) in every transition. Re-tapping the active tab scrolls its root to the top; from a pushed View, Back leads to the root. U23 (a shell bar outside the `Navigator`) would let it return to every View.
- **Back arrow (D-10):** Flutter's implied back button shows `arrow_back_ios_new_rounded` on iOS (Flet's theme has no `platform`, F8), so pushed views always show the Material back arrow, which navigates to `parent_of()` (D-19); Search passes `back_to=` its remembered `search_base`. S4 showed the Material arrow and a left-aligned title on the iOS simulator.
- **Tablets (P2, D-09):** at 600 dp and wider, `AppScaffold` puts an `ft.NavigationRail` in a `Row` beside the content (`View.navigation_bar` takes a `NavigationBar`, or a `CupertinoNavigationBar`, which D-10 rules out, but not a `NavigationRail`) and centres content at 720/840 dp.
- **Insets and system bars (#311, D-12):** `SafeArea` bodies, `use_safe_area=True` sheets, and `Theme.system_overlay_style` per colour scheme (§15, D-113); S1 checked 3-button and gesture navigation, in light and dark. The `SafeArea` also keeps landscape content clear of the side navigation bar.

### 5.6 Deep links (D-21, NEW-07, P2)

Both `[tool.flet.android.deep_linking]` and `[tool.flet.ios.deep_linking]` are configured, so links work with or without flet-dev/flet#6953 (F16). Each table sets both `scheme` and `host` (both named with the app identity, O-4); the build template registers nothing when either is missing. Link paths are internal routes: `<scheme>://<host>/schedule/session/42` arrives as `page.route == "/schedule/session/42"` and builds `[Schedule, Session]`, so Back never exits. Reminder taps use the same paths. "Share" uses the public `presentation_url` (`conference.toml`), never the scheme; synthetic ids share no URL.

---

## 6. State model

### 6.1 Stores (D-69)

All are `@ft.observable @dataclass` in `state.py`. Fields starting with `_` never notify. A method that persists awaits the write before assigning the field.

| Store | Fields | Methods | Phase |
|---|---|---|---|
| `Conference` | `data: ConferenceData \| None` (frozen, `eq=False`); `source: "none"\|"bundled"\|"cache"\|"network"`; `fetched_at: datetime \| None` (aware, D-145); `refreshing`; `problem: None\|"offline"\|"server"`; `version` (memo key); `changes` (last 24 h, P2); `_task`; `_foreground` (P1, #82) | `load_local`, `start_refresh`, `refresh`, `age`, `status` (D-146); `set_foreground` (P1, #82) | P0 |
| `Prefs` | persisted: `theme`, `high_contrast`, `excluded_tracks`, `onboarded`, `reminders`, `dev`; device, not persisted: `os_high_contrast`, `os_dark`, `reduce_motion`; `loaded` | `load`, `save(svc, **changes)`; properties `high_contrast_on`, `dark` | P0 |
| `Favorites` | `ids: list[str]` (a list, because it is persisted as `list[str]`, F12) | `load`, `toggle`, `add_many`, `remove_many` (each returns what Undo needs) | P1 |
| `Account` | `restored`, `signed_in`, `signing_in`, `email`, `nickname`, `lead_retrieval`, `door_check`, `mask_violation`, `is_speaker`, `scanner_consent`, `favorites_dirty`, `error` | `restore`, `sign_in`, `sign_out`, `refresh_flags` | P3 |
| `Staff` | `sponsor`; `pending`, `failed`, `synced`; `syncing`; `last_sync_at`; `last_error`; `revision`; memory-only PII: `inventory`, `coc_directory` | `select_sponsor`, `update_counts`, `clear` | P3 |

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

    async def load_local(self, storage: Storage, year: YearData) -> None:
        """Publish the persistent cache, or the bundled snapshot when there is no usable cache."""
        cached = await storage.read_feed()
        if cached is not None:
            try:
                data = feed.process(cached.raw, year.feed_settings)
            except feed.FeedError as error:
                await storage.delete_feed(f"it does not parse: {error}")   # logs (D-39)
            else:
                self._publish(data, "cache", datetime.fromtimestamp(cached.saved_at, UTC))
                return
        snapshot = year.read_snapshot()                      # bundled with the app (D-135)
        self._publish(feed.process(snapshot.raw, year.feed_settings), "bundled", snapshot.captured_at)

    def start_refresh(self, storage: Storage, year: YearData, *, transport=None) -> asyncio.Task[None]:
        """Start a background refresh unless one is in flight; return the one that runs (D-145)."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._refresh(storage, year, transport))
        return self._task

    async def refresh(self, storage: Storage, year: YearData, *, transport=None) -> None:
        """Refresh and wait; concurrent callers share one request, and one caller's cancellation spares it."""
        await asyncio.shield(self.start_refresh(storage, year, transport=transport))

    async def _refresh(self, storage: Storage, year: YearData, transport) -> None:
        self.refreshing = True
        try:
            raw = await api.fetch_feed(year.conference.feed_url, transport=transport)
            data = feed.process(raw, year.feed_settings)          # FeedError: nothing is written
        except api.NetworkError:
            self.problem = "offline"                              # D-146
        except (api.ApiError, feed.FeedError):
            logger.warning("Feed refresh failed; keeping the current data", exc_info=True)
            self.problem = "server"
        else:
            await storage.write_feed(raw)                          # atomic, after a good parse (D-39)
            previous, previous_source = self.data, self.source
            self._publish(data, "network", clock.now())
            if previous is not None and previous_source != "bundled":
                await self._record_changes(storage, diff(previous, data))   # P2, D-47
        finally:
            self.refreshing = False

    def _publish(self, data: ConferenceData, source: Source, fetched_at: datetime) -> None:
        self.data = data                  # eq=False: always notifies (F5)
        self.source, self.fetched_at, self.problem = source, fetched_at, None
        self.version += 1                 # writes in one block give one re-render


ConferenceCtx: ft.ContextProvider[Conference | None] = ft.create_context(None)


def use_conference() -> Conference:       # raises RuntimeError without a provider
    ...
```

- `age()` is the `timedelta` since `fetched_at` by `clock.now()`, never negative; `status(info)` is what the strip says: `refreshing`, `offline`, `problem`, `stale` (over 6 h on conference days, else 24 h) or `fresh` (D-146). P1 (#82) adds `set_foreground()` and `_foreground`, checked by the 60 s tick (D-40). One shared `_task` makes refresh single-flight, and it never deletes the cache first (fixes EVT-07, SPON-08). `transport` is for tests (`httpx.MockTransport`); the app leaves it None.
- A refresh that fails with an unexpected exception is logged by `start_refresh`'s done callback as soon as it ends (D-71), and `refresh()` callers also get the exception raised; P0-21's asyncio exception handler (F4) is the backstop. Expected failures never raise.
- `feed.process` is pure and runs on the loop (D-109: S1 measured 3-4 ms for `json.loads` plus a processing stand-in on the emulator). If the logged time exceeds 150 ms on the iPhone, revisit it per D-109; `asyncio.to_thread` does not shorten a GIL-bound stall. No diff against the bundled snapshot (first install); parser changes cannot cause false diffs, since the cache keeps raw bytes.

### 6.3 `ViewMemory` (D-18)

```python
@dataclass
class ViewMemory:
    """Where the user left each screen, for this app process (D-143).

    Plain, not observable: a screen reads it once to seed its own state and writes it back from its
    handlers, so remembering a scroll offset never re-renders another screen.
    """

    schedule_day: int | None = None
    schedule_offsets: dict[int, float] = field(default_factory=dict)
    jumped_to_now: bool = False
    search_query: str = ""
    search_scope: str = "all"
    search_base: str = "/now"            # where search was opened from; Back returns there (D-19)
    map_tab: str = "rooms"
    last_location: str = ""              # the top View's route; Start returns a new session there (D-143)
```

Filters are preferences (persisted in `Prefs`); positions are process memory (here). One `ViewMemory` lives as long as the Python process, so a new session after an activity recreation or a Back exit on Android (F26, F29) finds the positions and the last location as the user left them (D-143).

### 6.4 Screen pattern

A screen reads its stores through hooks, memoises its view model with `ft.use_memo(lambda: queries.x(conference.data, ...), [conference.version, tuple(favorites.ids), ...])` (lists passed as tuples), builds handlers as named functions (async ones wrapped in `report_errors`), and returns `AppScaffold(...)`. Undo is a `SnackBar(content=..., action="Undo", on_action=..., behavior=ft.SnackBarBehavior.FLOATING)` shown with `page.show_dialog`; an async undo runs through `page.run_task(favorites.toggle, svc, sid)`. Rows are `@ft.component`s keyed by session id and memoised on `(id, is_favorite)`, unless S2 decides otherwise.

---

## 7. Data pipeline

### 7.1 Sources (D-38, D-39) and the status strip (D-32)

| Source | Where | Used |
|---|---|---|
| Network | `fetch_feed(conference.feed_url)`: `httpx.AsyncClient`, 10 s timeout | background refresh |
| Persistent cache | `<data dir>/feed-<year>.json`, raw bytes; `saved_at` = file mtime | every start when present |
| Bundled snapshot | `data/<year>/conference.json`, read by `YearData.read_snapshot()` and refreshed by `tools/update_snapshot.py`, which refuses a feed that does not parse cleanly and also writes `conference.toml`'s `snapshot_captured_at` (D-135) | first launch, or a corrupt cache |

The strip is hidden when fresh; shows "Updating…" with an indeterminate `ProgressBar` while refreshing, "Updated N h ago · Refresh" when stale (6 h on conference days, else 24 h), and "Offline · schedule from Tue 10:42 · Refresh" when `problem == "offline"`. Skeletons only when `data is None` (impossible after bootstrap). A failed refresh leaves data and cache untouched.

### 7.2 Feed shape (2026; `docs/research/ionic/data-layer.md` §9)

Top level: `conference` (`sponsors` by level, `content` HTML blocks), `schedule` (728 slots), `open-spaces` (123), `posters` (25), `sprints` (24), `job-listings` (13). Gotchas: three `conf_key` spaces collide (hence `+9000` and `poster-detail-` ids); durations are minutes in `schedule` and seconds in `open-spaces` (always use `start`/`end`); markup is mixed per field (HTML descriptions and bios, Markdown open spaces, plain sponsor text, Markdown links in slot names); speakers are linked **by name**; `cancelled` is always false (cancellations arrive as placeholder slots).

### 7.3 Processing rules (`core/feed.py`, `core/records.py`, `core/rules.py`, `core/names.py`, `core/slugs.py`; D-41, each rule has a named test)

`process(raw: bytes, settings: FeedSettings) -> ConferenceData`, where `FeedSettings` (frozen, `YearData.feed_settings`) holds the time zone, the site URL, the hall prefix (D-122), the lightning talks' location (D-124) and the display-time overrides, and gains the sprint rooms with P2's `map.toml`. It lives in `core/rules.py` with `DisplayTimeOverride`. A structurally wrong feed raises `FeedError`: not JSON, not an object, no `schedule` list, an optional section (`open-spaces`, `posters`, `sprints`, `job-listings`; the 2025 feed has no posters, sprints or job listings) that is not a list, or no readable slot at all. A single bad record (a missing or mistyped field, a time without a UTC offset, an end before its start, a duplicate id) is skipped, recorded in `ConferenceData.skipped` as `schedule[5]: <problem>`, logged once at WARNING, and never blanks the schedule. Unknown fields are ignored.

**Decoding (P0-10, built).** Every id becomes a `str` (D-42); every time an aware datetime converted to the conference zone; each session's `day` is `timefmt.local_date(start)`. Slots and open spaces decode into plain records (`records.Slot`, `records.OpenSpace`) that the rules turn into sessions. Days are sorted by date; each day's `TimeGroup`s are keyed by their aware start (so every group has one, DATA-13) and sorted by it; within a group, sessions are ordered by location, then name. Only sessions with `in_timeline` are grouped.

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
| 15 | Sprint rooms | seeded from `map.toml` pins with `sprint = true`; rooms natural-sorted | MAP-08 |
| 16 | Markup | HTML → Markdown once per feed version, last, after the rules above (§7.7, D-130, D-140; built by #134): `description_md`, `bio_md`, `content_md` beside the raw HTML, and `Session.search_text` from `to_text`; open-space Markdown passed through with its links as written, its search text without link destinations or markers; sponsor text kept plain | DATA-23..25 |
| 17 | `slot.sessions` | a poster slot's are posters (D-121); any other kind's are logged and ignored | DATA-27 (drop) |

**Invariants** (D-77, in `tools/feed_invariants.py`: tested on the 2025 and 2026 fixtures by `tests/test_feed_invariants.py`, and run weekly on the live feed by `tools/check_feed.py`; testing-and-quality.md §3.3): no session lost beyond the documented drops and collapses; ids stable across runs; no placeholder survives; Job Fair grouped at 10:00, labelled 9:30; one Posters row and per-day Lunch rows; every speaker with sessions linked; every group has a start; `start <= end`; all datetimes aware; rooms and slugs consistent. `process()` logs `Feed processed in N ms` at INFO (D-109). A reviewed snapshot of the processed model and the one-off Ionic outputs (`tests/fixtures/ionic/<year>/`, no Node in CI, compared in `tests/test_ionic_reference.py`) settle ambiguous rules; intended differences are listed by feature id or D-number.

### 7.4 Models (`core/models.py`)

Built in P0-10..P0-12: `Speaker` (`id`, `name`, `photo_url`, `bio`), `Session` (`id`, `name`, `kind`, `track`, `location`, `display_location`, `rooms`, `description`, aware `start`/`display_start`/`end`, `day`, `speaker_ids`, `speaker_names`, `pre_registered`, `spanish`, `url`, `image_url`, `in_timeline`), `Room` (`slug`, `name`, `session_ids`), `TimeGroup` (`start`, `session_ids`), `Day` (`date`, `groups`), `Poster`, `Sprint`, `JobListing` and `ConferenceData` (`sessions` and `speakers` by id, `days`, `rooms` by slug, `posters`, `sprints`, `job_listings`, `dropped`, `skipped`), all `@dataclass(frozen=True, eq=False)`. #134 added the converted markup (D-140): `Session.description_md` and `search_text`, `Speaker.bio_md`, `description_md` on `Poster`, `Sprint` and `JobListing`, and `ConferenceData.content` (the raw `conference.content` blocks) with `content_md`. The rules add the rest of the target shape:

`Session` (`id: str`, name, track, kind, flags, `location`, `display_location`, `rooms`, `description_md`, `search_text` = folded title + description text + speaker names, speaker ids and names, aware `start`/`end`/`display_start`, `day`, URLs, `in_timeline`), `Speaker`, `Room`, `TimeGroup`, and `ConferenceData` (frozen, `eq=False`: `sessions: dict[str, Session]`, speakers, rooms, days, sponsors by level, sprints, job listings, `content_md`, `skipped`). Objects refer to each other by id only; queries return fresh view models and never mutate the model (Ionic wrote `hide` flags onto shared objects, SCHED-17).

### 7.5 Queries (`core/queries.py`)

| Query | Rule | Features |
|---|---|---|
| `days(data, first_day, last_day)` | every date from the conference's first day to its last (sprint days included), widened to any schedule day outside them; an immutable tuple, so a day index never moves (D-126); ignores filters. Built in P0 | DATA-17 |
| `timeline(data, day, excluded)` | one item per time slot, rows ordered by start then room (D-31); a track passes unless excluded | DATA-18, SCHED-02 |
| `search(data, query, scope)` | folded, **all** words must match `search_text` (D-46); grouped by type, sessions by day; ignores filters | NEW-02, SPKR-02 |
| `now_next(sessions, now)` | Now = `start <= now < end`; Next = the earliest later start; ignores filters | SCHED-25 |
| `next_for_me(data, favorites, now)` | earliest saved session with `end > now`, within 3 h | SCHED-25 |
| `my_schedule(data, favorites)` | saved sessions by day, plus `overlaps: dict[id, list[id]]` (sorted sweep) | NEW-01 |
| `current_slot_key(day, now)` | first slot with `start >= now`, else the last: `"slot-<iso>"`, the slot item's `ScrollKey` | SCHED-16 |
| `speakers(data)` | sorted by folded displayed name (D-46) | SPKR-01 |
| `track_sessions`, `room_sessions` | flat by start (poster details included), grouped by day | SCHED-22, ROOM-02 |
| `sprints(query)`, `jobs(query)` | all words over name, submitter or sponsor, and text (never raw HTML) | EVT-06, SPON-07 |

```python
# src/pycon_us/core/queries.py (excerpt)
def fold(text: str) -> str:
    """Lower-case and strip accents, so 'Cristián' matches 'cristian' (D-46)."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def matches(query: str, folded_haystack: str) -> bool:
    """True when every word of the query occurs in the already-folded haystack."""
    return all(word in folded_haystack for word in fold(query).split())
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
| `local_date(moment, zone)`, `today(now, zone)` | the conference-local date: the day bucket, and the one "today" |
| `time_label(moment, zone, use_24h=...)` | `9:25 AM`, or `09:25` when `page.media.always_use_24_hour_format` is set (F23) |
| `time_range_label(start, end, zone, use_24h=...)` | `9:25–10:10 AM`, `11:30 AM–12:15 PM`, one time when start equals end |
| `day_label(day)`, `day_heading(day)` | `Fri, May 15`, `Friday, May 15` |
| `zone_note(now, zone, zone_name, device_offset)` | `Times are Pacific Time (PDT)` when the device's offset at `now` differs, else None; the UI passes `now.astimezone().utcoffset()` |

Weekday and month names come from fixed tuples, never locale `strftime`, and naive datetimes raise `ValueError`. Tests run under `TZ=America/Los_Angeles` and `Pacific/Kiritimati` (the `machine_tz` fixture), and cover both DST changes and midnight.

### 7.7 HTML → Markdown (`core/html_md.py`; D-44)

Stdlib `html.parser`, once per feed version inside `feed.process()` (D-130), into a small tree that is then rendered; S3 settled the details (D-114, D-115; `docs/spikes/03-html-markdown.md`, whose `html_md_proto.py` was the reference) and #67 the boundaries (D-131). Two public functions: `to_markdown(value, site_url) -> str` and `to_text(value) -> str`.
- **Tags** (the 2025 and 2026 census): `p` → paragraph; `br` → `"  \n"`; `hr` → `---`; `h1`–`h6` → `#`–`######`; `ul`/`ol`/`li` → `- `/`N. `, continuation lines indented by the marker's width (three spaces under `1. `); `blockquote` → `> `; `strong`/`b`, `em`/`i`, `s`/`del`/`strike` → `**x**`, `*x*`, `~~x~~` with edge whitespace kept outside; `code` → a code span fenced with one backtick more than the longest run inside; `a` → `[text](url)`, the `href` joined to `site_url`, only `http`, `https` and `mailto` linked, the destination percent-encoded; bare `http(s)` URLs in text become explicit links; edge whitespace stays outside links and emphasis; emphasis that could not flank loses its markers.
- **Anything else is unwrapped** (its text stays in place); `script` and `style` are dropped. Whitespace collapses as in a browser; only `br` breaks a line.
- **A value with no tag is plain text:** entities decoded, blank lines make paragraphs, single newlines hard breaks (sprint descriptions).
- **Escaping** (D-115): in text, `` \ ` * _ [ ] ( < > | ~ $ & : `` and a block marker at the start of a line become numeric character references (`&#36;`), because `ft.Markdown` always enables LaTeX (F27) and GFM emoji; code spans stay raw.
- **A text-only form** (`to_text`, no markup) feeds search (D-46): the visible text, with blocks, list items and breaks as spaces so words never join; link targets, `script` and `style` left out; not yet folded.
- **Emphasis** is rendered as tokens and checked against CommonMark's flanking rules before it is joined into a paragraph; a pair that could not open or close loses its markers (D-114, D-131).

Rendered with `ft.Markdown(value, selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB, on_tap_link=..., md_style_sheet=...)`, with the one style sheet from `theme.py` whose text styles all name their colour (D-116, F28); links open with `launch_url(url, mode=ft.LaunchMode.IN_APP_BROWSER_VIEW)` (SESS-06). Job roles from `<a href>` anchors (SPON-09) and Venue & hours sections (MAP-09) arrive with their screens in P2.

### 7.8 Names and slugs (`core/slugs.py`)

Track display names (`short`, `plural`, `long`) and clean URL slugs (`ai`, `lightning-talks`; not Ionic's `ais`) come from the `[[tracks]]` table of `conference.toml`, with a humanised fallback (DATA-28, DATA-29). Three normalisers are copied exactly from Ionic because data keys depend on them: `slugify_room` (lower-case, `[^a-z0-9]+` → `-`, strip `-`), `normalize_room_key` (drop `room\s+`, keep `[a-z0-9]`; keys the pins) and `sponsor_slug` (lower-case, `\s+` → `-`, drop `[^a-z0-9-]`).

### 7.9 Change log (`core/diff.py`; D-47, NEW-04, P2)

`diff(old, new) -> list[Change]` compares sessions by id, skipping collapsed `break` and `poster` rows (their ids embed their start): `added`, `removed`, `time` (start or end), `room` (location) and `title`, each with old and new values. Batches are appended to `<data dir>/changes-<year>.json` (`[{"detected_at": ..., "changes": [...]}]`, trimmed to 14 days). `Conference.changes` holds the last 24 h for the "Changed" chip; a batch shows "Schedule updated · Review" (SnackBar) and a Now card; `/schedule/changes` lists saved sessions first. Wording: "Removed from the latest schedule", never "cancelled". A change also re-runs `reminders.plan()`.

---

## 8. Per-year bundled content (D-45)

| File | Holds | Replaces |
|---|---|---|
| `conference.toml` | name, dates, zone, venue, URLs, feed URL, snapshot time, tracks | `/2026/` literals |
| `content.toml` | links, Wi-Fi, safety contacts, keynotes, event reminders, venue hours, overrides, sponsor credits | hard-coded copy; `'temporal'`/`'google'` matching |
| `map.toml` | floor plans, pins, booths, sprint rooms | `ROOM_LOCATIONS`, booth tables |
| `conference.json` | the feed snapshot (NEW-03) | the first-launch spinner |

`config.YEAR = 2026` until the 2027 feed exists; rolling over = add `data/2027/` and its maps, then set `YEAR`. A content fix needs a new build (accepted); no remote config.

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
city = "Long Beach, CA"             # later: address (P2)
site_url = "https://us.pycon.org/2026/"
feed_url = "https://us.pycon.org/2026/schedule/conference.json"
presentation_url = "https://us.pycon.org/2026/schedule/presentation/{id}/"   # P1 (NEW-06)
snapshot_captured_at = 2026-10-11T09:00:00-07:00     # written by tools/update_snapshot.py; only the active year (D-135)

[[tracks]]
key = "Ai"                  # as produced by feed processing: the kind, first letter upper-cased
short = "AI"
plural = "Future of AI with Python"
long = "The Future of AI with Python"
icon = "MEMORY_OUTLINED"    # an outlined ft.Icons name (D-27); colours stay in the theme tokens (D-24, D-25)
group = "talks"             # filter-sheet group: talks | hands-on | community | logistics
slug = "ai"                 # P1 (DATA-29)
new = true                  # P1: "New track" badge
```

Every field without a phase note exists today (P0-08); the others arrive with their features. An unknown track key falls back to its humanised form (`Hallway-track` → "Hallway track"), so a new kind in next year's feed still reads well.

```toml
# data/2026/content.toml
[links]
lightning_talks_signup = "https://us.pycon.org/2026/events/lightning-talks/"
open_space_signup = "https://us.pycon.org/2026/events/open-spaces/"
report_app_issue = "https://github.com/OWNER/pycon-us/issues"

[wifi]
network = "PyCon2026"
password = "illustrative"
sponsor = "example-sponsor"         # sponsor_slug() of the credited sponsor (INFO-09)

[[safety_contacts]]
label = "Code of Conduct hotline"
kind = "tel"                        # tel | mailto | https
value = "+1-555-0100"
source = "https://us.pycon.org/2026/about/code-of-conduct/"   # verified public source
checked = 2026-10-11

[[keynotes]]                        # also: name, kind (keynote | panel), role, photo, abstract (Markdown)
session_ids = ["1001"]

[[event_reminders]]
id = 8000                           # 8000-8099, unique
category = "lightning"              # lightning | open_space | keynote
at = 2026-05-15T09:00:00-07:00
title = "Lightning talk sign-ups are open"
body = "Sign up at the board near registration."

hall_prefix = "Expo "                # "Hall AB" in a name is "Expo Hall AB" (D-122)
lightning_talks_location = "Pacific Ballroom - Arena"   # D-124

[[display_time_overrides]]          # also: [[venue_hours]] (service, pin, hours), [sponsor_credits]
match = '\s*job\s*fair\s*&\s*community\s*showcase\s*'   # regex, case-insensitive, fullmatch on the cleaned name
minutes = -30
```

```toml
# data/2026/map.toml
[[plans]]
id = "concourse"
title = "Concourse level"
image = "maps/2026/concourse.png"   # under src/assets, at most 2048 px (S7)
width = 2048
height = 1448

[[pins]]
key = "104c"                        # normalize_room_key(room name)
label = "Room 104C"
plan = "concourse"
x = 41.5                            # percent of the image
y = 62.0
sprint = false

[[booths]]
number = "613"
x = 0.412                           # ratios of the expo image; also y, w, h
```

### 8.2 Loader (`config.py`)

`tomllib` loads each file into frozen dataclasses (`Track`, `Wifi`, `SafetyContact`, `Keynote`, `EventReminder`, `Plan`, `Pin`, `Booth`, …) gathered in `YearData`. The loader is the schema:

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

As built (P0-08), one recursive `_build(cls, raw, file)` applies this check to every table and turns arrays of tables into tuples of their dataclass; errors read `2026/conference.toml: tracks[8].group: 'workshops' is not one of (...)`. Entries are then checked by rule (a unit test loads every year): a valid zone; ordered dates; `https://` URLs; unique reminder ids in 8000–8099 with aware times; pins 0–100 %, booths 0–1; referenced plans, pins, keynote sessions and sponsor slugs exist; safety contacts carry `source` and `checked`; every feed room has a pin or is under "Other locations".

---

## 9. Storage (D-48, D-49)

| What | Where | Key or file | Cleared by sign-out |
|---|---|---|---|
| Theme, high contrast | SharedPreferences | `pycon.theme` (`system`/`light`/`dark`), `pycon.high_contrast` (`system`/`on`/`off`) | no |
| Welcome seen | SharedPreferences | `pycon.onboarded` | no |
| Excluded tracks | SharedPreferences | `pycon.excluded_tracks` (`list[str]` of track keys; absent → `["Open Space"]`, an explicit `[]` kept) | no |
| Reminder settings, developer options | SharedPreferences | `pycon.reminders`, `pycon.dev` (JSON, merged over defaults) | no |
| Favourites | SharedPreferences | `pycon.<year>.favorites` (`list[str]`) | **no** (D-48) |
| Account, staff sponsor, start screen, sync flag (P3) | SharedPreferences | `pycon.account`, `pycon.staff_sponsor` (JSON), `pycon.start_screen`, `pycon.<year>.favorites_dirty` | yes, except start screen |
| API key and secret (P3) | `flet_secure_storage.SecureStorage` | `pycon.api_key`, `pycon.api_secret` | yes |
| Feed cache, change log | data dir | `feed-<year>.json` (raw bytes), `changes-<year>.json` | no |
| Staff outbox (P3) | sqlite in data dir | `outbox.db` | see §12.1 |
| Inventories, CoC directory (P3) | memory only | `Staff` fields | yes |

SharedPreferences takes only `str`, `int`, `float`, `bool` and `list[str]` (F12): dicts are JSON strings, and the feed never goes there. All keys are constants in one table in `services/storage.py`: each is a `Pref(key, default)` whose default's type is the value's type (`favorites(year)` builds the per-year key).

```python
# src/pycon_us/services/storage.py (excerpt)
THEME: Pref[str] = Pref("pycon.theme", "system")
EXCLUDED_TRACKS: Pref[list[str]] = Pref("pycon.excluded_tracks", ["Open Space"])
DEV: Pref[dict[str, Any]] = Pref("pycon.dev", {})           # a dict default: stored as JSON


def data_dir() -> Path:
    """The durable data directory, read from the environment on every start (D-108)."""
    configured = os.environ.get("FLET_APP_STORAGE_DATA")
    path = Path(configured) if configured else Path.cwd() / ".flet/storage/data"
    path.mkdir(parents=True, exist_ok=True)
    return path.absolute()


def write_atomic(path: Path, data: bytes) -> None:
    """Write so that readers see the old file or the new one, never a partial file."""
    tmp = path.with_name(path.name + ".tmp")
    with _write_lock:                      # writers share the temp file (D-120)
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
- Feed cache: `read_feed()` returns a `CachedFeed(raw, saved_at)` (bytes and mtime) or `None`; it does not judge the bytes. `write_feed(raw)` runs `write_atomic` in `asyncio.to_thread` and is called only after `raw` parsed (D-39). `delete_feed(reason)` removes a cache that no longer parses (or that the Developer screen clears) and logs why.
- Failures are logged and returned, never raised (D-120): `set` (also on a SharedPreferences timeout or client error) and `write_feed` return `False`, `get` returns the default, `read_feed` returns `None`, and the previous file stays. A store that saves what the user chose shows a `False` to the user. Only `data_dir()` raises, when the directory cannot be created (a broken install).
- `write_atomic` holds a module lock while it writes, because a cancelled refresh's `to_thread` write keeps running and the writers share the temp file.
- The OS may purge `FLET_APP_STORAGE_CACHE`, so nothing durable goes there; the data directory survives updates (F14, D-108). Read it from `FLET_APP_STORAGE_DATA` on every start; never persist its absolute path, because iOS moves the container on an update. Without the variable (not `flet run`, not a packaged build: pytest, or a plain `python`), it is `.flet/storage/data` under the working directory, the layout `flet run` uses.
- **sqlite (P3, outbox only):** one connection in the data directory, used **only from the asyncio loop thread** (statements take milliseconds), `PRAGMA journal_mode=WAL`, migrations by `PRAGMA user_version`. S1 ran `sqlite3` in the embedded Python on Android and iOS, and the database survived update installs (D-108).

---

## 10. Private API: boundary, client and signing (P3; D-50..D-55)

### 10.1 Boundary (D-51)

Private-API features (sign-in, account, favourites sync, staff tools) stay hidden unless a mock base URL is set in the Developer screen (`prefs.dev.mock_api_url`; the Android emulator reaches the laptop at `10.0.2.2`). The client refuses any `/api/v1` request to a `pycon.org` host whatever the configuration (unit test `test_client_refuses_psf_hosts`). Sign-in and Account say "Connected to the local mock server".

### 10.2 Client (`services/api.py`)

```python
# src/pycon_us/services/api.py (excerpt)
def refuse_private_psf(url: httpx.URL) -> None:
    """Make calling the PSF's private API impossible, even by misconfiguration (D-51)."""
    if (url.host == "pycon.org" or url.host.endswith(".pycon.org")) and "/api/v1/" in url.path:
        raise PermissionError(f"refusing a private PSF endpoint: {url.host}{url.path}")


class ApiClient:
    """Signed requests to the mock PyCon API, byte-compatible with the Ionic client (D-52, D-53)."""

    async def request(self, endpoint: Endpoint, *args: str, query: str = "", payload: object = None) -> object:
        path = f"/{self._year}/api/v1/{endpoint.path.format(*args)}" + (f"?{query}" if query else "")
        body = canonical_body(payload) if payload is not None else b""
        for attempt in (1, 2):
            request = self._http.build_request(endpoint.method, path, content=body or None,
                                               timeout=endpoint.timeout)
            refuse_private_psf(request.url)
            if body:
                request.headers["Content-Type"] = "application/json"
            if endpoint.signed:
                key, secret = self._credentials()
                ts = js_round(time.time() + self._skew)
                sent_path = request.url.raw_path.decode("ascii")     # exactly the bytes on the wire
                request.headers.update({"X-API-Key": key, "X-API-Timestamp": str(ts),
                                        "X-API-Signature": sign(secret, ts, endpoint.method, sent_path, body)})
            try:
                response = await self._http.send(request)
            except httpx.TransportError as error:                    # timeouts included
                raise NetworkError(str(error)) from error
            self._skew = skew_from(response.headers.get("date"), self._skew)
            if response.status_code == 403 and endpoint.signed and attempt == 1 and abs(self._skew) > 300:
                continue                                              # one retry, corrected timestamp
            return unwrap(response)                                   # {code, data} → data; else ApiError
        raise ApiError(403, "clock skew")
```

- Two errors only (D-53): `NetworkError` (no answer: connection, DNS or timeout; never counted in the outbox) and `ApiError(status, message)` with `.is_auth` for 401/403. `self._http` is one `httpx.AsyncClient(base_url=..., transport=...)`; tests pass the mock's `httpx.MockTransport`.
- Signing `url.raw_path` (exactly what httpx sends) rules out "re-encoded after signing" bugs; queries are still built the Ionic way (§10.4). `skew_from` parses the `Date` header (`email.utils.parsedate_to_datetime`). Callers trust these errors, not `ft.Connectivity`. `fetch_feed(url)` (P0) is an unsigned 10 s GET with the same errors.

### 10.3 Signing (`core/signing.py`; D-52)

```python
# src/pycon_us/core/signing.py
"""Request signing, byte-compatible with Ionic's pycon-api.ts (buildRequestAuthHeaders)."""
import hashlib
import json
import math
from urllib.parse import quote

JS_COMPONENT_SAFE = "!*'()"          # encodeURIComponent keeps A-Z a-z 0-9 - _ . ! ~ * ' ( )


def canonical_body(obj: object) -> bytes:
    """JSON.stringify: compact, insertion order, non-ASCII kept. Serialise once and send these bytes."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def js_round(x: float) -> int:
    """JavaScript Math.round (half up), not Python's banker's rounding."""
    return math.floor(x + 0.5)


def sign(secret: str, ts: int, method: str, path_with_query: str, body: bytes = b"") -> str:
    """Hex SHA-1 (not HMAC) of secret + timestamp + METHOD + path + body, with no separators."""
    base = secret.encode() + str(ts).encode() + method.upper().encode() + path_with_query.encode() + body
    return hashlib.sha1(base).hexdigest()


def enc(value: str) -> str:
    """encodeURIComponent."""
    return quote(value, safe=JS_COMPONENT_SAFE)
```

Headers `X-API-Key`, `X-API-Signature`, `X-API-Timestamp` (`str(ts)`; Ionic uses `Math.round(Date.now() / 1000)`). **Vectors** (`tests/test_signing.py`, secret `s3cr3t`, ts `1747324800`, recomputed with `hashlib`); D-52 adds vectors produced once by Ionic's own code (Unicode, escaping, query order, rounding) with their provenance, in `tests/fixtures/ionic/signing.json`:

| Method | Path with query | Body | Signature |
|---|---|---|---|
| GET | `/2027/api/v1/user/mobile_state/` | — | `77946e44677e7f97445336dd9de5f0a0b58dc016` |
| PATCH | `/2027/api/v1/user/mobile_state/` | `{"favorites":["123","poster-detail-7"]}` | `59b274bd80705949c06a5fd31abfe5f54307dc26` |
| POST | `/2027/api/v1/lead_retrieval/ABC123/note/` | `{"accessCode":"ABC123","note":"Interest: hot\nNotes: café"}` | `798ff969a24a536d3df9f504dcb16987f73dbd41` |
| GET | `/2027/api/v1/check_in/fetch_products/?attendee_access_code=ABC123&category_pk_list=1,2&mode=redemption_mode` | — | `3b49566459ec1ee2a43bdae2a2d87835c9aada52` |

### 10.4 Endpoints (data in `services/api.py`; under `/{year}/api/v1/`; envelopes `{code, data}` / `{code, error}`)

| Name | Method and path | Body | Timeout | Notes |
|---|---|---|---|---|
| `authenticate` | POST `authenticate/` (**unsigned**) | `{email, password}` | 3 s | single flight |
| `check_features` | GET `user/check_features/` | — | 2 s | absent flag = False |
| `mobile_state` | GET / PATCH `user/mobile_state/` | — / `{favorites}` | 2 s | §10.5 |
| `redeemable` | GET `check_in/redeemable/` | — | 2 s | categories split by `/shirt\|swag/i` |
| `inventory` | GET `check_in/attendees_by_product_with_quantity/<id>/` | — | 20 s | per product, gathered |
| `fetch_products` | GET `check_in/fetch_products/?…` | — | 10 s | query **not encoded** (Ionic); swag `category_pk_list` + `redemption_mode`, door `product_pk_list` + `door_check_mode` |
| `redeem` | POST `check_in/redeem_products/` | `{attendee_access_code, badge_validator, scanned_at, "product-redeem-<id>", "product-<id>-quantity"}` | 10 s | door omits a missing validator, swag sends `""` |
| `coc_attendees` | GET `mask_violations/attendees/` | — | 15 s | memory only |
| `coc_capture` | GET `mask_violations/capture/?attendee_access_code=<enc>` / POST `mask_violations/capture/` | — / `{attendee_access_code, notes?, force: true}` | 5 s | POST when there are notes or `force` |
| `lead_sponsors` | GET `lead_retrieval/sponsors/` | — | 5 s | strip quotes from names |
| `lead_capture` | GET `lead_retrieval/capture/?attendee_access_code=<enc>&badge_validator=<enc>[&sponsor_id=<enc>]` | — | 2 s | outbox only |
| `lead_note` | POST `lead_retrieval/<code>/note/` | `{accessCode, note[, sponsor_id]}` | 2 s | outbox only, after its capture |

### 10.5 Account and favourites sync (D-54, D-55)

- **Sign-in:** `AutofillGroup` with hints, an in-flight guard, distinct errors for a wrong password (`is_auth`) and for offline or timeout. Credentials reach SecureStorage *before* `signed_in` flips; then `check_features` and the first sync.
- **Favourites:** the first sync sends the **union** of both lists. Then each change sets `favorites_dirty` and schedules a debounced (1 s), idempotent full-list PATCH that clears it; start and resume retry. A pull pushes a dirty list first, else adopts the server's (ints become strings).
- **Sign-out:** with unsynced rows, an `AlertDialog` offers "Sync now" or "Sign out anyway (N unsynced)". Credentials, flags, consent and sponsor go; favourites, theme, filters and reminders stay.

---

## 11. Mock server (`tools/mock_api/`; D-50, D-57, NEW-08)

| Part | What it is |
|---|---|
| `handlers.py` | `MockState` (in-memory accounts, sponsors, products, attendees, records, faults, injectable `now`) and a pure `handle(state, method, raw_path, headers, body) -> (status, headers, body)` |
| `server.py` | stdlib `ThreadingHTTPServer` over `handle` (`python -m tools.mock_api.server --host 0.0.0.0 --port 8000`; development.md §6), a lock around `handle`, faults from the command line |
| `transport.py` | `mock_transport(state)`: `httpx.MockTransport` over the same `handle`, for client tests |
| `badges.py` | prints a sheet of mock-badge QR codes (`code:validator`) for the P3 exit test (one dev-only QR library, e.g. `segno`; D-75) |
| `README.md` | the contract: endpoints, envelopes and fields citing `pycon-api.ts` by line, plus what is **unknown** (server idempotency, the timestamp window) and how the mock models it |
| `tests/fixtures/mock/` | seed data: one account per role, sponsors, products, attendees with badges (the Ionic signing vectors are in `tests/fixtures/ionic/signing.json`) |

`handle` checks the route, then for signed routes: unknown key → 401; timestamp outside the window (600 s per the 2019 API docs, UNCONFIRMED) or wrong signature (`hmac.compare_digest` against `sign(secret, ts, method, raw_path, body)`) → 403. The mock never proxies or points at PSF hosts, and nothing test-only lives in the app.

`transport.py` wraps `handle` in `httpx.MockTransport`: a `connect` fault raises `httpx.ConnectError` before `handle` runs; a `lost-response` fault runs `handle` (the server commits) and then raises `httpx.ReadError`. Signatures are checked against `request.url.raw_path`, exactly as sent.

**Scenarios (D-57):** connection refused (tries not counted); committed-but-lost response (no duplicate lead); revoked key (sign-in prompt, rows wait); clock skewed by 900 s (one corrected retry); account or sponsor switch mid-queue (rows keep their snapshot); `MockState(capture="idempotent" | "non_idempotent")`, since client dedupe cannot prove server exactly-once.

---

## 12. Staff tools: outbox, sync and scanning (P3; D-56, D-65)

### 12.1 Outbox (`OUTBOX_V1` in `services/storage.py`)

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
    idem_key     TEXT                           -- door: code|sorted product ids|scan session
);
CREATE INDEX IF NOT EXISTS outbox_due ON outbox (owner, status, next_at);
CREATE INDEX IF NOT EXISTS outbox_key ON outbox (owner, kind, key);
CREATE UNIQUE INDEX IF NOT EXISTS outbox_idem ON outbox (idem_key) WHERE idem_key IS NOT NULL;

-- due rows: a note waits until its lead is synced
SELECT o.* FROM outbox o
WHERE o.owner = :owner AND o.status = 'pending' AND o.next_at <= :now
  AND (o.kind <> 'note' OR EXISTS (SELECT 1 FROM outbox l WHERE l.owner = o.owner AND l.kind = 'lead'
                                   AND l.key = o.key AND l.status = 'synced'))
ORDER BY CASE o.kind WHEN 'lead' THEN 0 WHEN 'door' THEN 1 ELSE 2 END, o.created_at;
```

Synced rows are kept: lead dedupe and door "Already checked in" read them. On an account switch, the previous owner's synced rows are deleted; their pending or failed rows stay (visible in Developer) until synced or cleared with confirmation.

### 12.2 Transitions (`core/outbox.py`, pure; hypothesis state-machine tests)

| From | Event | To | Effect |
|---|---|---|---|
| — | lead scan; a synced row exists for (owner, code) | — | "Already in your leads", no new row |
| — | lead scan; a pending row exists | pending | `next_at = now`, kick |
| — | lead scan otherwise | pending | snapshot sponsor, kick |
| — | note saved (non-empty) | pending | upsert one note per (owner, code) |
| — | door admit | pending | unique `idem_key`; one row per check-in |
| pending | sent | synced | result merged into the payload |
| pending | `NetworkError` | pending | tries unchanged, `next_at = now + 60`, end the pass |
| pending | `ApiError` | pending → failed | `tries += 1`, `last_error`; failed at 10 counted failures |
| failed | "Retry failed" | pending | `tries = 0`, `next_at = now` |

Invariants (property tests): no pending row lost; owner and sponsor fixed at enqueue; synced rows never re-sent; a note never precedes its lead. Swag pickup and CoC capture are **online-only** and say so before scanning.

### 12.3 `SyncWorker` (`services/sync.py`)

```python
# src/pycon_us/services/sync.py (excerpt)
class SyncWorker:
    """The only sync loop for staff records: every 60 s, on reconnect, on resume and on "Sync now"."""

    def __init__(self, db: OutboxDb, api: ApiClient, account: Account, staff: Staff):
        self._db, self._api, self._account, self._staff = db, api, account, staff
        self._wake = asyncio.Event()

    def kick(self) -> None:
        self._wake.set()

    @report_errors
    async def drain(self) -> None:
        """Send due rows in order; stop at the first network failure."""
        if not self._account.signed_in or self._staff.syncing:
            return
        self._staff.syncing = True
        try:
            owner = self._account.owner
            for row in self._db.due_rows(owner, time.time()):
                try:
                    result = await send(self._api, row)
                except NetworkError:
                    self._db.save(outbox.after_network_error(row, time.time()))
                    break
                except ApiError as error:
                    self._db.save(outbox.after_error(row, error.message, time.time()))
                else:
                    self._db.save(outbox.after_success(row, result))
            self._staff.update_counts(self._db.counts(owner))
        finally:
            self._staff.syncing = False
```

`run()` loops forever on `asyncio.wait_for(self._wake.wait(), timeout=60)` then `drain()`; an App effect with a cleanup starts it, so unmount cancels it (F2). `send()` is a `match row.kind` over `lead_capture`, `lead_note` and `redeem`. `ft.Connectivity(on_change=...)` kicks the worker when connectivity becomes anything but `NONE`; so do RESUME, every enqueue and "Sync now".

### 12.4 Staff gating (D-16, D-54; exhaustive truth-table test)

`staff_entries(flags)` (pure) drives the More "Staff tools" section and the Now card.

| Entry | Rule |
|---|---|
| Lead scanner | `lead_retrieval or door_check` |
| Door check, Swag pickup | `door_check` |
| CoC capture | `mask_violation` |
| "Scan on behalf of" sponsor picker | `door_check and not lead_retrieval` |
| Default start screen "Lead scanner" (applied after the account is restored) | `lead_retrieval` |
| Staff section and Now card | any entry above |

Each staff screen re-checks its rule ("Not available for this account"), so deep links cannot bypass it.

### 12.5 Badges, admission and the scan surface

- `parse_badge(raw)`: code = segment 0; validator = segment 1 for door and swag, the **last** segment for lead; CoC sends the code only (LEAD-03). `decide(code, products, inventory, kept_rows)` admits optimistically; an unknown badge falls back to `fetch_products` online, "Entry not permitted" offline (DOOR-04).
- One `ScanScreen` for all four tools (D-65): the E1 preview when `capabilities.SCANNER`; a manual `TextField(on_submit=...)` for the `code:validator` payload, which HID scanners also type; one accepted result per code every 4 s; outcomes as colour, icon and word, with haptics and a `Semantics(live_region=True)` panel; the screen stays awake while mounted (an `async def` effect awaits `svc.wakelock.enable()`; its **sync** cleanup calls `ft.context.page.run_task(svc.wakelock.disable)`, rule 3); camera permission via `await svc.permissions.request(Permission.CAMERA)` after a primer.

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


def _bundled(module: str) -> bool:
    return is_embedded() and find_spec(module) is not None


SECURE_STORAGE = _bundled("flet_secure_storage")
PERMISSIONS = _bundled("flet_permission_handler")
REMINDERS = _bundled("flet_local_notifications")    # E3 (flet-dev/flet#6948): module name is a placeholder
SCANNER = _bundled("flet_barcode_scanner")          # E1, not published yet: module name is a placeholder
```

| Constant | Owner module | Interim |
|---|---|---|
| `REMINDERS` (E3) | `services/reminders.py` | "Not available in this build", Now's next-session card, in-app Banner, `.ics` alarms (D-60) |
| `SCANNER` (E1) | `services/scanner.py` | manual and HID entry (always available anyway) |
| `SECURE_STORAGE` | `services/storage.py` | credentials kept in memory for the session |
| `PERMISSIONS` | reminders, scanner | the extension's own permission request |

`is_embedded()` is `FLET_PLATFORM is not None`, set by the build template, not by `flet run` (F14). The Developer screen shows these constants read-only (D-73); interims are exercised through `flet run` and the companion app, which is never embedded. A unit test per owner module checks the interim when not embedded.

---

## 14. Notifications and reminders (P2; D-58..D-62)

### 14.1 Plan, then apply

```python
# src/pycon_us/services/reminders.py (excerpt)
MAX_PENDING = 60                         # iOS keeps 64 pending notifications


@dataclass(frozen=True)
class Reminder:
    """One local notification to schedule."""

    id: int
    at: datetime
    title: str
    body: str
    route: str                           # opened on tap, e.g. "/my-schedule/session/42"


def plan(data: ConferenceData, favorites: Sequence[str], settings: ReminderSettings,
         events: Sequence[EventReminder], now: datetime) -> list[Reminder]:
    """Every future reminder the user asked for, soonest first, at most MAX_PENDING (pure)."""
    reminders = []
    for session in (data.sessions[i] for i in favorites if i in data.sessions):
        at = session.start - timedelta(minutes=settings.lead_minutes)
        if settings.lead_minutes and at > now:
            route = f"/my-schedule/session/{quote(session.id, safe='')}"
            reminders.append(Reminder(reminder_id(session.id), at, session.name, session.display_location, route))
    reminders += [Reminder(e.id, e.at, e.title, e.body, "/now") for e in events
                  if settings.wants(e.category) and e.at > now]
    return sorted(reminders, key=lambda r: r.at)[:MAX_PENDING]
```

`apply(plan)` cancels all and schedules the plan (idempotent, inexact by default), re-run when favourites, settings or the feed change. Its scheduling calls *(not in Flet yet: E3, flet-dev/flet#6948 plus scheduling)* live only here; until E3 is pinned, `apply` does nothing and the interim applies. `reminder_id()` is the numeric session id, or `1_000_000 + crc32(id) % 1_000_000` for synthetic ids; a test checks a year's plan for collisions with the 8000–8099 event ids. Taps open `route` (§5.6), cold start included; S6 settles killed-app delivery, reboot, denied exact alarms and the 64-notification limit.

### 14.2 Interim while the app is open

`App` owns one `ft.use_dialog` slot for an in-app reminder `Banner` ("Open", "Dismiss"), set by a foreground-only 60 s loop from `plan()`. The actions clear that state, so the Banner closes by re-render, never by `page.pop_dialog()` (which could close a newer dialog).

### 14.3 Permissions (D-61) and calendar (D-62)

Permissions are asked in context after a one-sentence primer: notifications on the first favourite or the first reminder switch, the camera on the first staff scan, never at launch. After a denial, Settings shows a `Banner` with "Open settings" (`await svc.permissions.open_app_settings()`). Notification permission is requested through E3's `request_permission()` on both platforms; `flet-permission-handler` checks status, opens settings and handles the camera (D-61, F17).

`core/ics.py` builds `.ics` bytes (UTC times, stable `UID`, escaping, 75-octet folding, a `VALARM` at the lead time) for one session or all of My schedule, shared with `await svc.share.share_files([ft.ShareFile.from_bytes(data, mime_type="text/calendar", name=f"{slug}.ics")], share_position_origin=...)` (a non-empty list; the origin, an `ft.Offset` at the tapped control, anchors the sheet on tablets, D-09, D-62). Native add-to-calendar *(not in Flet yet: E4)* comes later.

---

## 15. Theming (D-22..D-28, D-33, D-34)

```python
# src/pycon_us/theme.py (excerpt; P0 has LIGHT_SCHEME and DARK_SCHEME, P2 adds the HC ones)
SEED = "#3B3EA9"
LIGHT_SCHEME = ft.ColorScheme(primary="#3B3EA9", on_primary="#FFFFFF", secondary="#680579", on_secondary="#FFFFFF",
                              tertiary="#A1009A", on_tertiary="#FFFFFF", ...)   # + containers and surface text roles
DARK_SCHEME = ft.ColorScheme(primary="#BFC1FF", on_primary="#1F2189", secondary="#F4AEFF", on_secondary="#52005E",
                             tertiary="#FFACEB", on_tertiary="#5E0058", ...)
HC_LIGHT = ft.ColorScheme(primary="#4A0072", on_primary="#FFFFFF", surface="#FBFAF6", on_surface="#1A1D24")  # P2, + all roles
HC_DARK = ft.ColorScheme(primary="#FFD60A", on_primary="#0B0F17", surface="#0B0F17", on_surface="#F5F5F0")   # P2, + all roles
THEME_MODES = {"system": ft.ThemeMode.SYSTEM, "light": ft.ThemeMode.LIGHT, "dark": ft.ThemeMode.DARK}


def build_theme(*, dark: bool, high_contrast: bool) -> ft.Theme:
    """The one Material 3 theme, identical on Android and iOS (D-10, D-22)."""
    if high_contrast:                                   # P2; until then the standard scheme
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
        system_overlay_style=overlay_style(dark=dark),        # D-12, D-113, #311
    )
```

- Until P2 (THEME-04, THEME-05), `high_contrast=True` returns the standard scheme, so callers already pass the flag.
- `overlay_style(*, dark)` returns the `Theme.system_overlay_style` (D-12): light status- and navigation-bar icons on dark schemes, dark icons on light ones, a transparent status bar, a navigation bar in the `NavigationBar`'s colour (`SURFACE_CONTAINER`, D-151) and navigation-bar contrast **not** enforced (D-113), so Android's 3-button icons sit on the `NavigationBar`'s colour and never on a dark scrim (#311), also below Android 15, where the app is not drawn under the bar. S1 checked it with 3-button and gesture navigation, in light and dark; #71 again on Android 14 and 16, including a dark-mode switch while the app runs.
- `apply_theme(page, prefs)` sets `page.theme` and `page.dark_theme` from `build_theme()`, `page.theme_mode` from `THEME_MODES[prefs.theme]`, then `page.update()`.
- Flet builds `ColorScheme.fromSeed`, neutralises surfaces, then applies our overrides (F9): light and dark set the brand roles and their containers, each with its `on_*` partner, plus `surface`, `on_surface` and `on_surface_variant`, which repeat Flet's neutral ramp so the contrast test sees them; HC overrides every role, with `surface_container*` = `surface`. `Prefs.high_contrast_on` is `"on"`, or `"system"` with the OS flag (iOS, Android 34+; re-read on resume, F13); `Prefs.dark` resolves `"system"` with `os_dark`.
- **Values** come from `docs/ux.md` and are mirrored in `theme.py`: full HC schemes (P2); `Tokens` (D-24: `live`, `warning`, `success`, `favorite`; `build_tokens(*, dark, high_contrast)` picks them, `App` provides them through `TokensCtx` and screens read them with `use_tokens()`, D-150); track badges (P1-02; D-25: a tonal pair per track key and brightness, at least 4.5:1, outlined in HC; "En Español" the tonal pair `#FFD7F3` / `#5E0058` in light, inverted in dark). `tests/test_theme.py` checks every text/background pair in light and dark (HC from P2), and the text roles and tokens on every surface of Flet's neutral ramp.
- **Markdown:** `MARKDOWN_STYLE` is the one `ft.MarkdownStyleSheet` of D-116, passed to every `ft.Markdown(md_style_sheet=...)`. Its colours are scheme roles (`PRIMARY`, `ON_SURFACE`, `SURFACE_CONTAINER_HIGHEST`, `OUTLINE`), resolved against the theme on screen, so one constant serves every scheme; every text style in it names its colour (F28), its font family and, for links and strike-through, its decoration colour (D-152).
- **Type** (D-26, D-33): only the M3 scale (`ft.Text(theme_style=ft.TextThemeStyle.TITLE_MEDIUM)`), no fixed heights around text, reflow at 200 %. **Roboto:** `page.fonts` takes one static file per family, so 500/700 would be synthetic; declare the family's 400/500/700 files through `[tool.flet.flutter.pubspec]` (F18), verified in S5 (D-26).
- **Icons** (D-27): Material Icons only, outlined unless selected; icon-only buttons have a tooltip (their accessible name). **Motion** (D-34): M3 durations; with `prefs.reduce_motion`, durations drop to 0 and pulses are static. **iOS pins** (D-10): bundled font, `center_title=False`, Material back arrow, never `adaptive=True`; the Cupertino transition and bounce scrolling stay native.

---

## 16. Errors, logging and diagnostics (D-71, D-72)

### 16.1 Expected failures at explicit boundaries

| Failure | Boundary | Becomes |
|---|---|---|
| Feed: offline or timeout | `Conference._refresh` | `problem = "offline"`; data kept |
| Feed: HTTP error, bad JSON, `FeedError` | `Conference._refresh` | `problem = "server"`; data kept; logged |
| Corrupt cache | `Conference.load_local` | cache deleted, snapshot shown, logged |
| Storage read or write fails | `services/storage.py` | logged; `False` or `None` returned; the previous file and the data in memory kept (D-120) |
| Unreadable preference | `Prefs.load` | its default; logged (bad year data is a build bug: the loader test fails) |
| Share, URL, clipboard failure | the handler | SnackBar "Couldn't open the link" / "Couldn't share" |
| Permission denied | permission flows | `Banner` with "Open settings"; the task continues |
| `NetworkError`, `ApiError` (P3) | `Account`, `SyncWorker`, staff screens | inline errors, queued rows, "Retry failed" |

### 16.2 Unexpected exceptions: `report_errors`

An exception in an event handler (or a sync effect) ends the session; one in an async effect reaches only asyncio (F4). Until Flet makes handler errors non-fatal *(not in Flet yet: U15)*, handlers and effects are wrapped:

```python
# src/pycon_us/services/errors.py (excerpt)
logger = logging.getLogger("pycon_us")
_show_details = False


def report_errors(fn):
    """Log an unexpected exception from a handler or effect and tell the user, instead of ending the session.

    Keeps the signature (Flet counts handler parameters through __wrapped__) and the async-ness (F2).
    CancelledError always propagates. Delete once U15 is in the pinned Flet.
    """
    where = f"{fn.__module__}.{fn.__qualname__}"
    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def run_async(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                _report(where, error)

        return run_async

    @functools.wraps(fn)
    def run(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as error:
            _report(where, error)

    return run


def _report(where: str, error: Exception) -> None:
    logger.error("Unexpected error in %s", where, exc_info=error)
    text = f"Something went wrong: {error}" if _show_details else "Something went wrong."
    ft.context.page.show_dialog(ft.SnackBar(content=ft.Text(text), behavior=ft.SnackBarBehavior.FLOATING))
```

A last-resort net, not error handling (§16.1). Details show when not embedded or with Developer unlocked; review checks wrapping (no lint, D-71).

### 16.3 Logging

`setup_logging()` sends stdlib `logging` to stderr at INFO plus an asyncio exception handler; packaged apps capture it in `console.log` (F14). Feed processing logs its duration (D-80). **Never log** secrets, keys, signatures, emails or badge codes. "Share log" shares `ft.ShareFile.from_path(await svc.paths.get_console_log_filename())`. No Sentry, no analytics.

---

## 17. Developer screen (D-73)

`/more/developer`: always reachable when not embedded; in packaged builds, 7 taps on the version row in About this app. Fake clock (`dev.fake_now`, runs forward), feed URL override, mock API URL (enables P3), capability flags (read-only), refresh or clear the cache, show Welcome again, test reminder (P2), clear synced staff records (P3), share log, reset app. Destructive actions are confirmed.

---

## 18. Spikes this design depends on, and the API ledger

| Spike | Confirms |
|---|---|
| S1 | **Done** (`docs/spikes/01-packaged-runtime.md`): data dir survives updates (D-108); `tzdata`, `httpx`, `sqlite3`, SecureStorage on device; parsing stays on the loop (D-109); overlay style and insets (D-113). Page handlers firing without `page.update()` moved to S4 |
| S2 | row architecture; `build_controls_on_demand=False` per day list so `scroll_to(scroll_key=...)` reaches unbuilt slots (F7) |
| S3 | **Done** (`docs/spikes/03-html-markdown.md`): the converter covers both feeds' 17 tags with no text change; escaping (D-115) and the style sheet (D-116); E5 cut (D-117) |
| S4 | **Done** (`docs/spikes/04-router-back.md`): the drill shape and per-level params (D-141); every pop through our `on_view_pop` (D-141); D-17's root rule (D-142); one root View key (D-142); the bar on roots only (D-144); `ViewMemory` per process with the start route restoring the location (D-143); a replaced session stops its work from `page.on_close` (D-147); page handlers without `page.update()` (D-147); transitions (D-148). The iOS edge swipe is held for #121 |
| S5 | the pinned Flet 1.1 build; Roboto weights through the pubspec; both deep-linking tables |
| S6, S7, S8 | E3 reminders; floor plans in `InteractiveViewer`; E1 scanning |

**Not in Flet yet, and the interim:** `RefreshIndicator` (U1 → strip Refresh plus automatic refresh); sticky headers (U2 → time gutter per slot); absolute `InteractiveViewer` transform (U3 → highlight plus `reset`/`zoom`/`pan`); `page.get_app_info()` (U4 → `__version__`); `use_route_search` (U9 → `use_query()`); Router Back inside a modal sub-chain (U18 → our `page.on_view_pop` with `parent_of()`, D-19); a shell bar outside the `Navigator` (U23 → the bar on roots only, D-144); unmounting a replaced session (U24 → `page.on_close` stops our loops, D-147); `AppBar.bottom` (U10 → day tabs as the first body row); non-fatal handler errors (U15 → `report_errors`); `PageMediaData.text_scale_factor` (U16 → fluid layouts); an accessibility change event (U17 → re-read on resume); scheduled notifications (E3 → §14.2); barcode scanner (E1 → manual and HID entry); native calendar (E4 → `.ics`); HTML (`html_md`; E5 cut, D-117); LaTeX always on in `Markdown` (U21 → escaping, D-115); a style sheet that replaces the theme's styles (U22 → explicit colours, D-116); multi-weight families in `page.fonts` (→ pubspec fonts).

---

## 19. Discrepancies with PLAN.md and decisions.md

This file follows the right-hand column; each open row needs a `needs-decision` issue or an amendment in the implementing PR. Row numbers are stable ids (other docs cite them) and are never reused. Resolved in the decisions record on 2026-10-11, so retired: #1 search (D-19), #2 the `plan/<plan>` drill kind (§M), #3 the change-log path (§M; matrix NEW-04), #4 Roboto (D-26), #5 positions in `ViewMemory` (D-18), #7 the P3 storage keys (§M), #8 no parser-version key (D-47), #9 `services/api.py` from P0 (PLAN §5), #10 the mock's `transport.py` and `badges.py` and the QR library (D-50, D-75, §M). Resolved by S4 on 2026-10-12: #6 the bar on detail Views (D-144, #149: roots only).

No rows are open.
