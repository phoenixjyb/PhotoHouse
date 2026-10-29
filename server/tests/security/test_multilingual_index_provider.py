"""Synthetic CPU stubs qualify adapter contracts, not real-model relevance."""
import contextlib
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'backend')]
import semantic_siglip as adapter
import _semantic_siglip_encoding as encoding
import build_multilingual_image_index as indexer
import serve_multilingual_semantic_text as serving
import qualify_multilingual_pilot as pilot
from app.access.search_policy_binding import capture_current_query_policy_binding
from app.access.semantic_encoder import JointSpaceBinding, SemanticUnavailable, SemanticUnsupported
import app.access.search_policy_binding as policy_binding
from app.access.semantic_provider_transport import create_provider_app
from app.access.visual_vector_loader import _read_vector


class Tensor:
    def __init__(self, values, shape): self.values, self.shape = values, shape
    def to(self, *_a, **_k): return self
    def detach(self): return self
    def __getitem__(self, _i): return self
    def tolist(self): return self.values


@pytest.fixture
def model(monkeypatch, tmp_path):
    class Torch:
        float32 = object()
        @staticmethod
        def set_num_threads(count): assert count == 2
        @staticmethod
        def inference_mode(): return contextlib.nullcontext()
    class Processor:
        def __init__(self): self.tokenizer = self; self.seen = []
        def __call__(self, text=None, images=None, **kwargs):
            if type(text) is str:
                assert kwargs['truncation'] is False
                return {'input_ids': list(range(65 if text == 'long' else 4))}
            if images is not None:
                return {'pixel_values': Tensor([0.0], (1,3,256,256))}
            assert kwargs['truncation'] is False and kwargs['max_length'] == 64
            self.seen.append(text[0])
            return {'input_ids': Tensor([1]*64, (1,64))}
    class Model:
        def get_image_features(self, **kwargs): return Tensor([1.0]+[0.0]*767, (1,768))
        def get_text_features(self, **kwargs):
            assert set(kwargs) == {'input_ids'}
            return Tensor([1.0]+[0.0]*767, (1,768))
    class Pin:
        def __init__(self, digest): self.sha256 = digest
    directory = tmp_path/'model'; directory.mkdir(mode=0o700)
    real_import = encoding.importlib.import_module
    monkeypatch.setattr(encoding, 'importlib', SimpleNamespace(import_module=
        lambda name: Torch if name == 'torch' else real_import(name)))
    monkeypatch.setattr(encoding.qualification, 'installed_versions', lambda: encoding.qualification.EXPECTED_PACKAGES)
    monkeypatch.setattr(encoding.qualification, 'inspect_model_files',
        lambda *_a: {n: Pin(v['sha256']) for n,v in encoding.qualification.OFFICIAL_ARTIFACTS.items()})
    monkeypatch.setattr(encoding.qualification, 'load_model', lambda *_a:
        {'torch': Torch, 'processor': Processor(), 'model': Model(),
         'source_pins': {}, 'preprocessor_config': {'fixture': True}})
    monkeypatch.setattr(encoding, '_source_pin', lambda _p: Pin('a'*64))
    monkeypatch.setattr(encoding, '_current', lambda _p: None)
    monkeypatch.setattr(encoding, 'verify_checkpoint', lambda _p: None)
    return adapter.SiglipModel.load(model_directory=str(directory),
        artifacts=encoding.qualification.OFFICIAL_ARTIFACTS,
        package_versions=encoding.qualification.EXPECTED_PACKAGES)


def bind(model):
    return model.bind(JointSpaceBinding(model.image_identity, model.text_identity, 'e'*64))


def private_json(path, value):
    path.write_text(json.dumps(value), encoding='utf-8');path.chmod(0o600)
    return path


def index_configuration(tmp_path, *, reviewed=True):
    from PIL import Image
    images = tmp_path/'images';images.mkdir(mode=0o700)
    assets=[]
    for aid, colour in [(1,'red'),(2,'blue')]:
        p=images/f'{aid}.png'
        Image.new('RGB',(16,16),colour).save(p);p.chmod(0o600)
        assets.append({'asset_id':str(aid),'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    cohort={'schema':'photohouse.multilingual_image_cohort.v1','library_id':'fixture-library',
            'reviewed':reviewed,'assets':assets}
    cp=private_json(tmp_path/'cohort.json',cohort)
    return private_json(tmp_path/'config.json',{'schema':'photohouse.multilingual_image_index_run.v1',
        'model_directory':str(tmp_path/'model'),'artifacts':encoding.qualification.OFFICIAL_ARTIFACTS,
        'package_versions':encoding.qualification.EXPECTED_PACKAGES,'cohort':str(cp),'max_elapsed_seconds':30})


def inspect(path, *, expected_library):
    cohort=json.loads((path.parent.parent/'cohort.json').read_text())
    return indexer.inspect_index(path,expected_library=expected_library,expected_cohort=cohort)


def test_index_prepares_complete_768_artifacts_without_database_or_legacy_lookup(model,tmp_path):
    config=index_configuration(tmp_path)
    result=indexer.execute(config,tmp_path/'output',model_loader=lambda **_k:model)
    manifest,records,identities=inspect(tmp_path/'output/index.json',expected_library='fixture-library')
    assert result['image_count']==len(records)==2
    assert identities['image']==model.image_identity
    assert identities['text']==model.text_identity
    assert manifest['production_published'] is False and manifest['activation_performed'] is False
    assert all(len(_read_vector(tmp_path/'output',r))==768 for r in records)
    assert str(tmp_path) not in json.dumps(manifest)
    with pytest.raises(ValueError):indexer.execute(config,tmp_path/'output',model_loader=lambda **_k:model)
    with pytest.raises(ValueError):inspect(tmp_path/'output/index.json',expected_library='another-library')


@pytest.mark.parametrize('damage',['vector','metadata','missing','manifest','component_checksum','omitted_record','substituted_source','model_receipt'])
def test_index_refuses_partial_or_corrupt_complete_cohort(model,tmp_path,damage):
    config=index_configuration(tmp_path);target=tmp_path/'output'
    indexer.execute(config,target,model_loader=lambda **_k:model)
    manifest,records,_ids=inspect(target/'index.json',expected_library='fixture-library')
    record=records[-1];metadata=(target/record.relative_path).with_suffix('.json')
    if damage=='vector':(target/record.relative_path).write_bytes(b'corrupt')
    elif damage=='metadata':metadata.write_text('{}')
    elif damage=='missing':(target/record.relative_path).unlink()
    elif damage=='manifest':
        manifest['complete']=False;private_json(target/'index.json',manifest)
    elif damage=='omitted_record':
        manifest['records'].pop();manifest['image_timings_seconds'].pop();private_json(target/'index.json',manifest)
    elif damage=='model_receipt':
        manifest['model_receipt']['recipes']['image']['role']='text';private_json(target/'index.json',manifest)
    else:
        values=asdict(record)
        values['source_sha256' if damage=='substituted_source' else 'component_sha256']='0'*64
        private_json(metadata,values)
        manifest['records'][-1]['metadata_sha256']=hashlib.sha256(metadata.read_bytes()).hexdigest()
        private_json(target/'index.json',manifest)
    with pytest.raises((ValueError,TypeError,KeyError)):
        inspect(target/'index.json',expected_library='fixture-library')


def test_unreviewed_or_stale_image_refused_before_model_and_partial_failure_is_not_complete(model,tmp_path):
    config=index_configuration(tmp_path,reviewed=False)
    with pytest.raises(ValueError):indexer.execute(config,tmp_path/'out',model_loader=lambda **_k:pytest.fail('model loaded'))
    assert not (tmp_path/'out').exists()
    c=json.loads(config.read_text());cohort=Path(c['cohort']);d=json.loads(cohort.read_text());d['reviewed']=True
    private_json(cohort,d);Path(d['assets'][-1]['path']).write_bytes(b'changed')
    with pytest.raises(ValueError):indexer.execute(config,tmp_path/'out',model_loader=lambda **_k:pytest.fail('model loaded'))
    # No manifest may claim a completed candidate when encoding fails midway.
    d['assets'][-1]['sha256']=hashlib.sha256(Path(d['assets'][-1]['path']).read_bytes()).hexdigest();private_json(cohort,d)
    count=[]
    def fail(_pin,**_kwargs):
        count.append(1)
        if len(count)>1:raise SemanticUnavailable()
        return [1.0]+[0.0]*767
    model.encode_image=fail
    with pytest.raises(SemanticUnavailable):indexer.execute(config,tmp_path/'partial',model_loader=lambda **_k:model)
    assert (tmp_path/'partial/started.json').exists()
    assert not (tmp_path/'partial/index.json').exists()


def test_binding_normalization_original_query_and_overflow_are_protected(model):
    bind(model)
    out=model.encode('A RED kite')
    assert model._handle['processor'].seen==['a red kite']
    assert out.query_sha256==hashlib.sha256(b'A RED kite').hexdigest()
    assert len(out.vector)==768
    with pytest.raises(SemanticUnsupported):model.encode('a dog that is not on grass')
    with pytest.raises(SemanticUnsupported):model.encode('long')
    assert model._handle['processor'].seen==['a red kite']
    with pytest.raises(SemanticUnavailable):bind(model)
    r=model.receipt();r['recipes']['text']['normalization']='altered'
    assert model.receipt()['recipes']['text']['normalization']=='unicode_lowercase'


def test_siglip_rechecks_cancellation_after_final_policy_source_read(model, monkeypatch):
    bind(model)
    original_read = policy_binding._read_source
    source_reads = 0
    expired = False

    def observed_read(path):
        nonlocal source_reads, expired
        value = original_read(path)
        source_reads += 1
        if source_reads == 6:
            expired = True
        return value

    monkeypatch.setattr(policy_binding, '_read_source', observed_read)
    processor = model._handle['processor']
    model_calls = []
    original_text_features = model._handle['model'].get_text_features

    def observed_text_features(**kwargs):
        model_calls.append(kwargs)
        return original_text_features(**kwargs)

    monkeypatch.setattr(model._handle['model'], 'get_text_features', observed_text_features)

    def check():
        if expired:
            raise RuntimeError('deadline expired during final policy-source read')

    with pytest.raises(SemanticUnavailable):
        model.encode('a quiet family garden', check=check)
    assert source_reads == 6
    assert processor.seen == []
    assert model_calls == []
    assert model._lock.acquire(blocking=False)
    model._lock.release()


def test_wrong_legacy_or_recipe_identity_cannot_bind(model):
    for image,text in [(replace(model.image_identity,dimension=512),replace(model.text_identity,dimension=512)),
        (model.image_identity,replace(model.text_identity,preprocessing_sha256='b'*64))]:
        with pytest.raises(SemanticUnavailable):model.bind(JointSpaceBinding(image,text,'e'*64))


def test_authenticated_loopback_provider_exercises_real_transport_shape_and_refuses_exclusions(model):
    bind(model);token='fixture_'+('x'*40);port=43871
    app=create_provider_app(model,bearer_token=token,port=port)
    with TestClient(app,base_url=f'http://127.0.0.1:{port}',client=('127.0.0.1',41234))as client:
        payload={'version':1,'query':'A RED kite','binding_sha256':model.binding.binding_sha256}
        denied=client.post('/v1/encode-text',json=payload,headers={'Authorization':'Bearer invalid'})
        assert denied.status_code==401 and model._handle['processor'].seen==[]
        good=client.post('/v1/encode-text',json=payload,headers={'Authorization':'Bearer '+token})
        assert good.status_code==200 and len(good.json()['vector'])==768
        assert good.json()['query_sha256']==hashlib.sha256(b'A RED kite').hexdigest()
        bad=client.post('/v1/encode-text',json=payload|{'query':'no people'},headers={'Authorization':'Bearer '+token})
        assert bad.status_code==503  # Legacy clients have not opted into refusal receipts.
        bad=client.post('/v1/encode-text',json=payload|{'query':'no people'},
            headers={'Authorization':'Bearer '+token,'X-PhotoHouse-Semantic-Refusal':'1'})
        assert bad.status_code==422
        assert model._handle['processor'].seen==['a red kite']


def test_planning_imports_no_optional_ml_and_never_reads_private_files():
    program="""
import builtins,sys
original=builtins.__import__
def guarded(name,*a,**k):
 if name.split('.')[0] in {'torch','transformers','PIL','numpy','torchvision'}:raise AssertionError('ML import')
 return original(name,*a,**k)
builtins.__import__=guarded
sys.path[:0]=%r
import build_multilingual_image_index as i,serve_multilingual_semantic_text as s,qualify_multilingual_pilot as p
def denied(*a,**k):raise AssertionError('private file read')
i._load_private_document=s._load_private_document=p._load_private_document=denied
assert i.run([])==s.run([])==p.run([])==0
assert i.run(['--configuration','/private/no.json'])==2
assert s.run(['--configuration','/private/no.json'])==2
"""%[str(ROOT/'scripts'),str(ROOT/'backend')]
    result=subprocess.run([sys.executable,'-I','-B','-c',program],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_serving_requires_secret_binding_and_pins_before_model_load(monkeypatch,tmp_path):
    value={'schema':'photohouse.multilingual_text_provider.v1','model_directory':str(tmp_path/'model'),
        'artifacts':encoding.qualification.OFFICIAL_ARTIFACTS,'package_versions':encoding.qualification.EXPECTED_PACKAGES,
        'binding':None,'credential_file':None,'port':43871}
    p=private_json(tmp_path/'provider.json',value)
    with pytest.raises(ValueError):serving.configuration(p,serving=True)
    monkeypatch.setattr(encoding.qualification,'installed_versions',lambda:{'torch':'wrong'})
    monkeypatch.setattr(encoding.importlib,'import_module',lambda _n:pytest.fail('ML imported'))
    with pytest.raises(SemanticUnavailable):adapter.SiglipModel.load(model_directory=str(tmp_path),
        artifacts=encoding.qualification.OFFICIAL_ARTIFACTS,package_versions=encoding.qualification.EXPECTED_PACKAGES)


def test_explicit_serving_binds_only_loopback_with_bounded_server_options(model,monkeypatch):
    binding=JointSpaceBinding(model.image_identity,model.text_identity,'e'*64)
    config={'schema':'photohouse.multilingual_text_provider.v1','model_directory':'/private/model','artifacts':encoding.qualification.OFFICIAL_ARTIFACTS,
            'package_versions':encoding.qualification.EXPECTED_PACKAGES,'port':43871}
    monkeypatch.setattr(serving,'configuration',lambda _path,**_kwargs:(config,binding,'x'*40))
    monkeypatch.setattr(serving.SiglipModel,'load',lambda **_kwargs:model)
    calls=[]
    monkeypatch.setitem(sys.modules,'uvicorn',SimpleNamespace(run=lambda app,**kwargs:calls.append(kwargs)))
    assert serving.run(['serve','--configuration','/private/provider.json'])==0
    assert model.binding==binding
    assert len(calls)==1
    assert calls[0]['host']=='127.0.0.1' and calls[0]['workers']==1
    assert calls[0]['access_log']is False and calls[0]['proxy_headers']is False
    assert calls[0]['forwarded_allow_ips']==''
    assert calls[0]['limit_concurrency']==8 and calls[0]['backlog']==8


@pytest.mark.parametrize('schema', [
    'photohouse.multilingual_text_provider.v1',
    'photohouse.multilingual_text_provider.v2',
])
def test_probe_reports_current_policy_separately_from_model_receipt_without_listener(
        schema, model, monkeypatch, capsys):
    inner = JointSpaceBinding(model.image_identity, model.text_identity, 'e'*64)
    binding = inner
    config = {'schema': schema}
    if schema.endswith('.v1'):
        binding = inner
    else:
        from semantic_bilingual_clothing import POLICY
        recipe = serving.bilingual_recipe(inner)
        binding = JointSpaceBinding(inner.image_identity,
            replace(inner.text_identity, preprocessing_sha256=recipe['recipe_sha256']), 'f'*64)
        config.update(inner_binding=asdict(inner), normalization_policy=POLICY)
    config.update(model_directory='/private/model', artifacts=encoding.qualification.OFFICIAL_ARTIFACTS,
        package_versions=encoding.qualification.EXPECTED_PACKAGES, port=43871)
    monkeypatch.setattr(serving, 'configuration', lambda _path, **_kwargs: (config, binding, None))
    monkeypatch.setattr(serving.SiglipModel, 'load', lambda **_kwargs: model)

    assert serving.run(['probe', '--configuration', '/private/provider.json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['model'] == model.receipt()
    assert 'query_policy_binding' not in report['model']
    assert report['query_policy_binding'] == capture_current_query_policy_binding()
    assert report['query_policy_binding']['policy_version'] == 3
    assert report['provider_binding'] == asdict(binding)
    assert report['models_loaded'] is True
    assert report['listener_started'] is False
    assert report['activation_performed'] is False


def test_protected_pilot_uses_only_new_fixture_db_and_exercises_gate_filters_corruption_and_revocation(model,tmp_path):
    config=index_configuration(tmp_path);target=tmp_path/'index'
    indexer.execute(config,target,model_loader=lambda **_k:model)
    pconfig=json.loads(config.read_text())
    pconfig={k:v for k,v in pconfig.items()if k not in {'schema','max_elapsed_seconds'}}|{
        'schema':'photohouse.multilingual_pilot_run.v1','index':str(target/'index.json'),
        'queries':[{'id':language,'language':language,'text':text,'relevant_asset_id':'1'}
            for language,text in [('en','a red kite'),('zh','红色风筝'),('zh-en','红色kite')]],
        'max_elapsed_seconds':120,'repetitions':1}
    p=private_json(tmp_path/'pilot.json',pconfig)
    result=pilot.execute(p,tmp_path/'pilot',model_loader=lambda **_k:model)
    assert result['status']=='isolated_multilingual_pilot_measured'
    assert result['protected_request_latency']['count']==3
    assert result['activation_approved'] is False
    measurement=json.loads((tmp_path/'pilot/measurement.json').read_text())
    assert len(measurement['protected_checks'])==12
    assert measurement['tcp_tls_latency_measured'] is False
    assert measurement['production_database_opened'] is False
    assert measurement['real_account_sessions_created'] is False
    assert measurement['network_listener_started'] is False
    for query in pconfig['queries']:assert query['text'] not in json.dumps(measurement,ensure_ascii=False)
    indexer.inspect_index(target/'index.json',expected_library='fixture-library',
        expected_cohort=json.loads((tmp_path/'cohort.json').read_text()))


def test_network_configuration_requires_explicit_v2_and_private_tls_files(tmp_path):
    config=index_configuration(tmp_path)
    base=json.loads(config.read_text())
    base.update(schema='photohouse.multilingual_pilot_run.v2',index=str(tmp_path/'index.json'),
        queries=[{'id':'q','language':'en','text':'red kite','relevant_asset_id':'1'}],repetitions=1)
    files={key:str(private_json(tmp_path/(key+'.pem'),{}))for key in ('certificate','private_key','ca_file')}
    base['network']={'transport':'loopback_https_tcp',**files}
    path=private_json(tmp_path/'network.json',base)
    assert pilot.configuration(path)[0]['network']['transport']=='loopback_https_tcp'
    for change in ({'schema':'photohouse.multilingual_pilot_run.v1'},
                   {'network':{**base['network'],'transport':'asgi'}},
                   {'network':{**base['network'],'ca_file':'relative.pem'}}):
        with pytest.raises((pilot.PilotRefused,ValueError)):
            pilot.configuration(private_json(path,{**base,**change}))


def test_network_canary_selects_real_encoder_transport_and_closes_resources(model,tmp_path,monkeypatch):
    """Generated source fixture: fake servers replace sockets; never native timing."""
    import httpx
    import app.access.semantic_encoder as encoder_module
    config=index_configuration(tmp_path);target=tmp_path/'index'
    indexer.execute(config,target,model_loader=lambda **_k:model)
    base=json.loads(config.read_text());base.update(schema='photohouse.multilingual_pilot_run.v2',
        index=str(target/'index.json'),queries=[{'id':'q','language':'en','text':'red kite','relevant_asset_id':'1'}],
        repetitions=1)
    files={key:str(private_json(tmp_path/(key+'.pem'),{}))for key in ('certificate','private_key','ca_file')}
    base['network']={'transport':'loopback_https_tcp',**files}
    registry={};closed=[];sockets=[]
    class Socket:
        def __init__(self,port):self.port=port
        def getsockname(self):return ('127.0.0.1',self.port)
        def close(self):closed.append(self.port)
    def reserve():
        sock=Socket(44001+len(sockets));sockets.append(sock);return sock
    @contextlib.contextmanager
    def server(app,sock,certificate=None,private_key=None):
        scheme='https'if certificate else'http'
        if certificate:assert certificate==files['certificate']and private_key==files['private_key']
        origin=f'{scheme}://127.0.0.1:{sock.port}'
        asgi=TestClient(app,base_url=origin,client=('127.0.0.1',41234))
        asgi.__enter__()
        registry[origin]={'app':app,'client':asgi}
        try:yield
        finally:
            registry.pop(origin,None)
            asgi.__exit__(None,None,None)
            sock.close()
    @contextlib.contextmanager
    def client(origin,ca_file=None):
        if origin.startswith('https:'):assert ca_file==files['ca_file']
        yield registry[origin]['client']
    monkeypatch.setitem(sys.modules,'semantic_loopback_network',SimpleNamespace(
        reserve_socket=reserve,server=server,http_client=client))
    real_client=httpx.Client;encoder_calls=[]
    def forward(request):
        origin=str(request.url).rsplit('/v1/encode-text',1)[0]
        encoder_calls.append(('forward',origin))
        r=registry[origin]['client'].post('/v1/encode-text',
            content=request.content,headers=dict(request.headers))
        encoder_calls.append(('response',r.status_code))
        return httpx.Response(r.status_code,content=r.content,headers=r.headers)
    def encoder_client(**kwargs):
        assert kwargs['transport']is None and kwargs['trust_env']is False
        encoder_calls.append(True)
        return real_client(**{**kwargs,'transport':httpx.MockTransport(forward)})
    monkeypatch.setattr(encoder_module.httpx,'Client',encoder_client)
    def no_asgi_encoder(*_a,**_k):raise AssertionError('network mode fell back to ASGI adapter')
    monkeypatch.setattr(pilot,'LocalSemanticEncoder',no_asgi_encoder)
    result=pilot.execute(private_json(tmp_path/'network.json',base),tmp_path/'measurement',model_loader=lambda **_k:model)
    assert len(result['protected_checks'])==12
    assert encoder_calls.count(True)>0 and ('response',200)in encoder_calls
    assert not any(item==('response',503)for item in encoder_calls)
    measured=json.loads((tmp_path/'measurement/measurement.json').read_text())
    assert measured['network_listener_started']is True and measured['tcp_tls_latency_measured']is True
    assert measured['canary_resources_closed']is True and measured['remote_device_latency_measured']is False
    assert measured['tls_receipt']['trust']=='per_run_ca_only'
    assert set(closed)=={44001,44002}
    assert not registry


def test_bilingual_v2_run_serves_bound_original_query_after_normalization(model,tmp_path,monkeypatch):
    from dataclasses import asdict, replace
    from fastapi.testclient import TestClient
    from semantic_bilingual_clothing import POLICY
    inner=JointSpaceBinding(model.image_identity,model.text_identity,'e'*64)
    recipe=serving.bilingual_recipe(inner)
    outer=JointSpaceBinding(inner.image_identity,replace(inner.text_identity,
        preprocessing_sha256=recipe['recipe_sha256']),'f'*64)
    credential=private_json(tmp_path/'credential.json',{'token':'x'*40})
    config=private_json(tmp_path/'provider.json',{
        'schema':'photohouse.multilingual_text_provider.v2','model_directory':str(tmp_path/'model'),
        'artifacts':encoding.qualification.OFFICIAL_ARTIFACTS,
        'package_versions':encoding.qualification.EXPECTED_PACKAGES,'port':43871,
        'binding':asdict(outer),'inner_binding':asdict(inner),'normalization_policy':POLICY,
        'credential_file':str(credential)})
    monkeypatch.setattr(serving.SiglipModel,'load',lambda **_kwargs:model)
    apps=[]
    monkeypatch.setitem(sys.modules,'uvicorn',SimpleNamespace(run=lambda app,**kwargs:apps.append(app)))
    assert serving.run(['serve','--configuration',str(config)])==0
    query='穿蓝色衬衫的男孩'
    with TestClient(apps[0],base_url='http://127.0.0.1:43871',client=('127.0.0.1',53000))as client:
        request={'version':1,'binding_sha256':outer.binding_sha256,'query':query}
        assert client.post('/v1/encode-text',headers={'Authorization':'Bearer '+'y'*40},json=request).status_code==401
        response=client.post('/v1/encode-text',headers={'Authorization':'Bearer '+'x'*40},json=request)
        assert response.status_code==200,response.text
        assert response.json()['query_sha256']==hashlib.sha256(query.encode()).hexdigest()
        assert response.json()['binding_sha256']==outer.binding_sha256
    assert model._handle['processor'].seen==['a boy wearing a blue shirt']
