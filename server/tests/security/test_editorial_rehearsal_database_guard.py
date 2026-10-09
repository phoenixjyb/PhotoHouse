"""Local SQLite URI admission; generated paths only, with no database opens."""
from pathlib import Path, PureWindowsPath
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from run_editorial_rehearsal_group import database_within, sqlite_uri_filename


class RehearsalDatabaseGuardTests(unittest.TestCase):
    def test_canonical_windows_uri_maps_to_local_drive_not_unc_authority(self):
        root = PureWindowsPath('C:/private/candidate')
        for uri in ('file:///C:/private/candidate/journal.sqlite?mode=rw',
                    'file:/C:/private/candidate/journal.sqlite?mode=ro',
                    'file:C:/private/candidate/journal.sqlite?mode=rwc',
                    'file://localhost/C:/private/candidate/journal.sqlite?mode=rw'):
            with self.subTest(uri=uri):
                path = PureWindowsPath(sqlite_uri_filename(uri, windows=True))
                self.assertEqual('C:', path.drive)
                self.assertTrue(path.is_relative_to(root))

    def test_encoded_unicode_space_and_filename_delimiters_are_decoded_once(self):
        uri = 'file:///C:/private/candidate/%E5%9B%9E%E5%BF%86%20%23%3F%252F.sqlite?mode=rw'
        self.assertEqual('C:/private/candidate/回忆 #?%2F.sqlite',
                         sqlite_uri_filename(uri, windows=True))

    def test_posix_drive_shaped_directory_retains_leading_slash(self):
        self.assertEqual('/C:/private/candidate/data.sqlite',
                         sqlite_uri_filename('file:///C:/private/candidate/data.sqlite', windows=False))

    def test_local_generated_paths_and_file_uris_are_admitted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / '回忆 #?.sqlite'
            for value in (path, str(path), bytes(path), path.as_uri() + '?mode=rw',
                          path.as_uri() + '?mode=ro&cache=private&immutable=1'):
                with self.subTest(value=value):
                    self.assertTrue(database_within(value, root))
            self.assertFalse(path.exists())

    def test_sibling_prefix_parent_traversal_and_other_drive_are_not_within_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / 'candidate'
            for value in (root.parent / 'candidate-other' / 'db.sqlite',
                          root / '..' / 'outside.sqlite',
                          (root / '..' / 'outside.sqlite').as_uri()):
                self.assertFalse(database_within(value, root))
        self.assertFalse(PureWindowsPath(sqlite_uri_filename(
            'file:///D:/private/candidate/db.sqlite', windows=True)).is_relative_to(
                PureWindowsPath('C:/private/candidate')))

    def test_percent_encoded_traversal_resolves_outside_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / 'candidate'
            self.assertFalse(database_within(root.as_uri() + '/%2e%2e/outside.sqlite?mode=rw', root))

    def test_remote_authorities_and_drive_relative_uris_are_rejected(self):
        for uri in ('file://server/share/db.sqlite', 'file://user@localhost/db.sqlite',
                    'file://localhost:123/db.sqlite', 'file:C:db.sqlite', 'file:///C:db.sqlite'):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                sqlite_uri_filename(uri, windows=True)

    def test_invalid_escapes_controls_and_encoded_backslashes_are_rejected(self):
        for path in ('file:/private/%', 'file:/private/%xy', 'file:/private/%00db',
                     'file:/private/%0adb', 'file:/private/%ffdb',
                     'file:/private/%5cdb', 'file:/private/\ndb', 'file:'):
            with self.subTest(path=path), self.assertRaises((ValueError, UnicodeError)):
                sqlite_uri_filename(path, windows=True)

    def test_auxiliary_file_vfs_and_duplicate_options_are_rejected(self):
        for query in ('modeof=/outside', 'vfs=unix-dotfile', 'mode=rw&mode=ro',
                      'mode=unknown', 'cache=unknown', 'immutable=', 'flag',
                      'mode=rw&cache=private&immutable=1&extra=1&extra2=2'):
            with self.subTest(query=query), self.assertRaises(ValueError):
                sqlite_uri_filename('file:/candidate/data.sqlite?' + query, windows=False)

    def test_memory_uris_are_exact_and_fragment_does_not_change_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.assertTrue(database_within(':memory:', root))
            self.assertTrue(database_within('file::memory:?cache=shared', root))
            self.assertFalse(database_within('file::memory:outside', root))
            path = root / 'db.sqlite'
            self.assertTrue(database_within(path.as_uri() + '?mode=ro#ignored', root))

    def test_symlink_to_outside_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / 'candidate'
            root.mkdir()
            outside = root.parent / 'outside.sqlite'
            outside.write_bytes(b'generated')
            link = root / 'db.sqlite'
            link.symlink_to(outside)
            self.assertFalse(database_within(link, root))
            self.assertFalse(database_within(link.as_uri() + '?mode=rw', root))

    def test_unsupported_path_types_are_rejected(self):
        for value in (None, 123, {}, []):
            self.assertFalse(database_within(value, Path('/candidate')))


if __name__ == '__main__':
    unittest.main()
