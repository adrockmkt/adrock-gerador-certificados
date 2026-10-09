import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.auth.service import create_admin


class ClientEventTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database = Path(self.temp_dir.name) / "test.sqlite3"
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-secret",
            "DATABASE_URL": f"sqlite:///{database}",
        })
        self.client = self.app.test_client()
        create_admin(self.app, "admin", "safe-password-123")
        self.client.get("/login")
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        self.client.post("/login", data={"username": "admin", "password": "safe-password-123", "csrf_token": token})

    def tearDown(self):
        self.app.extensions["db_engine"].dispose()
        self.temp_dir.cleanup()

    def csrf(self):
        self.client.get("/")
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def test_client_can_be_created_and_listed(self):
        response = self.client.post("/clients", data={"name": "FIEP", "csrf_token": self.csrf()})
        self.assertEqual(response.status_code, 302)
        listing = self.client.get("/clients")
        self.assertIn(b"FIEP", listing.data)

    def test_event_belongs_to_selected_client(self):
        self.client.post("/clients", data={"name": "FIEP", "csrf_token": self.csrf()})
        response = self.client.post("/clients/1/events", data={
            "title": "Curso de GA4 e GTM", "csrf_token": self.csrf(),
        })
        self.assertEqual(response.status_code, 302)
        detail = self.client.get("/clients/1")
        self.assertIn("Curso de GA4 e GTM".encode(), detail.data)

    def test_empty_names_and_missing_client_are_rejected(self):
        self.assertEqual(self.client.post("/clients", data={"name": "  ", "csrf_token": self.csrf()}).status_code, 400)
        self.assertEqual(self.client.post("/clients/999/events", data={"title": "Evento", "csrf_token": self.csrf()}).status_code, 404)

    def test_creating_client_or_event_requires_csrf(self):
        self.assertEqual(self.client.post("/clients", data={"name": "FIEP"}).status_code, 400)
        self.client.post("/clients", data={"name": "FIEP", "csrf_token": self.csrf()})
        self.assertEqual(self.client.post("/clients/1/events", data={"title": "Curso"}).status_code, 400)

    def test_private_routes_require_authentication(self):
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.assertEqual(self.client.get("/clients").status_code, 302)
        self.assertEqual(self.client.get("/clients/1").status_code, 302)


if __name__ == "__main__":
    unittest.main()
