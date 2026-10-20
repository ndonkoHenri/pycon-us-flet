"""S8 throwaway extension: a barcode-scanner control (docs/spikes/08-scanner.md).

The API is the one docs/flet-gaps-and-extensions.md §4.2 proposes for E1,
reduced to what the spike exercises. It is not a package for the app.
"""

from dataclasses import dataclass, field
from enum import Enum

import flet as ft

__all__ = ["BarcodeFormat", "DetectEvent", "ErrorEvent", "S8Scanner"]


class BarcodeFormat(Enum):
    """Dart ``BarcodeFormat.name`` values; QR is all the app needs."""

    QR_CODE = "qrCode"
    ALL = "all"


@dataclass
class DetectEvent(ft.Event["S8Scanner"]):
    """One barcode the camera saw: its text and format."""

    raw_value: str | None = None
    format: str | None = None


@dataclass
class ErrorEvent(ft.Event["S8Scanner"]):
    """The camera could not start: ``code`` is the Dart ``MobileScannerErrorCode`` name."""

    code: str | None = None
    message: str | None = None


@ft.control("S8Scanner")
class S8Scanner(ft.LayoutControl):
    """A live camera preview that reports detected barcodes."""

    formats: list[BarcodeFormat] = field(
        default_factory=lambda: [BarcodeFormat.QR_CODE]
    )
    """The formats to look for."""

    paused: bool = False
    """True stops the camera and releases it; False starts it again."""

    torch: bool = False
    """Whether the torch is on, where the camera has one."""

    on_detect: ft.EventHandler[DetectEvent] | None = None
    """Called for each barcode in each analysed frame."""

    on_error: ft.EventHandler[ErrorEvent] | None = None
    """Called when the camera cannot start (permission denied, no camera)."""

    async def analyze_image(self, path: str) -> list[str]:
        """Decode the barcodes in an image file on the device.

        Args:
            path: An absolute path on the device.

        Returns:
            The raw values found, possibly none.
        """
        return await self._invoke_method("analyze_image", {"path": path})
