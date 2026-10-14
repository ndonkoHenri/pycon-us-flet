"""S6 reproducer: can a scheduled reminder fire while the app isn't running?

Spike S6 (docs/spikes/06-reminders.md). The app drives the throwaway
``flet_s6_reminders`` extension (the E3 API over flutter_local_notifications):
it asks for permission, schedules reminders a few minutes ahead, lists and
cancels them, and shows how it was opened (a cold-start tap or a tap while
running). Every step is also printed as a line starting with ``S6 `` (logcat tag
``flet.python`` on Android), so the drivers can read it.

A start route runs one step with no tap, which the iOS simulator needs:
``/schedule/<seconds>[/<exact|inexact>[/<id>]]``, ``/many/<count>/<seconds>``
and ``/move``.
A reminder's payload is ``/opened/<id>``, the route a tap would open in the app.

Imperative on purpose: the subject is the notification plumbing, not the UI.
"""

import time
from datetime import UTC, datetime, timedelta

import flet as ft
from flet_s6_reminders import S6Reminders, TapEvent

FIRST_ID = 42  # a numeric session id, as D-59 uses
MOVED_ID = 7  # the "moved session" check reuses one id
MANY_FIRST_ID = 1000  # the "more than 64" plan
TEST_LEAD_S = 120


def log(event: str, **values: object) -> None:
    """Print one ``S6`` line with the wall-clock time, for the drivers."""
    fields = " ".join(f"{key}={value}" for key, value in values.items())
    print(f"S6 {event} wall={time.time():.3f} {fields}", flush=True)


def utc_hms(at: datetime) -> str:
    """Format an instant as ``HH:MM:SS UTC`` for titles and bodies."""
    return at.astimezone(UTC).strftime("%H:%M:%S UTC")


async def main(page: ft.Page) -> None:
    """Build the screen, set the extension up and run the start route's step."""
    page.title = "S6 Reminders"
    page.theme_mode = ft.ThemeMode.SYSTEM
    status = ft.Text(selectable=True)
    opened = ft.Text(theme_style=ft.TextThemeStyle.TITLE_MEDIUM)
    pending_text = ft.Text(selectable=True)

    def on_tap(e: TapEvent) -> None:
        log("tap", id=e.id, payload=e.payload)
        opened.value = f"Opened from reminder {e.id} while running ({e.payload})"
        page.update()

    reminders = S6Reminders(on_tap=on_tap)

    async def refresh_status() -> None:
        perm = await reminders.permission_status()
        pending = await reminders.get_pending()
        log(
            "status",
            enabled=perm["enabled"],
            exact=perm["exact"],
            pending=len(pending),
            ids=",".join(str(p.id) for p in sorted(pending, key=lambda p: p.id)),
        )
        status.value = (
            f"Notifications allowed: {perm['enabled']}\n"
            f"Exact alarms allowed: {perm['exact']}\n"
            f"Pending: {len(pending)}"
        )
        pending_text.value = ", ".join(str(p.id) for p in pending[:12]) + (
            " …" if len(pending) > 12 else ""
        )
        page.update()

    async def schedule(rid: int, seconds: int, *, exact: bool = False) -> None:
        # Whole seconds: the plugin drops the fraction anyway (yyyy-mm-ddThh:mm:ss).
        at = (datetime.now(UTC) + timedelta(seconds=seconds)).replace(microsecond=0)
        error = await reminders.zoned_schedule(
            rid,
            f"Reminder {rid}",
            f"Due {utc_hms(at)}{' (exact)' if exact else ''}",
            at,
            payload=f"/opened/{rid}",
            exact=exact,
        )
        log("scheduled", id=rid, due=f"{at.timestamp():.3f}", exact=exact, error=error)

    async def schedule_one(seconds: int, exact: bool, rid: int = FIRST_ID) -> None:
        await schedule(rid, seconds, exact=exact)
        await refresh_status()

    async def schedule_many(count: int, seconds: int) -> None:
        # D-59's "cancel all, reschedule", with more than iOS's 64.
        await reminders.cancel_all()
        for i in range(count):
            await schedule(MANY_FIRST_ID + i, seconds + 60 * i)
        await refresh_status()

    async def move() -> None:
        # A saved session moved in the feed: the same id, rescheduled later.
        await reminders.cancel_all()
        await schedule(MOVED_ID, TEST_LEAD_S)
        await reminders.cancel_all()
        await schedule(MOVED_ID, 2 * TEST_LEAD_S)
        await refresh_status()

    async def ask(_: ft.Event[ft.Button]) -> None:
        granted = await reminders.request_permission()
        log("permission", granted=granted)
        await refresh_status()

    async def in_two(_: ft.Event[ft.Button]) -> None:
        await schedule_one(TEST_LEAD_S, exact=False)

    async def in_two_exact(_: ft.Event[ft.Button]) -> None:
        await schedule_one(TEST_LEAD_S, exact=True)

    async def seventy(_: ft.Event[ft.Button]) -> None:
        await schedule_many(70, TEST_LEAD_S)

    async def moved(_: ft.Event[ft.Button]) -> None:
        await move()

    async def exact_setting(_: ft.Event[ft.Button]) -> None:
        log("exact-setting", result=await reminders.request_exact())

    async def cancel(_: ft.Event[ft.Button]) -> None:
        await reminders.cancel_all()
        log("cancelled")
        await refresh_status()

    async def show_pending(_: ft.Event[ft.Button]) -> None:
        await refresh_status()

    page.add(
        ft.SafeArea(
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                spacing=12,
                controls=[
                    ft.Text(
                        "S6 Reminders", theme_style=ft.TextThemeStyle.HEADLINE_SMALL
                    ),
                    opened,
                    status,
                    pending_text,
                    ft.FilledButton("Allow notifications", on_click=ask),
                    ft.FilledButton("Remind me in 2 min", on_click=in_two),
                    ft.OutlinedButton(
                        "Remind me in 2 min (exact)", on_click=in_two_exact
                    ),
                    ft.OutlinedButton("Move reminder 7 to 4 min", on_click=moved),
                    ft.OutlinedButton("Plan 70 reminders", on_click=seventy),
                    ft.OutlinedButton(
                        "Alarms & reminders setting", on_click=exact_setting
                    ),
                    ft.TextButton("Show pending", on_click=show_pending),
                    ft.TextButton("Cancel all", on_click=cancel),
                ],
            )
        )
    )

    launch = await reminders.initialize()
    log(
        "launch",
        by_tap=launch.launched_by_tap,
        id=launch.id,
        payload=launch.payload,
        route=page.route,
    )
    if launch.launched_by_tap:
        opened.value = (
            f"Opened from reminder {launch.id} at cold start ({launch.payload})"
        )

    parts = [p for p in page.route.split("/") if p]
    if parts[:1] == ["schedule"] and len(parts) >= 2:
        rid = int(parts[3]) if len(parts) >= 4 else FIRST_ID
        await schedule_one(int(parts[1]), exact=parts[2:3] == ["exact"], rid=rid)
    elif parts[:1] == ["many"] and len(parts) == 3:
        await schedule_many(int(parts[1]), int(parts[2]))
    elif parts == ["move"]:
        await move()
    await refresh_status()


ft.run(main)
