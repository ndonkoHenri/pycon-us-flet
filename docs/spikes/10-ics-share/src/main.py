"""#364 reproducer: hand a calendar file to the OS in every way the pinned Flet allows.

Spike P2-04 (docs/spikes/10-ics-share.md). One screen of buttons, each a route
from the app to the phone's calendar:

1. **Share file (bytes)**: D-62 as written, ``Share.share_files`` with
   ``ShareFile.from_bytes(..., mime_type="text/calendar", name=...)``.
2. **Share file (path)**: the same file written to the temporary directory first
   and shared with ``ShareFile.from_path``.
3. **Save to a folder**: ``FilePicker.save_file(src_bytes=...)``, the platform's
   save dialog (Android's Downloads, iOS's Files).
4. **Open file URL**: the file written to the documents directory and opened
   with ``UrlLauncher.launch_url("file://...")``.
5. **Open data URL**: ``UrlLauncher.launch_url("data:text/calendar;base64,...")``.
6. **Serve, in-app browser**: the file served by the app itself on
   ``http://127.0.0.1:<port>/`` as ``text/calendar`` and opened in the in-app
   browser (``LaunchMode.IN_APP_BROWSER_VIEW``: SFSafariViewController on iOS,
   a Custom Tab on Android), where the app stays in front and keeps serving.
7. **Serve, browser**: the same URL in the external browser.

Every result prints a line starting with ``ICS `` (logcat tag ``flet.python``
on Android, the unified log on iOS) and shows under the buttons.
"""

import base64
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import flet as ft
from ics_sample import FILE_NAME, ICS_BYTES, MIME_TYPE

ERRORS = (TimeoutError, RuntimeError, OSError, ValueError)
"""What a call to the Flutter side raises (a timeout, a platform error), a file write
(``OSError``) or a bad argument (``ValueError``): each is reported, never raised."""


class IcsHandler(BaseHTTPRequestHandler):
    """Answer every GET with the calendar file, as a web server would."""

    def do_GET(self) -> None:
        """Send the file with its calendar media type."""
        self.send_response(200)
        self.send_header("Content-Type", f"{MIME_TYPE}; charset=utf-8")
        self.send_header("Content-Disposition", f'inline; filename="{FILE_NAME}"')
        self.send_header("Content-Length", str(len(ICS_BYTES)))
        self.end_headers()
        self.wfile.write(ICS_BYTES)

    def log_message(self, format: str, *args: object) -> None:
        """Print each request as an ``ICS`` line."""
        print("ICS served", format % args, flush=True)


SERVER: list[ThreadingHTTPServer] = []


def served_url() -> str:
    """Start the local server once and return the file's URL on it."""
    if not SERVER:
        server = ThreadingHTTPServer(("127.0.0.1", 0), IcsHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        SERVER.append(server)
    return f"http://127.0.0.1:{SERVER[0].server_address[1]}/{FILE_NAME}"


def main(page: ft.Page) -> None:
    """Build the one screen of the spike.

    Args:
        page: The session's page.
    """
    page.title = "ICS spike"
    share = ft.Share()
    launcher = ft.UrlLauncher()
    picker = ft.FilePicker()
    paths = ft.StoragePaths()
    results = ft.Column(spacing=4)

    def report(step: str, outcome: object) -> None:
        """Print one ``ICS`` line and show it on the screen."""
        line = f"ICS {step}: {outcome}"
        print(line, flush=True)
        results.controls.insert(0, ft.Text(line, selectable=True))
        page.update()

    def origin() -> ft.Offset | None:
        """Return the window's centre, where the sheet points from on a tablet."""
        if not page.width or not page.height:
            return None
        return ft.Offset(page.width / 2, page.height / 2)

    def write(directory: str) -> str:
        """Write the file into ``directory`` and return its path."""
        path = Path(directory, FILE_NAME)
        path.write_bytes(ICS_BYTES)
        return str(path)

    async def share_bytes(_: ft.Event[ft.Button]) -> None:
        """Share the file from memory, as D-62 prescribes."""
        try:
            result = await share.share_files(
                [
                    ft.ShareFile.from_bytes(
                        ICS_BYTES, mime_type=MIME_TYPE, name=FILE_NAME
                    )
                ],
                share_position_origin=origin(),
            )
            report("share bytes", f"{result.status.name} raw={result.raw!r}")
        except ERRORS as error:
            report("share bytes", f"error {type(error).__name__}: {error}")

    async def share_path(_: ft.Event[ft.Button]) -> None:
        """Share the file from a path in the temporary directory."""
        try:
            path = write(await paths.get_temporary_directory())
            result = await share.share_files(
                [ft.ShareFile.from_path(path, name=FILE_NAME)],
                share_position_origin=origin(),
            )
            report("share path", f"{result.status.name} raw={result.raw!r}")
        except ERRORS as error:
            report("share path", f"error {type(error).__name__}: {error}")

    async def save(_: ft.Event[ft.Button]) -> None:
        """Save the file through the platform's save dialog."""
        try:
            saved = await picker.save_file(
                dialog_title="Save the calendar file",
                file_name=FILE_NAME,
                src_bytes=ICS_BYTES,
            )
            report("save", saved)
        except ERRORS as error:
            report("save", f"error {type(error).__name__}: {error}")

    async def open_file_url(_: ft.Event[ft.Button]) -> None:
        """Open the file from the documents directory through a file URL."""
        try:
            path = write(await paths.get_application_documents_directory())
            url = f"file://{path}"
            can = await launcher.can_launch_url(url)
            await launcher.launch_url(url, mode=ft.LaunchMode.EXTERNAL_APPLICATION)
            report("file url", f"can_launch={can} launched")
        except ERRORS as error:
            report("file url", f"error {type(error).__name__}: {error}")

    async def open_data_url(_: ft.Event[ft.Button]) -> None:
        """Open the file as a data URL."""
        url = f"data:{MIME_TYPE};base64,{base64.b64encode(ICS_BYTES).decode()}"
        try:
            can = await launcher.can_launch_url(url)
            await launcher.launch_url(url, mode=ft.LaunchMode.EXTERNAL_APPLICATION)
            report("data url", f"can_launch={can} launched")
        except ERRORS as error:
            report("data url", f"error {type(error).__name__}: {error}")

    async def open_served(mode: ft.LaunchMode, step: str) -> None:
        """Open the served file's URL in ``mode``."""
        try:
            url = served_url()
            await launcher.launch_url(url, mode=mode)
            report(step, f"launched {url}")
        except ERRORS as error:
            report(step, f"error {type(error).__name__}: {error}")

    async def serve_in_app(_: ft.Event[ft.Button]) -> None:
        """Open the served file in the in-app browser."""
        await open_served(ft.LaunchMode.IN_APP_BROWSER_VIEW, "serve in-app")

    async def serve_external(_: ft.Event[ft.Button]) -> None:
        """Open the served file in the external browser."""
        await open_served(ft.LaunchMode.EXTERNAL_APPLICATION, "serve browser")

    page.add(
        ft.SafeArea(
            ft.Column(
                [
                    ft.Text(
                        "ICS spike (#364)", theme_style=ft.TextThemeStyle.TITLE_LARGE
                    ),
                    ft.Text(
                        f"{FILE_NAME}: {len(ICS_BYTES)} bytes, two events, one alarm"
                    ),
                    ft.FilledButton("Share file (bytes)", on_click=share_bytes),
                    ft.FilledButton("Share file (path)", on_click=share_path),
                    ft.FilledButton("Save to a folder", on_click=save),
                    ft.FilledButton("Open file URL", on_click=open_file_url),
                    ft.FilledButton("Open data URL", on_click=open_data_url),
                    ft.FilledButton("Serve, in-app browser", on_click=serve_in_app),
                    ft.FilledButton("Serve, browser", on_click=serve_external),
                    results,
                ],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            expand=True,
        )
    )


ft.run(main)
