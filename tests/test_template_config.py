import io
import json
import tempfile
import unittest
from pathlib import Path

from reportlab.pdfgen import canvas

from app import create_app
from app.auth.service import create_admin


def blank_pdf():
    output = io.BytesIO()
    document = canvas.Canvas(output, pagesize=(842, 595))
    document.showPage()
    document.save()
    return output.getvalue()


class TemplateConfigTests(unittest.TestCase):
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
            "name": "FIEP", "pdf": (io.BytesIO(blank_pdf()), "fiep.pdf"), "csrf_token": self.token,
        }, content_type="multipart/form-data")

    def tearDown(self):
        self.app.extensions["db_engine"].dispose()
        self.temp_dir.cleanup()

    def field(self, **changes):
        data = {
            "id": "field1", "key": "nome_completo", "x_pt": 100, "y_pt": 300,
            "width_pt": 500, "font_family": "Helvetica", "font_weight": "regular",
            "font_size_pt": 28, "min_font_size_pt": 18, "color": "#333333", "align": "center",
        }
        data.update(changes)
        return data

    def save(self, fields):
        return self.client.post("/templates/1/versions", data=json.dumps({"fields": fields}),
                                content_type="application/json", headers={"X-CSRF-Token": self.token})

    def test_editor_loads_and_saves_versioned_field_mapping(self):
        self.assertEqual(self.client.get("/templates/1/edit").status_code, 200)
        self.assertEqual(self.save([self.field()]).status_code, 201)
        second = self.save([self.field(x_pt=150)])
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.json["version"], 2)
        editor = self.client.get("/templates/1/edit")
        self.assertIn(b"nome_completo", editor.data)
        self.assertIn(b"editor.js", editor.data)
        script = self.client.get("/static/editor.js")
        vendor = self.client.get("/static/vendor/pdfjs/pdf.mjs")
        self.assertEqual(script.status_code, 200)
        self.assertEqual(vendor.status_code, 200)
        script.close()
        vendor.close()

    def test_coordinates_must_remain_within_pdf_page(self):
        self.assertEqual(self.save([self.field(x_pt=-1)]).status_code, 400)
        self.assertEqual(self.save([self.field(x_pt=700, width_pt=200)]).status_code, 400)
        self.assertEqual(self.save([self.field(y_pt=600)]).status_code, 400)

    def test_unknown_field_and_invalid_color_are_rejected(self):
        self.assertEqual(self.save([self.field(key="cpf")]).status_code, 400)
        self.assertEqual(self.save([self.field(color="red")]).status_code, 400)

    def test_two_line_field_height_is_validated(self):
        self.assertEqual(self.save([self.field(height_pt=110, max_lines=2)]).status_code, 201)
        self.assertEqual(self.save([self.field(height_pt=700, max_lines=2)]).status_code, 400)
        self.assertEqual(self.save([self.field(height_pt=20, max_lines=2)]).status_code, 400)

    def test_save_requires_csrf_and_authentication(self):
        response = self.client.post("/templates/1/versions", json={"fields": [self.field()]})
        self.assertEqual(response.status_code, 400)
        self.client.post("/logout", data={"csrf_token": self.token})
        self.assertEqual(self.client.get("/templates/1/edit").status_code, 302)


if __name__ == "__main__":
    unittest.main()
