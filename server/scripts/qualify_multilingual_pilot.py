#!/usr/bin/env python3
"""Protected ASGI/CPU canary over an explicit unpublished multilingual index.

Uses only a newly generated private database, accounts, credentials and vector
copies. Version 1 opens no listener; explicit version 2 measures temporary
loopback HTTPS/TCP. Neither mode opens a production DB or enables the feature.
"""
import argparse
from contextlib import closing, contextmanager, ExitStack
from dataclasses import asdict, replace
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from unittest.mock import patch

from build_multilingual_image_index import inspect_index, validate_cohort, npy_bytes
from semantic_siglip import SiglipModel
import qualify_multilingual_scenes as qualification
from qualify_semantic_pair import canonical, output_target, write_record, quiet_dependencies
from app.access.model_deployment import _load_private_document
from app.access.private_storage import require_private_directory, require_private_file
from app.access.semantic_encoder import JointSpaceBinding, LocalSemanticEncoder, _valid_query
from app.access.search_exclusions import requires_semantic_clarification
from app.access.visual_vector_loader import _read_vector, _COLUMNS


class PilotRefused(ValueError):
    def __init__(self, reason='contract_refused'):
        super().__init__('multilingual_pilot_measurement_unavailable:' + reason)


def _require(value, reason='contract_refused'):
    if not value:
        raise PilotRefused(reason)


def configuration(path):
    value = _load_private_document(path, source_root=qualification.ROOT.parent)
    fields = {'schema', 'model_directory', 'artifacts', 'package_versions',
        'index', 'cohort', 'queries', 'repetitions', 'max_elapsed_seconds'}
    _require(type(value) is dict)
    network = value.get('schema') == 'photohouse.multilingual_pilot_run.v2'
    _require(set(value) == fields | ({'network'} if network else set()))
    _require(value['schema'] in ('photohouse.multilingual_pilot_run.v1',
                                'photohouse.multilingual_pilot_run.v2')
        and type(value['model_directory']) is str
        and value['artifacts'] == qualification.OFFICIAL_ARTIFACTS
        and value['package_versions'] == qualification.EXPECTED_PACKAGES
        and type(value['repetitions']) is int and 1 <= value['repetitions'] <= 10
        and type(value['max_elapsed_seconds']) is int and 30 <= value['max_elapsed_seconds'] <= 1800
        and type(value['index']) is str and type(value['cohort']) is str
        and type(value['queries']) is list and 1 <= len(value['queries']) <= 12)
    cohort = validate_cohort(_load_private_document(value['cohort'], source_root=qualification.ROOT.parent))
    ids = {a['asset_id'] for a in cohort['assets']}
    seen = set()
    for query in value['queries']:
        _require(type(query) is dict and set(query) == {'id', 'language', 'text', 'relevant_asset_id'})
        _require(type(query['id']) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', query['id'])
            and query['id'] not in seen and query['language'] in ('en', 'zh', 'zh-en')
            and _valid_query(query['text']) and not requires_semantic_clarification(query['text'])
            and query['relevant_asset_id'] in ids)
        seen.add(query['id'])
    if network:
        net = value['network']
        _require(type(net) is dict and set(net) == {'transport', 'certificate', 'private_key', 'ca_file'}
            and net['transport'] == 'loopback_https_tcp')
        for key in ('certificate', 'private_key', 'ca_file'):
            _require(type(net[key]) is str and Path(net[key]).is_absolute()
                and '..' not in Path(net[key]).parts
                and not Path(net[key]).resolve().is_relative_to(qualification.ROOT.parent.resolve()))
            require_private_file(net[key])
    return value, cohort


def _summary(samples):
    ordered = sorted(samples)
    return {'count': len(ordered), 'p50_ms': ordered[math.ceil(len(ordered)*.5)-1],
            'p95_ms': ordered[math.ceil(len(ordered)*.95)-1], 'max_ms': ordered[-1]}


def _fixture(database, records, library, tokens, now):
    """Only this newly created synthetic database receives fixture rows."""
    from app.access.schema import apply_schema
    from app.access.credentials import session_digest
    with closing(sqlite3.connect(database)) as db, db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA foreign_keys=ON')
        db.executescript('''
CREATE TABLE assets(id INTEGER PRIMARY KEY,path TEXT,hash_sha256 TEXT,status TEXT,mime TEXT,width INTEGER,height INTEGER,duration_sec REAL,taken_at TEXT);
CREATE TABLE captions(id INTEGER PRIMARY KEY,asset_id INTEGER,text TEXT,user_edited INTEGER,superseded INTEGER);
CREATE TABLE face_detections(id INTEGER PRIMARY KEY,asset_id INTEGER,person_id INTEGER,label_source TEXT);
CREATE TABLE tags(id INTEGER PRIMARY KEY,name TEXT,type TEXT);
CREATE TABLE asset_tags(id INTEGER PRIMARY KEY,asset_id INTEGER,tag_id INTEGER,source TEXT);
CREATE TABLE asset_tag_blocks(id INTEGER PRIMARY KEY,asset_id INTEGER,tag_id INTEGER);
CREATE TABLE access_stories(id TEXT PRIMARY KEY,asset_id INTEGER,library_id TEXT,author_id TEXT,revision INTEGER,title TEXT,text TEXT,updated_at INTEGER,deleted INTEGER);
''')
        apply_schema(db.execute)
        for index, (name, role) in enumerate((('pilot-owner','owner'),('pilot-viewer','viewer'),('pilot-other','owner')), 1):
            db.execute('INSERT INTO access_accounts(id,phone_login,password_hash,state) VALUES(?,?,?,?)',
                (name,f'+1202555010{index}','synthetic-unused-password-hash','active'))
        db.execute('INSERT INTO access_libraries VALUES(?,?,?)',(library,'active','pilot-owner'))
        for name, role in [('pilot-owner','owner'),('pilot-viewer','viewer'),('pilot-other','owner')]:
            db.execute('INSERT INTO access_memberships VALUES(?,?,?,?,1,NULL,0,?)',
                (name,library,'approved',role,'pilot-owner'))
            db.execute('INSERT INTO access_sessions VALUES(?,?,?,0)',(session_digest(tokens[name]),name,now+3600))
        from app.access.visual_vector_schema import create_visual_vector_schema
        create_visual_vector_schema(db)
        for index, record in enumerate(records):
            day = '2026-01-01' if index%2 == 0 else '2026-01-02'
            db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,NULL,?)',
                (int(record.asset_id),'synthetic-fixture-no-original',record.source_sha256,'active','image/jpeg',16,16,day))
            db.execute('INSERT INTO access_asset_libraries VALUES(?,?)',(int(record.asset_id),library))
            db.execute('INSERT INTO captions VALUES(?,?,?,0,0)',(index+1,int(record.asset_id),'Synthetic fixture caption'))
            values=asdict(record)
            db.execute('INSERT INTO image_vector_artifacts('+_COLUMNS+') VALUES('+','.join('?' for _ in values)+')',
                tuple(values[name] for name in _COLUMNS.split(',')))


def measure(model, index_path, cohort, config, target, deadline):
    with ExitStack() as resources:
        result = _measure(model, index_path, cohort, config, target, deadline, resources)
    # Do not publish a successful measurement unless every owned listener stopped.
    result['canary_resources_closed'] = True
    return result


def _measure(model, index_path, cohort, config, target, deadline, resources):
    import httpx
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.access import discovery as d
    from app.access.credentials import session_digest
    from app.access.discovery_provider import ReviewedIndex, MemoryIndexProvider
    from app.access.discovery_transport import DiscoveryRuntime
    from app.access.transport import AccessRuntime
    from app.access.service import AccessService
    from app.access.semantic_configuration import load_semantic_runtime
    from app.access.semantic_provider_transport import create_provider_app

    manifest, records, identities = inspect_index(index_path,
        expected_library=cohort['library_id'], expected_cohort=cohort)
    _require(identities['image'] == model.image_identity and identities['text'] == model.text_identity)
    library = cohort['library_id']
    root = Path(index_path).parent
    vectors = target/'fixture-vectors';vectors.mkdir(mode=0o700)
    for record in records:
        # Copy verified derived vectors, never the original photos or an existing DB.
        raw = (root/record.relative_path).read_bytes()
        _require(hashlib.sha256(raw).hexdigest() == record.file_sha256)
        p = vectors/record.relative_path;p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with p.open('xb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        p.chmod(0o600);require_private_file(p)
    database = target/'synthetic.sqlite'
    with database.open('xb'): pass
    database.chmod(0o600);require_private_file(database)
    now=int(time.time())
    tokens={name:secrets.token_urlsafe(32) for name in ('pilot-owner','pilot-viewer','pilot-other')}
    _fixture(database,records,library,tokens,now)
    network = config['schema'] == 'photohouse.multilingual_pilot_run.v2'
    tls_hashes = ({key: hashlib.sha256(Path(config['network'][key]).read_bytes()).hexdigest()
                   for key in ('certificate', 'ca_file')} if network else None)
    origin='https://pilot.photohouse.test'
    port=43871
    if network:
        import semantic_loopback_network as net
        provider_socket=net.reserve_socket();resources.callback(provider_socket.close)
        api_socket=net.reserve_socket();resources.callback(api_socket.close)
        port=provider_socket.getsockname()[1]
        origin=f'https://127.0.0.1:{api_socket.getsockname()[1]}'
    @contextmanager
    def connection():
        with closing(sqlite3.connect(database,timeout=.25)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA query_only=ON')
            yield db
    access=AccessRuntime(connection,origin,clock=lambda:now)
    with closing(sqlite3.connect(database)) as db:
        with d.ReadBudget().attempt(db,lambda:False)as (_check,read):
            source=d.scoped_source(library,read)
    ids=tuple(record.asset_id for record in sorted(records,key=lambda r:int(r.asset_id)))
    review=ReviewedIndex(library,'1',ids,ids,d.digest(source))
    discovery=DiscoveryRuntime(access,MemoryIndexProvider((review,)),d.ReadBudget())
    # This binding attests only to an isolated technical canary, never to activation.
    technical_receipt=hashlib.sha256(canonical({'role':'isolated_fixture_not_activation',
        'index_sha256':hashlib.sha256(Path(index_path).read_bytes()).hexdigest()})).hexdigest()
    binding=JointSpaceBinding(identities['image'],identities['text'],technical_receipt)
    model.bind(binding)
    provider_token=secrets.token_urlsafe(32)
    credential=target/'credential.json';write_record(target,credential.name,{'token':provider_token})
    runtime_path=target/'runtime.json'
    write_record(target,runtime_path.name,{'format_version':2,'vector_root':str(vectors),
        'encoder_url':f'http://127.0.0.1:{port}/v1/encode-text','encoder_timeout_seconds':2.0,
        'credential_file':str(credential),'binding':asdict(binding),'binding_sha256':binding.binding_sha256,
        'operator_reviewed':True,'pilot_owner_account_id':'pilot-owner'})
    runtime=load_semantic_runtime(runtime_path,discovery=discovery,
        source_root=qualification.ROOT.parent,protected_paths=(database,))
    counters={'provider_calls':0,'vector_reads':0,'model_encode_calls':0}
    during_encode=[None]
    class ObservedProvider:
        binding=model.binding
        def encode(self,query,*,check):
            counters['provider_calls']+=1
            counters['model_encode_calls']+=1
            if during_encode[0] is not None:
                callback=during_encode[0];during_encode[0]=None;callback()
            return model.encode(query,check=check)
    provider_app=create_provider_app(ObservedProvider(),bearer_token=provider_token,port=port)
    original_read=_read_vector
    def observed_read(*args):
        counters['vector_reads']+=1
        return original_read(*args)
    def check():
        _require(time.monotonic()<deadline)
    def mutate(sql,args=()):
        with closing(sqlite3.connect(database,timeout=.25))as db, db:db.execute(sql,args)
    rows=[];protected=[];denial_times=[]
    if network:
        resources.enter_context(net.server(provider_app,provider_socket))
        provider_context=net.http_client(f'http://127.0.0.1:{port}')
    else:
        provider_context=TestClient(provider_app,base_url=f'http://127.0.0.1:{port}',client=('127.0.0.1',41234))
    with provider_context as provider:
        before=dict(counters)
        denied=provider.post('/v1/encode-text',json={'version':1,
            'binding_sha256':binding.binding_sha256,'query':config['queries'][0]['text']},
            headers={'Authorization':'Bearer invalid'})
        _require(denied.status_code==401 and counters==before)
        protected.append('provider_bad_bearer_denied_before_model')
        def forward(request):
            response=provider.request(request.method,'/v1/encode-text',content=request.content,
                headers=dict(request.headers))
            return httpx.Response(response.status_code,content=response.content,headers=response.headers)
        if not network:
            runtime=replace(runtime,encoder=LocalSemanticEncoder(binding,
                f'http://127.0.0.1:{port}/v1/encode-text',bearer_token=provider_token,
                transport=httpx.MockTransport(forward)))
        app=create_app(access_runtime=access,discovery_runtime=discovery,
                       assistant_enabled=True,semantic_search_runtime=runtime)
        if network:
            resources.enter_context(net.server(app,api_socket,
                certificate=config['network']['certificate'],private_key=config['network']['private_key']))
            client_context=net.http_client(origin,ca_file=config['network']['ca_file'])
        else:
            client_context=TestClient(app,base_url=origin)
        with client_context as client, patch('app.access.semantic_search._read_vector',observed_read):
            base=f'/libraries/{library}/semantic-search/v1/query'
            query=config['queries'][0]['text']
            def request(text=query,*,token=None,filters=None):
                check();started=time.monotonic()
                response=client.post(base,json={'query':text,'filters':filters or {}},
                    headers={'Authorization':'Bearer '+(token or tokens['pilot-owner'])})
                check();return response,(time.monotonic()-started)*1000
            for label,token in [('viewer',tokens['pilot-viewer']),('other_owner',tokens['pilot-other']),('invalid','invalid')]:
                before=dict(counters)
                response,elapsed=request(token=token)
                _require(response.status_code==401 and counters==before,
                         f'admission_{label}_http_{response.status_code}')
                denial_times.append(elapsed);protected.append(label+'_denied_before_vectors_and_provider')
            before=dict(counters)
            response=client.post(base,content=b'{'*25000,
                headers={'Authorization':'Bearer '+tokens['pilot-viewer'],'Content-Type':'application/json'})
            _require(response.status_code==401 and counters==before)
            protected.append('viewer_oversized_body_denied_before_body_processing')
            for text in ('no people','没有人的照片','没有people'):
                before=dict(counters);response,_elapsed=request(text)
                _require(response.status_code==422 and counters==before,
                         f'exclusion_http_{response.status_code}')
            protected.append('three_language_exclusions_clarified_before_vectors_and_provider')
            # Warmup is reported separately from the repeated request samples.
            response,warmup=request();_require(response.status_code==200)
            for item in config['queries']:
                for repetition in range(config['repetitions']):
                    response,elapsed=request(item['text'])
                    _require(response.status_code==200)
                    body=response.json();found=[x['id']for x in body['items']]
                    _require(set(found)<=set(ids) and body['total']==len(records)
                        and body['semantic']['candidate_count']==len(records))
                    rows.append({'query_id':item['id'],'language':item['language'],
                        'query_sha256':hashlib.sha256(item['text'].encode()).hexdigest(),
                        'repetition':repetition,'elapsed_ms':elapsed,
                        'top1_relevant':bool(found and found[0]==item['relevant_asset_id'])})
            allowed={r.asset_id for i,r in enumerate(records)if i%2==1}
            response,_elapsed=request(filters={'date':{'from':'2026-01-02','to':'2026-01-02'}})
            _require(response.status_code==200 and response.json()['total']==len(allowed)
                and {x['id']for x in response.json()['items']}<=allowed)
            protected.append('date_remains_hard_filter')
            # Deliberately damage only the disposable vector copy.
            p=vectors/records[-1].relative_path;raw=p.read_bytes()
            before=counters['provider_calls'];p.write_bytes(b'corrupt')
            try:
                response,_elapsed=request();_require(response.status_code==503 and counters['provider_calls']==before)
            finally:p.write_bytes(raw)
            protected.append('corrupt_eligible_vector_refuses_without_partial_ranking')
            p.unlink();before=counters['provider_calls']
            try:
                response,_elapsed=request();_require(response.status_code==503 and counters['provider_calls']==before)
            finally:
                with p.open('xb')as stream:stream.write(raw)
                p.chmod(0o600)
            protected.append('missing_eligible_vector_refuses_without_partial_ranking')
            during_encode[0]=lambda:mutate("UPDATE access_memberships SET role='viewer',revision=revision+1 WHERE account_id='pilot-owner'")
            response,_elapsed=request();_require(response.status_code in (401,409))
            mutate("UPDATE access_memberships SET role='owner',revision=revision+1 WHERE account_id='pilot-owner'")
            protected.append('owner_downgrade_during_provider_releases_no_cards')
            during_encode[0]=lambda:mutate('UPDATE access_sessions SET revoked=1 WHERE digest=?',(session_digest(tokens['pilot-owner']),))
            response,_elapsed=request();_require(response.status_code==401)
            mutate('UPDATE access_sessions SET revoked=0 WHERE digest=?',(session_digest(tokens['pilot-owner']),))
            protected.append('session_revocation_during_provider_releases_no_cards')
            response,_elapsed=request();_require(response.status_code==200)
            protected.append('new_request_succeeds_after_fixture_state_restore')
    model.verify()
    inspect_index(index_path,expected_library=library,expected_cohort=cohort)
    if network:
        _require(tls_hashes == {key: hashlib.sha256(Path(config['network'][key]).read_bytes()).hexdigest()
                                for key in ('certificate', 'ca_file')})
    return {'schema':'photohouse.multilingual_pilot_measurement.v1',
        'index_sha256':hashlib.sha256(Path(index_path).read_bytes()).hexdigest(),
        'query_plan_sha256':hashlib.sha256(canonical(config['queries'])).hexdigest(),
        'cohort_sha256':manifest['cohort_sha256'],'image_count':len(records),
        'model_receipt':model.receipt(),'samples':rows,'warmup_ms':warmup,
        'protected_request_latency':_summary([r['elapsed_ms']for r in rows]),
        'denial_latency':_summary(denial_times),'protected_checks':protected,
        **counters,
        'latency_boundary':('host_loopback_protected_api_https_and_authenticated_provider_tcp_cpu'
            if network else 'in_process_protected_api_and_authenticated_provider_asgi_cpu'),
        'tcp_tls_latency_measured':network,'production_database_opened':False,
        'production_listener_started':False,'network_listener_started':network,
        'remote_device_latency_measured':False,
        'tls_receipt':({'files_sha256':tls_hashes,'hostname_verified':True,
            'trust':'per_run_ca_only','api_connection':'reused_after_admission_probes',
            'provider_connection':'new_per_encode','first_api_request_ms':denial_times[0]}
            if network else None),
        'real_account_sessions_created':False,'production_index_published':False,
        'activation_performed':False,'activation_approved':False,
        'serving_load_accepted':False,'family_relevance_accepted':False}


def execute(config_path,output,*,model_loader=SiglipModel.load):
    config,cohort=configuration(config_path)
    inspect_index(config['index'],expected_library=cohort['library_id'],expected_cohort=cohort)
    target=output_target(output);target.mkdir(mode=0o700);require_private_directory(target)
    deadline=time.monotonic()+config['max_elapsed_seconds']
    write_record(target,'started.json',{'schema':'photohouse.multilingual_pilot_started.v1',
        'query_count':len(config['queries']),'activation_performed':False})
    model=model_loader(model_directory=config['model_directory'],artifacts=config['artifacts'],
                       package_versions=config['package_versions'])
    record=measure(model,config['index'],cohort,config,target,deadline)
    _require(time.monotonic()<deadline)
    write_record(target,'measurement.json',record)
    return {'status':'isolated_multilingual_pilot_measured','image_count':record['image_count'],
        'protected_request_latency':record['protected_request_latency'],
        'protected_checks':record['protected_checks'],'activation_approved':False,
        'activation_performed':False,'measurement_sha256':hashlib.sha256(canonical(record)+b'\n').hexdigest()}


def run(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self,_message):raise PilotRefused()
    try:
        parser=Parser(description=__doc__)
        parser.add_argument('--run',action='store_true')
        parser.add_argument('--configuration',type=Path)
        parser.add_argument('--output-directory',type=Path)
        args=parser.parse_args(argv)
        if not args.run:
            _require(args.configuration is None and args.output_directory is None)
            print(json.dumps({'status':'multilingual_pilot_plan','private_files_read':False,
                'models_loaded':False,'network_listener_started':False,'activation_performed':False}))
            return 0
        _require(args.configuration is not None and args.output_directory is not None)
        previous=logging.root.manager.disable;logging.disable(logging.CRITICAL)
        try:
            with quiet_dependencies():result=execute(args.configuration,args.output_directory)
        finally:logging.disable(previous)
        print(json.dumps(result,sort_keys=True,allow_nan=False));return 0
    except Exception:
        print('{"error":"multilingual_pilot_measurement_unavailable"}',file=__import__('sys').stderr)
        return 2


if __name__=='__main__':raise SystemExit(run())
