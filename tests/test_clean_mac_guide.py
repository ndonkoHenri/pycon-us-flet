"""The clean-Mac setup in ``docs/development.md`` gives commands that work on Xcode 27."""

from pathlib import Path

GUIDE = Path(__file__).resolve().parents[1] / "docs" / "development.md"


def _ios_setup_commands() -> list[str]:
    """Return the lines of the fenced block that §5.1's iOS step gives."""
    step = GUIDE.read_text(encoding="utf-8").split("**3. iOS.**", 1)[1]
    return step.split("```bash\n", 1)[1].split("```", 1)[0].splitlines()


def test_ios_setup_selects_full_xcode_before_using_it() -> None:
    """The block starts by leaving the Command Line Tools, which have no xcodebuild or simctl."""
    commands = _ios_setup_commands()
    assert commands[0] == (
        "sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer"
    )
    assert "sudo xcodebuild -runFirstLaunch" in commands


def test_guide_opens_device_hub_not_the_removed_simulator_app() -> None:
    """Xcode 27 has no Simulator app, so the guide opens Device Hub everywhere it boots one."""
    guide = GUIDE.read_text(encoding="utf-8")
    assert "open -a Simulator" not in guide
    assert "open -a DeviceHub" in _ios_setup_commands()
