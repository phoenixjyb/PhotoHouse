"""Synthetic private-file and Windows DACL policy checks; no ACL mutations."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from app.access.private_storage import _acl_is_private, require_private_directory, require_private_file


class PrivateStorageTests(unittest.TestCase):
    def test_windows_policy_rejects_other_users_null_owner_and_unknown_aces(self):
        user = 'S-1-5-21-111-222-333-1001'
        private = [(0,0,user),(0,0,'S-1-5-18'),(0,0,'S-1-5-32-544')]
        self.assertTrue(_acl_is_private(user,user,private))
        self.assertTrue(_acl_is_private('S-1-5-32-544',user,private))
        for trustee in ('S-1-1-0','S-1-5-11','S-1-5-32-545','S-1-5-21-111-222-333-1002'):
            self.assertFalse(_acl_is_private(user,user,private+[(0,0,trustee)]))
        self.assertFalse(_acl_is_private('',user,private))
        self.assertFalse(_acl_is_private(user,user,private+[(9,0,user)]))
        self.assertTrue(_acl_is_private(user,user,private+[(1,0,'S-1-1-0')]))
        self.assertTrue(_acl_is_private(user,user,private+[(0,8,'S-1-3-0')]))
        self.assertFalse(_acl_is_private(user,user,private+[(0,0,'S-1-3-0')]))

    def test_owner_rights_is_accepted_only_for_an_already_trusted_owner(self):
        user = 'S-1-5-21-111-222-333-1001'
        private = [(0,0,'S-1-3-4'),(0,0,'S-1-5-18'),(0,0,'S-1-5-32-544')]
        for owner in (user, 'S-1-5-18', 'S-1-5-32-544'):
            for flags in (0, 0x10, 0x03):
                with self.subTest(owner=owner, flags=flags):
                    self.assertTrue(_acl_is_private(owner,user,[(0,flags,'S-1-3-4'),*private[1:]]))
        for owner in ('', 'S-1-1-0', 'S-1-5-21-111-222-333-1002'):
            self.assertFalse(_acl_is_private(owner,user,private))
        self.assertFalse(_acl_is_private(user,'',private))

    def test_owner_rights_does_not_allow_public_trustees_or_unknown_ace_types(self):
        user = 'S-1-5-21-111-222-333-1001'
        private = [(0,0,'S-1-3-4'),(0,0,'S-1-5-18'),(0,0,'S-1-5-32-544')]
        for trustee in ('S-1-1-0', 'S-1-5-11', 'S-1-5-32-545', 'S-1-5-21-111-222-333-1002'):
            self.assertFalse(_acl_is_private(user,user,private+[(0,0,trustee)]))
        for kind in (5, 9, 11):
            self.assertFalse(_acl_is_private(user,user,[(kind,0,'S-1-3-4'),*private[1:]]))

    @unittest.skipIf(os.name=='nt','POSIX filesystem mode behavior')
    def test_posix_private_modes_and_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            root.chmod(0o700)
            path=root/'ledger.sqlite';path.write_bytes(b'synthetic');path.chmod(0o600)
            require_private_directory(root);require_private_file(path)
            path.chmod(0o644)
            with self.assertRaises(ValueError):require_private_file(path)
            path.chmod(0o600)
            alias=root/'alias';alias.symlink_to(path)
            with self.assertRaises(ValueError):require_private_file(alias)
            alias.unlink();os.link(path,alias)
            with self.assertRaises(ValueError):require_private_file(path)
            alias.unlink();root.chmod(0o755)
            with self.assertRaises(ValueError):require_private_directory(root)

    def test_missing_and_relative_selection_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing=Path(tmp).resolve()/'missing'
            with self.assertRaises(ValueError):require_private_file(missing)
            self.assertFalse(missing.exists())
        with self.assertRaises(ValueError):require_private_directory(Path('relative'))


if __name__=='__main__':unittest.main()
