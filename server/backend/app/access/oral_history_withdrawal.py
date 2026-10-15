"""Content-free recording withdrawal identity and prefix-safe offline replay.

Internal source only. Withdrawal hides an exact retained recording; it does not
erase source bytes or license a new HTTP/client/worker surface.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3

from .oral_history_schema import SESSION, SECTION, MAX_SECTIONS, assert_schema
from .oral_history_intake import (session_snapshot, wav_frames, _seed, _digest, _uuid,
                                 _text, _integer, MAX_TOTAL_FRAMES, MAX_TOTAL_BYTES)
from .service import AccessDenied
from .transport import TransportError
from .original_deletions import OriginalDeletionError

HEX = re.compile(r'^[0-9a-f]{64}$')
MAX_BINDING_BYTES = 16384
FIELDS = {'version','session_id','library_id','author_id','identity_sha256','seed_sha256',
          'manifest_sha256','section_heads','revision','state','request_id','request_digest'}


def _refuse():
    raise OriginalDeletionError('Recording withdrawal identity is unavailable')


def _json(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(',',':'))


def parse_recording_binding(raw):
    try:
        if type(raw) is not str or len(raw.encode('ascii'))>MAX_BINDING_BYTES:
            _refuse()
        def pairs(items):
            result={}
            for key,value in items:
                if key in result:_refuse()
                result[key]=value
            return result
        value=json.loads(raw,object_pairs_hook=pairs)
        if type(value) is not dict or set(value)!=FIELDS or type(value['version']) is not int or value['version']!=1:
            _refuse()
        for name in ('session_id','author_id','request_id'):_uuid(value[name])
        _text(value['library_id'],128,required=True)
        heads=value['section_heads']
        if type(heads) is not list or len(heads)>MAX_SECTIONS or len(set(heads))!=len(heads):_refuse()
        for digest in [value[k] for k in ('identity_sha256','seed_sha256','manifest_sha256','request_digest')]+heads:
            if type(digest) is not str or not HEX.fullmatch(digest):_refuse()
        if (value['state'] not in {'open','completed','cancelled'}
                or type(value['revision']) is not int
                or value['revision']!=1+len(heads)+int(value['state']!='open')
                or value['manifest_sha256']!=(heads[-1] if heads else value['seed_sha256'])
                or value['request_digest']!=_digest(['withdraw',value['library_id'],value['session_id'],
                                                    value['request_id'],value['revision']])):_refuse()
        if _json(value)!=raw:_refuse()
        return value
    except (KeyError,ValueError,TypeError,UnicodeError,RecursionError,TransportError):
        _refuse()


def _snapshot(db,ident,library,actor):
    if not db.in_transaction:_refuse()
    try:
        assert_schema(db)
        row=session_snapshot(db,actor,library,ident,allow_withdrawn=True)
        _integer(row['created_at'],2**63-1)
        heads=[]
        # Streaming one bounded section at a time; never hold a whole interview in memory.
        cursor=db.execute(f'SELECT audio,sha256,frames,manifest_sha256 FROM {SECTION} WHERE session_id=? ORDER BY ordinal LIMIT ?',
                          (ident,MAX_SECTIONS+1))
        for audio,sha,frames,head in cursor:
            if type(audio) is not bytes or wav_frames(audio)!=frames or hashlib.sha256(audio).hexdigest()!=sha:_refuse()
            heads.append(head)
        if len(heads)!=row['section_count']:_refuse()
        return row,heads
    except (sqlite3.Error,ValueError,TypeError,AccessDenied,TransportError):
        _refuse()


def prepare_recording_tombstone(db,ident,library,actor,revision,request,digest,occurred_at):
    try:
        for value in (ident,actor,request):_uuid(value)
        _text(library,128,required=True)
        _integer(occurred_at,2**63-1)
        row,heads=_snapshot(db,ident,library,actor)
        if row['state']=='withdrawn' or row['revision']!=revision:_refuse()
        seed=_seed(row)
        binding=_json({'version':1,'session_id':ident,'library_id':library,'author_id':actor,
            'identity_sha256':_digest(['oral-history-identity-v1',seed,row['created_at']]),
            'seed_sha256':seed,'manifest_sha256':row['manifest_sha256'],'section_heads':heads,
            'revision':revision,'state':row['state'],'request_id':request,'request_digest':digest})
        parse_recording_binding(binding)
        return {'collection':'oral_history','object_id':ident,'library_id':library,
            'original_kind':'recording','original_sha256':row['manifest_sha256'],
            'batch':None,'asset_id':None,'story_id':None,'occurred_at':occurred_at,
            'oral_binding_json':binding}
    except (ValueError,TypeError,TransportError):
        _refuse()


def verify_recording_record(db,record,*,preparing=False):
    try:
        binding=parse_recording_binding(record['oral_binding_json'])
        if (record['collection']!='oral_history' or record['original_kind']!='recording'
                or record['object_id']!=binding['session_id'] or record['library_id']!=binding['library_id']
                or record['original_sha256']!=binding['manifest_sha256']
                or any(record.get(k) is not None for k in ('batch','asset_id','story_id','family_binding_json','asset_binding_json'))):_refuse()
        _integer(record['occurred_at'],2**63-1)
        row,heads=_snapshot(db,binding['session_id'],binding['library_id'],binding['author_id'])
        seed=_seed(row)
        if (seed!=binding['seed_sha256']
                or _digest(['oral-history-identity-v1',seed,row['created_at']])!=binding['identity_sha256']
                or heads!=binding['section_heads'][:len(heads)] or len(heads)>len(binding['section_heads'])):_refuse()
        logical=row['withdrawn_from'] if row['state']=='withdrawn' else row['state']
        original_revision=row['revision']-int(row['state']=='withdrawn')
        if original_revision>binding['revision']:_refuse()
        if len(heads)<len(binding['section_heads']) and logical!='open':_refuse()
        # Same revision must be the exact reviewed state; an older backup can only be its verified prefix.
        if original_revision==binding['revision'] and (heads!=binding['section_heads'] or logical!=binding['state']):_refuse()
        if row['state']=='withdrawn' and (row['withdrawal_request_id']!=binding['request_id']
                or row['withdrawal_request_digest']!=binding['request_digest']):_refuse()
        if preparing and (row['state']=='withdrawn' or original_revision!=binding['revision']):_refuse()
        return binding,row
    except (KeyError,ValueError,TypeError,TransportError):
        _refuse()


def apply_recording_tombstone(db,record):
    """Withdraw an exact identity or older source prefix; keep original audio and rows."""
    binding,row=verify_recording_record(db,record)
    if row['state']=='withdrawn':return
    if db.execute('PRAGMA secure_delete').fetchone()[0]!=1:_refuse()
    changed=db.execute(f'''UPDATE {SESSION} SET withdrawn_from=state,state='withdrawn',revision=revision+1,
        withdrawal_request_id=?,withdrawal_request_digest=? WHERE id=? AND state!='withdrawn' ''',
        (binding['request_id'],binding['request_digest'],binding['session_id'])).rowcount
    if changed!=1:_refuse()
