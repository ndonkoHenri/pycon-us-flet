"""Tests for `tools/sweep.py`: every mode runs, and the device always goes back (#973)."""

import subprocess
from pathlib import Path

import pytest

from tools import device, sweep

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Record what a sweep would run, with no mock, device or Maestro."""
    made: list[list[str]] = []
    monkeypatch.setattr(sweep.own, "start", lambda state, options: 8123)
    monkeypatch.setattr(sweep.device, "main", made.append)
    return made


def test_every_mode_is_a_valid_prefs_line() -> None:
    """Each mode's options are ones `tools.device prefs` accepts."""
    parser = device._parser()
    for options in sweep.MODES.values():
        parser.parse_args(["prefs", "emulator-5594", *options])


def test_flow_runs_against_this_checkouts_mock() -> None:
    """The line names the device, the mock as that platform reaches it, and the folder."""
    command = sweep.maestro_command(
        "emulator-5594", "android", 8123, "staff_tour", Path("out")
    )
    assert command[:4] == ["maestro", "--device", "emulator-5594", "test"]
    assert "MOCK_URL=http://10.0.2.2:8123" in command
    assert command[-1] == "maestro/sweeps/staff_tour.yaml"


def test_failed_mode_doesnt_stop_the_rest(
    calls: list[list[str]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A tour that fails still leaves the next mode to run, exits 1 and resets the device."""
    ran: list[str] = []

    def run_flow(command: list[str]) -> bool:
        """Fail the first tour, and pass everything else."""
        ran.append(command[-1])
        return (
            ran.count("maestro/sweeps/staff_tour.yaml") != 1 or "sign_in" in command[-1]
        )

    monkeypatch.setattr(sweep, "run_flow", run_flow)
    with pytest.raises(SystemExit, match=r"^1$"):
        sweep.main(
            [
                "--device",
                "emulator-5594",
                "--modes",
                "default",
                "dark",
                "--output",
                str(tmp_path),
            ]
        )
    assert ran.count("maestro/sweeps/staff_tour.yaml") == 2
    assert calls[-1] == ["prefs", "emulator-5594", "--reset"]


def test_mode_signs_in_afresh_at_the_default_size(
    calls: list[list[str]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The text changes only after the sign-in: at the largest the scene can't be set."""
    order: list[str] = []
    monkeypatch.setattr(
        sweep, "run_flow", lambda command: order.append(command[-1]) or True
    )
    monkeypatch.setattr(
        sweep.device, "main", lambda argv: order.append(" ".join(argv[2:]))
    )
    sweep.main(
        ["--device", "emulator-5594", "--modes", "max", "--output", str(tmp_path)]
    )
    assert order == [
        "--reset",
        "maestro/sweeps/sign_in.yaml",
        "--text max --bold",
        "maestro/sweeps/staff_tour.yaml",
        "--reset",
    ]


def test_failed_sign_in_skips_that_tour(
    calls: list[list[str]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A mode whose sign-in fails runs no tour, and the next mode still signs in."""
    ran: list[str] = []

    def run_flow(command: list[str]) -> bool:
        """Fail every sign-in."""
        ran.append(command[-1])
        return "sign_in" not in command[-1]

    monkeypatch.setattr(sweep, "run_flow", run_flow)
    with pytest.raises(SystemExit, match=r"^1$"):
        sweep.main(
            [
                "--device",
                "emulator-5594",
                "--modes",
                "default",
                "dark",
                "--output",
                str(tmp_path),
            ]
        )
    assert ran == ["maestro/sweeps/sign_in.yaml"] * 2


def test_refused_setting_fails_that_mode_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A device that refuses one mode's settings fails it, and the next mode still runs."""

    def prefs(argv: list[str]) -> None:
        """Refuse dark, and accept everything else."""
        if "--dark" in argv:
            raise subprocess.CalledProcessError(1, "adb")

    monkeypatch.setattr(sweep.own, "start", lambda state, options: 8123)
    monkeypatch.setattr(sweep.device, "main", prefs)
    monkeypatch.setattr(sweep, "run_flow", lambda command: True)
    with pytest.raises(SystemExit, match=r"^1$"):
        sweep.main(
            [
                "--device",
                "emulator-5594",
                "--modes",
                "dark",
                "max",
                "--output",
                str(tmp_path),
            ]
        )
    out = capsys.readouterr().out
    assert "dark: FAILED" in out
    assert "max: reached every state" in out


def test_owners_device_is_refused(calls: list[list[str]]) -> None:
    """A sweep clears the app's data, so it never runs on the owner's emulator."""
    with pytest.raises(SystemExit, match="owner's"):
        sweep.main(["--device", "emulator-5554"])
    assert calls == []


def test_sweeps_stay_out_of_the_workspace() -> None:
    """`maestro test maestro` runs no sweep, so a full flow rerun isn't changed by them."""
    assert "sweeps" not in (ROOT / "maestro" / "config.yaml").read_text()
