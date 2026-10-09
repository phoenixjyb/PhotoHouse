"""Fresh-process source-package smoke; explicit extracted root, synthetic data only."""
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import socket
import threading
import uuid
from unittest.mock import patch

root=Path(sys.argv[1]).resolve(strict=True)
sys.path[:0]=[str(root/'backend'),str(root/'scripts')]
# Windows implements asyncio's internal socketpair with a short-lived loopback
# listener. Permit only that stdlib pair on its creating thread; application
# listeners and all other connects remain forbidden.
internal_pair=threading.local()
original_bind=socket.socket.bind
original_connect=socket.socket.connect
original_connect_ex=socket.socket.connect_ex
original_pair=socket.socketpair
internal_pairs=0
def pair(*args, **kwargs):
    global internal_pairs
    internal_pair.active=True; internal_pair.address=None
    try:
        result=original_pair(*args,**kwargs)
        internal_pairs+=1
        return result
    finally:
        internal_pair.active=False; internal_pair.address=None
def bind(sock, address):
    if (getattr(internal_pair,'active',False) and isinstance(address,tuple)
            and address[0] in ('127.0.0.1','::1') and address[1]==0):
        result=original_bind(sock,address)
        internal_pair.address=sock.getsockname()
        return result
    raise AssertionError('External I/O forbidden')
def connect(sock, address):
    if (getattr(internal_pair,'active',False) and isinstance(address,tuple)
            and address==getattr(internal_pair,'address',None)):
        return original_connect(sock,address)
    raise AssertionError('External I/O forbidden')
def connect_ex(sock, address):
    if (getattr(internal_pair,'active',False) and isinstance(address,tuple)
            and address==getattr(internal_pair,'address',None)):
        return original_connect_ex(sock,address)
    raise AssertionError('External I/O forbidden')
with ExitStack() as guards:
    guards.enter_context(patch('socket.socket.bind',new=bind))
    guards.enter_context(patch('socket.socket.connect',new=connect))
    guards.enter_context(patch('socket.socket.connect_ex',new=connect_ex))
    if sys.platform=='win32':
        guards.enter_context(patch('socket.socketpair',new=pair))
    for target in ('subprocess.Popen','os.system'):
        guards.enter_context(patch(target,side_effect=AssertionError('External I/O forbidden')))
    with socket.socket() as probe:
        for operation,address in ((probe.bind,('127.0.0.1',0)),
                                  (probe.connect,('192.0.2.1',443)),
                                  (probe.connect_ex,('192.0.2.1',443))):
            try: operation(address)
            except AssertionError: pass
            else: raise AssertionError('Network guard failed')
    from fastapi.testclient import TestClient
    import app
    from app.main import create_app
    from app.access.runtime import RuntimeConfiguration, REQUIRED_REVISION
    import provision_access
    import staging_app
    import home_memory_envelope
    import apply_memory_collaboration_schema
    import apply_memory_sources_schema
    import apply_memory_editorial_schema
    import serve_windows_tts
    import app.access.windows_tts as windows_tts
    import app.access.memory_book_planning as memory_book_planning
    import app.access.prepared_video as prepared_video
    import prepare_access_database
    from app.access import (captions, duplicates, promotion, task_recovery,
                            upload, upload_schema, upload_transport)
    for module in (app,provision_access,staging_app,prepare_access_database,prepared_video,
                   home_memory_envelope, memory_book_planning, apply_memory_collaboration_schema,
                   apply_memory_sources_schema, apply_memory_editorial_schema,
                   serve_windows_tts, windows_tts,
                   captions, duplicates, promotion, task_recovery,
                   upload, upload_schema, upload_transport):
        assert Path(module.__file__).resolve().is_relative_to(root)
    speech_plan=io.StringIO()
    with redirect_stdout(speech_plan):
        assert serve_windows_tts.main([])==0
    assert json.loads(speech_plan.getvalue())=={'mode':'plan','bind':'127.0.0.1',
        'port':7350,'path':'/speech','starts_listener':False,'reads_token':False,
        'enumerates_voices':False}
    with tempfile.TemporaryDirectory(prefix='photohouse-package-db-') as directory:
        data=Path(directory).resolve(); database=data/'synthetic.sqlite'
        with redirect_stdout(io.StringIO()):
            assert prepare_access_database.main(['initialize','--out',str(database)])==0
            assert prepare_access_database.main(['backup','--database',str(database),
                '--out',str(data/'backup.sqlite')])==0
            assert prepare_access_database.main(['rehearse-migration','--database',str(database)])==0
        preparation_output=io.StringIO()
        with redirect_stdout(preparation_output):
            assert prepare_access_database.main(['backup','--database',str(database),
                '--out',str(data/'candidate-backup.sqlite')])==0
        reviewed=json.loads(preparation_output.getvalue())['source_snapshot_digest']
        with redirect_stdout(io.StringIO()):
            assert prepare_access_database.main(['migrate-candidate','--database',str(database),
                '--backup',str(data/'candidate-backup.sqlite'),'--out',str(data/'candidate.sqlite'),
                '--reviewed-snapshot-digest',reviewed,'--authority-reference','synthetic-authority',
                '--quiescence-reference','synthetic-stopped-workers'])==0
        with TestClient(create_app(),base_url='https://photohouse.test') as client:
            assert client.get('/auth/session').status_code==503
        runtime=RuntimeConfiguration(database,'https://photohouse.test',(data/'originals',),data/'derived')
        with TestClient(runtime.build_app(),base_url='https://photohouse.test') as client:
            assert client.get('/auth/session').status_code==401
            assert client.get('/assets?library=synthetic-family').status_code==401
            assert client.get('/ui').status_code==200
            assert client.get('/ui/app.js').status_code==200
            assert client.get('/ui/styles.css').status_code==200
            assert client.get('/search').status_code==403
        request=data/'owner-request.json'; plan=data/'owner-plan.json'
        request.write_text(json.dumps({'phone_login':'+12025550123','library_id':'synthetic-family'}))
        plan_output=io.StringIO()
        with redirect_stdout(plan_output):
            assert provision_access.main(['plan-owner','--database',str(database),
                '--request',str(request),'--out',str(plan)])==0
        plan_digest=json.loads(plan_output.getvalue())['plan_digest']
        def operator(command, *args):
            output=io.StringIO()
            with redirect_stdout(output):
                assert provision_access.main([command,*map(str,args)])==0
            return json.loads(output.getvalue())
        owner_args=['--database',database,'--plan',plan,'--backup',data/'backup.sqlite',
            '--reviewed-plan-digest',plan_digest,'--authority-reference','synthetic-authority',
            '--restore-reference','synthetic-restore']
        operator('validate','--database',database,'--plan',plan)
        reviewed=operator('review',*owner_args)
        with patch('getpass.getpass',return_value='synthetic original owner password'):
            applied=operator('apply',*owner_args,'--review-digest',reviewed['review_digest'])
        preparation_output=io.StringIO()
        with redirect_stdout(preparation_output):
            assert prepare_access_database.main(['backup','--database',str(database),
                '--out',str(data/'owned-backup.sqlite')])==0
        reviewed_snapshot=json.loads(preparation_output.getvalue())['source_snapshot_digest']
        recovered=data/'recovered.sqlite'
        with redirect_stdout(io.StringIO()):
            assert prepare_access_database.main(['migrate-candidate','--database',str(database),
                '--backup',str(data/'owned-backup.sqlite'),'--out',str(recovered),
                '--reviewed-snapshot-digest',reviewed_snapshot,'--authority-reference','synthetic-authority',
                '--quiescence-reference','synthetic-stopped-workers'])==0
            assert prepare_access_database.main(['backup','--database',str(recovered),
                '--out',str(data/'recovered-backup.sqlite')])==0
        request=data/'recovery-request.json';plan=data/'recovery-plan.json'
        request.write_text(json.dumps({'operator_account_id':applied['actor_account_id'],
            'library_id':'synthetic-family','quiescence_reference':'synthetic-stopped-workers',
            'reconciliation_reference':'synthetic-owner-history-review'}))
        planned=operator('plan-recovery','--database',recovered,'--request',request,'--out',plan)
        operator('validate-recovery','--database',recovered,'--plan',plan)
        recovery_args=['--database',recovered,'--plan',plan,'--backup',data/'recovered-backup.sqlite',
            '--reviewed-plan-digest',planned['plan_digest'],'--authority-reference','synthetic-authority',
            '--restore-reference','synthetic-restore']
        reviewed=operator('review-recovery',*recovery_args)
        with patch('getpass.getpass',return_value='synthetic replacement owner password'):
            operator('apply-recovery',*recovery_args,'--review-digest',reviewed['review_digest'])
        assert operator('receipt','--database',recovered,'--plan-id',planned['plan_id'],
            '--reviewed-plan-digest',planned['plan_digest'])['receipt_found']
        from app.access.runtime import ExistingDatabase
        from app.access import management_import
        assert Path(management_import.__file__).resolve().is_relative_to(root)
        with ExistingDatabase(recovered)() as connection:
            connection.execute("INSERT INTO persons(id,display_name,face_count) VALUES (91,'Synthetic orphan',0)")
            connection.commit()
        with redirect_stdout(io.StringIO()):
            assert prepare_access_database.main(['backup','--database',str(recovered),
                '--out',str(data/'management-backup.sqlite')])==0
        request=data/'management-request.json';plan=data/'management-plan.json'
        request.write_text(json.dumps({'operator_account_id':applied['actor_account_id'],
            'library_id':'synthetic-family','person_ids':[91],'album_ids':[],
            'include_orphan_people':True,'include_empty_albums':False,
            'quiescence_reference':'synthetic-stopped-workers'}))
        planned=operator('plan-management','--database',recovered,'--request',request,'--out',plan)
        operator('validate','--database',recovered,'--plan',plan)
        management_args=['--database',recovered,'--plan',plan,'--backup',data/'management-backup.sqlite',
            '--reviewed-plan-digest',planned['plan_digest'],'--authority-reference','synthetic-authority',
            '--restore-reference','synthetic-restore']
        reviewed=operator('review',*management_args)
        operator('apply',*management_args,'--review-digest',reviewed['review_digest'],'--all-writers-stopped')
        assert operator('receipt','--database',recovered,'--plan-id',planned['plan_id'],
            '--reviewed-plan-digest',planned['plan_digest'])['receipt_found']
        from app.access import ownership_repair
        assert Path(ownership_repair.__file__).resolve().is_relative_to(root)
        with ExistingDatabase(recovered)() as connection:
            connection.execute("INSERT INTO persons(id,display_name,face_count) VALUES (92,'Synthetic target',2)")
            connection.executemany("INSERT INTO assets(id,path,hash_sha256,status) VALUES (?,?,?,?)",[
                (93,'synthetic/visible.jpg','synthetic-hash-93','active'),
                (94,'synthetic/suppressed.jpg','synthetic-hash-94','suppressed')])
            connection.execute("INSERT INTO access_asset_libraries VALUES (93,'synthetic-family')")
            connection.executemany("INSERT INTO face_detections(id,asset_id,bbox_x,bbox_y,bbox_w,bbox_h,person_id)"
                " VALUES (?,?,0,0,1,1,92)",[(931,93),(941,94)])
            connection.commit()
        with redirect_stdout(io.StringIO()):
            assert prepare_access_database.main(['backup','--database',str(recovered),
                '--out',str(data/'repair-backup.sqlite')])==0
        request=data/'repair-request.json';plan=data/'repair-plan.json'
        request.write_text(json.dumps({'library_id':'synthetic-family',
            'operator_account_id':applied['actor_account_id'],'person_id':92,'asset_ids':[94],
            'quiescence_reference':'synthetic-stopped-workers',
            'provenance_reference':'synthetic-ownership-review'}))
        planned=operator('plan-person-repair','--database',recovered,'--request',request,'--out',plan)
        operator('validate','--database',recovered,'--plan',plan)
        repair_args=['--database',recovered,'--plan',plan,'--backup',data/'repair-backup.sqlite',
            '--reviewed-plan-digest',planned['plan_digest'],'--authority-reference','synthetic-authority',
            '--restore-reference','synthetic-restore']
        reviewed=operator('review',*repair_args)
        operator('apply',*repair_args,'--review-digest',reviewed['review_digest'],'--all-writers-stopped')
        assert operator('receipt','--database',recovered,'--plan-id',planned['plan_id'],
            '--reviewed-plan-digest',planned['plan_digest'])['receipt_found']
        with ExistingDatabase(recovered,read_only=True)() as connection:
            assert connection.execute("SELECT library_id FROM access_person_libraries WHERE person_id=92").fetchall()==[('synthetic-family',)]
            assert connection.execute("SELECT status FROM assets WHERE id=94").fetchall()==[('suppressed',)]
        from app.access import memory_stories, memory_schema
        for module in (memory_stories, memory_schema):
            assert Path(module.__file__).resolve().is_relative_to(root)
        # The recovered database intentionally remains quarantined. Exercise
        # saved stories in the separate, still-active synthetic owner database.
        with ExistingDatabase(database)() as connection:
            connection.execute("""INSERT INTO assets(id,path,hash_sha256,status,mime,width,height)
                VALUES (93,'synthetic/story.jpg','synthetic-story-hash','active','image/jpeg',640,480)""")
            connection.execute("INSERT INTO access_asset_libraries VALUES (93,'synthetic-family')")
            connection.commit()
        story_runtime=RuntimeConfiguration(database,'https://photohouse.test',
            (data/'originals',),data/'derived')
        with TestClient(story_runtime.build_app(),base_url='https://photohouse.test',
                        client=('127.0.0.1',50123)) as client:
            login=client.post('/auth/login',json={'phone':'+12025550123',
                'password':'synthetic original owner password','transport':'native'})
            assert login.status_code==200, login.text
            headers={'Authorization':'Bearer '+login.json()['access_token']}
            preview=client.post('/story-workspace/preview?library=synthetic-family',headers=headers,
                json={'asset_ids':'93','title':'一起走过的日子','theme':'everyday','language':'zh'})
            assert preview.status_code==200, preview.text
            draft=preview.json()
            draft['chapters'][0]['narration']='这是家人写下的一段回忆。'
            body={'title':draft['title'],'theme':draft['theme'],'language':'zh','asset_ids':'93',
                'chapters':json.dumps(draft['chapters']), 'selection_revision':draft['selection_revision'],
                'revision':'0','mutation_id':str(uuid.uuid4())}
            saved=client.post('/memory-stories?library=synthetic-family',headers=headers,json=body)
            assert saved.status_code==200, saved.text
            ident=saved.json()['id']
            retry=client.post('/memory-stories?library=synthetic-family',headers=headers,json=body)
            assert retry.status_code==200 and retry.json()['id']==ident
            shelf=client.get('/memory-stories?library=synthetic-family',headers=headers)
            assert shelf.status_code==200 and shelf.json()['items'][0]['id']==ident
            reopened=client.get('/memory-stories/'+ident+'?library=synthetic-family',headers=headers)
            assert reopened.status_code==200, reopened.text
            assert reopened.json()['chapters'][0]['narration']=='这是家人写下的一段回忆。'
            assert client.get('/ui/story-workspace.js').status_code==200
print(json.dumps({'package_smoke':'pass','synthetic_migration_revision':REQUIRED_REVISION,
    'asgi_checks':7,'operator_commands':19,'database_preparation_commands':9,
    'saved_story_checks':7,'local_tts_plan_checks':1,
    'application_listeners_opened':False,'internal_loopback_socketpairs':internal_pairs,
    'live_data_accessed':False}))
