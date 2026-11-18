import unittest

from fastapi.testclient import TestClient

from app.main import app


class HealthTest(unittest.TestCase):
    def test_health_endpoint_reports_service_is_alive(self):
        response = TestClient(app).get('/api/v1/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_pet_write_is_not_exposed_before_authentication_exists(self):
        response = TestClient(app).post('/api/v1/pets', json={'name': '团团'})
        self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
