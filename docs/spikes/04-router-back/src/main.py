"""S4 reproducer: the Router, the recursive drill route and native Back.

Spike S4 (docs/spikes/04-router-back.md). The shell the decisions prescribe, with
stub screens: `page.on_view_pop` set before `page.render_views(App, memory)`
(D-19), a boot gate (D-69), `ft.Router(ROUTES, manage_views=True)` with five
tab roots, a More page, the recursive drill (`session`, `speaker`, `room`)
under every root, page and the global modal `/search`, and D-17's Back rule:
non-Now roots set `can_pop=False` and an `on_confirm_pop` that goes to Now.

Every step prints a line starting with `S4 ` (logcat tag `flet.python` on
Android, sender `dart_bridge` on iOS). With `S4_JOURNEY=1` in the
environment (`SIMCTL_CHILD_S4_JOURNEY=1` for `simctl launch`), or from More,
the app walks the journeys itself and checks each step.
"""

import asyncio
import os
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlparse

import flet as ft
from routes import TABS, drill_href, parent_of, stack_depth, tab_of

T0 = time.perf_counter()
# Module state survives a new session in the same process (F26); the spike counts
# sessions with it and keeps the knobs More toggles.
SESSIONS_STARTED = [0]
KNOBS = {
    "shared_root_key": True,
    "bar_on_pushed": True,
    "memory_per_process": False,
    "stop_on_close": False,
}
LEVELS: dict[str, tuple[str, str]] = {}  # view path -> (kind, ident) as rendered


def log(event: str, **values: object) -> None:
    """Print one `S4` line with the session number and seconds since start."""
    fields = " ".join(f"{key}={value}" for key, value in values.items())
    stamp = f"s={SESSIONS_STARTED[0]} t={time.perf_counter() - T0:.3f}"
    print(f"S4 {event} {stamp} {fields}", flush=True)


# ------------------------------------------------------------------ stub data
# Ids with ':', '+', ' ', '~' and non-ASCII check that per-level params survive
# URL quoting and the round trip through Flutter's route information.
SESSIONS = {
    "42": ("Keynote: Python everywhere", ("17", "23"), "hall-a"),
    "99": ("Typing in practice", ("17",), "room-102a"),
    "7": ("Async all the way down", ("23", "ç~31"), "room-102a"),
    "break--2026-05-13T12:30:00-07:00": ("Lunch", (), "hall-a"),
    "poster detail+1": ("Poster: a b+c", ("ç~31",), "expo-hall"),
}
SPEAKERS = {"17": "Ada Lovelace", "23": "Guido van Rossum", "ç~31": "Grace Hopper"}
ROOMS = {"hall-a": "Hall A", "room-102a": "Room 102A", "expo-hall": "Expo hall"}


def find_session(sid: str) -> tuple[str, tuple[str, ...], str] | None:
    """A stub session: one of SESSIONS, or a generated Schedule row `d<day>-<n>`."""
    if sid in SESSIONS:
        return SESSIONS[sid]
    if len(sid) > 3 and sid[0] == "d" and sid[1] in "123" and sid[2] == "-":
        return f"Day {sid[1]} talk {sid[3:]}", ("17",), "room-102a"
    return None


# ------------------------------------------------------------------ state
@dataclass
class ViewMemory:
    """Where the user left each screen (D-18): plain, so writing re-renders nothing."""

    schedule_day: int = 1
    schedule_offsets: dict[int, float] = field(default_factory=dict)
    search_query: str = ""
    search_scope: str = "all"
    search_base: str = "/now"
    last_location: str = ""


@ft.observable
@dataclass
class Device:
    """What the page handlers report; the boot gate opens on `loaded`."""

    loaded: bool = False
    dark: bool = False
    brightness_events: int = 0
    lifecycle: str = "-"
    lifecycle_events: int = 0
    session: int = 0
    ticks: int = 0


MemoryCtx = ft.create_context(ViewMemory())
DeviceCtx = ft.create_context(Device())
_PROCESS_MEMORY = ViewMemory()


# ------------------------------------------------------------------ shell
def nav_bar(tab: int, on_change) -> ft.NavigationBar:
    """The five fixed destinations (D-13): on tab roots, on pushed Views if the knob says so."""
    icons = (
        (ft.Icons.SENSORS_OUTLINED, ft.Icons.SENSORS, "Now"),
        (ft.Icons.CALENDAR_MONTH_OUTLINED, ft.Icons.CALENDAR_MONTH, "Schedule"),
        (ft.Icons.STAR_BORDER, ft.Icons.STAR, "My schedule"),
        (ft.Icons.MAP_OUTLINED, ft.Icons.MAP, "Map"),
        (ft.Icons.MORE_HORIZ, ft.Icons.MORE_HORIZ, "More"),
    )
    return ft.NavigationBar(
        selected_index=tab,
        label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
        destinations=[
            ft.NavigationBarDestination(icon=i, selected_icon=s, label=label)
            for i, s, label in icons
        ],
        on_change=on_change,
    )


@ft.component
def StatusLine() -> ft.Control:
    """What the page handlers last reported, re-rendered without page.update()."""
    device = ft.use_context(DeviceCtx)
    return ft.Text(
        f"Session {device.session} · ticks {device.ticks} · "
        f"{'dark' if device.dark else 'light'} "
        f"({device.brightness_events} brightness events) · lifecycle "
        f"{device.lifecycle} ({device.lifecycle_events})",
        theme_style=ft.TextThemeStyle.LABEL_SMALL,
    )


def scaffold(
    *,
    view_path: str,
    title: str,
    controls: list[ft.Control],
    actions: list[ft.Control] | None = None,
    back_to: str | None = None,
    on_retap=None,
) -> ft.View:
    """A View with the app bar, its tab's bar and the Back rules (D-10, D-17).

    A plain builder called unconditionally from each screen, so its hooks are safe.
    """
    page = ft.context.page
    memory = ft.use_context(MemoryCtx)
    location = ft.use_route_location()
    tab = tab_of(view_path)
    is_root = view_path in TABS
    intercept_back = is_root and view_path != "/now"
    if view_path == location:  # the top View of this render pass
        memory.last_location = page.route
        log("top", view=view_path, route=page.route)

    def on_tab(e: ft.Event[ft.NavigationBar]) -> None:
        target = TABS[e.control.selected_index or 0]
        retap = tab == e.control.selected_index
        log("tab", view=view_path, to=target, retap=retap)
        if retap and is_root and on_retap is not None:
            page.run_task(on_retap)  # a root's re-tap: its screen scrolls to the top
        else:
            page.navigate(target)  # from a pushed View: back to its root (D-17)

    def go_back() -> None:
        target = back_to or parent_of(view_path, memory.search_base)
        log("back-arrow", view=view_path, to=target)
        page.navigate(target)

    async def back_to_now(e: ft.Event[ft.View]) -> None:
        log("confirm-pop", view=view_path, to="/now")
        page.navigate("/now")
        await e.control.confirm_pop(False)

    shared = is_root and KNOBS["shared_root_key"]
    return ft.View(
        route="/" if shared else view_path,  # a shared key: tab switches don't animate
        padding=0,
        appbar=ft.AppBar(
            title=ft.Text(title),
            center_title=False,
            automatically_imply_leading=False,
            leading=None
            if is_root
            else ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Back", on_click=go_back),
            actions=actions or [],
        ),
        navigation_bar=nav_bar(tab, on_tab)
        if tab is not None and (is_root or KNOBS["bar_on_pushed"])
        else None,
        can_pop=not intercept_back,
        on_confirm_pop=back_to_now if intercept_back else None,
        controls=[
            ft.SafeArea(
                expand=True,
                content=ft.Column([StatusLine(), *controls], expand=True),
            )
        ],
    )


def search_action(view_path: str, scope: str) -> ft.IconButton:
    """The Search button: remember the opener (query included), then open /search."""
    page = ft.context.page
    memory = ft.use_context(MemoryCtx)

    def open_search() -> None:
        memory.search_base = page.route
        log("open-search", base=page.route, scope=scope)
        page.navigate(f"/search?scope={scope}")

    return ft.IconButton(ft.Icons.SEARCH, tooltip="Search", on_click=open_search)


def link(view_path: str, kind: str, ident: str, label: str) -> ft.ListTile:
    """A row that pushes one drill level (kind, ident) on top of view_path."""
    page = ft.context.page
    href = drill_href(view_path, kind, ident)

    def push() -> None:
        log("push", to=href)
        page.navigate(href)

    return ft.ListTile(
        title=ft.Text(label), subtitle=ft.Text(f"{kind} {ident}"), on_click=push
    )


# ------------------------------------------------------------------ screens
@ft.component
def Start() -> ft.View:
    """`/`: go to Now, or (per-process memory) back to where the user was."""
    page = ft.context.page
    memory = ft.use_context(MemoryCtx)

    async def go() -> None:
        target = memory.last_location if KNOBS["memory_per_process"] else ""
        if urlparse(target).path.split("/")[1:2] == ["search"]:
            target = memory.search_base  # a modal can't be rebuilt over `/`: its opener
        log("start", route=page.route, to=target or "/now")
        page.navigate(target or "/now")

    ft.use_effect(go, [])
    return ft.View(route="/", controls=[ft.ProgressRing()])


@ft.component
def Now() -> ft.View:
    """The Now root: a few sessions, one with a ':' in its id."""
    view_path = ft.use_view_path()
    rows = [
        link(view_path, "session", sid, SESSIONS[sid][0])
        for sid in ("42", "break--2026-05-13T12:30:00-07:00", "poster detail+1")
    ]
    return scaffold(
        view_path=view_path,
        title="Now",
        actions=[search_action(view_path, "all")],
        controls=[ft.ListView(rows, expand=True)],
    )


@ft.component
def Schedule() -> ft.View:
    """Three days of 40 rows; the day and each day's offset live in ViewMemory."""
    view_path = ft.use_view_path()
    memory = ft.use_context(MemoryCtx)
    day, set_day = ft.use_state(memory.schedule_day)
    list_ref = ft.use_ref(ft.Ref)
    renders = ft.use_ref(0)
    renders.current += 1

    async def restore() -> None:
        offset = memory.schedule_offsets.get(day, 0.0)
        if offset and list_ref.current.current is not None:
            await list_ref.current.current.scroll_to(offset=offset, duration=0)
        log("schedule-restore", day=day, offset=round(offset), renders=renders.current)

    ft.use_effect(restore, [day])

    async def scroll_to_top() -> None:
        if list_ref.current.current is not None:
            await list_ref.current.current.scroll_to(offset=0, duration=300)
        log("retap-scroll", day=day)

    def remember_offset(e: ft.OnScrollEvent) -> None:
        memory.schedule_offsets[day] = e.pixels  # no re-render (D-18)

    def pick_day(e: ft.Event[ft.SegmentedButton]) -> None:
        memory.schedule_day = int(next(iter(e.control.selected)))
        set_day(memory.schedule_day)

    rows = [
        link(view_path, "session", f"d{day}-{n:02}", f"Day {day} talk {n:02}")
        for n in range(1, 41)
    ]
    days = ft.SegmentedButton(
        segments=[
            ft.Segment(value=str(d), label=ft.Text(f"Day {d}")) for d in (1, 2, 3)
        ],
        selected=[str(day)],
        on_change=pick_day,
    )
    listing = ft.ListView(
        rows,
        expand=True,
        ref=list_ref.current,
        on_scroll=remember_offset,
        scroll_interval=100,
    )
    return scaffold(
        view_path=view_path,
        title="Schedule",
        actions=[search_action(view_path, "sessions")],
        controls=[days, listing],
        on_retap=scroll_to_top,
    )


@ft.component
def MySchedule() -> ft.View:
    """The My schedule root."""
    view_path = ft.use_view_path()
    rows = [link(view_path, "session", sid, SESSIONS[sid][0]) for sid in ("99", "7")]
    return scaffold(
        view_path=view_path,
        title="My schedule",
        controls=[ft.ListView(rows, expand=True)],
    )


@ft.component
def MapRoot() -> ft.View:
    """The Map root: rooms."""
    view_path = ft.use_view_path()
    rows = [link(view_path, "room", slug, name) for slug, name in ROOMS.items()]
    return scaffold(
        view_path=view_path,
        title="Map",
        actions=[search_action(view_path, "rooms")],
        controls=[ft.ListView(rows, expand=True)],
    )


@ft.component
def More() -> ft.View:
    """The More root: a page, the journey runner, the knobs and diagnostics."""
    page = ft.context.page
    view_path = ft.use_view_path()
    memory = ft.use_context(MemoryCtx)
    _, rerender = ft.use_state(0)

    def toggle(knob: str) -> None:
        KNOBS[knob] = not KNOBS[knob]
        log("knob", **{knob: KNOBS[knob]})
        rerender(lambda n: n + 1)

    def start_journeys() -> None:
        page.run_task(run_journeys, page, memory, "button")

    rows = [
        ft.ListTile(
            title=ft.Text("Speakers"), on_click=lambda: page.navigate("/more/speakers")
        ),
        ft.ListTile(title=ft.Text("Run journeys"), on_click=start_journeys),
        ft.Switch(
            label="Shared root View key",
            value=KNOBS["shared_root_key"],
            on_change=lambda: toggle("shared_root_key"),
        ),
        ft.Switch(
            label="ViewMemory per process",
            value=KNOBS["memory_per_process"],
            on_change=lambda: toggle("memory_per_process"),
        ),
        ft.Switch(
            label="Stop effects on close",
            value=KNOBS["stop_on_close"],
            on_change=lambda: toggle("stop_on_close"),
        ),
        ft.Switch(
            label="Bar on pushed Views",
            value=KNOBS["bar_on_pushed"],
            on_change=lambda: toggle("bar_on_pushed"),
        ),
        ft.Text(f"pid {os.getpid()} · memory {id(memory):x} · route {page.route}"),
    ]
    return scaffold(
        view_path=view_path,
        title="More",
        actions=[search_action(view_path, "all")],
        controls=[ft.ListView(rows, expand=True)],
    )


@ft.component
def Speakers() -> ft.View:
    """`/more/speakers`: a More page with drill rows."""
    view_path = ft.use_view_path()
    rows = [link(view_path, "speaker", spid, name) for spid, name in SPEAKERS.items()]
    return scaffold(
        view_path=view_path, title="Speakers", controls=[ft.ListView(rows, expand=True)]
    )


@ft.component
def Search() -> ft.View:
    """The global modal `/search` (D-19): results push details on top of it."""
    page = ft.context.page
    view_path = ft.use_view_path()
    memory = ft.use_context(MemoryCtx)
    scope, _ = ft.use_state(
        lambda: parse_qs(urlparse(page.route).query).get(
            "scope", [memory.search_scope]
        )[0]
    )
    query, set_query = ft.use_state(memory.search_query)
    memory.search_scope = scope

    def on_change(e: ft.Event[ft.TextField]) -> None:
        memory.search_query = e.control.value
        set_query(e.control.value)

    words = query.casefold().split()
    hits = [("session", sid, title) for sid, (title, _, _) in SESSIONS.items()]
    hits += [("speaker", spid, name) for spid, name in SPEAKERS.items()]
    hits += [("room", slug, name) for slug, name in ROOMS.items()]
    hits = [hit for hit in hits if all(w in hit[2].casefold() for w in words)]
    if scope != "all":
        hits = [hit for hit in hits if hit[0] + "s" == scope]
    log("search-render", query=repr(query), scope=scope, hits=len(hits))
    return scaffold(
        view_path=view_path,
        title="Search",
        back_to=memory.search_base,
        controls=[
            ft.TextField(value=query, label="Search", on_change=on_change),
            ft.Text(f"scope {scope} · opened from {memory.search_base}"),
            ft.ListView([link(view_path, *hit) for hit in hits], expand=True),
        ],
    )


@ft.component
def Drill() -> ft.Control:
    """One drill level: dispatch on this level's own kind and id (F6)."""
    params = ft.use_route_params()
    view_path = ft.use_view_path()
    kind, ident = params.get("kind", ""), unquote(params.get("ident", ""))
    LEVELS[view_path] = (kind, ident)
    log("level", view=view_path, kind=kind, ident=repr(ident))
    return Detail(kind=kind, ident=ident)


@ft.component
def Detail(kind: str, ident: str) -> ft.View:
    """A stub session, speaker or room screen; an unknown id goes to the parent."""
    page = ft.context.page
    view_path = ft.use_view_path()
    memory = ft.use_context(MemoryCtx)
    rows: list[ft.Control] = [
        ft.Text(f"{kind} {ident!r} at {view_path}", selectable=True)
    ]
    title = None
    if kind == "session" and (found := find_session(ident)):
        title, speakers, room = found
        rows += [link(view_path, "speaker", spid, SPEAKERS[spid]) for spid in speakers]
        rows.append(link(view_path, "room", room, ROOMS[room]))
    elif kind == "speaker" and ident in SPEAKERS:
        title = SPEAKERS[ident]
        own = [sid for sid, (_, spids, _) in SESSIONS.items() if ident in spids]
        rows += [link(view_path, "session", sid, SESSIONS[sid][0]) for sid in own]
    elif kind == "room" and ident in ROOMS:
        title = ROOMS[ident]
        own = [sid for sid, (_, _, slug) in SESSIONS.items() if slug == ident]
        rows += [link(view_path, "session", sid, SESSIONS[sid][0]) for sid in own]

    async def leave_unknown() -> None:
        if title is None:
            target = parent_of(view_path, memory.search_base)
            log("unknown-id", view=view_path, to=target)
            page.navigate(target)
            page.show_dialog(ft.SnackBar(ft.Text(f"That {kind} isn't in the schedule")))

    ft.use_effect(leave_unknown, [view_path])
    return scaffold(
        view_path=view_path,
        title=title or "Not found",
        actions=[search_action(view_path, "all")],
        controls=[ft.ListView(rows, expand=True)],
    )


DRILL = ft.Route(
    path=":kind(session|speaker|room)/:ident", recursive=True, component=Drill
)


def pushed(path: str, component, *children: ft.Route) -> ft.Route:
    """A screen that can open details on top of itself (roots, More pages, search)."""
    return ft.Route(path=path, component=component, children=[*children, DRILL])


ROUTES = [
    ft.Route(index=True, component=Start),
    ft.Route(path="search", component=Search, modal=True, children=[DRILL]),
    pushed("now", Now),
    pushed("schedule", Schedule),
    pushed("my-schedule", MySchedule),
    pushed("map", MapRoot),
    pushed("more", More, pushed("speakers", Speakers)),
]


# ------------------------------------------------------------------ app
@ft.component
def App(memory: ViewMemory):
    """Boot gate, then the Router; page handlers are set once preferences load."""
    page = ft.context.page
    device, _ = ft.use_state(Device)
    prefs = ft.use_memo(ft.SharedPreferences, [])
    stop = ft.use_memo(asyncio.Event, [])
    own = ft.use_memo(lambda: SESSIONS_STARTED[0], [])  # this session's number

    def on_brightness(e: ft.PlatformBrightnessChangeEvent) -> None:
        device.dark = page.platform_brightness == ft.Brightness.DARK
        device.brightness_events += 1
        log("brightness", dark=device.dark)

    def on_lifecycle(e: ft.AppLifecycleStateChangeEvent) -> None:
        device.lifecycle = e.state.value
        device.lifecycle_events += 1
        log("lifecycle", state=e.state.value)

    def on_close() -> None:  # a new session replaced this one (F26)
        log("close", own=own, stop=KNOBS["stop_on_close"])
        if KNOBS["stop_on_close"]:
            stop.set()  # what the effect's cleanup would do on unmount

    async def start() -> None:
        launches = int(await prefs.get("s4.launches") or 0) + 1
        await prefs.set("s4.launches", launches)
        device.dark = page.platform_brightness == ft.Brightness.DARK
        device.session = own
        page.on_platform_brightness_change = on_brightness
        page.on_app_lifecycle_state_change = on_lifecycle
        page.on_close = on_close
        device.loaded = True  # opens the boot gate
        log("loaded", launches=launches, route=page.route)
        if os.environ.get("S4_JOURNEY"):
            page.run_task(run_journeys, page, memory, "env")

    async def tick() -> None:  # does an old session's effect outlive it? (F26)
        try:
            while not stop.is_set():
                device.ticks += 1  # a store write: does it reach a client?
                log("tick", own=own, ticks=device.ticks)
                await asyncio.sleep(15)
        except BaseException as error:  # how the loop ends tells how the session ends
            log("tick-end", own=own, error=repr(error))
            raise
        log("tick-end", own=own, error="none")

    ft.use_effect(start, [])
    ft.use_effect(tick, [], cleanup=stop.set)

    if not device.loaded:
        return [
            ft.View(
                route="/",
                bgcolor="#680579",
                controls=[ft.Text("Booting…", color=ft.Colors.WHITE)],
            )
        ]
    return MemoryCtx(
        memory, lambda: DeviceCtx(device, lambda: ft.Router(ROUTES, manage_views=True))
    )


def main(page: ft.Page) -> None:
    """Set our view-pop handler, then render the views (D-19)."""
    SESSIONS_STARTED[0] += 1
    if os.environ.get("S4_BAR_ON_PUSHED") == "0":  # simctl launch can't tap a knob
        KNOBS["bar_on_pushed"] = False
    memory = _PROCESS_MEMORY if KNOBS["memory_per_process"] else ViewMemory()
    log(
        "main", pid=os.getpid(), route=page.route, memory=f"{id(memory):x}", knobs=KNOBS
    )
    transitions = ft.PageTransitionsTheme(
        android=ft.PageTransitionTheme.PREDICTIVE, ios=ft.PageTransitionTheme.CUPERTINO
    )
    page.theme = ft.Theme(color_scheme_seed="#3B3EA9", page_transitions=transitions)
    page.dark_theme = ft.Theme(
        color_scheme_seed="#3B3EA9", page_transitions=transitions
    )
    page.theme_mode = ft.ThemeMode.SYSTEM

    def on_view_pop(e: ft.ViewPopEvent) -> None:
        target = parent_of(e.route, memory.search_base)
        log("view-pop", route=e.route, to=target)
        page.navigate(target)

    page.on_disconnect = lambda: log("disconnect")
    page.on_view_pop = on_view_pop  # before render_views: the Router hands it every pop
    page.render_views(App, memory)


# ------------------------------------------------------------------ journeys
async def run_journeys(page: ft.Page, memory: ViewMemory, reason: str) -> None:
    """Walk the S4 journeys through the router and check every step.

    Taps call what the UI calls (`drill_href`, `parent_of`, the tab targets);
    system Back and gestures are driven from outside (`drive_android.py`).
    """
    results = {"pass": 0, "fail": 0}
    log("journey-start", reason=reason)

    async def step(action: str, target: str, expect: str, base: str = "/now") -> None:
        page.navigate(target)
        for _ in range(60):
            await asyncio.sleep(0.05)
            if urlparse(memory.last_location).path == urlparse(expect).path:
                break
        views = [ft.unwrap_component(v) for v in ft.unwrap_component(page.views)]
        top = urlparse(memory.last_location).path
        ok = top == urlparse(expect).path and len(views) == stack_depth(expect, base)
        results["pass" if ok else "fail"] += 1
        log(
            "step",
            ok=ok,
            action=action,
            expect=expect,
            top=top,
            views=len(views),
            want=stack_depth(expect, base),
            keys="|".join(getattr(v, "route", "?") for v in views),
        )

    async def checkpoint(name: str) -> None:
        log("checkpoint", name=name)
        await asyncio.sleep(3)  # the host takes a screenshot on this line

    def back() -> str:
        return parent_of(memory.last_location, memory.search_base)

    # J0: one slow push and pop, so a screen recording shows a whole transition.
    await step("tab", "/now", "/now")
    await asyncio.sleep(1.5)
    await step("push", "/now/session/42", "/now/session/42")
    await asyncio.sleep(1.5)
    await step("back-arrow", "/now", "/now")
    await asyncio.sleep(1.5)
    # J1: Now -> session -> speaker -> session -> room, then the back arrow x4.
    chain = [
        ("session", "42"),
        ("speaker", "17"),
        ("session", "99"),
        ("room", "room-102a"),
    ]
    for kind, ident in chain:
        here = urlparse(memory.last_location).path
        await step("push", drill_href(here, kind, ident), drill_href(here, kind, ident))
    levels = [LEVELS.get(v) for v in ("/now/session/42", "/now/session/42/speaker/17")]
    log("per-level", levels=levels, ok=levels == [("session", "42"), ("speaker", "17")])
    await checkpoint("j1-room")
    for _ in chain:
        await step("back-arrow", back(), back())
    # J2: ids with ':', '+', ' ', '~' and non-ASCII through three levels.
    for kind, ident in [
        ("session", "poster detail+1"),
        ("speaker", "ç~31"),
        ("session", "7"),
    ]:
        here = urlparse(memory.last_location).path
        await step("push", drill_href(here, kind, ident), drill_href(here, kind, ident))
    top_level = LEVELS.get(urlparse(memory.last_location).path)
    log("per-level", levels=[top_level], ok=top_level == ("session", "7"))
    await checkpoint("j2-quoted")
    await step("tab-retap", "/now", "/now")
    # J3: search from a pushed view, a result, a detail, Back to the results, Back out.
    await step("push", "/schedule", "/schedule")
    await step("push", "/schedule/session/d1-03", "/schedule/session/d1-03")
    memory.search_base, memory.search_query = page.route, "ada"
    base = memory.search_base
    await step("open-search", "/search?scope=speakers", "/search", base)
    await step("push", "/search/speaker/17", "/search/speaker/17", base)
    await step(
        "push", "/search/speaker/17/session/42", "/search/speaker/17/session/42", base
    )
    await checkpoint("j3-search-detail")
    await step("back-arrow", back(), "/search/speaker/17", base)
    await step("back-arrow", back(), "/search", base)
    log("search-kept", query=repr(memory.search_query), ok=memory.search_query == "ada")
    await checkpoint("j3-search-results")
    await step("search-back", parent_of("/search", memory.search_base), base)
    # J4: tabs: a pushed view, re-tap its tab, the others.
    await step("push", "/map/room/hall-a", "/map/room/hall-a")
    await checkpoint("j4-map-detail")
    await step("tab-retap", "/map", "/map")
    for root in ("/my-schedule", "/more", "/schedule", "/now"):
        await step("tab", root, root)
    # J5: ViewMemory: day and offset restored after a tab switch.
    memory.schedule_day, memory.schedule_offsets[2] = 2, 1500.0
    await step("tab", "/schedule", "/schedule")
    await checkpoint("j5-schedule-day2")
    await step("tab", "/now", "/now")
    # J6: deep entry: a three-level stack in one navigation, then Back x3.
    deep = "/map/room/hall-a/session/42/speaker/23"
    await step("deep", deep, deep)
    for _ in range(3):
        await step("back-arrow", back(), back())
    # J7: an unknown id renders once, then lands on its parent with a SnackBar.
    LEVELS.pop("/schedule/session/nope", None)
    await step("unknown", "/schedule/session/nope", "/schedule")
    rendered = LEVELS.get("/schedule/session/nope") == ("session", "nope")
    results["pass" if rendered else "fail"] += 1
    log("unknown-rendered", ok=rendered)
    await checkpoint("j7-unknown")
    await step("tab", "/now", "/now")
    log("journey-done", **results)


if __name__ == "__main__":
    ft.run(main)
