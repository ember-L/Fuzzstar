import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, User
from app.services.sessions import create_session, rotate_refresh_token


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.db.add(User(id=1, nickname='测试'))
        self.db.commit()
        self.now = datetime(2026, 11, 18)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_rotation_replay_revokes_only_its_session_chain(self):
        first = create_session(self.db, 1, self.now)
        other = create_session(self.db, 1, self.now)
        self.db.commit()
        rotated = rotate_refresh_token(self.db, first, self.now + timedelta(minutes=1))
        self.assertIsNotNone(rotated)
        self.db.commit()
        self.assertIsNone(rotate_refresh_token(self.db, first, self.now + timedelta(minutes=2)))
        self.db.commit()
        self.db.close()
        self.db = Session(self.engine, expire_on_commit=False)
        self.assertIsNone(rotate_refresh_token(self.db, rotated, self.now + timedelta(minutes=3)))
        self.assertIsNotNone(rotate_refresh_token(self.db, other, self.now + timedelta(minutes=3)))

    def test_expired_unknown_and_inactive_user_are_rejected(self):
        expired = create_session(self.db, 1, self.now)
        inactive = create_session(self.db, 1, self.now)
        self.db.commit()
        self.assertIsNone(rotate_refresh_token(self.db, 'unknown', self.now))
        self.assertIsNone(rotate_refresh_token(self.db, expired, self.now + timedelta(days=30)))
        self.db.get(User, 1).status = 'deleted'
        self.db.commit()
        self.assertIsNone(rotate_refresh_token(self.db, inactive, self.now + timedelta(minutes=1)))

    def test_refresh_tokens_are_not_stored_in_plaintext(self):
        from app.models import RefreshToken

        token = create_session(self.db, 1, self.now)
        self.db.commit()
        record = self.db.scalar(select(RefreshToken))
        self.assertNotEqual(record.token_hash, token)
        self.assertEqual(len(record.token_hash), 64)
