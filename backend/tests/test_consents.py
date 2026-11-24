import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, User
from app.services.consents import current_consents, grant_consent, has_required_consents


class ConsentTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.session.add(User(id=1, nickname='测试'))
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_requires_current_versions_and_training_defaults_off(self):
        self.assertFalse(has_required_consents(self.session, 1, 'v1', 'v1'))
        self.assertFalse(current_consents(self.session, 1).get('training', False))
        grant_consent(self.session, 1, 'privacy', 'v1', True)
        grant_consent(self.session, 1, 'terms', 'v1', True)
        self.session.commit()
        self.assertTrue(has_required_consents(self.session, 1, 'v1', 'v1'))
        self.assertFalse(has_required_consents(self.session, 1, 'v2', 'v1'))
        grant_consent(self.session, 1, 'privacy', 'v2', True)
        grant_consent(self.session, 1, 'training', 'v1', True)
        grant_consent(self.session, 1, 'training', 'v1', False)
        self.session.commit()
        self.assertTrue(has_required_consents(self.session, 1, 'v2', 'v1'))
        self.assertFalse(current_consents(self.session, 1)['training'])


if __name__ == '__main__':
    unittest.main()
