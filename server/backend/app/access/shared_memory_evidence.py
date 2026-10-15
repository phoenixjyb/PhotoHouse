"""Current, bounded source notes shared by explicitly reviewed memory groups.

The caller owns a library-authorized read/write transaction. This adapter does
not infer a group, copy a note, save text or open storage. Every group member and
source origin is checked in that same snapshot before any note can be shared.
"""
from .memory_groups import _stored, MAX_GROUPS_PER_ASSET
from .library import SOURCE
from .memory_group_schema import TABLE
from .transport import TransportError


def shared_notes(db, library, asset_ids, *, dependencies=None):
    """Return original rows per selected asset, keyed by canonical source ID.

    No token is needed here: the caller already authorized the library and full
    selection. Recheck all *other* group members using the group GET boundary;
    a withdrawn member invalidates the complete group, as on ordinary group GET.
    """
    selected = list(dict.fromkeys(asset_ids))
    result = {asset: {} for asset in selected}
    if not selected:
        return result
    placeholders = ','.join('?' for _ in selected)
    cursor = db.execute(f'''SELECT g.* FROM {TABLE} g WHERE g.library_id=?
        AND EXISTS (SELECT 1 FROM json_each(g.asset_ids_json) m
                    WHERE m.value IN ({placeholders}))
        ORDER BY g.updated_at DESC,g.id DESC LIMIT ?''',
        (library, *selected, len(selected) * MAX_GROUPS_PER_ASSET + 1))
    names = [column[0] for column in cursor.description]
    rows = cursor.fetchall()
    if len(rows) > len(selected) * MAX_GROUPS_PER_ASSET:
        raise TransportError(422, 'Choose a smaller set of shared memories')
    counts = {asset: 0 for asset in selected}
    for values in rows:
        group = dict(zip(names, values))
        content = _stored(group)
        if any(db.execute('SELECT a.id' + SOURCE + ''' AND a.id=?
                AND (a.mime GLOB 'image/*' OR a.mime GLOB 'video/*')''',
                (library, asset)).fetchone() is None for asset in content['asset_ids']):
            continue
        if dependencies is not None:
            # Private, content-free snapshot dependency. It is hashed into the
            # selection revision, never added to a public item or stored note.
            dependencies.append([group['id'], group['revision'], content])
        destinations = set(selected) & set(content['asset_ids'])
        for asset in destinations:
            counts[asset] += 1
            if counts[asset] > MAX_GROUPS_PER_ASSET:
                raise TransportError(422, 'Choose a smaller set of shared memories')
        for source_id in content['source_story_ids']:
            note = db.execute('''SELECT s.id,substr(s.title,1,160),substr(s.text,1,1800),
                    s.revision,s.asset_id,s.byline
                FROM access_stories s JOIN assets a ON a.id=s.asset_id
                JOIN access_asset_libraries l ON l.asset_id=a.id
                WHERE s.id=? AND s.library_id=? AND l.library_id=? AND s.deleted=0
                  AND (a.status IS NULL OR a.status='active')''',
                (source_id, library, library)).fetchone()
            if note is None or note[4] not in content['asset_ids']:
                continue
            for asset in destinations:
                result[asset][source_id] = note
    return result
