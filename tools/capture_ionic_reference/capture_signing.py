"""Capture request-signing vectors from Ionic's own `buildRequestAuthHeaders` (D-52; #662).

Run it by hand, rarely: only when the Ionic reference moves or a case is added.
It needs Node and npm; CI and the tests never run it, they only read its output:

    uv run python tools/capture_ionic_reference/capture_signing.py --ionic excluded/pycon-us-mobile

It copies Ionic's `pycon-api.ts` unchanged into a work directory, with the stand-ins
`capture.py` uses for Angular, RxJS, Ionic storage, Capacitor, `UserData` and the
environment, installs the `sha1-uint8array` version of Ionic's `package-lock.json`
there, bundles `signing_driver.ts` with the pinned esbuild and runs it under Node. The
cases and the headers Ionic computed for them go to `tests/fixtures/ionic/signing.json`,
with their provenance. Nothing is installed into the repository.
"""

import argparse
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from capture import ESBUILD, HERE, OUTPUT, REPO, command, copy, ionic_commit

IONIC_FILES = ("src/app/providers/pycon-api.ts", "tsconfig.json")
"""Ionic's files that `buildRequestAuthHeaders` needs, copied unchanged."""

STAND_INS = {
    "signing_driver.ts": "signing_driver.ts",
    "stubs.ts": "stubs.ts",
    "environment.ts": "src/environments/environment.ts",
    "user-data.ts": "src/app/providers/user-data.ts",
}
"""This folder's files, and where each goes in the work directory."""

STUBBED_PACKAGES = (
    "@angular/core",
    "@angular/common/http",
    "@ionic/storage-angular",
    "@capacitor/network",
    "rxjs",
    "rxjs/operators",
)
"""The packages `stubs.ts` stands in for; `buildRequestAuthHeaders` uses none of them."""

HASH_PACKAGE = "sha1-uint8array"
"""The one third-party code the signature runs through: Ionic's SHA-1."""


def main() -> None:
    """Capture the signing vectors and print where they went."""
    parser = argparse.ArgumentParser(description="Capture Ionic's request signatures.")
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
    work = args.work or Path(tempfile.mkdtemp(prefix="ionic-signing-"))

    version = prepare(ionic, work)
    captured = {
        "ionic": "PyCon/pycon-us-mobile@" + ionic_commit(ionic),
        "node": command(["node", "--version"], work).strip(),
        "npm": command(["npm", "--version"], work).strip(),
        "esbuild": ESBUILD,
        "packages": {HASH_PACKAGE: version},
        "date": datetime.now(UTC).date().isoformat(),
    }
    cases = json.loads(command(["node", "signing.js"], work))
    target = OUTPUT / "signing.json"
    text = json.dumps(
        {"captured": captured, "cases": cases}, indent=1, ensure_ascii=False
    )
    target.write_text(text + "\n", encoding="utf-8")
    print(target.relative_to(REPO))


def prepare(ionic: Path, work: Path) -> str:
    """Lay out the work directory, install Ionic's SHA-1 package and bundle the driver.

    Returns:
        The `sha1-uint8array` version installed: the one Ionic's lock file resolves.
    """
    for name in IONIC_FILES:
        copy(ionic / name, work / name)
    for name, target in STAND_INS.items():
        copy(HERE / name, work / target)

    lock = json.loads((ionic / "package-lock.json").read_text(encoding="utf-8"))
    version = lock["packages"][f"node_modules/{HASH_PACKAGE}"]["version"]
    package = {"private": True, "dependencies": {HASH_PACKAGE: version}}
    (work / "package.json").write_text(json.dumps(package, indent=2), encoding="utf-8")
    command(["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund"], work)

    aliases = [f"--alias:{name}=./stubs.ts" for name in STUBBED_PACKAGES]
    command(
        [
            "npx",
            "--yes",
            f"esbuild@{ESBUILD}",
            "signing_driver.ts",
            "--bundle",
            "--platform=node",
            "--format=cjs",
            "--outfile=signing.js",
            "--log-level=warning",
            *aliases,
        ],
        work,
    )
    return version


if __name__ == "__main__":
    main()
