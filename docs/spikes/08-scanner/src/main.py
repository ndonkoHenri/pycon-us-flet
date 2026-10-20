"""S8 reproducer: does a minimal mobile_scanner extension decode in release builds?

Spike S8 (docs/spikes/08-scanner.md). One screen with the throwaway
``flet_s8_scanner`` control (the E1 API over mobile_scanner 7.4.2), a pause and a
torch switch, an "Analyze image" button that decodes the bundled ``qr.png``, and
the manual entry that always ships (D-65). When the app is not embedded (the
companion app, D-63) it shows manual entry alone. Every step is printed as a line
starting with ``S8 `` (logcat tag ``flet.python`` on Android) for the drivers.

Start routes, for what a driver cannot tap:
``/paused`` mounts the scanner paused; ``/cycles/<n>[/<ms>]`` pauses and resumes it
n times, ``ms`` apart (default 1500); ``/analyze`` decodes the bundled image.

Imperative on purpose: the subject is the camera plumbing, not the UI.
"""

import asyncio
import time
from pathlib import Path

import flet as ft
from flet.utils import is_embedded

QR_IMAGE = Path(__file__).with_name("qr.png")


def log(event: str, **values: object) -> None:
    """Print one ``S8`` line with the monotonic time, for the drivers."""
    fields = " ".join(f"{key}={value}" for key, value in values.items())
    print(f"S8 {event} mono={time.monotonic():.3f} {fields}", flush=True)


def manual_entry(status: ft.Text) -> ft.TextField:
    """Return the manual-entry field, which works with or without a camera."""

    def submitted(e: ft.Event[ft.TextField]) -> None:
        log("manual", value=e.control.value)
        status.value = f"Entered: {e.control.value}"
        status.update()

    return ft.TextField(label="Badge code", on_submit=submitted)


async def main(page: ft.Page) -> None:
    """Build the screen and run the start route's step."""
    page.title = "S8 Scanner"
    status = ft.Text(selectable=True)
    log("start", route=page.route, embedded=is_embedded())
    if not is_embedded():
        status.value = "Camera scanning isn't available in this build."
        page.add(ft.SafeArea(ft.Column([status, manual_entry(status)])))
        return

    from flet_s8_scanner import DetectEvent, ErrorEvent, S8Scanner

    parts = [p for p in page.route.split("/") if p]
    mounted = time.monotonic()
    seen: list[float] = []

    def detected(e: DetectEvent) -> None:
        now = time.monotonic()
        seen.append(now)
        recent = [t for t in seen if now - t <= 5]
        log(
            "detect", n=len(seen), since_mount=f"{now - mounted:.3f}", value=e.raw_value
        )
        status.value = (
            f"{len(seen)} detections, {len(recent) / 5:.1f}/s over 5 s: {e.raw_value}"
        )
        status.update()

    def failed(e: ErrorEvent) -> None:
        log("error", code=e.code, message=e.message)
        status.value = f"Camera error: {e.code}"
        status.update()

    scanner = S8Scanner(
        paused=parts[:1] == ["paused"],
        height=360,
        on_detect=detected,
        on_error=failed,
    )

    def toggle_pause(e: ft.Event[ft.Button]) -> None:
        scanner.paused = not scanner.paused
        log("paused", value=scanner.paused)
        scanner.update()

    def toggle_torch(e: ft.Event[ft.Button]) -> None:
        scanner.torch = not scanner.torch
        log("torch", value=scanner.torch)
        scanner.update()

    async def analyze(e: ft.Event[ft.Button] | None = None) -> None:
        started = time.monotonic()
        values = await scanner.analyze_image(str(QR_IMAGE))
        log("analyze", values=values, ms=f"{(time.monotonic() - started) * 1000:.0f}")
        status.value = f"Image: {values}"
        status.update()

    page.add(
        ft.SafeArea(
            ft.Column(
                [
                    scanner,
                    ft.Row(
                        [
                            ft.Button("Pause/Resume", on_click=toggle_pause),
                            ft.Button("Torch", on_click=toggle_torch),
                            ft.Button("Analyze image", on_click=analyze),
                        ],
                        wrap=True,
                    ),
                    status,
                    manual_entry(status),
                ]
            )
        )
    )
    log("mounted")

    if parts[:1] == ["analyze"]:
        await analyze()
    elif parts[:1] == ["cycles"]:
        count = int(parts[1])
        gap = int(parts[2]) / 1000 if len(parts) > 2 else 1.5
        await asyncio.sleep(3)
        for i in range(count):
            for paused in (True, False):
                scanner.paused = paused
                scanner.update()
                await asyncio.sleep(gap)
            log("cycle", i=i + 1, detections=len(seen))
        log("cycles-done", count=count, detections=len(seen))


if __name__ == "__main__":
    ft.run(main)
