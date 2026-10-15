"""Durable-store checks for private pending search clarification state."""
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.assistant_workspace_store import (  # noqa: E402
    RETENTION_SECONDS,
    WorkspaceStoreConflict,
    WorkspaceStoreMissing,
    initialize_v2,
)
from app.access.search_pending import (  # noqa: E402
    PENDING_TTL_SECONDS, find_date_slot, make_pending,
)


def new_id():
    return str(uuid.uuid4())


def pending_for(query, created_at):
    slot = find_date_slot(query, {'labels': [], 'enabled': ['date']},
                          datetime(2032, 9, 14, 12, 0))
    if slot is None:
        raise AssertionError('expected one eligible vague-date slot')
    return make_pending(query, slot, 'a' * 64, created_at)


def search_context(library='family-a'):
    return {
        'library_id': library,
        'binding': 'b' * 64,
        'fingerprint': 'c' * 64,
        'filters': {'media': ['photo']},
        'visible_ids': ['103', '104'],
        'total': 2,
        'search_version': 3,
    }


def clarification(pending, *, reply='Which year do you mean?', context=None):
    return {
        'version': 3, 'kind': 'clarification', 'reply': reply,
        'context': context, 'filters': None, 'total': 0,
        'has_more': False, 'effect': None,
        'pending_intent': pending,
    }


def result_summary(*, kind='results', context=None):
    if context is None and kind in ('results', 'open'):
        context = search_context()
    return {
        'version': 3, 'kind': kind, 'reply': 'Stored response.',
        'context': context,
        'filters': None if context is None else context['filters'],
        'total': 0 if context is None else context['total'],
        'has_more': False, 'effect': None,
    }


class AssistantPendingIntentStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name).resolve() / 'turns.sqlite'
        self.now = [1_800_000_000]
        self.store = initialize_v2(self.path, clock=lambda: self.now[0])
        self.account = 'member-a'
        self.library = 'family-a'
        self.thread = self.store.create_thread(self.account, self.library)['thread_id']

    def begin(self, *, thread=None, account=None, library=None, request=None,
              revision=0, text='Find photos from childhood'):
        return self.store.begin_turn(
            self.account if account is None else account,
            self.library if library is None else library,
            self.thread if thread is None else thread,
            new_id() if request is None else request,
            revision, text,
        )

    def complete(self, pending_turn, summary):
        return self.store.complete_turn(
            self.account, self.library, self.thread,
            pending_turn['request_id'], pending_turn['lease_id'], summary,
            cards=[], receipts=[],
        )

    def test_pending_metadata_round_trips_and_reads_replay_saved_result(self):
        query = 'Find photos from childhood'
        first = self.begin(text=query)
        pending = pending_for(query, self.now[0])
        done = self.complete(first, clarification(pending))
        self.assertEqual(done['result_summary']['pending_intent'], pending)

        fetched = self.store.get_turn(self.account, self.library, self.thread,
                                      first['request_id'])
        replay = self.begin(request=first['request_id'], text=query)
        self.assertEqual(fetched['result_summary'], done['result_summary'])
        self.assertEqual(replay['result_summary'], done['result_summary'])
        self.assertNotIn('pending_intent', fetched)
        self.assertNotIn('pending_intent', replay)

        followup = self.begin(revision=1, text='2020')
        self.assertEqual(followup['pending_intent'], pending)

    def test_pending_intent_is_only_valid_on_v3_contextless_clarification(self):
        turn = self.begin()
        pending = pending_for('Find photos from childhood', self.now[0])
        invalid = (
            dict(clarification(pending), version=1),
            dict(clarification(pending), version=2),
            dict(clarification(pending), kind='results'),
            clarification(pending, context=search_context()),
        )
        for value in invalid:
            with self.subTest(version=value['version'], kind=value['kind'],
                              context=value['context'] is not None):
                with self.assertRaises(ValueError):
                    self.complete(turn, value)

    def test_pending_is_bound_to_immediately_previous_thread_scope_and_revision(self):
        query = 'Find photos from childhood'
        first = self.begin(text=query)
        pending = pending_for(query, self.now[0])
        self.complete(first, clarification(pending))

        with self.assertRaises(WorkspaceStoreConflict):
            self.begin(revision=0, text='2020')

        other_thread = self.store.create_thread(self.account, self.library)['thread_id']
        other = self.begin(thread=other_thread, revision=0, text='2020')
        self.assertNotIn('pending_intent', other)

        other_library_thread = self.store.create_thread(self.account, 'family-b')['thread_id']
        with self.assertRaises(WorkspaceStoreMissing):
            self.begin(thread=other_library_thread, library=self.library, text='2020')
        other_library_turn = self.store.begin_turn(
            self.account, 'family-b', other_library_thread, new_id(), 0, '2020')
        self.assertNotIn('pending_intent', other_library_turn)

    def test_completed_intervening_exchange_clears_pending_state(self):
        first = self.begin()
        pending = pending_for('Find photos from childhood', self.now[0])
        self.complete(first, clarification(pending))

        answer = self.begin(revision=1, text='2020')
        self.assertEqual(answer['pending_intent'], pending)
        self.complete(answer, result_summary(kind='unsupported', context=None))

        next_turn = self.begin(revision=2, text='Find more photos')
        self.assertNotIn('pending_intent', next_turn)

    def test_expired_pending_is_returned_for_expiry_explanation_but_not_committable(self):
        first = self.begin()
        pending = pending_for('Find photos from childhood', self.now[0])
        self.complete(first, clarification(pending))

        self.now[0] += PENDING_TTL_SECONDS + 1
        self.assertLess(PENDING_TTL_SECONDS + 1, RETENTION_SECONDS)
        answer = self.begin(revision=1, text='2020')
        self.assertEqual(answer['pending_intent'], pending)
        with self.assertRaises(WorkspaceStoreConflict):
            self.complete(answer, clarification(pending))

    def test_future_or_pre_request_pending_state_cannot_be_committed(self):
        query = 'Find photos from childhood'
        first = self.begin(text=query)
        wrong_query = pending_for('Find photos about childhood', self.now[0])
        with self.assertRaises(WorkspaceStoreConflict):
            self.complete(first, clarification(wrong_query))
        too_old = pending_for(query, self.now[0] - 1)
        with self.assertRaises(WorkspaceStoreConflict):
            self.complete(first, clarification(too_old))

        future_thread = self.store.create_thread(self.account, self.library)['thread_id']
        future = self.begin(thread=future_thread, text=query)
        future_pending = pending_for(query, self.now[0] + 1)
        with self.assertRaises(WorkspaceStoreConflict):
            self.store.complete_turn(self.account, self.library, future_thread,
                                     future['request_id'], future['lease_id'],
                                     clarification(future_pending), cards=[], receipts=[])

    def test_invalid_answer_can_carry_only_exact_prior_pending_without_extending_ttl(self):
        query = 'Find photos from childhood'
        first = self.begin(text=query)
        pending = pending_for(query, self.now[0])
        self.complete(first, clarification(pending))

        self.now[0] += 300
        answer = self.begin(revision=1, text='not a date')
        self.assertEqual(answer['pending_intent'], pending)
        carried = self.complete(answer, clarification(pending, reply='Please give a year.'))
        self.assertEqual(carried['result_summary']['pending_intent'], pending)
        self.assertEqual(carried['result_summary']['pending_intent']['created_at'],
                         self.now[0] - 300)

        self.now[0] += 300
        next_answer = self.begin(revision=2, text='still not a date')
        self.assertEqual(next_answer['pending_intent'], pending)

        replacement_thread = self.store.create_thread(self.account, self.library)['thread_id']
        original = self.begin(thread=replacement_thread, text=query)
        original_pending = pending_for(query, self.now[0])
        self.store.complete_turn(self.account, self.library, replacement_thread,
                                 original['request_id'], original['lease_id'],
                                 clarification(original_pending), cards=[], receipts=[])
        bad_answer = self.begin(thread=replacement_thread, revision=1, text='not a date')
        replacement = pending_for('Find photos about childhood', original_pending['created_at'])
        with self.assertRaises(WorkspaceStoreConflict):
            self.store.complete_turn(self.account, self.library, replacement_thread,
                                     bad_answer['request_id'], bad_answer['lease_id'],
                                     clarification(replacement), cards=[], receipts=[])


if __name__ == '__main__':
    unittest.main()
