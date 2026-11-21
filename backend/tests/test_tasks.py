from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest import TestCase

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, User
from app.services.pets import PetInput, create_pet
from app.services.tasks import claim_task, enqueue_task, finish_task, requeue_task


class TaskTests(TestCase):
    def setUp(self):
        url = environ.get('TASK_TEST_DATABASE_URL')
        local = not url
        if local:
            directory = TemporaryDirectory()
            self.addCleanup(directory.cleanup)
            url = 'sqlite:///' + str(Path(directory.name) / 'tasks.db')
        self.engine = create_engine(url, hide_parameters=True)
        self.addCleanup(self.engine.dispose)
        if local:
            Base.metadata.create_all(self.engine)
        with Session(self.engine) as db, db.begin():
            owner = User(nickname='测试')
            db.add(owner)
            db.flush()
            self.pet = create_pet(db, owner.id, PetInput(name='团团')).id

    def enqueue(self, db, key='upload-1', payload=None):
        return enqueue_task(db, self.pet, 'avatar_batch', key, {'media_id': 42} if payload is None else payload)

    def test_duplicate_submissions_share_one_task_and_conflicting_payload_is_rejected(self):
        def submit(_):
            with Session(self.engine) as db, db.begin():
                return self.enqueue(db).id

        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(submit, range(8)))
        self.assertEqual(len(set(ids)), 1)
        with Session(self.engine) as db, db.begin():
            with self.assertRaises(ValueError):
                self.enqueue(db, payload={'media_id': 43})
            self.assertNotEqual(self.enqueue(db, key='Upload-1').id, ids[0])

    def test_enqueue_rolls_back_with_business_transaction(self):
        with Session(self.engine) as db:
            abandoned = self.enqueue(db).id
            db.rollback()
        with Session(self.engine) as db, db.begin():
            self.assertNotEqual(self.enqueue(db).id, abandoned)

    def test_concurrent_claim_has_one_winner(self):
        with Session(self.engine) as db, db.begin():
            task_id = self.enqueue(db).id
        barrier = Barrier(4)

        def claim(_):
            with Session(self.engine) as db, db.begin():
                barrier.wait(timeout=5)
                return claim_task(db, task_id)

        with ThreadPoolExecutor(max_workers=4) as pool:
            claims = list(pool.map(claim, range(4)))
        self.assertEqual(claims.count(1), 1)
        self.assertEqual(claims.count(None), 3)

    def test_claim_and_retry_do_not_allow_stale_completion(self):
        with Session(self.engine) as db, db.begin():
            task_id = self.enqueue(db).id
            for attempt in range(1, 4):
                self.assertEqual(claim_task(db, task_id), attempt)
                self.assertIsNone(claim_task(db, task_id))
                self.assertFalse(finish_task(db, task_id, attempt - 1, result={'stale': True}))
                self.assertTrue(finish_task(db, task_id, attempt))
                saved = self.enqueue(db)
                self.assertEqual(saved.status, 'pending' if attempt < 3 else 'failed')
                self.assertEqual(saved.attempts, attempt)
                self.assertIsNone(saved.result)
            self.assertIsNone(claim_task(db, task_id))

    def test_expired_claims_are_recoverable_and_last_expiry_is_terminal(self):
        now = datetime(2026, 11, 18)
        with Session(self.engine) as db, db.begin():
            task_id = self.enqueue(db).id
        for attempt in range(1, 4):
            with Session(self.engine) as db, db.begin():
                self.assertEqual(claim_task(db, task_id, now=now), attempt)
                self.assertIsNone(claim_task(db, task_id, now=now))
                if attempt > 1:
                    self.assertFalse(finish_task(db, task_id, attempt - 1, {'late': True}, now=now))
            now += timedelta(minutes=15)
        with Session(self.engine) as db, db.begin():
            self.assertFalse(finish_task(db, task_id, 3, {'late': True}, now=now))
            self.assertIsNone(claim_task(db, task_id, now=now))
            self.assertEqual(self.enqueue(db).status, 'failed')

    def test_requeue_resets_only_failed_tasks(self):
        with Session(self.engine) as db, db.begin():
            task_id = self.enqueue(db).id
            for attempt in range(1, 4):
                self.assertEqual(claim_task(db, task_id), attempt)
                self.assertTrue(finish_task(db, task_id, attempt))
            self.assertEqual(self.enqueue(db).status, 'failed')
            self.assertTrue(requeue_task(db, task_id))
            saved = self.enqueue(db)
            self.assertEqual((saved.status, saved.attempts), ('pending', 0))
            self.assertIsNone(saved.lease_until)
            self.assertIsNone(saved.result)
            self.assertFalse(requeue_task(db, task_id))

    def test_success_keeps_result_and_prevents_another_claim(self):
        with Session(self.engine) as db, db.begin():
            task_id = self.enqueue(db).id
            attempt = claim_task(db, task_id)
            self.assertTrue(finish_task(db, task_id, attempt, result={'clips': []}))
            self.assertFalse(finish_task(db, task_id, attempt))
        with Session(self.engine) as db, db.begin():
            self.assertIsNone(claim_task(db, task_id))
            self.assertEqual(self.enqueue(db).result, {'clips': []})
            self.assertEqual(self.enqueue(db).status, 'succeeded')
