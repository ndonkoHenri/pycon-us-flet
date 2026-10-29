"""The scan screen's camera area (ux.md §7.2; E1, D-63).

The camera scanner is E1, absent at the Flet pin (``capabilities.SCANNER`` is False):
the area says so and manual entry is primary; #726 brings the preview here.
"""

import flet as ft

from pycon_us.theme import use_tokens
from pycon_us.theme_hc import hc_border

CAMERA_UNAVAILABLE = "Camera scanning isn't available in this build."


@ft.component
def CameraUnavailable() -> ft.Control:
    """Return the camera area's interim: the build has no camera scanner (E1, D-63)."""
    tokens = use_tokens()
    return ft.Container(
        ft.Row(
            [
                ft.Icon(
                    ft.Icons.NO_PHOTOGRAPHY_OUTLINED,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    apply_text_scaling=True,
                ),
                ft.Semantics(
                    identifier="scan.camera_unavailable",
                    container=True,
                    content=ft.Text(
                        CAMERA_UNAVAILABLE,
                        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    expand=True,
                ),
            ],
            spacing=12,
        ),
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        padding=16,
        border_radius=12,
        border=hc_border(tokens.high_contrast),
    )
