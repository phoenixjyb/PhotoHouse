"""One bounded CPU-only index refresh sweep for an explicitly selected library set.

A qualified host owns scheduling, cancellation and process resource limits.
Importing this module or serving gallery requests never starts the worker.
"""
from .library_photo_stacks import rebuild_photo_stack_index
from .photo_stack_schema import available
from .service import Conflict
from .photo_stack_index import PhotoStackCancelled
import sqlite3


class PhotoStackRefreshWorker:
    def __init__(self,connection_factory,libraries,*,stopped=lambda:False):
        if (not callable(connection_factory) or not callable(stopped) or type(libraries) is not tuple
            or not 1<=len(libraries)<=32 or len(set(libraries))!=len(libraries)
            or any(type(x) is not str or not 1<=len(x)<=128 or any(ord(c)<32 for c in x) for x in libraries)):
            raise ValueError('Explicit photo stack worker configuration required')
        self.connection_factory=connection_factory;self.libraries=libraries;self.stopped=stopped

    def run_once(self):
        results=[]
        for library in self.libraries:
            if self.stopped():break
            with self.connection_factory() as db:
                if db.in_transaction or db.execute('PRAGMA foreign_keys').fetchone()[0]!=1:
                    raise ValueError('Fresh migrated connection required')
                if not available(db):
                    results.append({'library_id':library,'status':'unavailable'});continue
                # A failed hash remains evidence and its photo stays individually visible.
                # Only runnable hash work is a reason to defer this sweep.
                pending=db.execute('''SELECT 1 FROM tasks t JOIN assets a ON a.id=
                    CASE WHEN json_valid(t.payload_json) THEN json_extract(t.payload_json,'$.asset_id') END
                    JOIN access_asset_libraries scope ON scope.asset_id=a.id
                    WHERE scope.library_id=? AND t.type='phash' AND t.cancel_requested=0
                    AND (a.status='active' OR a.status IS NULL)
                    AND (t.state='running' OR (t.state='pending' AND
                        (t.scheduled_at IS NULL OR t.scheduled_at<=CURRENT_TIMESTAMP))) LIMIT 1''',(library,)).fetchone()
                if pending:
                    results.append({'library_id':library,'status':'waiting'});continue
                current=db.execute('SELECT generation FROM access_photo_stack_indexes WHERE library_id=?',(library,)).fetchone()
                if self.stopped():break
                try:
                    result=rebuild_photo_stack_index(db,library,expected_generation=current[0] if current else None,
                                                     stopped=self.stopped)
                except PhotoStackCancelled:
                    results.append({'library_id':library,'status':'cancelled'});break
                except sqlite3.OperationalError as error:
                    if str(error)!='interrupted' or not self.stopped():raise
                    results.append({'library_id':library,'status':'cancelled'});break
                except Conflict:
                    results.append({'library_id':library,'status':'changed_retry'});continue
                results.append({'library_id':library,'status':'updated' if result['changed'] else 'unchanged',**result})
        return results
