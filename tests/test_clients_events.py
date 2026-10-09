import tempfile
import unittest
import uuid
from pathlib import Path

from sqlalchemy import func, select

from app import create_app
from app.auth.service import create_admin
from app.models import (Certificate, Client, CsvImport, Event, GenerationBatch,
                        Participant, PdfTemplate, TemplateVersion)


class ClientEventTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database = Path(self.temp_dir.name) / "test.sqlite3"
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-secret",
            "DATABASE_URL": f"sqlite:///{database}",
            "PRIVATE_STORAGE_DIR": str(Path(self.temp_dir.name) / "private"),
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

    def seed_event_with_data(self, client_name="FIEP", title="Curso GA4", template_id=None):
        with self.app.extensions["db_sessionmaker"]() as db:
            if template_id is None:
                template = PdfTemplate(name="Modelo compartilhado", file_key=uuid.uuid4().hex + ".pdf",
                                       sha256="0" * 64, page_width_pt=842, page_height_pt=595, rotation=0)
                db.add(template)
                db.flush()
                version = TemplateVersion(template_id=template.id, number=1, fields=[])
                db.add(version)
                db.flush()
            else:
                template = db.get(PdfTemplate, template_id)
                version = db.scalar(select(TemplateVersion).where(TemplateVersion.template_id == template_id))
            client = Client(name=client_name)
            db.add(client)
            db.flush()
            event = Event(client_id=client.id, title=title, template_id=template.id)
            db.add(event)
            db.flush()
            csv_key = uuid.uuid4().hex + ".csv"
            draft = CsvImport(event_id=event.id, file_key=csv_key, headers=["Nome", "Sobrenome"], status="pending")
            db.add(draft)
            db.flush()
            person = Participant(event_id=event.id, import_id=draft.id, source_row=2,
                                 first_name="Maria", last_name="Silva")
            db.add(person)
            db.flush()
            batch = GenerationBatch(event_id=event.id, template_version_id=version.id,
                                    request_key=uuid.uuid4().hex, status="completed",
                                    success_count=1, error_count=0)
            db.add(batch)
            db.flush()
            batch.zip_file_key = f"generated/{batch.id}/certificados.zip"
            certificate = Certificate(batch_id=batch.id, participant_id=person.id,
                                      file_key=f"generated/{batch.id}/sample.pdf", status="completed")
            db.add(certificate)
            db.commit()
            ids = {"client": client.id, "event": event.id, "template": template.id,
                   "batch": batch.id, "certificate": certificate.id, "csv_key": csv_key}
        storage = Path(self.app.config["PRIVATE_STORAGE_DIR"])
        (storage / "generated" / str(ids["batch"])).mkdir(parents=True)
        (storage / csv_key).write_bytes(b"Nome,Sobrenome\nMaria,Silva")
        (storage / "generated" / str(ids["batch"]) / "sample.pdf").write_bytes(b"pdf")
        (storage / "generated" / str(ids["batch"]) / "certificados.zip").write_bytes(b"zip")
        (storage / template.file_key).write_bytes(b"template")
        return ids

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
        self.assertEqual(self.client.get("/clients/1/delete").status_code, 302)
        self.assertEqual(self.client.post("/clients/1/delete", data={"confirm": "yes"}).status_code, 302)

    def test_client_and_event_names_can_be_edited(self):
        ids = self.seed_event_with_data()
        token = self.csrf()
        self.assertEqual(self.client.post(f"/clients/{ids['client']}/edit", data={
            "name": "  Novo cliente  ", "csrf_token": token,
        }).status_code, 302)
        self.assertEqual(self.client.post(f"/events/{ids['event']}/edit", data={
            "title": "  Novo evento  ", "csrf_token": token,
        }).status_code, 302)
        self.assertIn(b"Novo cliente", self.client.get(f"/clients/{ids['client']}").data)
        self.assertIn(b"Novo evento", self.client.get(f"/events/{ids['event']}").data)
        with self.app.extensions["db_sessionmaker"]() as db:
            self.assertEqual(db.get(Client, ids["client"]).name, "Novo cliente")
            self.assertEqual(db.get(Event, ids["event"]).title, "Novo evento")
        self.assertEqual(self.client.post(f"/clients/{ids['client']}/edit", data={
            "name": " ", "csrf_token": token,
        }).status_code, 400)
        self.assertEqual(self.client.post(f"/events/{ids['event']}/edit", data={
            "title": " ", "csrf_token": token,
        }).status_code, 400)
        self.assertEqual(self.client.post(f"/clients/{ids['client']}/edit", data={
            "name": "Sem CSRF",
        }).status_code, 400)

    def test_event_deletion_removes_owned_data_and_files_but_keeps_shared_template(self):
        removed = self.seed_event_with_data()
        retained = self.seed_event_with_data("Outro cliente", "Outro curso", removed["template"])
        storage = Path(self.app.config["PRIVATE_STORAGE_DIR"])
        confirmation = self.client.get(f"/events/{removed['event']}/delete")
        self.assertIn(b"1 certificado(s)", confirmation.data)
        self.assertIn(b"templates PDF", confirmation.data)
        self.assertEqual(self.client.post(f"/events/{removed['event']}/delete", data={
            "confirm": "yes",
        }).status_code, 400)
        self.assertEqual(self.client.post(f"/events/{removed['event']}/delete", data={
            "csrf_token": self.csrf(),
        }).status_code, 400)
        response = self.client.post(f"/events/{removed['event']}/delete", data={
            "confirm": "yes", "csrf_token": self.csrf(),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(f"/events/{removed['event']}").status_code, 404)
        self.assertEqual(self.client.get(f"/batches/{removed['batch']}").status_code, 404)
        self.assertEqual(self.client.get(f"/certificates/{removed['certificate']}/pdf").status_code, 404)
        self.assertFalse((storage / removed["csv_key"]).exists())
        self.assertFalse((storage / "generated" / str(removed["batch"])).exists())
        self.assertTrue((storage / retained["csv_key"]).exists())
        self.assertTrue((storage / "generated" / str(retained["batch"])).exists())
        with self.app.extensions["db_sessionmaker"]() as db:
            self.assertIsNotNone(db.get(PdfTemplate, removed["template"]))
            self.assertIsNotNone(db.get(Event, retained["event"]))
            self.assertEqual(db.scalar(select(func.count()).select_from(Participant).where(
                Participant.event_id == removed["event"])), 0)

    def test_client_deletion_removes_all_its_events_without_touching_other_client(self):
        first = self.seed_event_with_data()
        self.client.post(f"/clients/{first['client']}/events", data={
            "title": "Segundo curso", "csrf_token": self.csrf(),
        })
        unrelated = self.seed_event_with_data("Outro cliente", "Outro curso", first["template"])
        confirmation = self.client.get(f"/clients/{first['client']}/delete")
        self.assertIn(b"2 evento(s)", confirmation.data)
        response = self.client.post(f"/clients/{first['client']}/delete", data={
            "confirm": "yes", "csrf_token": self.csrf(),
        })
        self.assertEqual(response.status_code, 302)
        with self.app.extensions["db_sessionmaker"]() as db:
            self.assertIsNone(db.get(Client, first["client"]))
            self.assertEqual(db.scalar(select(func.count()).select_from(Event).where(
                Event.client_id == first["client"])), 0)
            self.assertIsNotNone(db.get(Client, unrelated["client"]))
            self.assertIsNotNone(db.get(PdfTemplate, first["template"]))
        storage = Path(self.app.config["PRIVATE_STORAGE_DIR"])
        self.assertFalse((storage / "generated" / str(first["batch"])).exists())
        self.assertTrue((storage / "generated" / str(unrelated["batch"])).exists())


if __name__ == "__main__":
    unittest.main()
