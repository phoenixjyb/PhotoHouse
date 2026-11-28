from contextlib import nullcontext
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import check_windows_storage, windows_work


class WindowsDependencyStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.work = self.root / 'work'
        self.work.mkdir()
        self.browser = self.root / 'server/tests/security/browser-tooling'
        self.browser.mkdir(parents=True)
        (self.browser / 'package-lock.json').write_text('{}', encoding='utf-8')
        (self.root / 'config').mkdir()
        (self.root / 'config/requirements-dev.lock').write_text('', encoding='utf-8')
        self.shell = {'PATH': 'developer tools', 'PIP_TARGET': 'C:/old-target',
                      'PIP_CACHE_DIR': 'C:/old-pip', 'npm_config_cache': 'C:/old-npm'}
        native = SimpleNamespace(name='nt', environ=self.shell, devnull=os.devnull)
        storage = windows_work.storage

        def private_child(parent, name):
            path = parent / name
            path.mkdir(exist_ok=True)
            return path

        self.enterContext(patch.object(windows_work, 'ROOT', self.root))
        self.enterContext(patch.object(windows_work, 'os', native))
        self.enterContext(patch.object(windows_work.sys, 'version_info', (3, 12, 8)))
        self.enterContext(patch.object(storage, 'work_root', return_value=self.work))
        self.volume = self.enterContext(patch.object(storage, 'volume'))
        self.space = self.enterContext(patch.object(storage, 'check_space', return_value={
            1: (self.root, 0)
        }))
        self.lock = self.enterContext(patch.object(storage, '_volume_lock', side_effect=lambda _: nullcontext()))
        self.enterContext(patch.object(storage, '_private_child', side_effect=private_child))
        self.enterContext(patch.object(windows_work, 'require_private_directory'))
        self.run = self.enterContext(patch.object(windows_work.subprocess, 'run'))

    def test_python_uses_scoped_pip_cache_and_creates_the_checkout_venv(self):
        venv = self.root / '.venv'
        interpreter = venv / 'Scripts/python.exe'
        cache = self.work / 'package-cache/pip'
        children = []

        def invoke(command, cwd, env, check):
            temporary = Path(env['TEMP'])
            self.assertTrue(temporary.is_dir())
            self.assertEqual(temporary.parent, cache)
            self.assertEqual(env['PIP_CACHE_DIR'], str(cache))
            self.assertEqual(env['PIP_CONFIG_FILE'], os.devnull)
            self.assertNotIn('PIP_TARGET', env)
            self.assertEqual(cwd, self.root)
            self.assertTrue(check)
            children.append(temporary)
            if 'venv' in command:
                interpreter.parent.mkdir(parents=True)
                interpreter.touch()
                (venv / 'pyvenv.cfg').touch()

        self.run.side_effect = invoke
        self.assertEqual(windows_work.main(['dependencies', 'python']), 0)
        self.assertEqual(windows_work.main(['dependencies', 'python']), 0)
        commands = [call.args[0] for call in self.run.call_args_list]
        self.assertEqual(commands[0][-3:], ['-m', 'venv', str(venv)])
        self.assertEqual(commands[1], commands[2])
        self.assertEqual(commands[1], [str(interpreter), '-I', '-m', 'pip', '--require-virtualenv',
                                      'install', '--require-hashes', '-r',
                                      str(self.root / 'config/requirements-dev.lock')])
        self.assertEqual(children[0], children[1])
        self.assertNotEqual(children[1], children[2])
        self.assertTrue(all(not child.exists() for child in children))
        self.assertEqual(self.shell['PIP_CACHE_DIR'], 'C:/old-pip')
        self.assertEqual(self.space.call_count, 4)
        self.assertEqual(self.lock.call_count, 2)

    def test_web_uses_locked_npm_install_and_leaves_the_shell_untouched(self):
        self.run.side_effect = subprocess.CalledProcessError(7, 'npm.cmd')
        self.assertEqual(windows_work.main(['dependencies', 'web']), 7)
        command = self.run.call_args.args[0]
        self.assertEqual(command, ['cmd.exe', '/d', '/c', 'npm.cmd', 'ci', '--ignore-scripts',
                                   '--no-audit', '--no-fund', '--global=false'])
        settings = self.run.call_args.kwargs
        self.assertEqual(settings['cwd'], self.browser)
        env = settings['env']
        cache = self.work / 'package-cache/npm'
        self.assertEqual(Path(env['NPM_CONFIG_CACHE']), cache)
        self.assertEqual(Path(env['NPM_CONFIG_LOGS_DIR']), cache / '_logs')
        self.assertEqual(Path(env['NPM_CONFIG_PREFIX']), self.browser)
        self.assertNotIn('npm_config_cache', env)
        self.assertEqual(self.shell['npm_config_cache'], 'C:/old-npm')
        self.assertEqual(Path(env['TMPDIR']).parent, cache)
        self.assertFalse(Path(env['TMPDIR']).exists())

    def test_refused_install_volume_leaves_cache_and_tools_idle(self):
        self.volume.side_effect = windows_work.storage.StorageRefused('system_volume_refused')
        with self.assertRaisesRegex(ValueError, 'system_volume_refused'):
            windows_work.setup_dependencies('web')
        self.assertFalse((self.work / 'package-cache').exists())
        self.run.assert_not_called()

    def test_generated_checks_override_inherited_npm_cache(self):
        env = check_windows_storage._environment({'npm_config_cache': 'C:/old-npm'}, self.work)
        self.assertEqual(Path(env['NPM_CONFIG_CACHE']), self.work / 'npm')
        self.assertNotIn('npm_config_cache', env)


if __name__ == '__main__':
    unittest.main()
