"""CPU-only contract tests for the unwired inference admission primitive."""
import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER / 'backend'))

from app.access.inference_admission import (AdmissionError, AdmissionIdentity,
    InferenceAdmission)


def identity(account, request, *, library='family', profile='story', digest='a'):
    return AdmissionIdentity(account, library, request, profile, digest * 64)


class InferenceAdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def wait_for_waiters(self, admission, count):
        async def ready():
            while admission.state().waiting != count:
                await asyncio.sleep(0)
        await asyncio.wait_for(ready(), 1)

    async def assert_reason(self, awaitable, reason):
        with self.assertRaises(AdmissionError) as caught:
            await asyncio.wait_for(awaitable, 1)
        self.assertEqual(caught.exception.reason, reason)

    async def test_one_permit_fifo_across_profiles_accounts_and_libraries(self):
        admission = InferenceAdmission()
        active = await admission.acquire(identity('owner', 'active'))
        order = [identity('a', 'a1', library='lib-a', profile='story'),
                 identity('b', 'b1', library='lib-b', profile='assistant'),
                 identity('c', 'c1', library='lib-c', profile='story'),
                 identity('d', 'd1', library='lib-d', profile='assistant')]
        tasks = [asyncio.create_task(admission.acquire(item)) for item in order]
        await self.wait_for_waiters(admission, 4)
        await self.assert_reason(admission.acquire(identity('e', 'e1')),
                                 'waiting_full')
        await self.assert_reason(admission.acquire(identity('fast', 'f1'), wait=False),
                                 'busy')

        granted = []
        for expected in order:
            active.finish(reconciled=True)
            active = await asyncio.wait_for(tasks[len(granted)], 1)
            granted.append(active.identity)
            self.assertEqual(active.identity, expected)
        active.finish(reconciled=True)
        self.assertEqual(admission.state().active, 0)
        self.assertEqual(admission.state().waiting, 0)

    async def test_one_waiter_per_account_across_libraries_and_profiles(self):
        admission = InferenceAdmission()
        active = await admission.acquire(identity('active', 'one'))
        task = asyncio.create_task(admission.acquire(
            identity('same-account', 'first', library='lib-a', profile='story')))
        await self.wait_for_waiters(admission, 1)
        await self.assert_reason(admission.acquire(
            identity('same-account', 'second', library='lib-b', profile='assistant')),
            'account_waiting')
        active.finish(reconciled=True)
        permit = await asyncio.wait_for(task, 1)
        self.assertEqual(permit.identity.request_id, 'first')
        permit.finish(reconciled=True)

    async def test_duplicate_owned_and_conflicting_request_are_distinct(self):
        admission = InferenceAdmission()
        active = await admission.acquire(identity('a', 'active'))
        queued = identity('b', 'request')
        task = asyncio.create_task(admission.acquire(queued))
        await self.wait_for_waiters(admission, 1)
        await self.assert_reason(admission.acquire(queued), 'duplicate_owned')
        conflict = AdmissionIdentity('b', 'family', 'request', 'assistant', 'b' * 64)
        await self.assert_reason(admission.acquire(conflict), 'request_conflict')
        active.finish(reconciled=True)
        permit = await asyncio.wait_for(task, 1)
        permit.finish(reconciled=True)

    async def test_expiration_releases_account_and_request_identity(self):
        admission = InferenceAdmission(wait_seconds=20)
        active = await admission.acquire(identity('owner', 'active'))
        expired = identity('member', 'request', library='lib-a')
        expiry = asyncio.create_task(admission.acquire(expired))
        await self.wait_for_waiters(admission, 1)
        # Deliver the scheduled expiry callback explicitly. The replacement
        # below must not have to beat a 10 ms wall-clock window on a busy host.
        admission._expire(admission._waiting[0])
        await self.assert_reason(expiry, 'waiting_expired')
        self.assertEqual(admission.state().waiting, 0)
        # Same account may wait again, and the expired request key is reusable.
        replacement_identity = identity('member', 'next', library='lib-b', profile='assistant')
        replacement = asyncio.create_task(admission.acquire(replacement_identity))
        await self.wait_for_waiters(admission, 1)
        active.finish(reconciled=True)
        permit = await asyncio.wait_for(replacement, 1)
        permit.finish(reconciled=True)
        retry = await admission.acquire(expired)
        retry.finish(reconciled=True)

    async def test_cancelled_waiter_is_removed_and_frees_account_and_key(self):
        admission = InferenceAdmission()
        active = await admission.acquire(identity('owner', 'active'))
        canceled_identity = identity('member', 'request')
        waiter = asyncio.create_task(admission.acquire(canceled_identity))
        await self.wait_for_waiters(admission, 1)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(waiter, 1)
        self.assertEqual(admission.state().waiting, 0)
        replacement = asyncio.create_task(admission.acquire(
            identity('member', 'request-2', library='other-library')))
        await self.wait_for_waiters(admission, 1)
        active.finish(reconciled=True)
        permit = await asyncio.wait_for(replacement, 1)
        permit.finish(reconciled=True)
        retry = await admission.acquire(canceled_identity)
        retry.finish(reconciled=True)

    async def test_promotion_rejects_overdue_waiter_before_timer_callback_runs(self):
        admission = InferenceAdmission(wait_seconds=20)
        active = await admission.acquire(identity('owner', 'active'))
        waiting = asyncio.create_task(admission.acquire(identity('member', 'wait')))
        await self.wait_for_waiters(admission, 1)
        loop = asyncio.get_running_loop()
        # No yield while time is advanced: the scheduled expiry callback cannot
        # run, so promotion itself must enforce the original deadline.
        with patch.object(loop, 'time', return_value=loop.time() + 21):
            active.finish(reconciled=True)
        await self.assert_reason(waiting, 'waiting_expired')
        self.assertEqual(admission.state().active, 0)
        next_permit = await admission.acquire(identity('member', 'next'))
        next_permit.finish(reconciled=True)

    async def test_zero_wait_capacity_and_read_only_limits_and_permit_identity(self):
        admission = InferenceAdmission(max_waiting=0)
        active = await admission.acquire(identity('owner', 'active'))
        await self.assert_reason(admission.acquire(identity('member', 'wait')), 'waiting_full')
        for field, value in (('max_waiting', 1000), ('wait_seconds', 1000)):
            with self.assertRaises(AttributeError):
                setattr(admission, field, value)
        with self.assertRaises(AttributeError):
            active.identity = identity('other', 'changed')
        active.finish(reconciled=True)

    async def test_cancel_after_promotion_before_acquire_returns_reclaims_permit(self):
        admission = InferenceAdmission()
        active = await admission.acquire(identity('owner', 'active'))
        promoted = asyncio.create_task(admission.acquire(identity('first', 'wait')))
        following = asyncio.create_task(admission.acquire(identity('second', 'wait')))
        await self.wait_for_waiters(admission, 2)

        # finish() promotes synchronously; cancel before the event loop can resume
        # the acquire task, exercising the handoff window without a timing race.
        active.finish(reconciled=True)
        promoted.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(promoted, 1)
        permit = await asyncio.wait_for(following, 1)
        self.assertEqual(permit.identity.account_id, 'second')
        self.assertEqual(admission.state().active, 1)
        permit.finish(reconciled=True)

    async def test_cancel_after_acquire_returns_retains_permit_until_finish(self):
        admission = InferenceAdmission()
        active = await admission.acquire(identity('owner', 'active'))
        acquired = asyncio.Event()
        holder = {}

        async def operation_owner():
            holder['permit'] = await admission.acquire(identity('member', 'wait'))
            acquired.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(operation_owner())
        await self.wait_for_waiters(admission, 1)
        active.finish(reconciled=True)
        await asyncio.wait_for(acquired.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        self.assertEqual(admission.state().active, 1)
        await self.assert_reason(admission.acquire(identity('new', 'fresh'), wait=False),
                                 'busy')
        holder['permit'].finish(reconciled=True)

    async def test_stale_double_finish_cannot_release_next_owner(self):
        admission = InferenceAdmission()
        first = await admission.acquire(identity('first', 'active'))
        second_task = asyncio.create_task(admission.acquire(identity('second', 'wait')))
        third_task = asyncio.create_task(admission.acquire(identity('third', 'wait')))
        await self.wait_for_waiters(admission, 2)
        self.assertTrue(first.finish(reconciled=True))
        second = await asyncio.wait_for(second_task, 1)
        self.assertFalse(first.finish(reconciled=True))
        self.assertEqual(admission.state().active, 1)
        self.assertEqual(admission.state().waiting, 1)
        await self.assert_reason(admission.acquire(identity('fresh', 'request'), wait=False),
                                 'busy')
        second.finish(reconciled=True)
        third = await asyncio.wait_for(third_task, 1)
        third.finish(reconciled=True)

    async def test_close_rejects_waiting_and_fresh_but_keeps_active(self):
        admission = InferenceAdmission()
        active = await admission.acquire(identity('owner', 'active'))
        waiter = asyncio.create_task(admission.acquire(identity('member', 'wait')))
        await self.wait_for_waiters(admission, 1)
        admission.close()
        await self.assert_reason(waiter, 'closed')
        await self.assert_reason(admission.acquire(identity('new', 'request')),
                                 'closed')
        self.assertEqual(admission.state().active, 1)
        self.assertEqual(admission.state().waiting, 0)
        self.assertTrue(active.finish(reconciled=True))
        self.assertEqual(admission.state().active, 0)

    async def test_uncertain_cleanup_quarantines_and_later_settlement_stays_quarantined(self):
        admission = InferenceAdmission()
        active = await admission.acquire(identity('owner', 'active'))
        waiter = asyncio.create_task(admission.acquire(identity('member', 'wait')))
        await self.wait_for_waiters(admission, 1)
        self.assertFalse(active.finish(reconciled=False))
        await self.assert_reason(waiter, 'quarantined')
        await self.assert_reason(admission.acquire(identity('new', 'request')),
                                 'quarantined')
        self.assertEqual(admission.state().active, 1)
        self.assertTrue(active.finish(reconciled=True))
        state = admission.state()
        self.assertEqual(state.active, 0)
        self.assertTrue(state.quarantined)
        await self.assert_reason(admission.acquire(identity('later', 'request')),
                                 'quarantined')

    async def test_constructor_rejects_invalid_caps_and_deadlines(self):
        for kwargs in ({'max_waiting': -1}, {'max_waiting': 5},
                       {'max_waiting': True}, {'wait_seconds': 0},
                       {'wait_seconds': 20.01}, {'wait_seconds': float('nan')},
                       {'wait_seconds': 10**400},
                       {'wait_seconds': True}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    InferenceAdmission(**kwargs)

    async def test_identity_validation_is_closed_and_digest_is_sha256(self):
        for values in (('', 'lib', 'req', 'story', 'a' * 64),
                       ('acct', 'lib', 'req', 'story', 'A' * 64),
                       ('acct', 'lib', 'req', 'story', 'a' * 63),
                       ('acct\n', 'lib', 'req', 'story', 'a' * 64),
                       ('acct\ud800', 'lib', 'req', 'story', 'a' * 64)):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    AdmissionIdentity(*values)

    async def test_cross_event_loop_use_is_rejected(self):
        admission = InferenceAdmission()
        active = await admission.acquire(identity('owner', 'active'))
        result = await asyncio.wait_for(asyncio.to_thread(
            lambda: asyncio.run(self._state_on_new_loop(admission))), 1)
        self.assertEqual(result, 'admission_event_loop_mismatch')
        active.finish(reconciled=True)

    @staticmethod
    async def _state_on_new_loop(admission):
        try:
            admission.state()
        except RuntimeError as error:
            return str(error)
        return 'accepted'


if __name__ == '__main__':
    unittest.main()
