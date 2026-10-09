from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import check


class AndroidCommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.project = self.root / "clients" / "android" / "android"
        self.project.mkdir(parents=True)

    def tearDown(self):
        self.temporary.cleanup()

    def _dispatch(self, platform, wrapper):
        (self.project / wrapper).touch()
        with mock.patch.object(check, "ROOT", self.root), \
                mock.patch.object(check.sys, "platform", platform), \
                mock.patch.object(check, "run") as run:
            check.android()
        return run

    def test_windows_dispatch_uses_batch_wrapper_through_fixed_cmd(self):
        run = self._dispatch("win32", "gradlew.bat")

        run.assert_called_once_with(
            ["cmd.exe", "/d", "/c", "gradlew.bat", "--no-daemon", "--console=plain",
             *check.ANDROID_TASKS],
            cwd=self.project,
        )

    def test_unix_dispatch_uses_shell_wrapper(self):
        run = self._dispatch("linux", "gradlew")

        run.assert_called_once_with(
            ["sh", "gradlew", "--no-daemon", "--console=plain", *check.ANDROID_TASKS],
            cwd=self.project,
        )

    def test_missing_platform_wrapper_is_rejected(self):
        (self.project / "gradlew").touch()

        with self.assertRaisesRegex(SystemExit, "missing gradlew.bat"):
            check.android_command(self.project, "win32")


class CpuEnvironmentTests(unittest.TestCase):
    def test_live_settings_and_python_plugin_inputs_are_not_forwarded(self):
        inherited = {"PATH": "synthetic-path", "HOME": "synthetic-home",
                     "DATABASE_URL": "sqlite:///synthetic-production",
                     "PHOTOHOUSE_MEMORY_GENERATION_ENABLED": "true",
                     "OLLAMA_HOST": "synthetic-provider", "CAPTION_EXTERNAL_DIR": "synthetic-model",
                     "PYTHONPATH": "synthetic-modules", "PYTEST_PLUGINS": "synthetic_plugin",
                     "PYTEST_ADDOPTS": "--synthetic-opt-in", "LD_PRELOAD": "synthetic-loader"}
        with mock.patch.dict(check.os.environ, inherited, clear=True):
            actual = check.cpu_environment()
            self.assertEqual(dict(check.os.environ), inherited)
        self.assertEqual(actual, {"PATH": "synthetic-path", "HOME": "synthetic-home",
            "PHOTOHOUSE_NO_DOTENV": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"})

    def test_windows_platform_basics_are_preserved_case_insensitively(self):
        inherited = {"SystemRoot": "synthetic-windows", "COMSPEC": "synthetic-cmd",
                     "PATHEXT": ".EXE;.BAT", "TEMP": "synthetic-temp", "localappdata": "synthetic-appdata"}
        with mock.patch.dict(check.os.environ, inherited, clear=True):
            actual = check.cpu_environment()
        for name, value in inherited.items(): self.assertEqual(actual[name], value)
        self.assertEqual(actual["PHOTOHOUSE_NO_DOTENV"], "1")

    def test_pytest_receives_only_the_generated_cpu_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);tests = root / "server" / "tests" / "security";tests.mkdir(parents=True)
            (tests / "test_synthetic.py").touch()
            with mock.patch.object(check, "ROOT", root), mock.patch.object(check, "run") as run, \
                    mock.patch.dict(check.os.environ, {"PHOTOHOUSE_LIVE_TOKEN": "synthetic-token"}, clear=True):
                check.api_tests(("test_synthetic.py",))
            self.assertEqual(run.call_args.kwargs["cwd"], root / "server")
            env = run.call_args.kwargs["env"]
            self.assertNotIn("PHOTOHOUSE_LIVE_TOKEN", env)
            self.assertEqual(env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"], "1")
            self.assertIn("--noconftest", run.call_args.args[0])

    def test_demo_uses_the_same_environment_after_api_checks(self):
        with mock.patch.object(check, "api_tests") as tests, mock.patch.object(check, "run") as run, \
                mock.patch.dict(check.os.environ, {"ASR_URL": "synthetic-provider"}, clear=True):
            check.api()
        tests.assert_called_once_with(check.API_TESTS, include_runtime_paths=True)
        self.assertEqual(run.call_args.args[0][-1], "examples/generated-demo/check_demo.py")
        self.assertNotIn("ASR_URL", run.call_args.kwargs["env"])
        self.assertEqual(run.call_args.kwargs["env"]["PHOTOHOUSE_NO_DOTENV"], "1")


class WebProfileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for relative in check.WEB_TESTS:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()

    def tearDown(self):
        self.temporary.cleanup()

    def test_web_bridges_keep_toolchain_paths_without_live_or_preload_settings(self):
        tools = {"PLAYWRIGHT_MODULE_PATH": "/existing/playwright", "PLAYWRIGHT_BROWSERS_PATH": "/existing/browser",
                 "PH_BROWSER_PYTHON": "/existing/python", "PH_BROWSER_EXECUTABLE": "/existing/chromium",
                 "PH_BROWSER_ARTIFACTS": str(self.root / "captures"), "NODE_PATH": "/existing/node-modules"}
        inherited = {**tools, "PATH": "synthetic-path", "DATABASE_URL": "synthetic-live-db",
                     "PHOTOHOUSE_MEMORY_GENERATION_ENABLED": "true", "ASR_URL": "synthetic-provider",
                     "PHOTOHOUSE_LIVE_TOKEN": "synthetic-token", "PYTHONPATH": "synthetic-live-code",
                     "PYTEST_PLUGINS": "synthetic-plugin", "NODE_OPTIONS": "--require synthetic-preload",
                     "LD_PRELOAD": "synthetic-loader"}
        with mock.patch.object(check, "ROOT", self.root), \
                mock.patch.object(check.shutil, "which", return_value="/existing/node"), \
                mock.patch.object(check, "run") as run, \
                mock.patch.dict(check.os.environ, inherited, clear=True):
            check.web()
            self.assertEqual(dict(check.os.environ), inherited)
        for call in run.call_args_list:
            env = call.kwargs["env"]
            for key, value in tools.items():
                if key != "PH_BROWSER_ARTIFACTS": self.assertEqual(env[key], value)
            self.assertEqual(env["PLAYWRIGHT_MODULE"], tools["PLAYWRIGHT_MODULE_PATH"])
            self.assertEqual(env["PHOTOHOUSE_NO_DOTENV"], "1")
            for key in inherited.keys() - tools.keys() - {"PATH"}:
                self.assertNotIn(key, env)

    def test_web_dispatch_includes_saved_edition_shelf_suite(self):
        shelf = "server/tests/security/test_memory_book_edition_shelf_browser.cjs"
        self.assertIn(shelf, check.WEB_TESTS)
        self.assertIn("server/tests/security/test_assistant_turn_trail_browser.cjs", check.WEB_TESTS)
        with mock.patch.object(check, "ROOT", self.root), \
                mock.patch.object(check.shutil, "which", return_value="/existing/node"), \
                mock.patch.object(check, "run") as run, \
                mock.patch.dict(check.os.environ, {"PLAYWRIGHT_MODULE": "/existing/playwright"}, clear=True):
            check.web()

        self.assertEqual(run.call_count, len(check.WEB_TESTS))
        calls = {Path(call.args[0][1]).relative_to(self.root).as_posix(): call for call in run.call_args_list}
        self.assertIn(shelf, calls)
        env = calls[shelf].kwargs["env"]
        self.assertEqual(env["PLAYWRIGHT_MODULE"], "/existing/playwright")
        self.assertEqual(env["PLAYWRIGHT_MODULE_PATH"], "/existing/playwright")
        self.assertEqual(env["PH_BROWSER_PYTHON"], check.sys.executable)

    def test_web_dispatch_includes_edition_source_inspector_suite(self):
        source = "server/tests/security/test_memory_book_edition_sources_browser.cjs"
        self.assertIn(source, check.WEB_TESTS)
        with mock.patch.object(check, "ROOT", self.root), \
                mock.patch.object(check.shutil, "which", return_value="/existing/node"), \
                mock.patch.object(check, "run") as run:
            check.web()
        self.assertEqual(run.call_count, len(check.WEB_TESTS))
        calls = {Path(call.args[0][1]).relative_to(self.root).as_posix(): call
                 for call in run.call_args_list}
        self.assertIn(source, calls)
        self.assertEqual(calls[source].kwargs["env"]["PH_BROWSER_PYTHON"], check.sys.executable)

    def test_missing_saved_edition_shelf_suite_stops_before_node(self):
        shelf = "server/tests/security/test_memory_book_edition_shelf_browser.cjs"
        (self.root / shelf).unlink()
        with mock.patch.object(check, "ROOT", self.root), \
                mock.patch.object(check.shutil, "which") as which:
            with self.assertRaisesRegex(SystemExit, "Web profile unavailable; missing generated-data suite"):
                check.web()
        which.assert_not_called()

    def test_missing_edition_source_inspector_suite_stops_before_node(self):
        source = "server/tests/security/test_memory_book_edition_sources_browser.cjs"
        (self.root / source).unlink()
        with mock.patch.object(check, "ROOT", self.root), \
                mock.patch.object(check.shutil, "which") as which:
            with self.assertRaisesRegex(SystemExit, "Web profile unavailable; missing generated-data suite"):
                check.web()
        which.assert_not_called()

    def test_web_artifact_records_survive_later_suites(self):
        artifacts = self.root / "synthetic captures"

        def record(_args, *, env):
            directory = Path(env["PH_BROWSER_ARTIFACTS"])
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "result.json").write_text(Path(_args[1]).stem)

        with mock.patch.object(check, "ROOT", self.root), \
                mock.patch.object(check.shutil, "which", return_value="/existing/node"), \
                mock.patch.object(check, "run", side_effect=record), \
                mock.patch.dict(check.os.environ, {"PH_BROWSER_ARTIFACTS": str(artifacts)}, clear=True):
            check.web()

        self.assertEqual(len(list(artifacts.glob("*/result.json"))), len(check.WEB_TESTS))
        for relative in check.WEB_TESTS:
            name = Path(relative).stem
            self.assertEqual((artifacts / name / "result.json").read_text(), name)


if __name__ == "__main__":
    unittest.main()
