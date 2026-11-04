"""Capture what Ionic's own `processData` makes of the recorded feeds (D-77; #66, SCHED-19).

Run it by hand, rarely: only when a recorded feed is added or the Ionic reference moves.
It needs Node and npm; CI and the tests never run it, they only read its output:

    uv run python tools/capture_ionic_reference/capture.py --ionic excluded/pycon-us-mobile

It copies Ionic's `conference-data.ts` and the files it imports for `processData`
unchanged from a clone of PyCon/pycon-us-mobile into the work directory, adds this
folder's stand-ins for Angular, RxJS, Ionic storage, `UserData` and the environment,
installs the exact `markdown-to-txt` and `marked` versions of Ionic's
`package-lock.json` there, bundles with a pinned esbuild, and runs `driver.ts` under
Node on each `tests/fixtures/feeds/conference-<year>.json`. The facts it prints go to
`tests/fixtures/ionic/<year>/*.json`, with their provenance in `summary.json`.
Nothing is installed into the repository.
"""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime, time
from pathlib import Path

from pycon_us.config import load_year

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
FEEDS = REPO / "tests" / "fixtures" / "feeds"
OUTPUT = REPO / "tests" / "fixtures" / "ionic"

ESBUILD = "0.28.2"
"""The esbuild release that bundles the copied TypeScript (any recent one would do)."""

IONIC_FILES = (
    "src/app/providers/conference-data.ts",
    "src/app/location-map/room-locations.ts",
    "src/app/location-map/venue-locations.ts",
    "tsconfig.json",
)
"""Ionic's files that `processData` needs, copied unchanged."""

STAND_INS = {
    "driver.ts": "driver.ts",
    "stubs.ts": "stubs.ts",
    "environment.ts": "src/environments/environment.ts",
    "user-data.ts": "src/app/providers/user-data.ts",
}
"""This folder's files, and where each goes in the work directory."""

STUBBED_PACKAGES = (
    "@angular/core",
    "@angular/common/http",
    "@ionic/angular",
    "@ionic/storage-angular",
    "rxjs",
    "rxjs/operators",
)
"""The packages `stubs.ts` stands in for; `processData` uses none of them."""

NPM_PACKAGES = (
    "markdown-to-txt",
    "marked",
    "lodash",
    "lodash.escape",
    "lodash.unescape",
)
"""The real code `processData` runs besides Ionic's own: its title cleaning.

`markdown-to-txt` 2.0.1 requires `lodash` without declaring it; Ionic's build finds
the copy its lock file hoists, so we install that one too.
"""


def main() -> None:
    """Capture the reference for every recorded feed and print where it went."""
    parser = argparse.ArgumentParser(description="Capture Ionic's processData output.")
    parser.add_argument(
        "--ionic",
        type=Path,
        default=REPO / "excluded" / "pycon-us-mobile",
        help="a clone of PyCon/pycon-us-mobile (default: excluded/pycon-us-mobile)",
    )
    parser.add_argument(
        "--work",
        type=Path,
        default=None,
        help="the directory to build in (default: a new temporary directory)",
    )
    args = parser.parse_args()
    ionic: Path = args.ionic.resolve()
    work = args.work or Path(tempfile.mkdtemp(prefix="ionic-ref-"))

    versions = prepare(ionic, work)
    provenance = {
        "ionic": "PyCon/pycon-us-mobile@" + ionic_commit(ionic),
        "node": command(["node", "--version"], work).strip(),
        "esbuild": ESBUILD,
        "npm": versions,
        "date": datetime.now(UTC).date().isoformat(),
    }
    for feed in sorted(FEEDS.glob("conference-*.json")):
        year = int(feed.stem.removeprefix("conference-"))
        written = capture(work, feed, year, provenance)
        print(f"{year}: {written.relative_to(REPO)}")


def prepare(ionic: Path, work: Path) -> dict[str, str]:
    """Lay out the work directory, install the npm packages and bundle the driver.

    Returns:
        The npm packages installed, by name, at the versions of Ionic's lock file.
    """
    for name in IONIC_FILES:
        copy(ionic / name, work / name)
    for name, target in STAND_INS.items():
        copy(HERE / name, work / target)

    lock = json.loads((ionic / "package-lock.json").read_text(encoding="utf-8"))
    versions = {
        name: lock["packages"][f"node_modules/{name}"]["version"]
        for name in NPM_PACKAGES
    }
    package = {"private": True, "dependencies": versions}
    (work / "package.json").write_text(json.dumps(package, indent=2), encoding="utf-8")
    command(["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund"], work)

    aliases = [f"--alias:{name}=./stubs.ts" for name in STUBBED_PACKAGES]
    command(
        [
            "npx",
            "--yes",
            f"esbuild@{ESBUILD}",
            "driver.ts",
            "--bundle",
            "--platform=node",
            "--format=cjs",
            "--outfile=bundle.js",
            "--log-level=warning",
            *aliases,
        ],
        work,
    )
    return versions


def capture(work: Path, feed: Path, year: int, provenance: dict[str, object]) -> Path:
    """Run Ionic's processing on one feed and write its facts.

    Ionic's environment names 2026's zone and UTC offset; each year runs with its own, as
    that year's build would have. The machine zone is UTC and the locale en-US, so the
    output does not depend on the machine.

    Returns:
        The folder the facts were written to.
    """
    conference = load_year(year).conference
    noon = datetime.combine(conference.first_day, time(12), tzinfo=conference.zone)
    offset = noon.utcoffset()
    assert offset is not None
    hours = int(offset.total_seconds() // 3600)
    env = {**os.environ, "TZ": "UTC", "LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"}
    output = command(
        ["node", "bundle.js", str(feed), conference.time_zone, str(hours)], work, env
    )
    facts = json.loads(output)
    environment = {"timezone": conference.time_zone, "utcOffset": hours}
    facts["summary"] = {
        "captured": {**provenance, "environment": environment},
        **facts["summary"],
    }

    folder = OUTPUT / str(year)
    folder.mkdir(parents=True, exist_ok=True)
    for name, value in facts.items():
        text = json.dumps(value, indent=1, ensure_ascii=False) + "\n"
        (folder / f"{name}.json").write_text(text, encoding="utf-8")
    return folder


def ionic_commit(ionic: Path) -> str:
    """The commit the clone has checked out, read from `.git` without running git."""
    git = ionic / ".git"
    head = (git / "HEAD").read_text(encoding="utf-8").strip()
    if not head.startswith("ref: "):
        return head
    ref = head.removeprefix("ref: ")
    if (git / ref).is_file():
        return (git / ref).read_text(encoding="utf-8").strip()
    for line in (git / "packed-refs").read_text(encoding="utf-8").splitlines():
        sha, _, name = line.partition(" ")
        if name == ref:
            return sha
    raise SystemExit(f"cannot find the commit of {ref} in {git}")


def copy(source: Path, target: Path) -> None:
    """Copy one file, making its folder."""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def command(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    """Run a command in `cwd` and return its output; stop with its errors if it fails."""
    result = subprocess.run(
        args, check=False, cwd=cwd, env=env, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise SystemExit(f"{' '.join(args[:3])} failed:\n{result.stderr}")
    return result.stdout


if __name__ == "__main__":
    main()
