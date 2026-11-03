"""The scan screen's camera note (ux.md §7.2; E1, D-63).

The camera scanner is E1, absent at the Flet pin (``capabilities.SCANNER`` is False):
the screen says so in one quiet line that also says how to go on, and manual entry is
primary; #726 brings the preview here.
"""

import flet as ft

CAMERA_UNAVAILABLE = (
    "This app can't scan with the camera yet. "
    "Type the badge code, or use a Bluetooth or USB scanner."
)


@ft.component
def CameraUnavailable() -> ft.Control:
    """Return the camera note: no camera scanner yet, and what to do instead (E1, D-63).

    A line of ``on_surface_variant`` text with a small icon, with no card of its own: the
    result panel under it is the screen's first thing, and a second grey box above it
    pushed the result and the field down at every text size (#1013). It says what is
    missing and how to proceed, never a build's excuse.
    """
    return ft.Container(
        ft.Row(
            [
                ft.Icon(
                    ft.Icons.NO_PHOTOGRAPHY_OUTLINED,
                    size=20,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    apply_text_scaling=True,
                ),
                ft.Semantics(
                    identifier="scan.camera_unavailable",
                    container=True,
                    content=ft.Text(
                        CAMERA_UNAVAILABLE,
                        theme_style=ft.TextThemeStyle.BODY_SMALL,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    expand=True,
                ),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        padding=ft.Padding.symmetric(vertical=4),
    )
