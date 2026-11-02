"""Add to calendar: an ``.ics`` file handed to the phone's calendar (D-272; SESS-04, SESS-05).

``add_to_calendar()`` is the one route, for one session (session detail, #425) or the
whole of My schedule (#426). No calendar takes a shared ``.ics`` on either platform
(P2-04), so each platform gets the path that reaches its calendar:

- **iOS:** the file is served on the loopback (``LoopbackFile``, started per tap) and
  opened in the in-app browser, whose ``text/calendar`` response iOS hands to its own
  "Add All" sheet, alarm included. ``launch_url`` raises although the sheet showed
  (F91), so the server's answered GET is the success; the server stops once the call
  returns or raises, ``SERVE_SECONDS`` at most. Never ``EXTERNAL_APPLICATION``: it
  opens Calendar's "Add Subscription Calendar" for a URL that stops answering.
- **Android** (and a desktop window, a developer host only): the system save dialog
  (``FilePicker.save_file``), then a SnackBar that says to open the file from the
  Files app, where Google Calendar imports it, without the alarm (U71 makes it one
  tap). The user picks the folder and the result is opaque, so no folder is named;
  a cancel says nothing.

Every outcome is said in place, on the View the user is on (D-210), so the function
returns nothing, as ``ui.links.open_link()`` and ``ui.share.share_text()`` do. A failure
is logged by the error's class only (D-72).
"""

import asyncio
import logging
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast
from urllib.parse import quote

import flet as ft

from pycon_us.services import Services
from pycon_us.services.errors import say
from pycon_us.services.storage import SERVICE_ERRORS

logger = logging.getLogger(__name__)

SERVE_SECONDS = 60.0
"""The longest the loopback server answers for one tap (D-272)."""

NOT_OPENED = "Couldn't open the calendar file"
"""What a SnackBar says when the file reached neither the calendar nor a folder."""

CONTENT_TYPE = "text/calendar; charset=utf-8"
"""The served file's type: what makes iOS hand it to its calendar sheet."""


def saved_text(name: str) -> str:
    """Return what Android's SnackBar says once the file is saved (D-272).

    It names no folder: the user picked it, and the platform does not say which. It
    promises no alarm: Google Calendar's import drops it.

    Args:
        name: The file's name as the app offered it, e.g. ``python-for-humans.ics``.
    """
    return f"Saved {name}. Open it from the Files app to add it to your calendar."


async def add_to_calendar(svc: Services, slug: str, data: bytes) -> None:
    """Hand an ``.ics`` file to the calendar by the platform's path; call it from a handler.

    Args:
        svc: The session's services: the launcher (iOS) and the file picker (Android).
        slug: The file's name without ``.ics``: letters, digits and ``-`` only.
        data: The file, from ``core.ics.calendar_file()``.
    """
    page = ft.context.page
    name = f"{slug}.ics"
    if page.platform == ft.PagePlatform.IOS:
        if not await _open_in_browser(svc, name, data):
            say(page, NOT_OPENED)
        return
    try:
        saved = await svc.file_picker.save_file(file_name=name, src_bytes=data)
    except SERVICE_ERRORS as error:
        logger.warning("Could not save the calendar file: %s", type(error).__name__)
        say(page, NOT_OPENED)
        return
    if saved is not None:  # None is a cancel, which needs no answer
        say(page, saved_text(name))


async def _open_in_browser(svc: Services, name: str, data: bytes) -> bool:
    """Serve the file on the loopback and open it in the in-app browser (iOS).

    Returns:
        Whether the browser fetched the file: iOS's sheet then showed (F91).
    """
    try:
        served = LoopbackFile(name, data)
    except OSError as error:  # no port to listen on
        logger.warning("Could not serve the calendar file: %s", type(error).__name__)
        return False
    try:
        await asyncio.wait_for(
            svc.launcher.launch_url(served.url, mode=ft.LaunchMode.IN_APP_BROWSER_VIEW),
            SERVE_SECONDS,
        )
    except SERVICE_ERRORS as error:
        # Raised after a load that showed the sheet too (F91): the GET decides below.
        logger.info("The calendar file's launch reported %s", type(error).__name__)
    finally:
        await asyncio.to_thread(served.close)  # waits up to half a second (D-272)
    return served.fetched.is_set()


class LoopbackFile:
    """One file served on ``127.0.0.1`` for one tap, at ``url``, until ``close()``.

    A ``ThreadingHTTPServer`` on a free port, answering on a daemon thread of its own:
    the file at its path with ``CONTENT_TYPE``, and 404 to anything else, such as a
    browser's icon. Each request is logged with its method, path and status, so a
    device's log shows what the browser and the calendar sheet asked for (D-272). Its
    threads write no store (D-70): ``fetched`` is a ``threading.Event``, read by the
    event loop once the launch is over.

    Attributes:
        url: Where the file is served: ``http://127.0.0.1:<port>/<name>``.
        fetched: Set once a GET of the file has been answered in full.
    """

    def __init__(self, name: str, data: bytes) -> None:
        """Start serving ``data`` as ``name``.

        Args:
            name: The file's name, e.g. ``python-for-humans.ics``.
            data: The file's bytes.

        Raises:
            OSError: No port could be bound on the loopback.
        """
        self.fetched = threading.Event()
        self._server = _Server(f"/{quote(name)}", name, data, self.fetched)
        port = self._server.server_address[1]
        self.url = f"http://127.0.0.1:{port}{self._server.file_path}"
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="calendar-file", daemon=True
        )
        self._thread.start()

    def close(self) -> None:
        """Stop answering and free the port; it blocks, so run it off the event loop.

        ``shutdown()`` waits for ``serve_forever``'s next poll, up to half a second.
        """
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()


class _Server(ThreadingHTTPServer):
    """The loopback server of one ``LoopbackFile``: what it serves, and its ``fetched``."""

    daemon_threads = True  # a request still open never holds the app's exit

    def __init__(
        self, file_path: str, name: str, data: bytes, fetched: threading.Event
    ) -> None:
        """Bind a free port on ``127.0.0.1``; ``serve_forever()`` starts answering."""
        super().__init__(("127.0.0.1", 0), _Handler)
        self.file_path = file_path
        self.name = name
        self.data = data
        self.fetched = fetched


class _Handler(BaseHTTPRequestHandler):
    """Answers one request: the file at its path, 404 to anything else."""

    @property
    def _file(self) -> _Server:
        """The server that took the request, with the file it serves."""
        return cast(_Server, self.server)

    def do_GET(self) -> None:
        """Send the file, then mark it fetched; any other path is not found."""
        if self._send_headers():
            self.wfile.write(self._file.data)
            self._file.fetched.set()

    def do_HEAD(self) -> None:
        """Send the file's headers only; a HEAD does not count as fetched."""
        self._send_headers()

    def _send_headers(self) -> bool:
        """Send the file's status and headers, or a 404; return whether it was the file."""
        if self.path != self._file.file_path:
            self.send_error(HTTPStatus.NOT_FOUND)
            return False
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", CONTENT_TYPE)
        self.send_header("Content-Disposition", f'inline; filename="{self._file.name}"')
        self.send_header("Content-Length", str(len(self._file.data)))
        self.end_headers()
        return True

    def log_message(self, format: str, *args: object) -> None:
        """Log the request line and status through ``logging``, not ``stderr``."""
        logger.info("Calendar file server: %s", format % args)
