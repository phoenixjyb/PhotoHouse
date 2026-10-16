"""Offline scene runner checks use generated media and stand-in ML objects."""
from contextlib import nullcontext, redirect_stdout, redirect_stderr
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'backend'), str(ROOT/'scripts')]
import qualify_semantic_scenes as subject
from semantic_openclip import PACKAGES


@pytest.fixture
def selected(tmp_path):
    tmp_path = tmp_path.resolve()
    tmp_path.chmod(0o700)
    images = []
    for i in range(4):
        path = tmp_path/f'image-{i}.png'
        Image.new('RGB', (32, 24), (i*50, 50, 100)).save(path)
        path.chmod(0o600)
        images.append({'id': f'image-{i}', 'path': str(path),
                       'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    dataset = {'schema': 'photohouse.semantic_scene_cases.v1',
        'review': {'natural_scenes': True, 'labels_reviewed': True},
        'images': images, 'cases': [
            {'id': f'case-{i}', 'relevant_images': [f'image-{i}'],
             'queries': {'en': f'A scene {i}', 'zh': f'场景{i}', 'zh-en': f'场景 scene {i}'}}
            for i in range(2)]}
    provider = {'schema': 'photohouse.semantic_text_provider.v1',
        'architecture': 'ViT-B-32', 'device': 'cpu',
        'checkpoint': {'path': str(tmp_path/'weights.pt'), 'sha256': 'a'*64},
        'bpe': {'path': str(tmp_path/'vocab.gz'), 'sha256': 'b'*64},
        'package_versions': {name: '1.2.3' for name in PACKAGES},
        'binding': None, 'port': 8912, 'credential_file': None}
    config = {'schema': 'photohouse.semantic_scene_run.v1',
        'provider_configuration': str(tmp_path/'provider.json'), 'dataset': str(tmp_path/'dataset.json'),
        'image_package_versions': {name: '1.2.3' for name in subject.IMAGE_PACKAGES},
        'max_elapsed_seconds': 120}
    def write():
        for name, value in (('provider.json', provider), ('dataset.json', dataset), ('run.json', config)):
            path = tmp_path/name
            path.write_text(json.dumps(value)); path.chmod(0o600)
    write()
    return SimpleNamespace(root=tmp_path, dataset=dataset, provider=provider, config=config, write=write)


def test_default_plan_never_reads_private_files_or_loads_models():
    output = io.StringIO()
    with patch.object(subject, 'configuration', side_effect=AssertionError), patch.object(
            subject, 'load_model', side_effect=AssertionError), redirect_stdout(output):
        assert subject.run([]) == 0
    result = json.loads(output.getvalue())
    assert result['status'] == 'scene_pair_plan'
    assert result['languages'] == ['en', 'zh', 'zh-en']
    assert not result['models_loaded'] and not result['private_files_read']


@pytest.mark.parametrize('mutation', ['schema', 'unknown', 'budget', 'versions', 'review', 'duplicate-json'])
def test_bad_configuration_or_unreviewed_cases_fail_before_model_load(selected, mutation):
    if mutation == 'schema': selected.config['schema'] = 'wrong'
    elif mutation == 'unknown': selected.config['extra'] = True
    elif mutation == 'budget': selected.config['max_elapsed_seconds'] = True
    elif mutation == 'versions': selected.config['image_package_versions'] = {}
    elif mutation == 'review': selected.dataset['review']['labels_reviewed'] = False
    selected.write()
    if mutation == 'duplicate-json':
        (selected.root/'run.json').write_text('{"schema":1,"schema":2}')
    factory = Mock(side_effect=AssertionError)
    with pytest.raises(ValueError):
        subject.execute(selected.root/'run.json', selected.root/'out', model_factory=factory)
    factory.assert_not_called()
    assert not (selected.root/'out').exists()


@pytest.mark.parametrize('mutation', ['hash', 'symlink', 'hardlink', 'byte-budget', 'version', 'existing-output'])
def test_file_and_resource_admission_precedes_model(selected, mutation):
    output = selected.root/'out'
    image = Path(selected.dataset['images'][0]['path'])
    if mutation == 'hash': selected.dataset['images'][0]['sha256'] = 'f'*64
    elif mutation == 'symlink':
        alias = selected.root/'alias.png'; alias.symlink_to(image)
        selected.dataset['images'][0]['path'] = str(alias)
    elif mutation == 'hardlink': os.link(image, selected.root/'hard.png')
    elif mutation == 'existing-output': output.mkdir(mode=0o700)
    selected.write()
    factory = Mock(side_effect=AssertionError)
    with patch.object(subject, 'version', return_value='9' if mutation == 'version' else '1.2.3'), patch.object(
            subject, 'MAX_IMAGE_BYTES', 1 if mutation == 'byte-budget' else subject.MAX_IMAGE_BYTES):
        with pytest.raises(ValueError): subject.execute(selected.root/'run.json', output, model_factory=factory)
    factory.assert_not_called()


def test_decode_pinned_bytes_rgb_exif_and_content_changes(selected):
    image = Path(selected.dataset['images'][0]['path'])
    exif = Image.Exif(); exif[274] = 6
    Image.new('RGB', (32, 24), 'red').save(image, format='JPEG', exif=exif)
    selected.dataset['images'][0]['sha256'] = hashlib.sha256(image.read_bytes()).hexdigest()
    pins = subject.inspect_images(selected.dataset)
    decoded = subject.decode_image(pins['image-0'])
    try:
        assert decoded.size == (24, 32) and decoded.mode == 'RGB'
        assert decoded.info == {}
    finally: decoded.close()
    image.write_bytes(b'changed')
    with pytest.raises(ValueError): subject.decode_image(pins['image-0'])


@pytest.mark.parametrize('kind', ['animated', 'pixels', 'format'])
def test_decode_rejects_unsupported_or_oversized_images(selected, kind):
    image = Path(selected.dataset['images'][0]['path'])
    if kind == 'animated':
        frames = [Image.new('RGB', (32, 24), color) for color in ('red', 'blue')]
        frames[0].save(image, format='PNG', save_all=True, append_images=frames[1:])
        for frame in frames: frame.close()
    elif kind == 'format': Image.new('RGB', (32, 24), 'red').save(image, format='BMP')
    selected.dataset['images'][0]['sha256'] = hashlib.sha256(image.read_bytes()).hexdigest()
    pins = subject.inspect_images(selected.dataset)
    with patch.object(subject, 'MAX_PIXELS', 10 if kind == 'pixels' else subject.MAX_PIXELS):
        with pytest.raises(ValueError): subject.decode_image(pins['image-0'])


def test_execution_reserves_once_retains_failure_and_summary_has_no_private_inputs(selected):
    factory = Mock(side_effect=RuntimeError('private details'))
    output = selected.root/'out'
    with patch.object(subject, 'version', return_value='1.2.3'):
        with pytest.raises(RuntimeError): subject.execute(selected.root/'run.json', output, model_factory=factory)
        assert (output/'started.json').exists() and not (output/'measurement.json').exists()
        with pytest.raises(ValueError): subject.execute(selected.root/'run.json', output, model_factory=factory)
    assert factory.call_count == 1
    record = json.loads((output/'started.json').read_text())
    assert str(selected.root) not in repr(record)
    assert '场景' not in repr(record)


def test_success_writes_private_report_without_binding_or_activation(selected):
    model = Mock()
    metric = {'overall': {'top1': 2}, 'languages': {'zh': {'top1': 1}}}
    measure = Mock(return_value={'metrics': metric})
    with patch.object(subject, 'version', return_value='1.2.3'):
        result = subject.execute(selected.root/'run.json', selected.root/'out',
                                 model_factory=Mock(return_value=model), measure_fn=measure)
    assert result['status'] == 'scene_pair_measured'
    assert not result['pair_binding_created'] and not result['activation_performed']
    assert not result['dialect_relevance_measured'] and not result['family_relevance_accepted']
    assert str(selected.root) not in repr(result) and '场景' not in repr(result)
    assert (selected.root/'out'/'measurement.json').exists()
    model.bind.assert_not_called()


def test_deadline_includes_model_load_and_refuses_late_success(selected):
    measure = Mock(side_effect=AssertionError)
    with patch.object(subject, 'version', return_value='1.2.3'), patch.object(
            subject.time, 'monotonic', side_effect=[0, 121, 121]):
        with pytest.raises(ValueError):
            subject.execute(selected.root/'run.json', selected.root/'out',
                            model_factory=Mock(), measure_fn=measure)
    measure.assert_not_called()
    assert (selected.root/'out'/'started.json').exists()


def test_cli_redacts_native_python_errors_and_restores_logging(selected):
    def fail(*args):
        print('PRIVATE QUERY'); os.write(2, b'PRIVATE PATH'); raise RuntimeError('PRIVATE MODEL')
    output, error = io.StringIO(), io.StringIO()
    before = logging.root.manager.disable
    with patch.object(subject, 'execute', side_effect=fail), redirect_stdout(output), redirect_stderr(error):
        assert subject.run(['--run', '--configuration', str(selected.root/'run.json'),
                            '--output-directory', str(selected.root/'out')]) == 1
    assert output.getvalue() == ''
    assert json.loads(error.getvalue()) == {'error': 'semantic_scene_measurement_unavailable'}
    assert logging.root.manager.disable == before


def test_measure_reuses_one_model_and_scores_all_languages_with_pinned_inputs(selected):
    def vector(index, scale=1): return [scale if i == index else 0.0 for i in range(512)]
    class Tensor:
        shape = (1, 3, 224, 224)
        def unsqueeze(self, dim): return self
        def to(self, **kwargs): return self
    class Output:
        shape = (1, 512)
        def __init__(self, values): self.values = values
        def detach(self): return self
        def to(self, **kwargs): return self
        def __getitem__(self, index): return self
        def tolist(self): return self.values
    lookup = {text: vector(i) for i, case in enumerate(selected.dataset['cases'])
              for text in case['queries'].values()}
    encode = Mock(side_effect=[Output(vector(i, 2)) for i in range(4)])
    model = SimpleNamespace(_device='cpu', _pins=(), _recipe={'package_versions': {}},
        _model=SimpleNamespace(visual=SimpleNamespace(preprocess_cfg={'size': 224}), encode_image=encode),
        _torch=SimpleNamespace(float32='float32', inference_mode=nullcontext),
        _vector=Mock(side_effect=lambda text, check: lookup[text]),
        probe=Mock(return_value={'dimension': 512, 'relevance_measured': False}))
    transform = SimpleNamespace(__file__=__file__, PreprocessCfg=lambda **kwargs: kwargs,
        image_transform_v2=Mock(return_value=lambda image: Tensor()))
    original = subject.importlib.import_module
    def module(name):
        if name == 'open_clip.transform': return transform
        if name.startswith(('torchvision.', 'PIL.')): return SimpleNamespace(__file__=__file__)
        return original(name)
    with patch.object(subject, 'version', return_value='1.2.3'), patch.object(
            subject.importlib, 'import_module', side_effect=module), patch.object(
            subject, '_source_pin', return_value=SimpleNamespace(sha256='c'*64)), patch.object(
            subject, '_current'), patch.object(subject, 'verify_checkpoint'), patch.object(
            subject, 'observe_preprocessing', return_value={'schema': 'generated-test'}), patch.object(
            subject, 'decode_image', side_effect=lambda pin: SimpleNamespace(close=Mock())):
        record = subject.measure(model, selected.dataset, {image['id']: object() for image in selected.dataset['images']},
            {name: '1.2.3' for name in subject.IMAGE_PACKAGES}, float('inf'))
    assert encode.call_count == 4 and model._vector.call_count == 6
    transform.image_transform_v2.assert_called_once_with({'size': 224}, is_train=False)
    assert record['metrics']['overall']['top1'] == 6
    assert all(v['top1'] == 2 for v in record['metrics']['languages'].values())
    assert len(record['images']) == 4 and not record['activation_performed']
    assert not record['content_authenticity_verified'] and not record['library_database_opened']
    assert str(selected.root) not in repr(record) and '场景' not in repr(record)
