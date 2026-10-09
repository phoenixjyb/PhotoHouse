from __future__ import annotations

from contextlib import redirect_stdout
from importlib import metadata
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from tools import doctor


def python312():
    return SimpleNamespace(major=3, minor=12, micro=4)


def make_root(base: Path, lock: str = "alpha==1.2.3\n") -> Path:
    (base / "config").mkdir(parents=True)
    (base / "config/requirements-dev.lock").write_text(lock, encoding="utf-8")
    (base / "server/tests/security").mkdir(parents=True)
    (base / "clients/android/android/gradle/wrapper").mkdir(parents=True)
    return base


class DoctorTests(unittest.TestCase):
    def test_lock_reads_includes_and_skips_inactive_platform_pins(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            (root / "config").mkdir(parents=True)
            (root / "config/requirements-dev.lock").write_text(
                "-r requirements-api.lock\npytest==9.0.3 \\\n    --hash=sha256:" + "a" * 64 + "\n"
                "colorama==0.4.6 ; sys_platform == \"win32\" \\\n    --hash=sha256:" + "b" * 64 + "\n",
                encoding="utf-8",
            )
            (root / "config/requirements-api.lock").write_text("FastAPI==0.135.2\n", encoding="utf-8")
            pins, skipped = doctor.parse_cpu_lock(root / "config/requirements-dev.lock", "darwin")
        self.assertEqual({"fastapi": "0.135.2", "pytest": "9.0.3"}, pins)
        self.assertEqual(1, skipped)

    def test_missing_tools_and_sdk_do_not_hide_available_cpu_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = make_root(Path(temporary) / "repo")
            report = doctor.build_report(
                root,
                env={},
                platform="linux",
                version_info=python312(),
                version_lookup=lambda name: "1.2.3" if name == "alpha" else None,
                which=lambda _name: None,
                probe=lambda *_args, **_kwargs: self.fail("no executable should be probed"),
                home=root / "empty-home",
            )
        checks = report["checks"]
        profiles = {item["name"]: item for item in report["profiles"]}
        self.assertEqual("available", profiles["api"]["status"])
        self.assertEqual("available", profiles["memory"]["status"])
        self.assertEqual("missing", profiles["android"]["status"])
        self.assertEqual("missing", profiles["web"]["status"])
        self.assertEqual("missing", checks["node"]["status"])
        self.assertEqual("missing", checks["jdk17"]["status"])
        self.assertEqual("missing", checks["android_sdk34"]["status"])

    def test_paths_with_spaces_and_present_android_and_web_prerequisites(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = make_root(Path(temporary) / "source checkout with spaces")
            sdk = Path(temporary) / "Android SDK 34"
            (sdk / "platforms/android-34").mkdir(parents=True)
            (sdk / "platforms/android-34/android.jar").touch()
            build_tools = sdk / "build-tools/34.0.0"
            (build_tools / "lib").mkdir(parents=True)
            for name in ("aapt2", "d8", "zipalign"):
                (build_tools / name).touch()
            (build_tools / "lib/apksigner.jar").touch()
            android = root / "clients/android/android"
            (android / "gradlew").touch()
            (android / "gradle/wrapper/gradle-wrapper.jar").touch()
            (android / "gradle/wrapper/gradle-wrapper.properties").write_text(
                "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.10.2-bin.zip\n"
                "distributionSha256Sum=" + "a" * 64 + "\n",
                encoding="utf-8",
            )
            home = Path(temporary) / "home with spaces"
            gradle = home / ".gradle/wrapper/dists/gradle-8.10.2-bin/cache/gradle-8.10.2/bin/gradle"
            gradle.parent.mkdir(parents=True)
            gradle.touch()
            java = Path(temporary) / "JDK 17 with spaces/bin/java"
            java.parent.mkdir(parents=True)
            java.touch()
            node = str(Path(temporary) / "Node Install with spaces/node")
            chromium = Path(temporary) / "Browser Cache with spaces/chrome"
            chromium.parent.mkdir(parents=True)
            chromium.touch()
            for suite in doctor.WEB_SUITES:
                path = root / suite
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            seen = []

            def probe(argv, **_kwargs):
                seen.append(argv)
                if argv[-1] == "-version":
                    return {"status": "available", "detail": "probe_passed", "output": 'openjdk version "17.0.16"'}
                if argv[-1] == "--version":
                    return {"status": "available", "detail": "probe_passed", "output": "v22.17.0"}
                return {"status": "available", "detail": "probe_passed",
                        "output": '{"resolved":true,"nodeEngine":">=18"}'}

            report = doctor.build_report(
                root,
                env={
                    "JAVA_HOME": str(java.parent.parent),
                    "ANDROID_HOME": str(sdk),
                    "PH_BROWSER_EXECUTABLE": str(chromium),
                },
                platform="darwin",
                version_info=python312(),
                version_lookup=lambda _name: "1.2.3",
                which=lambda name: node if name == "node" else None,
                probe=probe,
                home=home,
            )
        checks = report["checks"]
        profiles = {item["name"]: item for item in report["profiles"]}
        self.assertEqual("available", profiles["android"]["status"])
        self.assertEqual("available", profiles["web"]["status"])
        self.assertEqual("available", checks["android_sdk34"]["status"])
        self.assertEqual("available", checks["playwright_module"]["status"])
        self.assertEqual("available", checks["gradle_wrapper_cache"]["status"])
        self.assertEqual(node, seen[0][0])
        self.assertEqual(str(java), seen[1][0])
        self.assertTrue(all(isinstance(arg, str) for argv in seen for arg in argv))

    def test_probe_timeout_failure_and_output_are_bounded(self):
        class TimedProcess:
            stdout = io.BytesIO(b"")

            def wait(self, timeout=None):
                if timeout is not None:
                    self.assert_timeout = timeout
                    raise subprocess.TimeoutExpired(["java", "-version"], timeout)
                return -9

            def kill(self):
                pass

        def timeout_factory(_argv, **kwargs):
            self.assertEqual(subprocess.PIPE, kwargs["stdout"])
            return TimedProcess()

        timed_out = doctor._run_probe(["java", "-version"], popen_factory=timeout_factory)
        self.assertEqual("unverified", timed_out["status"])
        self.assertEqual("probe_timed_out", timed_out["detail"])

        class FailedProcess:
            stdout = io.BytesIO(("SENTINEL" * 2000).encode())

            @staticmethod
            def wait(timeout=None):
                return 1

        failed = doctor._run_probe(
            ["node", "--version"], popen_factory=lambda *_a, **_k: FailedProcess()
        )
        self.assertEqual("unverified", failed["status"])
        self.assertEqual(doctor.MAX_PROBE_OUTPUT, len(failed["output"]))
        self.assertTrue(failed["truncated"])

        class OversizedSuccessfulProcess:
            stdout = io.BytesIO(b"v22.17.0" + b"x" * (doctor.MAX_PROBE_OUTPUT + 32))

            @staticmethod
            def wait(timeout=None):
                return 0

        oversized_result = doctor._run_probe(
            ["node", "--version"],
            popen_factory=lambda *_a, **_k: OversizedSuccessfulProcess(),
        )
        self.assertEqual("available", oversized_result["status"])
        self.assertTrue(oversized_result["truncated"])
        oversized = doctor._node_check(
            {}, lambda _name: "node", lambda *_a, **_k: oversized_result
        )[0]
        self.assertEqual("unverified", oversized["status"])
        self.assertEqual("node_probe_output_truncated", oversized["detail"])

    def test_failed_and_unreadable_version_probes_are_unverified(self):
        result = doctor._node_check(
            {},
            lambda _name: "/path that must not print/node",
            lambda *_args, **_kwargs: {"status": "unverified", "detail": "probe_timed_out"},
        )[0]
        self.assertEqual("unverified", result["status"])
        unreadable = doctor._node_check(
            {},
            lambda _name: "node",
            lambda *_args, **_kwargs: {"status": "available", "output": "not a version"},
        )[0]
        self.assertEqual("unverified", unreadable["status"])

    def test_sdk_and_wrapper_require_real_components_and_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = make_root(Path(temporary) / "repo")
            sdk = Path(temporary) / "sdk"
            (sdk / "platforms/android-34").mkdir(parents=True)
            (sdk / "platforms/android-34/android.jar").touch()
            build_tools = sdk / "build-tools/34.0.0"
            build_tools.mkdir(parents=True)
            (build_tools / "aapt2").touch()
            partial = doctor._sdk_check({"ANDROID_HOME": str(sdk)}, "darwin", Path(temporary))
            self.assertEqual("missing", partial["build_tools_34"])
            self.assertEqual("missing", partial["build_tools_components"]["d8"])

            android = root / "clients/android/android"
            (android / "gradlew").touch()
            properties = android / "gradle/wrapper/gradle-wrapper.properties"
            properties.write_text(
                "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.10.2-bin.zip\n"
                "distributionSha256Sum=bad\n",
                encoding="utf-8",
            )
            status, _ = doctor._wrapper_check(root, "darwin")
            self.assertEqual("missing", status["status"])
            (android / "gradle/wrapper/gradle-wrapper.jar").touch()
            status, _ = doctor._wrapper_check(root, "darwin")
            self.assertEqual("unverified", status["status"])
            properties.write_text(
                "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.10.2-bin.zip\n"
                "distributionSha256Sum=" + "a" * 64 + "\n",
                encoding="utf-8",
            )
            status, version = doctor._wrapper_check(root, "darwin")
            self.assertEqual("available", status["status"])
            self.assertEqual("8.10.2", version)

    def test_playwright_node_engine_must_be_known_supported_and_satisfied(self):
        probe = lambda *_a, **_k: {
            "status": "available", "output": '{"resolved":true,"nodeEngine":">=18.12.3"}'
        }
        node_status = {"status": "available", "version": "20.0.0"}
        self.assertEqual("available", doctor._playwright_check(
            Path("server/tests/security"), {}, "node", node_status, probe
        )["status"])
        old_node = {"status": "available", "version": "18.12.2"}
        self.assertEqual("missing", doctor._playwright_check(
            Path("server/tests/security"), {}, "node", old_node, probe
        )["status"])
        exact_node = {"status": "available", "version": "18.12.3"}
        self.assertEqual("available", doctor._playwright_check(
            Path("server/tests/security"), {}, "node", exact_node, probe
        )["status"])
        unknown = lambda *_a, **_k: {
            "status": "available", "output": '{"resolved":true,"nodeEngine":null}'
        }
        self.assertEqual("unverified", doctor._playwright_check(
            Path("server/tests/security"), {}, "node", node_status, unknown
        )["status"])

    def test_absolute_playwright_module_path_with_spaces_reads_package_engine(self):
        node = doctor.shutil.which("node")
        if not node:
            self.skipTest("Node.js is optional and not installed")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server = root / "server tests with spaces"
            server.mkdir()
            module = root / "Playwright Module with spaces"
            module.mkdir()
            (module / "package.json").write_text(
                '{"name":"playwright-core","version":"1.0.0",'
                '"main":"index.js","engines":{"node":">=999.0.0"}}',
                encoding="utf-8",
            )
            (module / "index.js").write_text("module.exports = {};\n", encoding="utf-8")
            node_status = doctor._node_check(
                {}, lambda _name: node, doctor._run_probe
            )[0]
            status = doctor._playwright_check(
                server,
                {"PLAYWRIGHT_MODULE": str(module), "PATH": os.environ.get("PATH", "")},
                node,
                node_status,
                doctor._run_probe,
            )
        self.assertEqual("missing", status["status"])
        self.assertEqual("node_below_playwright_minimum", status["detail"])
        self.assertEqual("999.0.0", status["required_node_version"])

    def test_windows_sdk_requires_native_executable_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            sdk = Path(temporary) / "SDK with spaces"
            (sdk / "platforms/android-34").mkdir(parents=True)
            (sdk / "platforms/android-34/android.jar").touch()
            build_tools = sdk / "build-tools/34.0.0"
            (build_tools / "lib").mkdir(parents=True)
            for name in ("aapt2.exe", "d8.bat", "zipalign.exe", "lib/apksigner.jar"):
                (build_tools / name).touch()
            checked = doctor._sdk_check({"ANDROID_HOME": str(sdk)}, "win32", Path(temporary))
        self.assertEqual("available", checked["status"])

    def test_native_probes_receive_only_needed_environment_values(self):
        received = []

        def probe(argv, **kwargs):
            received.append((argv, kwargs.get("env", {})))
            output = 'openjdk version "17.0.16"' if argv[-1] == "-version" else "v22.17.0"
            return {"status": "available", "detail": "probe_passed", "output": output}

        with tempfile.TemporaryDirectory() as temporary:
            jdk = Path(temporary) / "JDK 17"
            (jdk / "bin").mkdir(parents=True)
            (jdk / "bin/java").touch()
            env = {
                "PATH": "/safe/bin",
                "JAVA_HOME": str(jdk),
                "NODE_PATH": "/existing/node modules",
                "PRIVATE_TOKEN": "DO_NOT_FORWARD_THIS",
            }
            doctor._java_check(env, lambda _name: "java", probe, "darwin")
            doctor._node_check(env, lambda _name: "/Node Install/node", probe)
        for _argv, child_env in received:
            self.assertNotIn("PRIVATE_TOKEN", child_env)
            self.assertEqual("/safe/bin", child_env["PATH"])
        self.assertEqual("/existing/node modules", received[1][1]["NODE_PATH"])

    def test_malformed_lock_and_mismatched_or_missing_versions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = make_root(Path(temporary) / "malformed", "pip install something\n")
            malformed = doctor._package_checks(root, "darwin", lambda _name: "1.2.3")
            self.assertEqual("unverified", malformed["status"])
            self.assertNotIn("pip install", json.dumps(malformed))

            valid = make_root(Path(temporary) / "versions")

            def lookup(name):
                if name == "alpha":
                    return "9.9.9"
                raise metadata.PackageNotFoundError(name)

            checked = doctor._package_checks(valid, "darwin", lookup)
            self.assertEqual("missing", checked["status"])
            self.assertEqual("missing", checked["packages"][0]["status"])
            self.assertEqual("9.9.9", checked["packages"][0]["installed_version"])

    def test_conflicting_environment_is_unverified_and_never_printed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = make_root(Path(temporary) / "repo")
            secret = "SECRET_PRIVATE_PATH_91"
            report = doctor.build_report(
                root,
                env={
                    "JAVA_HOME": f"/{secret}/jdk",
                    "ANDROID_HOME": f"/{secret}/sdk-one",
                    "ANDROID_SDK_ROOT": f"/{secret}/sdk-two",
                    "PH_BROWSER_EXECUTABLE": f"/{secret}/chrome",
                    "PLAYWRIGHT_MODULE": secret,
                    "PRIVATE_TOKEN": secret,
                },
                platform="linux",
                version_info=python312(),
                version_lookup=lambda _name: "1.2.3",
                which=lambda _name: None,
                probe=lambda *_args, **_kwargs: {"status": "unverified", "detail": "probe_failed"},
                home=root / "home",
            )
            text = doctor.format_text(report)
            encoded = json.dumps(report)
        self.assertEqual("unverified", report["checks"]["android_sdk34"]["status"])
        self.assertNotIn(secret, text)
        self.assertNotIn(secret, encoded)
        self.assertNotIn("PRIVATE_TOKEN", text)
        self.assertNotIn("PRIVATE_TOKEN", encoded)

    def test_cli_json_and_text_are_both_read_only_reports(self):
        checks = {
            key: {"status": "available", "detail": "detected"}
            for key in (
                "python312", "cpu_dependencies", "node", "jdk17", "android_sdk34",
                "gradle_wrapper", "gradle_wrapper_cache", "playwright_module",
                "chromium_cache", "web_suite_files",
            )
        }
        checks["cpu_dependencies"].update({"package_count": 1, "matching_count": 1})
        report = {
            "tool": "PhotoHouse development doctor",
            "read_only": True,
            "meaning": "prerequisite availability only; no tests or builds were run",
            "profiles": [{"name": "api", "status": "available", "requirement": "required CPU profile"}],
            "checks": checks,
        }
        with mock.patch.object(doctor, "build_report", return_value=report):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, doctor.main(["--json"]))
            self.assertEqual(report, json.loads(output.getvalue()))
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, doctor.main([]))
            self.assertIn("no tests/builds run", output.getvalue())


if __name__ == "__main__":
    unittest.main()
