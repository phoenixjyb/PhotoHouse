"""Synthetic SQLite coverage for immutable authored family annotations."""
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

OLD_HEAD = 'a8d4c2e6f901'
POLICY_HEAD = 'c3f7a91d5e20'
ANNOTATION_HEAD = 'd4a7e3c9b821'
CURRENT_HEAD = 'f7c3a9d2e614'


def config():
    cfg = Config()
    cfg.set_main_option('script_location', str(ROOT / 'backend/migrations'))
    return cfg


class FamilyAnnotationMigrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-annotations-')
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

    def test_current_head_preserves_a8_uploads_through_c3_c4(self):
        self.assertEqual(ScriptDirectory.from_config(config()).get_heads(), [CURRENT_HEAD])
        self.upgrade(OLD_HEAD)
        with self.engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO access_accounts(id,phone_login,password_hash,state) "
                "VALUES('owner','+12025550101','synthetic','active')")
            connection.exec_driver_sql("INSERT INTO access_libraries(id,state,bootstrap_operator) "
                "VALUES('family','active','owner')")
            connection.exec_driver_sql("INSERT INTO assets(id,path,hash_sha256) VALUES(1,'synthetic/a.jpg','h')")
            connection.exec_driver_sql("INSERT INTO access_uploads(id,asset_id,account_id,incoming_label,batch,"
                "original_name,sha256,bytes,state,created_at) "
                "VALUES(1,1,'owner','owner','b','a.jpg','h',10,'incoming',1)")

        self.upgrade(POLICY_HEAD)
        with self.engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO access_upload_auto_policies "
                "(library_id,account_id,revision,enabled_by,updated_at) "
                "VALUES('family','owner',1,'owner',2)")
        self.upgrade()
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql(
                'SELECT version_num FROM alembic_version').scalar_one(), CURRENT_HEAD)
            self.assertEqual(connection.exec_driver_sql(
                'SELECT destination_library_id,approval_mode FROM access_uploads').all(), [(None, None)])
            self.assertEqual(connection.exec_driver_sql(
                'SELECT enabled,revision FROM access_upload_auto_policies').all(), [(0, 1)])
            context = MigrationContext.configure(connection, opts={
                'include_object': lambda obj, name, kind, reflected, compare_to:
                    kind != 'table' or name.startswith('access_'),
                'compare_server_default': True})
            self.assertEqual(compare_metadata(context, migration_metadata(Base.metadata)), [])
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])

    def test_original_validation_derivation_states_and_immutability(self):
        self.upgrade()
        with self.engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO access_accounts(id,phone_login,password_hash,state) "
                "VALUES('owner','+12025550101','synthetic','active')")
            connection.exec_driver_sql("INSERT INTO access_libraries(id,state,bootstrap_operator) "
                "VALUES('family','active','owner')")
            valid = ("'note','owner','family',?,'text','hello',NULL,NULL,NULL,"
                     "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',"
                     "'en',1,'mutation','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',1")
            connection.exec_driver_sql("INSERT INTO access_upload_annotations "
                "(id,author_id,library_id,batch,kind,original_text,original_audio,mime,duration_ms,"
                "sha256,language,consent,mutation_id,request_digest,created_at) VALUES(" + valid + ")",
                ('0123456789abcdef0123456789abcdef',))
            connection.exec_driver_sql("INSERT INTO access_annotation_derivations "
                "(annotation_id,revision,state,created_at,updated_at) VALUES('note',1,'held',1,1)")
            connection.exec_driver_sql("INSERT INTO access_annotation_tag_proposals "
                "(annotation_id,tag,status,revision) VALUES('note','garden','proposed',1)")
            self.assertEqual(connection.exec_driver_sql(
                'SELECT state FROM access_annotation_derivations').scalar_one(), 'held')

        with self.assertRaises(Exception):
            with self.engine.begin() as connection:
                connection.exec_driver_sql("UPDATE access_upload_annotations SET original_text='edited' WHERE id='note'")

        bad_rows = [
            # Text exceeds the 16 KiB UTF-8 source bound.
            ("'large','owner','family','0123456789abcdef0123456789abcdef','text',?,NULL,NULL,NULL,"
             "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','en',0,'mutation-2',"
             "'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',2", ('x' * 16385,)),
            # Invalid language and wrong text/audio field combination.
            ("'bad-language','owner','family','0123456789abcdef0123456789abcdef','text','hello',NULL,NULL,NULL,"
             "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','fr',0,'mutation-3',"
             "'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',2", ()),
        ]
        for values, params in bad_rows:
            with self.assertRaises(Exception):
                with self.engine.begin() as connection:
                    connection.exec_driver_sql("INSERT INTO access_upload_annotations "
                        "(id,author_id,library_id,batch,kind,original_text,original_audio,mime,duration_ms,"
                        "sha256,language,consent,mutation_id,request_digest,created_at) VALUES(" + values + ")", params)

        with self.assertRaises(Exception):
            with self.engine.begin() as connection:
                connection.exec_driver_sql("INSERT INTO access_annotation_derivations "
                    "(annotation_id,revision,state,created_at,updated_at) VALUES('note',2,'queued',2,2)")


if __name__ == '__main__':
    unittest.main()
