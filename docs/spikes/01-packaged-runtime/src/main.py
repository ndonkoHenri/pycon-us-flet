"""S1 reproducer: our runtime stack inside a packaged Flet app.

Spike S1 (docs/spikes/01-packaged-runtime.md). On start the stub reads the cached
2026 feed from the durable data directory (``FLET_APP_STORAGE_DATA``), then
refreshes it from the public feed with httpx and writes it back atomically. It
also exercises sqlite3, SharedPreferences, SecureStorage and zoneinfo with tzdata.
Every measurement is shown on screen and printed as a line starting with ``S1 ``
(on Android, stdout goes to logcat under the tag ``flet.python``).
"""

import time

T0 = time.perf_counter()  # the first statement: Python has reached main.py


def since_start_ms() -> float:
    """Milliseconds since Python reached the top of this file."""
    return (time.perf_counter() - T0) * 1000


def log(event: str, **values: object) -> None:
    """Print one measurement line: the event, wall-clock time and time since T0.

    The wall clock lines the event up with the OS's own launch log (logcat's
    ActivityTaskManager START and Displayed lines on Android).
    """
    fields = " ".join(f"{key}={value}" for key, value in values.items())
    print(
        f"S1 {event} wall={time.time():.3f} py_ms={since_start_ms():.0f} {fields}",
        flush=True,
    )


log("py-start")

# Imports are timed in groups to decide whether lazy imports are worth it.
IMPORT_MS: dict[str, float] = {}
_t = time.perf_counter()
import asyncio
import json
import os
import sqlite3
import statistics
import sys
import zoneinfo
from collections.abc import Awaitable, Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

IMPORT_MS["stdlib"] = (time.perf_counter() - _t) * 1000
_t = time.perf_counter()
import httpx

IMPORT_MS["httpx"] = (time.perf_counter() - _t) * 1000
_t = time.perf_counter()
import flet as ft

IMPORT_MS["flet"] = (time.perf_counter() - _t) * 1000
_t = time.perf_counter()
import flet_secure_storage as fss

IMPORT_MS["flet_secure_storage"] = (time.perf_counter() - _t) * 1000
log("imports", **{name: f"{ms:.0f}" for name, ms in IMPORT_MS.items()})

FEED_URL = "https://us.pycon.org/2026/schedule/conference.json"  # public feed only
LA = "America/Los_Angeles"
DATA_DIR = Path(os.environ.get("FLET_APP_STORAGE_DATA", "."))
CACHE = DATA_DIR / "feed-2026.json"
PREF_LAUNCHES = "s1.launches"
PREF_OVERLAY = "s1.overlay"
SECURE_KEY = "s1.secret"
SEED = "#680579"


def read_cache() -> bytes | None:
    """Return the cached feed bytes, or None when there is no cache yet."""
    try:
        return CACHE.read_bytes()
    except FileNotFoundError:
        return None


def write_cache(raw: bytes) -> None:
    """Replace the cache atomically: write a temp file, fsync it, then os.replace."""
    tmp = CACHE.with_name(CACHE.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CACHE)


def process(doc: dict) -> int:
    """Stand in for feed processing: localise every start, group by day, sort."""
    tz = zoneinfo.ZoneInfo(LA)
    days: dict[date, list[tuple[datetime, int]]] = {}
    for item in doc["schedule"]:
        if start := item.get("start"):
            local = datetime.fromisoformat(start).astimezone(tz)
            days.setdefault(local.date(), []).append((local, item.get("conf_key", 0)))
    for rows in days.values():
        rows.sort()
    return sum(len(rows) for rows in days.values())


def timed_parse(raw: bytes) -> tuple[float, float, int]:
    """Parse and process the feed; return (parse ms, process ms, sessions)."""
    t = time.perf_counter()
    doc = json.loads(raw)
    parse_ms = (time.perf_counter() - t) * 1000
    t = time.perf_counter()
    sessions = process(doc)
    return parse_ms, (time.perf_counter() - t) * 1000, sessions


def record_launch() -> int:
    """Insert a row into a table in the data directory; return the row count."""
    with closing(sqlite3.connect(DATA_DIR / "s1.db")) as db, db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS launches (n INTEGER PRIMARY KEY, at TEXT)"
        )
        db.execute(
            "INSERT INTO launches (at) VALUES (?)", (datetime.now(UTC).isoformat(),)
        )
        return db.execute("SELECT count(*) FROM launches").fetchone()[0]


def session_time() -> str:
    """Format a 2026 session start (16:30 UTC) in the venue's time zone."""
    start = datetime(2026, 5, 15, 16, 30, tzinfo=UTC).astimezone(zoneinfo.ZoneInfo(LA))
    on_disk = any(Path(p, LA).exists() for p in zoneinfo.TZPATH)
    return (
        f"{start:%a %d %b %Y, %H:%M %Z} ({'system zoneinfo' if on_disk else 'tzdata'})"
    )


async def max_loop_gap_ms(work: Callable[[], Awaitable[object]]) -> float:
    """Run work while a 4 ms heartbeat measures the longest event-loop stall."""
    gaps: list[float] = []
    done = asyncio.Event()

    async def beat() -> None:
        last = time.perf_counter()
        while not done.is_set():
            await asyncio.sleep(0.004)
            now = time.perf_counter()
            gaps.append((now - last) * 1000)
            last = now

    task = asyncio.create_task(beat())
    await asyncio.sleep(0.02)
    await work()
    done.set()
    await task
    return max(gaps)


async def benchmark(raw: bytes) -> str:
    """Compare the loop stall of parsing on the event loop and in a worker thread."""

    async def on_loop() -> None:
        timed_parse(raw)

    async def in_thread() -> None:
        await asyncio.to_thread(timed_parse, raw)

    on, off, totals = [], [], []
    for _ in range(5):
        on.append(await max_loop_gap_ms(on_loop))
        off.append(await max_loop_gap_ms(in_thread))
        parse_ms, process_ms, _ = timed_parse(raw)
        totals.append(parse_ms + process_ms)
    result = {
        "parse_total_ms": f"{statistics.median(totals):.0f}",
        "gap_on_loop_ms": f"{statistics.median(on):.0f}",
        "gap_to_thread_ms": f"{statistics.median(off):.0f}",
    }
    log("bench", **result)
    return ", ".join(f"{k} {v}" for k, v in result.items())


def build_theme(dark: bool, overlay: str) -> ft.Theme:
    """A seeded theme; `overlay` picks the system overlay style under test (D-12)."""
    icons = ft.Brightness.LIGHT if dark else ft.Brightness.DARK
    style = None
    if overlay != "none":
        style = ft.SystemOverlayStyle(
            status_bar_color=ft.Colors.TRANSPARENT,
            system_navigation_bar_color=ft.Colors.TRANSPARENT,
            status_bar_icon_brightness=icons,
            system_navigation_bar_icon_brightness=icons,
            status_bar_brightness=ft.Brightness.DARK if dark else ft.Brightness.LIGHT,
            enforce_system_navigation_bar_contrast=overlay == "icons+scrim",
        )
    return ft.Theme(color_scheme_seed=SEED, system_overlay_style=style)


@dataclass
class Services:
    """The page services the stub uses, created once in main()."""

    prefs: ft.SharedPreferences
    secure: fss.SecureStorage


@ft.component
def App(services: Services) -> list[ft.View]:
    """One view with an AppBar and a NavigationBar, like the real app's roots."""
    page = ft.context.page
    rows, set_rows = ft.use_state(
        lambda: {
            "is_embedded()": str(ft.utils.is_embedded()),
            "Python": f"{sys.version.split()[0]} on {sys.platform}, flet {ft.__version__}",
            "Imports (ms)": ", ".join(f"{k} {v:.0f}" for k, v in IMPORT_MS.items()),
            "FLET_APP_STORAGE_DATA": str(DATA_DIR),
            "Session time": session_time(),
        }
    )
    phase, set_phase = ft.use_state("starting")
    overlay, set_overlay = ft.use_state("none")
    with_appbar, set_with_appbar = ft.use_state(True)
    feed = ft.use_ref(b"")

    def put(key: str, value: str) -> None:
        set_rows(lambda current: {**current, key: value})

    async def start() -> None:
        await services.prefs.get(PREF_LAUNCHES)  # answered after the first render
        put("Python start to first frame", f"{since_start_ms():.0f} ms")
        log("first-frame")
        set_overlay(str(await services.prefs.get(PREF_OVERLAY) or "none"))
        launches = int(await services.prefs.get(PREF_LAUNCHES) or 0) + 1
        await services.prefs.set(PREF_LAUNCHES, launches)
        put("SharedPreferences launches", str(launches))
        rows_in_db = record_launch()
        put("sqlite3 rows", str(rows_in_db))
        secret = await services.secure.get(SECURE_KEY)
        fresh = secret is None
        if fresh:
            secret = f"set {datetime.now(UTC):%Y-%m-%d %H:%M:%S}"
            await services.secure.set(SECURE_KEY, secret)
        same = await services.secure.get(SECURE_KEY) == secret
        kept = "new" if fresh else "kept"
        put("SecureStorage", f"{secret}, {kept}, read back {same}")
        log("storage", launches=launches, sqlite_rows=rows_in_db, secure=kept)
        if raw := read_cache():
            parse_ms, process_ms, sessions = timed_parse(raw)
            feed.current = raw
            put("Cache", f"{len(raw):,} bytes, {sessions} sessions")
            put("Cache parse + process", f"{parse_ms:.0f} + {process_ms:.0f} ms")
            log(
                "cache",
                bytes=len(raw),
                parse_ms=f"{parse_ms:.0f}",
                process_ms=f"{process_ms:.0f}",
            )
        else:
            put("Cache", "none yet")
        set_phase("cache-shown")

    async def cache_shown() -> None:
        if phase != "cache-shown":
            return
        await services.prefs.get(PREF_LAUNCHES)  # answered after the cache render
        put("Python start to cached content", f"{since_start_ms():.0f} ms")
        log("cache-frame")
        await refresh()

    async def refresh() -> None:
        t = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(FEED_URL)
                response.raise_for_status()
        except httpx.HTTPError as e:
            put("Network", f"failed: {e!r}; the cache stays")
            log("net-failed", error=type(e).__name__)
            return
        fetch_ms = (time.perf_counter() - t) * 1000
        raw = response.content
        parse_ms, process_ms, _ = timed_parse(
            raw
        )  # write only after a good parse (D-39)
        write_cache(raw)
        feed.current = raw
        put("Network", f"{len(raw):,} bytes in {fetch_ms:.0f} ms; cache written")
        put("Network parse + process", f"{parse_ms:.0f} + {process_ms:.0f} ms")
        put("Data dir files", ", ".join(sorted(p.name for p in DATA_DIR.iterdir())))
        log(
            "net",
            bytes=len(raw),
            fetch_ms=f"{fetch_ms:.0f}",
            parse_ms=f"{parse_ms:.0f}",
        )

    async def run_benchmark() -> None:
        if feed.current:
            put("Benchmark (median of 5)", "running…")
            put("Benchmark (median of 5)", await benchmark(feed.current))

    async def choose_overlay(e: ft.Event[ft.SegmentedButton]) -> None:
        value = next(iter(e.control.selected or ["none"]))
        set_overlay(value)
        await services.prefs.set(PREF_OVERLAY, value)

    async def apply_theme() -> None:  # effect setups are coroutines (D-70)
        page.theme = build_theme(dark=False, overlay=overlay)
        page.dark_theme = build_theme(dark=True, overlay=overlay)
        page.update()

    ft.use_effect(start, [])
    ft.use_effect(cache_shown, [phase])
    ft.use_effect(apply_theme, [overlay])

    controls: list[ft.Control] = [
        ft.SegmentedButton(
            segments=[
                ft.Segment(value="none", label=ft.Text("No style")),
                ft.Segment(value="icons", label=ft.Text("Icons")),
                ft.Segment(value="icons+scrim", label=ft.Text("Icons+scrim")),
            ],
            selected=[overlay],
            on_change=choose_overlay,
        ),
        ft.Row(
            [
                ft.Switch(
                    label="AppBar",
                    value=with_appbar,
                    on_change=lambda e: set_with_appbar(e.control.value),
                ),
                ft.FilledButton("Parse benchmark", on_click=run_benchmark),
            ]
        ),
    ]
    controls += [
        ft.ListTile(
            title=ft.Text(key), subtitle=ft.Text(value, selectable=True), dense=True
        )
        for key, value in rows.items()
    ]
    return [
        ft.View(
            route="/",
            appbar=ft.AppBar(title=ft.Text("S1 runtime")) if with_appbar else None,
            navigation_bar=ft.NavigationBar(
                destinations=[
                    ft.NavigationBarDestination(icon=ft.Icons.TODAY, label="Now"),
                    ft.NavigationBarDestination(
                        icon=ft.Icons.CALENDAR_MONTH, label="Schedule"
                    ),
                ]
            ),
            controls=[ft.ListView(controls=controls, expand=True)],
            padding=0,
        )
    ]


def main(page: ft.Page) -> None:
    """Create the services, then render the views."""
    log("main")
    page.theme_mode = ft.ThemeMode.SYSTEM
    services = Services(prefs=ft.SharedPreferences(), secure=fss.SecureStorage())
    page.render_views(App, services)


if __name__ == "__main__":
    ft.run(main)
