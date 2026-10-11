"""Entry point of the app: ``flet run`` and ``flet build`` start here.

``[tool.flet.app] path = "src"`` points both commands at this file. Until the
real entry point lands (P0-20: boot gate, stores and router), it shows a
placeholder so the toolchain can be exercised end to end.
"""

import flet as ft

import pycon_us


def main(page: ft.Page) -> None:
    """Show a placeholder screen with the app version."""
    page.title = "PyCon US"
    page.add(ft.SafeArea(content=ft.Text(f"PyCon US companion {pycon_us.__version__}")))


if __name__ == "__main__":
    ft.run(main)
