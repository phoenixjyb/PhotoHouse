"""Synthetic browser-to-ASGI JSON-lines bridge over stdin/stdout; opens no port.

Only run from the browser security test. All storage lives in temporary fixtures.
"""
import base64
import hashlib
import json
import shutil
from pathlib import Path
import sys

from test_library_reads import LibraryReadTests
from app.access.runtime import RuntimeConfiguration
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]

fixture = LibraryReadTests()
LibraryReadTests.setUpClass()
head_503 = False
index_serial = 0
story_source_detail_fixture = False


def build_client(*, source_detail=False):
    """Build the protected app with an index produced by the real offline tool.

    The artifact is derived from the *current* fixture database by the producer's own
    functions, called in-process because this harness forbids subprocess and network I/O.
    That keeps the browser checkpoint on the producer -> artifact -> loader -> runtime
    chain instead of a hand-written index. A fresh file is written each call because the
    producer refuses to overwrite, and the artifact is a whole-library snapshot: any later
    mutation makes it stale, so a checkpoint running after one must refresh first.
    """
    global index_serial
    from contextlib import closing
    from dataclasses import asdict
    import time
    sys.path.insert(0, str(ROOT / 'scripts'))
    import prepare_access_discovery_index as producer
    index_serial += 1
    out = root.resolve() / f'discovery-index-{index_serial}.json'
    start = time.monotonic()
    with closing(producer.open_read_only(fixture.path.resolve(), start)) as db:
        index, _catalog = producer.derive(db, producer.library('family-a'), producer.revision('1'))
    # This browser fixture opts into one explicit reviewed place so the protected
    # UI exercises the real locations facet/search contract. The synthetic source
    # has no GPS semantics here: regions are reviewed IDs only.
    from dataclasses import replace
    from app.access.discovery_provider import NamedPlace
    index=replace(index, places=(NamedPlace('family-a','601','Example region / 示例地区',('测试地区','Exampleland')),),
                 regions=(('101','601'),('102','601')),
                 enabled=tuple((*index.enabled,'locations')))
    producer.write_new(out, json.dumps(asdict(index), sort_keys=True, ensure_ascii=True,
                                       separators=(',', ':'), allow_nan=False).encode())
    options={}
    if source_detail:
        # Explicit test-only opt-in, used only by the focused saved-story source
        # journey. This isolated journal is private fixture state, never a
        # production or default-browser configuration.
        from app.access.original_deletions import OriginalDeletionJournal
        journal=root.resolve()/'private-original-deletions.sqlite'
        namespace='d0000000-0000-4000-8000-000000000099'
        if not journal.exists():
            selected=OriginalDeletionJournal.initialize(journal,namespace)
            with fixture.connection() as db:selected.bind(db)
        options.update(memory_collaboration_enabled=True,memory_originals_enabled=True,
            memory_generation_enabled=True,original_deletion_journal_path=journal,
            original_deletion_namespace=namespace)
    return TestClient(RuntimeConfiguration(fixture.path.resolve(), 'https://photohouse.test',
        (originals,), derived, discovery_indexes=(out,),**options).build_app(clock=lambda:fixture.now),
        base_url='https://photohouse.test', client=('192.0.2.20',23456))


try:
    fixture.setUp()
    # Tiny generated JPEG fixtures, never real family media. Pillow is a test-only
    # dependency; the application itself does not import it on this path.
    from PIL import Image, ImageDraw
    root = fixture.path.parent
    originals, derived = root / 'originals', root / 'derived'
    originals.mkdir(); (derived / 'thumbnails/256').mkdir(parents=True)
    for asset_id,color in ((101,'#b6c7b0'),(102,'#d2ad89'),(201,'#8aa9c4')):
        image=Image.new('RGB',(400,300),color)
        draw=ImageDraw.Draw(image);draw.rectangle((30,30,370,270),outline='#fff9ed',width=3)
        draw.text((135,145),f'SYNTHETIC {asset_id}',fill='#302c28')
        image.save(derived / f'thumbnails/256/{asset_id}.jpg')
        image.save(originals / f'{asset_id}.jpg')
        fixture.mutate('UPDATE assets SET path=? WHERE id=?',(str(originals / f'{asset_id}.jpg'),asset_id))
    (derived/'faces/256').mkdir(parents=True)
    with fixture.connection() as db:
        for person,name in [(1,'Alice'),(2,'Shared person'),*[(i,f'Person {i:02}') for i in range(10,37)]]:
            db.execute('INSERT INTO persons(id,display_name,face_count) VALUES(?,?,1)',(person,name))
            db.execute('INSERT INTO face_detections(id,asset_id,person_id,bbox_x,bbox_y,bbox_w,bbox_h) VALUES(?,101,?,0,0,1,1)',(person,person))
            Image.new('RGB',(100,100),'#b6c7b0').save(derived/f'faces/256/{person}.jpg')
        db.execute('INSERT INTO face_detections(id,asset_id,person_id,bbox_x,bbox_y,bbox_w,bbox_h) VALUES(99,201,2,0,0,1,1)')
        db.execute('INSERT INTO face_detections(id,asset_id,bbox_x,bbox_y,bbox_w,bbox_h) VALUES(200,102,0,0,1,1)')
        Image.new('RGB',(100,100),'#d2ad89').save(derived/'faces/256/200.jpg')
        # Read-only tag catalog fixture. Only tags carrying a *visible* family-a photo may ever
        # reach the member: 201 belongs to family-b and 103 is deleted, so those two are the
        # negative controls the browser checkpoint asserts are absent.
        for tag_id,name in ((1,'beach'),(2,'cake'),(3,'foreign-only'),(4,'deleted-only')):
            db.execute('INSERT INTO tags(id,name,type) VALUES(?,?,?)',(tag_id,name,'caption-auto'))
        for tag_id,asset in ((1,101),(1,102),(2,101),(3,201),(4,103)):
            db.execute('INSERT INTO asset_tags(asset_id,tag_id,source) VALUES(?,?,?)',(asset,tag_id,'cap'))
        # Exact-duplicate fixture. 101 and 102 are visible in family-a and active; 103 is
        # deleted and 201 belongs to family-b, so those two are the negative controls the
        # duplicate checkpoint asserts never appear.
        db.execute("UPDATE assets SET hash_sha256='dup-shared' WHERE id IN (101,102,103,201)")
        db.commit()
    fixture.client = build_client()
    fixture.addCleanup(fixture.client.close)
    print(json.dumps({'ready':True}),flush=True)
    for line in sys.stdin:
        message=json.loads(line)
        if message.get('command')=='quit':
            break
        if message.get('command')=='mutate':
            # Strict synthetic scenarios; no caller-supplied SQL or file paths.
            scenario=message['scenario']
            if scenario in {'enable-story-title-fixture', 'disable-story-title-fixture'}:
                class SyntheticTitleAdapter:
                    def suggest(self, bundle):
                        return {'version': 1, 'selection_revision': bundle['selection_revision'],
                            'titles': [{'text': '一起走过的午後', 'source_ids': [bundle['sources'][0]['id']]},
                                       {'text': '<b>家人的片段</b>', 'source_ids': [bundle['sources'][-1]['id']]}],
                            'needs_review': True}
                fixture.client.app.state.story_title_suggester = (SyntheticTitleAdapter()
                    if scenario == 'enable-story-title-fixture' else None)
                print(json.dumps({'id':message['id'],'ok':True,'fixture_only':True}),flush=True);continue
            if scenario in {'story-author-chosen-name', 'story-author-renamed', 'story-author-no-name'}:
                name = {'story-author-chosen-name': '爸爸 & Dad',
                        'story-author-renamed': 'New display name',
                        'story-author-no-name': None}[scenario]
                fixture.mutate('UPDATE access_accounts SET display_name=? WHERE phone_login=?',
                               (name, '+12025550100'))
                print(json.dumps({'id':message['id'],'ok':True,'fixture_only':True}),flush=True);continue
            if scenario=='enable-story-source-detail-fixture':
                fixture.client.close()
                fixture.client=build_client(source_detail=True)
                story_source_detail_fixture=True
                print(json.dumps({'id':message['id'],'ok':True,'fixture_only':True}),flush=True);continue
            if scenario=='story-ref-contributions':
                if not story_source_detail_fixture:raise ValueError('Story source detail fixture is not enabled')
                import re, uuid
                story_id=message.get('story_id','');chapter_id=message.get('chapter_id','')
                if not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',story_id) or chapter_id not in {f'chapter-{i}' for i in range(1,7)}:
                    raise ValueError('Invalid synthetic story reference seed')
                ident='a0000000-0000-4000-8000-000000000099'
                audio_ident='a0000000-0000-4000-8000-000000000098'
                text='合成家人原话：湖边散步时，大家一起唱了歌。'
                transcript='合成录音里的家人原话。';audio=b'SYNTHETIC-WAV-NOT-FETCHED'
                with fixture.connection() as db:
                    story=db.execute("SELECT content,revision FROM access_memory_stories WHERE id=? AND library_id='family-a'",(story_id,)).fetchone()
                    if story is None or chapter_id not in {chapter['id'] for chapter in json.loads(story[0])['chapters']}:
                        raise ValueError('Synthetic story or chapter not found')
                    actor=db.execute("SELECT bootstrap_operator FROM access_libraries WHERE id='family-a'").fetchone()[0]
                    db.execute('''INSERT INTO access_memory_contributions
                        (id,story_id,library_id,author_id,kind,original_text,original_audio,language,byline,
                         sha256,duration_ms,local_processing_consent,chapter_id,base_story_revision,state,
                         mutation_id,request_digest,created_at,reviewed_by_id,reviewed_at)
                        VALUES(?,?,'family-a',?,'text',?,NULL,'zh','测试家人',?,NULL,1,?,?,
                         'accepted',?,?,?, ?,?)''',
                        (ident,story_id,actor,text,hashlib.sha256(text.encode('utf-8')).hexdigest(),chapter_id,
                         story[1],str(uuid.uuid4()),hashlib.sha256((story_id+chapter_id).encode()).hexdigest(),
                         fixture.now,actor,fixture.now))
                    db.execute('''INSERT INTO access_memory_contributions
                        (id,story_id,library_id,author_id,kind,original_text,original_audio,language,byline,
                         sha256,duration_ms,local_processing_consent,chapter_id,base_story_revision,state,
                         mutation_id,request_digest,created_at,reviewed_by_id,reviewed_at)
                        VALUES(?,?,'family-a',?,'audio',NULL,?,'zh','录音家人',?,1000,1,?,?,
                         'accepted',?,?,?, ?,?)''',
                        (audio_ident,story_id,actor,audio,hashlib.sha256(audio).hexdigest(),chapter_id,
                         story[1],str(uuid.uuid4()),hashlib.sha256((story_id+chapter_id+'audio').encode()).hexdigest(),
                         fixture.now,actor,fixture.now))
                    db.execute('''INSERT INTO access_memory_contribution_derivations
                        (contribution_id,revision,state,transcript,polished_text,tags,provider,model,error_code,
                         created_at,updated_at) VALUES(?,1,'ready',?,NULL,'[]','synthetic-local','fixture',NULL,?,?)''',
                        (audio_ident,transcript,fixture.now,fixture.now))
                    db.commit()
                print(json.dumps({'id':message['id'],'ok':True,'contribution_id':ident,'audio_contribution_id':audio_ident}),flush=True);continue
            if scenario=='library-organization':
                from app.access.library_organization import create_presets
                from app.access.service import AccessService
                with fixture.connection() as db:
                    access=AccessService(db,clock=lambda:fixture.now)
                    with access._transaction(write=True):
                        actor=db.execute("SELECT bootstrap_operator FROM access_libraries WHERE id='family-a'").fetchone()[0]
                        create_presets(access,actor)
                        for asset_id,mime in ((9501,'image/jpeg'),(9502,'video/mp4')):
                            db.execute("INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,taken_at) VALUES (?,?,?,'active',?,400,300,'2050-01-01')",(asset_id,str(originals/f'{asset_id}.jpg'),str(asset_id),mime))
                            db.execute("INSERT INTO access_asset_libraries VALUES (?,'family-a')",(asset_id,))
                            shutil.copyfile(originals/'101.jpg',originals/f'{asset_id}.jpg')
                            shutil.copyfile(derived/'thumbnails/256/101.jpg',derived/f'thumbnails/256/{asset_id}.jpg')
            elif scenario=='family-default':
                with fixture.connection() as db:
                    actor=db.execute("SELECT bootstrap_operator FROM access_libraries WHERE id='family-a'").fetchone()[0]
                    db.execute("INSERT INTO access_libraries(id,bootstrap_operator) VALUES ('family',?)",(actor,))
                    db.execute("INSERT INTO access_memberships(account_id,library_id,status,role,revision,approved_by) VALUES (?,'family','approved','owner',1,?)",(actor,actor))
                    db.execute("INSERT INTO assets(id,path,hash_sha256,status,mime,width,height) VALUES (9601,?,'synthetic-family-default','active','image/jpeg',400,300)",(str(originals/'9601.jpg'),))
                    db.execute("INSERT INTO access_asset_libraries VALUES (9601,'family')")
                    db.commit()
                shutil.copyfile(originals/'101.jpg',originals/'9601.jpg')
                shutil.copyfile(derived/'thumbnails/256/101.jpg',derived/'thumbnails/256/9601.jpg')
            elif scenario=='family-default-unavailable':
                fixture.mutate("UPDATE access_libraries SET state='closed' WHERE id='family'")
            elif scenario=='family-default-no-access':
                fixture.mutate("UPDATE access_memberships SET status='revoked',revision=revision+1 WHERE account_id=(SELECT bootstrap_operator FROM access_libraries WHERE id='family-a')")
            elif scenario=='person-name-html':
                fixture.mutate("UPDATE persons SET display_name=?,updated_at='changed-by-test' WHERE id=1",('<img src=x onerror="window.syntheticXSS=true">',))
            elif scenario=='face-assignment-changed':
                fixture.mutate("UPDATE face_detections SET label_source='dnn',label_score=0.2 WHERE id=200")
            elif scenario=='album-title-changed':
                fixture.mutate("UPDATE albums SET title='Changed elsewhere' WHERE id IN (SELECT album_id FROM access_album_libraries)")
                fixture.mutate('UPDATE access_album_libraries SET revision=revision+1')
            elif scenario=='china-login':
                fixture.mutate("UPDATE access_accounts SET phone_login='+8610000000000' WHERE id=?", (fixture.member_id,))
            elif scenario=='international-login':
                fixture.mutate("UPDATE access_accounts SET phone_login='+12025550102' WHERE id=?", (fixture.member_id,))
            elif scenario=='revoke-member':
                fixture.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",(fixture.member_id,))
            elif scenario=='restore-member':
                fixture.mutate("UPDATE access_memberships SET status='approved' WHERE account_id=?",(fixture.member_id,))
            elif scenario=='change-joined-membership':
                fixture.mutate("UPDATE access_memberships SET revision=revision+1 WHERE account_id IN (SELECT id FROM access_accounts WHERE phone_login='+12025550103')")
            elif scenario=='expire-sessions':
                fixture.mutate('UPDATE access_sessions SET expires_at=0')
            elif scenario=='caption-html':
                fixture.mutate("UPDATE captions SET text=? WHERE id=101",('<img src=x onerror="window.syntheticXSS=true">',))
            elif scenario=='member-second-library':
                from app.access.service import AccessService
                from test_access_foundation import MEMBER
                with fixture.connection() as db:
                    service=AccessService(db,clock=lambda:fixture.now)
                    code=service.invite(fixture.other_token,'family-b',MEMBER)
                    service.accept_invitation(fixture.member_token,code)
            elif scenario=='prepare-1024-thumbnail':
                from PIL import Image
                (derived/'thumbnails/1024').mkdir(parents=True,exist_ok=True)
                image=Image.open(derived/'thumbnails/256/101.jpg')
                image.resize((1024,768)).save(derived/'thumbnails/1024/101.jpg')
            elif scenario=='missing-caption':
                # Add the same active, undescribed photo used by the caption-write
                # contract so the browser can exercise the real positive form path.
                from PIL import Image
                with fixture.connection() as db:
                    db.execute('''INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,taken_at)
                        VALUES(104,'private-synthetic/104.jpg','private-hash-104','active','image/jpeg',
                               640,480,'2026-01-04')''')
                    db.execute("INSERT INTO access_asset_libraries VALUES (104,'family-a')")
                    db.commit()
                with Image.open(derived/'thumbnails/256/101.jpg') as image:
                    image.save(derived/'thumbnails/256/104.jpg')
            elif scenario=='prepared-video-unavailable':
                # Synthetic video row for the WebUI contract: the default browser app has
                # no prepared provider configured, so playback must remain visibly unavailable
                # and must never fall back to the original path.
                with fixture.connection() as db:
                    db.execute('''INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,taken_at)
                        VALUES(105,'private-synthetic/105.mp4','private-video-hash-105','active','video/mp4',640,360,'2027-01-01')''')
                    db.execute("INSERT INTO access_asset_libraries VALUES (105,'family-a')")
                    db.commit()
                (originals/'105.mp4').write_bytes(b'ftyp synthetic protected-video fixture')
                fixture.mutate('UPDATE assets SET path=? WHERE id=105',(str(originals/'105.mp4'),))
                Image.open(derived/'thumbnails/256/101.jpg').save(derived/'thumbnails/256/105.jpg')
            elif scenario=='prepared-video-ready':
                from app.access.media import MediaRuntime
                from app.access.prepared_video import PreparedVideos
                raw=Path(__file__).resolve().parent/'fixtures'/'home-video.mp4'
                source=originals/'105.mp4';shutil.copyfile(raw,source)
                fixture.mutate('UPDATE assets SET path=?,hash_sha256=? WHERE id=105',(str(source),hashlib.sha256(source.read_bytes()).hexdigest()))
                prepared_root=(derived.parent/'prepared-videos-root').resolve();prepared_root.mkdir(parents=True,exist_ok=True)
                folder=(prepared_root/'asset-105').resolve();folder.mkdir(parents=True,exist_ok=True)
                output=folder/'video.mp4';shutil.copyfile(raw,output)
                digest=hashlib.sha256(output.read_bytes()).hexdigest();chunks=[digest]
                chunk_file=folder/'video.chunks.json';chunk_raw=json.dumps(chunks,separators=(',',':')).encode();chunk_file.write_bytes(chunk_raw)
                info=source.stat();video_raw=output.read_bytes()
                metadata={'state':'ready','mime':'video/mp4','video_codec':'h264','audio_codec':'aac','width':320,'height':180,'duration_ms':1000,'bytes':len(video_raw),'sha256':digest,'chunks_sha256':hashlib.sha256(chunk_raw).hexdigest()}
                index_value={'version':1,'assets':[{'id':105,'source_identity':[info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns],'directory':folder.name,'video':metadata}]}
                index_raw=json.dumps(index_value,separators=(',',':')).encode();index=(derived.parent/'prepared-video-index.json').resolve();index.write_bytes(index_raw)
                fixture.client.close();fixture.client=build_client()
                provider=PreparedVideos(index,hashlib.sha256(index_raw).hexdigest(),prepared_root)
                fixture.client.app.state.media_runtime=MediaRuntime((originals,),derived,prepared_videos=provider)
            elif scenario=='memory-concurrent-edit':
                fixture.mutate("UPDATE access_memory_stories SET revision=revision+1 WHERE library_id='family-a'")
            elif scenario=='memory-concurrent-reorder':
                with fixture.connection() as db:
                    ident,raw=db.execute("SELECT id,content FROM access_memory_stories WHERE library_id='family-a'").fetchone()
                    content=json.loads(raw)
                    content['asset_ids'][:2]=reversed(content['asset_ids'][:2])
                    content['chapters'][0]['asset_ids'][:2]=reversed(content['chapters'][0]['asset_ids'][:2])
                    db.execute('UPDATE access_memory_stories SET content=?,revision=revision+1 WHERE id=?',
                               (json.dumps(content),ident))
                    db.commit()
            elif scenario=='related-day-seed':
                fixture.mutate("UPDATE assets SET taken_at='2025-06-01T23:30:00+08:00' WHERE id=101")
                fixture.mutate("UPDATE assets SET taken_at=NULL,path='private-synthetic/微信图片_20250601.jpg' WHERE id=102")
                fixture.mutate("UPDATE assets SET mime='video/mp4',duration_sec=12 WHERE id=1129")
            elif scenario=='many-assets':
                # Grows family-a past one gallery page at page_size 24. taken_at keeps
                # 102/101 ahead of the new rows, so page 1 order is unchanged.
                (derived/'thumbnails/256').mkdir(parents=True,exist_ok=True)
                with fixture.connection() as db:
                    for asset_id in range(1101,1130):
                        db.execute('''INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,
                            taken_at,gps_lat,gps_lon,caption_error_last) VALUES (?,?,?,?,?,640,480,?,1,2,?)''',
                            (asset_id,f'private-synthetic/{asset_id}.jpg',f'private-hash-{asset_id}',
                             'active','image/jpeg','2025-06-01','private-provider-error'))
                        db.execute('INSERT INTO access_asset_libraries VALUES (?,?)',(asset_id,'family-a'))
                    db.commit()
                source=derived/'thumbnails/256/101.jpg'
                for asset_id in range(1101,1130):
                    Image.open(source).save(derived/f'thumbnails/256/{asset_id}.jpg')
            elif scenario=='thumbnail-head-503':
                head_503=True
            elif scenario=='unnamed-cluster':
                # An unnamed cluster is a real person row with no saved name, so the
                # owner cannot find it by searching for a name. Both faces land on
                # asset 102, whose face list no checkpoint counts, so this stays
                # side-effect free for the asset-101 panel checks. Face 301 is the
                # library's own unassigned worklist entry; face 200 is already used
                # by the per-photo assignment checkpoints and is left alone.
                with fixture.connection() as db:
                    db.execute("INSERT INTO persons(id,display_name,face_count) VALUES(50,'',1)")
                    db.execute('''INSERT INTO face_detections(id,asset_id,person_id,bbox_x,bbox_y,bbox_w,bbox_h)
                        VALUES(50,102,50,0,0,1,1),(301,102,NULL,0,0,1,1)''')
                    db.commit()
                Image.new('RGB',(100,100),'#c9b8a8').save(derived/'faces/256/50.jpg')
                Image.new('RGB',(100,100),'#a8b8c9').save(derived/'faces/256/301.jpg')
            elif scenario=='refresh-discovery-index':
                # Re-derive the reviewed index from the mutated database and rebuild the
                # app. The artifact is a whole-library snapshot loaded once at startup, so
                # any mutation makes it stale and the service answers 409 until it is
                # re-derived and reloaded. This keeps the discovery checkpoint independent
                # of whatever earlier scenarios changed.
                fixture.client.close()
                fixture.client = build_client()
            else:
                raise ValueError('Unknown synthetic scenario')
            print(json.dumps({'id':message['id'],'ok':True}),flush=True);continue
        fixture.client.cookies.clear()
        if (head_503 and message['method']=='HEAD' and
                message['path'].startswith('/assets/101/thumbnail?') and
                'size=1024' in message['path']):
            head_503=False
            print(json.dumps({'id':message['id'],'status':503,'headers':{},'body':''}),flush=True)
            continue
        response=fixture.client.request(message['method'],message['path'],
            headers=message['headers'],content=base64.b64decode(message.get('body','')),
            follow_redirects=False)
        fixture.client.cookies.clear()
        print(json.dumps({'id':message['id'],'status':response.status_code,
            'headers':dict(response.headers),'body':base64.b64encode(response.content).decode()}),flush=True)
finally:
    fixture.doCleanups()
    LibraryReadTests.tearDownClass()
