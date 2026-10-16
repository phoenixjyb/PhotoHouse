"""Private offline workflow checks with generated images and a fake encoder."""
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, replace
import hashlib
import io
import json
import logging
from pathlib import Path
import sys
from unittest.mock import Mock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'backend'), str(ROOT/'scripts'), str(ROOT/'tests/security')]
import qualify_reviewed_semantic_scenes as subject
from test_qualify_semantic_scenes import selected
from app.access.semantic_encoder import JointSpaceBinding, TextVector
from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum
from semantic_reviewed_projection import ReviewedProjection, composition_recipe, reviewed_document_sha256
from semantic_scene_cases import dataset_sha256, evaluate


@pytest.fixture
def reviewed_set(selected):
    text = VectorSpaceIdentity('a'*64, 'b'*64, 'generated-review-space', 'text-v1', 512, 'unit_l2')
    selected.inner = JointSpaceBinding(replace(text, preprocessing_sha256='d'*64), text, 'c'*64)
    selected.provider['binding'] = asdict(selected.inner)
    selected.write()
    selected.projection = {'schema': 'photohouse.reviewed_scene_projection.v1',
        'policy': 'exact_reviewed_only',
        'review': {'status': 'operator_reviewed', 'reference_sha256': '5'*64},
        'entries': [{'original': query, 'model_input': f'a scene {i}'}
            for i, case in enumerate(selected.dataset['cases']) for query in case['queries'].values()]}
    projection = ReviewedProjection(selected.projection,
        expected_sha256=reviewed_document_sha256(selected.projection))
    digest, _ = subject.reviewed.implementation_receipt()
    recipe = composition_recipe(selected.inner, projection, digest)
    selected.outer = JointSpaceBinding(selected.inner.image_identity,
        replace(text, preprocessing_sha256=recipe['recipe_sha256']), 'f'*64)
    selected.reviewed = {'schema': 'photohouse.reviewed_semantic_text_provider.v1',
        'encoder_configuration': {'path': str(selected.root/'provider.json'),
            'document_sha256': subject.reviewed.document_sha256(selected.provider)},
        'projection': {'path': str(selected.root/'projection.json'),
            'document_sha256': reviewed_document_sha256(selected.projection)},
        'binding': asdict(selected.outer), 'port': 8915,
        'credential_file': str(selected.root/'absent-credential.json')}
    selected.config.update(schema='photohouse.reviewed_scene_run.v1',
        provider_configuration=str(selected.root/'reviewed.json'))
    def write():
        for name, value in [('run.json', selected.config), ('dataset.json', selected.dataset),
                ('projection.json', selected.projection), ('reviewed.json', selected.reviewed)]:
            path = selected.root/name
            path.write_text(json.dumps(value, ensure_ascii=False)); path.chmod(0o600)
    selected.reviewed_write = write
    write()
    return selected


class FakeInner:
    def __init__(self):
        self.binding = None
        self.queries = []
        self.bind_calls = []
    def bind(self, binding):
        self.binding = binding; self.bind_calls.append(binding)
    def probe(self):
        return {'schema': 'generated-inner-probe', 'dimension': 512}
    def encode(self, query, *, check):
        check(); self.queries.append(query)
        vector = tuple(float(j == int(query.rsplit(' ', 1)[1])) for j in range(512))
        return TextVector(self.binding.binding_sha256, hashlib.sha256(query.encode()).hexdigest(),
            vector, canonical_vector_checksum(vector))


def generated_measure(model, dataset, pins, versions, deadline, *, reviewed_provider):
    images = {image['id']: tuple(float(j == i) for j in range(512))
        for i, image in enumerate(dataset['images'])}
    texts, receipts = {}, {}
    for case in dataset['cases']:
        for language in ('en', 'zh', 'zh-en'):
            key = case['id'] + ':' + language
            result = reviewed_provider.encode(case['queries'][language])
            texts[key] = result.vector
            receipts[key] = {'original_query_sha256': result.query_sha256,
                'vector_checksum_sha256': result.checksum_sha256}
    return {'schema': 'photohouse.reviewed_scene_measurement.v1',
        'dataset_sha256': dataset_sha256(dataset), 'metrics': evaluate(dataset, images, texts),
        'query_receipts': receipts, 'pair_binding_created': False, 'activation_performed': False}


def test_plan_never_opens_private_files_models_or_listeners():
    output = io.StringIO()
    with patch.object(subject, 'configuration', side_effect=AssertionError), patch.object(
            subject.reviewed.direct, 'load_model', side_effect=AssertionError), redirect_stdout(output):
        assert subject.run([]) == 0
    record = json.loads(output.getvalue())
    assert record['status'] == 'reviewed_scene_pair_plan'
    assert record['requires_existing_bindings'] and record['complete_query_coverage_required']
    assert not record['private_files_read'] and not record['models_loaded']


@pytest.mark.parametrize('mutation', ['schema', 'extra', 'budget', 'versions', 'review',
    'outer-null', 'outer-old', 'unknown-query', 'query-whitespace', 'mapping-hash'])
def test_preflight_refuses_invalid_or_uncovered_inputs_before_model_and_output(reviewed_set, mutation):
    s = reviewed_set
    if mutation == 'schema': s.config['schema'] = 'wrong'
    elif mutation == 'extra': s.config['extra'] = True
    elif mutation == 'budget': s.config['max_elapsed_seconds'] = True
    elif mutation == 'versions': s.config['image_package_versions'] = {}
    elif mutation == 'review': s.dataset['review']['labels_reviewed'] = False
    elif mutation == 'outer-null': s.reviewed['binding'] = None
    elif mutation == 'outer-old': s.reviewed['binding'] = asdict(s.inner)
    elif mutation == 'unknown-query': s.dataset['cases'][0]['queries']['zh'] = '未审核的场景'
    elif mutation == 'query-whitespace': s.dataset['cases'][0]['queries']['en'] += ' '
    elif mutation == 'mapping-hash': s.reviewed['projection']['document_sha256'] = '0'*64
    s.reviewed_write()
    model = Mock(side_effect=AssertionError)
    with patch.object(subject.reviewed.direct, 'load_model', model):
        with pytest.raises(Exception): subject.execute(s.root/'run.json', s.root/'out')
    model.assert_not_called()
    assert not (s.root/'out').exists()


@pytest.mark.parametrize('mutation', ['image-hash', 'version', 'existing-output', 'source-recipe'])
def test_resource_and_source_admission_precedes_model_load(reviewed_set, mutation):
    s = reviewed_set
    if mutation == 'image-hash': s.dataset['images'][0]['sha256'] = '0'*64
    if mutation == 'existing-output': (s.root/'out').mkdir(mode=0o700)
    s.reviewed_write()
    model = Mock(side_effect=AssertionError)
    digest, pins = subject.reviewed.implementation_receipt()
    with patch.object(subject.scenes, 'version', return_value='9' if mutation == 'version' else '1.2.3'), patch.object(
            subject.reviewed, 'implementation_receipt', return_value=('0'*64 if mutation == 'source-recipe' else digest, pins)), patch.object(
            subject.reviewed.direct, 'load_model', model):
        with pytest.raises(Exception): subject.execute(s.root/'run.json', s.root/'out')
    model.assert_not_called()


def test_success_loads_one_bound_model_preserves_original_cohorts_and_hash_provenance(reviewed_set):
    s = reviewed_set; model = FakeInner()
    original_reader = subject.reviewed._load_private_document
    with patch.object(subject.scenes, 'version', return_value='1.2.3'), patch.object(
            subject.reviewed.direct, 'load_model', return_value=model) as factory, patch.object(
            subject.reviewed, '_load_private_document', wraps=original_reader) as reader:
        result = subject.execute(s.root/'run.json', s.root/'out', measure_fn=generated_measure)
    factory.assert_called_once()
    assert model.bind_calls == [s.inner]
    assert model.queries == ['a scene 0']*3 + ['a scene 1']*3
    assert all('credential' not in str(call.args[0]) for call in reader.call_args_list)
    report = json.loads((s.root/'out'/'measurement.json').read_text())
    assert report['dataset_sha256'] == dataset_sha256(s.dataset)
    assert report['metrics']['overall']['top1'] == 6
    assert all(value['top1'] == 2 for value in report['metrics']['languages'].values())
    for case in s.dataset['cases']:
        for language, query in case['queries'].items():
            receipt = report['query_receipts'][case['id']+':'+language]
            assert receipt['original_query_sha256'] == hashlib.sha256(query.encode()).hexdigest()
            assert receipt['model_input_sha256'] == hashlib.sha256(
                f"a scene {case['id'][-1]}".encode()).hexdigest()
            assert receipt['projection_sha256'] == s.reviewed['projection']['document_sha256']
    assert not result['pair_binding_created'] and not result['activation_performed']
    assert not result['serving_transport_measured'] and not result['dialect_relevance_measured']
    encoded = json.dumps(report, ensure_ascii=False)
    assert str(s.root) not in encoded and '场景' not in encoded and 'a scene 0' not in encoded
    assert '"vector"' not in encoded
    assert (s.root/'out'/'measurement.json').stat().st_mode & 0o777 == 0o600
    assert result['measurement_sha256'] == hashlib.sha256((s.root/'out'/'measurement.json').read_bytes()).hexdigest()


def test_partial_failure_keeps_started_record_and_never_overwrites(reviewed_set):
    s = reviewed_set; model = Mock(side_effect=RuntimeError('private path or query'))
    with patch.object(subject.scenes, 'version', return_value='1.2.3'), patch.object(
            subject.reviewed.direct, 'load_model', model):
        with pytest.raises(RuntimeError): subject.execute(s.root/'run.json', s.root/'out')
        assert (s.root/'out'/'started.json').exists()
        assert not (s.root/'out'/'measurement.json').exists()
        with pytest.raises(Exception): subject.execute(s.root/'run.json', s.root/'out')
    assert model.call_count == 1


def test_model_loading_deadline_and_late_report_refusal(reviewed_set):
    s = reviewed_set
    with patch.object(subject.scenes, 'version', return_value='1.2.3'), patch.object(
            subject.time, 'monotonic', side_effect=[0, 0, 121, 121]):
        with pytest.raises(ValueError): subject.execute(s.root/'run.json', s.root/'out',
            prepare_fn=lambda _: (Mock(), Mock(), {}), measure_fn=Mock(side_effect=AssertionError))
    assert (s.root/'out'/'started.json').exists()
    assert not (s.root/'out'/'measurement.json').exists()


@pytest.mark.parametrize('failure', ['deadline', 'source'])
def test_late_measurement_or_source_change_retains_only_started_record(reviewed_set, failure):
    s = reviewed_set; model = FakeInner(); changed = False
    def measure(*args, **kwargs):
        nonlocal changed
        report = generated_measure(*args, **kwargs)
        changed = True
        return report
    def source_check(_pin):
        if changed and failure == 'source': raise ValueError('private source detail')
    with patch.object(subject.scenes, 'version', return_value='1.2.3'), patch.object(
            subject.reviewed.direct, 'load_model', return_value=model), patch.object(
            subject, '_current', side_effect=source_check), patch.object(
            subject.time, 'monotonic', side_effect=lambda: 121 if changed and failure == 'deadline' else 0):
        with pytest.raises(ValueError): subject.execute(s.root/'run.json', s.root/'out', measure_fn=measure)
    assert len(model.queries) == 6
    assert (s.root/'out'/'started.json').exists()
    assert not (s.root/'out'/'measurement.json').exists()


def test_shared_exact_original_retains_each_language_row(reviewed_set):
    s = reviewed_set; model = FakeInner()
    s.dataset['cases'][0]['queries']['zh-en'] = s.dataset['cases'][0]['queries']['en']
    s.reviewed_write()
    with patch.object(subject.scenes, 'version', return_value='1.2.3'), patch.object(
            subject.reviewed.direct, 'load_model', return_value=model):
        subject.execute(s.root/'run.json', s.root/'out', measure_fn=generated_measure)
    report = json.loads((s.root/'out'/'measurement.json').read_text())
    receipts = report['query_receipts']
    assert len(receipts) == 6
    assert receipts['case-0:en'] == receipts['case-0:zh-en']
    assert report['metrics']['languages']['en']['queries'] == 2
    assert report['metrics']['languages']['zh-en']['queries'] == 2


@pytest.mark.parametrize('tamper', ['dataset', 'original', 'query-set'])
def test_mismatched_measurement_receipts_never_publish_success(reviewed_set, tamper):
    s = reviewed_set; model = FakeInner()
    def altered(*args, **kwargs):
        report = generated_measure(*args, **kwargs)
        if tamper == 'dataset': report['dataset_sha256'] = '0'*64
        elif tamper == 'query-set': report['query_receipts'].pop(next(iter(report['query_receipts'])))
        else: report['query_receipts'][next(iter(report['query_receipts']))]['original_query_sha256'] = '0'*64
        return report
    with patch.object(subject.scenes, 'version', return_value='1.2.3'), patch.object(
            subject.reviewed.direct, 'load_model', return_value=model):
        with pytest.raises(ValueError): subject.execute(s.root/'run.json', s.root/'out', measure_fn=altered)
    assert (s.root/'out'/'started.json').exists()
    assert not (s.root/'out'/'measurement.json').exists()


def test_cli_failure_redacts_native_diagnostics_and_restores_logging():
    import os
    def fail(*args):
        print('PRIVATE QUERY'); os.write(2, b'PRIVATE PATH'); raise RuntimeError('PRIVATE TOKEN')
    out, err = io.StringIO(), io.StringIO(); previous = logging.root.manager.disable
    with patch.object(subject, 'execute', side_effect=fail), redirect_stdout(out), redirect_stderr(err):
        assert subject.run(['--run', '--configuration', '/private/run.json',
            '--output-directory', '/private/new-output']) == 1
    assert out.getvalue() == ''
    assert err.getvalue() == '{"error":"reviewed_scene_measurement_unavailable"}\n'
    assert logging.root.manager.disable == previous
