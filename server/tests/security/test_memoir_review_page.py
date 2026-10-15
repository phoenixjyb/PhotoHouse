"""Private canary review pages preserve exact text and source boundaries offline."""
from contextlib import redirect_stdout
from copy import deepcopy
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import build_memoir_review_page as page


class Elements(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags, self.ids, self.hrefs = [], [], []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if 'href' in attrs:
            self.hrefs.append(attrs['href'])


class ReviewPageTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.private = Path(tmp.name).resolve()
        self.private.chmod(0o700)
        self.network = patch.object(socket, 'create_connection', side_effect=AssertionError('no network'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def capture(self, case_id='synthetic-coherence', companion_kind='answer', prose=None):
        case, criteria = page.canary._case_plan(case_id)
        calls = []

        class Provider:
            def __init__(self, *args, **kwargs):
                pass

            def narrative(self, bundle):
                calls.append('narrative')
                return {'version': 1, 'title': bundle['title'], 'chapters': [
                    {'id': c['id'], 'narration': prose if prose is not None else c['narration'],
                     'source_ids': c['evidence_ids']} for c in bundle['chapters']],
                    'questions': ['What would you like to remember?'], 'needs_review': True}

            def companion(self, bundle):
                calls.append('companion')
                return {'version': 1, 'kind': companion_kind,
                        'reply': prose if prose is not None else 'A synthetic reply.',
                        'source_ids': [bundle['sources'][0]['id']] if companion_kind == 'answer' else [],
                        'questions': ['Which year do you remember?'], 'proposal': None}

            def suggest(self, bundle):
                calls.append('suggest')
                return {'version': 1, 'selection_revision': bundle['selection_revision'],
                        'titles': ([{'text': prose or 'Synthetic title',
                                     'source_ids': [bundle['sources'][0]['id']]}] if bundle['sources'] else []),
                        'needs_review': True}

        target = self.private / ('capture-' + case_id + '-' + companion_kind)
        result = page.canary._run_case(case, criteria, {
            'ollama_url': 'http://127.0.0.1:11434', 'ollama_model': 'private-review-model',
            'timeout_seconds': 30.0}, target, narrator_factory=Provider, title_suggester_factory=Provider)
        self.assertEqual(result['status'], 'captured_for_human_review')
        self.assertEqual(len(calls), 1)
        return target

    def rewrite(self, target, name, change):
        path = target / name
        value = json.loads(path.read_text())
        change(value)
        path.write_bytes(page.canary._canonical(value))

    def call(self, target, output):
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = page.main(['--capture-directory', str(target), '--output', str(output)])
        return code, json.loads(stream.getvalue())

    def test_all_eight_real_canary_capture_shapes_render_offline_with_resolvable_citations(self):
        for case_id in sorted(page.canary.CASE_IDS):
            with self.subTest(case_id=case_id):
                target = self.capture(case_id)
                review = page.load_review(target)
                text = page.render_review(review)
                elements = Elements(text)
                self.assertEqual(len(elements.ids), len(set(elements.ids)))
                self.assertTrue(all(h.startswith('#') and h[1:] in elements.ids for h in elements.hrefs))
                self.assertIn('全部未评审', text)
                self.assertNotIn('private-review-model', text)
                self.assertNotIn('127.0.0.1', text)
                self.assertNotIn(str(self.private), text)
                self.assertNotIn('script', [tag for tag, _ in elements.tags])
                self.assertFalse(any(attr.startswith('on') for _, attrs in elements.tags for attr in attrs))
                if case_id == 'synthetic-title-abstention':
                    self.assertIn('没有标题建议', text)

    def test_page_creation_is_private_and_redacted_and_preserves_all_capture_bytes(self):
        target = self.capture()
        before = {p.name: p.read_bytes() for p in target.iterdir()}
        output = self.private / 'review.html'
        code, report = self.call(target, output)
        self.assertEqual(0, code, report)
        self.assertTrue(output.is_file())
        self.assertEqual(before, {p.name: p.read_bytes() for p in target.iterdir()})
        self.assertFalse(report['quality_evaluated'])
        self.assertFalse(report['provider_contacted'])
        self.assertFalse(report['activation_performed'])
        for value in (str(self.private), 'private-review-model', '五月'):
            self.assertNotIn(value, json.dumps(report))
        if os.name != 'nt':
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_model_markup_remains_literal_and_csp_only_permits_exact_styles(self):
        malicious = '<script>alert(1)</script><img src="https://example.invalid/" onerror="alert(2)">'
        target = self.capture(prose=malicious)
        text = page.render_review(page.load_review(target))
        elements = Elements(text)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', text)
        self.assertNotIn('img', [tag for tag, _ in elements.tags])
        csp = next(attrs['content'] for tag, attrs in elements.tags
                   if tag == 'meta' and attrs.get('http-equiv') == 'Content-Security-Policy')
        self.assertIn("default-src 'none'", csp)
        self.assertIn("script-src 'none'", csp)
        self.assertNotIn('unsafe-inline', csp)
        expected = page.base64.b64encode(page.hashlib.sha256(page.STYLE.encode()).digest()).decode()
        self.assertIn('sha256-' + expected, csp)

    def test_valid_source_free_clarification_stays_distinct_from_confirmed_sources(self):
        target = self.capture('synthetic-provenance', companion_kind='clarification')
        text = page.render_review(page.load_review(target))
        self.assertIn('澄清 · 尚待人工核对', text)
        self.assertIn('最近对话：不是已确认来源', text)
        self.assertIn('没有引用来源', text)

    def test_tampered_input_output_and_record_are_refused_before_writing(self):
        for name, change in (
            ('input-bundle.json', lambda d: d.update(title='Substituted input')),
            ('output.json', lambda d: d.update(title='Substituted output')),
            ('record.json', lambda d: d.update(task='companion')),
            ('record.json', lambda d: d.update(quality_evaluated=True)),
            ('record.json', lambda d: d.update(status='request_failed')),
        ):
            with self.subTest(name=name, change=change):
                target = self.capture()
                self.rewrite(target, name, change)
                output = self.private / 'refused.html'
                code, report = self.call(target, output)
                self.assertEqual(2, code)
                self.assertEqual('refused', report['status'])
                self.assertFalse(output.exists())
                # Each case owns its separate immutable temporary capture.
                for item in target.iterdir():
                    item.unlink()
                target.rmdir()

    def test_forged_hash_does_not_bypass_current_answer_citation_contract(self):
        target = self.capture('synthetic-provenance')
        self.rewrite(target, 'output.json', lambda d: d.update(source_ids=[]))
        output = json.loads((target / 'output.json').read_text())
        self.rewrite(target, 'record.json', lambda d: d.update(output_sha256=page.digest(output)))
        with self.assertRaisesRegex(page.PageError, '^capture_contract_mismatch$'):
            page.load_review(target)

    def test_existing_output_and_private_input_links_are_refused(self):
        target = self.capture()
        output = self.private / 'existing.html'
        output.write_text('Keep this file')
        output.chmod(0o600)
        code, _ = self.call(target, output)
        self.assertEqual(2, code)
        self.assertEqual('Keep this file', output.read_text())
        original = target / 'output.json'
        original.rename(target / 'retained.json')
        original.symlink_to(target / 'retained.json')
        with self.assertRaises(page.PageError):
            page.load_review(target)

    def test_unprivate_oversized_and_duplicate_key_inputs_are_refused(self):
        if os.name == 'nt':
            self.skipTest('POSIX permission part; Windows ACL coverage belongs to private storage suite')
        target = self.capture()
        record = target / 'record.json'
        original = record.read_bytes()
        record.chmod(0o644)
        with self.assertRaises(page.PageError):
            page.load_review(target)
        record.chmod(0o600)
        for raw in (b' ' * (128 * 1024 + 1), b'{"schema":1,"schema":1}'):
            record.write_bytes(raw)
            with self.assertRaises(page.PageError):
                page.load_review(target)
        record.write_bytes(original)

    def test_cross_file_content_change_is_refused(self):
        target = self.capture()
        real_read = page._read
        count = 0

        def changing(path):
            nonlocal count
            count += 1
            value = real_read(path)
            if count == 4:
                value = deepcopy(value)
                value['duration_seconds'] += 1
            return value

        with patch.object(page, '_read', side_effect=changing):
            with self.assertRaisesRegex(page.PageError, '^capture_changed$'):
                page.load_review(target)


def write_browser_fixtures(directory):
    """Generate render fixtures with a fake provider; never establishes model execution."""
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    for case_id, kind, prose in (
        ('synthetic-coherence', 'answer', None),
        ('synthetic-conflict', 'answer', None),
        ('synthetic-provenance', 'clarification', None),
        ('synthetic-title-abstention', 'answer', None),
        ('synthetic-title-family', 'answer', '<img src="https://example.invalid/" onerror="alert(1)">'),
    ):
        fixture = ReviewPageTests()
        fixture.setUp()
        try:
            target = fixture.capture(case_id, companion_kind=kind, prose=prose)
            code, report = fixture.call(target, directory / (case_id + '.html'))
            if code:
                raise AssertionError(report)
        finally:
            fixture.doCleanups()


if __name__ == '__main__':
    unittest.main()
