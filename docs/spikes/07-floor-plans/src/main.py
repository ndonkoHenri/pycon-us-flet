"""#361 reproducer: a real floor plan with 61 booths in an `InteractiveViewer`.

Spike S7 (docs/spikes/07-floor-plans.md). Three tabs, Plain (a text list, the
memory baseline), Plan (the Concourse floor plan) and Expo (the 2026 expo hall
with its 61 booths from the Ionic app), each plan in
`InteractiveViewer(min_scale=1, max_scale=natural / displayed)`. The toolbar
switches what the spike compares:

- **Tabs:** `swipe` puts the panes in a `TabBarView`; `fixed` shows the
  selected pane alone under the `TabBar`.
- **Hotspots:** `containers` (one `Container` per booth in
  `Semantics(button=True)`), `gesture` (one `GestureDetector` over the plan,
  hit-tested here) or `none`.
- **Image:** `expo.webp` / `expo.jpg` (2048 px) or `expo-source.jpg` (4966 px);
  **Cache:** `Image.cache_width` off or 1080 px. **2x tap:** a double-tap
  `GestureDetector` around the viewer, on or off.
- **Cycle 20:** unmounts and mounts the Expo viewer 20 times.

The viewer's buttons zoom (about the top-left corner, F76), pan, reset and try the
three ways to bring a zoom back: `save_state`/`restore_state`, a transform
remembered from `on_transform_changed` and put back with `reset`, `zoom` and
`pan` (U3's interim), and `get_transform`. Every event prints an `S7` line
(logcat `flet.python`; the iOS unified log).
"""

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path

import flet as ft

HERE = Path(__file__).parent
BOOTHS = json.loads((HERE / "booths.json").read_text())
"""The 61 booths: id, name and the rectangle as ratios of the plan (x, y, w, h)."""

SIZES = {
    "expo.webp": (2048, 1448),
    "expo.jpg": (2048, 1448),
    "expo-source.jpg": (4966, 3511),
    "concourse.webp": (2048, 1583),
}
"""Each plan's natural size in pixels, as reencode.py wrote it."""

MEMORY: dict[str, tuple[float, float, float]] = {}
"""The last transform each viewer reported (scale, x, y): ViewMemory's stand-in (D-18)."""

AMBER = "#F2C14E"


def log(*parts: object) -> None:
    """Print one `S7` line with a monotonic timestamp in milliseconds."""
    print("S7", f"ms={time.monotonic() * 1000:.1f}", *parts, flush=True)


@dataclass(frozen=True)
class Options:
    """What the toolbar picked."""

    tabs: str = "fixed"
    hotspots: str = "containers"
    image: str = "expo.webp"
    cache: bool = False
    double_tap: bool = False


def booth_at(x: float, y: float, width: float, height: float) -> dict | None:
    """Return the booth under a point of the plan, or None.

    Args:
        x: The point's x in the plan's laid-out coordinates.
        y: The point's y.
        width: The plan's laid-out width.
        height: The plan's laid-out height.
    """
    u, v = x / width, y / height
    for booth in BOOTHS:
        if (
            booth["x"] <= u <= booth["x"] + booth["w"]
            and booth["y"] <= v <= booth["y"] + booth["h"]
        ):
            return booth
    return None


def fitted(box: tuple[float, float], natural: tuple[int, int]) -> tuple[float, float]:
    """Return the plan's size in the box with `BoxFit.CONTAIN`.

    Args:
        box: The viewer's size in logical pixels.
        natural: The image's size in pixels.
    """
    scale = min(box[0] / natural[0], box[1] / natural[1])
    return natural[0] * scale, natural[1] * scale


@ft.component
def Viewer(name: str, image: str, booths: bool, options: Options) -> ft.Control:
    """One plan in an `InteractiveViewer`, with its zoom buttons and hotspots.

    Args:
        name: The pane's name, in every log line and key.
        image: The asset under `plans/`.
        booths: Whether to draw the expo's booths.
        options: The toolbar's choices.
    """
    started = time.monotonic()
    box, set_box = ft.use_state((0.0, 0.0))
    selected, set_selected = ft.use_state("")
    viewer = ft.use_memo(ft.Ref[ft.InteractiveViewer], [])

    async def mounted() -> None:
        """Log how long the first render took, once."""
        log("mounted", name, f"render_ms={(time.monotonic() - started) * 1000:.1f}")

    ft.use_effect(mounted, [])

    def resized(e: ft.LayoutSizeChangeEvent) -> None:
        """Keep the viewer's size, which places the plan and its booths."""
        set_box((e.width, e.height))

    natural = SIZES[image]
    width, height = fitted(box, natural) if box[0] else (0.0, 0.0)
    max_scale = max(1.0, natural[0] / width) if width else 1.0

    def tapped(booth: dict, how: str) -> None:
        """Select a booth and log the tap."""
        log("tap", name, how, f"booth={booth['id']}")
        set_selected(booth["id"])

    def gesture_down(e: ft.TapEvent) -> None:
        """Log when the finger came down (for the double-tap delay)."""
        log("tap_down", name)

    def gesture_tap(e: ft.TapEvent) -> None:
        """Hit-test the tap against the booths in Python."""
        t0 = time.perf_counter()
        hit = booth_at(e.local_position.x, e.local_position.y, width, height)
        cost = (time.perf_counter() - t0) * 1000
        log(
            "hit",
            name,
            f"x={e.local_position.x:.1f} y={e.local_position.y:.1f}",
            f"test_ms={cost:.3f}",
        )
        if hit:
            tapped(hit, "gesture")
        else:
            set_selected("")

    def hotspot(booth: dict) -> ft.Control:
        """One booth as a positioned, outlined `Container` in `Semantics`."""
        is_selected = booth["id"] == selected
        return ft.Container(
            left=booth["x"] * width,
            top=booth["y"] * height,
            width=booth["w"] * width,
            height=booth["h"] * height,
            key=booth["id"],
            # content= by name: a positional ft.Semantics(x) sets tooltip (F130).
            content=ft.Semantics(
                content=ft.Container(
                    bgcolor=ft.Colors.with_opacity(0.6, AMBER) if is_selected else None,
                    border=ft.Border.all(
                        2 if is_selected else 1,
                        ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                    ),
                    on_click=lambda e, b=booth: tapped(b, "container"),
                ),
                button=True,
                label=f"Booth {booth['id']}, {booth['name']}",
                identifier=f"booth.{booth['id']}",
            ),
        )

    layers: list[ft.Control] = [
        ft.Image(
            src=f"plans/{image}",
            width=width,
            height=height,
            fit=ft.BoxFit.CONTAIN,
            cache_width=1080 if options.cache else None,
            semantics_label=f"{name} plan",
        )
    ]
    if booths and options.hotspots == "containers":
        layers += [hotspot(b) for b in BOOTHS]
    elif booths and options.hotspots == "gesture" and selected:
        booth = next(b for b in BOOTHS if b["id"] == selected)
        layers.append(
            ft.Container(
                left=booth["x"] * width,
                top=booth["y"] * height,
                width=booth["w"] * width,
                height=booth["h"] * height,
                bgcolor=ft.Colors.with_opacity(0.6, AMBER),
            )
        )
    plan: ft.Control = ft.Stack(layers, width=width, height=height)
    if booths and options.hotspots == "gesture":
        plan = ft.GestureDetector(
            content=plan, on_tap=gesture_tap, on_tap_down=gesture_down
        )

    def transformed(e: ft.InteractiveViewerTransformEvent) -> None:
        """Remember the transform the way ViewMemory would (D-18)."""
        MEMORY[name] = (e.scale, e.translation_x, e.translation_y)
        log(
            "transform",
            name,
            f"scale={e.scale:.3f} x={e.translation_x:.1f} y={e.translation_y:.1f}",
        )

    async def remember() -> None:
        """Read the transform and log it (MEMORY follows on_transform_changed only)."""
        t = await viewer.current.get_transform()
        log(
            "get_transform",
            name,
            f"scale={t.scale:.3f} x={t.translation_x:.1f} y={t.translation_y:.1f}",
        )

    async def act(action: str) -> None:
        """Run one viewer method and log the transform after it."""
        v = viewer.current
        if action == "in":
            await v.zoom(1.5)
        elif action == "max":
            await v.zoom(max_scale)
        elif action == "pan":
            await v.pan(-60, -40)
        elif action == "reset":
            await v.reset(animation_duration=ft.Duration(milliseconds=250))
            await asyncio.sleep(0.3)
        elif action == "save":
            await v.save_state()
        elif action == "restore":
            await v.restore_state()
        elif action == "recall" and name in MEMORY:
            scale, x, y = MEMORY[name]
            await v.reset()
            await v.zoom(scale)
            await v.pan(x / scale, y / scale)
        await remember()
        log("action", name, action, f"max_scale={max_scale:.2f}")

    def button(label: str, action: str) -> ft.Control:
        """A small button that runs one viewer action."""

        async def click(e: ft.Event) -> None:
            await act(action)

        return ft.TextButton(label, on_click=click, key=f"{name}.{action}")

    async def double_tapped(e: ft.Event) -> None:
        """Toggle between 1x and 2.5x, as ux.md §6.1 asks."""
        t = await viewer.current.get_transform()
        await (viewer.current.reset() if t.scale > 1.01 else viewer.current.zoom(2.5))
        await remember()

    zoom_layer: ft.Control = ft.InteractiveViewer(
        ref=viewer,
        min_scale=1,
        max_scale=max_scale,
        content=ft.Container(plan, alignment=ft.Alignment.CENTER),
        on_interaction_end=lambda e: log("interaction_end", name),
        on_transform_changed=transformed,
        expand=True,
    )
    if options.double_tap:
        zoom_layer = ft.GestureDetector(
            content=zoom_layer, on_double_tap=double_tapped, expand=True
        )
    return ft.Column(
        [
            ft.Container(
                zoom_layer,
                expand=True,
                on_size_change=resized,
                bgcolor=ft.Colors.SURFACE,
            ),
            ft.Row(
                [
                    button("In", "in"),
                    button("Max", "max"),
                    button("Pan", "pan"),
                    button("Reset", "reset"),
                    button("Save", "save"),
                    button("Restore", "restore"),
                    button("Recall", "recall"),
                ],
                wrap=True,
                spacing=0,
            ),
            ft.Text(
                f"{name}: {image} {natural[0]}x{natural[1]} max {max_scale:.2f}x booth {selected or '-'}"
            ),
        ],
        spacing=0,
        expand=True,
    )


@ft.component
def App() -> ft.Control:
    """The toolbar and the three panes."""
    options, set_options = ft.use_state(Options())
    tab, set_tab = ft.use_state(0)
    hidden, set_hidden = ft.use_state(False)

    def cycle(field: str, values: tuple) -> ft.Control:
        """A button that steps one option through its values."""
        value = getattr(options, field)

        def click(e: ft.Event) -> None:
            nxt = values[(values.index(value) + 1) % len(values)]
            log("option", field, nxt)
            set_options(Options(**{**options.__dict__, field: nxt}))

        return ft.OutlinedButton(f"{field}: {value}", on_click=click)

    async def cycles(e: ft.Event) -> None:
        """Unmount and mount the Expo viewer 20 times."""
        for i in range(20):
            set_hidden(True)
            await asyncio.sleep(0.5)
            set_hidden(False)
            await asyncio.sleep(1.5)
            log("cycle", i + 1)

    def changed(e: ft.Event[ft.Tabs]) -> None:
        """Follow the selected tab."""
        log("tab", e.control.selected_index)
        set_tab(e.control.selected_index)

    plain = ft.ListView(
        [ft.ListTile(title=ft.Text(f"Row {i}")) for i in range(40)], expand=True
    )
    # Keyed, so Plan and Expo in the one slot of the "fixed" body are two
    # components: unkeyed, Flet migrates one into the other, hook state and all.
    panes = [
        plain,
        Viewer("plan", "concourse.webp", False, options, key="plan"),
        ft.Text("Closed")
        if hidden
        else Viewer("expo", options.image, True, options, key="expo"),
    ]
    body = ft.TabBarView(panes, expand=True) if options.tabs == "swipe" else panes[tab]
    return ft.SafeArea(
        ft.Column(
            [
                ft.Row(
                    [
                        cycle("tabs", ("fixed", "swipe")),
                        cycle("hotspots", ("containers", "gesture", "none")),
                        cycle("image", ("expo.webp", "expo.jpg", "expo-source.jpg")),
                        cycle("cache", (False, True)),
                        cycle("double_tap", (False, True)),
                        ft.OutlinedButton("Cycle 20", on_click=cycles),
                    ],
                    wrap=True,
                    spacing=4,
                    run_spacing=0,
                ),
                ft.Tabs(
                    length=3,
                    selected_index=tab,
                    on_change=changed,
                    expand=True,
                    content=ft.Column(
                        [
                            ft.TabBar(
                                [
                                    ft.Tab(label="Plain"),
                                    ft.Tab(label="Plan"),
                                    ft.Tab(label="Expo"),
                                ]
                            ),
                            body,
                        ],
                        spacing=0,
                        expand=True,
                    ),
                ),
            ],
            spacing=0,
            expand=True,
        ),
        expand=True,
    )


def main(page: ft.Page) -> None:
    """Render the reproducer."""
    page.theme_mode = ft.ThemeMode.LIGHT
    log("start")
    page.render(App)


ft.run(main, assets_dir="assets")
