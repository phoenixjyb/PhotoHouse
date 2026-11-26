"""Revisioned private groups of library media with read-through family notes.

Group rows and revisions contain IDs and a theme only. Note wording always comes
from the current ``access_stories`` row through ``Stories._present``.
"""
import hashlib
import json
import uuid

from .library import SOURCE, _asset, _integer
from .memory_group_schema import (TABLE, REVISION_TABLE, GROUP_REVISIONS,
                                  verify_memory_group_schema)
from .service import AccessDenied
from .stories import Stories, _uuid
from .transport import TransportError

FIELDS = {'asset_ids', 'excluded_asset_ids', 'source_story_ids', 'theme',
          'revision', 'mutation_id'}
MEMORY_GROUP_FIELDS = FIELDS
MEMORY_GROUP_SPLIT_FIELDS = {'asset_ids', 'revision', 'mutation_id'}
MEMORY_GROUP_COMBINE_FIELDS = {'group_ids', 'group_revisions', 'source_story_ids',
                               'source_story_revisions', 'theme', 'mutation_id'}
THEMES = {'trip', 'growing_up', 'birthday', 'grandparents',
          'year_in_review', 'everyday'}
MAX_ASSETS = 24
MAX_EXCLUDED = 512
MAX_SOURCE_STORIES = 12
MAX_GROUPS_PER_ASSET = 8
MAX_RECENT_GROUPS = 8
MAX_RECENT_GROUP_CANDIDATES = 64
MAX_RESPONSE_BYTES = 1024 * 1024


def _csv(value, field, *, maximum, identifiers=False, required=False):
    if type(value) is not str:
        raise TransportError(400, 'Invalid memory group request')
    if not value:
        if required:
            raise TransportError(422, 'Select one to 24 group assets')
        return []
    parts = value.split(',')
    if not 1 <= len(parts) <= maximum or len(set(parts)) != len(parts):
        raise TransportError(422, 'Invalid memory group selection')
    if identifiers:
        try:
            return [_uuid(part) for part in parts]
        except (TypeError, AttributeError):
            raise TransportError(400, 'Invalid memory group identifier') from None
    try:
        ids = [_integer(part, 2**63 - 1) for part in parts]
    except (AttributeError, TypeError):
        raise TransportError(400, 'Invalid memory group asset identifier') from None
    if any(str(ident) != part for ident, part in zip(ids, parts)):
        raise TransportError(400, 'Invalid memory group asset identifier')
    return ids


def _body(body):
    if (type(body) is not dict or set(body) != FIELDS
            or any(type(value) is not str for value in body.values())):
        raise TransportError(400, 'Invalid memory group request')
    try:
        encoded_size = sum(len(value.encode('utf-8')) for value in body.values())
    except UnicodeError:
        raise TransportError(400, 'Invalid memory group request') from None
    if encoded_size > 24 * 1024:
        raise TransportError(413, 'Memory group request too large')
    assets = _csv(body['asset_ids'], 'asset_ids', maximum=MAX_ASSETS, required=True)
    excluded = _csv(body['excluded_asset_ids'], 'excluded_asset_ids', maximum=MAX_EXCLUDED)
    sources = _csv(body['source_story_ids'], 'source_story_ids', maximum=MAX_SOURCE_STORIES,
                   identifiers=True)
    if set(assets) & set(excluded):
        raise TransportError(422, 'Included and excluded assets must be distinct')
    if body['theme'] not in THEMES:
        raise TransportError(422, 'Unsupported memory group theme')
    revision, mutation_id = _mutation_identity(body)
    content = {
        'theme': body['theme'],
        'asset_ids': assets,
        'excluded_asset_ids': excluded,
        'source_story_ids': sources,
    }
    return content, revision, mutation_id


def _revision(value):
    revision = 0 if value == '0' else _integer(value, 2**63 - 2)
    if str(revision) != value:
        raise TransportError(400, 'Invalid memory group revision')
    return revision


def _mutation_identity(body):
    mutation = _uuid(body['mutation_id'])
    return _revision(body['revision']), mutation


def _request_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    separators=(',', ':')).encode()).hexdigest()


def _stored(row):
    try:
        assets = json.loads(row['asset_ids_json'])
        excluded = json.loads(row['excluded_asset_ids_json'])
        sources = json.loads(row['source_story_ids_json'])
        if (row['theme'] not in THEMES or type(assets) is not list
                or not 1 <= len(assets) <= MAX_ASSETS
                or any(type(value) is not int or value < 1 for value in assets)
                or len(set(assets)) != len(assets)
                or type(excluded) is not list or len(excluded) > MAX_EXCLUDED
                or any(type(value) is not int or value < 1 for value in excluded)
                or len(set(excluded)) != len(excluded) or set(assets) & set(excluded)
                or type(sources) is not list or len(sources) > MAX_SOURCE_STORIES
                or any(type(value) is not str for value in sources)
                or len(set(sources)) != len(sources)):
            raise ValueError()
        sources = [_uuid(value) for value in sources]
        return {'theme': row['theme'], 'asset_ids': assets,
                'excluded_asset_ids': excluded, 'source_story_ids': sources}
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise TransportError(503, 'Memory group unavailable') from None


class MemoryGroups:
    """Domain operations; HTTP routing and optional-schema activation are separate."""

    def __init__(self, access):
        self.access = access
        self.db = access.db
        self.stories = Stories(access)

    def _ready(self):
        versions = [tuple(row) for row in self.db.execute('SELECT version_num FROM alembic_version')]
        if len(versions)!=1 or versions[0][0] not in GROUP_REVISIONS or not verify_memory_group_schema(self.db):
            raise TransportError(503, 'Memory groups unavailable')

    def _row(self, ident, library):
        row = self.access._one(
            f'SELECT * FROM {TABLE} WHERE id=? AND library_id=?', (ident, library))
        if row is None:
            raise AccessDenied('Access denied')
        return row

    @staticmethod
    def _can_edit(member, row):
        return (member['role'] == 'owner'
                or (member['role'] == 'contributor'
                    and row['author_id'] == member['account_id']))

    def _assets(self, token, library, asset_ids):
        # Resolve every member before returning any partial group. Inactive,
        # unsupported, moved or withdrawn members invalidate the whole group.
        items = []
        for ident in asset_ids:
            row = self.db.execute('SELECT a.id,a.mime,a.width,a.height,a.duration_sec,a.taken_at'
                + SOURCE + ' AND a.id=?', (library, ident)).fetchone()
            if row is None or not ((row[1] or '').startswith('image/')
                                   or (row[1] or '').startswith('video/')):
                raise AccessDenied('Access denied')
            items.append(_asset(row, library))
        return items

    def _sources(self, token, library, content):
        member_ids = set(content['asset_ids'])
        sources = []
        visible_ids = []
        for ident in content['source_story_ids']:
            try:
                row, member = self.stories._story(token, library, ident)
            except AccessDenied:
                # Erased or moved family notes are omitted on read. They are
                # never hydrated from revision snapshots or copied group text.
                continue
            if row['deleted'] or row['asset_id'] not in member_ids:
                continue
            sources.append(self.stories._present(row, member))
            visible_ids.append(ident)
        return visible_ids, sources

    def _present(self, token, row, library, member):
        content = _stored(row)
        items = self._assets(token, library, content['asset_ids'])
        source_ids, sources = self._sources(token, library, content)
        result = {
            'version': 1,
            'type': 'memory_group',
            'id': row['id'],
            'library_id': library,
            'revision': str(row['revision']),
            'theme': content['theme'],
            'asset_ids': [str(value) for value in content['asset_ids']],
            'excluded_asset_ids': [str(value) for value in content['excluded_asset_ids']],
            'source_story_ids': source_ids,
            'items': items,
            'sources': sources,
            'can_edit': self._can_edit(member, row),
        }
        if len(json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) > MAX_RESPONSE_BYTES:
            raise TransportError(503, 'Memory group response unavailable')
        return result

    def get(self, token, library, ident):
        ident = _uuid(ident)
        with self.access._transaction():
            member = self.access._require(token, library, 'library.read')
            self._ready()
            return self._present(token, self._row(ident, library), library, member)

    def _page_anchor(self, token, library, page):
        ident, separator, revision = page.partition('.')
        if not separator or str(_integer(revision, 2**63 - 1)) != revision:
            raise TransportError(400, 'Invalid memory group page')
        try:
            row = self._row(_uuid(ident), library)
            self._assets(token, library, _stored(row)['asset_ids'])
        except AccessDenied:
            raise TransportError(409, 'Memory group page changed') from None
        if str(row['revision']) != revision:
            raise TransportError(409, 'Memory group page changed')
        return row['updated_at'], row['id']

    def list_recent(self, token, library, page=None):
        with self.access._transaction():
            self.access._require(token, library, 'library.read')
            self._ready()
            filters, parameters = [], [library]
            limit = MAX_RECENT_GROUP_CANDIDATES
            wanted = MAX_RECENT_GROUPS
            if page is not None:
                if page != 'first':
                    filters.append('AND (g.updated_at,g.id) < (?,?)')
                    parameters.extend(self._page_anchor(token, library, page))
                # Skip withdrawn members in the query so a run of hidden groups
                # cannot conceal older groups. Recheck every returned member.
                filters.append(f"""AND NOT EXISTS (
                    SELECT 1 FROM json_each(CASE WHEN json_valid(g.asset_ids_json)
                        THEN g.asset_ids_json ELSE '[]' END) AS m
                    WHERE m.type!='integer' OR NOT EXISTS (
                        SELECT 1 {SOURCE} AND a.id=m.value
                            AND substr(a.mime,1,6) IN ('image/','video/')
                    )
                )""")
                parameters.append(library)
                wanted += 1
                limit = wanted
            rows = self.db.execute(f'''SELECT g.* FROM {TABLE} AS g WHERE g.library_id=?
                {' '.join(filters)} ORDER BY g.updated_at DESC,g.id DESC LIMIT ?''',
                (*parameters, limit))
            names = tuple(column[0] for column in rows.description)
            items = []
            for values in rows:
                row = dict(zip(names, values))
                content = _stored(row)
                try:
                    members = self._assets(token, library, content['asset_ids'])
                except AccessDenied:
                    continue
                # Verify the whole group even though only its cover is shown.
                items.append({'id': row['id'], 'revision': str(row['revision']),
                              'theme': content['theme'], 'count': len(members),
                              'cover': members[0]})
                if len(items) == wanted:
                    break
            result = {'version': 1, 'library_id': library, 'items': items[:MAX_RECENT_GROUPS]}
            if page is not None:
                result['next_page'] = None
                if len(items) > MAX_RECENT_GROUPS:
                    last = items[MAX_RECENT_GROUPS - 1]
                    result['next_page'] = f"{last['id']}.{last['revision']}"
            return result

    def list_for_asset(self, token, library, asset_id):
        if type(asset_id) is not int or asset_id < 1:
            raise TransportError(400, 'Invalid asset identifier')
        with self.access._transaction():
            self.access._require(token, library, 'library.read')
            self._ready()
            # The requested asset itself must currently be visible in this
            # library. This prevents using the listing as an ID oracle.
            self._assets(token, library, [asset_id])
            rows = self.db.execute(f'''SELECT g.* FROM {TABLE} g
                WHERE g.library_id=? AND EXISTS (
                    SELECT 1 FROM json_each(g.asset_ids_json) member
                    WHERE member.value=?)
                ORDER BY g.updated_at DESC,g.id DESC LIMIT 65''',
                (library, asset_id)).fetchall()
            names = [column[0] for column in self.db.execute(
                f'SELECT * FROM {TABLE} LIMIT 0').description]
            result = []
            for values in rows[:64]:
                row = dict(zip(names, values))
                content = _stored(row)
                try:
                    result.append(self._present(token, row, library,
                        self.access._require(token, library, 'library.read')))
                except AccessDenied:
                    # List only complete, currently authorized groups.
                    continue
                if len(result) > MAX_GROUPS_PER_ASSET:
                    break
            has_more = len(result) > MAX_GROUPS_PER_ASSET or len(rows) > 64
            items = result[:MAX_GROUPS_PER_ASSET]
            response = {'version': 1, 'library_id': library,
                        'asset_id': str(asset_id), 'has_more': has_more,
                        'items': items}
            if len(json.dumps(response, ensure_ascii=False,
                              separators=(',', ':')).encode('utf-8')) > MAX_RESPONSE_BYTES:
                raise TransportError(503, 'Memory group response unavailable')
            return response

    def save(self, token, library, body, ident=None):
        content, revision, mutation = _body(body)
        if ident is not None:
            ident = _uuid(ident)
            if revision < 1:
                raise TransportError(400, 'Invalid memory group revision')
        elif revision != 0:
            raise TransportError(400, 'New memory group revision must be zero')
        digest = _request_digest([library, ident, revision, content])
        with self.access._transaction(write=True):
            member = self.access._require(token, library, 'story.write')
            self._ready()
            row = self._row(ident, library) if ident is not None else None
            if row is not None and not self._can_edit(member, row):
                raise AccessDenied('Access denied')
            actor = member['account_id']
            prior = self._mutation(actor, mutation)
            if prior is not None:
                if prior['request_digest'] != digest:
                    raise TransportError(409, 'Memory group request identifier already used')
                current = self._row(prior['group_id'], library)
                return self._present(token, current, library, member)
            # Validate all members and source-note bindings in the same write
            # transaction as the revision, so scope cannot change mid-save.
            self._assets(token, library, content['asset_ids'])
            for story_id in content['source_story_ids']:
                source, _source_member = self.stories._story(token, library, story_id)
                if source['deleted'] or source['asset_id'] not in set(content['asset_ids']):
                    raise TransportError(422, 'Source stories must be active on a group asset')
            if row is not None and row['revision'] != revision:
                raise TransportError(409, 'Memory group changed; reload before saving')

            group_id = ident or str(uuid.uuid4())
            self._record(group_id, library, actor, revision, mutation, digest, content)
            return self._present(token, self._row(group_id, library), library, member)

    def _mutation(self, actor, mutation):
        return self.access._one(f'''SELECT group_id,request_digest
            FROM {REVISION_TABLE} WHERE editor_id=? AND mutation_id=?''', (actor, mutation))

    def _record(self, group_id, library, actor, revision, mutation, digest, content):
        next_revision = revision + 1
        now = self.access._now()
        fields = (content['theme'], json.dumps(content['asset_ids'], separators=(',', ':')),
                  json.dumps(content['excluded_asset_ids'], separators=(',', ':')),
                  json.dumps(content['source_story_ids'], separators=(',', ':')))
        if revision == 0:
            self.db.execute(f'''INSERT INTO {TABLE}
                (id,library_id,author_id,revision,theme,asset_ids_json,
                 excluded_asset_ids_json,source_story_ids_json,created_at,updated_at)
                VALUES(?,?,?,1,?,?,?,?,?,?)''',
                (group_id, library, actor, *fields, now, now))
        else:
            self.db.execute(f'''UPDATE {TABLE} SET revision=?,theme=?,asset_ids_json=?,
                excluded_asset_ids_json=?,source_story_ids_json=?,updated_at=? WHERE id=?''',
                (next_revision, *fields, now, group_id))
        self.db.execute(f'''INSERT INTO {REVISION_TABLE}
            (group_id,revision,editor_id,mutation_id,request_digest,theme,asset_ids_json,
             excluded_asset_ids_json,source_story_ids_json,occurred_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)''',
            (group_id, next_revision, actor, mutation, digest, *fields, now))
        self.access._audit(actor, 'memory.group_create' if revision == 0
                           else 'memory.group_edit', library)

    def split(self, token, library, body, ident):
        """Commit both reviewed groups together with one replayable mutation."""
        if (type(body) is not dict or set(body) != MEMORY_GROUP_SPLIT_FIELDS
                or any(type(value) is not str for value in body.values())):
            raise TransportError(400, 'Invalid memory group request')
        ident = _uuid(ident)
        revision, mutation = _mutation_identity(body)
        if revision < 1:
            raise TransportError(400, 'Invalid memory group revision')
        moved = set(_csv(body['asset_ids'], 'asset_ids', maximum=MAX_ASSETS, required=True))
        sibling_mutation = str(uuid.uuid5(uuid.UUID(mutation), 'photohouse-memory-group-split-sibling-v1'))
        digest = _request_digest(['split-v1', library, ident, revision, sorted(moved)])
        with self.access._transaction(write=True):
            member = self.access._require(token, library, 'story.write')
            self._ready()
            row = self._row(ident, library)
            if not self._can_edit(member, row):
                raise AccessDenied('Access denied')
            actor = member['account_id']
            prior = self._mutation(actor, mutation)
            sibling = self._mutation(actor, sibling_mutation)
            if prior is not None or sibling is not None:
                if (prior is None or sibling is None or prior['group_id'] != ident
                        or sibling['group_id'] == ident or prior['request_digest'] != digest
                        or sibling['request_digest'] != digest):
                    raise TransportError(409, 'Memory group request identifier already used')
                created_id = sibling['group_id']
                created = self._row(created_id, library)
                self._assets(token, library, _stored(row)['asset_ids'])
                self._assets(token, library, _stored(created)['asset_ids'])
            else:
                if row['revision'] != revision:
                    raise TransportError(409, 'Memory group changed; reload before splitting')
                content = _stored(row)
                assets = content['asset_ids']
                if not moved < set(assets):
                    raise TransportError(422, 'Move some assets and leave at least one')
                self._assets(token, library, assets)
                retained = [asset_id for asset_id in assets if asset_id not in moved]
                transferred = [asset_id for asset_id in assets if asset_id in moved]
                exclusions = content['excluded_asset_ids']
                if len(exclusions) + max(len(retained), len(transferred)) > MAX_EXCLUDED:
                    raise TransportError(422, 'Review the group exclusions before splitting')
                retained_sources, moved_sources = [], []
                for story_id in content['source_story_ids']:
                    try:
                        source, _ = self.stories._story(token, library, story_id)
                    except AccessDenied:
                        raise TransportError(409, 'Review the available family notes before splitting') from None
                    if source['deleted'] or source['asset_id'] not in assets:
                        raise TransportError(409, 'Review the available family notes before splitting')
                    target = moved_sources if source['asset_id'] in moved else retained_sources
                    target.append(story_id)
                created_id = str(uuid.uuid4())
                self._record(ident, library, actor, revision, mutation, digest,
                    {'theme': content['theme'], 'asset_ids': retained,
                     'excluded_asset_ids': exclusions + transferred, 'source_story_ids': retained_sources})
                self._record(created_id, library, actor, 0, sibling_mutation, digest,
                    {'theme': content['theme'], 'asset_ids': transferred,
                     'excluded_asset_ids': exclusions + retained, 'source_story_ids': moved_sources})
            return {'version': 1, 'library_id': library, 'source_id': ident, 'created_id': created_id}

    def combine(self, token, library, body):
        """Create one group from two reviewed revisions, preserving both originals."""
        if (type(body) is not dict or set(body) != MEMORY_GROUP_COMBINE_FIELDS
                or any(type(value) is not str for value in body.values())):
            raise TransportError(400, 'Invalid memory group request')
        groups = _csv(body['group_ids'], 'group_ids', maximum=2, identifiers=True)
        revision_fields = body['group_revisions'].split(',')
        if len(groups) != 2 or len(revision_fields) != 2:
            raise TransportError(422, 'Select exactly two memory groups')
        revisions = [_revision(value) for value in revision_fields]
        if 0 in revisions:
            raise TransportError(400, 'Invalid memory group revision')
        notes = _csv(body['source_story_ids'], 'source_story_ids',
                     maximum=MAX_SOURCE_STORIES, identifiers=True)
        note_revision_fields = body['source_story_revisions'].split(',') if body['source_story_revisions'] else []
        if len(note_revision_fields) != len(notes):
            raise TransportError(400, 'Invalid family note revisions')
        note_revisions = [_revision(value) for value in note_revision_fields]
        if 0 in note_revisions:
            raise TransportError(400, 'Invalid family note revision')
        theme = body['theme']
        if theme not in THEMES:
            raise TransportError(422, 'Unsupported memory group theme')
        mutation = _uuid(body['mutation_id'])
        digest = _request_digest(['combine-v1', library, groups, revisions,
                                  notes, note_revisions, theme])

        with self.access._transaction(write=True):
            member = self.access._require(token, library, 'story.write')
            self._ready()
            rows = [self._row(ident, library) for ident in groups]
            actor = member['account_id']
            prior = self._mutation(actor, mutation)
            if prior is not None:
                if prior['request_digest'] != digest:
                    raise TransportError(409, 'Memory group request identifier already used')
                created_id = prior['group_id']
                self._assets(token, library, _stored(self._row(created_id, library))['asset_ids'])
            else:
                if [row['revision'] for row in rows] != revisions:
                    raise TransportError(409, 'Memory groups changed; review them before combining')
                parts = [_stored(row) for row in rows]
                assets = list(dict.fromkeys(asset for part in parts for asset in part['asset_ids']))
                included = set(assets)
                exclusions = list(dict.fromkeys(asset for part in parts for asset in part['excluded_asset_ids']
                                                if asset not in included))
                if len(assets) > MAX_ASSETS or len(exclusions) > MAX_EXCLUDED:
                    raise TransportError(422, 'The combined group exceeds the media selection limits')
                self._assets(token, library, assets)
                current_notes = {note['id']: note['revision'] for part in parts
                                 for note in self._sources(token, library, part)[1]}
                if len(current_notes) > MAX_SOURCE_STORIES:
                    raise TransportError(422, 'The combined group exceeds the family note limit')
                if list(current_notes.items()) != list(zip(notes, note_revisions, strict=True)):
                    raise TransportError(409, 'Review the current family notes before combining')
                created_id = str(uuid.uuid4())
                self._record(created_id, library, actor, 0, mutation, digest,
                    {'theme': theme, 'asset_ids': assets, 'excluded_asset_ids': exclusions,
                     'source_story_ids': notes})
            return {'version': 1, 'library_id': library, 'source_group_ids': groups,
                    'created_id': created_id}
