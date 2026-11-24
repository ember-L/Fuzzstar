import unittest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.models import Base, ChatMessage, DietRecord, HealthScreening, Pet, User, WeightRecord
from scripts.seed_demo import DEMO_EMAIL, DEMO_PASSWORD, seed_demo


class SeedDemoTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.settings = Settings.from_env(
            {
                'DATABASE_URL': 'sqlite://',
                'JWT_SECRET': 'test-signing-key-32-bytes-or-more',
                'PRIVACY_VERSION': 'p1',
                'TERMS_VERSION': 't1',
                'PRIVACY_URL': 'https://example.com/privacy',
                'TERMS_URL': 'https://example.com/terms',
            }
        )

    def tearDown(self):
        self.engine.dispose()

    def _count(self, model):
        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(model))

    def test_seed_creates_complete_demo_account_and_is_idempotent(self):
        with Session(self.engine) as session:
            first = seed_demo(session, self.settings)
            session.commit()
        self.assertEqual(first['email'], DEMO_EMAIL)
        self.assertEqual(self._count(User), 1)
        self.assertEqual(self._count(Pet), 1)
        self.assertEqual(self._count(WeightRecord), 5)
        self.assertEqual(self._count(DietRecord), 4)
        self.assertEqual(self._count(HealthScreening), 1)
        self.assertEqual(self._count(ChatMessage), 4)

        with Session(self.engine) as session:
            second = seed_demo(session, self.settings)
            session.commit()
        self.assertEqual(second['created'], {'weights': 0, 'diet': 0, 'screenings': 0, 'chat_messages': 0})
        self.assertEqual(self._count(User), 1)
        self.assertEqual(self._count(WeightRecord), 5)
        self.assertEqual(self._count(DietRecord), 4)
        self.assertEqual(self._count(HealthScreening), 1)
        self.assertEqual(self._count(ChatMessage), 4)

        with Session(self.engine) as session:
            user = session.scalar(select(User).where(User.nickname == '团团的铲屎官'))
            pet = session.scalar(select(Pet).where(Pet.user_id == user.id))
            self.assertEqual((pet.name, pet.breed, pet.neutered), ('团团', '中华田园猫', True))
            self.assertEqual(DEMO_PASSWORD, 'Rongxing2026')


if __name__ == '__main__':
    unittest.main()
