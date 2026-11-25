"""Actual byte reader with generated Windows pathname/handle stat semantics."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "server/backend/app/access/search_policy_binding.py"
spec = importlib.util.spec_from_file_location("generated_policy_source_identity", SOURCE)
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


def info(source, *, ctime, **changed):
    values = {key: getattr(source, key) for key in
              ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_mode")}
    values.update(st_ctime_ns=ctime, st_birthtime_ns=123456789)
    values.update(changed)
    return SimpleNamespace(**values)


class PolicySourceIdentityTests(unittest.TestCase):
    def test_windows_birthtime_matches_despite_ctime_alias_and_other_fields_refuse(self):
        with tempfile.TemporaryDirectory() as selected:
            path = Path(selected).resolve() / "source.py"
            content = b"# exact\r\n# byte \x1a remains\n"
            path.write_bytes(content)
            real = path.lstat()
            identity = subject._identity
            lstat = Path.lstat

            def path_info(item, *args, **kwargs):
                return info(real, ctime=100) if item == path else lstat(item, *args, **kwargs)

            with patch.object(Path, "lstat", path_info), \
                    patch.object(subject, "_identity", lambda value: identity(value, windows=True)):
                with patch.object(subject.os, "fstat", return_value=info(real, ctime=200)):
                    self.assertEqual(subject._read_source(path), content)
                # Every meaningful path/handle identity field remains mandatory.
                for key in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_birthtime_ns"):
                    with self.subTest(changed=key):
                        changed = info(real, ctime=200)
                        setattr(changed, key, getattr(changed, key) + 1)
                        with patch.object(subject.os, "fstat", return_value=changed):
                            with self.assertRaises(subject.QueryPolicyUnavailable):
                                subject._read_source(path)
                for birthtime in (None, True, 123.0):
                    with self.subTest(invalid_birthtime=birthtime):
                        changed = info(real, ctime=200, st_birthtime_ns=birthtime)
                        with patch.object(subject.os, "fstat", return_value=changed):
                            with self.assertRaises(subject.QueryPolicyUnavailable):
                                subject._read_source(path)
                missing = info(real, ctime=200)
                del missing.st_birthtime_ns
                with patch.object(subject.os, "fstat", return_value=missing):
                    with self.assertRaises(subject.QueryPolicyUnavailable):
                        subject._read_source(path)

    def test_posix_ctime_and_actual_replaced_inode_are_still_rejected(self):
        with tempfile.TemporaryDirectory() as selected:
            path = Path(selected).resolve() / "source.py"
            path.write_bytes(b"# unchanged bytes\n")
            real = path.lstat()
            self.assertNotEqual(subject._identity(info(real, ctime=100), windows=False),
                                subject._identity(info(real, ctime=200), windows=False))
            replacement = path.with_name("replacement.py")
            replacement.write_bytes(path.read_bytes())
            fstat = subject.os.fstat
            replaced = False

            def replace_after_open(fd):
                nonlocal replaced
                value = fstat(fd)
                if not replaced:
                    replaced = True
                    replacement.replace(path)
                return value

            # Windows disallows replacing some open handles. Generated Windows
            # metadata cases above cover its identity fields independently.
            if subject.os.name != "nt":
                with patch.object(subject.os, "fstat", replace_after_open):
                    with self.assertRaises(subject.QueryPolicyUnavailable):
                        subject._read_source(path)
                self.assertTrue(replaced)


if __name__ == "__main__":
    unittest.main()
