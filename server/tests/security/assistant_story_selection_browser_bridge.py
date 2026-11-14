"""Synthetic assistant bridge variant with one generated video fixture."""
import runpy
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/security'))
from test_library_reads import LibraryReadTests

original_set_up = LibraryReadTests.setUp


def set_up_with_video(self):
    original_set_up(self)
    # This is a disposable migrated test database created by setUp(), never a
    # household library. Keep asset identity and search fixtures unchanged.
    with closing(sqlite3.connect(self.path)) as db, db:
        db.execute("UPDATE assets SET mime='video/mp4' WHERE id=102")


LibraryReadTests.setUp = set_up_with_video

sys.path.insert(0, str(ROOT / 'backend'))
from app.access.runtime import RuntimeConfiguration

original_build_app = RuntimeConfiguration.build_app


def build_app_with_generated_media(self, **kwargs):
    media = self.derived_root / 'thumbnails'
    for asset_id in (101, 102, *range(2000, 2044)):
        image = Image.new('RGB', (640, 480), (222, 232, 219) if asset_id % 2 else (215, 228, 241))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((38, 38, 602, 442), radius=30, outline=(50, 74, 82), width=7)
        draw.text((62, 72), f'Synthetic selection fixture {asset_id}', fill=(30, 48, 54))
        for size in (256, 1024):
            directory=media / str(size);directory.mkdir(parents=True, exist_ok=True)
            image.save(directory / f'{asset_id}.jpg', format='JPEG', quality=82)
        if asset_id == 102:
            frame=self.derived_root / 'video_frames' / str(asset_id);frame.mkdir(parents=True, exist_ok=True)
            image.save(frame / 'frame_00001.jpg', format='JPEG', quality=82)
    return original_build_app(self, **kwargs)


RuntimeConfiguration.build_app = build_app_with_generated_media
runpy.run_path(str(Path(__file__).with_name('assistant_workspace_browser_bridge.py')), run_name='__main__')
