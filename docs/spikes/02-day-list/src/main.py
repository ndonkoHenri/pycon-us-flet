"""S2 reproducer: the busiest schedule day in components mode, in several variants.

Spike S2 (docs/spikes/02-day-list.md). The app processes the bundled 2026 snapshot with the
real ``pycon_us`` code and draws the schedule as ux.md §5.2 and §3.9 describe it: day tabs, a
search field, and for each day one list item per time slot, with the time in a 64 dp gutter
beside the slot's rows. Session rows carry a track badge, the title, "time · room", the
speakers and a 48 dp star; notices and breaks are compact rows without a star.

The launch route picks the variant, ``/<rows>/<list>/<days>``:

- rows: ``memo`` (each row an ``@ft.component`` keyed by session id and wrapped in
  ``ft.memo``, so it re-renders only when ``(row, is_fav)`` changes), ``component`` (the same
  component without ``ft.memo``), ``plain`` (plain controls rebuilt by the day list) or
  ``tree`` (``memo`` rows inside memoised slot components, inside memoised day lists that
  receive only their own day's favourites, so a change re-renders one path of the tree);
- list: ``lazy`` (``ListView``, ``build_controls_on_demand=True``, the default), ``eager``
  (``ListView(build_controls_on_demand=False)``), ``column`` (``Column(scroll=AUTO)``) or
  ``cache`` (a lazy ``ListView`` with a 100,000 px ``cache_extent``);
- days: ``all`` (every day's list is rendered at start, as a ``TabBarView`` page),
  ``visited`` (a day's list is rendered the first time its tab is shown) or ``deferred``
  (the shown day first; the other days in a second render right after the first frame).

Every measurement is a line ``S2 <event> wall=<epoch> py_ms=<since main.py> ...`` on stdout
(logcat tag ``flet.python`` on Android, the unified log on iOS). An action (a star tap, a
keystroke, a day switch, a jump) logs ``<action>-in`` in its handler, then ``patched`` when the
re-render has been sent to Flutter, and ``acked`` when a SharedPreferences round trip made
after it returns: Flutter handles messages in order, so the patch has been applied by then,
but the reply does not wait for a frame (the S1 proxy, D-112).
"""

import time

T0 = time.perf_counter()  # the first statement: Python has reached main.py


def since_start_ms() -> float:
    """Milliseconds since Python reached the top of this file."""
    return (time.perf_counter() - T0) * 1000


def log(event: str, **values: object) -> None:
    """Print one measurement line: the event, the wall clock and the time since T0."""
    fields = " ".join(f"{key}={value}" for key, value in values.items())
    print(
        f"S2 {event} wall={time.time():.3f} py_ms={since_start_ms():.0f} {fields}",
        flush=True,
    )


log("py-start")

import asyncio
from dataclasses import dataclass

import flet as ft

from pycon_us import config
from pycon_us.core import feed, queries, timefmt
from pycon_us.core.models import Day, Session
from pycon_us.theme import build_theme, build_tokens

log("imports")

# ---------------------------------------------------------------- data, once per process

YEAR = config.load_year()
ZONE = YEAR.conference.zone
_t = time.perf_counter()
DATA = feed.process(YEAR.read_snapshot().raw, YEAR.feed_settings)
log("processed", ms=f"{(time.perf_counter() - _t) * 1000:.0f}")

DAYS: tuple[Day, ...] = DATA.days
BUSIEST = max(
    range(len(DAYS)), key=lambda i: sum(len(g.session_ids) for g in DAYS[i].groups)
)
JUMP_SLOT = 20
"""The busiest day's slot that the jump buttons scroll to: far below the first screen."""

NOTICE_TRACKS = {"Break", "Informational"}

# ux.md §3.4: (fill, text) per track key, light then dark.
BADGES: dict[str, tuple[tuple[str, str], tuple[str, str]]] = {
    "Talk": (("#DCD6F5", "#24165A"), ("#291966", "#D6CEF3")),
    "Tutorial": (("#F5D6F3", "#5A1655"), ("#661961", "#F3CEF0")),
    "Keynote": (("#F0D6F5", "#50165A"), ("#5B1966", "#EDCEF3")),
    "Plenary": (("#F0D6F5", "#50165A"), ("#5B1966", "#EDCEF3")),
    "Lightning-talks": (("#F0DBEA", "#502042"), ("#5B254B", "#EDD3E6")),
    "Security": (("#F5E9D6", "#5A4116"), ("#664A19", "#F3E5CE")),
    "Ai": (("#D6F5EB", "#165A44"), ("#19664D", "#CEF3E7")),
    "Charla": (("#DBE3F0", "#21334F"), ("#253A5A", "#D4DEED")),
    "Poster": (("#F5DED6", "#5A2717"), ("#662D1A", "#F3D7CE")),
    "Sponsor Presentation": (("#F5ECD6", "#5A4616"), ("#665019", "#F3E8CE")),
    "Open Space": (("#D9F2E3", "#1C5433"), ("#20603A", "#D1F0DE")),
    "Summit": (("#E1E7EA", "#2E3C42"), ("#34444B", "#DBE2E6")),
    "Event": (("#D6F2F5", "#16545A"), ("#196066", "#CEF0F3")),
}
NEUTRAL_BADGE = (("#E6E6E6", "#383838"), ("#404040", "#E0E0E0"))
SPANISH_BADGE = (("#FFD7F3", "#5E0058"), ("#5E0058", "#FFD7F3"))


@dataclass(frozen=True, eq=False)
class RowView:
    """What a row shows, computed once per session (rows never format times themselves).

    Frozen with identity equality (D-70 rule 6), so ``ft.memo`` compares it by identity.
    """

    id: str
    track: str
    badge: str
    spanish: bool
    registration: bool
    title: str
    meta: str
    speakers: str
    notice: bool
    search_text: str
    spoken: str


def row_view(session: Session) -> RowView:
    """Build the view model of one row from the processed session."""
    when = timefmt.time_range_label(
        session.display_start, session.end, ZONE, use_24h=False
    )
    meta = f"{when} · {session.display_location}" if session.display_location else when
    speakers = ", ".join(session.speaker_names)
    badge = YEAR.conference.track_name(session.track)
    spoken = ". ".join(part for part in (badge, session.name, meta, speakers) if part)
    return RowView(
        id=session.id,
        track=session.track,
        badge=badge,
        spanish=session.spanish,
        registration=session.pre_registered,
        title=session.name,
        meta=meta,
        speakers=speakers,
        notice=session.track in NOTICE_TRACKS,
        search_text=session.search_text,
        spoken=spoken,
    )


@dataclass(frozen=True, eq=False)
class SlotView:
    """One time slot: its key, gutter labels and rows."""

    key: str
    time: str
    meridiem: str
    spoken_time: str
    rows: tuple[RowView, ...]


_t = time.perf_counter()
SLOTS: tuple[tuple[SlotView, ...], ...] = tuple(
    tuple(
        SlotView(
            key=f"slot-{group.start.isoformat()}",
            time=timefmt.time_label(group.start, ZONE, use_24h=False).split()[0],
            meridiem=timefmt.time_label(group.start, ZONE, use_24h=False).split()[1],
            spoken_time=timefmt.time_label(group.start, ZONE, use_24h=False),
            rows=tuple(row_view(DATA.sessions[sid]) for sid in group.session_ids),
        )
        for group in day.groups
    )
    for day in DAYS
)
log(
    "views",
    ms=f"{(time.perf_counter() - _t) * 1000:.0f}",
    busiest=DAYS[BUSIEST].date,
    slots=len(SLOTS[BUSIEST]),
    rows=sum(len(s.rows) for s in SLOTS[BUSIEST]),
)

SLOT_IDS = {
    slot.key: frozenset(r.id for r in slot.rows) for day in SLOTS for slot in day
}
DAY_IDS = [frozenset(r.id for slot in day for r in slot.rows) for day in SLOTS]

# ---------------------------------------------------------------- measurement state

ROW_RENDERS = [0]
"""Row bodies run since the process started; the difference per action is logged."""

PENDING: dict[str, object] = {}
"""The action in flight: its name and the row-render count when it began."""


def begin(action: str, **values: object) -> None:
    """Log the start of a user action and remember it for the next ``patched`` line."""
    PENDING.clear()
    PENDING.update(action=action, rows_before=ROW_RENDERS[0])
    log(f"{action}-in", **values)


@dataclass(frozen=True)
class Variant:
    """The variant under test, from the launch route."""

    rows: str = "memo"
    list: str = "lazy"
    days: str = "all"
    auto: bool = False  # ``?auto=1``: the app drives itself (no taps on a simulator)

    @staticmethod
    def from_route(route: str) -> Variant:
        """Parse ``/<rows>/<list>/<days>``; missing or unknown parts take the defaults."""
        parts = [p for p in route.split("?")[0].split("/") if p]
        rows = (
            parts[0]
            if parts[:1] and parts[0] in ("memo", "component", "plain", "tree")
            else "memo"
        )
        lst = (
            parts[1]
            if parts[1:2] and parts[1] in ("lazy", "eager", "column", "cache")
            else "lazy"
        )
        days = (
            parts[2]
            if parts[2:3] and parts[2] in ("all", "visited", "deferred")
            else "all"
        )
        return Variant(rows, lst, days, auto="auto=1" in route)


# ---------------------------------------------------------------- rows


def badge(
    text: str, colours: tuple[tuple[str, str], tuple[str, str]], dark: bool
) -> ft.Control:
    """A tonal track badge (ux.md §3.4): fill and text colour, 8 dp radius."""
    fill, ink = colours[1 if dark else 0]
    return ft.Container(
        bgcolor=fill,
        border_radius=8,
        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
        content=ft.Text(text, color=ink, theme_style=ft.TextThemeStyle.LABEL_SMALL),
    )


def row_controls(row: RowView, is_fav: bool, on_toggle, dark: bool) -> ft.Control:
    """The controls of one session row (ux.md §3.9 SessionRow and FavoriteButton)."""
    ROW_RENDERS[0] += 1
    badges = [badge(row.badge, BADGES.get(row.track, NEUTRAL_BADGE), dark)]
    if row.spanish:
        badges.append(badge("En Español", SPANISH_BADGE, dark))
    if row.registration:
        badges.append(
            ft.Container(
                bgcolor=ft.Colors.ERROR_CONTAINER,
                border_radius=8,
                padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                content=ft.Text(
                    "Registration required",
                    color=ft.Colors.ON_ERROR_CONTAINER,
                    theme_style=ft.TextThemeStyle.LABEL_SMALL,
                ),
            )
        )
    lines: list[ft.Control] = [
        ft.Row(wrap=True, spacing=4, run_spacing=4, controls=badges),
        ft.Text(row.title, theme_style=ft.TextThemeStyle.TITLE_MEDIUM, max_lines=3),
        ft.Text(row.meta, theme_style=ft.TextThemeStyle.BODY_MEDIUM),
    ]
    if row.speakers:
        lines.append(ft.Text(row.speakers, theme_style=ft.TextThemeStyle.BODY_MEDIUM))
    body = ft.Container(
        ink=True,
        on_click=lambda _: log("open", id=row.id),
        padding=ft.Padding.only(left=8, top=12, right=4, bottom=12),
        content=ft.Column(spacing=4, controls=lines),
    )
    tokens = build_tokens(dark=dark, high_contrast=False)
    return ft.Row(
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.START,
        controls=[
            ft.MergeSemantics(expand=True, content=body),
            ft.IconButton(
                icon=ft.Icons.STAR_BORDER,
                selected_icon=ft.Icons.STAR,
                selected=is_fav,
                selected_icon_color=tokens.favorite,
                tooltip="Remove from My schedule" if is_fav else "Add to My schedule",
                on_click=lambda _: on_toggle(row.id),
            ),
        ],
    )


def notice_controls(row: RowView) -> ft.Control:
    """A compact notice or break row without a star (ux.md §3.9 NoticeRow)."""
    ROW_RENDERS[0] += 1
    return ft.Container(
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border_radius=8,
        margin=ft.Margin.only(left=8, right=16, top=4, bottom=4),
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        content=ft.Row(
            spacing=8,
            controls=[
                ft.Icon(
                    ft.Icons.COFFEE_OUTLINED
                    if row.track == "Break"
                    else ft.Icons.INFO_OUTLINE,
                    size=20,
                ),
                ft.Text(
                    f"{row.title} · {row.meta}",
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    expand=True,
                ),
            ],
        ),
    )


@ft.component
def SessionRow(row: RowView, is_fav: bool, on_toggle, dark: bool) -> ft.Control:
    """A session row as a component: its own node in the render tree."""
    return row_controls(row, is_fav, on_toggle, dark)


@ft.component
def NoticeRow(row: RowView) -> ft.Control:
    """A notice row as a component."""
    return notice_controls(row)


MemoSessionRow = ft.memo(SessionRow)
MemoNoticeRow = ft.memo(NoticeRow)


def build_row(
    row: RowView, is_fav: bool, on_toggle, dark: bool, mode: str
) -> ft.Control:
    """One row in the variant's form."""
    if mode == "plain":
        return (
            notice_controls(row)
            if row.notice
            else row_controls(row, is_fav, on_toggle, dark)
        )
    if mode == "memo":
        if row.notice:
            return MemoNoticeRow(row, key=row.id)
        return MemoSessionRow(row, is_fav, on_toggle, dark, key=row.id)
    if row.notice:
        return NoticeRow(row, key=row.id)
    return SessionRow(row, is_fav, on_toggle, dark, key=row.id)


def slot_item(
    slot: SlotView,
    rows: list[RowView],
    favs: frozenset[str],
    on_toggle,
    dark: bool,
    mode: str,
) -> ft.Control:
    """One list item per slot (D-31): a divider, then the gutter beside the rows."""

    def labels(time: str, meridiem: str, opacity: float = 1.0) -> ft.Control:
        return ft.Column(
            spacing=0,
            opacity=opacity,
            controls=[
                ft.Text(time, theme_style=ft.TextThemeStyle.TITLE_SMALL),
                ft.Text(meridiem, theme_style=ft.TextThemeStyle.LABEL_SMALL),
            ],
        )

    # No fixed width: a fixed 64 dp broke "7:30" over two lines at 200 % text. An
    # invisible "10:00 AM" sets the width, so it grows with the text and stays the same
    # for every slot, and the rows keep one left edge.
    gutter = ft.Semantics(
        header=True,
        label=slot.spoken_time,
        exclude_semantics=True,
        content=ft.Container(
            padding=ft.Padding.only(left=16, top=12, right=8),
            content=ft.Stack(
                controls=[
                    labels("10:00", "AM", opacity=0),
                    labels(slot.time, slot.meridiem),
                ]
            ),
        ),
    )
    return ft.Container(
        key=ft.ScrollKey(slot.key),
        content=ft.Column(
            spacing=0,
            controls=[
                ft.Divider(height=1),
                ft.Row(
                    spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        gutter,
                        ft.Column(
                            expand=True,
                            spacing=0,
                            controls=[
                                build_row(r, r.id in favs, on_toggle, dark, mode)
                                for r in rows
                            ],
                        ),
                    ],
                ),
            ],
        ),
    )


def matches(row: RowView, words: list[str]) -> bool:
    """D-46: every folded word of the query is in the row's search text or meta."""
    return all(w in row.search_text or w in row.meta.casefold() for w in words)


@ft.component
def SlotItem(
    slot: SlotView,
    rows: tuple[RowView, ...],
    favs_here: frozenset[str],
    on_toggle,
    dark: bool,
) -> ft.Control:
    """A slot item as a component (``tree``): props are the slot, its rows, its favourites."""
    return slot_item(slot, list(rows), favs_here, on_toggle, dark, "memo")


MemoSlotItem = ft.memo(SlotItem)


@ft.component
def DayList(
    index: int,
    query: str,
    favs: frozenset[str],
    on_toggle,
    variant: Variant,
    dark: bool,
    list_ref: ft.Ref,
) -> ft.Control:
    """The list of one day: a slot item per time slot that has a matching row."""
    words = queries.fold(query).split()
    items = []
    for slot in SLOTS[index]:
        rows = [r for r in slot.rows if matches(r, words)] if words else list(slot.rows)
        if rows and variant.rows == "tree":
            here = favs & SLOT_IDS[slot.key]
            items.append(
                MemoSlotItem(slot, tuple(rows), here, on_toggle, dark, key=slot.key)
            )
        elif rows:
            items.append(slot_item(slot, rows, favs, on_toggle, dark, variant.rows))
    if not items:
        return ft.Container(
            padding=24,
            content=ft.Text(
                "No sessions match.", theme_style=ft.TextThemeStyle.BODY_LARGE
            ),
        )

    def on_scroll(e: ft.OnScrollEvent) -> None:
        if e.event_type == ft.ScrollType.END:
            log(
                "scrolled",
                day=index,
                pixels=f"{e.pixels:.0f}",
                max=f"{e.max_scroll_extent:.0f}",
            )

    if variant.list == "column":
        return ft.Column(
            ref=list_ref,
            controls=items,
            spacing=0,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            on_scroll=on_scroll,
        )
    return ft.ListView(
        ref=list_ref,
        controls=items,
        expand=True,
        build_controls_on_demand=variant.list != "eager",
        cache_extent=100_000 if variant.list == "cache" else None,
        on_scroll=on_scroll,
    )


MemoDayList = ft.memo(DayList)


# ---------------------------------------------------------------- the screen


@ft.component
def App(variant: Variant, dark: bool) -> list[ft.View]:
    """The Schedule root: app bar, day tabs, a search field and the day lists."""
    favs, set_favs = ft.use_state(frozenset())
    query, set_query = ft.use_state("")
    day, set_day = ft.use_state(BUSIEST)
    visited, set_visited = ft.use_state(frozenset({BUSIEST}))
    rest, set_rest = ft.use_state(False)  # deferred: the other days are rendered
    prefs = ft.use_memo(lambda: ft.SharedPreferences(), [])
    refs = ft.use_memo(lambda: [ft.Ref() for _ in DAYS], [])

    def toggle(session_id: str) -> None:
        begin("star", id=session_id)
        set_favs(lambda f: f - {session_id} if session_id in f else f | {session_id})

    on_toggle = ft.use_callback(toggle, [])

    def on_query(e: ft.ControlEvent) -> None:
        begin("key", q=repr(e.control.value))
        set_query(e.control.value)

    def on_day(e: ft.ControlEvent) -> None:
        index = int(e.data)
        begin("day", index=index)
        set_day(index)
        set_visited(lambda v: v | {index})

    async def jump(e: ft.ControlEvent) -> None:
        slot = SLOTS[day][min(JUMP_SLOT, len(SLOTS[day]) - 1)]
        log("jump-in", key=slot.key, list=variant.list)
        await refs[day].current.scroll_to(scroll_key=ft.ScrollKey(slot.key), duration=0)
        log("jump-done", key=slot.key)

    async def jump_two_step(e: ft.ControlEvent) -> None:
        """Jump to an estimated offset first, so the target is built, then to its key."""
        slots = SLOTS[day]
        target = min(JUMP_SLOT, len(slots) - 1)
        # Logical pixels: a notice row is about 48 dp, a session row about 120 dp at 100 %.
        estimate = sum(48 if r.notice else 120 for s in slots[:target] for r in s.rows)
        log("jump2-in", key=slots[target].key, estimate=estimate)
        await refs[day].current.scroll_to(offset=estimate, duration=0)
        await asyncio.sleep(0.05)  # a few frames: the slots near the estimate get built
        await refs[day].current.scroll_to(
            scroll_key=ft.ScrollKey(slots[target].key), duration=0
        )
        log("jump2-done", key=slots[target].key)

    async def after_render() -> None:
        action = PENDING.get("action", "first")
        rows = ROW_RENDERS[0] - int(PENDING.get("rows_before", 0))  # type: ignore[arg-type]
        log("patched", action=action, rows_rendered=rows)
        await prefs.get("s2")
        log("acked", action=action)
        PENDING.clear()
        if action == "first" and variant.days == "deferred":
            begin("rest")
            set_rest(True)

    ft.use_effect(after_render, [favs, query, day, rest])

    async def drive() -> None:
        """With ``?auto=1``: jump, star, filter and switch days through the handlers."""
        if not variant.auto:
            return
        await asyncio.sleep(3)
        slot = SLOTS[BUSIEST][JUMP_SLOT]
        log("jump-in", key=slot.key, list=variant.list)
        await refs[BUSIEST].current.scroll_to(
            scroll_key=ft.ScrollKey(slot.key), duration=0
        )
        log("jump-done", key=slot.key)
        for _ in range(4):
            await asyncio.sleep(1.5)
            on_toggle(slot.rows[0].id)
        for text in ("p", "py", "pyt", "pyth", "pytho", "python", ""):
            await asyncio.sleep(1.5)
            begin("key", q=repr(text))
            set_query(text)
        for index in (3, 1, BUSIEST):
            await asyncio.sleep(1.5)
            begin("day", index=index)
            set_day(index)
        log("auto-done")

    ft.use_effect(drive, [])

    pages: list[ft.Control] = []
    for index in range(len(DAYS)):
        if variant.days == "all" or index in visited or rest:
            pages.append(
                (MemoDayList if variant.rows == "tree" else DayList)(
                    index,
                    query if index == day else "",
                    favs & DAY_IDS[index] if variant.rows == "tree" else favs,
                    on_toggle,
                    variant,
                    dark,
                    refs[index],
                    key=f"day-{index}",
                )
            )
        else:
            pages.append(ft.Container(key=f"day-{index}"))

    body = ft.Tabs(
        length=len(DAYS),
        selected_index=day,
        on_change=on_day,
        expand=True,
        content=ft.Column(
            spacing=0,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.TabBar(
                    # Two-line DayLabel (ux.md §5.2): five days fit, so the bar is fixed
                    # and the tabs keep their places.
                    tabs=[
                        ft.Tab(label=timefmt.day_label(d.date).replace(", ", "\n"))
                        for d in DAYS
                    ],
                    scrollable=False,
                ),
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                    content=ft.TextField(
                        # Controlled: without value=query, each re-render patches the
                        # field back to its constructor default and wipes what was typed.
                        value=query,
                        hint_text="Filter this day",
                        prefix_icon=ft.Icons.SEARCH,
                        dense=True,
                        # No blinking cursor: the screen recordings find each keystroke
                        # as the first change in the field (spike only).
                        show_cursor=False,
                        on_change=on_query,
                    ),
                ),
                ft.TabBarView(expand=True, controls=pages),
            ],
        ),
    )
    return [
        ft.View(
            route="/",
            padding=0,
            appbar=ft.AppBar(
                title=ft.Text(
                    f"Schedule · {variant.rows}/{variant.list}/{variant.days}"
                ),
                actions=[
                    ft.IconButton(
                        ft.Icons.SCHEDULE, tooltip="Jump to slot", on_click=jump
                    ),
                    ft.IconButton(
                        ft.Icons.MORE_TIME,
                        tooltip="Jump in two steps",
                        on_click=jump_two_step,
                    ),
                ],
            ),
            navigation_bar=ft.NavigationBar(
                selected_index=1,
                destinations=[
                    ft.NavigationBarDestination(
                        icon=ft.Icons.TODAY_OUTLINED, label="Now"
                    ),
                    ft.NavigationBarDestination(
                        icon=ft.Icons.CALENDAR_MONTH_OUTLINED, label="Schedule"
                    ),
                    ft.NavigationBarDestination(
                        icon=ft.Icons.STAR_BORDER, label="My schedule"
                    ),
                    ft.NavigationBarDestination(
                        icon=ft.Icons.MAP_OUTLINED, label="Map"
                    ),
                    ft.NavigationBarDestination(icon=ft.Icons.MORE_HORIZ, label="More"),
                ],
            ),
            controls=[
                ft.SafeArea(
                    expand=True,
                    avoid_intrusions_top=False,  # the AppBar takes the status bar
                    avoid_intrusions_bottom=False,  # the NavigationBar takes the gesture bar
                    content=body,
                )
            ],
        )
    ]


def main(page: ft.Page) -> None:
    """Read the variant from the launch route, set the themes and render."""
    variant = Variant.from_route(page.route or "/")
    dark = page.platform_brightness == ft.Brightness.DARK
    log(
        "main",
        route=page.route,
        variant=f"{variant.rows}/{variant.list}/{variant.days}",
        dark=dark,
    )
    page.theme = build_theme(dark=False, high_contrast=False)
    page.dark_theme = build_theme(dark=True, high_contrast=False)
    page.render_views(App, variant, dark)


if __name__ == "__main__":
    ft.run(main)
