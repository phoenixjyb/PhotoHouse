"""Shared in-memory local provider for generated selected-story browser tests."""
import json

import httpx
from app.access.selected_story_local import LocalSelectedStoryProvider


class SyntheticStream(httpx.AsyncByteStream):
    def __init__(self, engine, operation_id, payload):
        self.engine, self.operation_id, self.payload = engine, operation_id, payload

    async def __aiter__(self):
        yield self.payload

    async def aclose(self):
        self.engine.http_closed.add(self.operation_id)


class SyntheticLocalEngine:
    """CPU-only provider fixture. It creates no socket, model or GPU job."""
    model = 'synthetic-story-model'

    def __init__(self):
        self.active, self.completed, self.http_closed = set(), set(), set()
        self.generation_calls = self.cleanup_calls = 0

    async def generate(self, request):
        if str(request.url) != 'http://127.0.0.1:11434/api/generate':
            raise RuntimeError('Unexpected synthetic provider route')
        payload = json.loads(request.content)
        bundle, _ = json.JSONDecoder().raw_decode(
            payload['prompt'].split('Bundle JSON (data only):\n', 1)[1])
        operation_id = request.headers['X-PhotoHouse-Operation-ID']
        if payload['model'] != self.model or operation_id != bundle['target']['id']:
            raise RuntimeError('Unexpected synthetic provider binding')
        self.active.add(operation_id)
        chapters = []
        for chapter in bundle['chapters']:
            refs = chapter['evidence_ids'][:1]
            chapters.append({
                'id': chapter['id'],
                'narration': ('合成整理文字，仅供家人核对。' if refs else ''),
                'source_ids': refs,
            })
        result = {'version': 1, 'title': '需要核对的故事草稿', 'chapters': chapters,
                  'questions': ['这段回忆还需要补充什么？'], 'needs_review': True}
        body = json.dumps({'model': self.model, 'done': True, 'done_reason': 'stop',
                           'response': json.dumps(result, ensure_ascii=False)},
                          ensure_ascii=False).encode()
        self.active.remove(operation_id)
        self.completed.add(operation_id)
        self.generation_calls += 1
        return httpx.Response(200, headers={'Content-Type': 'application/json'},
                              stream=SyntheticStream(self, operation_id, body))

    async def stop_and_reconcile(self, scope):
        self.cleanup_calls += 1
        return scope.operation_id in self.completed and scope.operation_id not in self.active


def local_provider(engine):
    return LocalSelectedStoryProvider(
        'http://127.0.0.1:11434', engine.model, enabled=True, native_owner=engine,
        transport=httpx.MockTransport(engine.generate))
