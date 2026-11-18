import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.identity import InvalidCredentials, InvalidVerification, create_email_account, login_email, verify_email
from app.models import Base, UserCredential


class EmailIdentityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.now = datetime(2026, 11, 18, 10, 0)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_requires_verified_email_before_login_and_stores_hashes(self):
        token = create_email_account(self.session, 'Cat@Example.com', 'Strong123', self.now)
        self.session.commit()
        credential = self.session.scalar(select(UserCredential))
        self.assertNotEqual(credential.secret_hash, 'Strong123')
        self.assertTrue(credential.secret_hash.startswith('$argon2id$'))
        self.assertNotEqual(credential.verification_hash, token)
        with self.assertRaises(InvalidCredentials):
            login_email(self.session, 'cat@example.com', 'Strong123')
        verify_email(self.session, token, self.now + timedelta(minutes=1))
        self.session.commit()
        self.assertEqual(login_email(self.session, 'cat@example.com', 'Strong123').id, credential.user_id)
        with self.assertRaises(InvalidCredentials):
            login_email(self.session, 'cat@example.com', 'wrong123')
        with self.assertRaises(InvalidVerification):
            verify_email(self.session, token, self.now + timedelta(minutes=2))

    def test_expired_link_and_weak_password_are_rejected(self):
        with self.assertRaises(ValueError):
            create_email_account(self.session, 'cat@example.com', '12345678', self.now)
        token = create_email_account(self.session, 'cat@example.com', 'Strong123', self.now)
        self.session.commit()
        with self.assertRaises(InvalidVerification):
            verify_email(self.session, token, self.now + timedelta(hours=24))
        with self.assertRaises(InvalidCredentials):
            login_email(self.session, 'cat@example.com', 'Strong123')

    def test_duplicate_and_invalid_email_rejected(self):
        create_email_account(self.session, 'CAT@example.com', 'Strong123', self.now)
        self.session.commit()
        with self.assertRaises(ValueError):
            create_email_account(self.session, 'cat@example.com', 'Strong123', self.now)
        with self.assertRaises(ValueError):
            create_email_account(self.session, 'not-an-email', 'Strong123', self.now)


if __name__ == '__main__':
    unittest.main()
