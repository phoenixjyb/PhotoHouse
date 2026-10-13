"""The WSL adapter accepts transient, authenticated WAV bytes only."""
import io
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import wave

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
if importlib.util.find_spec('assistant_asr_service') is None:
    # This WSL/GPU adapter is deliberately outside the curated CPU source
    # export. Broad unittest discovery must report the optional boundary;
    # an available adapter with broken dependencies must still fail import.
    create_app = MAX_WAV_BYTES = None
else:
    from assistant_asr_service import create_app, MAX_WAV_BYTES


@unittest.skipIf(create_app is None, 'External WSL ASR adapter is outside the curated CPU source profile')
class AssistantAsrServiceTests(unittest.TestCase):
    def test_private_raw_wav_without_job_file(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            model = base / 'model'
            model.mkdir()
            (model / 'model.bin').write_bytes(b'fixture')
            captured = []

            def fake_transcribe(payload, **kwargs):
                captured.append(payload)
                self.assertEqual(kwargs['model_path'], model)
                return '找家庭照片'

            app = create_app(model_path=model, gpu_lock=base / 'gpu.lock',
                             token='s' * 32, transcriber=fake_transcribe)
            client = TestClient(app)
            output = io.BytesIO()
            with wave.open(output, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b'\0\0' * 1600)
            sound = output.getvalue()
            headers = {'Authorization': 'Bearer ' + 's' * 32,
                       'Content-Type': 'audio/wav'}
            self.assertEqual(client.post('/transcribe', content=sound).status_code, 403)
            self.assertEqual(client.post('/transcribe', content=sound,
                headers={'Authorization': headers['Authorization'],
                         'Content-Type': 'text/plain'}).status_code, 415)
            response = client.post('/transcribe', content=sound, headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), {'success': True, 'text': '找家庭照片'})
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(captured, [sound])
            self.assertEqual(sorted(p.name for p in base.iterdir()), ['model'])
            self.assertEqual(client.post('/transcribe', content=b'x' * (MAX_WAV_BYTES + 1),
                headers=headers).status_code, 413)


if __name__ == '__main__':
    unittest.main()
