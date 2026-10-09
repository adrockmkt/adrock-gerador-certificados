import io
import json
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from app import create_app
from app.auth.service import create_admin
from app.certificates.render import fit_font_size, render_certificate


def base_pdf():
    output = io.BytesIO()
    document = canvas.Canvas(output, pagesize=(842, 595))
    document.drawString(30, 30, "Template original")
    document.showPage()
    document.save()
    return output.getvalue()


FIELD = {
    "id": "name1", "key": "nome_completo", "x_pt": 150, "y_pt": 300,
    "width_pt": 500, "font_family": "Montserrat", "font_weight": "semibold",
    "font_size_pt": 28, "min_font_size_pt": 18, "color": "#333333", "align": "center",
}


class PdfRenderingTests(unittest.TestCase):
    def test_long_name_wraps_into_two_lines_within_configured_area(self):
        field = {**FIELD, "width_pt": 300, "height_pt": 110, "font_size_pt": 40,
                 "min_font_size_pt": 18, "max_lines": 2}
        result = render_certificate(base_pdf(), [field], "Ana Maria Carolina", "de Albuquerque Santos")
        extracted = PdfReader(io.BytesIO(result)).pages[0].extract_text()
        self.assertIn("Ana Maria Carolina", extracted.splitlines())
        self.assertIn("de Albuquerque Santos", extracted.splitlines())
        self.assertNotIn("Ana Maria Carolina de Albuquerque Santos", extracted)

    def test_long_name_that_cannot_fit_two_lines_is_reported(self):
        field = {**FIELD, "width_pt": 70, "height_pt": 45, "font_size_pt": 40,
                 "min_font_size_pt": 18, "max_lines": 2}
        with self.assertRaises(ValueError):
            render_certificate(base_pdf(), [field], "Ana Maria Carolina", "de Albuquerque Santos")

    def test_open_font_choices_render_accented_names(self):
        for family in ("Lato", "Poppins"):
            with self.subTest(family=family):
                field = {**FIELD, "font_family": family, "font_weight": "semibold"}
                result = render_certificate(base_pdf(), [field], "Márcia", "Ávila")
                self.assertIn("Márcia Ávila", PdfReader(io.BytesIO(result)).pages[0].extract_text())

    def test_original_content_and_accented_name_are_preserved(self):
        result = render_certificate(base_pdf(), [FIELD], "José", "Ávila")
        reader = PdfReader(io.BytesIO(result))
        extracted = reader.pages[0].extract_text()
        self.assertIn("Template original", extracted)
        self.assertIn("José Ávila", extracted)
        self.assertEqual(len(reader.pages), 1)

    def test_long_name_shrinks_or_reports_it_cannot_fit(self):
        self.assertLess(fit_font_size("Maria " * 7, "Montserrat", "semibold", 28, 18, 500), 28)
        with self.assertRaises(ValueError):
            fit_font_size("Maria " * 100, "Montserrat", "semibold", 28, 18, 50)

    def test_missing_name_is_rejected(self):
        with self.assertRaises(ValueError):
            render_certificate(base_pdf(), [FIELD], "", "Ávila")


class PreviewRouteTests(unittest.TestCase):
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
        self.client.post("/templates", data={
            "name": "FIEP", "pdf": (io.BytesIO(base_pdf()), "fiep.pdf"), "csrf_token": self.token,
        }, content_type="multipart/form-data")

    def tearDown(self):
        self.app.extensions["db_engine"].dispose()
        self.temp_dir.cleanup()

    def test_preview_uses_saved_version(self):
        self.client.post("/templates/1/versions", data=json.dumps({"fields": [FIELD]}),
                         content_type="application/json", headers={"X-CSRF-Token": self.token})
        response = self.client.post("/templates/1/preview", data={
            "nome": "José", "sobrenome": "Ávila", "csrf_token": self.token,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertIn("José Ávila", PdfReader(io.BytesIO(response.data)).pages[0].extract_text())

    def test_preview_requires_saved_config_and_csrf(self):
        self.assertEqual(self.client.post("/templates/1/preview", data={
            "nome": "José", "sobrenome": "Ávila", "csrf_token": self.token,
        }).status_code, 400)
        self.assertEqual(self.client.post("/templates/1/preview", data={"nome": "José", "sobrenome": "Ávila"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
