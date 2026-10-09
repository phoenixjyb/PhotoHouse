"""Member-visible, read-only tag catalog.

A member sees tag names and how many of *this* library's active assets carry them,
and nothing else. There is no write path here at all: no add, no remove, no rename,
no tag derivation and no per-link provenance.

What is deliberately not exposed, and why:

- **No `source` breakdown** (`cap` / `img` / `cap+img` / `manual` / `rule`). That is
  pipeline provenance — how a caption or an image model produced the tag — not a
  family-facing fact, and legacy's per-source counters are not a member feature.
- **No tag `type`**, for the same reason: it names the derivation, not the content.
- **No global or cross-library counts.** Every count is a count of the caller's own
  visible assets. A library-wide or global total would let a member infer the size of
  an audience they are not in.
- **No probe by id.** A tag that carries nothing in this library is indistinguishable
  from a tag that does not exist, and neither is ever confirmed.

Legacy listing semantics are preserved deliberately: `DELETE /assets/{id}/tags`
removes the `asset_tags` row and records a *separate* `asset_tag_blocks` row only to
stop automatic re-adding, so a blocked pair has no link and never inflates a count.
Counting from `asset_tags` alone therefore matches legacy `/tags`, which also ignores
blocks.

The visibility predicate is the one the gallery uses (`library.SOURCE`): an asset is
visible when `access_asset_libraries` maps it to the library and its status is active
or absent. The catalog query writes that predicate out inline because it groups by
tag, and the tests pin the two definitions together by asserting a foreign library's
tag is invisible rather than by comparing SQL text.
"""
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .library import FIELDS, SOURCE, LibraryRoute, _asset, _integer, _query
from .service import AccessDenied, AccessService
from .transport import TransportError, _body, _runtime, credentials_from_request

router = APIRouter(route_class=LibraryRoute)
PAGE_SIZE = 25

# Accepted family-note labels are a separate named facet. Legacy /tags and the
# phone discovery v1 artifact keep their existing numeric tag identity.
ACCEPTED_LINKS = '''SELECT DISTINCT p.tag AS tag,u.asset_id AS asset_id
    FROM access_annotation_tag_proposals p
    JOIN access_upload_annotations n ON n.id=p.annotation_id
    JOIN access_annotation_derivations d ON d.annotation_id=n.id AND d.revision=p.revision
    JOIN access_uploads u ON u.account_id=n.author_id AND u.batch=n.batch
        AND u.destination_library_id=n.library_id AND u.state='assigned'
        AND (n.asset_id IS NULL OR n.asset_id=u.asset_id)
    JOIN assets a ON a.id=u.asset_id
    JOIN access_asset_libraries m ON m.asset_id=a.id AND m.library_id=n.library_id
    WHERE n.library_id=? AND p.status='accepted' AND d.state='completed'
        AND d.revision=(SELECT max(revision) FROM access_annotation_derivations
            WHERE annotation_id=n.id)
        AND (a.status IS NULL OR a.status='active')'''


class Tags:
    def __init__(self, access):
        self.access, self.db = access, access.db

    def catalog(self, token, library, page, query):
        """Library-scoped tag catalog: a name and this library's asset count.

        Gated on `library.read`, so any approved membership may read it rather than
        the owner only. Only tags with at least one link to a visible asset of this
        library appear, ordered most-used first, so the result can only ever confirm
        tags the caller can already see.
        """
        if len(query) > 128 or any(ord(c) < 32 for c in query):
            raise TransportError(400, 'Invalid search')
        pattern = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        with self.access._transaction():
            self.access._require(token, library, 'library.read')
            sql = '''WITH visible AS (SELECT x.tag_id AS tag_id,count(DISTINCT x.asset_id) AS n
                FROM asset_tags x JOIN assets a ON a.id=x.asset_id
                JOIN access_asset_libraries scope ON scope.asset_id=a.id
                WHERE scope.library_id=? AND (a.status IS NULL OR a.status='active')
                GROUP BY x.tag_id)
                SELECT t.id,substr(t.name,1,128),length(t.name),v.n
                FROM tags t JOIN visible v ON v.tag_id=t.id
                WHERE t.name LIKE ? ESCAPE '\\' '''
            parameters = (library, pattern)
            total = self.db.execute('SELECT count(*) FROM (' + sql + ')', parameters).fetchone()[0]
            rows = self.db.execute(
                sql + ' ORDER BY v.n DESC,t.name COLLATE NOCASE,t.id LIMIT 25 OFFSET ?',
                parameters + ((page - 1) * PAGE_SIZE,)).fetchall()
            return {'library_id': library, 'page': page, 'page_size': PAGE_SIZE, 'total': total,
                    'items': [{'id': str(row[0]), 'name': row[1], 'name_truncated': row[2] > 128,
                               'asset_count': row[3]} for row in rows]}

    def assets(self, token, library, tag, page):
        """Visible assets of this library carrying one tag, same shape as the gallery."""
        with self.access._transaction():
            member = self.access._require(token, library, 'library.read')
            if self.db.execute('SELECT 1' + SOURCE +
                    ' AND a.id IN (SELECT asset_id FROM asset_tags WHERE tag_id=?) LIMIT 1',
                    (library, tag)).fetchone() is None:
                raise AccessDenied('Access denied')
            total = self.db.execute('SELECT count(*)' + SOURCE +
                ' AND a.id IN (SELECT asset_id FROM asset_tags WHERE tag_id=?)',
                (library, tag)).fetchone()[0]
            rows = self.db.execute('SELECT ' + FIELDS + SOURCE +
                ' AND a.id IN (SELECT asset_id FROM asset_tags WHERE tag_id=?)'
                ' ORDER BY a.taken_at DESC,a.id DESC LIMIT ? OFFSET ?',
                (library, tag, PAGE_SIZE, (page - 1) * PAGE_SIZE)).fetchall()
            return {'library_id': library, 'tag_id': str(tag), 'page': page, 'page_size': PAGE_SIZE,
                    'total': total, 'originals_allowed': bool(member['originals']),
                    'items': [_asset(row, library) for row in rows]}

    def family_catalog(self, token, library, page, query):
        """Names and visible-asset counts for accepted, current family note labels."""
        if (len(query) > 128 or len(query.encode('utf-8')) > 512
                or any(ord(c) < 32 or ord(c) == 127 for c in query)):
            raise TransportError(400, 'Invalid search')
        pattern = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        with self.access._transaction():
            self.access._require(token, library, 'library.read')
            sql = '''WITH links AS (''' + ACCEPTED_LINKS + ''')
                SELECT tag,count(DISTINCT asset_id) AS n FROM links
                WHERE tag LIKE ? ESCAPE '\\' GROUP BY tag'''
            args = (library, pattern)
            total = self.db.execute('SELECT count(*) FROM (' + sql + ')', args).fetchone()[0]
            rows = self.db.execute(sql + ''' ORDER BY n DESC,tag COLLATE NOCASE,tag
                LIMIT ? OFFSET ?''', args + (PAGE_SIZE, (page - 1) * PAGE_SIZE)).fetchall()
            return {'library_id': library, 'page': page, 'page_size': PAGE_SIZE, 'total': total,
                    'items': [{'name': row[0], 'asset_count': row[1]} for row in rows]}

    def family_assets(self, token, library, tag, page):
        """Gallery-shaped assets for one exact accepted family note label."""
        if (not tag.strip() or len(tag) > 128 or len(tag.encode('utf-8')) > 512
                or any(ord(c) < 32 or ord(c) == 127 for c in tag)):
            raise TransportError(400, 'Invalid tag')
        with self.access._transaction():
            member = self.access._require(token, library, 'library.read')
            scope = '''WITH links AS (''' + ACCEPTED_LINKS + ''') SELECT '''
            predicate = SOURCE + ' AND a.id IN (SELECT asset_id FROM links WHERE tag=?)'
            args = (library, library, tag)
            total = self.db.execute(scope + 'count(*)' + predicate, args).fetchone()[0]
            if not total:
                raise AccessDenied('Access denied')
            rows = self.db.execute(scope + FIELDS + predicate +
                ' ORDER BY a.taken_at DESC,a.id DESC LIMIT ? OFFSET ?',
                args + (PAGE_SIZE, (page - 1) * PAGE_SIZE)).fetchall()
            return {'library_id': library, 'tag': tag, 'page': page, 'page_size': PAGE_SIZE,
                    'total': total, 'originals_allowed': bool(member['originals']),
                    'items': [_asset(row, library) for row in rows]}


def _call(runtime, action, *args):
    with runtime.connection_factory() as db:
        deadline = time.monotonic() + 3
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        try:
            return getattr(Tags(AccessService(db, clock=runtime.clock)), action)(*args)
        finally:
            db.set_progress_handler(None, 0)


@router.get('/tags')
async def catalog(request: Request):
    # Member-facing catalog. Distinct from the retired legacy /tags on purpose: the
    # legacy response carried per-source counters and a tag type, and the legacy page
    # also offered the write path. Neither is reproduced here.
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'page', 'q'})
    return JSONResponse(await run_in_threadpool(_call, _runtime(request, allow_query=True), 'catalog', token,
        query['library'], _integer(query.get('page', '1'), 100000), query.get('q', '')))


@router.get('/tags/{tag_id}/assets')
async def assets(tag_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'page'})
    return JSONResponse(await run_in_threadpool(_call, _runtime(request, allow_query=True), 'assets', token,
        query['library'], _integer(tag_id, 2**63-1), _integer(query.get('page', '1'), 100000)))


@router.get('/family-tags')
async def family_catalog(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'page', 'q'})
    return JSONResponse(await run_in_threadpool(_call, _runtime(request, allow_query=True),
        'family_catalog', token, query['library'], _integer(query.get('page', '1'), 100000),
        query.get('q', '')))


@router.post('/family-tags/assets')
async def family_assets(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    body = await _body(request, {'tag', 'page'}, max_body=1024)
    return JSONResponse(await run_in_threadpool(_call, _runtime(request, allow_query=True),
        'family_assets', token, query['library'], body['tag'],
        _integer(body['page'], 100000)))
