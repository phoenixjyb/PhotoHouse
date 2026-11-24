#!/usr/bin/env python3
"""Run prebuilt, unconfigured QA instrumentation on one explicit emulator only.

Never use a broad Gradle connected task when a physical device is attached.
This runner does not build, select a device automatically, uninstall or publish.
"""
import argparse
from pathlib import Path
import re
import subprocess

PACKAGE_PREFIX = {"phone": "dev.photohouse.connected", "tv": "dev.photohouse.tv"}


class Refused(RuntimeError):
    """A device or artifact did not meet the explicit QA boundary."""


def execute(args, run=subprocess.run):
    if not re.fullmatch(r"emulator-[0-9]{4,5}", args.serial):
        raise Refused("An explicit emulator serial is required; physical devices are refused")
    prefix_package = PACKAGE_PREFIX.get(getattr(args, "client", "phone"))
    if prefix_package is None:
        raise Refused("Select phone or TV QA")
    test_name = re.escape(prefix_package) + r"\.[A-Za-z0-9_.$]+(?:#[A-Za-z0-9_$]+)?"
    if not re.fullmatch(test_name + rf"(?:,{test_name})*", args.test_class):
        raise Refused("Select explicit PhotoHouse test classes")
    qa_package = prefix_package + ".qa"
    qa_test_package = qa_package + ".test"
    runner = qa_test_package + "/androidx.test.runner.AndroidJUnitRunner"
    for path in (args.apk, args.test_apk):
        if not Path(path).is_file():
            raise Refused("A prebuilt APK is missing")

    def command(argv, timeout=30):
        result = run(argv, check=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()

    for apk, expected in ((args.apk, qa_package), (args.test_apk, qa_test_package)):
        output = command([args.aapt, "dump", "badging", str(apk)])
        packages = re.findall(r"^package: name='([^']+)'", output, re.MULTILINE)
        if packages != [expected]:
            raise Refused("Only the separate QA application and QA test packages are allowed")

    prefix = [args.adb, "-s", args.serial]

    def ensure_emulator():
        if command(prefix + ["get-state"]) != "device":
            raise Refused("The selected emulator is unavailable")
        if command(prefix + ["get-serialno"]) != args.serial:
            raise Refused("The selected device identity changed")
        if command(prefix + ["shell", "getprop", "ro.boot.qemu"]) != "1":
            raise Refused("The selected device is not an emulator")

    ensure_emulator()
    # The streamed install can time out after the emulator has already committed
    # the APK. Use ADB's separate push/install path for a clear bounded result.
    planned = [
        prefix + ["install", "--no-streaming", "-r", str(args.apk)],
        prefix + ["install", "--no-streaming", "-r", str(args.test_apk)],
        prefix + ["shell", "am", "instrument", "-w", "-r", "-e", "class", args.test_class, runner],
    ]
    if args.dry_run:
        return {"status": "qa_emulator_preflight_passed", "serial": args.serial, "commands": planned}
    for argv in planned[:2]:
        ensure_emulator()
        if "Success" not in command(argv, timeout=120):
            raise Refused("QA installation did not report success")
    ensure_emulator()
    output = command(planned[2], timeout=600)
    passed = re.search(r"\bOK \(([1-9][0-9]*) tests?\)", output)
    if not passed or any(marker in output for marker in
                         ("FAILURES!!!", "INSTRUMENTATION_FAILED", "Process crashed", "shortMsg=")):
        raise Refused("The explicit emulator instrumentation did not pass")
    return {"status": "qa_emulator_tests_passed", "serial": args.serial, "tests": int(passed.group(1))}


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--client", choices=PACKAGE_PREFIX, default="phone")
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--test-apk", required=True, type=Path)
    parser.add_argument("--aapt", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--class", dest="test_class", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(execute(args), sort_keys=True))
    except (Refused, OSError, subprocess.SubprocessError) as error:
        # Fixed controller messages only; do not echo device output or app logs.
        parser.exit(1, (str(error) if isinstance(error, Refused) else "Emulator check failed") + "\n")


if __name__ == "__main__":
    main()
