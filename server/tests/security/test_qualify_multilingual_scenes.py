from __future__ import annotations

import contextlib
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import qualify_multilingual_scenes as runner  # noqa: E402


def test_no_argument_import_and_plan_do_not_import_optional_ml(tmp_path):
    script = ROOT / 'scripts' / 'qualify_multilingual_scenes.py'
    code = """
import builtins, runpy, sys
blocked = ('torch', 'torchvision', 'transformers', 'PIL', 'numpy', 'tokenizers', 'sentencepiece')
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in blocked:
        raise AssertionError('optional ML import attempted: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
sys.path.insert(0, %r)
sys.argv = ['qualify_multilingual_scenes.py']
runpy.run_path(sys.argv[0] if False else %r, run_name='__main__')
""" % (str(script.parent), str(script))
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
    assert result.returncode == 0
    plan = json.loads(result.stdout)
    assert plan['models_loaded'] is False
    assert plan['private_files_read'] is False
    assert plan['dimension'] == 768


def test_package_versions_are_checked_before_any_ml_import(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, 'installed_versions', lambda: {'torch': 'wrong'})
    monkeypatch.setattr(runner.importlib, 'import_module',
        lambda _name: pytest.fail('optional module imported before package gate'))
    with pytest.raises(runner.Refused):
        runner.load_model(tmp_path, {}, runner.EXPECTED_PACKAGES)


def test_directory_must_be_canonical_absolute_and_private(tmp_path):
    directory = tmp_path / 'model'
    directory.mkdir(mode=0o700)
    assert runner.canonical_private_directory(str(directory)) == directory
    with pytest.raises(runner.Refused):
        runner.canonical_private_directory(str(directory / '..' / 'model'))
    link = tmp_path / 'linked'
    link.symlink_to(directory, target_is_directory=True)
    with pytest.raises(runner.Refused):
        runner.canonical_private_directory(str(link))


def test_model_file_set_and_hash_pins_reject_missing_unknown_and_mutation(tmp_path):
    directory = tmp_path / 'model'
    directory.mkdir(mode=0o700)
    contents = {name: ('file-' + name).encode() for name in runner.MODEL_FILES}
    pins = {}
    for name, payload in contents.items():
        (directory / name).write_bytes(payload)
        (directory / name).chmod(0o600)
        pins[name] = {'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload)}
    observed = runner.inspect_model_files(directory, pins)
    assert set(observed) == runner.MODEL_FILES
    (directory / 'config.json').write_bytes(b'replaced')
    (directory / 'config.json').chmod(0o600)
    with pytest.raises(Exception):
        runner.verify_checkpoint(observed['config.json'])
    (directory / 'config.json').write_bytes(contents['config.json'])
    (directory / 'config.json').chmod(0o600)

    (directory / 'unknown.txt').write_text('extra')
    with pytest.raises(runner.Refused):
        runner.inspect_model_files(directory, pins)
    (directory / 'unknown.txt').unlink()
    (directory / 'tokenizer.json').write_bytes(b'mutated')
    with pytest.raises(runner.Refused):
        runner.inspect_model_files(directory, pins)
    (directory / 'tokenizer.json').unlink()
    with pytest.raises(runner.Refused):
        runner.inspect_model_files(directory, {k: v for k, v in pins.items() if k != 'model.safetensors'})


def test_configuration_refuses_unreviewed_data_and_noncanonical_model(monkeypatch, tmp_path):
    dataset = {'schema': 'photohouse.semantic_scene_cases.v1',
        'review': {'natural_scenes': True, 'labels_reviewed': False},
        'images': [{'id': f'i{index}', 'path': f'/private/i{index}.jpg',
                    'sha256': f'{index:064x}'} for index in range(1, 5)],
        'cases': [{'id': f'c{index}', 'relevant_images': ['i1'],
            'queries': {'en': 'scene', 'zh': '场景', 'zh-en': '场景 scene'}}
            for index in range(1, 3)]}
    # The dataset validator is reached only after the explicit model directory check.
    model_dir = tmp_path / 'model'
    model_dir.mkdir(mode=0o700)
    config = {'schema': 'photohouse.multilingual_scene_run.v1',
        'model_directory': str(model_dir), 'artifacts': runner.OFFICIAL_ARTIFACTS.copy(),
        'package_versions': runner.EXPECTED_PACKAGES.copy(),
        'dataset': '/private/dataset.json', 'max_elapsed_seconds': 30}
    monkeypatch.setattr(runner, '_load_private_document', lambda *_a, **_k: config)
    with pytest.raises(ValueError):
        runner.configuration('/private/config.json')

    config['model_directory'] = str(model_dir / '..' / 'model')
    with pytest.raises(runner.Refused):
        runner.configuration('/private/config.json')


class FakeTensor:
    def __init__(self, values, shape=None):
        self.values = values
        self.shape = shape or (1, len(values))

    def detach(self):
        return self

    def to(self, *_args, **_kwargs):
        return self

    def __getitem__(self, index):
        assert index == 0
        return self

    def tolist(self):
        return self.values

    def sum(self):
        return FakeScalar(sum(self.values))


class FakeScalar:
    def __init__(self, value):
        self.value = value

    def item(self):
        return self.value


class FakeTorch:
    float32 = object()

    @staticmethod
    def inference_mode():
        return contextlib.nullcontext()


def test_vector_normalization_requires_finite_nonzero_768_components():
    vector = runner._normalise(FakeTensor([3.0] + [0.0] * 767), FakeTorch)
    assert len(vector) == 768 and math.isclose(math.sqrt(math.fsum(v*v for v in vector)), 1.0)
    with pytest.raises(runner.Refused):
        runner._normalise(FakeTensor([float('nan')] + [0.0] * 767), FakeTorch)
    with pytest.raises(runner.Refused):
        runner._normalise(FakeTensor([0.0] * 768), FakeTorch)


class FakeTokenizer:
    model_input_names = ['input_ids']

    def __init__(self):
        self.seen = []

    def __call__(self, query, **kwargs):
        assert kwargs['truncation'] is False
        self.seen.append(query)
        return {'input_ids': list(range(65 if query == 'long' else 4))}


def test_query_validation_rejects_controls_and_overlength_without_truncation():
    tokenizer = FakeTokenizer()
    assert runner._query_tokens(type('P', (), {'tokenizer': tokenizer})(), 'HeLLo') == ('hello', 4)
    assert tokenizer.seen == ['hello']
    with pytest.raises(runner.Refused):
        runner._query_tokens(type('P', (), {'tokenizer': FakeTokenizer()})(), 'long')
    with pytest.raises(runner.Refused):
        runner._query_tokens(type('P', (), {'tokenizer': FakeTokenizer()})(), 'bad\nquery')
    with pytest.raises(runner.Refused):
        runner._query_tokens(type('P', (), {'tokenizer': FakeTokenizer()})(), 'x' * 513)
    with pytest.raises(runner.Refused):
        runner._query_tokens(type('P', (), {'tokenizer': FakeTokenizer()})(), '\ud800')


@pytest.mark.parametrize('with_exclusions', [False, True])
def test_measure_uses_fake_cpu_model_and_records_only_query_receipts(monkeypatch, with_exclusions):
    class FakeProcessor:
        tokenizer = FakeTokenizer()

        def __call__(self, text=None, images=None, padding=False, truncation=None,
                     max_length=None, return_tensors='pt'):
            if images is not None:
                assert text is None and return_tensors == 'pt'
                return {'pixel_values': FakeTensor([0.0] * 768, (1, 3, 256, 256))}
            assert images is None and padding == 'max_length' and truncation is False
            assert max_length == runner.TEXT_MAX_LENGTH and return_tensors == 'pt'
            model_input, token_count = runner._query_tokens(self, text[0])
            assert model_input == text[0]
            return {'input_ids': FakeTensor([1] * 64, (1, 64))}

    class FakeModel:
        def get_image_features(self, **_kwargs):
            return FakeTensor([1.0] + [0.0] * 767)

        def get_text_features(self, **_kwargs):
            assert set(_kwargs) == {'input_ids'}
            return FakeTensor([0.0, 1.0] + [0.0] * 766)

    class FakeImage:
        def close(self):
            pass

    images = [{'id': f'i{index}', 'path': f'/private/i{index}.jpg',
               'sha256': f'{index:064x}'} for index in range(1, 5)]
    cases = [{'id': f'c{index}', 'relevant_images': ['i1'],
        'queries': {'en': 'HELLO', 'zh': '你好', 'zh-en': '你好 HELLO'}} for index in range(1, 3)]
    dataset = runner.validate_dataset({'schema': 'photohouse.semantic_scene_cases.v1',
        'review': {'natural_scenes': True, 'labels_reviewed': True},
        'images': images, 'cases': cases})
    class FakePin:
        sha256 = 'a' * 64
        stat_identity = (1, 1, 0, 1, 1, 1, 1)

    image_pins = {image['id']: FakePin() for image in images}
    model_pins = {name: FakePin() for name in runner.MODEL_FILES}
    packages = runner.EXPECTED_PACKAGES.copy()
    monkeypatch.setattr(runner, 'installed_versions', lambda: packages)
    monkeypatch.setattr(runner, '_source_pin', lambda _p: FakePin())
    monkeypatch.setattr(runner, '_current', lambda _p: None)
    monkeypatch.setattr(runner, 'verify_checkpoint', lambda _p: None)
    monkeypatch.setattr(runner, 'decode_image', lambda _p: FakeImage())
    labels = {'schema': 'photohouse.semantic_exclusion_cases.v1',
        'images': [image['id'] for image in images],
        'cases': [{**case, 'forbidden_images': ['i2']} for case in cases]}
    report = runner.measure({'torch': FakeTorch, 'model': FakeModel(),
        'processor': FakeProcessor(), 'preprocessor_config': {'resample': 2},
        'tokenizer_config': {'tokenizer_class': 'GemmaTokenizer', 'do_lower_case': True,
                             'add_bos_token': False, 'add_eos_token': True,
                             'model_input_names': ['input_ids'],
                             'model_max_length': 1000000000000000019884624838656},
        'source_pins': {'fake': FakePin()}}, dataset, image_pins, model_pins, packages,
        float('inf'), exclusion_dataset=wrap_exclusions(dataset, labels) if with_exclusions else None)
    assert report['device'] == 'cpu'
    assert report['model']['dimension'] == 768
    assert report['model']['tokenizer']['model_input_names'] == ['input_ids']
    assert report['model']['tokenizer']['configured_model_max_length'] > 10**20
    assert report['model']['tokenizer']['attention_mask'] == 'not_supplied'
    assert len(report['images']) == 4
    assert len(report['queries']) == 6
    assert all('original_query_sha256' in receipt and 'model_input_sha256' in receipt
               and receipt['model_input_normalization'] == 'unicode_lowercase'
               and 'token_count_including_special_tokens' in receipt
               for receipt in report['queries'].values())
    serialized = json.dumps(report)
    assert 'hello' not in serialized and '你好' not in serialized
    assert '/private/' not in serialized
    assert report['vectors_persisted'] is False
    assert report['serving_binding_created'] is False
    if with_exclusions:
        assert report['schema'] == 'photohouse.multilingual_exclusion_measurement.v1'
        score = report['exclusion_scorecard']
        assert score['overall']['forbidden_ahead_or_tied'] == 6
        assert score['overall']['forbidden_in_top_k'] == 6
        assert score['dataset_sha256'] == runner.exclusions.dataset_sha256(labels)
        assert score['activation_approved'] is False
        assert report['activation_approved'] is False
        assert 'exclusion_cases' in report['source_sha256']
    else:
        assert report['schema'] == 'photohouse.multilingual_scene_measurement.v1'
        assert 'exclusion_scorecard' not in report


def wrap_exclusions(scenes, labels):
    return {'schema': 'photohouse.multilingual_exclusion_labels.v1',
        'scene_dataset_sha256': runner.dataset_sha256(scenes), 'dataset': labels}


def exclusion_fixture():
    scenes = {'schema': 'photohouse.semantic_scene_cases.v1',
        'review': {'natural_scenes': True, 'labels_reviewed': True},
        'images': [{'id': f'i{index}', 'path': f'/private/i{index}.jpg',
                    'sha256': f'{index:064x}'} for index in range(1, 5)],
        'cases': [{'id': f'c{index}', 'relevant_images': ['i1'],
            'queries': {'en': 'No people', 'zh': '没有人的场景', 'zh-en': '没有 people'}}
            for index in range(1, 3)]}
    labels = {'schema': 'photohouse.semantic_exclusion_cases.v1',
        'images': [image['id'] for image in scenes['images']],
        'cases': [{**case, 'forbidden_images': ['i2']} for case in scenes['cases']]}
    return scenes, labels


@pytest.mark.parametrize('change', ['query', 'case', 'image', 'relevant', 'review', 'overlap', 'image_bytes', 'missing_digest'])
def test_exclusion_binding_refuses_mismatch_before_loading_or_output(monkeypatch, tmp_path, change):
    import copy
    scenes, original_labels = exclusion_fixture()
    labels = copy.deepcopy(original_labels)
    envelope = wrap_exclusions(scenes, labels)
    if change == 'query':
        labels['cases'][0]['queries']['en'] = 'no people'
    elif change == 'case':
        labels['cases'].pop()
    elif change == 'image':
        labels['images'][-1] = 'other'
    elif change == 'relevant':
        labels['cases'][0]['relevant_images'] = ['i3']
    elif change == 'review':
        scenes['review']['labels_reviewed'] = False
    elif change == 'overlap':
        labels['cases'][0]['forbidden_images'] = ['i1']
    elif change == 'image_bytes':
        scenes['images'][0]['sha256'] = 'a' * 64
    elif change == 'missing_digest':
        envelope.pop('scene_dataset_sha256')
    monkeypatch.setattr(runner, 'configuration', lambda _path: ({}, tmp_path, scenes))
    monkeypatch.setattr(runner, '_load_private_document', lambda *_a, **_k: envelope)
    monkeypatch.setattr(runner, 'installed_versions', lambda: pytest.fail('version lookup reached'))
    output = tmp_path / 'output'
    with pytest.raises(ValueError):
        runner.execute(tmp_path / 'config.json', output, exclusion_path=tmp_path / 'labels.json',
            model_loader=lambda *_a: pytest.fail('model loaded'))
    assert not output.exists()


def test_binding_accepts_reordered_exact_candidates_without_modifying_queries():
    scenes, labels = exclusion_fixture()
    labels['images'].reverse()
    labels['cases'].reverse()
    envelope = wrap_exclusions(scenes, labels)
    bound = runner.bind_exclusions(scenes, envelope)
    assert bound == envelope
    assert bound['dataset']['cases'][0]['queries']['en'] == 'No people'


def test_exclusion_cli_requires_run_and_sanitizes_failure(capsys, monkeypatch):
    monkeypatch.setattr(runner, '_load_private_document',
        lambda *_a, **_k: pytest.fail('private file read in planning mode'))
    assert runner.run(['--exclusion-dataset', '/private/labels.json']) == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert json.loads(captured.err) == {'error': 'multilingual_scene_measurement_unavailable'}


def test_output_must_be_outside_source_and_new():
    with pytest.raises(Exception):
        runner.output_target(ROOT / 'private-output')
