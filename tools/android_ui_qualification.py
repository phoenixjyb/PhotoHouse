#!/usr/bin/env python3
"""Run the fixed PhotoHouse fixture-only UI suite on one owned API 34 emulator.

Build the unconfigured QA APKs separately. This runner refuses physical devices,
installs only the separate QA packages, strictly parses the selected test run,
and downloads only the seven named app-private fixture screenshots.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

if __package__:
    from .android_emulator_test import execute as install_and_test, Refused as EmulatorRefused
    from .android_instrumentation_report import summarize
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools.android_emulator_test import execute as install_and_test, Refused as EmulatorRefused
    from tools.android_instrumentation_report import summarize

QA_PACKAGE = "dev.photohouse.connected.qa"
QA_TEST_PACKAGE = QA_PACKAGE + ".test"
SERIAL = "emulator-5560"
API_LEVEL = "34"
ABI = "x86_64"
RUNNER = "androidx.test.runner.AndroidJUnitRunner"
TEST_CLASS = (
    "dev.photohouse.connected.AssistantSceneUiTest,"
    "dev.photohouse.connected.ConnectedUiTest#phonePhotoStacksKeepCountActionsAndViewOnlyControlsVisibleAtLargeText,"
    "dev.photohouse.connected.ConnectedUiTest#libraryPhotoStackResetIsVisibleEvenWhenNoGroupsRemain"
)
SCREENSHOTS = (
    "scene-zh-actions-150.png",
    "scene-en-actions-150.png",
    "scene-zh-ranking-150.png",
    "scene-en-ranking-150.png",
    "photo-stacks-en-150.png",
    "photo-stacks-zh-150.png",
    "photo-stacks-separated-zh-150.png",
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_SCREENSHOT_BYTES = 20 * 1024 * 1024


class QualificationError(RuntimeError):
    """A fixed safety or qualification gate failed."""


def package_from_badging(output: str) -> str | None:
    rows = re.findall(r"^package: name='([^']+)'(?:\s|$)", output, re.MULTILINE)
    return rows[0] if len(rows) == 1 else None


def validate_png(raw: bytes) -> tuple[int, int]:
    if (len(raw) < 24 or len(raw) > MAX_SCREENSHOT_BYTES or
            raw[:8] != PNG_SIGNATURE or raw[12:16] != b"IHDR"):
        raise QualificationError("fixture_screenshot_png_invalid")
    width = int.from_bytes(raw[16:20], "big")
    height = int.from_bytes(raw[20:24], "big")
    if not (1 <= width <= 4096 and 1 <= height <= 4096):
        raise QualificationError("fixture_screenshot_dimensions_invalid")
    return width, height


def parse_instrumentation(raw: bytes) -> dict:
    report = summarize(raw)
    if report.get("status") != "passed" or report.get("complete") is not True or report.get("passed") != 7:
        raise QualificationError("strict_instrumentation_report_failed")
    return report


def device_rows(output: str) -> list[tuple[str, str]]:
    rows = []
    for line in output.splitlines()[1:]:
        fields = line.split()
        if fields:
            rows.append((fields[0], fields[1] if len(fields) > 1 else ""))
    return rows


def _write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def _write_failure(path: Path, value: dict) -> None:
    try:
        with path.open("w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
    except OSError:
        pass


def _git_value(revision: str) -> str | None:
    root = Path(__file__).resolve().parents[1]
    try:
        result = subprocess.run(["git", "-C", str(root), "rev-parse", revision],
                                check=True, capture_output=True, text=True,
                                encoding="utf-8", errors="strict", timeout=10)
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None
    value = result.stdout.strip()
    return value if re.fullmatch(r"[0-9a-f]{40,64}", value) else None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_command(argv: list[str]) -> dict:
    tool = Path(argv[0]).name
    if tool not in {"adb", "aapt", "sdkmanager", "avdmanager", "emulator"}:
        tool = "unknown"
    safe_args = []
    for value in argv[1:]:
        if value.startswith(("/", "\\")) or "/" in value or "\\" in value:
            safe_args.append(Path(value).name or "<path>")
        elif re.fullmatch(r"[A-Za-z0-9_.:=,@+-]{1,160}", value):
            safe_args.append(value)
        else:
            safe_args.append("<redacted>")
    return {"tool": tool, "arguments": safe_args}


def _run(argv: list[str], timeout: int = 30, *, env=None, input_text=None,
         failure_artifacts: Path | None = None) -> str:
    try:
        result = subprocess.run(argv, check=True, capture_output=True, text=True,
                                encoding="utf-8", errors="strict", timeout=timeout, env=env,
                                input=input_text)
    except (OSError, subprocess.SubprocessError, UnicodeError) as error:
        if failure_artifacts is not None:
            record = {"reason": "android_ui_command_failed", "command": _safe_command(argv),
                      "error_kind": type(error).__name__}
            if isinstance(error, subprocess.CalledProcessError):
                record["returncode"] = error.returncode
            elif isinstance(error, subprocess.TimeoutExpired):
                record["timeout_seconds"] = timeout
            _write_failure(failure_artifacts / "command-failure.json", record)
        raise QualificationError("android_ui_command_failed") from None
    return result.stdout.strip()


def _direct_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink() and path.resolve() == path


def run_qualification(args) -> dict:
    sdk = args.sdk_root.resolve(strict=True)
    artifacts = args.artifacts.resolve()
    avd_home = args.avd_home.resolve()
    if not sdk.is_dir() or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", args.avd_name):
        raise QualificationError("sdk_or_avd_identity_invalid")
    if not (30 <= args.boot_timeout <= 900):
        raise QualificationError("boot_timeout_out_of_bounds")
    if artifacts.exists() and any(artifacts.iterdir()):
        raise QualificationError("artifact_directory_must_be_empty")
    artifacts.mkdir(parents=True, exist_ok=True)
    avd_home.mkdir(parents=True, exist_ok=True)

    sdkmanager = sdk / "cmdline-tools/latest/bin/sdkmanager"
    avdmanager = sdk / "cmdline-tools/latest/bin/avdmanager"
    emulator = sdk / "emulator/emulator"
    adb = sdk / "platform-tools/adb"
    aapt = sdk / "build-tools/34.0.0/aapt"
    app_apk = args.app_apk.resolve(strict=True)
    test_apk = args.test_apk.resolve(strict=True)
    if (not all(p.is_file() for p in (sdkmanager, avdmanager, emulator, adb, aapt)) or
            not _direct_file(app_apk) or not _direct_file(test_apk)):
        raise QualificationError("android_sdk_or_qa_apk_missing")

    env = dict(os.environ)
    env["ANDROID_SDK_ROOT"] = str(sdk)
    env["ANDROID_HOME"] = str(sdk)
    env["ANDROID_AVD_HOME"] = str(avd_home)
    def checked_run(argv, timeout=30, *, input_text=None):
        return _run(argv, timeout=timeout, env=env, input_text=input_text,
                    failure_artifacts=artifacts)

    initial_devices = checked_run([str(adb), "devices"])
    if initial_devices != "List of devices attached":
        rows = device_rows(initial_devices)
        if rows:
            raise QualificationError("preexisting_android_device_refused")
    for apk, expected in ((app_apk, QA_PACKAGE), (test_apk, QA_TEST_PACKAGE)):
        badging = checked_run([str(aapt), "dump", "badging", str(apk)], timeout=60)
        if package_from_badging(badging) != expected:
            raise QualificationError("qa_apk_package_mismatch")

    avd_created = False
    process = None
    emulator_log = None
    try:
        checked_run([str(sdkmanager), "--sdk_root=" + str(sdk), "--install",
              "system-images;android-34;google_apis;x86_64"], timeout=900)
        checked_run([str(avdmanager), "create", "avd", "--name", args.avd_name,
              "--package", "system-images;android-34;google_apis;x86_64",
              "--device", "pixel_2"], timeout=120, input_text="no\n")
        avd_created = True
        emulator_log = (artifacts / "emulator.log").open("xb")
        os.chmod(emulator_log.name, 0o600)
        process = subprocess.Popen(
            [str(emulator), "-avd", args.avd_name, "-port", "5560", "-no-window",
             "-no-audio", "-no-boot-anim", "-no-snapshot", "-wipe-data",
             "-gpu", "swiftshader_indirect", "-feature", "-Vulkan", "-accel", "on",
             "-camera-back", "none", "-camera-front", "none"],
            env=env, stdin=subprocess.DEVNULL, stdout=emulator_log,
            stderr=subprocess.STDOUT)
        prefix = [str(adb), "-s", SERIAL]
        deadline = time.monotonic() + args.boot_timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise QualificationError("owned_emulator_exited_before_boot")
            try:
                checked_run(prefix + ["wait-for-device"], timeout=min(10, max(1, int(deadline - time.monotonic()))))
                if checked_run(prefix + ["get-serialno"]) == SERIAL:
                    if checked_run(prefix + ["shell", "getprop", "sys.boot_completed"]) == "1":
                        break
            except QualificationError:
                time.sleep(2)
        else:
            raise QualificationError("emulator_boot_timeout")

        current_devices = device_rows(checked_run([str(adb), "devices"]))
        qemu = checked_run(prefix + ["shell", "getprop", "ro.boot.qemu"])
        api_level = checked_run(prefix + ["shell", "getprop", "ro.build.version.sdk"])
        abi = checked_run(prefix + ["shell", "getprop", "ro.product.cpu.abi"])
        _write_json(artifacts / "platform-preflight.json", {
            "serial": SERIAL, "device_rows": current_devices,
            "qemu_property": qemu, "api_level": api_level, "abi": abi,
        })
        if current_devices != [(SERIAL, "device")]:
            raise QualificationError("single_emulator_identity_required")
        if qemu != "1" or api_level != API_LEVEL or abi != ABI:
            raise QualificationError("emulator_platform_identity_mismatch")

        def verify_native_emulator() -> None:
            if (checked_run(prefix + ["get-serialno"]) != SERIAL or
                    checked_run(prefix + ["shell", "getprop", "ro.boot.qemu"]) != "1"):
                raise QualificationError("emulator_identity_changed_before_write")

        def device_write(arguments: list[str]) -> str:
            verify_native_emulator()
            return checked_run(prefix + arguments)

        # The QA build has blank origins. Record the verified airplane-mode
        # setting without treating that setting as an independent isolation proof.
        for namespace, key, value in (
            ("global", "device_provisioned", "1"), ("secure", "user_setup_complete", "1"),
            ("global", "window_animation_scale", "0"),
            ("global", "transition_animation_scale", "0"), ("global", "animator_duration_scale", "0"),
        ):
            device_write(["shell", "settings", "put", namespace, key, value])
        device_write(["shell", "cmd", "connectivity", "airplane-mode", "enable"])
        airplane_mode = checked_run(prefix + ["shell", "settings", "get", "global", "airplane_mode_on"])
        if airplane_mode != "1":
            raise QualificationError("airplane_mode_not_confirmed")
        device_write(["shell", "input", "keyevent", "KEYCODE_WAKEUP"])
        device_write(["shell", "wm", "dismiss-keyguard"])
        device_write(["shell", "input", "keyevent", "KEYCODE_HOME"])

        instrument_outputs: list[bytes] = []
        instrumentation_log = artifacts / "instrumentation.log"
        def capture_run(argv, **kwargs):
            is_instrumentation = "instrument" in argv
            try:
                result = subprocess.run(argv, **kwargs)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                if is_instrumentation:
                    output = error.stdout or ""
                    raw_output = (output if isinstance(output, bytes) else
                                  output.encode("utf-8", errors="strict"))
                    instrument_outputs.append(raw_output)
                    with instrumentation_log.open("xb") as stream:
                        stream.write(raw_output)
                raise
            if is_instrumentation:
                output = result.stdout or ""
                raw_output = (output if isinstance(output, bytes) else
                              output.encode("utf-8", errors="strict"))
                instrument_outputs.append(raw_output)
                with instrumentation_log.open("xb") as stream:
                    stream.write(raw_output)
            return result

        import argparse
        try:
            run_result = install_and_test(argparse.Namespace(
                serial=SERIAL, apk=app_apk, test_apk=test_apk, aapt=str(aapt), adb=str(adb),
                test_class=TEST_CLASS, dry_run=False), run=capture_run)
        except (EmulatorRefused, OSError, subprocess.SubprocessError):
            raise QualificationError("explicit_qa_test_run_failed") from None
        if run_result.get("tests") != 7 or len(instrument_outputs) != 1:
            raise QualificationError("explicit_qa_test_count_mismatch")
        instrumentation = parse_instrumentation(instrument_outputs[0])

        screenshot_rows = []
        for name in SCREENSHOTS:
            raw = subprocess.run(prefix + ["exec-out", "run-as", QA_PACKAGE, "cat", "files/" + name],
                                 check=True, capture_output=True, timeout=30, env=env).stdout
            width, height = validate_png(raw)
            target = artifacts / name
            with target.open("xb") as stream:
                stream.write(raw)
            screenshot_rows.append({"name": name, "sha256": hashlib.sha256(raw).hexdigest(),
                                    "bytes": len(raw), "width": width, "height": height})
        result = {"status": "passed", "serial": SERIAL, "api_level": int(API_LEVEL), "abi": ABI,
                  "package": QA_PACKAGE, "instrumentation": instrumentation,
                  "screenshots": screenshot_rows, "physical_device_used": False,
                  "household_origin_configured": False,
                  "airplane_mode": "enabled_and_verified",
                  "source_revision": _git_value("HEAD"),
                  "android_tree_revision": _git_value("HEAD:clients/android/android"),
                  "app_apk_sha256": _file_sha256(app_apk),
                  "test_apk_sha256": _file_sha256(test_apk)}
        _write_json(artifacts / "qualification-result.json", result)
        return result
    finally:
        if process is not None:
            try:
                subprocess.run([str(adb), "-s", SERIAL, "emu", "kill"], check=False,
                               capture_output=True, timeout=15, env=env)
                process.wait(timeout=20)
            except (OSError, subprocess.SubprocessError):
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill()
        if emulator_log is not None:
            emulator_log.flush()
            emulator_log.close()
        if avd_created:
            subprocess.run([str(avdmanager), "delete", "avd", "--name", args.avd_name],
                           check=False, capture_output=True, timeout=60, env=env)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--app-apk", required=True, type=Path)
    parser.add_argument("--test-apk", required=True, type=Path)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--avd-home", required=True, type=Path)
    parser.add_argument("--avd-name", required=True)
    parser.add_argument("--boot-timeout", type=int, default=420)
    args = parser.parse_args(argv)
    try:
        result = run_qualification(args)
    except QualificationError as error:
        if args.artifacts.is_dir():
            _write_failure(args.artifacts / "qualification-failure.json",
                           {"status": "failed", "reason": str(error)})
        parser.exit(1, f"Android UI qualification failed: {error}\n")
    except (OSError, subprocess.SubprocessError):
        if args.artifacts.is_dir():
            _write_failure(args.artifacts / "qualification-failure.json",
                           {"status": "failed", "reason": "android_ui_operation_failed"})
        parser.exit(1, "Android UI qualification failed: android_ui_operation_failed\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
