"""Generated E7 worker qualification and bounded Windows launch contract."""
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import bounded_windows_job as controller
import qualify_memory_group_workers as qualification
from PIL import Image


class MemoryGroupWorkersQualificationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="group-workers-qualification-")
        self.addCleanup(temp.cleanup)
        self.parent = Path(temp.name).resolve()
        if os.name != "nt":
            self.parent.chmod(0o700)
        self.target = self.parent / "generated"
        self.ffmpeg = Path(shutil.which("ffmpeg") or "/missing/ffmpeg").resolve()
        self.ffprobe = Path(shutil.which("ffprobe") or "/missing/ffprobe").resolve()

    def test_actual_d1_to_e7_fixture_with_portable_worker_boundary(self):
        if not self.ffmpeg.is_file() or not self.ffprobe.is_file():
            self.skipTest("local ffmpeg and ffprobe are unavailable")
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:////must-never-open-live.sqlite"}), \
                patch("socket.socket.connect", side_effect=AssertionError("external connect")), \
                patch("socket.socket.bind", side_effect=AssertionError("external listener")), \
                patch.object(qualification, "_worker_once", side_effect=self._simulate_native_workers):
            report = qualification.run(self.target, self.ffmpeg, self.ffprobe)
        expected = qualification._fixture_report()
        expected.update(decoded_thumbnails=[{"width": 96, "height": 64},
                                            {"width": 96, "height": 64}])
        for key, value in qualification._fixture_report().items():
            if key not in {"decoded_thumbnails", "decoded_keyframes"}:
                self.assertEqual(report[key], value)
        self.assertGreaterEqual(report["decoded_keyframes"], 1)
        self.assertLessEqual(report["decoded_keyframes"], 32)
        self.assertEqual(report["decoded_thumbnails"], expected["decoded_thumbnails"])
        database = self.target / "primary.sqlite"
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                             qualification.TO)
            self.assertEqual(db.execute("SELECT count(*) FROM access_memory_groups").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM access_memory_group_revisions").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT type,state FROM tasks WHERE type IN ('thumb','phash','video_probe','video_keyframes') ORDER BY type").fetchall(),
                             [("phash", "finished"), ("thumb", "finished"),
                              ("video_keyframes", "finished"), ("video_probe", "finished")])
        self.assertEqual(json.loads((self.target / qualification.REPORT_NAME).read_text()), report)
        self.assertFalse((self.target / qualification.FAILURE_NAME).exists())
        self.assertTrue((self.target / "originals" / "synthetic.png").is_file())
        self.assertTrue((self.target / "originals" / "synthetic.mp4").is_file())

    def _simulate_native_workers(self, script, args, target, timeout):
        """Portable host cannot create the Windows Job required by real workers."""
        del timeout
        database = Path(args[args.index("--database") + 1])
        if script == "run_approved_cpu_worker.py":
            with closing(sqlite3.connect(database)) as db:
                pending = db.execute("SELECT type FROM tasks WHERE type IN ('thumb','phash') AND state='pending' ORDER BY priority,id LIMIT 1").fetchone()
                self.assertIsNotNone(pending)
                kind = pending[0]
                if kind == "thumb":
                    for edge in (256, 1024):
                        path = target / "derived" / "thumbnails" / str(edge) / "101.jpg"
                        path.parent.mkdir(parents=True, exist_ok=True)
                        Image.new("RGB", (96, 64), (30, 120, 170)).save(path, "JPEG")
                    db.execute("UPDATE tasks SET state='finished' WHERE type='thumb'")
                else:
                    db.execute("UPDATE assets SET perceptual_hash='0123456789abcdef' WHERE id=101")
                    db.execute("UPDATE tasks SET state='finished' WHERE type='phash'")
                db.commit()
            return
        with closing(sqlite3.connect(database)) as db:
            if db.execute("SELECT 1 FROM tasks WHERE type='video_probe' AND state='pending'").fetchone():
                db.execute("UPDATE assets SET duration_sec=2.0,width=128,height=72,fps=5.0 WHERE id=102")
                db.execute("UPDATE tasks SET state='finished' WHERE type='video_probe'")
                db.execute("INSERT INTO tasks(type,state,priority,payload_json) VALUES('video_keyframes','pending',70,'{\"asset_id\":102}')")
            else:
                frames = target / "derived" / "video_frames" / "102"
                frames.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (128, 72), (30, 120, 170)).save(frames / "frame_00001.jpg", "JPEG")
                db.execute("UPDATE tasks SET state='finished' WHERE type='video_keyframes'")
                db.execute("INSERT INTO tasks(type,state,priority,payload_json) VALUES('video_embed','pending',90,'{\"asset_id\":102}')")
                db.execute("INSERT INTO tasks(type,state,priority,payload_json) VALUES('caption','pending',110,'{\"asset_id\":102}')")
            db.commit()

    def test_refuses_existing_output_and_invalid_paths_before_mutation(self):
        self.target.mkdir(mode=0o700)
        sentinel = self.target / "keep"
        sentinel.write_bytes(b"owned data")
        with self.assertRaisesRegex(ValueError, "new_absolute_output_required"):
            qualification.run(self.target, self.ffmpeg, self.ffprobe)
        self.assertEqual(sentinel.read_bytes(), b"owned data")
        with self.assertRaises(ValueError):
            qualification.run(Path("relative"), self.ffmpeg, self.ffprobe)
        self.assertEqual(sentinel.read_bytes(), b"owned data")

    def test_task_verifier_requires_exact_worker_and_chained_rows(self):
        database = self.parent / "task-check.sqlite"
        with closing(sqlite3.connect(database)) as db:
            db.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY,type TEXT,state TEXT,payload_json TEXT)")
            rows = [(kind, "finished", json.dumps({"asset_id": asset_id}))
                    for kind, asset_id in qualification.WORKER_ASSET_IDS.items()]
            rows.extend((("caption", "pending", '{"asset_id":102}'),
                         ("video_embed", "pending", '{"asset_id":102}')))
            db.executemany("INSERT INTO tasks(type,state,payload_json) VALUES(?,?,?)", rows)
            db.commit()
        qualification._verify_tasks(database)
        with closing(sqlite3.connect(database)) as db:
            db.execute("INSERT INTO tasks(type,state,payload_json) VALUES('thumb','finished','{\"asset_id\":101}')")
            db.commit()
        with self.assertRaisesRegex(RuntimeError, "synthetic_worker_task_count_invalid"):
            qualification._verify_tasks(database)

    def _write_mock_report(self, target, value):
        target.mkdir(mode=0o700)
        payload = {**value,
                   "decoded_thumbnails": [{"width": 96, "height": 64},
                                          {"width": 96, "height": 64}],
                   "decoded_keyframes": 2}
        qualification.memory_qualification._write_json(target / qualification.REPORT_NAME, payload)
        return 0

    def _executable_stub(self, name):
        path = self.parent / name
        path.write_bytes(b"synthetic executable stub")
        if os.name != "nt":
            path.chmod(0o700)
        return path.resolve(strict=True)

    def test_windows_supervisor_pins_limits_environment_and_child(self):
        # The current host is portable; this exercises the public Windows gate
        # with a mocked Job and its exact child command/environment contract.
        ffmpeg, ffprobe = self._executable_stub("ffmpeg-stub.exe"), self._executable_stub("ffprobe-stub.exe")
        with patch.dict(os.environ, {"SystemRoot": "synthetic-system", "DATABASE_URL": "must-not-pass"}), \
                patch.object(controller, "WindowsAPI", return_value=object()), \
                patch.object(controller, "run_bounded", side_effect=lambda *a, **k:
                             self._write_mock_report(self.target, qualification._fixture_report())) as launch:
            report = qualification._bounded_report(self.target, ffmpeg, ffprobe)
        args, kwargs = launch.call_args
        self.assertEqual(kwargs, {"timeout_seconds": 900, "memory_limit": 2 * 1024**3,
                                  "process_limit": 8, "minimum_free_ram": 8 * 1024**3})
        self.assertEqual(args[2][1:4], ["-I", "-B", "-c"])
        self.assertIn("runpy.run_path", args[2][4])
        self.assertIn(str(ffmpeg), args[2][4])
        self.assertIn(str(ffprobe), args[2][4])
        self.assertNotIn("DATABASE_URL", args[3])
        self.assertEqual(report["decoded_keyframes"], 2)

    def test_windows_output_path_budget_checked_before_launch(self):
        with patch.object(qualification, "_check_windows_paths",
                          side_effect=ValueError("windows_fixture_path_too_long")), \
                patch.object(controller, "run_bounded") as launch:
            with self.assertRaisesRegex(ValueError, "windows_fixture_path_too_long"):
                qualification._bounded_report(self.target, self.ffmpeg, self.ffprobe)
        launch.assert_not_called()
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
