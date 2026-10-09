"""Synthetic SQLite coverage for the additive owner upload policy migration."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.db import Base
from app.access.metadata import migration_metadata

PRE_POLICY = 'a8d4c2e6f901'
POLICY_HEAD = 'c3f7a91d5e20'


def config():
    cfg = Config()
    cfg.set_main_option('script_location', str(ROOT / 'backend/migrations'))
    return cfg


class UploadAutoPolicyMigrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-upload-policy-')
        self.addCleanup(directory.cleanup)
        self.engine = create_engine('sqlite:///' + str(Path(directory.name) / 'synthetic.sqlite'))
        self.addCleanup(self.engine.dispose)
        for target in ('socket.socket.connect', 'socket.socket.bind', 'subprocess.Popen', 'os.system'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start()
            self.addCleanup(guard.stop)

    def upgrade(self, target='head'):
        with self.engine.begin() as connection:
            cfg = config()
            cfg.attributes['connection'] = connection
            command.upgrade(cfg, target)

    def test_revision_is_the_single_head(self):
        self.assertEqual(ScriptDirectory.from_config(config()).get_heads(), ['e6b2f8a1c903'])

    def test_existing_rows_stay_null_and_constraints_and_metadata_match(self):
        self.upgrade(PRE_POLICY)
        with self.engine.begin() as connection:
            self.assertNotIn('destination_library_id', {row[1] for row in
                connection.exec_driver_sql('PRAGMA table_info(access_uploads)')})
            self.assertNotIn('approval_mode', {row[1] for row in
                connection.exec_driver_sql('PRAGMA table_info(access_uploads)')})
            self.assertNotIn('destination_library_id', {row[1] for row in
                connection.exec_driver_sql('PRAGMA table_info(access_upload_transfers)')})
            connection.exec_driver_sql("INSERT INTO access_accounts(id,phone_login,password_hash,state) "
                "VALUES('owner','+12025550101','synthetic','active')")
            connection.exec_driver_sql("INSERT INTO access_libraries(id,state,bootstrap_operator) "
                "VALUES('family','active','owner')")
            connection.exec_driver_sql("INSERT INTO assets(id,path,hash_sha256) VALUES(1,'synthetic/a.jpg','h')")
            connection.exec_driver_sql("INSERT INTO access_uploads(id,asset_id,account_id,incoming_label,batch,"
                "original_name,sha256,bytes,state,created_at) VALUES(1,1,'owner','owner','b','a.jpg','h',10,'incoming',1)")
            connection.exec_driver_sql("INSERT INTO access_upload_transfers(id,account_id,request_id,batch,filename,"
                "bytes,sha256,kind,offset,state,asset_id,created_at) "
                "VALUES('transfer','owner','request','b','a.jpg',10,'h','image',0,'uploading',NULL,1)")

        self.upgrade()
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql(
                'SELECT destination_library_id,approval_mode FROM access_uploads').all(), [(None, None)])
            self.assertEqual(connection.exec_driver_sql(
                'SELECT destination_library_id FROM access_upload_transfers').all(), [(None,)])
            self.assertEqual(connection.exec_driver_sql(
                'SELECT enabled,revision,enabled_by,updated_at FROM access_upload_auto_policies').all(), [])
            columns = {c['name'] for c in inspect(connection).get_columns('access_uploads')}
            self.assertTrue({'destination_library_id', 'approval_mode'} <= columns)
            self.assertIn('destination_library_id', {c['name'] for c in
                inspect(connection).get_columns('access_upload_transfers')})
            context = MigrationContext.configure(connection, opts={
                'include_object': lambda obj, name, kind, reflected, compare_to:
                    kind != 'table' or name.startswith('access_'),
                'compare_server_default': True})
            diffs = compare_metadata(context, migration_metadata(Base.metadata))
            self.assertEqual(diffs, [])

    def test_policy_defaults_off_and_rejects_invalid_values_and_orphans(self):
        self.upgrade()
        with self.engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO access_accounts(id,phone_login,password_hash,state) "
                "VALUES('owner','+12025550101','synthetic','active')")
            connection.exec_driver_sql("INSERT INTO access_libraries(id,state,bootstrap_operator) "
                "VALUES('family','active','owner')")
            connection.exec_driver_sql("INSERT INTO assets(id,path,hash_sha256) VALUES(1,'synthetic/a.jpg','h')")
            connection.exec_driver_sql("INSERT INTO access_uploads(id,asset_id,account_id,incoming_label,batch,"
                "original_name,sha256,bytes,state,created_at) "
                "VALUES(1,1,'owner','owner','b','a.jpg','h',10,'incoming',1)")
            connection.exec_driver_sql("INSERT INTO access_upload_auto_policies "
                "(library_id,account_id,revision,enabled_by,updated_at) VALUES('family','owner',1,'owner',10)")
            self.assertEqual(connection.exec_driver_sql(
                "SELECT enabled FROM access_upload_auto_policies").scalar_one(), 0)
        for sql in (
            "UPDATE access_upload_auto_policies SET enabled=2",
            "UPDATE access_upload_auto_policies SET revision=0",
            "UPDATE access_uploads SET approval_mode='silent'",
            "INSERT INTO access_upload_auto_policies "
                "(library_id,account_id,revision,enabled_by,updated_at) "
                "VALUES('missing','owner',1,'owner',11)",
        ):
            with self.assertRaises(Exception):
                with self.engine.begin() as connection:
                    connection.exec_driver_sql(sql)


if __name__ == '__main__':
    unittest.main()
