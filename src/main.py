"""Entry point of the app: ``flet run`` and ``flet build`` start here.

``[tool.flet.app] path = "src"`` points both commands at this file. Until the
real entry point lands (P0-20: boot gate, stores and router), it shows a
placeholder so the toolchain can be exercised end to end.
"""

import flet as ft

import pycon_us

# The display name stays a neutral placeholder until O-4 (D-36); it matches
# [tool.flet] product in pyproject.toml.
APP_NAME = "Conf Companion"

# The bundled font package (D-105). flet run has no such package and falls back
# to the system font (D-26).
ROBOTO = "packages/roboto_fonts/Roboto"


def main(page: ft.Page) -> None:
    """Show a placeholder screen with the app name and version in Roboto."""
    page.title = APP_NAME
    page.theme = ft.Theme(font_family=ROBOTO)
    page.dark_theme = ft.Theme(font_family=ROBOTO)
    page.add(
        ft.SafeArea(
            content=ft.Column(
                [
                    ft.Text(APP_NAME, theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM),
                    ft.Text(
                        f"Version {pycon_us.__version__}",
                        theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
                    ),
                    ft.Text("Not an official PSF app."),
                ]
            )
        )
    )


if __name__ == "__main__":
    ft.run(main)
