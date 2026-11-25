import unittest
from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, UserCredential
from app.services.identity import (
    InvalidCredentials,
    create_email_account,
    login_email,
)


class EmailIdentityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.now = datetime(2026, 11, 18, 10, 0)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_account_is_usable_immediately_and_stores_argon2_hashes(self):
        user = create_email_account(self.session, 'Cat@Example.com', 'Strong123', self.now)
        self.session.commit()
        credential = self.session.scalar(select(UserCredential))
        self.assertNotEqual(credential.secret_hash, 'Strong123')
        self.assertTrue(credential.secret_hash.startswith('$argon2id$'))
        self.assertIsNotNone(credential.verified_at)
        self.assertEqual(login_email(self.session, 'cat@example.com', 'Strong123').id, user.id)
        with self.assertRaises(InvalidCredentials):
            login_email(self.session, 'cat@example.com', 'wrong123')

    def test_weak_password_is_rejected(self):
        with self.assertRaises(ValueError):
            create_email_account(self.session, 'cat@example.com', '12345678', self.now)

    def test_duplicate_and_invalid_email_rejected(self):
        create_email_account(self.session, 'CAT@example.com', 'Strong123', self.now)
        self.session.commit()
        with self.assertRaises(ValueError):
            create_email_account(self.session, 'cat@example.com', 'Strong123', self.now)
        with self.assertRaises(ValueError):
            create_email_account(self.session, 'not-an-email', 'Strong123', self.now)


if __name__ == '__main__':
    unittest.main()
