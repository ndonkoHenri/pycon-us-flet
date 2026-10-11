# Architecture: PyCon US 2027 app on Flet

**Status:** companion to [`PLAN.md`](../PLAN.md) §5, 2026-10-11. **For:** the implementer. **Covers:** modules, routes, stores, data pipeline, API, storage, outbox, staff tools, theming, capabilities, errors, schemas, DEMO.

- PLAN.md records decisions; this file records how to build them. Where the two differ, §18 says so.
- `D-nn` are entries of the decisions record ([`decisions.md`](decisions.md), D-01..D-136) PLAN.md was built from. Feature ids (`SCHED-16`, …) are rows of [`feature-matrix.md`](feature-matrix.md).
- Every Flet API named here was checked in the local monorepo (1.1.0-dev) on 2026-10-11. APIs that **do not exist yet** are always tagged with their upstream item (`U1`–`U15`, `E1`–`E6`) and interim. §17 is the ledger.
- Code blocks are sketches: imports, copy and styling are trimmed.

---

## 0. Ground rules (PLAN §3.6, decisions §N, verified in the SDK)

Ground rules are numbered `GR-1`..`GR-10`; `R1`–`R15` are PLAN §12 risks (decisions §M).

| # | Rule | SDK fact behind it |
|---|---|---|
| GR-1 | Await coroutine APIs (`*` in §17: `page.show_drawer/close_drawer/push_route`, `scroll_to`, `zoom/pan/reset`, `confirm_dismiss`, and every service method) only in `async def` handlers/effects. `page.navigate(route, **query)` and `page.show_dialog()` are sync. | `inspect.iscoroutinefunction`; `navigate` wraps `asyncio.create_task(push_route(…))` |
| GR-2 | `ft.use_effect(setup)` makes a task only when `setup` is a coroutine function (a bound `async def` method qualifies). A lambda returning a coroutine never runs. | `session.py` effect runner |
| GR-3 | Long-running async effects pass `cleanup=` (`NOOP` is enough). The runner cancels the setup task before a re-run and before cleanup, but on unmount it acts **only if `cleanup` is callable**. | `Component._run_unmount_effects` |
| GR-4 | One context per `@ft.observable` store, read through typed hooks; never a container of stores in one context. | `use_context` subscribes only if the value is an `Observable`; nested observables don't propagate |
| GR-5 | Hooks are positional. Every `use_*`, `use_route_*`, `is_route_active`, `use_dialog` and `shell_view()` is called unconditionally, before any branch. Compute first, return once. | `Component.use_hook` |
| GR-6 | `@safe` on every handler and effect (§15); handlers are named `def`s, lambdas only bind arguments. | handler/sync-effect error → `SESSION_CRASHED`; async effect errors only reach asyncio |
| GR-7 | Never mutate a store from a thread; `asyncio.to_thread` returns values, the loop assigns. | `Component._schedule_update` uses `ft.context.page` |
| GR-8 | Big immutable store values are `@dataclass(frozen=True, eq=False)` with id references, no cycles. | `Observable.__setattr__` runs `old == new` before notifying: deep compares are slow, cycles recurse to `RecursionError` |
| GR-9 | `core/` never imports `flet` (lint). | PLAN §5.1 |
| GR-10 | Several field writes in one synchronous block give one re-render per subscriber. | `session.schedule_update` collects into a set |

---

## 1. Module layout (PLAN §5.1, decisions §M)

| Module | Responsibility |
|---|---|
| `src/main.py` | `ft.run(lambda page: page.render_views(App))` |
| `app.py` | `App`: create stores once, run bootstrap, show the boot View until `Prefs.loaded`, provide contexts, mount `ft.Router` |
| `routes.py` | `ROUTES`, `session_route()`, `drill_route()`, `href()`, `drill_href()`, `open_floor_plan()`, `use_query()`, `guarded()`, `IndexRedirect`, `ShortLink`, `Drill`, `NotFound` |
| `settings.py` | `Settings`: env, YEAR, CONF_TZ, site/API/config URLs, key prefix `pycon.<env>.`, DEV, DEMO, FAKE_NOW; dev base URL `10.0.2.2:8000` on the Android emulator (DEV-07, DATA-34) |
| `build_info.py` | CI-generated (dev stub committed): `VERSION`, `BUILD_NUMBER`, `GIT_SHA`, `TARGET`, `CAPS`, `PYCON_ENV`, `DEMO`, `CAPS_OVERRIDE`, plus `YEAR`, `CONF_TZ`, `SITE_URL` from `config/conference.json` (D-125, §18 #8) |
| `core/` (no Flet) | `feed` (decode, contract guards), `process` (§5.1), `models` (frozen dataclasses), `queries` (§5.2), `timefmt` (§5.3), `slugs` (§5.5), `html_md` (§5.4), `ics`, `badges`, `signing` (§7.1), `admission` (§10.2), `outbox` (§9), `changelog` (§5.6) |
| `api/` (no Flet) | `transport` (`HttpxTransport`, `PyfetchTransport`), `endpoints` (§7.2), `errors`, `client` (§7.3) |
| `stores/` | `__init__.py` `Stores` (create, bootstrap, shutdown, lifecycle); one module per store (§4); `contexts.py` |
| `services/` | `storage` (prefs, SecureStorage, files, sqlite), `bootstrap` (§4.4), `sync_worker` (§9.2), `safe` (§15.1), `crash` (§15.2), `bridge_import` (OD-8) |
| `platform/` | `caps.py` (`Caps`, probes, `select_providers`); `scanner/ push/ reminders/ calendar/ analytics/ app_info/`: protocols + implementations; the only code that imports extensions, lazily |
| `ui/` | `shell.py` (`shell_view`, `DrawerContent`, `BottomChrome`, `MenuButton`, `SponsorBanner`, `StaffSheet`), `components/` (`SessionRow`, `NoticeRow`, `TrackBadge`, `HeroPage`, `LocationCard`, `FloorPlan`, `Refreshable`, `TopToast`, `Skeleton`), `theme/` (`brand`, `tokens`, `themes`) |
| `screens/<area>/` | one package per area; `staff/{lead,door,swag,coc}` |

---

## 2. Entry point, App, contexts

```python
# src/pycon_us/app.py
@ft.component
def App():
    # Built once inside the page context: every ft.Service created in Stores.create() registers with this page.
    s = ft.use_memo(lambda: Stores.create(ft.context.page), [])
    prefs, _ = ft.use_state(s.prefs)                     # use_state subscribes App to an Observable value
    ft.use_effect(s.bootstrap, [], cleanup=s.shutdown)   # async bound method → task (GR-2); shutdown stops tasks (GR-3)
    if not prefs.loaded:                                 # boot gate (PLAN §5.3): hooks above stay unconditional (GR-5)
        return [BootView(route=ft.context.page.route or "/")]      # #680579, same as the splash
    return provide_stores(s, lambda: ft.Router(ROUTES, not_found=NotFound, manage_views=True))
```

The gate keeps the default theme and filters from flashing on any entry URL, deep links and web URLs included: the Router mounts only after bootstrap step 1, reading `page.route` then. `App` sits above the providers, so it cannot use `use_prefs()`; `ft.use_state(s.prefs)` is the subscribing hook instead. It re-renders `App` on every `Prefs` change, which is rare and user-driven. Bootstrap sets `prefs.loaded = True` only after the theme is applied (§4.4).

```python
# src/pycon_us/stores/contexts.py
FeedCtx = ft.create_context(None)
CapsCtx = ft.create_context(None)
# … AppConfigCtx, ContentCtx, AuthCtx, FeaturesCtx, PrefsCtx, FavoritesCtx, StaffCtx, OutboxCtx,
#   BannersCtx, ChangeLogCtx: one per store
ServicesCtx = ft.create_context(None)   # not a store: frozen Services bundle, never changes


def _use(ctx, name):
    value = ft.use_context(ctx)           # subscribes because the value is an Observable (GR-4)
    if value is None:
        raise RuntimeError(f"{name}() used outside provide_stores()")
    return value


def use_feed() -> FeedStore: return _use(FeedCtx, "use_feed")
def use_caps() -> Caps: return _use(CapsCtx, "use_caps")
# use_app_config, use_content, use_auth, use_features, use_prefs, use_favorites, use_staff,
# use_outbox, use_banners, use_changelog, use_services: same two lines each


def provide_stores(s: "Stores", render):
    chain = [(FeedCtx, s.feed), (AppConfigCtx, s.app_config), (ContentCtx, s.content), (AuthCtx, s.auth),
             (FeaturesCtx, s.features), (PrefsCtx, s.prefs), (FavoritesCtx, s.favorites), (StaffCtx, s.staff),
             (OutboxCtx, s.outbox), (BannersCtx, s.banners), (ChangeLogCtx, s.changelog), (CapsCtx, s.caps),
             (ServicesCtx, s.services)]

    def nest(i):
        if i == len(chain):
            return render()
        ctx, value = chain[i]
        return ctx(value, lambda: nest(i + 1))      # provider(value, callback)

    return nest(0)
```

`Services` is a frozen bundle (prefs, secure, paths (`None` on web), connectivity, url, share, clipboard, haptics, semantics, permissions, api, settings). Screens never construct services: a `Service` built in a handler registers a new instance each time.

---

## 3. Routing and navigation (PLAN §5.2, D-30..D-43)

### 3.1 Router behaviour this design relies on (`components/router.py`)

- Routes match in order; a route with children tries them first, then its own exact match. So `tracks/open-spaces` precedes `tracks/:track_slug`.
- With `manage_views=True` every matched route **with a component** is one View; component-less groups (`app/tabs`) emit none. No `outlet=True` layouts here (D-32).
- `recursive=True` gives one match per segment, trying non-recursive children first; per-level params accumulate, so a deeper `ref` overrides a shallower one.
- Params are raw, percent-encoded segments: `unquote` every id. Verified: `/…/session/break--2026-05-13T12%3A30%3A00-07%3A00` → `session_id="break--2026-05-13T12%3A30%3A00-07%3A00"`.
- A top-level `modal=True` route is **global** (base rebuilt from the last non-modal path); a modal child is **local** (base = parent chain). Closing navigates to the last non-modal entry's resolved URL.
- The default `on_view_pop` navigates to the previous entry's resolved path and drops the query (good for #313). The app never sets `page.on_view_pop`.
- `not_found()` is wrapped as `[View(route=pathname, controls=[not_found()])]`, so `NotFound` returns content. `use_route_location()` is pathname only (no `use_route_search` until U9). Under a global modal, `page.route` is the modal URL, so `use_query()` in base views sees the modal's query.

### 3.2 Route table

Paths under the component-less group `app/tabs`. Tab lit = first segment after `/app/tabs/` (D-39). Guards also apply app-config kill switches (D-83); a failed guard renders "Not available for this account".

| Path | Component | Kind | Tab lit | Guard | Ids |
|---|---|---|---|---|---|
| `/` and `app/tabs` index | `IndexRedirect` | redirect (boot View) | – | – | SHELL-03, AUTH-08 |
| `/tutorial` | `Welcome` | root, no shell, `can_pop=False` | – | – | SHELL-02 |
| `/floor-plan/:plan?pin=<key>&back=<path>` | `FloorPlanModal` | **global modal** | – | – | INFO-13, ROOM-05, MAP-05, SESS-10 |
| `/s/:id`, `/p/:id`, `/r/:slug` | `ShortLink` | redirect | – | – | D-38 |
| `/login`, `/account` (top level, Ionic `app-routing`) | `ShortLink` | redirect to `/app/tabs/login` / `/app/tabs/account` | – | – (the target applies its guard) | D-31 |
| `schedule` | `Schedule` | root | Schedule | – | SCHED-01..20 |
| `schedule/filter` | `ScheduleFilter` | local modal | Schedule | – | SCHED-09/10 |
| `schedule/changes` | `ScheduleChanges` | child | Schedule | – | #312 |
| `schedule/session/:session_id` (+drill) | `SessionDetail` | child | Schedule | – | SESS-01..12 |
| `now` (+`session/:session_id`+drill) | `NowNext` / `SessionDetail` | root/child | Now | – | SCHED-25/26 |
| `speakers` | `Speakers` | root | Speakers | – | SPKR-01/02 |
| `speakers/speaker-details/:speaker_id` (+drill) | `SpeakerDetail` | child | Speakers | – | SPKR-03 |
| `keynote-speakers` (+session+drill) | `KeynoteSpeakers` | root/child | – | – | SPKR-04 |
| `tracks/open-spaces` | `OpenSpaces` | root | – | – | EVT-01/02 |
| `tracks/:track_slug` (+session+drill) | `TrackPage` | root/child | – | – | SCHED-21..24 |
| `rooms` | `Rooms` | root | – | – | ROOM-01 |
| `rooms/room-detail/:room_slug?session=` (+drill) | `RoomDetail` | child | – | – | ROOM-02..04 |
| `speakers/session/:session_id`, `rooms/session/:session_id` (+drill) | `SessionDetail` | child | Speakers / – | – | URL parity |
| `conference-map` | `ConferenceMap(initial_view="floor-plans")` | root | Map | – | MAP-01..04 |
| `expo-hall?booth=N` | `ConferenceMap(initial_view="expo-hall")` | root | – | – | EXPO, SPON-04 |
| `sponsors` (+`sponsor-detail/:sponsor_id`) | `Sponsors` / `SponsorDetail` | root/child | – | – | SPON-01..05 |
| `job-listings` | `JobListings` | root | – | – | SPON-06..10 |
| `sprints` | `Sprints` | root | – | – | EVT-05..08 |
| `venues-hours` | `VenuesHours` (info screen) | root | – | – | MAP-09..11 |
| `lightning-talks`, `session-types`, `about-pycon`, `about-psf`, `coc`, `wifi`, `social-media`, `help` | info screens | root | – | – | EVT-03/04, INFO-01..12 |
| `notifications` | `NotificationSettings` | root | – | – | NOTIF-01..11 |
| `login` | `Login` | root | Login | – | AUTH-01 |
| `account` | `Account` | root | – | logged in | AUTH-09/10 |
| `lead-retrieval` (+`note/:code` local modal) | `LeadScanner` / `LeadNote` | root/modal | **Scanner** | `lead_retrieval or door_check`; kill `lead_retrieval` | LEAD |
| `door-check` | `DoorCheck` | root | – | `door_check`; kill `door_check` | DOOR |
| `t-shirt-redemption` (+`redeem` local modal) | `SwagPickup` / `RedeemProducts` | root/modal | – | `door_check`; kill `swag` | SHIRT |
| `mask-violation` | `CocIncident` | root | – | `mask_violation`; kill `coc` | MASK |
| `dev-tools` | `DevTools` (always declared, behind `Guard`) | root | – | `settings.DEV or prefs.dev_unlocked` | DEV-01 |
| other | `NotFound` | `not_found` | – | – | – |

Tab order (Ionic): Speakers, Map, Schedule, Now, then Scanner or Login (they never coexist). Map lights only on `conference-map`; Scanner only on `lead-retrieval`.

**Staff gating truth table** (D-41; test `test_AUTH_05_gating_truth_table`; `door_check` = server `features.door_check_in`):

| Entry point | Rule |
|---|---|
| Scanner tab opens the Staff sheet | `door_check or mask_violation` |
| Scanner tab navigates to `lead-retrieval` | `lead_retrieval and not door_check and not mask_violation` |
| Door Check, Swag Pickup (sheet, drawer) | `door_check` |
| Lead Scanner (sheet, drawer) | `lead_retrieval or door_check` |
| CoC Incident | `mask_violation` |
| "Scan on behalf of" picker (`is_staff_scanner`) | `door_check and not lead_retrieval` |
| Launch / post-login redirect to Lead Scanner | `lead_retrieval` only (D-42) |
| Login tab / drawer "Apps" header | `not logged_in` / any flag (live, not sticky: SHELL-11) |

### 3.3 `routes.py`

```python
def drill_route() -> ft.Route:                      # child of every session/speaker/room detail (D-34)
    return ft.Route(path=":ref", recursive=True, component=Drill)


def session_route() -> ft.Route:                    # generated, never copy-pasted
    return ft.Route(path="session/:session_id", component=SessionDetail, children=[drill_route()])


def guarded(screen, rule, kill=None):
    @ft.component
    def Guard():
        f, a, p, cfg = use_features(), use_auth(), use_prefs(), use_app_config()   # fixed hook order (GR-5)
        return screen() if rule(f, a, p) and (kill is None or cfg.enabled(kill)) else NotAvailable()
    return Guard


LEAD = lambda f, a, p: f.lead_retrieval or f.door_check
DOOR = lambda f, a, p: f.door_check
DEV = lambda f, a, p: settings.DEV or p.dev_unlocked                  # DEV-01

ROUTES = [
    ft.Route(index=True, component=IndexRedirect),
    ft.Route(path="tutorial", component=Welcome),
    ft.Route(path="floor-plan/:plan", component=FloorPlanModal, modal=True),                 # global modal
    *[ft.Route(path=p, component=ShortLink) for p in ("s/:id", "p/:id", "r/:slug", "login", "account")],
    ft.Route(path="app/tabs", children=[                                                     # componentless
        ft.Route(index=True, component=IndexRedirect),
        ft.Route(path="schedule", component=Schedule, children=[
            ft.Route(path="filter", component=ScheduleFilter, modal=True),                    # local modal
            ft.Route(path="changes", component=ScheduleChanges), session_route()]),
        ft.Route(path="speakers", component=Speakers, children=[
            ft.Route(path="speaker-details/:speaker_id", component=SpeakerDetail, children=[drill_route()]),
            session_route()]),
        ft.Route(path="tracks/open-spaces", component=OpenSpaces),                           # before :track_slug
        # now, keynote-speakers, tracks/:track_slug: same shape (component + [session_route()])
        # rooms: like speakers with room-detail/:room_slug; conference-map / expo-hall: partial(ConferenceMap, …)
        ft.Route(path="lead-retrieval", component=guarded(LeadScanner, LEAD, "lead_retrieval"), children=[
            ft.Route(path="note/:code", component=guarded(LeadNote, LEAD, "lead_retrieval"), modal=True)]),
        ft.Route(path="t-shirt-redemption", component=guarded(SwagPickup, DOOR, "swag"), children=[
            ft.Route(path="redeem", component=guarded(RedeemProducts, DOOR, "swag"), modal=True)]),
        # door-check, mask-violation, account: guarded(...) per §3.2;
        # dev-tools: guarded(DevTools, DEV) (a Guard, always declared); rest: plain roots
    ]),
]


def href(*segments: str) -> str:
    return "/app/tabs/" + "/".join(quote(s, safe="") for s in segments)


def drill_href(view_path: str, kind: str, ident: str) -> str:          # kind ∈ s | p | r
    return f"{view_path.rstrip('/')}/{kind}~{quote(ident, safe='')}"


def open_floor_plan(plan: str, pin: str | None = None) -> None:     # call from a handler; §3.5
    page = ft.context.page
    page.navigate(f"/floor-plan/{quote(plan, safe='')}", **({"pin": pin} if pin else {}),
                  back=urlparse(page.route or "/").path)


def use_query() -> dict[str, str]:            # hook; interim for U9 ft.use_route_search()
    ft.use_route_location()                   # hook slot only (GR-5); re-render comes from the Router re-rendering
                                              # route components on any route change: never call use_query in a memoised component
    q = urlparse(ft.context.page.route or "/").query
    return {k: v[-1] for k, v in parse_qs(q).items()}
```

Lists open details with `page.navigate(href("schedule", "session", s.id))`. Query strings go in kwargs: `page.navigate(url, session=sid)` appends `?session=…`. Drawer destinations navigate to a root URL, which yields a one-View stack, so Back on a root exits (D-36).

### 3.4 Drill segment (D-34, SESS-12, #279)

```python
@ft.component
def Drill():
    kind, _, raw = ft.use_route_params().get("ref", "").partition("~")
    view_path = ft.use_view_path()                                       # hooks first (GR-5)
    ident = unquote(raw)
    if kind == "s":
        return SessionDetail(session_id=ident)
    if kind == "p":
        return SpeakerDetail(speaker_id=ident)
    if kind == "r":
        return RoomDetail(room_slug=ident)
    return ft.View(route=view_path, controls=[NotFound()])   # shared NotFound content (§3.1); no new name
```

Detail components take an optional prop and fall back to their route param (`sid = session_id or unquote(params.get("session_id", ""))`), so a drilled `SessionDetail` never reads the parent's `session_id`. The next hop is `drill_href(ft.use_view_path(), …)`.

| Step | URL | Stack |
|---|---|---|
| Schedule tab | `/app/tabs/schedule` | Schedule |
| session 42 | `…/schedule/session/42` | + Session 42 |
| speaker 17 | `…/session/42/p~17` | + Speaker 17 |
| their talk 99 | `…/p~17/s~99` | + Session 99 |
| room 102A | `…/s~99/r~room-102a?session=99` | + Room 102A, 99 highlighted and scrolled to once |
| poster row in that room | `…/r~room-102a/s~poster-detail-7` | + Poster 7 |
| Back | `…/s~99/r~room-102a` | previous entry's resolved path: no query, no re-highlight (#313) |
| Back ×4 | `/app/tabs/schedule` | Schedule, same instance (day, search, scroll kept) |
| Back on a root | app exits (Android) | system nav stays visible (#311) |
| collapsed break row | `…/session/break--2026-05-13T12%3A30%3A00-07%3A00` | ids quoted with `safe=""` |
| floor plan from Session 99 | `/floor-plan/1?pin=102a&back=…%2Fs~99` | base rebuilt from `…/s~99`; Back and Close return there (spike S9) |

### 3.5 Redirects and the global modal

```python
@ft.component
def IndexRedirect():
    prefs, auth, features = use_prefs(), use_auth(), use_features()
    page = ft.context.page

    @safe
    def go():
        if not (prefs.loaded and auth.restored):           # D-42: only after auth.restore()
            return
        if not prefs.did_tutorial:
            page.navigate("/tutorial")
        else:
            page.navigate(href("lead-retrieval") if features.lead_retrieval else href("schedule"))

    ft.use_effect(go, [prefs.loaded, auth.restored])
    return BootView(route=ft.use_view_path())             # #680579 + white ring, no AppBar
```

`ShortLink` maps `/s/:id`, `/p/:id`, `/r/:slug` to the session, speaker-details and room-detail URLs the same way, and Ionic's top-level `/login` and `/account` to `href("login")` and `href("account")`, where the target's own guard applies. There is no replace-navigation, so on web, browser Back onto `/` re-runs the redirect (spike S9 notes it).

```python
@ft.component
def FloorPlanModal():
    plan_id = ft.use_route_params().get("plan", "1")      # "1".."4", "job-fair"
    pin_key = use_query().get("pin")
    back = use_query().get("back", "")                    # opener's path, set by open_floor_plan()
    content, caps = use_content(), use_caps()
    box_w, set_box_w = ft.use_state(0.0)
    page = ft.context.page
    iv = ft.Ref()                                         # per-render Ref, as in the SDK declarative todo example
    plan, pin = content.plan(plan_id), content.pin(pin_key)

    @safe
    async def zoom_in():
        await iv.current.zoom(2.0)

    @safe
    def close():                                          # explicit button keeps the Ionic label (D-70)
        page.navigate(back if back.startswith("/app/tabs/") else href("conference-map"))

    @safe
    def on_size(e: ft.LayoutSizeChangeEvent):
        set_box_w(e.width)

    return ft.View(
        route=ft.use_view_path(), fullscreen_dialog=True,
        appbar=ft.AppBar(leading=ft.IconButton(ft.Icons.CLOSE, tooltip="Close floor plan", on_click=close),
                         title=ft.Text(plan.title)),
        controls=[ft.GestureDetector(on_double_tap=zoom_in, content=ft.InteractiveViewer(
            ref=iv, min_scale=1, max_scale=max(1.0, plan.width / box_w) if box_w else 4.0,
            content=FloorPlan(plan, pin, pulse=not caps.reduce_motion, on_size_change=on_size)))],
    )
```

Every entry point opens the plan with `open_floor_plan(plan, pin)` (`routes.py`), which calls `page.navigate(f"/floor-plan/{plan}", pin=pin, back=urlparse(page.route).path)` from the opener's handler. The opener is the last non-modal location, so `back` is the base the Router rebuilt under the modal, without its query (as on Back, #313). The system Back and the swipe pop through `on_view_pop`, where the Router navigates to the base URL it stamped when the modal matched. The explicit "Close floor plan" button (Ionic `aria-label`, kept verbatim per D-70) navigates to `back`; a deep link without one falls back to the Conference Map. It never reads `page.views`: under `render_views` that is the root `App` component (it would need `ft.unwrap_component`), and the Router documents that a modal pop never uses `views[-2].route`.

`FloorPlan` is a `Stack[Image, pin]` with the pin at `x% × rendered width`, so it zooms with the image (INFO-13). Local modals return `ft.View(route=ft.use_view_path(), fullscreen_dialog=True, …)` and read inputs from stores, never from URL payloads.

---

## 4. State (PLAN §5.3, D-44..D-47)

### 4.1 Stores (every field)

All are `@ft.observable @dataclass`. Fields starting with `_` hold collaborators and tasks and never notify. Persisted fields are listed with their prefs key in §8.1.

| Store | Fields | Ids |
|---|---|---|
| `FeedStore` | `conf: Conference \| None` (frozen, `eq=False`); `version: int` (memo key); `status: "boot"\|"cached"\|"fresh"\|"offline"\|"error"`; `fetched_at: float \| None`; `refreshing: bool`; `error: str \| None`; `_task` | DATA-01..03, SCHED-13/14 |
| `AppConfigStore` | `latest {version, build}`; `min_supported {ios, android, web}`; `store_urls`; `banners: list[dict]`; `features: dict[str, bool]` (veto: `False` disables, `True` = absent); `feed_url`, `content_url`; `staff_data_purge_after` (default conference end + 7 d = 2027-05-25); `update_available`, `update_required: bool`; `fetched_at`; `resumed_at: float` (bumped on RESUME; an effect dependency). Method `enabled(key)` | LIVE-02..04, NOTIF-04/08/12 |
| `ContentStore` | `content: AppContent` (frozen, `eq=False`; bundled copy loaded in `create`); `source: "bundled"\|"cache"\|"remote"`; `version: int`; helpers `plan()`, `pin()`, `keynotes_for()`, `reminders()` | SESS-08, DATA-32 |
| `AuthStore` | `restored`, `logged_in`, `login_in_flight: bool`; `email`, `nickname`, `login_error: str \| None`; `_key`, `_secret` (memory copies of SecureStorage) | STORE-03/04, AUTH-01/07 |
| `Features` | `lead_retrieval`, `door_check`, `mask_violation`, `is_speaker`, `scanner_consent: bool`; `refreshed_at`. Properties (not fields): `has_apps`, `is_staff_scanner`, `scanner_tab → "sheet"\|"lead"\|None` | STORE-05/06, AUTH-04/05 |
| `Prefs` | `loaded`, `did_tutorial: bool`; `theme: "system"\|"light"\|"dark"\|"high-contrast-light"\|"high-contrast-dark"` (default `system`, OD-6); `excluded_tracks: list[str] \| None` (`None` → `["Open Space"]`, `[]` kept); `notification_prefs: dict[str, bool]` (six, all-true defaults); `dev_unlocked`, `crash_opt_out: bool`; `bridge_imported_at` | THEME-01, STORE-07..10 |
| `Favorites` | `ids: list[str]` (ObservableList, **never a set**); `merged_for: str \| None` (owner whose union merge ran, OD-5). Methods `toggle`, `add_many` (returns undo), `remove_many`, `pull` | STORE-02, SCHED-12 |
| `StaffStore` | `sponsor {id, name, logo} \| None`; `products`, `categories: list[dict]`; **memory-only PII**: `inventory: dict[code, dict[product, qty]]`, `dietary: dict[code, dict]`, `coc_directory: list[dict]`; `inventory_status`, `coc_status: "idle"\|"loading"\|"ready"\|"error"`; `redeem_candidate: dict \| None` | DOOR-03, MASK-01, STORE-11 |
| `OutboxStore` | `pending`, `failed`, `synced: int` (current owner); `by_kind: dict[str, dict[str, int]]`; `syncing: bool`; `last_sync_at`, `last_error`; `revision: int` (+1 per write; list memo key) | API-10, LEAD-08 |
| `BannerStore` | `top: list[dict]` (app-config + reminder banners filtered by category; emergency always, OD-18); `dismissed: list[str]`; `sponsor_current: dict \| None`; `_rotation` | SHELL-08, NOTIF-08 |
| `ChangeLog` | `recent: dict[str, str]` (session → change kind, 24 h); `unseen: int`; `last_diff_at` | #312 |
| `Caps` | 11 capability keys + device flags `reduce_motion`, `high_contrast`, `dark_os`, `wide`, and the viewport `window_height: float` (§12.1; THEME-09's motion flag lives here, so there is no non-observable context; `wide` and `window_height` are set by the same `page.on_resize` handler, seeded from `page.width`/`page.height`, and `window_height` sizes the Staff sheet, SHELL-07) | §12 |

### 4.2 One store in full: `FeedStore`

```python
# src/pycon_us/stores/feed.py
FeedStatus = Literal["boot", "cached", "fresh", "offline", "error"]


@ft.observable
@dataclass
class FeedStore:
    conf: Conference | None = None
    version: int = 0
    status: FeedStatus = "boot"
    fetched_at: float | None = None
    refreshing: bool = False
    error: str | None = None
    _deps: "FeedDeps | None" = field(default=None, repr=False)   # storage, api, settings, app_config, on_new_feed
    _task: asyncio.Task | None = field(default=None, repr=False)

    async def publish_cache(self) -> None:
        cached = await self._deps.storage.read_feed_cache()          # (bytes, mtime) | None
        if cached is None:
            return
        try:
            conf = await self._parse(cached[0])
        except Exception as ex:                                       # D-88: drop a corrupt cache, keep going
            await self._deps.storage.delete_feed_cache()
            report(ex, "feed.cache_corrupt")
            return
        self._publish(conf, "cached", cached[1])

    def start_refresh(self, force: bool = False) -> asyncio.Future:
        if self._task is not None and not self._task.done():
            return self._task                                         # single flight (DATA-02)
        if not force and self.fetched_at and time.time() - self.fetched_at < 300:
            f = asyncio.get_running_loop().create_future()
            f.set_result(None)
            return f
        self._task = asyncio.create_task(self._refresh())
        return self._task

    @safe
    async def refresh(self, force: bool = True) -> None:             # button; never deletes the cache
        await self.start_refresh(force)

    @safe(toast=None)
    async def _refresh(self) -> None:
        d = self._deps
        self.refreshing = True
        try:
            body = await d.api.get_feed(d.app_config.feed_url or d.settings.feed_url)   # 10 s
            conf = await self._parse(body)
            old = self.conf
            await d.storage.write_feed_cache(body)                    # atomic, only after a good parse
            self._publish(conf, "fresh", time.time())
            await d.on_new_feed(old, conf)                            # change-log diff (§5.6)
        except ApiError:
            if self.conf is None:
                self.status, self.error = "error", "Unable to load schedule, no offline cache available"
            else:
                self.status = "offline"                               # keep the cache, show the stale chip
        finally:
            self.refreshing = False

    async def _parse(self, body: bytes) -> Conference:            # to_thread only if spike S3 > 150 ms (GR-7)
        return process.process(json.loads(body), self._deps.settings.process_ctx)

    def _publish(self, conf: Conference, status: FeedStatus, fetched_at: float) -> None:
        self.conf = conf              # eq=False → identity compare → always notifies (GR-8)
        self.fetched_at, self.status, self.error = fetched_at, status, None
        self.version += 1             # one re-render for all of these (GR-10)
```

Context and typed hook: `FeedCtx` / `use_feed()` (§2). Screens memoise on `feed.version`, with list dependencies passed as `tuple(...)` (D-47).

### 4.3 `Stores.create()`: the one place that builds services

```python
@classmethod
def create(cls, page: ft.Page) -> "Stores":
    st = settings.load(page)
    s = cls(page, st)
    secure, prefs_svc = SecureStorage(), ft.SharedPreferences()
    paths = None if page.web else ft.StoragePaths()                        # its methods raise FletUnsupportedPlatformException on web; don't create/use it there
    transport = PyfetchTransport() if page.pyodide else HttpxTransport()   # httpx absent under Emscripten
    s.storage, s.api = Storage(prefs_svc, secure, paths, st), ApiClient(transport, st, credentials=s.credentials)
    s.make_stores()                                                        # the 12 stores; content from the bundled copy
    s.sync_worker = SyncWorker(s)                                          # the only one (D-59)
    conn = ft.Connectivity(on_change=s.sync_worker.on_connectivity)        # handler set before registration
    s.services = Services(prefs_svc, secure, paths, conn, ft.UrlLauncher(), ft.Share(), ft.Clipboard(),
                          ft.HapticFeedback(), ft.SemanticsService(), PermissionHandler(), s.api, st)
    s.wire()                                                               # inject _deps
    safe_module.bind(page, s)                                              # @safe reporter + toast target
    return s
```

### 4.4 Bootstrap (replaces Ionic's 200/300 ms flag timers and the 5 s deferred init; D-46, DATA-35)

```python
# src/pycon_us/services/bootstrap.py
@safe
async def run(s: "Stores") -> None:
    page, svc = s.page, s.services
    crash.install(s)                                                   # handlers first (§15.2)
    # 1. prefs, a11y and theme before the first themed render (THEME-01, THEME-09)
    await s.prefs.load(s.storage)                                      # reads values; leaves `loaded` False
    s.caps.apply_device(await svc.semantics.get_accessibility_features(), page)
    themes.apply(page, s.prefs.theme, s.caps)
    s.prefs.loaded = True                                              # opens App's boot gate (§2)
    # 2. optional bridge import (OD-8)
    await bridge_import.maybe_import(s)
    # 3. auth restore: SecureStorage + persisted flags; IndexRedirect may route now
    await s.auth.restore(s.storage, s.features)
    # 4. cached feed (ends BootView), 5. network refresh (single flight, not awaited)
    await s.feed.publish_cache()
    s.feed.start_refresh(force=True)
    # 6. once per cold start (Ionic did three mobile_state GETs)
    if s.auth.logged_in:
        await asyncio.gather(s.features.refresh(s.api), s.favorites.pull(s.api, first_sync=False))
    # 7. server-driven files, then capabilities
    await asyncio.gather(s.app_config.fetch(), s.content.fetch())
    s.caps.derive(build_info.CAPS, s.app_config.features)
    # 8. background work: one of each
    s.sync_worker.start()
    s.banners.start_rotation(s.feed)
    s.app_config.start_polling(300)                                    # each loop awaits page.wait_until_visible()
    page.on_app_lifecycle_state_change = s.on_lifecycle
    page.on_resize = s.on_resize                                       # → caps.wide (>= 992 px), caps.window_height (e.width, e.height)
    page.on_platform_brightness_change = s.on_brightness               # → caps.dark_os
    page.update()                                                      # spike S9: confirm handlers need this
```

`Stores.bootstrap` is `async def bootstrap(self): await bootstrap.run(self)`. `Stores.shutdown` cancels the worker, rotation and poller. Each store method is `@safe` on its own, so a failing step (for example a `check_features` timeout) never blocks the next.

`Stores.on_lifecycle` (`@safe async`, `e: ft.AppLifecycleStateChangeEvent`) acts only on `ft.AppLifecycleState.RESUME`. It bumps `app_config.resumed_at` (the Now page recomputes, SCHED-26), re-reads accessibility features and re-applies the theme (OS high contrast may have changed), and gathers `app_config.fetch()`, `feed.refresh(force=False)` and, when logged in, `features.refresh()` (AUTH-04). Then it kicks the `SyncWorker`.

---

## 5. Data pipeline (PLAN §5.4)

### 5.1 `processData` → `core/process.py`, rule by rule

Input: `conference.json` (~824 KB). Output: `Conference` (frozen, `eq=False`). The differential suite compares every row against Ionic's own code on the 2025 and 2026 feeds (D-97).

| # | Ionic step | Python | Ids |
|---|---|---|---|
| 0 | writes `schedule-cache` on every call | cache written by `FeedStore` only after a good parse of a **network** body | DATA-02 |
| 1 | poster speakers → speakers (by id) | `Speaker(id=str(id), photo=resolve_photo(), bio_md)` | DATA-07/15 |
| 2 | register `Open Space` track if any | registry in feed order, no `'open-spaces'` sentinel | DATA-14 |
| 3 | open-spaces loop first; skip missing start/end or blank `room_display or room` | `id=str(conf_key+9000)`, `track="Open Space"`, `location=room_display`, markdown description, `site_url=…/open-spaces/#OpenSpace-<key>` | DATA-05 |
| 4 | drop `available-open-space*`, `open-space`, placeholders, `Posters` plenary | placeholder = name equals kind, empty description, no contact/authors, **kind not poster/break** | DATA-04 |
| 5 | collapse key `kind-day-name[-start]` (lunch per day, other breaks per exact start); name `Posters`; `Break` 12:00–13:59 Fri–Sun → `Lunch`; trailing `(Room)` → room; `^Hall ` → `Expo Hall `; earliest start → latest end | `collapse_rows()` | DATA-06, SCHED-19 |
| 6.1–6.3 | `sponsor-workshop` → `Sponsor Presentation`; register speakers; `markdownToTxt(name)` | `md_link_text()` + `html.unescape` | DATA-08/15 |
| 6.4 | `pre_registered` (phrase, tutorial, summit except Typing); strip suffix | verbatim | DATA-09 |
| 6.5 | plenary/keynote/lightning/event: `(X)` → location; lightning display `Pacific Ballroom - Arena`; `Hall` → `Expo Hall`; strip `^<kind>\s*[—:\-–]\s*` | verbatim regexes | DATA-08 |
| 6.6 | `is_spanish` (charla or `en espa[ñn]ol`), strip suffix | | DATA-10 |
| 6.7 | Job Fair labelled −30 min, grouped on canonical start | app-content `display_time_overrides` | DATA-11 |
| 6.8–6.10 | session object; `track = Cap(kind)`; track icon; speakers linked **by name** | name match, id cross-check logged | DATA-13/14/15/26 |
| 6.11 | `slot.sessions` branch | not ported; contract test fails if the key appears | DATA-27 (drop) |
| 6.12 | first group of a new day had no `startTime` | `TimeGroup.start` always set | DATA-13 |
| 7 | collapsed rows appended with id `` `${kind}-${room}-${start}` `` | same id, e.g. `break--2026-05-13T12:30:00-07:00` (§18 #1) | DATA-06/26 |
| 8 | sort groups | by `start` | DATA-13 |
| 9 | `poster-detail-<conf_key>` sessions inherit the Posters row (defaults `Expo Hall AB`, `Sun`), not in the timeline | `in_timeline=False` | DATA-07 |
| 10 | `speaker.tracks` in encounter order | | SPKR-01 |
| 11 | rooms: split `location` on `,`; `slugify_room`; `room_links`; `display_location = override or first link or location`; generic `Break` → `''` | verbatim | DATA-16, ROOM-06, SCHED-03 |
| 12–13 | seed 16 sprint rooms (pins with sublabel `/sprints/i`, not S-7); room sessions by start; rooms natural-sorted | pins from app-content | DATA-16, MAP-08 |
| – | six content blocks → Markdown once per version | `html_md.to_markdown(html, base=site)` | DATA-23/25 |

`Session`: `id: str`, `name`, `track`, `tracks: tuple`, `kind`, `section`, `pre_registered`, `is_spanish`, `informational`, `location`, `display_location`, `room_links: tuple[RoomLink, ...]`, `description_md`, `description_text` (search haystack), `speaker_ids`, `speaker_names`, `start`, `end`, `display_start: datetime`, `day: date`, `image_url`, `site_url`, `in_timeline`. `Speaker`: `id`, `name`, `photo`, `bio_md`, `session_ids`, `tracks`. Sessions and speakers refer to each other by id only (GR-8). A bad slot is caught in `process_slot()`, recorded in `Conference.skipped` and reported once per feed version; it never blanks the schedule.

### 5.2 Queries (`core/queries.py`)

The tokeniser follows Ionic: lowercase, `,` `.` `-` become spaces, split, drop empties. Every query returns fresh view models and none mutates `Conference` (Ionic mutated shared `hide` flags).

| Query | Rule | Ids |
|---|---|---|
| `timeline(conf, day, query, excluded, fav_only_ids, fav_ids)` | ANY word ⊂ name, `description_text` or a speaker name; a track passes if any of `tracks` is not excluded; favourites-only **ignores** `excluded` (OD-13) | DATA-18, SCHED-05/07/17 |
| `all_days_timeline(…)` | same, across days, with `day_label` | DATA-19, SCHED-06/08 |
| `sessions()` / `track_sessions(slug)` | flat by start incl. poster details / day-grouped Mon..Sun | DATA-20, SCHED-22/23 |
| `speakers(query)` | ANY word ⊂ name; sorted by last token; hidden ones flagged | DATA-21, SPKR-02 |
| `sprints/jobs(query)` | ALL words over name + submitter/sponsor + text | EVT-06, SPON-07 |
| `coc_search(query)` | every term ⊂ `full_name nickname badge_name`, max 25 | MASK-02 |
| `days(conf)` | `DayTab(index:int, date, label)`, ignores filters | DATA-17, SCHED-01 |
| `now_next(conf, now)` | Now = `start <= now < end`; Next = earliest group with `start > now`; no track filter | SCHED-25 (OD-12) |
| `scroll_target(vm, now)` | first group with `start >= now`, else last → `"slot-<iso>"` | SCHED-16 |

### 5.3 Time (`core/timefmt.py`, D-52)

`TZ = zoneinfo.ZoneInfo(settings.CONF_TZ)` with a pinned `tzdata` wheel (spike S2); feed instants carry offsets (`datetime.fromisoformat`). `conf_now()` returns `settings.FAKE_NOW` (DEMO or `PYCON_FAKE_NOW`) or `datetime.now(TZ)`, and Schedule, Now and Jump to Now all use it. Day bucket = `start.astimezone(TZ).date()`. Labels are en-US without locale: `f"{h12}:{m:02d} {'am' if h < 12 else 'pm'}"` and weekdays from a fixed tuple, never `strftime("%a")`. `date_ago()` keeps the four Ionic strings, with a 60 s tick on the lead list (DATA-31).

### 5.4 `core/html_md.py` (D-53)

Tags in the 2026 feed: `p` 970, `li` 311, `a` 165, `strong` 140, `code` 71, `em` 69, `ul` 64, `h2` 18, `h3` 11, `br` 11, `ol` 4, `hr` 3, `h4` 3, `blockquote` 1, `h1` 1; entities `&amp;` `&gt;` `&mdash;`.

| HTML | Markdown |
|---|---|
| `p` / `br` | paragraph / hard break `"  \n"` |
| `strong` `b` / `em` `i` / `code` | `**x**` / `*x*` / `` `x` `` |
| `a href` | `[text](url)`; relative `/…` → `site + path` |
| `ul` `ol` `li` (nested) | `- ` / `1. `, 2-space indent per level |
| `h1`–`h4`, `blockquote`, `hr` | `#`–`####`, `> `, `---` |
| `table`, unknown tags | text content (INFO-05) |

Input kinds: `html`; `markdown` (open spaces: pass through, absolutise links); `plain` (sponsor and some sprint text: escape, keep newlines). `parse_roles()` serves job listings (SPON-09); `section_split()` cuts Venue & Hours at `h1`–`h3` (MAP-09). Rendering: `ft.Markdown(value, selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB, on_tap_link=…)`, with links opened via `await svc.url.launch_url(url, mode=ft.LaunchMode.IN_APP_BROWSER_VIEW)` (SESS-06). E5 replaces this behind `caps.html`.

### 5.5 Names and slugs (`core/slugs.py`)

- `track_name(key, form)` uses the Ionic short/plural/long tables (`Ai` → `AI` / `Future of AI with Python` / `The Future of AI with Python`), falling back to title case (DATA-28).
- `track_slug = slugify(name + "s")` gives `ais`, `securitys`, `lightning-talkss`, `open-spaces`, … (DATA-29).
- Three different normalisers, copied exactly:
  - `slugify_room`: lower-case, `[^a-z0-9]+` → `-`, then strip leading and trailing `-`.
  - `normalize_room_key`: drop `room\s+`, keep `[a-z0-9]`.
  - `sponsor_slug`: lower-case, `\s+` → `-`, drop `[^a-z0-9-]`; keeps `qube-research--technologies`.

### 5.6 Change log (#312, D-54)

```python
def diff(old: Conference | None, new: Conference, parser_changed: bool) -> list[Change]:
    if old is None or parser_changed:                 # first install or new PROCESS_VERSION: no diff
        return []
    def tracked(c):                                   # collapsed rows embed their start in the id: skip them
        return {s.id: s for s in c.sessions if s.track not in ("Break", "Poster") or s.id.startswith("poster-detail-")}
    o, n = tracked(old), tracked(new)
    out = [Change(i, "added") for i in n.keys() - o.keys()] + [Change(i, "removed") for i in o.keys() - n.keys()]
    for i in o.keys() & n.keys():
        a, b = o[i], n[i]
        if (a.start, a.end) != (b.start, b.end):
            out.append(Change(i, "time", f"{a.start}|{a.end}", f"{b.start}|{b.end}"))
        if a.location != b.location:
            out.append(Change(i, "room", a.location, b.location))
        if a.name != b.name:
            out.append(Change(i, "title", a.name, b.name))
    return out
```

The feed's `cancelled` is always `false`; cancellations appear as placeholder slots and so surface as `removed`. Rows go to `schedule_changes` (§8.3). `ChangeLog.recent` drives the 24 h "Changed" chip. A non-empty batch raises an in-app banner when `scheduleChanges` is on, and `schedule/changes` lists the rows newest first.

---

## 6. Shell, chrome and screens (D-32, D-39, D-43)

### 6.1 `shell_view` and chrome (SHELL-05..14)

`shell_view()` is a hook-using builder: each View-level screen calls it exactly once per render and returns its View, so each stacked View has its own title, actions, drawer and bottom chrome.

```python
# src/pycon_us/ui/shell.py (excerpt)
NAV_H, SPONSOR_H, WIDE = 80, 56, 992
TABS = [("speakers", "Speakers", ft.Icons.PEOPLE_OUTLINE, ft.Icons.PEOPLE),
        ("conference-map", "Map", ft.Icons.MAP_OUTLINED, ft.Icons.MAP),
        ("schedule", "Schedule", ft.Icons.CALENDAR_MONTH_OUTLINED, ft.Icons.CALENDAR_MONTH),
        ("now", "Now", ft.Icons.RADIO, ft.Icons.RADIO)]


def shell_view(*, title, controls, root=False, actions=None, fab=None, scroll=None,
               appbar_bgcolor=brand.INDIGO) -> ft.View:
    page = ft.context.page
    location = ft.use_route_location()                  # ONE call, prefix checks only (D-39)
    view_path = ft.use_view_path()
    f, auth, caps, cfg, banners = use_features(), use_auth(), use_caps(), use_app_config(), use_banners()
    sheet_open, set_sheet_open = ft.use_state(False)

    tabs = list(TABS)
    if f.scanner_tab:                                   # "sheet" | "lead" per the truth table
        tabs.append(("lead-retrieval", "Scanner", ft.Icons.QR_CODE_SCANNER, ft.Icons.QR_CODE_SCANNER))
    elif not auth.logged_in:
        tabs.append(("login", "Login", ft.Icons.LOGIN, ft.Icons.LOGIN))
    seg = location.removeprefix("/app/tabs/").split("/", 1)[0]
    lit = next((i for i, t in enumerate(tabs) if t[0] == seg), None)    # expo-hall, rooms, … → None

    @safe
    def on_tab(e: ft.Event[ft.NavigationBar]):
        target = tabs[e.control.selected_index][0]
        if target == "lead-retrieval" and f.scanner_tab == "sheet":
            set_sheet_open(True)                         # no navigation; re-render restores the index
        else:
            page.navigate(f"/app/tabs/{target}")

    @safe
    def close_sheet():
        set_sheet_open(False)

    ft.use_dialog(staff_sheet(f, max_height=0.35 * caps.window_height, on_close=close_sheet) if sheet_open else None)

    nav = ft.NavigationBar(
        adaptive=True, height=NAV_H, on_change=on_tab, selected_index=lit if lit is not None else 0,
        indicator_color=None if lit is not None else ft.Colors.TRANSPARENT,          # int index: fake "none"
        destinations=[ft.NavigationBarDestination(label=l, icon=i, selected_icon=s if lit is not None else i)
                      for _, l, i, s in tabs])
    bottom = BottomChrome(nav, sponsor=SponsorBanner() if banners.sponsor_current else None)
    body = [*top_banner_rows(banners), *controls]       # top banners as first rows (U10 interim)
    if caps.wide:                                        # permanent 304 px menu (SHELL-14)
        body = [ft.Row([ft.Container(DrawerContent(permanent=True), width=304), ft.VerticalDivider(width=1),
                        ft.Column(body, expand=True, scroll=scroll)], expand=True)]
    return ft.View(
        route=view_path, padding=0, scroll=None if caps.wide else scroll,
        appbar=ft.AppBar(leading=MenuButton(cfg.update_available) if root and not caps.wide else None,
                         title=ft.Text(title), bgcolor=appbar_bgcolor, color=ft.Colors.WHITE,
                         actions=actions or []),
        drawer=ft.NavigationDrawer(controls=[DrawerContent()]) if root and not caps.wide else None,   # roots only
        bottom_appbar=bottom, floating_action_button=fab,
        controls=[ft.SafeArea(content=ft.Column(body, expand=True), expand=True)],
    )


def BottomChrome(nav: ft.NavigationBar, sponsor: ft.Control | None) -> ft.BottomAppBar:   # plain builder, no hooks
    return ft.BottomAppBar(padding=0, height=NAV_H + (SPONSOR_H if sponsor else 0),          # one slot (D-43)
                           content=ft.Column([c for c in (sponsor, nav) if c], spacing=0, tight=True))


def MenuButton(update: bool) -> ft.IconButton:
    page = ft.context.page

    @safe
    async def open_drawer():
        await page.show_drawer()

    return ft.IconButton(ft.Icons.MENU, tooltip="Menu", on_click=open_drawer,
                         badge=ft.Badge(small_size=8) if update else None)      # LIVE-04: str | Badge
```

- **Bottom chrome:** `BottomChrome` puts the sponsor strip and `NavigationBar` in one `bottom_appbar` with an explicit height. Check the inset on a Pixel 9 with 3-button nav (#311); a UI test checks the Scanner intercept keeps Schedule lit.
- **Staff sheet:** `staff_sheet()` (the decisions' `StaffSheet`) is `ft.BottomSheet(show_drag_handle=True, draggable=True, size_constraints=ft.BoxConstraints(max_height=max_height))`, with `max_height=0.35 * caps.window_height` passed by `shell_view`, gated by the truth table, fixed height (no detents). The height comes from `Caps` (read via `use_caps()`), not a plain `page.height` read, so a resize or rotation re-renders the sheet (SHELL-07).
- **Drawer:** `DrawerContent` has headers, `ListTile`s, two `ExpansionTile(expanded=False)` groups, Apps, Account, theme row and update card. The active item is a prefix check; only page groups highlight. Handlers `navigate` then `await page.close_drawer()`. Roots only: no drawer on `Welcome` or on detail Views.
- **Sponsor banner:** shows `BannerStore.sponsor_current` and links to `href("sponsors","sponsor-detail",sponsor_slug(name))`. **One** rotation task in the store (30 s, uniform random over all `mobile_banner` sponsors, repeat possible, as Ionic: `tabs-page.ts` hides the current banner before drawing from the live `bannerSponsorHidden` collection), `animate_opacity` unless `reduce_motion` (SHELL-08).
- **Leading button:** roots pass `root=True` (hamburger and drawer); details have no drawer, so Flutter's AppBar implies the back arrow (with a drawer it would imply a hamburger instead). `HeroPage` fades the title in after 100 px of `on_scroll` (INFO-01, SCHED-27).

### 6.2 `Schedule` (root; SCHED-01..20)

```python
@ft.component
def Schedule():
    feed, prefs, favs, caps = use_feed(), use_prefs(), use_favorites(), use_caps()
    page = ft.context.page
    day, set_day = ft.use_state(None)           # None = today (auto)
    text, set_text = ft.use_state("")           # field value
    query, set_query = ft.use_state("")         # debounced value
    favs_only, set_favs_only = ft.use_state(False)
    jump, set_jump = ft.use_state(0)            # Jump to Now counter
    list_ref = ft.Ref()

    days = ft.use_memo(lambda: queries.days(feed.conf), [feed.version])
    today = queries.today_index(days, timefmt.conf_today())          # None outside conference days
    active = day if day is not None else (today or 0)
    excluded, fav_ids = tuple(prefs.excluded()), tuple(favs.ids)
    vm = ft.use_memo(lambda: queries.timeline(feed.conf, active, query, excluded,
                                              fav_ids if favs_only else None, fav_ids),
                     [feed.version, active, query, excluded, favs_only, fav_ids])

    @safe
    async def debounce():                        # a re-run cancels the previous task: 250 ms debounce
        await asyncio.sleep(0.25)
        set_query(text)

    ft.use_effect(debounce, [text], cleanup=NOOP)

    @safe
    async def scroll_once():                     # per day entry and Jump to Now; not on Back or refresh (#313)
        lv = list_ref.current
        if lv is None or feed.conf is None:
            return
        key = queries.scroll_target(vm, timefmt.conf_now()) if active == today else None
        await (lv.scroll_to(scroll_key=key, duration=500) if key else lv.scroll_to(offset=0))

    ft.use_effect(scroll_once, [active, jump, feed.conf is not None], cleanup=NOOP)

    @safe
    def open_session(session_id: str):
        page.navigate(href("schedule", "session", session_id))

    @safe
    def jump_to_now():
        set_day(today)
        set_jump(jump + 1)

    @safe
    def open_filter():
        page.navigate(href("schedule", "filter"))

    @safe
    def toggle_favs():
        set_favs_only(not favs_only)

    return shell_view(
        title="Schedule", root=True,
        actions=[ft.IconButton(ft.Icons.STAR if favs_only else ft.Icons.STAR_BORDER, on_click=toggle_favs,
                               tooltip="Show all sessions" if favs_only else "Show favorites only"),
                 ft.IconButton(ft.Icons.FILTER_ALT_OUTLINED, on_click=open_filter, tooltip="Filter sessions",
                               badge=ft.Badge(small_size=8) if prefs.is_custom_filter() else None),
                 RefreshButton()],                                    # U1 interim (SCHED-13)
        fab=JumpToNow(on_click=jump_to_now, collapse=not caps.reduce_motion) if today is not None else None,
        controls=[DaySelector(days, active, on_change=set_day, today=today),   # first row (U10 interim)
                  SearchField(text, on_change=set_text),
                  StaleChip(),                                                 # "Updated N h ago"
                  Refreshable(content=TimelineList(vm, list_ref=list_ref, favs=favs, on_open=open_session),
                              on_refresh=feed.refresh)],
    )
```

`TimelineList` uses `ft.ListView(ref=list_ref, build_controls_on_demand=False)` when spike S3 allows, else a two-step offset-then-key jump (D-68). Each group opens with `ft.Container(key=ft.ScrollKey("slot-<iso>"), content=ft.Text("Sat - 9:25 am"))` (U2 interim). `SessionRow` wraps rows in `ft.Dismissible(dismiss_direction=ft.DismissDirection.END_TO_START, on_confirm_dismiss=…)`; its `@safe async` handler awaits `e.control.confirm_dismiss(False)` (snap back), toggles the favourite and shows the Ionic SnackBar (SCHED-11). `NoticeRow`s don't swipe; long press and the star are the non-gesture paths.

### 6.3 `SessionDetail` (child, also rendered by `Drill`; SESS-01..12)

```python
@ft.component
def SessionDetail(session_id: str | None = None):
    params = ft.use_route_params()
    feed, favs, content, svc = use_feed(), use_favorites(), use_content(), use_services()
    providers, tokens = use_providers(), use_tokens()          # all hooks first (GR-5)
    page, view_path = ft.context.page, ft.use_view_path()
    sid = session_id or unquote(params.get("session_id", ""))
    s = ft.use_memo(lambda: queries.session(feed.conf, sid), [feed.version, sid])
    starred = sid in favs.ids

    @safe
    def toggle_star():
        favs.toggle(sid)

    @safe
    async def add_to_calendar():                                # .ics share; E4 prompt when caps.calendar
        await providers.calendar.add_session(s)

    @safe
    def open_room(slug: str):
        page.navigate(drill_href(view_path, "r", slug), session=sid)

    @safe
    def open_speaker(speaker_id: str):
        page.navigate(drill_href(view_path, "p", speaker_id))

    @safe
    async def open_link(e: ft.Event[ft.Markdown]):
        await svc.url.launch_url(absolutise(e.data), mode=ft.LaunchMode.IN_APP_BROWSER_VIEW)

    body = [NotFoundCard("Session not found")] if s is None else [
        SessionHero(s, new_track=s.track in content.new_tracks),           # location, never display_location
        MetaCard(s),                                                        # "Sat 9:25 am – 10:10 am"
        *[ft.TextButton(content=ft.Text(r.name), on_click=lambda _, slug=r.slug: open_room(slug))
          for r in s.room_links],                                           # SESS-02
        ft.Markdown(s.description_md, selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                    on_tap_link=open_link),
        *speaker_tiles(s, feed.conf, on_open=open_speaker),                 # SESS-07 (plain builders)
        *poster_rows(s, feed.conf, view_path),                              # SESS-09: drill s~poster-detail-N
        *job_fair_card(s),                                                  # SESS-10: /floor-plan/job-fair
    ]
    actions = [] if s is None else [
        ft.IconButton(ft.Icons.STAR if starred else ft.Icons.STAR_BORDER, selected=starred, on_click=toggle_star,
                      icon_color=tokens.favorite_star if starred else ft.Colors.WHITE,
                      tooltip="Remove from favorites" if starred else "Add to favorites"),
        ft.IconButton(ft.Icons.EVENT, tooltip="Add to calendar", on_click=add_to_calendar)]
    return shell_view(title="", actions=actions, controls=body, scroll=ft.ScrollMode.AUTO)
```

---

## 7. API client (PLAN §5.5, D-55..D-58)

### 7.1 Signing (`core/signing.py`)

```python
JS_COMPONENT_SAFE = "!*'()"          # encodeURIComponent leaves A-Za-z0-9 - _ . ! ~ * ' ( ) unescaped


def canonical_body(obj) -> bytes:    # JSON.stringify: compact, insertion order, non-ASCII raw. Serialise ONCE.
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def js_round(x: float) -> int:       # Math.round (half up), not banker's round()
    return math.floor(x + 0.5)


def sign(secret: str, ts: int, method: str, full_path: str, body: bytes = b"") -> str:
    """sha1(secret + str(ts) + METHOD + full_path + body) hex. SHA-1, not HMAC; no separators;
    full_path starts at /{YEAR}/ and includes the query exactly as sent."""
    return hashlib.sha1(secret.encode() + str(ts).encode() + method.upper().encode()
                        + full_path.encode() + body).hexdigest()


def enc(v: str) -> str:
    return quote(v, safe=JS_COMPONENT_SAFE)


def capture_query(code, validator, sponsor_id=None) -> str:                       # encoded (Ionic)
    q = f"attendee_access_code={enc(code)}&badge_validator={enc(validator)}"
    return q + (f"&sponsor_id={enc(sponsor_id)}" if sponsor_id else "")


def fetch_products_query(code, ids, *, by, mode) -> str:                           # NOT encoded (Ionic)
    return f"attendee_access_code={code}&{by}={','.join(map(str, ids))}&mode={mode}"
```

**Test vectors** (`tests/unit/test_API_01_signing.py`; computed with `hashlib` on 2026-10-11; secret `s3cr3t`, ts `1747324800`):

| Method | full_path | body bytes | signature |
|---|---|---|---|
| GET | `/2027/api/v1/user/mobile_state/` | (empty) | `77946e44677e7f97445336dd9de5f0a0b58dc016` |
| PATCH | `/2027/api/v1/user/mobile_state/` | `{"favorites":["123","poster-detail-7"]}` | `59b274bd80705949c06a5fd31abfe5f54307dc26` |
| POST | `/2027/api/v1/lead_retrieval/ABC123/note/` | `{"accessCode":"ABC123","note":"Interest: hot\nNotes: café"}` (UTF-8 `é`) | `798ff969a24a536d3df9f504dcb16987f73dbd41` |
| GET | `/2027/api/v1/check_in/fetch_products/?attendee_access_code=ABC123&category_pk_list=1,2&mode=redemption_mode` | (empty) | `3b49566459ec1ee2a43bdae2a2d87835c9aada52` |

The 2019 `docs/api.rst` example and P3 staging captures join this file at M2; the vectors are offered to pycon-site as JSON (D-48). Headers: `X-API-Key`, `X-API-Signature`, `X-API-Timestamp` (`str(ts)`), plus `Content-Type: application/json` on POST/PATCH. Signed calls raise `AuthFailed` client-side when logged out.

### 7.2 Endpoints (`api/endpoints.py`; paths under `/{YEAR}/api/v1/`)

| Key | Method | Path | Body | Timeout | Notes |
|---|---|---|---|---|---|
| `authenticate` | POST | `authenticate/` (**unsigned**) | `{email, password}` | 3 s | single flight; `Invalid Auth: <message>` |
| `check_features` | GET | `user/check_features/` | – | 2 s | start, resume, Account open |
| `mobile_state_get` / `_patch` | GET / PATCH | `user/mobile_state/` | – / `{favorites:[…]}` | 2 s | PATCH via outbox, debounced 1 s |
| `redeemable` | GET | `check_in/redeemable/` | – | 2 s | categories split by `/shirt\|swag/i` |
| `inventory` | GET | `check_in/attendees_by_product_with_quantity/<id>/` | – | 20 s | one per product, `asyncio.gather` |
| `fetch_products` | GET | `check_in/fetch_products/?…` | – | 10 s | **unencoded**; swag `category_pk_list` + `redemption_mode`, door `product_pk_list` + `door_check_mode` |
| `redeem` | POST | `check_in/redeem_products/` | `{attendee_access_code, badge_validator, scanned_at, "product-redeem-<id>": id, "product-<id>-quantity": qty, …}` | 10 s | insertion order; door omits a missing validator, swag sends `""` (Ionic) |
| `coc_attendees` | GET | `mask_violations/attendees/` | – | 15 s | memory only |
| `coc_capture` / `_force` | GET / POST | `mask_violations/capture/?attendee_access_code=<enc>` / `mask_violations/capture/` (no query) | – / `{attendee_access_code, notes?, force: true}` | 5 s | POST whenever `notes` or `force` is set (the code travels only in the body); the scan path (no notes) uses GET and never sends `force` |
| `lead_sponsors` | GET | `lead_retrieval/sponsors/` | – | 5 s | strip quotes from names |
| `lead_capture` | GET | `lead_retrieval/capture/?<capture_query>` | – | 2 s | outbox only (§18 #2) |
| `lead_note` | POST | `lead_retrieval/<code>/note/` | `{accessCode, note[, sponsor_id]}` | 2 s | outbox only, after its capture |

Envelopes: `{code, data}` / `{code, error}`. The feed (`{site}/{YEAR}/schedule/conference.json`, 10 s, unsigned) uses the same transport.

### 7.3 `request()`, errors, skew

```python
async def request(self, ep: Endpoint, *, args=(), query="", obj=None) -> dict:
    path = f"/{self.st.year}/api/v1/{ep.path.format(*args)}" + (f"?{query}" if query else "")
    body = canonical_body(obj) if obj is not None else b""
    for attempt in (1, 2):
        headers = {"Content-Type": "application/json"} if body else {}
        if ep.signed:
            key, secret = self.credentials()                     # AuthFailed when logged out
            ts = js_round(time.time() + self.skew)
            headers |= {"X-API-Key": key, "X-API-Timestamp": str(ts),
                        "X-API-Signature": sign(secret, ts, ep.method, path, body)}
        resp = await self.transport.request(ep.method, self.st.site + path, headers=headers,
                                            body=body or None, timeout=ep.timeout)  # Offline / Timeout
        self.skew = self._skew_from(resp.headers.get("date"), self.skew)         # email.utils.parsedate_to_datetime
        if resp.status == 403 and ep.signed and attempt == 1 and abs(self.skew) > SKEW_SUSPECT:
            continue                                             # one retry with a corrected ts
        return self._unwrap(resp, ep)
    raise ClockSkew(self.skew)
```

| Error | When | Outbox |
|---|---|---|
| `Offline` | connect/DNS failure (`httpx.TransportError` except timeouts; pyfetch network error) | try **not** counted; wait for reconnect |
| `Timeout` | per-endpoint timeout | counted |
| `AuthFailed` | 401, login `{message}`, no credentials | counted |
| `Forbidden` / `NotFound` | 403 not explained by skew / 404 | counted |
| `Server` | 5xx, bad JSON, missing envelope | counted |
| `ClockSkew` | 403 again after the skew retry | counted; Developer Info shows the skew |

`SKEW_SUSPECT = 300 s`, half of the 2019 600 s window; the current window is UNCONFIRMED (P3). Connectivity is not reachability, so the worker trusts transport errors, not `ft.Connectivity`. `HttpxTransport` keeps one `httpx.AsyncClient`. `PyfetchTransport` wraps `pyodide.http.pyfetch` in `asyncio.wait_for`, and login works there only if the PSF enables CORS (D-93).

### 7.4 Auth flows

- **Login** (AUTH-01/02): unsigned `authenticate` → SecureStorage `key`/`secret`, prefs `email`/`nickname`/`features` → `Features.apply()` → `favorites.pull(first_sync=True)` (union, OD-5) → Lead Scanner only if `lead_retrieval` (D-42). Writes are awaited before the observable flips (AUTH-07). Logging in as a different account purges the previous owner's **synced** staff rows (D-61).
- **Favourites** (D-58): server ints become `str`. The first sync after login unions local and server, then PATCHes; a server `[]` never wipes local favourites. Afterwards the server wins on pull. Changes coalesce into one full-list `favorites` outbox row.
- **Logout** (D-62, SHELL-13): with rows pending, ask "Sync now" / "Log out anyway (N unsynced)". Then remove (awaited) key, secret, `email`, `nickname`, `features`, `scanner_consent`, `staff_sponsor`, `favorite_sessions`; reset `Favorites`, `Features` and `StaffStore`; go to Schedule. Theme, filters, notification prefs, cache and the tutorial flag stay.

---

## 8. Storage (D-57, D-59, D-60)

### 8.1 SharedPreferences (prefix `pycon.<env>.`; `str/int/float/bool/list[str]` only, dicts as JSON)

| Key | Type (default) | Ionic key | Logout clears |
|---|---|---|---|
| `did_tutorial` | bool (False) | `ion_did_tutorial` | no |
| `theme` | str (`system`) | `theme` | no |
| `schedule_filters` | JSON list or absent (→ `["Open Space"]`) | `scheduleFilters` | no |
| `notification_prefs` | JSON of 6 bools (all true) | same | no |
| `favorite_sessions` | `list[str]` | same | yes |
| `email`, `nickname` | str | same | yes |
| `features` | JSON `{lead_retrieval, door_check, mask_violation, is_speaker}` | 4 keys | yes |
| `scanner_consent` | bool | `hasScannerConsent` | yes |
| `staff_sponsor` | JSON `{id, name, logo}` | `staff-sponsor-*` | yes |
| `dev_unlocked`, `crash_opt_out`, `bridge_imported_at` | bool, bool, str | – | no |
| `feed_cache` (web only) | str | `schedule-cache` | no (§18 #6) |

SecureStorage keys: `pycon.<env>.key`, `pycon.<env>.secret`.

### 8.2 Files

| File | Where | Notes |
|---|---|---|
| `conference-{YEAR}.json` | `await paths.get_application_cache_directory()` | atomic (`tmp` + `os.replace`) after a good parse; mtime = `fetched_at`; sidecar `.meta.json` has `PROCESS_VERSION` and sha256 |
| `app-content-{YEAR}.json` | cache dir | last good remote copy; bundled copy is the fallback |
| `pycon.db` (`pycon-demo.db` in DEMO) | `await paths.get_application_support_directory()` | stdlib `sqlite3`, WAL, `PRAGMA user_version` migrations; not on web |

### 8.3 sqlite DDL (`core/outbox.py: SCHEMA_V1`)

```sql
CREATE TABLE IF NOT EXISTS outbox (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL CHECK (kind IN ('lead', 'note', 'door', 'favorites')),
    key          TEXT NOT NULL,                 -- access code, or 'favorites'
    payload_json TEXT NOT NULL,                 -- request; on success {...request, "result": data}
    sponsor_id   TEXT,                          -- snapshotted at enqueue (STORE-11)
    sponsor_name TEXT,
    owner        TEXT NOT NULL,                 -- lower-cased account email at enqueue
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'synced', 'failed')),
    tries        INTEGER NOT NULL DEFAULT 0,
    next_at      REAL NOT NULL,                 -- epoch seconds
    created_at   REAL NOT NULL,                 -- = scanned_at
    last_error   TEXT,
    idem_key     TEXT                           -- door: code|sorted product ids|scan session
);
CREATE INDEX IF NOT EXISTS outbox_due ON outbox (owner, status, next_at);
CREATE INDEX IF NOT EXISTS outbox_key ON outbox (owner, kind, key);
CREATE UNIQUE INDEX IF NOT EXISTS outbox_idem ON outbox (idem_key) WHERE idem_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS schedule_changes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_sha    TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    change      TEXT NOT NULL CHECK (change IN ('added', 'removed', 'time', 'room', 'title')),
    old_value   TEXT,
    new_value   TEXT,
    detected_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS schedule_changes_recent ON schedule_changes (detected_at, session_id);
```

One connection, an `asyncio.Lock`, and calls through `asyncio.to_thread`; rows come back to the loop, which updates stores (GR-7).

---

## 9. Outbox and `SyncWorker` (D-59; API-10/11, LEAD-07..13, DOOR-07)

### 9.1 State machine (`core/outbox.py`, pure, table-tested)

| From | Event | To | Effect |
|---|---|---|---|
| – | lead scan; a `synced` row exists for (owner, code) | – | ignored silently (parity) |
| – | lead scan; a `pending` row exists | pending | `next_at = now`, kick |
| – | lead scan otherwise | pending | snapshot sponsor, `tries = 0`, kick |
| – | note saved (non-empty) | pending | upsert for (owner, code) |
| – | door admit | pending | unique `idem_key`; many pending per attendee allowed |
| – | favourites change | pending | **coalesced** into the single pending `favorites` row |
| pending | sent OK | synced | `result` merged into `payload_json` |
| pending | `Offline` | pending | tries unchanged, `next_at = now + 60`, end the pass |
| pending | other `ApiError` | pending | `tries += 1`, `last_error`, `next_at = now + 60` |
| pending | `tries > cap` (lead 10, note 20, door 30, favorites 30) | failed | "Retry failed" list (LEAD-13) |
| failed | "Retry failed" | pending | `tries = 0`, `next_at = now` |
| pending note | its lead not `synced` yet | pending | not due (LEAD-11) |
| synced | past `staff_data_purge_after`, or another owner logs in | deleted | D-61; other owners' pending/failed rows wait for the purge date |

`tries > cap` mirrors Ionic's `tries > 10`, so a row fails on its 11th failure. Synced rows are kept because lead dedupe and door "Already checked in" read them.

Due rows:

```sql
SELECT o.* FROM outbox o
WHERE o.owner = :owner AND o.status = 'pending' AND o.next_at <= :now
  AND (o.kind <> 'note' OR EXISTS (SELECT 1 FROM outbox l WHERE l.owner = o.owner AND l.kind = 'lead'
                                   AND l.key = o.key AND l.status = 'synced'))
ORDER BY CASE o.kind WHEN 'lead' THEN 0 WHEN 'door' THEN 1 WHEN 'note' THEN 2 ELSE 3 END, o.created_at;
```

### 9.2 `SyncWorker` (`services/sync_worker.py`)

```python
class SyncWorker:
    """The app's only sync loop: 60 s tick + connectivity change + RESUME (D-59, LEAD-12)."""

    def __init__(self, s: "Stores"):
        self.s, self._wake, self._lock, self._task = s, asyncio.Event(), asyncio.Lock(), None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    def kick(self) -> None:                                               # stop() cancels _task
        self._wake.set()

    @safe(toast=None)
    async def on_connectivity(self, e: ft.ConnectivityChangeEvent) -> None:
        if any(c != ft.ConnectivityType.NONE for c in e.connectivity):
            self.kick()

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=60)   # a schedule, not a sync timer
            except TimeoutError:
                pass
            self._wake.clear()
            try:
                await self.drain()
            except Exception as ex:                                       # the loop never dies
                report(ex, "sync_worker.drain")

    async def drain(self) -> None:
        s = self.s
        if not s.auth.logged_in or self._lock.locked():
            return
        async with self._lock:
            s.outbox.syncing = True
            try:
                db, owner = s.storage.db, s.auth.owner
                for row in await db.due_rows(owner, time.time()):
                    try:
                        result = await self._send(row)
                    except Offline:
                        await db.apply(ob.on_offline(row, time.time()))
                        break
                    except ApiError as err:
                        await db.apply(ob.on_error(row, err, time.time()))
                    else:
                        await db.apply(ob.on_success(row, result))
                await s.outbox.refresh_counts(db, owner)                  # counters, revision += 1
                s.outbox.last_sync_at = time.time()
            finally:
                s.outbox.syncing = False

    async def _send(self, row) -> dict:
        api = self.s.api
        match row.kind:
            case "lead":
                return await api.lead_capture(row.key, row.payload["validator"], row.sponsor_id)
            case "note":
                return await api.lead_note(row.key, row.payload["note"], row.sponsor_id)
            case "door":
                return await api.redeem(row.payload)                      # payload built once at enqueue
            case "favorites":
                return await api.mobile_state_patch(row.payload["favorites"])
```

The worker is kicked after every enqueue, on a `Connectivity` change to anything but `NONE`, on RESUME, and from "Sync now".

---

## 10. Staff tools (D-80..D-84)

### 10.1 Shared

- `parse_badge(raw, tool)`: code = `raw.split(":")[0]`. Validator = segment 1 (door, swag) or the **last** segment (lead; equals the code for a one-segment payload, Ionic parity); CoC uses the code. An empty code raises `InvalidBadge`. Vectors come from PSF badges (P3).
- `providers.scanner.surface(active, on_payload)` (§12.2). `ManualEntryScanner` is an autofocused `TextField(on_submit=…)` for the full `code:validator` payload (typed, pasted, or a USB/BT HID wedge ending in Enter). With E1 the camera replaces it and manual entry stays one tap away.
- Consent `AlertDialog(modal=True)` on every Lead Scanner entry until accepted; Cancel goes to Schedule (LEAD-04). The camera card appears only with E1 (`PermissionHandler.get_status/request(Permission.CAMERA)`, `open_app_settings()`).
- Each outcome is announced with `await svc.semantics.announce_message(text)` plus its own haptic (D-70): Checked in → `medium_impact()`, Already → `selection_click()` ×2, Entry not permitted → `heavy_impact()`, Invalid QR → `vibrate()`, Captured → `light_impact()`.

### 10.2 Flows and timings

| Tool | Flow | Pacing | Dedupe | Offline |
|---|---|---|---|---|
| Lead | consent → (staff scanner: sponsor picker with Cancel, "Tap to change", name filter) → scan → outbox `lead`. Footer awaits the sync result (no 100 ms polling), clears after 5 s, note button → `note/:code`. List: newest 50, current owner, PENDING/FAILED, 60 s `date_ago` tick | re-arm 500 ms | synced → ignore; pending → kick | always queues; > 10 tries → failed |
| Door | non-swag chips (single-select, tap again clears) → products by `product_sort_key` → "All sessions in this category" or one → Start preloads inventory (`gather`, "Ready (N attendees)") → scan → `decide()`. Headcount resets on category/product change and clear, not Stop/Start | re-arm 250 ms | last code in the 5 s card + `counted_codes`; Already = product overlap with kept rows | inventory decides; unknown → "Entry not permitted"; admits queue (30 tries, idem key) |
| Swag | swag chips (multi) → scan under `asyncio.Lock` → `fetch_products` → `StaffStore.redeem_candidate` → `redeem` modal (alphabetical, all-or-nothing) → POST → five TopToasts; "Invalid QR code" shown ≥ 2 s | paused until modal closes | server | online only, explicit message |
| CoC | directory (memory, Retry) → search (all terms, max 25) → "Record incident" + notes (2000) → POST `force: true`; scan → GET. Card > 2 danger / > 1 warning, cleared 5 s after the request | 3 s per-code cooldown | cooldown | online only |

```python
def decide(code: str, scanning: list[str], inventory: dict[str, dict[str, int]], rows: list[DoorRow]) -> Decision:
    per = inventory.get(code, {})
    qty = {p: per[p] for p in scanning if per.get(p, 0) > 0}
    already = any(set(r.products) & set(scanning) for r in rows if r.key == code)   # synced or pending
    return Decision(access=bool(qty), quantity=sum(qty.values()), product_quantities=qty,
                    already=already, needs_fallback=not qty)   # the screen then tries fetch_products online
```

Kill switches `features.lead_retrieval/door_check/swag/coc` hide a tool's entries and make its Guard show "Not available". Dev and DEMO builds add "Simulate Scan" (`SIM12345:SIMULATED`) and use `pycon-demo.db` (D-84). Inventories, dietary data and the CoC directory are never written to disk and are reset on logout or account switch.

---

## 11. Theming (D-64, D-65; THEME-01..12)

### 11.1 Tokens per mode

Brand constants (`brand.py`, never change): `INDIGO #3B3EA9`, `MAGENTA #DD04D2`, `PURPLE #680579`, `GOLD #FFD779`, hero end `#101136`, violet `#5833E9`.

| Token | Light | Dark iOS | Dark Android | HC light | HC dark |
|---|---|---|---|---|---|
| primary / on_primary | `#3880ff`/`#ffffff` | `#428cff`/`#ffffff` | `#428cff`/`#ffffff` | `#4a0072`/`#ffffff` | `#ffd60a`/`#0b0f17` |
| secondary | `#3dc2ff` | `#50c8ff` | `#50c8ff` | `#003a99` | `#5ac8fa` |
| tertiary | `#5260ff` | `#6a64ff` | `#6a64ff` | `#7a1a8a` | `#c084ff` |
| success | `#2dd36f` | `#2fdf75` | `#2fdf75` | `#146c2e` | `#30d158` |
| warning | `#ffc409` | `#ffd534` | `#ffd534` | `#7a4a00` | `#ffd60a` |
| danger | `#eb445a` | `#ff4961` | `#ff4961` | `#a30000` | `#ff8a80` |
| medium | `#92949c` | `#989aa2` | `#989aa2` | `#4a4d54` | `#b0b3ba` |
| light | `#f4f5f8` | `#222428` | `#222428` | `#f0eee8` | `#1a1d24` |
| background / text | `#ffffff`/`#000000` | `#000000`/`#ffffff` | `#121212`/`#ffffff` | `#fbfaf6`/`#1a1d24` | `#0b0f17`/`#f5f5f0` |
| border | default | default | `#222222` | `#1a1d24` | `#f5f5f0` |
| item bg / plain toolbar | default | `#000000`/`#0d0d0d` | `#1e1e1e`/`#1f1f1f` | `#fbfaf6`/`#fbfaf6` | `#0b0f17`/`#0b0f17` |
| tab bar bg / selected | default/`#DD04D2` | default/`#DD04D2` | `#1f1f1f`/`#DD04D2` | `#fbfaf6`/`#4a0072` | `#0b0f17`/`#ffd60a` |
| card | default | default | default | `#ffffff` | `#11151d` |
| `favorite_star` / `favorite_swipe` | `#fbbf24`/`#69bb7b` | `#fbbf24`/`#69bb7b` | `#fbbf24`/`#69bb7b` | `#fbbf24`/`#4a0072` | `#fbbf24`/`#ffd60a` |
| hero accent / `hc` | `#DD04D2`/F | `#DD04D2`/F | `#DD04D2`/F | `#4a0072`/T | `#ffd60a`/T |
| `text_scale` | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 (the golden suite sets 2.0) |

`favorite_star` is Ionic's hard-coded session-detail star (`#fbbf24` in every theme, on the always-`#3B3EA9` header: 5.1:1); only `favorite_swipe` (`--ion-color-favorite`) changes per HC theme. The contrast unit test includes `favorite_star` on `brand.INDIGO` in all five modes (5.1:1 passes the 4.5:1 floor; as a non-text icon on a fixed brand header it is outside the 7:1 HC text rule, which §18 #15 records).

**Track palette** (THEME-08; keys = feed track names): talk `#5833E9`, tutorial `#A6049B`, keynote `#680579`, plenary `#630675`, break `#3A3A3A`, lightning-talks `#9C3F80`, security `#F19C0B` (text `#1a1a1a`), ai `#10B57F`, charla `#3D5F94`, poster `#D47454`, sponsor presentation `#B8860B`, open space `#6FCF97` (ai, poster, sponsor presentation and open space use dark text); default medium.

- **Badges:** New `#680579`; En Español `#DD04D2`; Pre-registration is a danger outline.
- **High contrast** (THEME-06):
  - Pills become transparent, with a 1.5 px border and text in the text colour.
  - Cards get a 1 px border and no shadow.
  - Secondary text uses the full text colour, and the focus ring is 3 px primary.

### 11.2 Applying themes (`ui/theme/themes.py`)

```python
def build(p: Palette, text_scale: float = 1.0) -> ft.Theme:          # Tokens.text_scale
    return ft.Theme(
        text_theme=scaled_text_theme(text_scale),     # every TextTheme style's size × text_scale (emulates OS text scale)
        color_scheme=ft.ColorScheme(primary=p.primary, on_primary=p.on_primary, secondary=p.secondary,
                                    tertiary=p.tertiary, error=p.danger, surface=p.background, on_surface=p.text,
                                    on_surface_variant=p.medium, outline=p.border, surface_container=p.card),
        scaffold_bgcolor=p.background, card_bgcolor=p.card,
        appbar_theme=ft.AppBarTheme(bgcolor=brand.INDIGO, color=ft.Colors.WHITE),
        navigation_bar_theme=ft.NavigationBarTheme(bgcolor=p.tab_bar, indicator_color=p.tab_selected_bg),
        system_overlay_style=ft.SystemOverlayStyle(status_bar_icon_brightness=ft.Brightness.LIGHT,   # Android
                                                   status_bar_brightness=ft.Brightness.DARK))        # iOS


def apply(page: ft.Page, pref: str, caps: "Caps") -> None:
    dark = DARK_IOS if page.platform == ft.PagePlatform.IOS else DARK_ANDROID     # HC is platform-independent
    if pref == "system":
        light_p, dark_p = (HC_LIGHT, HC_DARK) if caps.high_contrast else (LIGHT, dark)
        page.theme, page.dark_theme, page.theme_mode = build(light_p), build(dark_p), ft.ThemeMode.SYSTEM
    else:
        p = {"light": LIGHT, "dark": dark, "high-contrast-light": HC_LIGHT, "high-contrast-dark": HC_DARK}[pref]
        page.theme = page.dark_theme = build(p)
        page.theme_mode = ft.ThemeMode.DARK if p.is_dark else ft.ThemeMode.LIGHT
    page.update()
```

`Tokens` also carries `text_scale`, applied to `Theme.text_theme` sizes in `build()`: 1.0 in the app, 2.0 in the golden suite, which emulates OS text scale because Flet cannot set it (D-70). On Android below API 34, OS high contrast is not detectable (`high_contrast` is always False), so users pick HC manually; a unit test checks that the HC theme picker stays reachable when `high_contrast` is False. `use_tokens()` memoises the active `Tokens` (success/warning/medium/favourite slots Material lacks) on `(prefs.theme, caps.high_contrast, caps.dark_os, page.platform)`. The picker (THEME-01) goes through `ft.use_dialog`: on iOS `ft.CupertinoBottomSheet(content=ft.CupertinoActionSheet(…))` (`CupertinoActionSheet` is not a `DialogControl`), elsewhere `ft.BottomSheet` + `ft.RadioGroup`. Options: Match system, Light, Dark, High Contrast (Light), High Contrast (Dark). Goldens set `page.theme_animation_style = ft.AnimationStyle.no_animation()`. `caps.reduce_motion` gates every repeating animation.

---

## 12. Capabilities and providers (PLAN §5.7, D-74..D-79)

### 12.1 `Caps` (`platform/caps.py`)

```python
CAP_KEYS = ("scanner", "push", "local_notifications", "calendar", "analytics", "refresh_indicator",
            "app_info", "iv_set_transform", "html", "slidable", "sticky_headers")


def _mod(name, attr, method=None):
    def probe():
        try:
            obj = getattr(importlib.import_module(name), attr, None)
        except ImportError:
            return False
        return obj is not None and (method is None or hasattr(obj, method))
    return probe


PROBES = {
    "scanner": _mod("flet_barcode_scanner", "BarcodeScanner"),                        # E1, not released
    "push": _mod("flet_firebase", "FirebaseMessaging"),                               # E2
    "analytics": _mod("flet_firebase_analytics", "FirebaseAnalytics"),                # E2 separate wheel + OD-3 (D-111)
    "local_notifications": _mod("flet_notifications", "LocalNotifications", "zoned_schedule"),  # E3 (OD-15 name)
    "calendar": _mod("flet_add_to_calendar", "AddToCalendar"),                        # E4
    "html": _mod("flet_html", "Html"), "slidable": _mod("flet_slidable", "Slidable"),  # E5/E6, 27.1, names TBD
    "refresh_indicator": lambda: hasattr(ft, "RefreshIndicator"),                     # U1: absent today
    "app_info": lambda: hasattr(ft.Page, "get_app_info"),                             # U4: absent today
    "iv_set_transform": lambda: hasattr(ft.InteractiveViewer, "set_transform"),       # U3: absent today
    "sticky_headers": lambda: False,                                                  # U2: probe set when merged
}


@ft.observable
@dataclass
class Caps:
    scanner: bool = False; push: bool = False; local_notifications: bool = False; calendar: bool = False
    analytics: bool = False; refresh_indicator: bool = False; app_info: bool = False
    iv_set_transform: bool = False; html: bool = False; slidable: bool = False; sticky_headers: bool = False
    reduce_motion: bool = False; high_contrast: bool = False; dark_os: bool = False; wide: bool = False  # device
    window_height: float = 0.0                                  # viewport; Staff sheet max height (SHELL-07)

    def derive(self, manifest: frozenset[str], remote: Mapping[str, bool]) -> None:
        """On only if bundled (CI manifest) AND the probe passes AND not vetoed: remote can only veto."""
        for k in CAP_KEYS:
            setattr(self, k, k in manifest and PROBES[k]() and remote.get(k) is not False)

    def apply_device(self, feats, page: ft.Page) -> None:      # feats: AccessibilityFeatures
        self.reduce_motion = bool(feats.reduce_motion or feats.disable_animations)
        self.high_contrast = bool(feats.high_contrast)
        self.dark_os = page.platform_brightness == ft.Brightness.DARK
        self.wide = (page.width or 0) >= 992
        self.window_height = page.height or 0.0

    def apply_size(self, width: float, height: float) -> None:   # Stores.on_resize(e: ft.PageResizeEvent)
        self.wide = width >= 992
        self.window_height = height

    def key_tuple(self) -> tuple[bool, ...]:
        return tuple(getattr(self, k) for k in CAP_KEYS)
```

`tools/caps_manifest.py` writes `build_info.CAPS`: extension keys from the bundled `[tool.flet.android|ios].dependencies`, core keys when the pinned Flet contains the U item. `flet run` uses the stub's **empty** manifest, so the companion app never gets controls it lacks. `derive()` re-runs on every app-config change, and `python -m pycon_us.platform.caps` prints the matrix for release notes.

### 12.2 Protocols and provider selection (D-75)

| Protocol | Interim (shipped, tested) | Upgrade | Cap |
|---|---|---|---|
| `BadgeScanner.surface(active, on_payload)` | `ManualEntryScanner` | `MobileScanner`: E1 `BarcodeScanner(formats=[BarcodeFormat.QR_CODE], facing=CameraFacing.BACK, on_detect)` | `scanner` |
| `PushService` | `BannerPoller` | `FirebasePush` (E2) | `push` |
| `Reminders` | `InAppReminders` + `IcsReminderPack` | `ScheduledReminders` (E3; cancel 8000–80xx, reschedule enabled future ones) | `local_notifications` |
| `Calendar.add_session(s)` | `IcsShare` (`share_files([ft.ShareFile.from_bytes(ics, mime_type="text/calendar", name=…)])`) | `NativeCalendar` (E4 `AddToCalendar.add_event`) | `calendar` |
| `Analytics` / `AppInfo` | `NullAnalytics` / `BuildInfoAppInfo` | `FirebaseAnalytics` (E2's separate `flet-firebase-analytics` wheel, OD-3, D-111) / `PageAppInfo` (U4) | `analytics` / `app_info` |
| `Refreshable(content, on_refresh)` | content + AppBar button | `getattr(ft, "RefreshIndicator")(…)` (U1) | `refresh_indicator` |

```python
def select_providers(caps: Caps, svc: "Services", st: "Settings") -> Providers:
    if caps.scanner:
        from pycon_us.platform.scanner.mobile import MobileScanner     # the only module importing E1
        scanner = MobileScanner()
    else:
        scanner = ManualEntryScanner()
    if st.demo or st.dev:
        scanner = SimulatedScanner(inner=scanner)                    # adds "Simulate Scan" (D-84)
    return Providers(
        scanner=scanner,
        push=FirebasePush(svc) if caps.push else BannerPoller(),
        reminders=ScheduledReminders(svc) if caps.local_notifications else InAppReminders(),
        calendar=NativeCalendar() if caps.calendar else IcsShare(svc.share),
        analytics=FirebaseAnalytics() if caps.analytics else NullAnalytics(),
        app_info=PageAppInfo() if caps.app_info else BuildInfoAppInfo())


def use_providers() -> Providers:                                     # hook
    caps, svc = use_caps(), use_services()
    return ft.use_memo(lambda: select_providers(caps, svc, svc.settings), [caps.key_tuple()])
```

Screens use providers only and never import an extension. The fallback-parity suite runs every UI flow with all capabilities faked on, then off.

### 12.3 Notification channels (D-76, D-77)

| Toggle (UI order) | 27.0 in-app | With E2 topic | With E3 |
|---|---|---|---|
| `lightning`, `openSpace` | app-content reminder rows: in-app banner during `[at, at + 30 min)`, `.ics` `VALARM` | – | `zoned_schedule`, ids 8000+ |
| `announcements` | app-config banners + keynote reminders | `announcements` | keynote reminders |
| `scheduleChanges` | change-log banner + banners | `schedule-changes` | – |
| `dailyDigest` | banners | `daily-digest` | – |
| `emergency` | banners, **always in-app** (OD-18) | `emergency` | – |

Topics are in Firebase project `pycon-us-2023-mobile`. In mixed state the master toggle shows off and "Mixed"; flipping it writes all six (NOTIF-02). App-config banners are persistent `TopToast`s showing `text` (with its optional `url` link) and a close button; later, E2 foreground pushes show "{title}: {body}" (title defaulting to 'PyCon US'). Both are hidden when all four push categories are off except emergency (NOTIF-08). The OS push prompt comes only from E2, at the end of Welcome or on the first Notifications visit, never on web (D-78). `AppConfigStore` drives NOTIF-12 and LIVE-02..04. The Dev Tools test notification uses id 8999 (DEV-06).

---

## 13. Server-driven files (D-63, PLAN §9.4)

Served `no-cache` from `us.pycon.org/{YEAR}/mobile/` or PSF Firebase Hosting (P7). Fetched on start, on resume and every 5 min in the foreground (the poller parks on `await page.wait_until_visible()`); failures are silent. `app-content` also ships bundled. CI validates both with `jsonschema` (draft 2020-12).

**`config/app-config.schema.json`**

```json
{"$schema": "https://json-schema.org/draft/2020-12/schema",
 "type": "object", "required": ["schema", "latest", "min_supported"], "additionalProperties": false,
 "properties": {
  "schema": {"const": 1},
  "latest": {"type": "object", "required": ["version", "build"], "additionalProperties": false,
             "properties": {"version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
                            "build": {"type": "integer", "minimum": 27000}}},
  "min_supported": {"type": "object", "additionalProperties": false,
                    "properties": {"ios": {"type": "integer"}, "android": {"type": "integer"}, "web": {"type": "integer"}}},
  "store_urls": {"type": "object", "additionalProperties": false,
                 "properties": {"ios": {"type": "string", "format": "uri"}, "android": {"type": "string", "format": "uri"}}},
  "banners": {"type": "array", "maxItems": 20, "items": {"$ref": "#/$defs/banner"}},
  "features": {"type": "object", "additionalProperties": {"type": "boolean"},
               "propertyNames": {"enum": ["scanner", "push", "local_notifications", "calendar", "analytics",
                 "refresh_indicator", "app_info", "iv_set_transform", "html", "slidable", "sticky_headers",
                 "lead_retrieval", "door_check", "swag", "coc"]}},
  "feed_url": {"type": ["string", "null"], "format": "uri"},
  "content_url": {"type": ["string", "null"], "format": "uri"},
  "staff_data_purge_after": {"type": "string", "format": "date-time"}},
 "$defs": {"banner": {"type": "object", "required": ["id", "category", "severity", "text"], "additionalProperties": false,
   "properties": {"id": {"type": "string", "minLength": 1},
                  "category": {"enum": ["announcements", "scheduleChanges", "dailyDigest", "emergency"]},
                  "severity": {"enum": ["info", "warning", "critical"]},
                  "text": {"type": "string", "minLength": 1, "maxLength": 280},
                  "url": {"type": ["string", "null"], "format": "uri"},
                  "starts_at": {"type": "string", "format": "date-time"},
                  "ends_at": {"type": "string", "format": "date-time"}}}}}
```

**`config/app-content.schema.json`**

```json
{"$schema": "https://json-schema.org/draft/2020-12/schema",
 "type": "object", "required": ["schema", "year", "conference", "urls", "room_pins", "venue_spots"],
 "additionalProperties": false,
 "properties": {
  "schema": {"const": 1},
  "year": {"type": "integer", "minimum": 2027},
  "conference": {"type": "object", "required": ["name", "dates", "venue"], "additionalProperties": false,
    "properties": {"name": {"type": "string"}, "venue": {"type": "string"},
      "dates": {"type": "object", "required": ["start", "end"],
                "properties": {"start": {"type": "string", "format": "date"}, "end": {"type": "string", "format": "date"}}}}},
  "keynotes": {"type": "array", "items": {"type": "object", "required": ["session_ids", "name"], "additionalProperties": false,
    "properties": {"session_ids": {"type": "array", "items": {"type": "string"}}, "name": {"type": "string"},
                   "role": {"type": "string"}, "abstract_md": {"type": "string"}, "photo": {"type": "string", "format": "uri"},
                   "kind": {"enum": ["keynote", "panel", "steering-council"]}}}},
  "reminders": {"type": "array", "items": {"type": "object", "required": ["id", "category", "at", "title", "body"],
    "additionalProperties": false,
    "properties": {"id": {"type": "integer", "minimum": 8000, "maximum": 8099},
                   "category": {"enum": ["lightning", "openSpace", "announcements"]},
                   "at": {"type": "string", "format": "date-time"}, "title": {"type": "string"}, "body": {"type": "string"}}}},
  "wifi": {"type": "object", "properties": {"ssid": {"type": "string"}, "password": {"type": "string"}}},
  "wifi_sponsor_needle": {"type": ["string", "null"]},
  "booths": {"type": "object", "additionalProperties": {"$ref": "#/$defs/rect"}},
  "room_pins": {"type": "object", "additionalProperties": {"$ref": "#/$defs/pin"}},
  "venue_spots": {"type": "object", "additionalProperties": {"$ref": "#/$defs/pin"}},
  "display_time_overrides": {"type": "array", "items": {"type": "object", "required": ["match", "start_offset_minutes"],
    "additionalProperties": false,
    "properties": {"match": {"type": "string", "format": "regex"}, "start_offset_minutes": {"type": "integer"}}}},
  "new_tracks": {"type": "array", "items": {"type": "string"}},
  "urls": {"type": "object", "additionalProperties": {"type": "string", "format": "uri"}},
  "sponsored_spaces": {"type": "object", "additionalProperties": {"type": "string"}},
  "concept3d_id": {"type": ["string", "null"]},
  "coc_contacts": {"type": "array", "items": {"type": "object", "required": ["label", "kind", "value"], "additionalProperties": false,
    "properties": {"label": {"type": "string"}, "kind": {"enum": ["tel", "mailto", "https"]}, "value": {"type": "string"}}}}},
 "$defs": {
  "pin": {"type": "object", "required": ["label", "floor", "x", "y"], "additionalProperties": false,
          "properties": {"label": {"type": "string"}, "sublabel": {"type": ["string", "null"]},
                         "floor": {"enum": ["1", "2", "3", "4"]},
                         "x": {"type": "number", "minimum": 0, "maximum": 100}, "y": {"type": "number", "minimum": 0, "maximum": 100}}},
  "rect": {"type": "object", "required": ["x", "y", "w", "h"], "additionalProperties": false,
           "properties": {"x": {"type": "number", "minimum": 0, "maximum": 1}, "y": {"type": "number", "minimum": 0, "maximum": 1},
                          "w": {"type": "number", "exclusiveMinimum": 0, "maximum": 1}, "h": {"type": "number", "exclusiveMinimum": 0, "maximum": 1}}}}}
```

`features` is veto-only (`true` = absent). `booths` are ratios of the 9931×7021 reference raster; `room_pins` are keyed by `normalize_room_key`. `urls` holds the year-scoped links (open-space sign-up, lightning talks, sprints, store listings, report an issue).

---

## 14. DEMO mode (PLAN §3.9, D-84)

| Aspect | `DEMO=1` (baked into `build_info`) |
|---|---|
| Feed | bundled `assets/demo/conference.json`; no network feed refresh |
| Clock | `FAKE_NOW` = a fixed conference Saturday, 10:05 local: Now & Next, Jump to Now and the "Changed" chip are deterministic |
| API / app-config | staging; needed only for the sync step and the live `scanner` veto |
| Scanner / DB | `SimulatedScanner(inner=camera or manual)` / `pycon-demo.db` |
| Stage script | airplane mode → cached schedule, Now, HC-dark, swipe favourite, floor-plan zoom → scan shows PENDING → online → SYNCED → veto `scanner` in staging app-config → manual entry appears with no restart (`Caps.derive`) |

Goldens use the same bundled feed with `PYCON_FAKE_NOW`.

---

## 15. Errors and observability (PLAN §5.8, D-85..D-88)

### 15.1 `@safe` (`services/safe.py`)

```python
DEFAULT_TOAST = "Something went wrong. Please try again."


def NOOP() -> None:                       # cleanup= for long-running async effects (GR-3)
    return None


def report(ex: BaseException, where: str) -> None:
    logging.getLogger("pycon_us").error("unhandled in %s", where, exc_info=ex)   # → crash handler


def safe(fn=None, *, toast: str | None = DEFAULT_TOAST):
    """Report + non-blocking top toast instead of SESSION_CRASHED. functools.wraps sets __wrapped__, so
    inspect.signature (Flet's get_param_count) still sees the real arity; async stays async (GR-2)."""
    def deco(f):
        where = f"{f.__module__}.{f.__qualname__}"
        if inspect.iscoroutinefunction(f):
            @functools.wraps(f)
            async def aw(*a, **k):
                try:
                    return await f(*a, **k)
                except asyncio.CancelledError:
                    raise                                 # effect re-run or unmount
                except Exception as ex:
                    report(ex, where)
                    _toast(toast)
            return aw

        @functools.wraps(f)
        def sw(*a, **k):
            try:
                return f(*a, **k)                         # sync effects may return a cleanup callable
            except Exception as ex:
                report(ex, where)
                _toast(toast)
        return sw

    return deco(fn) if fn is not None else deco
```

`_toast` uses the page bound in `Stores.create`: `show_top_toast` shows `ft.Banner(content=..., actions=[ft.TextButton("Dismiss", on_click=…)])` with `page.show_dialog()` (a `Banner` needs at least one visible action and has no duration), and both that action and an app-level auto-hide task close it with `page.pop_dialog()` (PLAN §5.8). Component-owned dialogs use `ft.use_dialog` (D-66); bottom messages use `ft.SnackBar`. Tests: `test_safe_preserves_arity_and_coroutine`, `test_safe_reraises_cancelled`. A CI AST lint requires every `on_*=` and `use_effect` setup to be a `@safe` name or a lambda calling only one, and rejects lambdas calling GR-1 coroutine APIs.

### 15.2 Crash reporting (`services/crash.py`, OD-4, spike S6)

```python
def install(s: "Stores") -> None:
    h = ForwardHandler(level=logging.INFO)            # ring buffer (last 50, scrubbed) + Sentry for >= ERROR
    logging.getLogger("flet").addHandler(h)           # Flet logs "Unhandled error in 'on_x' handler"
    logging.getLogger("pycon_us").addHandler(h)
    asyncio.get_running_loop().set_exception_handler(asyncio_handler)
    if settings.SENTRY_DSN and not s.prefs.crash_opt_out:
        sentry_sdk.init(dsn=settings.SENTRY_DSN, environment=build_info.PYCON_ENV, send_default_pii=False,
                        release=f"pycon-us@{build_info.VERSION}+{build_info.BUILD_NUMBER}", before_send=scrub_event)
        sentry_sdk.set_tag("caps", ",".join(k for k in CAP_KEYS if getattr(s.caps, k)))
```

`scrub` drops emails, badge codes, key, secret, `X-API-*` headers and signed queries. `page.on_error` (Flutter-side) and `sys.excepthook` (never fires) aren't relied on, and asyncio only reports unretrieved task errors at GC, which is why every effect is `@safe`. A corrupt cache is deleted and the app continues (D-88); bad bundled app-content fails CI. "Share diagnostics" (INFO-04) shares redacted JSON (versions, caps, outbox counts, last 50 log lines) via `share_files([ft.ShareFile.from_bytes(data, mime_type="application/json", name="pycon-diagnostics.json")])`.

---

## 16. What the spikes must confirm

Spike S2: `zoneinfo` + `tzdata` on all targets. Spike S3: parse ≤ 400 ms on a Pixel 6a, and whether day lists can be non-lazy (D-68). Spike S6: `sentry-sdk` on device. Spike S9: the query in `page.route`; encoded drill ids (`%3A`, `%20`) round-tripping; a global modal over a drill, with Back and the explicit Close (`back` query) both returning to the drill URL; whether page handlers set in bootstrap need `page.update()`; the NavigationBar index after the Scanner intercept.

---

## 17. Flet API ledger (local SDK, 2026-10-11)

**Exist and are used** (`*` = coroutine): every hook, router API, `Page` member, service method and control field that appears in the code above was introspected. The non-obvious ones:
- `use_effect(setup, dependencies, cleanup)`, and `Route(path, index, component, children, loader, outlet, modal, recursive)`.
- `Page`: `navigate` (sync), `push_route*`, `show_drawer*`/`close_drawer*`, `wait_until_visible*`, `platform_brightness`, `pyodide`, `on_app_lifecycle_state_change`.
- Coroutine services: `SharedPreferences*`, `StoragePaths*`, `UrlLauncher.launch_url*`, `Share.share_files*`, `Clipboard.set*`, `HapticFeedback*`, `SemanticsService.announce_message*/get_accessibility_features*`.
- Controls: `ListView.build_controls_on_demand`/`scroll_to*`, `Dismissible.confirm_dismiss*`, `InteractiveViewer.zoom*/pan*/reset*`, `NavigationBar.selected_index: int`, `IconButton.badge: str | Badge`.
- Dialog controls: `Banner` and `CupertinoBottomSheet` are `DialogControl`s; `CupertinoActionSheet` is not, so it is wrapped in `CupertinoBottomSheet`.
- Extensions: `flet_secure_storage.SecureStorage*`, and `flet_permission_handler.PermissionHandler*` with `Permission.CAMERA`.

**Do not exist, each with its interim:** `ft.RefreshIndicator` (U1 → button), sticky headers (U2 → dividers), `InteractiveViewer.set_transform/zoom_to_rect` (U3 → reset/zoom/pan), `Page.get_app_info` (U4 → `build_info`), iOS entitlements (U5), Android `<queries>` (U6), `core_library_desugaring` (U7) and resource-valued (inline-table, `android:resource`) app `meta_data` (U8; plain string `[tool.flet.android.meta_data]` / `--android-meta-data` already exist), `ft.use_route_search` (U9 → `use_query`), `AppBar.bottom` (U10 → first row), non-fatal handler errors (U15 → `@safe`), `flet_barcode_scanner.BarcodeScanner` (E1 → manual/HID), `flet_firebase.*` (E2 → banners, `NullAnalytics`), `LocalNotifications.zoned_schedule` (E3 → in-app + `.ics`), `flet_add_to_calendar.AddToCalendar` (E4 → `.ics` share), `flet-html` (E5 → `html_md`), `flet-slidable` (E6 → `Dismissible`). App-side helpers, not Flet: `use_query`, `use_tokens`, `use_providers`, `shell_view`, `Caps.wide` (the matrix's `use_window_width()`).

---

## 18. Discrepancies with PLAN.md and the decisions record (this document follows the right-hand column)

The decisions record is binding and is amended before a document diverges. Every row below is now **resolved**: it names the D-number (section P of [`decisions.md`](decisions.md)) that records it, and PLAN.md and the feature matrix follow. The left column keeps the superseded wording for reference.

| # | PLAN / decisions say | Correct behaviour used here |
|---|---|---|
| 1 | PLAN §5.4 and D-50 list `kind-day-name-start` as a stable synthetic id | **Resolved by D-115** (supersedes the D-50 id wording; matrix DATA-06 agrees). That is Ionic's **collapse key**. Collapsed rows keep Ionic's **id** `` `${kind}-${room}-${start}` `` (e.g. `break--2026-05-13T12:30:00-07:00`), which is what the server-side favourites already contain. |
| 2 | D-56: "lead sponsors and capture 5 s"; `mobile_state` PATCH not listed | **Resolved by D-116** (supersedes the D-56 timeout list). Ionic: lead capture 2 s, lead note 2 s, CoC capture 5 s, PATCH 2 s. These values are used. |
| 3 | §N.2 covers effect start only | **Resolved by D-122.** Async effect tasks are cancelled on unmount only when `cleanup` is callable (GR-3). Long effects pass `cleanup=NOOP`; `App` passes `cleanup=s.shutdown`, as the PLAN §5.3 sketch now does. |
| 4 | – (missing from §N) | **Resolved by D-122.** An observable assignment runs `old == new`: big values must be `eq=False` containers with no object cycles (GR-8). |
| 5 | PLAN §5.2: every view-level screen returns its own View | **Resolved by D-121.** The Router wraps `not_found()` in a View itself, so `NotFound` returns content. |
| 6 | D-60 key list / §M file names | **Resolved by D-117.** Additions: web-only `feed_cache` key (D-49 puts the web cache in SharedPreferences), `app-content-{YEAR}.json` and the feed `.meta.json` sidecar. |
| 7 | D-59 columns | **Resolved by D-117.** No column for the server response (lead first name): it is merged into `payload_json.result`. The schema is unchanged. |
| 8 | D-90 `build_info` fields | **Resolved by D-125.** Add `YEAR`, `CONF_TZ`, `SITE_URL` (from `config/conference.json`) so the 2028 rollover needs no code edit (criterion S12). |
| 9 | THEME-09 "MotionContext"; SHELL-14 `use_window_width()` | **Resolved by D-132**; matrix THEME-09 and SHELL-14 now use `Caps.reduce_motion` and `Caps.wide`. A plain context would not be observable and `use_window_width` is not a Flet hook. Both live in `Caps` (`reduce_motion`, `wide` via `page.on_resize`). |
| 10 | D-65 "favorite `#fbbf24`" | **Resolved by D-118.** `#fbbf24` is the gold star. Ionic's `--ion-color-favorite` is `#69bb7b`, used by the swipe action. Both are tokens. |
| 11 | D-64 "`CupertinoActionSheet`" picker | **Resolved by D-118.** It is not a `DialogControl`; it is shown inside `ft.CupertinoBottomSheet`. |
| 12 | PLAN §5.5 "10 tries, then failed" | **Resolved by D-117.** Parity is `tries > 10`, i.e. failed on the 11th failure. Kept. |
| 13 | D-54: diff over start, end, room, title **and `cancelled`** | **Resolved by D-124.** `cancelled` is not diffed: the feed's `cancelled` is always `false`, and cancellations arrive as placeholder slots, so they surface as `removed` (§5.6). |
| 14 | PLAN §5.3 sketch gates on `s.prefs.loaded` read directly in `App` | **Resolved by D-122.** A plain attribute read does not subscribe, so `App` would never re-render when the flag flips. `App` reads `Prefs` through `ft.use_state(s.prefs)` (which subscribes to an Observable), and bootstrap sets `loaded` only after the theme is applied (§2, §4.4). |
| 15 | D-70 ">= 7:1 HC" for palette tokens | **Resolved by D-119.** `favorite_star` stays Ionic's `#fbbf24` in HC modes (5.1:1 on the fixed `#3B3EA9` header; the previous HC values `#4a0072`/`#ffd60a` were the swipe colour and gave 1.6:1 in HC light). |
| 16 | – (floor-plan URL in PLAN §5.2 is `/floor-plan/:plan?pin=`) | **Resolved by D-123.** Entry points add `back=<opener path>` so the explicit "Close floor plan" button returns to the Router's base without reading `page.views` (§3.5). |
