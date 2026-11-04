"""Guard D-472: Android's Auto Backup takes only the preferences file.

The secure-storage files hold ciphertext that only this phone's Keystore can open, and
`outbox-<year>.db` would send a restored phone's queued scans again. The rules are an
allowlist of the one file the preferences live in, in both files Android reads (Android
11 and older, then 12 and newer), and `pyproject.toml` points the manifest at them.
The backup and restore itself is run on an emulator (`docs/development.md` §8.1).
"""

import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from flet_cli.utils.android import android_resource_files

ROOT = Path(__file__).resolve().parents[1]
ROOTS = {
    "backup_rules.xml": "full-backup-content",
    "data_extraction_rules.xml": "data-extraction-rules",
}
"""The root element Android reads in each rules file; another name is silently ignored."""
PREFERENCES = ("sharedpref", "FlutterSharedPreferences.xml")
"""The (domain, path) of the one file Auto Backup may take: SharedPreferences' own."""


def android_settings() -> dict:
    """Return `[tool.flet.android]` from `pyproject.toml`."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return pyproject["tool"]["flet"]["android"]


def res_dir() -> Path:
    """Return the project's Android resource folder, as flet-cli resolves it."""
    return ROOT / android_settings()["res_dir"]


def includes(file: str, *parents: str) -> list[tuple[str | None, str | None]]:
    """Return the (domain, path) of every `<include>` under `parents` in a rules file.

    Args:
        file: The rules file's name in `res/xml`.
        parents: The element names from the root down to the one holding the includes;
            none for a root that holds them itself.
    """
    node = ET.parse(res_dir() / "xml" / file).getroot()
    assert node.tag == ROOTS[file], f"{file}'s root is <{node.tag}>"
    for name in parents:
        found = node.find(name)
        assert found is not None, f"{file} has no <{name}>"
        node = found
    assert node.findall("exclude") == [], f"{file}: an allowlist needs no exclude"
    return [(i.get("domain"), i.get("path")) for i in node.findall("include")]


def test_the_manifest_names_both_rule_files_and_says_backup_is_on() -> None:
    """`allowBackup` is stated, and each rules attribute names a file that ships."""
    application = android_settings()["manifest_application"]
    assert application["allowBackup"] == "true"
    assert application["fullBackupContent"] == "@xml/backup_rules"
    assert application["dataExtractionRules"] == "@xml/data_extraction_rules"
    shipped = {file.as_posix() for file in android_resource_files(res_dir())}
    assert {"xml/backup_rules.xml", "xml/data_extraction_rules.xml"} <= shipped


def test_android_11_and_older_backs_up_only_the_preferences_file() -> None:
    """`fullBackupContent` includes the preferences file and nothing else."""
    assert includes("backup_rules.xml") == [PREFERENCES]


@pytest.mark.parametrize("target", ["cloud-backup", "device-transfer"])
def test_android_12_and_newer_takes_only_the_preferences_file(target: str) -> None:
    """A cloud backup and a transfer to a new phone both include only that file."""
    assert includes("data_extraction_rules.xml", target) == [PREFERENCES]
