import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'approved_media_environment.py'
SPEC = importlib.util.spec_from_file_location('approved_media_environment', SCRIPT)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class MediaEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='approved-media-environment-')
        self.root = Path(self.temporary.name).resolve()
        self.bindings = {}
        for name in ('ffmpeg', 'ffprobe'):
            path = self.root / (name + '.exe')
            path.write_bytes(name.encode())
            path.chmod(0o700)
            self.bindings[name] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def tearDown(self):
        self.temporary.cleanup()

    def test_restricted_worker_can_find_bound_tools_without_changing_storage(self):
        before = {'PATH': str(self.root / 'interpreter'), 'TEMP': str(self.root / 'scratch'),
                  'TORCH_HOME': str(self.root / 'cache'), 'PROGRAMW6432': 'existing-program-folder'}
        result = module.bind_media_tools(before, self.bindings)
        self.assertEqual(shutil.which('ffmpeg.exe', path=result['PATH']), self.bindings['ffmpeg']['path'])
        self.assertEqual(result['FFPROBE_EXE'], self.bindings['ffprobe']['path'])
        for key in ('TEMP', 'TORCH_HOME', 'PROGRAMW6432'):
            self.assertEqual(result[key], before[key])
        self.assertEqual(before['PATH'], str(self.root / 'interpreter'))
        self.assertEqual(result['PATH'].split(os.pathsep).count(str(self.root)), 1)

    def test_changed_executable_is_refused_before_environment_is_returned(self):
        Path(self.bindings['ffmpeg']['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'media_tool_fingerprint_mismatch'):
            module.bind_media_tools({}, self.bindings)

    def test_relative_or_differently_named_program_is_not_selected(self):
        for invalid in ('ffmpeg.exe', str(self.root / 'other.exe')):
            with self.subTest(invalid=invalid):
                bindings = {**self.bindings, 'ffmpeg': {**self.bindings['ffmpeg'], 'path': invalid}}
                with self.assertRaisesRegex(ValueError, 'media_tool_path_invalid'):
                    module.bind_media_tools({}, bindings)

    def test_incomplete_binding_cannot_fall_back_to_unpinned_path(self):
        with self.assertRaisesRegex(ValueError, 'media_tool_binding_required'):
            module.bind_media_tools({'PATH': str(self.root)}, {'ffmpeg': self.bindings['ffmpeg']})
