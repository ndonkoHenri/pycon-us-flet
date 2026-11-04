"""Print Android's accessibility tree, headings included, for the screen on an emulator (#257).

`uiautomator dump` has no heading attribute, so it cannot show what TalkBack's Headings
navigation moves by (D-211). This tool builds a small instrumentation APK
(`tools/a11y_tree_apk`) with the Android SDK, installs it on the emulator you name, and
runs it: it walks the active window through `UiAutomation` and returns
`uiautomator dump`'s attributes plus `heading`, `accessibility-focused`,
`state-description` and `hint`. TalkBack can stay on while it runs.

From the repo root, with the app open on your own emulator (never another agent's):

    uv run python -m tools.a11y_tree --serial emulator-5578              # the whole tree
    uv run python -m tools.a11y_tree --serial emulator-5578 --headings   # headings only
    uv run python -m tools.a11y_tree --serial emulator-5578 --route /more --xml > more.xml

`--route` opens that route first through the app's deep link (D-269). The APK is signed
with a throwaway key generated in `build/a11y_tree` (git-ignored, D-86). Like
`uiautomator dump`, connecting makes Flutter report a screen reader (F72).
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools" / "a11y_tree_apk"
BUILD = ROOT / "build" / "a11y_tree"
PACKAGE = "io.github.ndonkohenri.a11ytree"
RUNNER = f"{PACKAGE}/.A11yTree"
RESULT = "INSTRUMENTATION_RESULT: "


class DumpError(RuntimeError):
    """The instrumentation ran but returned no tree."""


# ------------------------------------------------------------------ the tree


@dataclass(frozen=True)
class A11yNode:
    """One node of the dump, with the attributes the screen-reader checks read."""

    depth: int
    cls: str
    ident: str
    text: str
    desc: str
    state: str
    hint: str
    heading: bool
    flags: tuple[str, ...]
    bounds: str

    @property
    def label(self) -> str:
        """What TalkBack reads as the name: the content description, else the text."""
        return self.desc or self.text


FLAGS = (
    "clickable",
    "long-clickable",
    "focusable",
    "scrollable",
    "checkable",
    "checked",
    "selected",
    "focused",
    "accessibility-focused",
)
"""The `true` attributes a line lists, in this order; `disabled` and `offscreen` follow."""


def parse(xml: str) -> list[A11yNode]:
    """Read a dump (the tool's, or `uiautomator dump`'s) into its nodes, in document order."""
    nodes: list[A11yNode] = []

    def walk(element: ET.Element, depth: int) -> None:
        a = element.attrib
        flags = [name for name in FLAGS if a.get(name) == "true"]
        if a.get("enabled") == "false":
            flags.append("disabled")
        if a.get("visible-to-user") == "false":
            flags.append("offscreen")
        nodes.append(
            A11yNode(
                depth=depth,
                cls=a.get("class", ""),
                ident=a.get("resource-id", ""),
                text=a.get("text", ""),
                desc=a.get("content-desc", ""),
                state=a.get("state-description", ""),
                hint=a.get("hint", ""),
                heading=a.get("heading") == "true",
                flags=tuple(flags),
                bounds=a.get("bounds", ""),
            )
        )
        for child in element.findall("node"):
            walk(child, depth + 1)

    for top in ET.fromstring(xml).findall("node"):
        walk(top, 0)
    return nodes


def _quote(value: str) -> str:
    """`value` in double quotes, each newline written as a backslash and `n`, so a node stays on one line."""
    return '"' + value.replace("\n", "\\n") + '"'


def describe(node: A11yNode, bounds: bool = False) -> str:
    """One line for `node`: class, `HEADING`, `#identifier`, label, then its states."""
    parts = [node.cls.rsplit(".", 1)[-1] or "?"]
    if node.heading:
        parts.append("HEADING")
    if node.ident:
        parts.append("#" + node.ident)
    if node.label:
        parts.append(_quote(node.label))
    if node.desc and node.text and node.text != node.desc:
        parts.append("text=" + _quote(node.text))
    if node.state:
        parts.append("state=" + _quote(node.state))
    if node.hint:
        parts.append("hint=" + _quote(node.hint))
    if node.flags:
        parts.append("[" + ", ".join(node.flags) + "]")
    if bounds and node.bounds:
        parts.append(node.bounds)
    return " ".join(parts)


def render(nodes: list[A11yNode], headings: bool = False, bounds: bool = False) -> str:
    """The tree, indented two spaces a level; `headings` lists the heading nodes alone, flat."""
    if headings:
        return "\n".join(describe(n, bounds) for n in nodes if n.heading)
    return "\n".join("  " * n.depth + describe(n, bounds) for n in nodes)


def result_xml(output: str) -> str:
    """The XML from `am instrument -w -r`'s output; raises `DumpError` when it has none."""
    error = ""
    for line in output.splitlines():
        if line.startswith(RESULT + "xml="):
            return line.removeprefix(RESULT + "xml=")
        if line.startswith(RESULT + "error="):
            error = line.removeprefix(RESULT + "error=")
    raise DumpError(error or output.strip() or "am instrument printed nothing")


def deep_link(route: str) -> str:
    """The app's link to `route` (`/more`), from `[tool.flet.deep_linking]` (D-269)."""
    with (ROOT / "pyproject.toml").open("rb") as file:
        linking = tomllib.load(file)["tool"]["flet"]["deep_linking"]
    return f"{linking['scheme']}://{linking['host']}/{route.lstrip('/')}"


# ------------------------------------------------------------------ the APK


def _sdk() -> Path:
    """The Android SDK: `ANDROID_HOME`, `ANDROID_SDK_ROOT`, else Android Studio's default."""
    for name in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(name):
            return Path(os.environ[name])
    return Path.home() / "Library" / "Android" / "sdk"


def _newest(folder: Path) -> Path:
    """The subfolder of `folder` with the highest version (`36.0.0`, `android-36`)."""
    versions = [p for p in folder.iterdir() if p.name.rsplit("-", 1)[-1][:1].isdigit()]
    if not versions:
        raise FileNotFoundError(f"nothing installed in {folder}")
    return max(
        versions,
        key=lambda p: tuple(int(x) for x in p.name.rsplit("-", 1)[-1].split(".")),
    )


def _run(*args: str | Path) -> str:
    """Run a build or adb command, failing on a non-zero exit; return its standard output."""
    result = subprocess.run(
        [str(a) for a in args], check=False, capture_output=True, text=True, timeout=300
    )
    if result.returncode:
        raise RuntimeError(
            f"{' '.join(map(str, args))} failed:\n{result.stderr or result.stdout}"
        )
    return result.stdout


def build() -> Path:
    """Build and sign the APK in `build/a11y_tree`, unless it is newer than its sources."""
    apk = BUILD / "a11y-tree.apk"
    sources = [SOURCE / "A11yTree.java", SOURCE / "AndroidManifest.xml"]
    if apk.exists() and apk.stat().st_mtime > max(s.stat().st_mtime for s in sources):
        return apk
    sdk = _sdk()
    tools = _newest(sdk / "build-tools")
    android_jar = _newest(sdk / "platforms") / "android.jar"
    shutil.rmtree(BUILD / "classes", ignore_errors=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    _run(
        "javac",
        "--release",
        "11",
        "-classpath",
        android_jar,
        "-d",
        BUILD / "classes",
        sources[0],
    )
    classes = sorted((BUILD / "classes").rglob("*.class"))
    _run(
        tools / "d8",
        "--release",
        "--min-api",
        "30",
        "--lib",
        android_jar,
        "--output",
        BUILD,
        *classes,
    )
    unsigned = BUILD / "unsigned.apk"
    _run(
        tools / "aapt2",
        "link",
        "-o",
        unsigned,
        "--manifest",
        sources[1],
        "-I",
        android_jar,
    )
    with zipfile.ZipFile(unsigned, "a") as zf:
        zf.write(BUILD / "classes.dex", "classes.dex")
    aligned = BUILD / "aligned.apk"
    _run(tools / "zipalign", "-f", "-p", "4", unsigned, aligned)
    keystore = BUILD / "throwaway.keystore"  # *.keystore is git-ignored too (D-86)
    if not keystore.exists():
        _run(
            "keytool", "-genkeypair", "-keystore", keystore, "-storepass", "android",
            "-alias", "a11ytree", "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
            "-dname", "CN=a11y tree", "-noprompt",
        )  # fmt: skip
    _run(
        tools / "apksigner", "sign", "--ks", keystore, "--ks-pass", "pass:android",
        "--out", apk, aligned,
    )  # fmt: skip
    return apk


# ------------------------------------------------------------------ the device


def dump(serial: str, route: str | None = None, wait: float = 2.0) -> str:
    """Install the APK on `serial`, open `route` if given, and return the screen's XML."""
    adb = ("adb", "-s", serial)
    _run(*adb, "install", "-r", build())
    if route:
        _run(
            *adb,
            "shell",
            "am",
            "start",
            "-W",
            "-a",
            "android.intent.action.VIEW",
            "-d",
            deep_link(route),
        )
        time.sleep(wait)
    return result_xml(_run(*adb, "shell", "am", "instrument", "-w", "-r", RUNNER))


def main(argv: list[str] | None = None) -> int:
    """Parse the command line, dump the screen and print it."""
    parser = argparse.ArgumentParser(
        description="Print the accessibility tree of the screen on an Android emulator."
    )
    parser.add_argument(
        "--serial", required=True, help="the emulator, such as emulator-5578"
    )
    parser.add_argument("--route", help="open this route first, such as /more")
    parser.add_argument(
        "--wait", type=float, default=2.0, help="seconds to let --route settle (2)"
    )
    parser.add_argument(
        "--headings", action="store_true", help="list only the heading nodes"
    )
    parser.add_argument("--bounds", action="store_true", help="add each node's bounds")
    parser.add_argument("--xml", action="store_true", help="print the raw XML instead")
    args = parser.parse_args(argv)
    try:
        xml = dump(args.serial, args.route, args.wait)
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(f"a11y_tree: {error}", file=sys.stderr)
        return 1
    print(xml if args.xml else render(parse(xml), args.headings, args.bounds))
    return 0


if __name__ == "__main__":
    sys.exit(main())
