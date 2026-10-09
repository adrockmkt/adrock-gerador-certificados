import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.auth.service import create_admin, reset_password
from app.models import Admin
from sqlalchemy import select


class AuthFlowTests(unittest.TestCase):
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

    def tearDown(self):
        self.app.extensions["db_engine"].dispose()
        self.temp_dir.cleanup()

    def csrf(self):
        self.client.get("/login")
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def login(self, password="safe-password-123"):
        return self.client.post("/login", data={
            "username": "admin",
            "password": password,
            "csrf_token": self.csrf(),
        })

    def test_private_home_requires_login(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)

    def test_admin_can_login_and_logout(self):
        response = self.login()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 200)
        response = self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_wrong_password_does_not_authenticate(self):
        response = self.login("wrong-password")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_unknown_user_gets_same_generic_error(self):
        response = self.client.post("/login", data={
            "username": "unknown",
            "password": "wrong-password",
            "csrf_token": self.csrf(),
        })
        self.assertEqual(response.status_code, 401)
        self.assertIn(b"Usu\xc3\xa1rio ou senha inv\xc3\xa1lidos", response.data)

    def test_login_page_has_security_headers(self):
        response = self.client.get("/login")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_csrf_is_required_for_login_and_logout(self):
        response = self.client.post("/login", data={"username": "admin", "password": "safe-password-123"})
        self.assertEqual(response.status_code, 400)
        self.login()
        response = self.client.post("/logout")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_repeated_failures_are_limited(self):
        for _ in range(5):
            self.assertEqual(self.login("wrong-password").status_code, 401)
        self.assertEqual(self.login().status_code, 429)

    def test_session_cookie_has_sensible_security_settings(self):
        self.assertTrue(self.app.config["SESSION_COOKIE_HTTPONLY"])
        self.assertEqual(self.app.config["SESSION_COOKIE_SAMESITE"], "Lax")
        self.assertEqual(self.app.config["PERMANENT_SESSION_LIFETIME"].total_seconds(), 3600)

    def test_reverse_proxy_prefix_keeps_links_and_cookie_under_subpath(self):
        self.app.config["APPLICATION_ROOT"] = "/gerador-certificados"
        headers = {
            "Host": "mobiledelivery.com.br",
            "X-Forwarded-Prefix": "/gerador-certificados",
            "X-Forwarded-Proto": "https",
        }
        response = self.client.get("/login", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'/gerador-certificados/static/app.css', response.data)
        self.assertIn(b'/gerador-certificados/login', response.data)
        self.assertIn("Path=/gerador-certificados", response.headers["Set-Cookie"])
        home = self.client.get("/", headers=headers)
        self.assertEqual(home.location, "/gerador-certificados/login")

    def test_expired_session_requires_login_again(self):
        self.login()
        self.app.config["PERMANENT_SESSION_LIFETIME"] = -1
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_admin_password_is_hashed_and_second_admin_is_rejected(self):
        with self.app.extensions["db_sessionmaker"]() as db:
            admin = db.scalar(select(Admin))
            self.assertNotEqual(admin.password_hash, "safe-password-123")
            self.assertTrue(admin.password_hash.startswith("pbkdf2:sha256:"))
        with self.assertRaises(ValueError):
            create_admin(self.app, "second", "another-safe-password")

    def test_password_can_be_reset_locally_without_email(self):
        self.assertEqual(self.login().status_code, 302)
        reset_password(self.app, "admin", "new-safe-password")
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertEqual(self.login().status_code, 401)
        self.assertEqual(self.login("new-safe-password").status_code, 302)


if __name__ == "__main__":
    unittest.main()
