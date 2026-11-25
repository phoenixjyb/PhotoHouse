"""Private graph revision drafts change only explicit generated assertions or aliases."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(Path(__file__).parent))

from app.access.kinship import KinshipGraph, load_private_graph
from prepare_kinship_revision import main
from test_kinship import SOURCE_ROOT, graph_document, per_account_graph_document


class PrepareKinshipRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kinship-revision-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        os.chmod(self.root, 0o700)
        self.graph_path = self.root / 'graph.json'
        self.patch_path = self.root / 'patch.json'
        self.output_path = self.root / 'draft.json'

    def write_private(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=True, sort_keys=True), encoding='ascii')
        os.chmod(path, 0o600)

    def patch(self, document, operations, *, digest=None, revision='revision-2'):
        return {'version': 1,
                'expected_graph_sha256': digest or KinshipGraph(document).digest,
                'revision': revision, 'operations': operations}

    @staticmethod
    def assertion(ident, subject, relation, obj):
        return {'id': ident, 'subject_id': subject, 'relation': relation,
                'object_id': obj, 'source': 'user'}

    def run_tool(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(['--graph', str(self.graph_path), '--patch', str(self.patch_path),
                         '--out', str(self.output_path)])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_reviewed_relative_correction_writes_private_new_revision_only(self):
        base = graph_document()
        self.write_private(self.graph_path, base)
        original_bytes = self.graph_path.read_bytes()
        patch = self.patch(base, [{
            'op': 'replace', 'assertion_id': 'a-mgm',
            'assertion': self.assertion('a-mgm', 'mother', 'mother', 'paternal-grandmother'),
        }])
        self.write_private(self.patch_path, patch)

        code, stdout, stderr = self.run_tool()

        self.assertEqual((code, stderr), (0, ''))
        summary = json.loads(stdout)
        self.assertTrue(summary['created'])
        self.assertEqual(set(summary), {'created', 'graph_sha256', 'output_sha256'})
        self.assertEqual(os.stat(self.output_path).st_mode & 0o777, 0o600)
        self.assertEqual(self.graph_path.read_bytes(), original_bytes)
        draft = load_private_graph(self.output_path, SOURCE_ROOT)
        self.assertEqual(draft.document['revision'], 'revision-2')
        original = KinshipGraph(base)
        self.assertEqual(original.resolve("my mother's mother"), {'maternal-grandmother'})
        self.assertEqual(draft.resolve("my mother's mother"), {'paternal-grandmother'})
        self.assertEqual(draft.resolve('妈妈'), {'mother'})
        self.assertEqual(draft.document['people'], base['people'])
        self.assertEqual(draft.document['scope'], base['scope'])
        self.assertEqual(draft.document['graph_id'], base['graph_id'])
        self.assertEqual(draft.document['assertions'][0]['id'], 'a-mother')

    def test_schema_v2_account_scope_and_perspectives_are_preserved(self):
        base = per_account_graph_document()
        self.write_private(self.graph_path, base)
        self.write_private(self.patch_path, self.patch(base, [
            {'op': 'add', 'assertion': self.assertion(
                'a-sister-mother', 'older-sister', 'mother', 'mother')},
            {'op': 'remove', 'assertion_id': 'a-husband'},
        ]))

        code, _, stderr = self.run_tool()

        self.assertEqual((code, stderr), (0, ''))
        draft = load_private_graph(self.output_path, SOURCE_ROOT).document
        self.assertEqual(draft['schema'], 2)
        self.assertEqual(draft['scope'], base['scope'])
        self.assertEqual(draft['perspectives'], base['perspectives'])
        self.assertEqual(draft['people'], base['people'])
        assertions = {item['id']: item for item in draft['assertions']}
        self.assertNotIn('a-husband', assertions)
        self.assertEqual(assertions['a-sister-mother'],
                         self.assertion('a-sister-mother', 'older-sister', 'mother', 'mother'))

    def test_reviewed_aliases_bind_to_one_person_without_changing_relationships(self):
        base = graph_document()
        self.write_private(self.graph_path, base)
        original = self.graph_path.read_bytes()
        self.write_private(self.patch_path, self.patch(base, [{
            'op': 'replace_aliases', 'person_id': 'mother',
            'aliases': ['Fictional Nickname', '示例小名'],
        }]))

        code, stdout, stderr = self.run_tool()

        self.assertEqual((code, stderr), (0, ''))
        self.assertNotIn('Fictional Nickname', stdout)
        self.assertEqual(self.graph_path.read_bytes(), original)
        draft = load_private_graph(self.output_path, SOURCE_ROOT)
        self.assertEqual(draft.resolve('fictional nickname'), {'mother'})
        self.assertEqual(draft.resolve('示例小名'), {'mother'})
        self.assertEqual(KinshipGraph(base).resolve('fictional nickname'), set())
        self.assertEqual(draft.document['assertions'], base['assertions'])
        self.assertEqual(draft.document['scope'], base['scope'])
        self.assertEqual(draft.document['people'][1]['name_en'], base['people'][1]['name_en'])

    def test_unknown_repeated_or_ambiguous_alias_edit_refuses_without_output(self):
        base = graph_document()
        self.write_private(self.graph_path, base)
        edit = {'op': 'replace_aliases', 'person_id': 'mother', 'aliases': ['Fictional Nickname']}
        for changes in (
            [dict(edit, person_id='absent')],
            [edit, dict(edit, aliases=[])],
            [dict(edit, aliases=['Fictional Nickname', 'fictional nickname'])],
            [dict(edit, catalog_binding={'person_id': '8', 'label': 'Fictional Person'})],
        ):
            with self.subTest(changes=changes):
                self.write_private(self.patch_path, self.patch(base, changes))
                code, stdout, _stderr = self.run_tool()
                self.assertEqual((code, stdout), (2, ''))
                self.assertFalse(self.output_path.exists())

    def test_stale_digest_and_contradictory_relationship_refuse_without_output(self):
        base = graph_document()
        self.write_private(self.graph_path, base)
        for patch in (
            self.patch(base, [{'op': 'remove', 'assertion_id': 'a-husband'}], digest='0' * 64),
            self.patch(base, [{'op': 'add', 'assertion': self.assertion(
                'a-father-contradiction', 'child', 'father', 'mother')}]),
            self.patch(base, [{'op': 'add', 'assertion': {
                **self.assertion('a-scope-edit', 'child', 'mother', 'mother'),
                'scope': {'account_id': 'other', 'library_id': 'other'},
            }}]),
        ):
            with self.subTest(patch=patch):
                if self.patch_path.exists():
                    self.patch_path.unlink()
                self.write_private(self.patch_path, patch)
                code, stdout, stderr = self.run_tool()
                self.assertEqual(code, 2)
                self.assertEqual(stdout, '')
                self.assertIn('refused', stderr)
                self.assertFalse(self.output_path.exists())

    def test_existing_output_is_never_replaced(self):
        base = graph_document()
        self.write_private(self.graph_path, base)
        self.write_private(self.patch_path, self.patch(base, [{'op': 'remove', 'assertion_id': 'a-husband'}]))
        self.write_private(self.output_path, {'preserve': 'existing draft'})
        original = self.output_path.read_bytes()

        code, stdout, stderr = self.run_tool()

        self.assertEqual(code, 2)
        self.assertEqual(stdout, '')
        self.assertIn('refused', stderr)
        self.assertEqual(self.output_path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
