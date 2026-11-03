"""Tests for ``tools/device.py``: the commands it builds, and the owner's devices it refuses."""

from pathlib import Path

import pytest

from tools import device


def test_android_prefs_set_all_four() -> None:
    """200 % text, bold, high contrast and dark become the four settings F84 and #828 used."""
    commands = device.android_prefs("emulator-5594", "200", True, True, True, False)
    assert [c[3:] for c in commands] == [
        ["shell", "settings", "put", "system", "font_scale", "2.0"],
        ["shell", "settings", "put", "secure", "font_weight_adjustment", "300"],
        ["shell", "settings", "put", "secure", "contrast_level", "1"],
        ["shell", "cmd", "uimode", "night", "yes"],
    ]
    assert all(c[:3] == ["adb", "-s", "emulator-5594"] for c in commands)


def test_android_reset_returns_to_the_defaults() -> None:
    """Reset ignores the other choices and sets each of the four back."""
    commands = device.android_prefs("emulator-5594", "max", True, False, False, True)
    assert [c[-1] for c in commands] == ["1.0", "0", "0", "no"]


def test_android_prefs_leave_what_isnt_asked() -> None:
    """Asking for one thing sets one thing, so a sweep can change one at a time."""
    assert (
        len(device.android_prefs("emulator-5594", None, False, False, True, False)) == 1
    )
    assert device.android_prefs("emulator-5594", None, False, False, False, False) == []


def test_ios_prefs_set_all_four() -> None:
    """The largest text, Bold Text, Increase Contrast and dark are ``simctl``'s four."""
    commands = device.ios_prefs("U", "max", True, True, True, False)
    assert commands[0][-2:] == ["content_size", "accessibility-extra-extra-extra-large"]
    assert commands[1][-3:] == ["EnhancedTextLegibilityEnabled", "-bool", "true"]
    assert commands[2][-2:] == ["increase_contrast", "enabled"]
    assert commands[3][-2:] == ["appearance", "dark"]


def test_ios_reset_returns_to_the_defaults() -> None:
    """Reset sets iOS's default text size and turns the other three off."""
    commands = device.ios_prefs("U", None, False, False, False, True)
    assert [c[-1] for c in commands] == ["large", "false", "disabled", "light"]


def test_every_text_size_exists_on_both_platforms() -> None:
    """``--text`` offers one set of choices, so both tables have the same keys."""
    assert set(device.IOS_TEXT) == set(device.ANDROID_TEXT)


def test_emulator_boots_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """The boot line uses the SDK from the environment and leaves the AVD's disk alone."""
    monkeypatch.setenv("ANDROID_HOME", "/sdk")
    command = device.emulator_command("avd", 5594)
    assert Path(command[0]) == Path("/sdk/emulator/emulator")
    assert command[1:5] == ["-avd", "avd", "-port", "5594"]
    assert "-read-only" in command


def test_setup_keeps_animations_unless_asked() -> None:
    """Animations stay on by default, for recordings; flows ask to turn them off."""
    assert len(device.serial_setup("emulator-5594", True)) == 1
    assert len(device.serial_setup("emulator-5594", False)) == 4


@pytest.mark.parametrize(
    "argv",
    [
        ["up", "android", "--port", "5554"],
        ["up", "android", "--port", "5594", "--avd", device.OWNERS_AVD],
        ["up", "ios", "--name", device.OWNERS_SIMULATOR],
        ["prefs", device.OWNERS_SERIAL, "--reset"],
        ["prefs", device.OWNERS_SIMULATOR, "--reset"],
        ["down", device.OWNERS_SERIAL],
        ["down", device.OWNERS_SIMULATOR],
    ],
)
def test_owners_devices_are_refused(
    argv: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every command stops on the owner's devices, before it runs anything."""

    def no_call(*args: object, **kwargs: object) -> str:
        """Fail the test if a command would run."""
        raise AssertionError(f"ran {args}")

    monkeypatch.setattr(device.subprocess, "run", no_call)
    monkeypatch.setattr(device.subprocess, "Popen", no_call)
    monkeypatch.setattr(device, "_running_emulators", list)
    with pytest.raises(SystemExit, match="owner's"):
        device.main(argv)


def test_owners_simulator_is_refused_by_udid(monkeypatch: pytest.MonkeyPatch) -> None:
    """Naming the owner's simulator by its udid is refused too."""
    monkeypatch.setattr(
        device,
        "_simulators",
        lambda: [{"name": device.OWNERS_SIMULATOR, "udid": "U", "state": "Booted"}],
    )
    with pytest.raises(SystemExit, match="owner's"):
        device.main(["prefs", "U", "--reset"])
