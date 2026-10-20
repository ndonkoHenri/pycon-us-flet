"""Run the S8 checks on an Android emulator whose back camera is the virtual scene.

Start the emulator with gRPC and the badge QR as the scene's wall poster:

    emulator -avd <avd> -read-only -no-audio -no-boot-anim -port <port> -grpc <grpc-port> \
        -camera-back virtualscene -virtualscene-poster wall=$PWD/src/qr.png

then install the release APK with the camera granted (``adb install -g``) and run

    uv run --with grpcio-tools python drive_android.py <serial> <grpc-port> <check> [...]

Checks: ``cold`` (5 cold starts facing the QR: mount to first detection), ``rate``
(20 s facing it: detections per second), ``turn`` (start facing away, turn to the
QR: turn to first detection), ``background`` (Home for 10 s facing the QR, then
back: detections while away, resume to first detection, camera clients),
``cycles`` (50 pause/resume cycles facing the QR, then a detection), ``gate``
(the app's error lines in logcat). Each prints one ``S8-DRIVER`` line per result.

The scene puts the wall poster at (-0.807, 0.320, 5.316), turned -150° (the
emulator's ``resources/Toren1BD.posters``); the device faces it from
(-0.5, 0, 3) turned 180°.
"""

import itertools
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PKG = "io.github.ndonkohenri.pyconus.s8"
FACING_QR = ([-0.5, 0.0, 3.0], [0.0, 180.0, 0.0])
FACING_AWAY = ([0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
SDK_PROTO = Path.home() / "Library/Android/sdk/emulator/lib/emulator_controller.proto"

serial, grpc_port, *checks = sys.argv[1:]


def adb(*args: str) -> str:
    """Run one adb command on the emulator and return its output."""
    return subprocess.run(
        ["adb", "-s", serial, *args], capture_output=True, text=True, check=False
    ).stdout


def controller():
    """Compile the SDK's emulator_controller.proto once and return a stub and its module."""
    out = Path(tempfile.gettempdir()) / "s8-grpc"
    out.mkdir(exist_ok=True)
    if not (out / "emulator_controller_pb2.py").exists():
        import grpc_tools
        from grpc_tools import protoc

        well_known = Path(grpc_tools.__file__).parent / "_proto"
        protoc.main(
            [
                "protoc",
                f"-I{SDK_PROTO.parent}",
                f"-I{well_known}",
                f"--python_out={out}",
                f"--grpc_python_out={out}",
                str(SDK_PROTO),
            ]
        )
    sys.path.insert(0, str(out))
    import emulator_controller_pb2 as pb
    import emulator_controller_pb2_grpc as pbg
    import grpc

    return pbg.EmulatorControllerStub(
        grpc.insecure_channel(f"localhost:{grpc_port}")
    ), pb


STUB, PB = controller()


def face(pose: tuple[list[float], list[float]]) -> None:
    """Move and turn the virtual device, which moves the scene camera."""
    for target, values in zip(
        (PB.PhysicalModelValue.POSITION, PB.PhysicalModelValue.ROTATION),
        pose,
        strict=False,
    ):
        STUB.setPhysicalModel(
            PB.PhysicalModelValue(target=target, value=PB.ParameterValue(data=values))
        )


def lines() -> list[str]:
    """Return the app's ``S8`` lines from logcat."""
    return [
        line
        for line in adb("logcat", "-d", "-s", "flet.python:I").splitlines()
        if " S8 " in line
    ]


def field(line: str, name: str) -> str:
    """Return one ``name=value`` field of an ``S8`` line."""
    return re.search(rf"{name}=(\S+)", line).group(1)


def wait_for(event: str, after: int, timeout: float = 30) -> list[str]:
    """Wait until an ``S8 <event>`` line appears after the first ``after`` lines."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        new = [line for line in lines()[after:] if f"S8 {event} " in line]
        if new:
            return new
        time.sleep(0.25)
    return []


def launch(route: str = "/") -> None:
    """Cold-start the app on a route, with an empty log."""
    adb("shell", "am", "force-stop", PKG)
    adb("logcat", "-c")
    adb(
        "shell",
        "am",
        "start",
        "-W",
        "-n",
        f"{PKG}/.MainActivity",
        "--es",
        "route",
        route,
    )


def report(check: str, **values: object) -> None:
    """Print one result line."""
    print(
        "S8-DRIVER", check, " ".join(f"{k}={v}" for k, v in values.items()), flush=True
    )


def camera_clients() -> int:
    """Count the app's entries under "Active Camera Clients" in ``dumpsys media.camera``."""
    out = adb("shell", "dumpsys", "media.camera")
    active = out.split("Active Camera Clients:")[1].split("]")[0]
    return active.count(f"Client Package Name: {PKG}")


def pss_kb() -> int:
    """Return the app's total PSS in kB (``dumpsys meminfo``)."""
    out = adb("shell", "dumpsys", "meminfo", PKG)
    return int(re.search(r"TOTAL PSS:\s+(\d+)", out).group(1))


for check in checks:
    if check == "cold":
        face(FACING_QR)
        for run in range(5):
            launch()
            hit = wait_for("detect", 0)
            report(
                "cold",
                run=run + 1,
                mount_to_first_s=field(hit[0], "since_mount") if hit else "none",
            )
    elif check == "rate":
        face(FACING_QR)
        launch()
        wait_for("detect", 0)
        start = len([x for x in lines() if "S8 detect " in x])
        time.sleep(20)
        hits = [float(field(x, "mono")) for x in lines() if "S8 detect " in x][start:]
        gaps = [b - a for a, b in itertools.pairwise(hits)]
        report(
            "rate",
            detections=len(hits),
            per_s=f"{len(hits) / 20:.2f}",
            median_gap_ms=f"{sorted(gaps)[len(gaps) // 2] * 1000:.0f}"
            if gaps
            else "none",
        )
    elif check == "turn":
        for run in range(5):
            face(FACING_AWAY)
            launch()
            wait_for("mounted", 0)
            time.sleep(5)
            before = len(lines())
            turned = time.time()
            face(FACING_QR)
            hit = wait_for("detect", before)
            # logcat's wall clock and the host's are the same clock on an emulator.
            stamp = hit[0].split()[1] if hit else None
            if stamp:
                day = time.strftime("%Y-%m-%d ")
                seen = time.mktime(
                    time.strptime(day + stamp.split(".")[0], "%Y-%m-%d %H:%M:%S")
                )
                seen += float("0." + stamp.split(".")[1])
            report(
                "turn",
                run=run + 1,
                turn_to_first_s=f"{seen - turned:.2f}" if stamp else "none",
            )
    elif check == "background":
        face(FACING_QR)
        launch()
        wait_for("detect", 0)
        report("background", camera_clients_foreground=camera_clients())
        adb("shell", "input", "keyevent", "HOME")
        time.sleep(2)
        count = len([x for x in lines() if "S8 detect " in x])
        clients = camera_clients()
        time.sleep(8)
        away = len([x for x in lines() if "S8 detect " in x]) - count
        before = len(lines())
        back = time.monotonic()
        adb("shell", "am", "start", "-n", f"{PKG}/.MainActivity")
        hit = wait_for("detect", before)
        report(
            "background",
            detections_while_away=away,
            camera_clients_away=clients,
            resume_to_first_s=f"{time.monotonic() - back:.2f}" if hit else "none",
        )
    elif check == "cycles":
        face(FACING_QR)
        launch("/cycles/50/1500")
        wait_for("cycle", 0)
        pss_first = pss_kb()
        done = wait_for("cycles-done", 0, timeout=240)
        before = len(lines())
        hit = wait_for("detect", before, timeout=15)
        cycles = [x for x in lines() if "S8 cycle " in x]
        steps = [
            int(field(b, "detections")) - int(field(a, "detections"))
            for a, b in itertools.pairwise(cycles)
        ]
        report(
            "cycles",
            completed=field(done[0], "count") if done else "none",
            cycles_without_detection=sum(1 for s in steps if s == 0),
            detects_after=bool(hit),
            camera_clients=camera_clients(),
            pss_after_cycle_1_kb=pss_first,
            pss_after_cycle_50_kb=pss_kb(),
        )
    elif check == "gate":
        log = adb("logcat", "-d")
        bad = [
            x
            for x in log.splitlines()
            if re.search(
                r"No Material widget|FlutterError|Unhandled Exception|CameraX.*(Error|Exception)|"
                r"FATAL EXCEPTION|ANR in",
                x,
            )
        ]
        report("gate", bad_lines=len(bad))
        print("\n".join(bad[:20]))
