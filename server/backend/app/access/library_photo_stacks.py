"""Indexed, reversible gallery presentation and account-private choices.

Requests never build an index or open media/models. The offline refresh helper
uses optimistic source binding and atomic publication; live execution is a
separate operation. Stale groups dissolve to ordinary authorized assets.
"""
from contextlib import contextmanager
import sqlite3
import hashlib
import json
import re
import time
import uuid

from .library import FIELDS, HINT_FIELDS, SOURCE, GALLERY_ORDER, _asset
from .photo_stack_schema import available
from .service import Conflict
from .transport import TransportError
from .photo_stack_index import check_stopped

PAGE_SIZE = 12
MAX_MEMBERS = 24
MAX_CHOICES = 4096
MAX_ASSETS = 100000
FIELDS_WRITE = {'index_revision','revision','group_id','cover_asset_id','separate_asset_id','reset'}
ID = re.compile(r'[1-9][0-9]{0,18}\Z', re.ASCII)
DIGEST = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)
_INPUT = FIELDS + ''',a.perceptual_hash,
 (SELECT u.account_id FROM access_uploads u WHERE u.asset_id=a.id LIMIT 1),
 (SELECT u.batch FROM access_uploads u WHERE u.asset_id=a.id LIMIT 1)'''
# live carries current library authorization, active state and grouping inputs.
_LIVE = HINT_FIELDS + ''',a.perceptual_hash,
 (SELECT u.account_id FROM access_uploads u WHERE u.asset_id=a.id LIMIT 1),
 (SELECT u.batch FROM access_uploads u WHERE u.asset_id=a.id LIMIT 1),
 COALESCE(a.taken_at,(SELECT datetime(u.created_at,'unixepoch') FROM access_uploads u WHERE u.asset_id=a.id))'''
CTE = '''WITH live(id,mime,width,height,duration_sec,taken_at,path,received,phash,account,batch,ordering) AS (
 SELECT __LIVE__ __SOURCE__),
 valid_groups AS (
 SELECT g.* FROM access_photo_stack_groups g WHERE g.library_id=?
 AND (SELECT count(*) FROM access_photo_stack_members m WHERE m.library_id=g.library_id AND m.group_id=g.group_id)=g.member_count
 AND NOT EXISTS(SELECT 1 FROM access_photo_stack_members m LEFT JOIN live a ON a.id=m.asset_id
 WHERE m.library_id=g.library_id AND m.group_id=g.group_id AND (
 a.id IS NULL OR a.mime IS NOT m.source_mime OR a.taken_at IS NOT m.source_taken_at
 OR a.phash IS NOT m.source_phash OR a.account IS NOT m.source_account OR a.batch IS NOT m.source_batch))),
 remaining AS (
 SELECT m.group_id,m.asset_id,m.ordinal FROM access_photo_stack_members m JOIN valid_groups g
 ON g.library_id=m.library_id AND g.group_id=m.group_id
 WHERE m.library_id=? AND m.asset_id NOT IN(SELECT CAST(value AS INTEGER) FROM json_each(?))),
 effective AS (SELECT g.* FROM valid_groups g WHERE
 (SELECT count(*) FROM remaining r WHERE r.group_id=g.group_id)>=2),
 tiles AS (
 SELECT 'asset' AS tile_kind,'' AS group_id,a.id AS anchor_id,a.id AS cover_id,a.ordering
 FROM live a WHERE a.id NOT IN(SELECT r.asset_id FROM remaining r JOIN effective e ON e.group_id=r.group_id)
 __MEDIA__
 UNION ALL
 SELECT 'group',g.group_id,g.anchor_id,
 COALESCE((SELECT r.asset_id FROM remaining r WHERE r.group_id=g.group_id
 AND r.asset_id=CAST(json_extract(?,'$."'||g.group_id||'"[1]') AS INTEGER)
),
 (SELECT r.asset_id FROM remaining r WHERE r.group_id=g.group_id ORDER BY r.ordinal LIMIT 1)),a.ordering
 FROM effective g JOIN live a ON a.id=g.anchor_id)
'''.replace('__LIVE__', _LIVE).replace('__SOURCE__', SOURCE)


def _ident(value):
    return type(value) is str and ID.fullmatch(value) is not None and int(value) <= 2**63-1


def _generation(value):
    try:
        return type(value) is str and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _source(db, library):
    if db.execute("SELECT 1 FROM access_libraries WHERE id=? AND state='active'", (library,)).fetchone() is None:
        raise ValueError('active_library_required')
    history=getattr(db,'original_deletions',None)
    if history is None and db.execute('SELECT 1 FROM access_original_deletion_state LIMIT 1').fetchone():
        raise ValueError('deletion_history_guard_required')
    if history is not None:history.assert_current(db)
    rows = db.execute('SELECT '+_INPUT+SOURCE+GALLERY_ORDER+' LIMIT ?', (library,MAX_ASSETS+1)).fetchall()
    if len(rows)>MAX_ASSETS:
        raise ValueError('photo_stack_asset_limit')
    digest = hashlib.sha256(json.dumps(rows,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    return rows,digest


def rebuild_photo_stack_index(db, library, *, expected_generation, clock=time.time, stopped=None):
    """Offline worker entry: no implicit schema creation or runtime activation.

    CPU clustering runs outside a write transaction. Re-read source under the
    publication lock and refuse changes; previous index and choices survive any
    failure. Existing account preferences are never rewritten by this helper.
    """
    if stopped is not None and not callable(stopped):
        raise ValueError('explicit_stop_callback_required')
    check_stopped(stopped)
    if db.in_transaction or db.execute('PRAGMA foreign_keys').fetchone()[0]!=1 or not available(db):
        raise ValueError('explicit_migrated_connection_required')
    if expected_generation is not None and not _generation(expected_generation):
        raise ValueError('invalid_expected_generation')
    db.execute('BEGIN')
    try:
        rows,digest = _source(db,library)
        check_stopped(stopped)
        current=db.execute('SELECT generation,source_digest FROM access_photo_stack_indexes WHERE library_id=?',(library,)).fetchone()
        if (current[0] if current else None)!=expected_generation:raise Conflict('Photo stack index changed')
        if current and current[1]==digest:
            count=db.execute('SELECT count(*) FROM access_photo_stack_groups WHERE library_id=?',(library,)).fetchone()[0]
            db.commit();return {'index_revision':current[0],'groups':count,'changed':False}
        db.commit()
    except BaseException:
        db.rollback();raise
    from .photo_stack_index import build_library_photo_stacks
    groups=(build_library_photo_stacks(rows) if stopped is None
            else build_library_photo_stacks(rows,stopped=stopped))
    check_stopped(stopped)
    by_id={r[0]:r for r in rows}
    db.execute('BEGIN IMMEDIATE')
    try:
        current=db.execute('SELECT generation,source_digest FROM access_photo_stack_indexes WHERE library_id=?',(library,)).fetchone()
        if (current[0] if current else None)!=expected_generation:
            raise Conflict('Photo stack index changed')
        if _source(db,library)[1]!=digest:
            raise Conflict('Photo stack source changed')
        if current and current[1]==digest:
            db.commit();return {'index_revision':current[0],'groups':len(groups),'changed':False}
        generation=str(uuid.uuid4())
        db.execute('DELETE FROM access_photo_stack_groups WHERE library_id=?',(library,))
        db.execute('''INSERT INTO access_photo_stack_indexes VALUES (?,?,?,?,?)
            ON CONFLICT(library_id) DO UPDATE SET generation=excluded.generation,
            source_digest=excluded.source_digest,asset_count=excluded.asset_count,built_at=excluded.built_at''',
            (library,generation,digest,len(rows),int(clock())))
        for g in groups:
            check_stopped(stopped)
            signature=hashlib.sha256(json.dumps([g['reason'],sorted(g['asset_ids'],key=int)],separators=(',',':')).encode()).hexdigest()
            db.execute('INSERT INTO access_photo_stack_groups VALUES (?,?,?,?,?,?)',
                (library,g['id'],signature,int(g['asset_ids'][0]),g['reason'],g['count']))
            db.executemany('INSERT INTO access_photo_stack_members VALUES (?,?,?,?,?,?,?,?,?)',
                [(library,g['id'],int(ident),ordinal,by_id[int(ident)][1],by_id[int(ident)][5],
                  by_id[int(ident)][6],by_id[int(ident)][7],by_id[int(ident)][8])
                 for ordinal,ident in enumerate(g['asset_ids'])])
        history=getattr(db,'original_deletions',None)
        if history is not None:history.assert_current(db)
        check_stopped(stopped)
        db.commit();return {'index_revision':generation,'groups':len(groups),'changed':True}
    except BaseException:
        db.rollback();raise


class LibraryPhotoStacks:
    def __init__(self,access):
        self.access=access;self.db=access.db

    @contextmanager
    def _budget(self):
        deadline=time.monotonic()+3;steps=0
        def progress():
            nonlocal steps
            steps+=1000
            return int(steps>20000000 or time.monotonic()>deadline)
        self.db.set_progress_handler(progress,1000)
        try:
            yield
        except sqlite3.OperationalError as error:
            if str(error)=='interrupted':
                raise TransportError(503,'Indexed gallery temporarily unavailable') from None
            raise
        finally:
            self.db.set_progress_handler(None,0)

    def _index(self,library):
        if not available(self.db):
            raise TransportError(404,'Indexed gallery unavailable')
        row=self.db.execute('SELECT generation FROM access_photo_stack_indexes WHERE library_id=?',(library,)).fetchone()
        if not row:
            raise TransportError(404,'Indexed gallery unavailable')
        if not _generation(row[0]):
            raise TransportError(503,'Indexed gallery unavailable')
        count=self.db.execute('SELECT count(*) FROM(SELECT a.id'+SOURCE+' LIMIT ?)',(library,MAX_ASSETS+1)).fetchone()[0]
        if count>MAX_ASSETS:raise TransportError(404,'Indexed gallery unavailable')
        return row[0]

    def _preferences(self,library,account):
        row=self.db.execute('SELECT revision,choices_json FROM access_photo_stack_preferences WHERE library_id=? AND account_id=?',
                            (library,account)).fetchone()
        if not row:return 0,{'covers':{},'separate':[]}
        try:
            if type(row[0]) is not int or not 1<=row[0]<2**63-1 or len(row[1].encode())>262144:raise ValueError()
            value=json.loads(row[1])
            if type(value) is not dict or set(value)!={'covers','separate'}:raise ValueError()
            covers=value['covers'];separate=value['separate']
            if (type(covers) is not dict or len(covers)>MAX_CHOICES or type(separate) is not list
                or len(separate)>MAX_CHOICES or len(set(separate))!=len(separate) or not all(_ident(x) for x in separate)):raise ValueError()
            for key,pair in covers.items():
                if (not _ident(key) or type(pair) is not list or len(pair)!=2
                    or type(pair[0]) is not str or not DIGEST.fullmatch(pair[0]) or not _ident(pair[1])):raise ValueError()
            return row[0],value
        except (ValueError,TypeError,UnicodeError,RecursionError):
            raise TransportError(503,'Display choices unavailable') from None

    def _query(self,library,choices,media='all'):
        sql=CTE.replace('__MEDIA__'," AND a.mime GLOB 'image/*'" if media=='image' else '')
        covers=json.dumps(choices['covers'],separators=(',',':'))
        return sql,(library,library,library,json.dumps(choices['separate']),covers)

    def gallery(self,token,library,*,page=1,media='all'):
        if type(page) is not int or not 1<=page<=100000 or media not in {'all','image'}:
            raise TransportError(400,'Invalid indexed gallery request')
        with self.access._transaction(),self._budget():
            member=self.access._require(token,library,'library.read')
            generation=self._index(library)
            revision,choices=self._preferences(library,member['account_id'])
            sql,args=self._query(library,choices,media)
            tiles=self.db.execute(sql+'SELECT tile_kind,group_id,anchor_id,cover_id,count(*) OVER() FROM tiles\n                ORDER BY ordering DESC,anchor_id DESC,tile_kind,group_id LIMIT ? OFFSET ?',
                args+(PAGE_SIZE,(page-1)*PAGE_SIZE)).fetchall()
            total=tiles[0][4] if tiles else self.db.execute(sql+'SELECT count(*) FROM tiles',args).fetchone()[0]
            items=[];groups=[]
            for kind,gid,anchor,cover,_ in tiles:
                if kind=='group':
                    rows=self.db.execute('SELECT '+HINT_FIELDS+SOURCE+' AND a.id IN(\n                        SELECT asset_id FROM access_photo_stack_members WHERE library_id=? AND group_id=?\n                        AND asset_id NOT IN(SELECT CAST(value AS INTEGER) FROM json_each(?)))'+GALLERY_ORDER,
                        (library,library,gid,json.dumps(choices['separate']))).fetchall()
                    if not 2<=len(rows)<=MAX_MEMBERS or cover not in {r[0] for r in rows}:
                        raise TransportError(503,'Indexed gallery unavailable')
                    reason=self.db.execute('SELECT reason FROM access_photo_stack_groups WHERE library_id=? AND group_id=?',(library,gid)).fetchone()[0]
                    groups.append({'id':gid,'cover_asset_id':str(cover),'asset_ids':[str(r[0]) for r in rows],'count':len(rows),'reason':reason})
                else:
                    rows=self.db.execute('SELECT '+HINT_FIELDS+SOURCE+' AND a.id=?',(library,cover)).fetchall()
                items.extend(_asset(row,library,hints=True) for row in rows)
            return {'library_id':library,'page':page,'page_size':PAGE_SIZE,'total':total,
                'originals_allowed':bool(member['originals']),'items':items,
                'photo_stacks':{'version':2,'scope':'library','index_revision':generation,
                                'preference_revision':revision,'groups':groups}}

    def update(self,token,library,body):
        if (type(body) is not dict or set(body)!=FIELDS_WRITE or any(type(v) is not str for v in body.values())
            or not _generation(body['index_revision']) or not re.fullmatch(r'0|[1-9][0-9]{0,18}',body['revision'])
            or int(body['revision'])>=2**63-2 or body['reset'] not in {'0','1'}):
            raise TransportError(400,'Invalid display choice')
        reset=body['reset']=='1'
        if reset:
            if any(body[k] for k in ['group_id','cover_asset_id','separate_asset_id']):raise TransportError(400,'Invalid display choice')
        elif (not _ident(body['group_id']) or bool(body['cover_asset_id'])==bool(body['separate_asset_id'])
              or not _ident(body['cover_asset_id'] or body['separate_asset_id'])):
            raise TransportError(400,'Invalid display choice')
        with self.access._transaction(write=True),self._budget():
            member=self.access._require(token,library,'library.read');generation=self._index(library)
            revision,choices=self._preferences(library,member['account_id'])
            if body['index_revision']!=generation or int(body['revision'])!=revision:
                raise TransportError(409,'Refresh display choices')
            if reset:choices={'covers':{},'separate':[]}
            else:
                sql,args=self._query(library,choices)
                row=self.db.execute(sql+'SELECT signature FROM valid_groups WHERE group_id=?',args+(body['group_id'],)).fetchone()
                target=body['cover_asset_id'] or body['separate_asset_id']
                if row is None or self.db.execute(sql+'SELECT 1 FROM remaining WHERE group_id=? AND asset_id=?',args+(body['group_id'],int(target))).fetchone() is None:
                    raise TransportError(409,'Refresh display choices')
                if body['cover_asset_id']:choices['covers'][body['group_id']]=[row[0],target]
                else:
                    choices['separate'].append(target)
                    if choices['covers'].get(body['group_id'],[None,None])[1]==target:choices['covers'].pop(body['group_id'],None)
                if max(len(choices['covers']),len(choices['separate']))>MAX_CHOICES:
                    raise TransportError(422,'Reset display choices before adding more')
            encoded=json.dumps(choices,separators=(',',':'),sort_keys=True)
            if len(encoded.encode())>262144:raise TransportError(422,'Display choice limit reached')
            self.db.execute('''INSERT INTO access_photo_stack_preferences VALUES (?,?,?,?,?)
                ON CONFLICT(library_id,account_id) DO UPDATE SET revision=excluded.revision,
                choices_json=excluded.choices_json,updated_at=excluded.updated_at''',
                (library,member['account_id'],revision+1,encoded,self.access._now()))
            return {'index_revision':generation,'preference_revision':revision+1}
