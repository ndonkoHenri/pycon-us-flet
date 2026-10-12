"""Entry point of the app: ``flet run`` and ``flet build`` start here.

``[tool.flet.app] path = "src"`` points both commands at this file. Until the
real entry point lands (P0-20: boot gate, stores and router), it shows a
placeholder so the toolchain can be exercised end to end.
"""

import flet as ft

import pycon_us
from pycon_us.theme import build_theme

# The display name stays a neutral placeholder until O-4 (D-36); it matches
# [tool.flet] product in pyproject.toml.
APP_NAME = "Conf Companion"


def main(page: ft.Page) -> None:
    """Show a placeholder screen with the app name and version in the app's theme."""
    page.title = APP_NAME
    # theme_mode stays SYSTEM: the OS appearance picks the scheme (Appearance is P2).
    page.theme = build_theme(dark=False, high_contrast=False)
    page.dark_theme = build_theme(dark=True, high_contrast=False)
    page.add(
        ft.SafeArea(
            content=ft.Column(
                [
                    ft.Text(APP_NAME, theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM),
                    ft.Text(
                        f"Version {pycon_us.__version__}",
                        theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
                    ),
                    ft.Text(
                        "Not an official PSF app.",
                        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    ),
                ]
            )
        )
    )


if __name__ == "__main__":
    ft.run(main)
