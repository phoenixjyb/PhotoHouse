"""Exercise caption frame loading without importing model or database runtimes."""
import ast
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image


SOURCE = Path(__file__).resolve().parents[2] / 'backend' / 'app' / 'tasks.py'
tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
resolver = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_caption_ffmpeg')
executor = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'TaskExecutor')
loader = next(node for node in executor.body if isinstance(node, ast.FunctionDef) and node.name == '_load_caption_image')
namespace = {'os': os, 'Path': Path, 'shutil': shutil, 'subprocess': subprocess,
             'tempfile': tempfile, 'Image': Image, 'Asset': SimpleNamespace,
             'safe_exif_transpose': lambda image: image}
exec(compile(ast.Module(body=[resolver, loader], type_ignores=[]), str(SOURCE), 'exec'), namespace)


class CaptionVideoToolTests(unittest.TestCase):
    def test_missing_tool_fails_before_allocating_scratch_or_submitting_a_process(self):
        asset = SimpleNamespace(path='generated.mp4', mime='video/mp4', duration_sec=4)
        with patch.dict(os.environ, {}, clear=True), patch.object(shutil, 'which', return_value=None), \
                patch.object(tempfile, 'NamedTemporaryFile') as temporary, patch.object(subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'ffmpeg on PATH or an absolute FFMPEG_EXE'):
                namespace['_load_caption_image'](None, asset)
        temporary.assert_not_called()
        run.assert_not_called()

    def test_explicit_tool_and_selected_scratch_are_used_and_cleaned(self):
        with tempfile.TemporaryDirectory(prefix='caption-frame-tool-') as directory:
            root = Path(directory).resolve(); executable = root / 'ffmpeg.exe'; executable.touch()
            scratch = root / 'scratch'; scratch.mkdir(); commands = []
            def extract(command, **kwargs):
                commands.append(command)
                with Image.new('RGB', (8, 8)) as frame:
                    frame.save(command[-1], 'JPEG')
                self.assertEqual(Path(command[-1]).parent, scratch)
            with patch.dict(os.environ, {'FFMPEG_EXE': str(executable), 'VLM_TMP_DIR': str(scratch)}), \
                    patch.object(subprocess, 'run', side_effect=extract):
                image = namespace['_load_caption_image'](None, SimpleNamespace(
                    path='generated.mp4', mime='video/mp4', duration_sec=4))
            self.assertEqual(image.size, (8, 8)); image.close()
            self.assertEqual(commands[0][0], str(executable))
            self.assertLess(commands[0].index('-ss'), commands[0].index('-i'))
            self.assertIn('-nostdin', commands[0])
            self.assertEqual(list(scratch.iterdir()), [])

    def test_explicit_relative_tool_does_not_silently_use_path(self):
        with patch.dict(os.environ, {'FFMPEG_EXE': 'ffmpeg.exe'}), patch.object(shutil, 'which') as search:
            with self.assertRaisesRegex(RuntimeError, 'absolute FFMPEG_EXE'):
                namespace['_caption_ffmpeg']()
        search.assert_not_called()
