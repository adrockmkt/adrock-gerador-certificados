import io
import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.auth.service import create_admin
from app.models import PdfTemplate, TemplateVersion


class CsvImportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-secret",
            "DATABASE_URL": f"sqlite:///{root / 'test.sqlite3'}",
            "PRIVATE_STORAGE_DIR": str(root / "private"),
        })
        self.client = self.app.test_client()
        create_admin(self.app, "admin", "safe-password-123")
        self.client.get("/login")
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        self.client.post("/login", data={"username": "admin", "password": "safe-password-123", "csrf_token": token})
        self.client.get("/")
        with self.client.session_transaction() as session:
            self.token = session["csrf_token"]
        self.client.post("/clients", data={"name": "FIEP", "csrf_token": self.token})
        self.client.post("/clients/1/events", data={"title": "GA4", "csrf_token": self.token})

    def tearDown(self):
        self.app.extensions["db_engine"].dispose()
        self.temp_dir.cleanup()

    def upload(self, content):
        return self.client.post("/events/1/imports", data={
            "csv": (io.BytesIO(content), "participantes.csv"), "csrf_token": self.token,
        }, content_type="multipart/form-data")

    def test_csv_mapping_review_and_confirm(self):
        csv = "Nome,Sobrenome,Email\nMaria,Silva,maria@example.com\nJosé,Ávila,jose@example.com\n".encode()
        self.assertEqual(self.upload(csv).status_code, 302)
        mapping = self.client.get("/imports/1/map")
        self.assertIn(b"Nome", mapping.data)
        review = self.client.post("/imports/1/review", data={
            "first_col": "Nome", "last_col": "Sobrenome", "csrf_token": self.token,
        })
        self.assertEqual(review.status_code, 200)
        self.assertIn("José Ávila".encode(), review.data)
        confirm = self.client.post("/imports/1/confirm", data={
            "first_col": "Nome", "last_col": "Sobrenome", "csrf_token": self.token,
        })
        self.assertEqual(confirm.status_code, 302)
        listing = self.client.get("/events/1/participants")
        self.assertIn("José Ávila".encode(), listing.data)
        self.assertNotIn(b"jose@example.com", listing.data)
        self.assertIn(b"Pr\xc3\xb3ximo passo: associar um template PDF", listing.data)
        self.assertNotIn(b"Gerar certificados", listing.data)
        self.assertIn(b"Enviar template PDF", listing.data)
        generation = self.client.get("/events/1/generate")
        self.assertIn(b"Associar template", generation.data)
        self.assertEqual(self.client.post("/imports/1/confirm", data={
            "first_col": "Nome", "last_col": "Sobrenome", "csrf_token": self.token,
        }).status_code, 409)

    def test_participants_page_guides_template_association_and_configuration(self):
        self.upload(b"Nome,Sobrenome\nMaria,Silva\n")
        self.client.post("/imports/1/confirm", data={
            "first_col": "Nome", "last_col": "Sobrenome", "csrf_token": self.token,
        })
        with self.app.extensions["db_sessionmaker"]() as db:
            db.add(PdfTemplate(name="Certificado webinar", file_key="a" * 32 + ".pdf",
                               sha256="0" * 64, page_width_pt=842, page_height_pt=595, rotation=0))
            db.commit()

        page = self.client.get("/events/1/participants")
        self.assertIn(b"Certificado webinar", page.data)
        self.assertIn(b"Associar template", page.data)
        self.assertNotIn(b"Gerar certificados", page.data)
        association = self.client.post("/events/1/template", data={
            "template_id": "1", "return_to": "participants", "csrf_token": self.token,
        })
        self.assertEqual(association.status_code, 302)
        self.assertIn("/events/1/participants", association.location)

        page = self.client.get("/events/1/participants")
        self.assertIn(b"configurar o nome", page.data)
        self.assertIn(b"/templates/1/edit", page.data)
        self.assertNotIn(b"Gerar certificados", page.data)
        self.assertIn(b"Configurar nome no template", self.client.get("/events/1/generate").data)
        with self.app.extensions["db_sessionmaker"]() as db:
            db.add(TemplateVersion(template_id=1, number=1, fields=[{"key": "nome_completo"}]))
            db.commit()

        page = self.client.get("/events/1/participants")
        self.assertIn(b"Pronto para gerar", page.data)
        self.assertIn(b"Gerar certificados", page.data)
        self.assertIn(b"/events/1/generate", page.data)
        self.assertIn(b"Gerar 1 certificado", self.client.get("/events/1/generate").data)

    def test_duplicate_is_flagged_and_invalid_row_is_excluded(self):
        csv = "Nome,Sobrenome\nMaria,Silva\nMaria,Silva\n,SemNome\n".encode()
        self.upload(csv)
        review = self.client.post("/imports/1/review", data={
            "first_col": "Nome", "last_col": "Sobrenome", "csrf_token": self.token,
        })
        self.assertIn(b"Duplicidades poss\xc3\xadveis: 1", review.data)
        self.assertIn(b"Linhas inv\xc3\xa1lidas: 1", review.data)
        self.client.post("/imports/1/confirm", data={
            "first_col": "Nome", "last_col": "Sobrenome", "csrf_token": self.token,
        })
        listing = self.client.get("/events/1/participants")
        self.assertEqual(listing.data.count(b"Maria Silva"), 2)

    def test_invalid_encoding_and_missing_columns_are_rejected(self):
        self.assertEqual(self.upload(b"Nome,Sobrenome\n\xff,Silva\n").status_code, 400)
        self.upload(b"Nome,Sobrenome\nMaria,Silva\n")
        self.assertEqual(self.client.post("/imports/1/review", data={
            "first_col": "Nome", "last_col": "Inexistente", "csrf_token": self.token,
        }).status_code, 400)

    def test_import_routes_require_auth_and_csrf(self):
        response = self.client.post("/events/1/imports", data={
            "csv": (io.BytesIO(b"Nome,Sobrenome\nMaria,Silva\n"), "participants.csv"),
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)
        self.client.post("/logout", data={"csrf_token": self.token})
        self.assertEqual(self.client.get("/events/1/participants").status_code, 302)

    def test_spreadsheet_template_download_requires_login(self):
        page = self.client.get("/events/1/participants")
        self.assertIn(b"modelo-participantes.xlsx", page.data)
        self.assertNotIn(b"Gerar certificados", page.data)
        download = self.client.get("/downloads/modelo-participantes.xlsx")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.mimetype, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertTrue(download.data.startswith(b"PK"))
        download.close()
        self.client.post("/logout", data={"csrf_token": self.token})
        self.assertEqual(self.client.get("/downloads/modelo-participantes.xlsx").status_code, 302)


if __name__ == "__main__":
    unittest.main()
