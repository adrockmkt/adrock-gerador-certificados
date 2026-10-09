import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from app import create_app
from app.auth.service import create_admin


def sample_pdf():
    output = io.BytesIO()
    doc = canvas.Canvas(output, pagesize=(842, 595))
    doc.drawString(30, 30, "Original FIEP")
    doc.showPage()
    doc.save()
    return output.getvalue()


FIELD = {
    "id": "name1", "key": "nome_completo", "x_pt": 150, "y_pt": 300,
    "width_pt": 500, "font_family": "Montserrat", "font_weight": "semibold",
    "font_size_pt": 28, "min_font_size_pt": 18, "color": "#333333", "align": "center",
}


class BatchGenerationTests(unittest.TestCase):
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
        self.client.post("/templates", data={
            "name": "FIEP", "pdf": (io.BytesIO(sample_pdf()), "fiep.pdf"), "csrf_token": self.token,
        }, content_type="multipart/form-data")
        self.client.post("/events/1/template", data={"template_id": "1", "csrf_token": self.token})
        self.save_field(FIELD)

    def tearDown(self):
        self.app.extensions["db_engine"].dispose()
        self.temp_dir.cleanup()

    def save_field(self, field):
        return self.client.post("/templates/1/versions", data=json.dumps({"fields": [field]}),
                                content_type="application/json", headers={"X-CSRF-Token": self.token})

    def import_people(self, csv):
        self.client.post("/events/1/imports", data={
            "csv": (io.BytesIO(csv.encode()), "people.csv"), "csrf_token": self.token,
        }, content_type="multipart/form-data")
        return self.client.post("/imports/1/confirm", data={
            "first_col": "Nome", "last_col": "Sobrenome", "csrf_token": self.token,
        })

    def generate(self, key="once"):
        return self.client.post("/events/1/batches", data={
            "request_key": key, "confirmed_preview": "yes", "csrf_token": self.token,
        })

    def test_batch_creates_individual_pdfs_and_valid_zip(self):
        self.import_people("Nome,Sobrenome\nMaria,Silva\nJosé,Ávila\n")
        response = self.generate()
        self.assertEqual(response.status_code, 302)
        detail = self.client.get("/batches/1")
        self.assertIn(b"2 certificados gerados", detail.data)
        individual = self.client.get("/certificates/1/pdf")
        self.assertEqual(individual.status_code, 200)
        self.assertIn("certificado-ga4-maria-silva-1.pdf", individual.headers["Content-Disposition"])
        self.assertIn("Maria Silva", PdfReader(io.BytesIO(individual.data)).pages[0].extract_text())
        individual.close()
        zipped = self.client.get("/batches/1/zip")
        self.assertEqual(zipped.status_code, 200)
        self.assertIn("certificados-ga4-lote-1.zip", zipped.headers["Content-Disposition"])
        with zipfile.ZipFile(io.BytesIO(zipped.data)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.namelist(), [
                "certificado-ga4-maria-silva-1.pdf",
                "certificado-ga4-jose-avila-2.pdf",
            ])
        zipped.close()

    def test_old_zip_names_are_updated_when_downloaded(self):
        self.import_people("Nome,Sobrenome\nMaria,Silva\n")
        self.generate()
        path = Path(self.app.config["PRIVATE_STORAGE_DIR"]) / "generated/1/certificados.zip"
        with zipfile.ZipFile(path) as original:
            pdf_data = original.read(original.namelist()[0])
        with zipfile.ZipFile(path, "w") as legacy:
            legacy.writestr("certificado-1.pdf", pdf_data)
        self.client.post("/events/1/edit", data={"title": "Webinar / 1", "csrf_token": self.token})

        response = self.client.get("/batches/1/zip")
        self.assertEqual(response.status_code, 200)
        self.assertIn("certificados-webinar-1-lote-1.zip", response.headers["Content-Disposition"])
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            self.assertEqual(archive.namelist(), ["certificado-webinar-1-maria-silva-1.pdf"])
            self.assertIsNone(archive.testzip())
        response.close()
        individual = self.client.get("/certificates/1/pdf")
        self.assertIn("certificado-webinar-1-maria-silva-1.pdf", individual.headers["Content-Disposition"])
        individual.close()

    def test_certificate_catalog_filters_clients_and_shows_batch_downloads(self):
        self.import_people("Nome,Sobrenome\nMaria,Silva\n")
        self.generate()
        self.client.post("/clients", data={"name": "Outro cliente", "csrf_token": self.token})
        self.client.post("/clients/2/events", data={"title": "Webinar 2", "csrf_token": self.token})

        page = self.client.get("/certificates")
        self.assertIn(b"Certificados emitidos", page.data)
        self.assertIn(b"FIEP", page.data)
        self.assertIn(b"Outro cliente", page.data)
        self.assertIn(b"Lote 1", page.data)
        self.assertIn(b"/batches/1/zip", page.data)

        filtered = self.client.get("/certificates?client_id=1")
        self.assertIn(b"FIEP", filtered.data)
        self.assertIn(b"Lote 1", filtered.data)
        self.assertNotIn(b"Webinar 2", filtered.data)
        self.assertEqual(self.client.get("/certificates?client_id=999").status_code, 404)
        self.assertEqual(self.client.get("/certificates?client_id=invalid").status_code, 400)

    def test_repeated_submission_does_not_create_second_batch(self):
        self.import_people("Nome,Sobrenome\nMaria,Silva\n")
        self.assertEqual(self.generate("same-key").status_code, 302)
        self.assertEqual(self.generate("same-key").status_code, 302)
        self.assertEqual(self.client.get("/batches/2").status_code, 404)

    def test_unfitting_name_is_recorded_without_losing_valid_certificate(self):
        self.save_field({**FIELD, "width_pt": 90})
        self.import_people("Nome,Sobrenome\nAna,Li\nMariaMariaMariaMariaMaria,SilvaSilvaSilva\n")
        self.generate()
        detail = self.client.get("/batches/1")
        self.assertIn(b"1 certificados gerados", detail.data)
        self.assertIn(b"1 falhas", detail.data)
        zipped = self.client.get("/batches/1/zip")
        with zipfile.ZipFile(io.BytesIO(zipped.data)) as archive:
            self.assertEqual(len(archive.namelist()), 1)
        zipped.close()

    def test_confirmation_and_downloads_are_protected(self):
        self.import_people("Nome,Sobrenome\nMaria,Silva\n")
        self.assertEqual(self.client.post("/events/1/batches", data={
            "request_key": "x", "csrf_token": self.token,
        }).status_code, 400)
        self.generate()
        self.client.post("/logout", data={"csrf_token": self.token})
        self.assertEqual(self.client.get("/certificates").status_code, 302)
        self.assertEqual(self.client.get("/batches/1/zip").status_code, 302)
        self.assertEqual(self.client.get("/certificates/1/pdf").status_code, 302)


if __name__ == "__main__":
    unittest.main()
