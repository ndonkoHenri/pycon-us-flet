"""S3 render check: the converted feed samples in `ft.Markdown` on a phone.

Spike S3 (docs/spikes/03-html-markdown.md). `census.py` writes `samples.json`
next to this file; the stub shows one sample at a time with the options the app
would use (`selectable=True`, `GITHUB_WEB`, `on_tap_link`). The AppBar steps
through the samples, toggles a proposed style sheet against Flet's default, and
shows the Markdown source. A tapped link is shown in a SnackBar, never opened.
"""

import json
from pathlib import Path

import flet as ft

SAMPLES = json.loads((Path(__file__).parent / "samples.json").read_text())


def proposed_style() -> ft.MarkdownStyleSheet:
    """The style sheet S3 proposes: underlined links in the primary colour, smaller headings.

    A style given here replaces the theme's instead of merging with it, so every
    text style names its colour (without one, text is black in dark mode).
    """
    text = ft.Colors.ON_SURFACE
    heading = ft.FontWeight.W_500
    return ft.MarkdownStyleSheet(
        a_text_style=ft.TextStyle(
            color=ft.Colors.PRIMARY, decoration=ft.TextDecoration.UNDERLINE
        ),
        p_text_style=ft.TextStyle(size=16, height=1.5, color=text),
        h1_text_style=ft.TextStyle(size=22, weight=heading, color=text),
        h2_text_style=ft.TextStyle(size=18, weight=heading, color=text),
        h3_text_style=ft.TextStyle(size=16, weight=heading, color=text),
        h4_text_style=ft.TextStyle(size=16, weight=heading, color=text),
        list_bullet_text_style=ft.TextStyle(size=16, height=1.5, color=text),
        blockquote_text_style=ft.TextStyle(size=16, height=1.5, color=text),
        blockquote_decoration=ft.BoxDecoration(
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border=ft.Border(left=ft.BorderSide(4, ft.Colors.OUTLINE)),
        ),
        code_text_style=ft.TextStyle(
            font_family="monospace",
            size=14,
            color=text,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        ),
        block_spacing=12,
    )


def main(page: ft.Page) -> None:
    """Show one sample at a time."""
    state = {"index": 0, "styled": False, "source": False}
    title = ft.Text()
    caption = ft.Text(theme_style=ft.TextThemeStyle.LABEL_MEDIUM, selectable=True)
    body = ft.Column()

    def on_tap_link(e: ft.Event[ft.Markdown]) -> None:
        print(f"S3 link {e.data}", flush=True)
        page.show_dialog(ft.SnackBar(ft.Text(f"Link: {e.data}"), persist=False))

    def show() -> None:
        sample = SAMPLES[state["index"]]
        title.value = (
            f"{state['index'] + 1}/{len(SAMPLES)}{' styled' if state['styled'] else ''}"
        )
        caption.value = f"{sample['year']} {sample['field']} · {sample['why']}"
        if state["source"]:
            content: ft.Control = ft.Text(
                sample["markdown"], font_family="monospace", size=12, selectable=True
            )
        else:
            content = ft.Markdown(
                sample["markdown"],
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                on_tap_link=on_tap_link,
                md_style_sheet=proposed_style() if state["styled"] else None,
            )
        body.controls = [caption, ft.Divider(), content]
        print(
            f"S3 show {state['index'] + 1} styled={state['styled']} source={state['source']}",
            flush=True,
        )
        page.update()

    def step(delta: int) -> None:
        state["index"] = (state["index"] + delta) % len(SAMPLES)
        show()

    def toggle(key: str) -> None:
        state[key] = not state[key]
        show()

    page.appbar = ft.AppBar(
        title=title,
        actions=[
            ft.IconButton(
                ft.Icons.CHEVRON_LEFT, tooltip="Previous", on_click=lambda _: step(-1)
            ),
            ft.IconButton(
                ft.Icons.CHEVRON_RIGHT, tooltip="Next", on_click=lambda _: step(1)
            ),
            ft.IconButton(
                ft.Icons.PALETTE_OUTLINED,
                tooltip="Style",
                on_click=lambda _: toggle("styled"),
            ),
            ft.IconButton(
                ft.Icons.CODE, tooltip="Source", on_click=lambda _: toggle("source")
            ),
        ],
    )
    page.scroll = ft.ScrollMode.AUTO
    page.padding = 16
    page.add(ft.SafeArea(body))
    show()


ft.run(main)
