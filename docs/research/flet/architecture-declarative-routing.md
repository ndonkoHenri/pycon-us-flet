# PyCon US mobile → Flet 1.1 (declarative) — architecture, routing, state, theming, testing

Source of truth used for every API below: the local monorepo at
`/Users/ndonkohenri/PycharmProjects/flet-dev/flet` (main, 1.1.0-dev). Paths are abbreviated:

- `SDK` = `sdk/python/packages/flet/src/flet`
- `EXT` = `sdk/python/packages`
- `IONIC` = `/Users/ndonkohenri/PycharmProjects/flet-dev/others/pycon-us/excluded/pycon-us-mobile/src/app`

Everything marked **GAP** was searched for and is not in the local source.

---

## 0. What the Ionic app actually is (facts the design depends on)

| Ionic fact | Where |
|---|---|
| Root routes: `''→/tutorial` (guarded by `CheckTutorial`), `account`, `login`, `app` (tabs), `tutorial` | `IONIC/app-routing.module.ts` |
| Tabs shell `/app/tabs/...` with children `schedule` (+`session/:sessionId`), `tracks/:trackSlug`, `speakers` (+`session/:sessionId`, `speaker-details/:speakerId`), `sponsors` (+`sponsor-detail/:sponsorId`), `expo-hall`, `conference-map`, `lead-retrieval`, `door-check`, `t-shirt-redemption`, `mask-violation`, `coc`, `wifi`, `notifications`, `rooms` (+`room-detail/:roomSlug`, `session/:sessionId`), `venues-hours`, `lightning-talks`, `session-types`, `about-pycon`, `about-psf`, `social-media`, `sprints`, `keynote-speakers`, `job-listings`, `now`, `help`, `account`, `login`, `dev-tools`, `''→/app/tabs/schedule` | `IONIC/pages/tabs-page/tabs-page-routing.module.ts` |
| Bottom tab bar: Speakers, Map, Schedule, Now, Scanner (staff → bottom-sheet "Staff Tools" `ion-modal` with breakpoints), Login (when logged out); plus a rotating sponsor banner tab-bar | `IONIC/pages/tabs-page/tabs-page.html` |
| Side menu (`ion-split-pane` + `ion-menu`): sections Apps (conditional on `hasMaskViolation/hasDoorCheck/hasLeadRetrieval`), Schedule, Presentations (accordion), Events, Expo & Sponsors, Information (accordion), plus "Hello, {nickname}" and Dev Tools | `IONIC/app.component.html`, page lists in `IONIC/app.component.ts` |
| Theme: `theme ∈ {'light','dark','high-contrast-light','high-contrast-dark'}` persisted under storage key `theme`, applied as CSS classes on `ion-app` | `IONIC/app.component.html`, `IONIC/providers/user-data.ts` (`getTheme/setTheme`) |
| API auth: `X-API-Key`, `X-API-Signature = sha1(secret + timestamp + method + url + body).hex`, `X-API-Timestamp`; 2 s timeouts | `IONIC/providers/pycon-api.ts` (`buildRequestAuthHeaders`) |
| Login: `POST {base}/2026/api/v1/authenticate/ {email,password}` → `{nickname,key,secret,...}` stored in Ionic Storage | `IONIC/pages/login/login.ts`, `user-data.ts` |
| Feed: `GET {base}/2026/schedule/conference.json` (10 s timeout), cache under `schedule-cache`, serve cache first then network, `processData()` builds schedule/speakers/tracks/sessions/posters/sprints/job-listings | `IONIC/providers/conference-data.ts` |
| Capacitor plugins used: `@capacitor-mlkit/barcode-scanning` (map.ts, door-check), `@capacitor/inappbrowser`, `@ebarooni/capacitor-calendar`, `@capacitor/share` + `filesystem`, `@capacitor/network`, `@capacitor/local-notifications`, `@capacitor-firebase/messaging` + `analytics`, `@capacitor/live-updates`, `splash-screen`, `haptics`, `status-bar`, `keyboard`, `device` | `package.json`, `app.component.ts`, `notifications.service.ts` |
| Overlays used: `ModalController` (schedule-filter, lead-note, floor-plan, redemption), `AlertController`, `LoadingController`, `ToastController`, `ion-refresher`, `ion-searchbar`, `ion-segment` (days) | `pages/schedule/schedule.ts`, `schedule.html`, `speaker-list.html`, `map.html` |

---

## 1. Recommended project layout

```
pycon_us/
├── pyproject.toml                # [tool.flet] product/org/app.path="src"; deps: flet, httpx, flet-permission-handler, flet-secure-storage
├── src/
│   ├── main.py                   # def main(page): page.render_views(App)   (entry for ft.run / flet build / flet test)
│   ├── assets/                   # icons, img/, fonts/  (ft.run(..., assets_dir=...), see §1.1)
│   └── pycon_us/
│       ├── config.py             # BASE_URL="https://us.pycon.org", YEAR="2026", TZ="America/Los_Angeles"
│       ├── app.py                # App component: contexts, theme effect, bootstrap, Router
│       ├── routes.py             # ROUTES: list[ft.Route]  (§2)
│       ├── models/
│       │   ├── feed.py           # @dataclass Conference, Session, Speaker, Room, Track, Sponsor, Poster, Sprint, JobListing, OpenSpace
│       │   ├── user.py           # @dataclass UserProfile(nickname, email, key, secret, features)
│       │   └── prefs.py          # ThemeChoice(Enum), NotificationPrefs, ScheduleFilters
│       ├── services/
│       │   ├── api_client.py     # PyConAPI (httpx.AsyncClient + sha1 signing)  (§6)
│       │   ├── feed_loader.py    # FeedService: cache-first load, refresh, parse → models
│       │   ├── cache.py          # FileCache over ft.StoragePaths cache dir (JSON)
│       │   ├── auth.py           # AuthService: login/logout, key/secret in flet-secure-storage
│       │   ├── favorites.py      # FavoritesService: local list + PATCH mobile_state sync
│       │   ├── prefs.py          # PrefsService over ft.SharedPreferences
│       │   ├── notifications.py  # Notifications Protocol + NoopNotifications (GAP, see §9)
│       │   ├── scanner.py        # BarcodeScanner Protocol + ManualEntryScanner fallback (GAP)
│       │   └── platform.py       # Haptics/Share/OpenUrl/Connectivity wrappers (ft services)
│       ├── state/
│       │   ├── store.py          # @ft.observable AppStore, AuthState, UiState
│       │   └── contexts.py       # StoreContext, ServicesContext = ft.create_context(None)
│       ├── components/           # shared widgets (all @ft.component)
│       │   ├── tabs_shell.py     # outlet layout: AppBar + NavigationDrawer + NavigationBar
│       │   ├── app_drawer.py     # the side menu (sections, conditional staff entries)
│       │   ├── session_tile.py, speaker_tile.py, sponsor_banner.py, day_segment.py,
│       │   ├── search_field.py, empty_state.py, loading.py, toast.py (use_toast hook)
│       │   └── staff_tools_sheet.py
│       ├── screens/              # one module per Ionic page, grouped like the Ionic menu
│       │   ├── tutorial.py, login.py, account.py, now.py, dev_tools.py, notification_settings.py
│       │   ├── schedule/   schedule.py, schedule_filter.py (modal), session_detail.py, track_list.py
│       │   ├── speakers/   speaker_list.py, speaker_detail.py, keynote_speakers.py
│       │   ├── rooms/      rooms.py, room_detail.py
│       │   ├── events/     lightning_talks.py, sprints.py          # open-spaces = track_list("open-spaces")
│       │   ├── expo/       sponsors.py, sponsor_detail.py, expo_hall.py, job_listings.py
│       │   ├── info/       about_pycon.py, coc.py, wifi.py, venues_hours.py, session_types.py,
│       │   │               about_psf.py, social_media.py, conference_map.py, help.py
│       │   └── staff/      lead_retrieval.py, door_check.py, swag_pickup.py, mask_violation.py, lead_note.py (modal)
│       └── theme/
│           ├── themes.py         # build_light(), build_dark(), build_hc_light(), build_hc_dark() → ft.Theme
│           └── apply.py          # apply_theme(page, choice)
└── tests/
    ├── unit/                     # pure Python: api signing, feed parsing, store logic (no Flet runtime)
    └── ui/                       # flet pytest plugin: test_navigation.py, test_schedule.py, golden/<platform>/...
```

### 1.1 Entry point (verified APIs)

- `ft.run(main, before_main=None, name="", host=None, port=0, view=AppView.FLET_APP, assets_dir=DEFAULT_ASSETS_DIR, upload_dir=None, web_renderer=WebRenderer.AUTO, route_url_strategy=RouteUrlStrategy.PATH, no_cdn=False, export_asgi_app=False)` — `SDK/app.py:68-80`. A relative `assets_dir` is resolved against the caller module; env `FLET_ASSETS_DIR` overrides it (`SDK/app.py:677-731`).
- `page.render_views(component, *args, **kwargs)` replaces `page.views` with the rendered list, calls `page.update()`, enables components mode and starts the batched update scheduler (`SDK/controls/page.py:776-811`). `page.render(...)` does the same into `page.views[0].controls` (`page.py:751`).

```python
# src/main.py
from pathlib import Path
import flet as ft
from pycon_us.app import App

def main(page: ft.Page):
    page.title = "PyCon US 2026"
    page.render_views(App)          # Router(manage_views=True) returns list[View]

if __name__ == "__main__":
    ft.run(main, assets_dir=str(Path(__file__).parent / "assets"))
```

---

## 2. Navigation model

### 2.1 How `ft.Router` matches and renders (from `SDK/components/router.py`)

- `Route(path=None, index=False, component=None, children=None, loader=None, outlet=False, modal=False, recursive=False)` — `router.py:48-108`.
- `Router(routes, not_found=None, manage_views=False)` — `router.py:593-598`. It is a `@component`; it holds `location` via `use_state(page.route or "/")`, installs `page.on_route_change = lambda e: set_location(e.route)` in a mount effect, restores the previous handler on unmount (`router.py:660-720`).
- Matching: `_match_routes()` tries top-level routes in order; `_try_match()` compiles `repath.pattern(full_path)` (Express-style `:param`, `:param?`, `:param*`, `:param(\d+)`) and returns a **chain** of `_RouteMatch(route, params, full_path, resolved_path)` from outermost to innermost (`router.py:163-314`). Index routes match the parent path exactly (`:188`). A route with `children` first tries children; if none match and it has a `component`, it matches exactly (`:259-297`). Params from the whole chain are merged (`:797-799`). Loaders are called synchronously with the merged params on every Router render (`:802-805`).
- `manage_views=False`: one tree, layouts nest via `_outlet_context` (`:460-496`).
- `manage_views=True`: `_split_chain_into_view_levels()` makes every component-bearing match its **own View**, except matches with `outlet=True` that are not last, which become **layouts wrapping each View below them** (`:504-536`). Each View level is rendered inside `_view_path_context` / `_location_context` / `_params_context` (`:879-900`). `modal=True` routes are stacked on top of the previous non-modal chain (`:744-795`).
- Default back handling: `page.on_view_pop` is installed by the Router; on pop it navigates to the **previous view entry's `resolved_path`** computed structurally from the chain (`:672-713`), so shared `View.route` keys (used to suppress tab-switch animation) do not break back navigation. A pre-existing `page.on_view_pop` set **before** `render_views` is delegated to (`:674-680`).
- Hooks: `use_route_params()`, `use_route_location()`, `use_view_path()`, `use_route_outlet()`, `use_route_loader_data()`, `is_route_active(path, exact=False)` (`:340-452`). All are hooks (they call `use_context`) — fixed call count per render is mandatory.
- Navigation: `page.navigate(route, **query)` (sync, wraps `push_route` in `asyncio.create_task`, `page.py:1094-1106`) and `await page.push_route(route, **query)` (`page.py:1013`); query kwargs are appended via `page.query.post(kwargs)`; `page.query.get(key)` / `to_dict()` read them (`SDK/controls/query_string.py:74-94`). `await page.pop_views_until(route, result)` fires `page.on_views_pop_until` (`page.py:1108`).
- `View` fields used by the shell: `route`, `appbar`, `navigation_bar`, `drawer`, `end_drawer`, `floating_action_button`, `fullscreen_dialog`, `can_pop`, `on_confirm_pop`, `padding`, `bgcolor`, `scroll` (`SDK/controls/core/view.py:38-158`); `View.show_drawer()/close_drawer()` and `page.show_drawer()/close_drawer()` (`view.py:187-215`, `base_page.py:493-520`).

### 2.2 Route table (mirrors Ionic 1:1 so web URLs and deep links stay identical)

Design choices:

1. **One outlet layout = Ionic's `ion-tabs` + `ion-menu`.** `Route(path="app/tabs", component=TabsShell, outlet=True, children=[...])`. Because `outlet=True` layouts wrap *every* View below them (`router.py:530-533`), the bottom tab bar + drawer stay visible on nested detail pages, exactly like `ion-tabs`.
2. **List → detail as parent → child routes**, so the view stack is `[Schedule, SessionDetail]` and the AppBar back arrow / iOS swipe-back / Android back pop to the list. A grouping route without a component (Ionic's `path:'schedule', children:[...]`) would *not* put the list on the stack — `_split_chain_into_view_levels` skips component-less routes (`:525-526`).
3. **Modals**: schedule filter, lead-note, floor-plan, redemption, staff tools → `modal=True` child routes whose component returns `View(fullscreen_dialog=True)` (`router.py:74-91`), or `use_dialog(BottomSheet)` for the small ones (§5).
4. **Redirects** (`'' → /tutorial`, `/app/tabs → schedule`) are components that `navigate()` in a mount effect (same pattern as `examples/apps/router/auth_page/main.py:63-74`).

```python
# src/pycon_us/routes.py
import flet as ft
from pycon_us.components.tabs_shell import TabsShell
from pycon_us.screens import tutorial, login, account, now, dev_tools, notification_settings
from pycon_us.screens.schedule import schedule, schedule_filter, session_detail, track_list
from pycon_us.screens.speakers import speaker_list, speaker_detail, keynote_speakers
from pycon_us.screens.rooms import rooms, room_detail
from pycon_us.screens.events import lightning_talks, sprints
from pycon_us.screens.expo import sponsors, sponsor_detail, expo_hall, job_listings
from pycon_us.screens.info import (about_pycon, coc, wifi, venues_hours, session_types,
                                   about_psf, social_media, conference_map, help_page)
from pycon_us.screens.staff import lead_retrieval, door_check, swag_pickup, mask_violation, lead_note

def _redirect(to: str):
    @ft.component
    def Redirect():
        ft.use_effect(lambda: ft.context.page.navigate(to), [])
        return ft.View(route=ft.use_view_path(), controls=[ft.ProgressRing()])
    return Redirect

SESSION = ft.Route(path="session/:session_id", component=session_detail.SessionDetail)

ROUTES: list[ft.Route] = [
    ft.Route(index=True, component=_redirect("/tutorial")),      # CheckTutorial guard lives in Tutorial itself
    ft.Route(path="tutorial", component=tutorial.Tutorial),
    ft.Route(path="login", component=login.Login),
    ft.Route(path="account", component=account.Account),
    ft.Route(
        path="app/tabs", component=TabsShell, outlet=True,
        children=[
            ft.Route(index=True, component=_redirect("/app/tabs/schedule")),
            ft.Route(path="schedule", component=schedule.Schedule, children=[
                SESSION,
                ft.Route(path="filter", component=schedule_filter.ScheduleFilter, modal=True),
            ]),
            ft.Route(path="tracks/:track_slug", component=track_list.TrackList, children=[SESSION]),
            ft.Route(path="speakers", component=speaker_list.SpeakerList, children=[
                SESSION,
                ft.Route(path="speaker-details/:speaker_id", component=speaker_detail.SpeakerDetail,
                         children=[SESSION]),
            ]),
            ft.Route(path="keynote-speakers", component=keynote_speakers.KeynoteSpeakers,
                     children=[ft.Route(path="speaker-details/:speaker_id", component=speaker_detail.SpeakerDetail)]),
            ft.Route(path="rooms", component=rooms.Rooms, children=[
                ft.Route(path="room-detail/:room_slug", component=room_detail.RoomDetail, children=[SESSION]),
                SESSION,
            ]),
            ft.Route(path="sponsors", component=sponsors.Sponsors, children=[
                ft.Route(path="sponsor-detail/:sponsor_id", component=sponsor_detail.SponsorDetail)]),
            ft.Route(path="expo-hall", component=expo_hall.ExpoHall),
            ft.Route(path="conference-map", component=conference_map.ConferenceMap),
            ft.Route(path="job-listings", component=job_listings.JobListings),
            ft.Route(path="lightning-talks", component=lightning_talks.LightningTalks),
            ft.Route(path="sprints", component=sprints.Sprints),
            ft.Route(path="now", component=now.Now, children=[SESSION]),
            ft.Route(path="coc", component=coc.CoC),
            ft.Route(path="wifi", component=wifi.Wifi),
            ft.Route(path="venues-hours", component=venues_hours.VenuesHours),
            ft.Route(path="session-types", component=session_types.SessionTypes),
            ft.Route(path="about-pycon", component=about_pycon.AboutPyCon),
            ft.Route(path="about-psf", component=about_psf.AboutPSF),
            ft.Route(path="social-media", component=social_media.SocialMedia),
            ft.Route(path="help", component=help_page.Help),
            ft.Route(path="notifications", component=notification_settings.NotificationSettings),
            ft.Route(path="lead-retrieval", component=lead_retrieval.LeadRetrieval, children=[
                ft.Route(path="note/:attendee_id", component=lead_note.LeadNote, modal=True)]),
            ft.Route(path="door-check", component=door_check.DoorCheck),
            ft.Route(path="t-shirt-redemption", component=swag_pickup.SwagPickup),
            ft.Route(path="mask-violation", component=mask_violation.MaskViolation),
            ft.Route(path="account", component=account.Account),
            ft.Route(path="login", component=login.Login),
            ft.Route(path="dev-tools", component=dev_tools.DevTools),
        ],
    ),
]
```

Resulting view stacks (what `page.views` becomes, each wrapped by `TabsShell`):

| URL | stack |
|---|---|
| `/app/tabs/schedule` | `[Schedule]` |
| `/app/tabs/schedule/session/42` | `[Schedule, SessionDetail{session_id=42}]` — back → `/app/tabs/schedule` |
| `/app/tabs/speakers/speaker-details/7/session/42` | `[SpeakerList, SpeakerDetail, SessionDetail]` |
| `/app/tabs/schedule/filter` | `[Schedule] + modal [ScheduleFilter]` (local modal; pop → `/app/tabs/schedule`, `router.py:782-789`) |
| `/login`, `/tutorial` | single View, no tabs |

### 2.3 TabsShell (drawer + bottom bar + AppBar)

```python
# src/pycon_us/components/tabs_shell.py
import flet as ft
from pycon_us.state.contexts import StoreContext

TAB_ROUTES = ["/app/tabs/speakers", "/app/tabs/conference-map", "/app/tabs/schedule", "/app/tabs/now"]

@ft.component
def TabsShell():
    page = ft.context.page
    store = ft.use_context(StoreContext)          # observable → auto-subscribed (use_context.py:111-112)
    outlet = ft.use_route_outlet()
    location = ft.use_route_location()            # ONE hook call; compare strings below, never is_route_active() in loops
    view_path = ft.use_view_path()

    # Tab roots share a fixed route key so switching tabs does not slide; deeper views keep unique keys
    # (cookbook/router.md "Avoiding transition animation"; pop stays correct: router.py:689-708).
    is_tab_root = view_path in TAB_ROUTES
    tab_index = next((i for i, r in enumerate(TAB_ROUTES) if location.startswith(r)), 2)

    destinations = [
        ft.NavigationBarDestination(icon=ft.Icons.PEOPLE_OUTLINE, selected_icon=ft.Icons.PEOPLE, label="Speakers"),
        ft.NavigationBarDestination(icon=ft.Icons.MAP_OUTLINED, selected_icon=ft.Icons.MAP, label="Map"),
        ft.NavigationBarDestination(icon=ft.Icons.CALENDAR_MONTH_OUTLINED, selected_icon=ft.Icons.CALENDAR_MONTH, label="Schedule"),
        ft.NavigationBarDestination(icon=ft.Icons.RADIO_OUTLINED, selected_icon=ft.Icons.RADIO, label="Now"),
    ]
    targets = list(TAB_ROUTES)
    if store.auth.has_staff_tools:
        destinations.append(ft.NavigationBarDestination(icon=ft.Icons.QR_CODE_SCANNER, label="Scanner"))
        targets.append("/app/tabs/lead-retrieval")          # or open StaffToolsSheet (§5)
    elif not store.auth.logged_in:
        destinations.append(ft.NavigationBarDestination(icon=ft.Icons.LOGIN, label="Login"))
        targets.append("/app/tabs/login")

    def on_tab(e: ft.Event[ft.NavigationBar]):
        page.navigate(targets[e.control.selected_index])

    return ft.View(
        route="/app/tabs" if is_tab_root else view_path,
        can_pop=not is_tab_root,
        padding=0,
        appbar=ft.AppBar(
            leading=ft.IconButton(ft.Icons.MENU, on_click=lambda: page.run_task(page.show_drawer)),
            title=ft.Text("PyCon US 2026"),
        ),
        drawer=AppDrawer(),                                   # §2.4
        navigation_bar=ft.NavigationBar(selected_index=min(tab_index, len(destinations) - 1),
                                        destinations=destinations, on_change=on_tab),
        controls=[ft.SafeArea(content=outlet, expand=True)],
    )
```

Verified: `NavigationBar(destinations, selected_index, on_change, label_behavior, ...)` and `NavigationBarDestination(icon, label, selected_icon)` — `SDK/controls/material/navigation_bar.py:49-213`; `AppBar(leading, title, actions, automatically_imply_leading, ...)` — `material/app_bar.py:19-216`; `SafeArea(content, avoid_intrusions_*, minimum_padding)` — `core/safe_area.py:14-71`; `page.run_task(coro_fn, *args)` requires a coroutine *function* (`page.py:930-965`).

### 2.4 Drawer (Ionic side menu)

`NavigationDrawer.controls: list[Control]` accepts any control (`material/navigation_drawer.py:104`), so the Ionic menu with headers, accordions and conditional staff items becomes `ft.Text` headers + `ft.ListTile(selected=...)` rows + `ft.ExpansionTile(title, controls)` groups (`material/expansion_tile.py:53-110`, `material/list_tile.py:94-275`). Only the *static* item lists use `ListTile.selected = location.startswith(url)` from the single `use_route_location()` call. Close with `page.run_task(page.close_drawer)` after `page.navigate(url)`.

### 2.5 Back, deep links, web URLs

- Back arrow (`AppBar.automatically_imply_leading=True` default), iOS swipe-back, Android back button and the modal close "X" all end in `page.on_view_pop`, which the Router turns into `page.navigate(parent.resolved_path)` (`router.py:689-708`). `View.can_pop=False` + `on_confirm_pop` (`view.py:149-185`) for "discard changes?" on the lead-note modal.
- **Web**: the initial `page.route` is the browser path (`RouteUrlStrategy.PATH` default, `app.py:77`), so `https://host/app/tabs/schedule/session/42` renders the full stack from the URL alone; `page.push_route` updates browser history (`page.py:1013-1024`). `page.web`, `page.pwa` flags (`page.py:517-531`).
- **Mobile deep links** (custom scheme / universal links): the Router handles any `page.route` it is given, but **GAP** — no Flet API registers app links/intent filters; this needs Flutter project edits via `flet build` templates.

---

## 3. State strategy

Mechanics (verified): `@ft.observable` mixes `Observable` into any class, including dataclasses (`SDK/components/observable.py:19-45`); every public attribute assignment notifies unless `value_equal(old, new)`; `_`-prefixed attributes never notify (`:230-240`); `list`/`dict` fields are wrapped into `ObservableList`/`ObservableDict` which notify on mutation (`:257-452`); `notify()` for manual bursts (`:219`). A component re-renders when (a) an observable passed as an *argument* changes (`Component._subscribe_observable_args`, `components/component.py:234`), (b) an observable held in `use_state` changes (`hooks/use_state.py:62-85`), (c) an observable obtained via `use_context` changes (`hooks/use_context.py:111-112`), or (d) a `use_state` setter is called with a `!=` value (`use_state.py:101-114`).

| Data | Mechanism | Why |
|---|---|---|
| `AppStore.feed: Feed | None`, `feed_version`, `loading`, `error`, `online` | `@ft.observable @dataclass AppStore`, provided via `StoreContext = ft.create_context(None)` | Shared by every screen; refresh = reassign `store.feed` → all subscribed screens re-render |
| `AuthState(logged_in, nickname, features: Features)` | nested `@ft.observable`, exposed as `store.auth` | Drawer/tab bar subscribe to `store.auth` only, not the whole store |
| `favorites: list[str]` | field on `AppStore` (ObservableList) — **not a `set`**, sets are not wrapped | mutation notifies |
| `prefs: Prefs(theme: ThemeChoice, notifications: NotificationPrefs, filters: ScheduleFilters)` | `@ft.observable`; persisted via `PrefsService` after each change | theme effect in `App` depends on `store.prefs.theme` |
| Search text, selected day, drawer-open, "submitting" flags, scroll positions | `ft.use_state` in the screen | ephemeral, local |
| Derived lists (sessions for day X filtered by query/tracks) | `ft.use_memo(fn, [store.feed, day, query, tuple(filters)])` (`hooks/use_memo.py:27`) | avoid recomputing on every render |
| Services (API, feed loader, prefs, scanner, notifications) | plain objects in `ServicesContext`; created in `App` with `use_memo(..., [])` | not state; never re-rendered |
| Dialog visibility | `use_state(bool)` + `ft.use_dialog` (§5) | declarative |

```python
# src/pycon_us/state/store.py
from dataclasses import dataclass, field
import flet as ft
from pycon_us.models.feed import Feed
from pycon_us.models.prefs import Prefs

@ft.observable
@dataclass
class Features:
    lead_retrieval: bool = False
    door_check: bool = False
    mask_violation: bool = False

@ft.observable
@dataclass
class AuthState:
    logged_in: bool = False
    nickname: str = ""
    features: Features = field(default_factory=Features)
    @property
    def has_staff_tools(self) -> bool:
        return self.features.door_check or self.features.mask_violation or self.features.lead_retrieval

@ft.observable
@dataclass
class AppStore:
    feed: Feed | None = None
    feed_version: int = 0           # bump on every refresh so use_memo deps change even if Feed is a frozen dataclass
    loading: bool = False
    error: str | None = None
    favorites: list[str] = field(default_factory=list)
    auth: AuthState = field(default_factory=AuthState)
    prefs: Prefs = field(default_factory=Prefs)
```

```python
# src/pycon_us/app.py
import flet as ft
from pycon_us.state.store import AppStore
from pycon_us.state.contexts import StoreContext, ServicesContext
from pycon_us.services.registry import build_services      # creates ft.SharedPreferences(), ft.StoragePaths(), httpx client...
from pycon_us.routes import ROUTES
from pycon_us.theme.apply import apply_theme

@ft.component
def App():
    page = ft.context.page
    store, _ = ft.use_state(AppStore)                       # callable initializer → created once (use_state.py:49-65)
    services = ft.use_memo(lambda: build_services(page), [])  # services auto-register with the page (services/service.py:44-54)

    async def bootstrap():                                   # async setup → scheduled with asyncio.create_task (messaging/session.py:734)
        await services.prefs.load_into(store)
        await services.auth.restore_into(store)
        await services.feed.load(store)                      # cache first, then network (§6)
    ft.use_effect(bootstrap, [])

    ft.use_effect(lambda: apply_theme(page, store.prefs.theme), [store.prefs.theme])   # §4

    return ServicesContext(services, lambda: StoreContext(store, lambda: ft.Router(ROUTES, manage_views=True)))
```

`create_context(default)` returns a provider callable `provider(value, callback)` that pushes the value for the duration of `callback` (`hooks/use_context.py:52-76`); it is not a control, so it nests as lambdas as above (same as `examples/apps/router/auth_page/main.py:91-108`).

Login toggling menu items: `AuthService.login()` sets `store.auth.logged_in = True`, `store.auth.nickname`, and `store.auth.features.* = ...`. `TabsShell`/`AppDrawer` read `store.auth` through `use_context(StoreContext)` → re-render; the tab list grows/shrinks and the "Scanner"/"Login" destination appears. Guarded screens (`LeadRetrieval`, `DoorCheck`, `Account`) use the layout-guard pattern from `cookbook/router.md` ("Authentication"): `if not store.auth.logged_in: use_effect(lambda: page.navigate("/app/tabs/login"), []); return View(...)`.

---

## 4. Theming: light / dark / high-contrast-light / high-contrast-dark

Verified API: `page.theme`, `page.dark_theme`, `page.theme_mode: ThemeMode (SYSTEM|LIGHT|DARK)`, `page.theme_animation_style` (`SDK/controls/base_page.py:169-194`, `types.py:860-878`); `page.platform_brightness` + `page.on_platform_brightness_change` (`page.py:572,615`). `ft.Theme(color_scheme_seed, surfaces: ThemeSurfaces, font_family, use_material3, color_scheme: ColorScheme, text_theme: TextTheme, appbar_theme, navigation_bar_theme..., system_overlay_style: SystemOverlayStyle, visual_density, page_transitions, scaffold_bgcolor)` (`theme.py:3304-3640`); `ThemeSurfaces.NEUTRAL|TONAL` (`theme.py:3280-3301`, new in 1.1.0 — CHANGELOG.md); `ColorScheme` with the full M3 role set incl. `surface_container_*`, `outline`, `outline_variant` (`theme.py:145-425`); `TextTheme.body_*/title_*/label_*/headline_*/display_*` (`theme.py:429-520`).

**GAP**: there is no "high contrast" `ThemeMode`; Flet exposes exactly two theme slots (light/dark). So high contrast is implemented as *alternative `Theme` objects* placed into the same two slots, and the user's choice drives which pair is installed and which `ThemeMode` is forced:

| `ThemeChoice` | `page.theme` | `page.dark_theme` | `page.theme_mode` |
|---|---|---|---|
| `SYSTEM` | `build_light()` | `build_dark()` | `SYSTEM` |
| `LIGHT` | `build_light()` | `build_dark()` | `LIGHT` |
| `DARK` | `build_light()` | `build_dark()` | `DARK` |
| `HC_LIGHT` | `build_hc_light()` | `build_hc_dark()` | `LIGHT` |
| `HC_DARK` | `build_hc_light()` | `build_hc_dark()` | `DARK` |

```python
# src/pycon_us/theme/themes.py
import flet as ft
SEED = "#1565C0"

def build_light() -> ft.Theme:
    return ft.Theme(color_scheme_seed=SEED, surfaces=ft.ThemeSurfaces.NEUTRAL, use_material3=True,
                    font_family="Inter")

def build_dark() -> ft.Theme:
    return ft.Theme(color_scheme_seed=SEED, surfaces=ft.ThemeSurfaces.NEUTRAL, use_material3=True)

def _hc_text() -> ft.TextTheme:
    bold = ft.TextStyle(weight=ft.FontWeight.W_600)
    return ft.TextTheme(body_medium=bold, body_large=bold, label_large=bold, title_medium=bold)

def build_hc_light() -> ft.Theme:
    return ft.Theme(
        use_material3=True,
        color_scheme=ft.ColorScheme(                      # explicit roles win over seed/surfaces (cookbook/theming.md:41,116)
            primary="#0000A0", on_primary="#FFFFFF", primary_container="#0000A0", on_primary_container="#FFFFFF",
            surface="#FFFFFF", on_surface="#000000", surface_container="#FFFFFF", surface_container_high="#F2F2F2",
            on_surface_variant="#000000", outline="#000000", outline_variant="#000000",
            error="#B00020", on_error="#FFFFFF", secondary="#004D40", on_secondary="#FFFFFF",
        ),
        text_theme=_hc_text(),
        scaffold_bgcolor="#FFFFFF",
    )

def build_hc_dark() -> ft.Theme:
    return ft.Theme(
        use_material3=True,
        color_scheme=ft.ColorScheme(
            primary="#FFFF00", on_primary="#000000", primary_container="#FFFF00", on_primary_container="#000000",
            surface="#000000", on_surface="#FFFFFF", surface_container="#000000", surface_container_high="#1A1A1A",
            on_surface_variant="#FFFFFF", outline="#FFFFFF", outline_variant="#FFFFFF",
            error="#FF6E6E", on_error="#000000", secondary="#00FFFF", on_secondary="#000000",
        ),
        text_theme=_hc_text(),
        scaffold_bgcolor="#000000",
    )
```

```python
# src/pycon_us/theme/apply.py
import flet as ft
from pycon_us.models.prefs import ThemeChoice
from pycon_us.theme import themes

def apply_theme(page: ft.Page, choice: ThemeChoice):
    hc = choice in (ThemeChoice.HC_LIGHT, ThemeChoice.HC_DARK)
    page.theme = themes.build_hc_light() if hc else themes.build_light()
    page.dark_theme = themes.build_hc_dark() if hc else themes.build_dark()
    page.theme_mode = {
        ThemeChoice.SYSTEM: ft.ThemeMode.SYSTEM,
        ThemeChoice.LIGHT: ft.ThemeMode.LIGHT, ThemeChoice.HC_LIGHT: ft.ThemeMode.LIGHT,
        ThemeChoice.DARK: ft.ThemeMode.DARK, ThemeChoice.HC_DARK: ft.ThemeMode.DARK,
    }[choice]
    # In components mode, page attribute assignment schedules a batched page update:
    # Page.render()/render_views() set self._notify = self.__notify → schedule_update() (page.py:767-772, 835-843)
```

Persistence: `PrefsService` stores `"theme"` as the enum value string via `ft.SharedPreferences().set("theme", value)` / `.get("theme")` (`SDK/controls/services/shared_preferences.py`: `set/get/contains_key/remove/get_keys/clear`, values limited to `str|int|float|bool|list[str]`). Legacy Ionic keys (`darkTheme: true`, `theme: 'high-contrast'`) are migrated in `load_into()` exactly like `user-data.ts:91-113`. Status bar colours per theme: `Theme.system_overlay_style = ft.SystemOverlayStyle(status_bar_color=..., status_bar_icon_brightness=ft.Brightness.LIGHT|DARK)` (`theme.py:692-740`) replaces Capacitor `StatusBar`.

Track/slot colours (`slotColors` in `conference-data.ts`) become a small `tokens.py` mapping to `ft.Colors.PRIMARY_CONTAINER`, `TERTIARY_CONTAINER`, `SURFACE_CONTAINER_HIGH` etc. so they follow all four schemes automatically.

---

## 5. Dialogs, toasts, action sheets, bottom sheets (declarative)

Verified: `ft.use_dialog(dialog: DialogControl | None)` — call on every render; non-`None` shows (sets `open=True`, appends to `page._dialogs`), `None` hides; same-type re-render patches the open dialog in place preserving TextField focus; unmount closes it (`SDK/components/hooks/use_dialog.py:52-181`). `DialogControl(open, on_dismiss)` subclasses: `AlertDialog`, `BottomSheet`, `SnackBar`, `Banner`, `CupertinoBottomSheet`, `DatePicker`, `TimePicker` (`SDK/controls/dialog_control.py`, `material/*.py`, `cupertino/cupertino_bottom_sheet.py`). `CupertinoActionSheet(title, message, actions, cancel)` is a layout control hosted inside `CupertinoBottomSheet(content=...)` (`cupertino/cupertino_action_sheet.py:13-71`). Imperative `page.show_dialog(dialog)` / `page.pop_dialog()` still exist (`base_page.py:402-445`) and are the right tool for fire-and-forget toasts raised from services.

| Ionic | Flet |
|---|---|
| `AlertController` | `use_dialog(ft.AlertDialog(modal=True, title, content, actions, on_dismiss))` |
| `ToastController` (top toasts) | `ft.SnackBar(content, behavior=ft.SnackBarBehavior.FLOATING, duration, show_close_icon, action)` (`material/snack_bar.py:155-321`) via a `use_toast()` hook (below) or `page.show_dialog(ft.SnackBar(...))` from services |
| `LoadingController` | `use_dialog(ft.AlertDialog(modal=True, content=ft.ProgressRing()))` or inline `ft.ProgressRing` |
| `ion-modal` with breakpoints (Staff Tools) | `use_dialog(ft.BottomSheet(content, show_drag_handle=True, draggable=True, scrollable=True))` (`material/bottom_sheet.py:16-134`) |
| `ModalController` full pages (filter, lead-note, floor-plan, redemption) | Router `modal=True` route + `View(fullscreen_dialog=True)` (§2) |
| iOS action sheet | `use_dialog(ft.CupertinoBottomSheet(content=ft.CupertinoActionSheet(actions=[ft.CupertinoActionSheetAction(...)])))` |
| update banner | `use_dialog(ft.Banner(content, actions, leading))` (`material/banner.py:22-151`) |

```python
# src/pycon_us/components/toast.py
import flet as ft

def use_toast():
    """Returns show(message, icon=None). Toasts are queued one at a time via state."""
    toast, set_toast = ft.use_state(None)
    ft.use_dialog(
        ft.SnackBar(
            content=ft.Row([ft.Icon(toast["icon"]) if toast.get("icon") else ft.Container(), ft.Text(toast["text"])]),
            behavior=ft.SnackBarBehavior.FLOATING, show_close_icon=True,
            duration=ft.Duration(milliseconds=toast.get("ms", 3000)),
            on_dismiss=lambda: set_toast(None),          # fires after close animation (cookbook/declarative-dialogs.md)
        ) if toast else None
    )
    return lambda text, icon=None, ms=3000: set_toast({"text": text, "icon": icon, "ms": ms})
```

```python
# Staff Tools sheet (Ionic ion-modal with breakpoints) in TabsShell
show_tools, set_show_tools = ft.use_state(False)
ft.use_dialog(
    ft.BottomSheet(
        show_drag_handle=True, scrollable=True, on_dismiss=lambda: set_show_tools(False),
        content=ft.Column(tight=True, controls=[
            ft.Text("Staff Tools", size=20, weight=ft.FontWeight.BOLD),
            *[ft.ListTile(leading=ft.Icon(icon), title=ft.Text(label), trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
                          on_click=lambda e, u=url: (set_show_tools(False), page.navigate(u)))
              for icon, label, url in staff_tools(store.auth.features)],
        ]),
    ) if show_tools else None
)
```

Pitfall: `use_dialog` is a hook — it must be called unconditionally (pass `None` to hide), never inside an `if`.

---

## 6. Async & networking

- Flet apps run on one asyncio loop per session (`page.loop`, `page.py:1343`); event handlers and `use_effect` setups may be `async def` — the scheduler wraps coroutine setups/cleanups in `asyncio.create_task` (`SDK/messaging/session.py:734-743`). Use `page.run_task(coro_fn, *args)` to start work from sync code and `page.run_thread(fn, *args)` for blocking CPU/IO in the executor (`page.py:930-1011`).
- `httpx >= 0.28.1` is already a dependency of `flet` on non-Emscripten platforms (`sdk/python/packages/flet/pyproject.toml:13`), so `httpx.AsyncClient` is the natural client; on Pyodide (`page.pyodide`, `page.py:564`) httpx is unavailable — keep the HTTP layer behind a tiny Protocol so a `pyfetch` implementation can be swapped in for the web build.
- Timeouts mirror Ionic: 2 s for signed user endpoints, 3 s login, 10 s feed (`httpx.Timeout`).
- Offline cache: JSON file under `await ft.StoragePaths().get_application_cache_directory()` (`SDK/controls/services/storage_paths.py:20`), documents dir for user data (`:41`). Small prefs → `ft.SharedPreferences`; secrets (`key`, `secret`) → `flet_secure_storage.SecureStorage.set/get/remove` (`EXT/flet-secure-storage/src/flet_secure_storage/secure_storage.py:81-260`).
- Connectivity: `ft.Connectivity().get_connectivity()` + `on_change` (`services/connectivity.py:58-74`) replaces `@capacitor/network`.
- Foreground/background re-fetch: `page.on_app_lifecycle_state_change` with `AppLifecycleState.RESUME` (`page.py:630`, `types.py:1106-1130`).

```python
# src/pycon_us/services/api_client.py
import hashlib, json, time
import httpx
from pycon_us.config import BASE_URL, YEAR

class PyConAPI:
    def __init__(self, secrets):                      # secrets: SecureStorage wrapper with async get(key)
        self._client = httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(2.0))
        self._secrets = secrets

    async def _auth_headers(self, method: str, url: str, body: str) -> dict[str, str]:
        api_key = await self._secrets.get("key") or ""
        secret = await self._secrets.get("secret") or ""
        ts = str(int(round(time.time())))
        base = f"{secret}{ts}{method}{url}{body}"                     # same concatenation as pycon-api.ts:28-35
        return {"X-API-Key": api_key,
                "X-API-Signature": hashlib.sha1(base.encode()).hexdigest(),
                "X-API-Timestamp": ts}

    async def _signed(self, method: str, path: str, payload=None, timeout: float | None = None):
        body = json.dumps(payload) if payload is not None else ""
        headers = await self._auth_headers(method, path, body)
        if payload is not None:
            headers["Content-Type"] = "application/json"
        r = await self._client.request(method, path, content=body or None, headers=headers,
                                       timeout=timeout or 2.0)
        r.raise_for_status()
        return r.json() if r.content else None

    async def authenticate(self, email: str, password: str) -> dict:
        r = await self._client.post(f"/{YEAR}/api/v1/authenticate/", json={"email": email, "password": password}, timeout=3.0)
        r.raise_for_status(); return r.json()
    async def fetch_features(self):          return await self._signed("GET", f"/{YEAR}/api/v1/user/check_features/")
    async def fetch_preferences(self):       return await self._signed("GET", f"/{YEAR}/api/v1/user/mobile_state/")
    async def patch_user_data(self, payload): return await self._signed("PATCH", f"/{YEAR}/api/v1/user/mobile_state/", payload)
    async def fetch_conference_json(self) -> dict:
        r = await self._client.get(f"/{YEAR}/schedule/conference.json", timeout=10.0); r.raise_for_status(); return r.json()
```

```python
# src/pycon_us/services/feed_loader.py
import httpx
from pycon_us.models.feed import parse_feed
from pycon_us.state.store import AppStore

class FeedService:
    CACHE = "schedule-cache.json"
    def __init__(self, api, cache, toast):           # cache: FileCache(StoragePaths); toast: callable(str)
        self.api, self.cache, self.toast = api, cache, toast

    async def load(self, store: AppStore, force: bool = False):
        if store.feed and not force:
            return
        store.loading = True
        cached = await self.cache.read_json(self.CACHE)
        if cached and not store.feed:
            store.feed = parse_feed(cached); store.feed_version += 1      # instant render from cache
        try:
            fresh = await self.api.fetch_conference_json()
            await self.cache.write_json(self.CACHE, fresh)
            store.feed = parse_feed(fresh); store.feed_version += 1; store.error = None
        except (httpx.HTTPError, ValueError) as e:
            store.error = str(e)
            if not store.feed:
                self.toast("Unable to load schedule, no offline cache available")
        finally:
            store.loading = False
```

Pull-to-refresh (`ion-refresher`): **GAP** — no `RefreshIndicator` control in `SDK/controls` (grep). Use an AppBar refresh `IconButton` calling `services.feed.load(store, force=True)` and a `ft.ProgressBar` while `store.loading`.

Screens consume it declaratively:

```python
@ft.component
def Schedule():
    store = ft.use_context(StoreContext)
    day, set_day = ft.use_state(0)
    query, set_query = ft.use_state("")
    sessions = ft.use_memo(lambda: select_sessions(store.feed, day, query, store.prefs.filters),
                           [store.feed_version, day, query, store.prefs.filters.version])
    ...
```

---

## 7. Testing strategy

Verified pieces:

- `flet test` CLI (`EXT/flet-cli/src/flet_cli/commands/test.py`) and the `pytest11` plugin `SDK/pytest_plugin.py` provide fixtures `flet_app` and `flet_app_function` (`:112-140`). Device mode is the default (`FLET_TEST_DEVICE_MODE`, `:28-38`); host mode runs `main` in-process, resolved from `FLET_TEST_APP_PATH`/`FLET_TEST_APP_MODULE` or from `request.param["flet_app_main"]` (`:83-110`).
- `FletTestApp(flutter_app_dir, flet_app_main, assets_dir, test_path, ..., device_mode)` (`SDK/testing/flet_test_app.py:141-189`); `.page`, `.tester`, `.assert_screenshot(name, png_bytes, similarity_threshold)`, `.assert_control_screenshot(name, control, bgcolor=...)`, `.take_page_controls_screenshot()`, `.create_gif/assert_gif` (`:468-1030`). Golden path: `tests/golden/<FLET_TEST_PLATFORM>/<test_module_without_test_>/<name>.png` (`:634-640`); `FLET_TEST_GOLDEN=1` records, `FLET_TEST_GOLDEN=failed` rewrites only mismatches (CHANGELOG 1.1.0; `integration_tests/README.md`).
- `Tester`/`RemoteTester`: `pump()`, `pump_and_settle()`, `find_by_text/_containing/_key/_tooltip/_icon/_semantics_identifier`, `tap`, `long_press`, `enter_text`, `drag`, `mouse_hover`, `take_screenshot(name)` (`SDK/testing/tester.py:15-271`, `remote_tester.py`). `Finder.first/last/at/count` (`testing/finder.py`).
- App-level example: `sdk/python/examples/apps/flet_test_counter/tests/test_main.py` with `pyproject.toml` `[tool.pytest.ini_options] asyncio_mode="auto"`, dev deps `flet[test]`, `flet-cli`, `flet-desktop`.

Layers:

1. **Pure unit tests (no Flet runtime)** — `tests/unit/`: `hashlib`-signature of `PyConAPI._auth_headers` against a fixed `time.time` and a recorded Ionic request; `parse_feed()` against a checked-in `conference.json` fixture (placeholder-slot filtering, poster speakers registration, room slugs — the rules in `conference-data.ts:60-80, 180-230`); `AppStore`/`AuthState` logic with `Observable.subscribe()` to assert notifications (`observable.py:148`). Observables are plain Python objects, so these run with plain pytest.
2. **UI tests with the Flet plugin** — `tests/ui/`: give interactive controls `key=` values (`BaseControl.key`; `flet_test_counter` uses `find_by_key("increment")`). Inject a fake `FeedService`/`PyConAPI` by parametrizing `flet_app` with a `flet_app_main` that renders `App` with a `services_override`.

```python
# tests/ui/test_navigation.py
import pytest, flet as ft, flet.testing as ftt
from pycon_us.app import App
from tests.ui.fakes import fake_services

def app_main(page: ft.Page):
    page.render_views(lambda: App(services_override=fake_services()))

@pytest.mark.parametrize("flet_app", [{"flet_app_main": app_main}], indirect=True)
async def test_session_detail_and_back(flet_app: ftt.FletTestApp):
    t = flet_app.tester
    await flet_app.page.push_route("/app/tabs/schedule")
    await t.pump_and_settle()
    await t.tap(await t.find_by_key("session-42"))
    await t.pump_and_settle()
    assert flet_app.page.route == "/app/tabs/schedule/session/42"
    assert (await t.find_by_text("Keynote: ...")).count == 1
    await t.tap(await t.find_by_tooltip("Back"))
    await t.pump_and_settle()
    assert flet_app.page.route == "/app/tabs/schedule"

@pytest.mark.parametrize("flet_app", [{"flet_app_main": app_main}], indirect=True)
async def test_schedule_golden(flet_app: ftt.FletTestApp, request):
    flet_app.page.theme_mode = ft.ThemeMode.LIGHT
    await flet_app.page.push_route("/app/tabs/schedule")
    await flet_app.tester.pump_and_settle()
    flet_app.assert_screenshot(request.node.name, await flet_app.tester.take_screenshot(request.node.name))
```

3. **Golden matrix**: one screenshot test per screen × 4 theme choices (call `apply_theme(flet_app.page, choice)` before capture) run on `macos` in CI and on an iOS simulator / Android emulator via `FLET_TEST_DEVICE`/`FLET_TEST_PLATFORM` before releases. Host-mode (`FLET_TEST_DEVICE_MODE=0`) is faster for routing tests; device mode (`flet test`) validates the packaged app and extensions.

---

## 8. Pitfalls specific to Flet 1.x components mode

1. **Hooks are positional** (`Component.use_hook`, `component.py:290`; state migration is skipped when the function differs, `:103-115`). Never call `use_*`, `use_dialog`, `is_route_active`, `use_route_*` conditionally or in loops of varying length. Read `use_route_location()` once and compare strings (the comment in `examples/apps/router/app_drawer/main.py:104-110` is explicit about this).
2. **Every route component under `manage_views=True` must return a `View`**; outlet layouts must use `route=ft.use_view_path()` or a deliberate fixed key (`cookbook/router.md` "Shared layouts with outlet=True"/"Avoiding transition animation").
3. **Component-less grouping routes do not create Views** (`router.py:525-526`); to get a back stack the list page must be the *parent route component*.
4. **`loader` is synchronous and re-runs on every Router render** (`router.py:802-805`) — do not do network I/O in loaders; use the store.
5. **Observable limits**: `_private` attributes do not notify (`observable.py:233`); `set`/`tuple` fields are not wrapped (only `list`/`dict`, `:245-250`); mutating a nested *non-observable* dataclass does not notify (replace it or make it observable); assigning an equal value is a no-op (`value_equal`); re-assigning a list wraps it to `ObservableList` (keep the reference you mutate).
6. **`use_state` setter compares with `!=`** (`use_state.py:109`): a `@dataclass` with eq and identical fields will not re-render; bump a version or pass a new object.
7. **Do not keep controls in state** (`.agents/skills/imperative-to-declarative-flet/SKILL.md`); store ids/enums and build controls in render. If you must touch a control (e.g. `ListView.scroll_to`), use `use_ref` and call its async methods from handlers.
8. **Event handler typing is invariant**: annotate `e: ft.Event[ft.NavigationBar]`, or take no argument (SKILL.md).
9. **`page.navigate()` is sync (creates a task); `page.push_route()` must be awaited** (`page.py:1094-1106`).
10. **Router owns `page.on_route_change` and `page.on_view_pop` after mount** (`router.py:660-720`); custom pop logic must be installed *before* `render_views`.
11. **Async `use_effect` setups run as tasks** (`session.py:734`): exceptions do not propagate to the test; wrap bodies in try/except and surface errors through the store/toast. Provide `cleanup` to cancel long tasks on unmount.
12. **`use_dialog` is per-component**: a dialog opened by a screen is closed when that screen unmounts (`use_dialog.py:174-181`) — global toasts from services should use `page.show_dialog(ft.SnackBar(...))`.
13. **Services auto-register only when constructed inside a page context** (`services/service.py:44-54`): create `ft.SharedPreferences()`, `ft.StoragePaths()`, `ft.HapticFeedback()`, `ft.UrlLauncher()`, `SecureStorage()` in `App` (`use_memo(..., [])`) or `main`, not at import time.
14. **`SharedPreferences` values are `str|int|float|bool|list[str]` only** (`shared_preferences.py:14-40`) — JSON-encode dicts (`notification_prefs`, `scheduleFilters`).
15. **Tabs/NavigationBar echo**: `Tabs.on_change` fires after programmatic `selected_index` changes (`app_drawer/main.py:120-128`); compare with current state before navigating.
16. **`flet run` sets `FLET_ASSETS_DIR`** and overrides `assets_dir=` (SKILL.md; `app.py:728-730`).
17. **Theme changes animate by default** — set `page.theme_animation_style = ft.AnimationStyle.no_animation()` if golden tests flake (`base_page.py:186-194`).
18. **Memoise expensive subtrees** with `ft.memo(Component)` (shallow arg compare, `components/memo.py`) — e.g. `SessionTile(session, favorite: bool)` so a favourites change re-renders only affected tiles; pass primitives, not the whole store.

---

## 9. Capability map (Ionic/Capacitor → Flet)

| Ionic / Capacitor | Flet equivalent (verified path) | Status |
|---|---|---|
| Angular Router (nested, lazy, params, redirects, guards) | `ft.Router`/`ft.Route` nested tree, `use_route_params`, redirect components, layout guards (`SDK/components/router.py`) | exists |
| `ion-tabs` + `ion-tab-bar` | `View.navigation_bar=ft.NavigationBar(...)` inside an `outlet=True` layout | exists |
| `ion-menu` / `ion-split-pane` | `View.drawer=ft.NavigationDrawer(controls=[...])`, `page.show_drawer()`; split-pane on wide screens = `ft.NavigationRail` + `use_route_outlet` (`material/navigation_rail.py`) | exists |
| `ion-back-button`, swipe back, hardware back | `manage_views=True` stack; `AppBar.automatically_imply_leading`; Router default `on_view_pop` | exists |
| `ion-modal` (full page) | `Route(modal=True)` + `View(fullscreen_dialog=True)` | exists |
| `ion-modal` with breakpoints / action sheet | `ft.BottomSheet(draggable, show_drag_handle)`, `ft.CupertinoBottomSheet(content=ft.CupertinoActionSheet)` via `use_dialog` | exists |
| Alert / Toast / Loading | `ft.AlertDialog`, `ft.SnackBar`, `ft.ProgressRing` via `use_dialog` / `page.show_dialog` | exists |
| `ion-refresher` | **no RefreshIndicator control** → refresh button + `ProgressBar` | gap |
| `ion-searchbar` | `ft.SearchBar` (`material/search_bar.py`) or `ft.TextField(prefix_icon=SEARCH)` | exists |
| `ion-segment` (days) | `ft.SegmentedButton` (`material/segmented_button.py`) / `ft.Tabs(content=ft.TabBar)` | exists |
| `ion-accordion` | `ft.ExpansionTile` | exists |
| `ion-item-sliding` / swipe actions | `ft.Dismissible` (`core/dismissible.py`) | exists |
| Markdown rendering (`markdown-to-txt`) | `ft.Markdown` (`core/markdown.py:928`) | exists |
| Ionic Storage (`@ionic/storage-angular`) | `ft.SharedPreferences` (scalars/str lists) + JSON files via `ft.StoragePaths`; **`page.client_storage` does not exist in 1.x** | partial |
| Secrets (`key`, `secret`) | `flet_secure_storage.SecureStorage` (`EXT/flet-secure-storage`) | exists |
| Theme classes light/dark/HC-light/HC-dark | `page.theme/dark_theme/theme_mode` + custom `ft.Theme(color_scheme=ft.ColorScheme(...), text_theme=...)`; HC handled by swapping theme objects | partial |
| `@capacitor/status-bar` | `Theme.system_overlay_style=ft.SystemOverlayStyle(...)` | exists |
| `@capacitor/splash-screen` | `flet-platform-assets` generates splash; auto-hide at first frame (no manual hide API needed) | partial |
| `@capacitor/network` | `ft.Connectivity` | exists |
| `@capacitor/haptics` | `ft.HapticFeedback.light_impact/medium_impact/heavy_impact/selection_click/vibrate` (`services/haptic_feedback.py`) | exists |
| `@capacitor/share` (+Filesystem for ICS) | `ft.Share.share_text/share_uri/share_files` (`services/share.py:162-235`) | exists |
| `@capacitor/inappbrowser` | `ft.UrlLauncher.launch_url(url, mode=ft.LaunchMode.IN_APP_BROWSER_VIEW)`; gesture-safe web links via `action=ft.OpenUrl(...)` (`services/url_launcher.py`); embedded pages via `flet-webview` | exists |
| `@capacitor/device` | `await page.get_device_info()` (`page.py:1370-1393`), `page.platform.is_mobile()/is_apple()` (`types.py:835-850`) | exists |
| `@capacitor/app` (lifecycle, back) | `page.on_app_lifecycle_state_change`, `View.can_pop/on_confirm_pop` | exists |
| `@capacitor/keyboard` | `page.media.view_insets` (`base_page.py:82`), `BottomSheet.maintain_bottom_view_insets_padding` | partial |
| `@capacitor-mlkit/barcode-scanning` (QR lead scanner, door check) | `flet-camera` gives frames (`Camera.start_image_stream`, `EXT/flet-camera/src/flet_camera/camera.py:177`) but **no decoder**; options: new `flet-barcode` extension (mobile_scanner) or Python `zxing-cpp`/`pyzbar` on frames | gap |
| `@capacitor/local-notifications` | **none** → `Notifications` Protocol + no-op; candidate extension around `flutter_local_notifications` | gap |
| `@capacitor-firebase/messaging` + `analytics` | **none** → extension needed (`firebase_messaging`); `flet-permission-handler` has `Permission.NOTIFICATION` for the prompt only | gap |
| `@capacitor/live-updates` (Appflow) | **none**; Flet ships Python inside the app bundle, no OTA | gap |
| `@ebarooni/capacitor-calendar` | **none** → generate `.ics` and `Share.share_files`, or `launch_url("webcal://…")` | gap |
| Camera/notification permissions | `flet_permission_handler.PermissionHandler.request(Permission.CAMERA)` (`EXT/flet-permission-handler/...:56`) | exists |
| Tutorial swiper (`ion-slides`) | `ft.PageView` (`core/page_view.py:21`) | exists |
| Pinch-zoom floor plan (`ngx-pinch-zoom`) | `ft.InteractiveViewer` (`core/interactive_viewer.py`) | exists |
| Service worker / PWA | `flet build web` (`--pwa-short-name`, CHANGELOG 1.0.4); `page.pwa` | exists |
| Deep links / universal links into the app | Router handles any `page.route`, but no Flet API to register app links | gap |
| Unit/E2E tests (Karma/Protractor) | pure pytest for services/stores + `flet test` plugin with golden screenshots | exists |
