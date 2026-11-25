import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.models import MediaUpload, User
from app.services.consents import grant_consent, has_required_consents
from app.services.identity import create_email_account, login_email
from app.services.pets import PetInput, create_pet, list_pets
from app.services.sessions import create_session, rotate_refresh_token
from app.services.tasks import claim_task, enqueue_task, finish_task


class MigrationTests(unittest.TestCase):
    def test_upgrade_creates_persistent_tables_and_is_repeatable(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            url = 'sqlite:///' + str(Path(directory) / 'migration.db')
            env = {**os.environ, 'DATABASE_URL': url}
            for _ in range(2):
                subprocess.run(
                    [sys.executable, '-m', 'alembic', 'upgrade', 'head'],
                    cwd=root,
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            engine = create_engine(url)
            self.assertTrue(
                {
                    'users',
                    'pets',
                    'user_credentials',
                    'consents',
                    'auth_sessions',
                    'refresh_tokens',
                    'auth_rate_buckets',
                    'tasks',
                    'media_uploads',
                    'alembic_version',
                }
                <= set(inspect(engine).get_table_names())
            )
            with engine.connect() as connection:
                self.assertEqual(connection.execute(text('select count(*) from alembic_version')).scalar_one(), 1)
            with Session(engine) as session:
                session.add(User(id=1, nickname='测试'))
                session.commit()
                pet = create_pet(session, 1, PetInput(name='团团'))
                session.add(
                    MediaUpload(
                        id='a' * 32,
                        pet_id=pet.id,
                        content_type='image/png',
                        size_bytes=42,
                        expires_at=datetime(2026, 11, 18),
                    )
                )
                task_id = enqueue_task(session, pet.id, 'avatar_batch', 'photo-1', {}).id
                session.commit()
                attempt = claim_task(session, task_id)
                self.assertEqual(attempt, 1)
                self.assertTrue(finish_task(session, task_id, attempt, result={}))
                session.commit()
            with Session(engine) as session:
                self.assertEqual([pet.name for pet in list_pets(session, 1)], ['团团'])
                create_email_account(session, 'cat@example.com', 'Strong123', datetime(2026, 11, 18))
                user = login_email(session, 'cat@example.com', 'Strong123')
                grant_consent(session, user.id, 'privacy', 'v1', True)
                grant_consent(session, user.id, 'terms', 'v1', True)
                session.commit()
                self.assertTrue(has_required_consents(session, user.id, 'v1', 'v1'))
                refresh = create_session(session, user.id, datetime(2026, 11, 18))
                session.commit()
                self.assertIsNotNone(rotate_refresh_token(session, refresh, datetime(2026, 11, 18)))
                session.commit()
            engine.dispose()


if __name__ == '__main__':
    unittest.main()
