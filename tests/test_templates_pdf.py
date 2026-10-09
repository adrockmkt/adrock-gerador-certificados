import hashlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter

from app import create_app
from app.auth.service import create_admin


def make_pdf(pages=1, pagesize=(842, 595)):
    output = io.BytesIO()
    document = canvas.Canvas(output, pagesize=pagesize)
    for page in range(pages):
        document.drawString(20, 20, f"Original {page + 1}")
        document.showPage()
    document.save()
    return output.getvalue()


class TemplateUploadTests(unittest.TestCase):
    def test_relative_private_storage_path_is_resolved_for_download(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app = create_app({
                "TESTING": True, "SECRET_KEY": "test-only-secret",
                "DATABASE_URL": f"sqlite:///{root / 'test.sqlite3'}",
                "PRIVATE_STORAGE_DIR": os.path.relpath(root / "private"),
            })
            self.assertTrue(Path(app.config["PRIVATE_STORAGE_DIR"]).is_absolute())
            app.extensions["db_engine"].dispose()

    def test_small_landscape_a_series_pdf_is_scaled_for_print_and_original_retained(self):
        original = make_pdf(pagesize=(100, 71))
        self.assertEqual(self.upload(original).status_code, 302)
        working = self.client.get("/templates/1/pdf")
        source = self.client.get("/templates/1/source")
        page = PdfReader(io.BytesIO(working.data)).pages[0]
        self.assertAlmostEqual(float(page.mediabox.width), 841.89, places=1)
        self.assertAlmostEqual(float(page.mediabox.height), 595.28, places=1)
        self.assertIn("Original 1", page.extract_text())
        self.assertEqual(source.data, original)
        working.close()
        source.close()

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

    def tearDown(self):
        self.app.extensions["db_engine"].dispose()
        self.temp_dir.cleanup()

    def csrf(self):
        self.client.get("/")
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def upload(self, data, filename="certificate.pdf"):
        return self.client.post("/templates", data={
            "name": "FIEP GA4",
            "pdf": (io.BytesIO(data), filename),
            "csrf_token": self.csrf(),
        }, content_type="multipart/form-data")

    def test_original_pdf_is_stored_and_download_is_private(self):
        original = make_pdf()
        response = self.upload(original)
        self.assertEqual(response.status_code, 302)
        pdf_response = self.client.get("/templates/1/pdf")
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(hashlib.sha256(pdf_response.data).hexdigest(), hashlib.sha256(original).hexdigest())
        self.assertEqual(pdf_response.mimetype, "application/pdf")
        pdf_response.close()
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.assertEqual(self.client.get("/templates/1/pdf").status_code, 302)

    def test_illustrator_reference_download_requires_login(self):
        page = self.client.get("/templates")
        self.assertIn(b"modelo-certificado-template.ai", page.data)
        download = self.client.get("/downloads/modelo-certificado-template.ai")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.mimetype, "application/octet-stream")
        self.assertTrue(download.data.startswith(b"%PDF-"))
        download.close()
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.assertEqual(self.client.get("/downloads/modelo-certificado-template.ai").status_code, 302)

    def test_invalid_and_multi_page_pdfs_are_rejected(self):
        self.assertEqual(self.upload(b"not a pdf").status_code, 400)
        self.assertEqual(self.upload(make_pdf(2)).status_code, 400)
        self.assertEqual(self.upload(make_pdf(), "certificate.txt").status_code, 400)
        self.assertEqual(len(list(Path(self.app.config["PRIVATE_STORAGE_DIR"]).glob("*.pdf"))), 0)

    def test_rotated_pdf_is_rejected_until_editor_supports_it(self):
        writer = PdfWriter()
        writer.append(PdfReader(io.BytesIO(make_pdf())))
        writer.pages[0].rotate(90)
        output = io.BytesIO()
        writer.write(output)
        self.assertEqual(self.upload(output.getvalue()).status_code, 400)

    def test_template_can_be_reused_by_two_events(self):
        self.upload(make_pdf())
        self.client.post("/clients", data={"name": "FIEP", "csrf_token": self.csrf()})
        for title in ("Curso 1", "Curso 2"):
            self.client.post("/clients/1/events", data={"title": title, "csrf_token": self.csrf()})
        for event_id in (1, 2):
            response = self.client.post(f"/events/{event_id}/template", data={"template_id": "1", "csrf_token": self.csrf()})
            self.assertEqual(response.status_code, 302)
            self.assertIn(b"FIEP GA4", self.client.get(f"/events/{event_id}").data)

    def test_template_upload_and_association_require_csrf(self):
        response = self.client.post("/templates", data={"name": "FIEP GA4", "pdf": (io.BytesIO(make_pdf()), "certificate.pdf")}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
