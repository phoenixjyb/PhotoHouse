"""Mocked Cargo target routing; tests never execute Cargo or write artifacts."""
import importlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from rust import build_literal_kernel, build_paths, build_vector_kernel


class CargoTargetSelectionTests(unittest.TestCase):
    def test_cli_overrides_environment_and_default_remains_crate_target(self):
        crate = Path("/private/work/rust/literal-python")
        env = {"CARGO_TARGET_DIR": "/private/shared/cargo-target"}
        self.assertEqual(build_paths.selected_target(crate, "/private/explicit", env),
                         Path("/private/explicit"))
        self.assertEqual(build_paths.selected_target(crate, None, env),
                         Path("/private/shared/cargo-target"))
        self.assertEqual(build_paths.selected_target(crate, None, {}), crate / "target")

    def test_importing_builders_has_no_build_or_filesystem_effect(self):
        with patch("subprocess.run") as run, patch.object(Path, "mkdir") as mkdir:
            importlib.reload(build_literal_kernel)
            importlib.reload(build_vector_kernel)
        run.assert_not_called()
        mkdir.assert_not_called()

    def test_both_builders_pass_selected_dir_to_cargo_and_read_artifact_from_it(self):
        cases = (
            (build_literal_kernel, "photohouse_literal_kernel.so", "NEW_LITERAL_EXTENSION_BUILT_NOT_ACTIVATED"),
            (build_vector_kernel, "photohouse_vector_kernel.so", "LOCAL_EXTENSION_BUILT"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "shared-cargo-target"
            for module, filename, expected_status in cases:
                run = Mock()
                copyfile = Mock()
                crate = root / "rust" / ("literal-python" if "literal" in filename else "vector-python")
                with patch.object(Path, "mkdir") as mkdir:
                    result = module.build(selected, environ={"CARGO_TARGET_DIR": str(root / "ambient")},
                                         run=run, copyfile=copyfile, root=root, crate=crate)
                mkdir.assert_called_once_with(exist_ok=True)
                run.assert_called_once_with(
                    [module.shutil.which("cargo") or str(Path.home() / ".cargo/bin/cargo"),
                     "build", "--release", "--locked", "--offline", "--manifest-path",
                     str(crate / "Cargo.toml"), "--target-dir", str(selected)],
                    check=True, env=unittest.mock.ANY,
                )
                env = run.call_args.kwargs["env"]
                if module is build_literal_kernel:
                    self.assertEqual(env["PYO3_PYTHON"], sys.executable)
                copyfile.assert_called_once_with(selected / "release" / module._extension_name(),
                                                 selected / "python" / filename)
                self.assertEqual(result["status"], expected_status)
                reported = selected / "python" / filename if module is build_literal_kernel else selected / "python"
                self.assertEqual(result["output"], str(reported))

    def test_windows_route_refusal_precedes_cargo_mkdir_and_copy(self):
        for module in (build_literal_kernel, build_vector_kernel):
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as directory:
                run = Mock()
                copyfile = Mock()
                with patch.object(module, "validate_windows_paths", side_effect=SystemExit("D: refused")), \
                        patch.object(Path, "mkdir") as mkdir:
                    with self.assertRaisesRegex(SystemExit, "D: refused"):
                        module.build(Path(directory) / "target", environ={}, run=run,
                                     copyfile=copyfile, root=Path(directory),
                                     crate=Path(directory) / "crate")
                run.assert_not_called()
                copyfile.assert_not_called()
                mkdir.assert_not_called()

    def test_windows_actual_route_checks_direct_volume_and_privacy(self):
        # Exercise the wrapper's real gate without pretending POSIX fixtures
        # prove native Windows ACLs or volume APIs (those helpers own that proof).
        class WindowsDirectory:
            def __init__(self, text):
                self.text = text
                self.drive = text[:2]
            def exists(self):
                return True
        storage = SimpleNamespace(direct=Mock(), volume=Mock())
        privacy = SimpleNamespace(require_private_directory=Mock())
        root, target = WindowsDirectory('D:/source'), WindowsDirectory('D:/cache')
        env = {'CARGO_HOME': 'D:/cargo', 'TEMP': 'D:/tmp', 'TMP': 'D:/tmp'}
        with patch.object(build_paths, 'os', SimpleNamespace(name='nt', environ=env)), \
                patch.object(build_paths, 'Path', WindowsDirectory), \
                patch.object(build_paths, '_storage_helpers', return_value=(storage, privacy)):
            build_paths.validate_windows_paths(root, target, env)
            self.assertEqual(storage.direct.call_count, 5)
            self.assertEqual(storage.volume.call_count, 5)
            self.assertEqual(privacy.require_private_directory.call_count, 4)
            storage.volume.side_effect = ValueError('system_volume_refused')
            with self.assertRaises(SystemExit):
                build_paths.validate_windows_paths(root, target, env)
            storage.volume.side_effect = None
            storage.direct.side_effect = ValueError('reparse_path_refused')
            with self.assertRaises(SystemExit):
                build_paths.validate_windows_paths(root, target, env)
            storage.direct.side_effect = None
            with self.assertRaises(SystemExit):
                build_paths.validate_windows_paths(root, WindowsDirectory('C:/cache'), env)


if __name__ == "__main__":
    unittest.main()
