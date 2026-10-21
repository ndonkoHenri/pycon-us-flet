"""Check the spike's calendar file on the host before it goes to a device.

Run from any folder, e.g. ``uv run python check_ics.py`` here: it needs only the
standard library and ``src/``. It checks what a calendar needs from the file and
prints ``ok``; it is not a full RFC 5545 validator.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from ics_sample import ICS_BYTES  # the app's own folder, as in the build


def main() -> None:
    """Assert CRLF line ends, lines of at most 75 octets and balanced blocks."""
    text = ICS_BYTES.decode()
    assert text.endswith("\r\n"), "the file ends with CRLF"
    lines = text.split("\r\n")[:-1]
    assert all("\n" not in line for line in lines), "every line ends with CRLF"
    assert all(len(line.encode()) <= 75 for line in lines), "lines fold at 75 octets"
    for block in ("VCALENDAR", "VEVENT", "VALARM"):
        begins = lines.count(f"BEGIN:{block}")
        assert begins == lines.count(f"END:{block}"), f"{block} is balanced"
    assert lines.count("BEGIN:VEVENT") == 2, "two events"
    assert lines.count("BEGIN:VALARM") == 1, "one alarm"
    print("ok", len(ICS_BYTES), "bytes")


if __name__ == "__main__":
    main()
