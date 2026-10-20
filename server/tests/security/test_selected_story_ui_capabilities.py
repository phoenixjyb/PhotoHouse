"""Protected capability contract for the selected-story draft UI."""
from pathlib import Path
import importlib
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests/security'))

from app.access.transport import AccessRuntime, COOKIE
from app.main import create_app


def library_fixture_class():
    return importlib.import_module('test_library_reads').LibraryReadTests


class SyntheticProvider:
    async def prepare(self, bundle, scope):
        chapters = []
        for chapter in bundle['chapters']:
            refs = chapter['evidence_ids'][:1]
            chapters.append({
                'id': chapter['id'],
                'narration': ('合成整理文字，仅供家人核对。' if refs else ''),
                'source_ids': refs,
            })
        return {'version': 1, 'title': '需要核对的故事草稿', 'chapters': chapters,
                'questions': ['这段回忆还需要补充什么？'], 'needs_review': True}

    async def stop_and_reconcile(self, scope):
        return True


class SelectedStoryUiCapabilitiesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        library_fixture_class().setUpClass()

    @classmethod
    def tearDownClass(cls):
        library_fixture_class().tearDownClass()

    def setUp(self):
        self.fixture = library_fixture_class()()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        with self.fixture.connection() as db:
            db.execute("UPDATE access_memberships SET role='contributor' WHERE account_id=? AND library_id='family-a'",
                       (self.fixture.member_id,))
            db.commit()

    def app(self, *, ui=False, api=True, provider=True):
        runtime = AccessRuntime(self.fixture.connection, 'https://photohouse.test',
                                clock=lambda: self.fixture.now)
        return create_app(
            access_runtime=runtime,
            selected_story_provider=SyntheticProvider() if provider else None,
            selected_story_drafts_enabled=api,
            selected_story_ui_enabled=ui,
            memory_collaboration_enabled=True,
        )

    def client(self, app):
        client = TestClient(app, base_url='https://photohouse.test',
                            client=('192.0.2.25', 23461))
        with patch('app.access.memory_jobs.maintenance', lambda _runtime: None):
            client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        client.headers['Authorization'] = 'Bearer ' + self.fixture.owner_token
        client.headers['Sec-Fetch-Site'] = 'same-origin'
        return client

    def capability(self, client, library='family-a', suffix=''):
        return client.get(f'/story-workspace/drafts/capabilities?library={library}{suffix}')

    def assert_payload(self, response, *, enabled, can_prepare):
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {
            'version': 1, 'enabled': enabled, 'can_prepare': can_prepare,
            'source_policy': 'chapter_sources_v1',
        })

    def test_default_off_and_provider_alone_remain_disabled(self):
        default = self.client(create_app(access_runtime=AccessRuntime(
            self.fixture.connection, 'https://photohouse.test', clock=lambda: self.fixture.now)))
        self.assert_payload(self.capability(default), enabled=False, can_prepare=False)

        provider_only = self.client(self.app(ui=False, api=True))
        self.assert_payload(self.capability(provider_only), enabled=False, can_prepare=False)

    def test_flags_require_booleans_and_both_explicit_opt_ins(self):
        runtime = AccessRuntime(self.fixture.connection, 'https://photohouse.test',
                                clock=lambda: self.fixture.now)
        with self.assertRaises(ValueError):
            create_app(access_runtime=runtime, selected_story_ui_enabled=1)
        with self.assertRaises(ValueError):
            create_app(access_runtime=runtime, selected_story_ui_enabled=True)
        with self.assertRaises(ValueError):
            create_app(access_runtime=runtime, selected_story_drafts_enabled='true')
        with self.assertRaises(ValueError):
            create_app(access_runtime=runtime, selected_story_ui_enabled=True,
                       selected_story_drafts_enabled=True)

        api_only = self.client(self.app(ui=False, api=True))
        self.assert_payload(self.capability(api_only), enabled=False, can_prepare=False)

    def test_enabled_owner_and_contributor_can_prepare_but_viewer_only_reads(self):
        client = self.client(self.app(ui=True, api=True))
        self.assert_payload(self.capability(client), enabled=True, can_prepare=True)

        client.headers['Authorization'] = 'Bearer ' + self.fixture.member_token
        self.assert_payload(self.capability(client), enabled=True, can_prepare=True)
        client.headers.pop('Authorization')
        with self.fixture.connection() as db:
            db.execute("UPDATE access_memberships SET role='viewer' WHERE account_id=? AND library_id='family-a'",
                       (self.fixture.member_id,))
            db.commit()
        client.headers['Authorization'] = 'Bearer ' + self.fixture.member_token
        self.assert_payload(self.capability(client), enabled=True, can_prepare=False)

    def test_scope_and_auth_failures_are_fresh_and_protected(self):
        client = self.client(self.app(ui=False, api=False, provider=False))
        self.assertEqual(self.capability(client, library='family-b').status_code, 401)
        self.assertEqual(self.capability(client, suffix='&extra=1').status_code, 400)
        self.assertEqual(self.capability(client, suffix='&library=family-a').status_code, 400)
        client.headers.pop('Authorization', None)
        self.assertEqual(self.capability(client).status_code, 401)

        client.cookies.set(COOKIE, self.fixture.owner_token)
        self.assert_payload(self.capability(client), enabled=False, can_prepare=False)
        client.cookies.clear()
        client.headers['Authorization'] = 'Bearer ' + self.fixture.member_token
        with self.fixture.connection() as db:
            db.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=? AND library_id='family-a'",
                       (self.fixture.member_id,))
            db.commit()
        self.assertEqual(self.capability(client).status_code, 401)


if __name__ == '__main__':
    unittest.main()
