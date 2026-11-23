import unittest
from datetime import date

from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import Base, Pet, User
from app.services.pets import PetInput, PetLimitReached, PetNotFound, create_pet, delete_pet, get_pet, list_pets, update_pet


class PetServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.session.add_all([User(id=1, nickname='甲'), User(id=2, nickname='乙')])
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_pet_is_persisted_and_unknown_birthday_is_null(self):
        pet = create_pet(self.session, 1, PetInput(name='团团', birth_date=None))
        self.session.commit()
        self.session.expire_all()
        saved = get_pet(self.session, 1, pet.id)
        self.assertEqual((saved.name, saved.species, saved.birth_date), ('团团', 'cat', None))

    def test_isolation_and_soft_delete(self):
        pet = create_pet(self.session, 1, PetInput(name='团团'))
        self.session.commit()
        self.assertEqual(list_pets(self.session, 2), [])
        with self.assertRaises(PetNotFound):
            update_pet(self.session, 2, pet.id, PetInput(name='别人的猫'))
        delete_pet(self.session, 1, pet.id)
        self.session.commit()
        self.assertEqual(list_pets(self.session, 1), [])
        self.assertEqual(self.session.execute(select(Pet).where(Pet.id == pet.id)).scalar_one().status, 'deleted')
        with self.assertRaises(PetNotFound):
            get_pet(self.session, 1, pet.id)

    def test_limit_counts_only_active_pets_per_owner(self):
        pets = [create_pet(self.session, 1, PetInput(name=f'猫{i}')) for i in range(5)]
        self.session.commit()
        with self.assertRaises(PetLimitReached):
            create_pet(self.session, 1, PetInput(name='第六只'))
        create_pet(self.session, 2, PetInput(name='另一只'))
        delete_pet(self.session, 1, pets[0].id)
        create_pet(self.session, 1, PetInput(name='新猫'))
        self.session.commit()
        self.assertEqual(len(list_pets(self.session, 1)), 5)

    def test_profile_input_rejects_invalid_values(self):
        for values in ({'name': '   '}, {'name': '猫' * 65}, {'name': '猫', 'sex': 'other'},
                       {'name': '猫', 'birth_date': date(2999, 1, 1)}, {'name': '猫', 'species': 'dog'}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                PetInput(**values)

    def test_update_changes_profile_without_changing_owner(self):
        pet = create_pet(self.session, 1, PetInput(name='团团'))
        updated = update_pet(self.session, 1, pet.id, PetInput(name='小团', neutered=True))
        self.session.commit()
        self.assertEqual((updated.name, updated.neutered, updated.user_id), ('小团', True, 1))

    def test_rollback_does_not_persist_a_pet(self):
        create_pet(self.session, 1, PetInput(name='未保存'))
        self.session.rollback()
        self.assertEqual(list_pets(self.session, 1), [])

    def test_deleted_or_missing_owner_cannot_create_pets(self):
        owner = self.session.get(User, 1)
        owner.status = 'deleted'
        self.session.commit()
        for owner_id in (1, 999):
            with self.subTest(owner_id=owner_id), self.assertRaises(PetNotFound):
                create_pet(self.session, owner_id, PetInput(name='团团'))


if __name__ == '__main__':
    unittest.main()
