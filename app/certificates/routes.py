import re
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

from flask import Blueprint, abort, current_app, redirect, render_template, request, send_file, url_for
from sqlalchemy import func, select

from app.auth.routes import csrf_token, login_required, require_csrf
from app.certificates.names import batch_filename, certificate_filename
from app.certificates.render import render_certificate
from app.models import Certificate, Client, Event, GenerationBatch, Participant, PdfTemplate, TemplateVersion


certificates_bp = Blueprint("certificates", __name__)
_REQUEST_KEY = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _storage() -> Path:
    path = Path(current_app.config["PRIVATE_STORAGE_DIR"])
    path.mkdir(parents=True, exist_ok=True)
    return path


@certificates_bp.get("/certificates")
@login_required
def index():
    raw_client_id = request.args.get("client_id", "")
    if raw_client_id and (not raw_client_id.isdecimal() or int(raw_client_id) < 1):
        abort(400, description="Selecione um cliente válido.")
    selected_id = int(raw_client_id) if raw_client_id else None
    with current_app.extensions["db_sessionmaker"]() as db:
        clients = db.scalars(select(Client).order_by(Client.name, Client.id)).all()
        if selected_id and not any(client.id == selected_id for client in clients):
            abort(404)
        events = db.scalars(select(Event).order_by(Event.id.desc())).all()
        event_ids = [event.id for event in events if selected_id is None or event.client_id == selected_id]
        batches = (db.scalars(select(GenerationBatch).where(GenerationBatch.event_id.in_(event_ids))
                              .order_by(GenerationBatch.id.desc())).all() if event_ids else [])
    batches_by_event = {}
    for batch in batches:
        batches_by_event.setdefault(batch.event_id, []).append(batch)
    groups = [
        (client, [(event, batches_by_event.get(event.id, [])) for event in events if event.client_id == client.id])
        for client in clients if selected_id is None or client.id == selected_id
    ]
    return render_template("certificates/index.html", clients=clients, selected_id=selected_id,
                           groups=groups, has_events=any(events for _, events in groups),
                           csrf_token=csrf_token())


@certificates_bp.get("/events/<int:event_id>/generate")
@login_required
def generate_page(event_id):
    with current_app.extensions["db_sessionmaker"]() as db:
        event = db.get(Event, event_id)
        if event is None:
            abort(404)
        template = db.get(PdfTemplate, event.template_id) if event.template_id else None
        version = (db.scalar(select(TemplateVersion).where(TemplateVersion.template_id == template.id)
                             .order_by(TemplateVersion.number.desc())) if template else None)
        count = db.scalar(select(func.count()).select_from(Participant).where(Participant.event_id == event_id))
        batches = db.scalars(select(GenerationBatch).where(GenerationBatch.event_id == event_id)
                             .order_by(GenerationBatch.id.desc())).all()
    return render_template("certificates/generate.html", event=event, template=template,
                           version=version, count=count, batches=batches,
                           request_key=uuid.uuid4().hex, csrf_token=csrf_token())


@certificates_bp.post("/events/<int:event_id>/batches")
@login_required
def create_batch(event_id):
    require_csrf()
    if request.form.get("confirmed_preview") != "yes":
        abort(400, description="Confirme a prévia antes de gerar o lote.")
    key = request.form.get("request_key", "")
    if not _REQUEST_KEY.fullmatch(key):
        abort(400, description="Identificador de envio inválido.")

    with current_app.extensions["db_sessionmaker"]() as db:
        event = db.get(Event, event_id)
        if event is None:
            abort(404)
        existing = db.scalar(select(GenerationBatch).where(GenerationBatch.event_id == event_id,
                                                             GenerationBatch.request_key == key))
        if existing:
            return redirect(url_for("certificates.batch_detail", batch_id=existing.id))
        if not event.template_id:
            abort(400, description="Associe um template PDF ao evento.")
        template = db.get(PdfTemplate, event.template_id)
        version = db.scalar(select(TemplateVersion).where(TemplateVersion.template_id == event.template_id)
                            .order_by(TemplateVersion.number.desc()))
        if template is None or version is None:
            abort(400, description="Configure e salve os campos do template.")
        participants = db.scalars(select(Participant).where(Participant.event_id == event_id)
                                  .order_by(Participant.id)).all()
        if not participants or len(participants) > 500:
            abort(400, description="O lote precisa ter de 1 a 500 participantes.")
        original_path = _storage() / template.file_key
        if not original_path.is_file():
            abort(404, description="O PDF original não foi encontrado.")
        original_pdf = original_path.read_bytes()
        fields = version.fields
        batch = GenerationBatch(event_id=event_id, template_version_id=version.id,
                                request_key=key, status="processing", success_count=0, error_count=0)
        db.add(batch)
        db.commit()
        batch_id = batch.id

        output_dir = _storage() / "generated" / str(batch_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        successful = []
        for participant in participants:
            certificate = Certificate(batch_id=batch_id, participant_id=participant.id, status="failed")
            try:
                pdf_data = render_certificate(original_pdf, fields, participant.first_name, participant.last_name)
                file_key = f"generated/{batch_id}/{uuid.uuid4().hex}.pdf"
                (_storage() / file_key).write_bytes(pdf_data)
                certificate.file_key = file_key
                certificate.status = "completed"
                batch.success_count += 1
                successful.append((participant, file_key))
            except ValueError as exc:
                certificate.error = str(exc)[:300]
                batch.error_count += 1
            db.add(certificate)
            db.commit()

        if successful:
            zip_key = f"generated/{batch_id}/certificados.zip"
            zip_path = _storage() / zip_key
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for participant, file_key in successful:
                    archive.write(_storage() / file_key,
                                  arcname=certificate_filename(event.title, participant.first_name,
                                                               participant.last_name, participant.id))
            with zipfile.ZipFile(zip_path) as archive:
                if archive.testzip() is not None:
                    raise RuntimeError("Falha na verificação do ZIP gerado.")
            batch.zip_file_key = zip_key
        batch.status = "completed_with_errors" if batch.error_count else "completed"
        if not successful:
            batch.status = "failed"
        db.commit()
    return redirect(url_for("certificates.batch_detail", batch_id=batch_id))


@certificates_bp.get("/batches/<int:batch_id>")
@login_required
def batch_detail(batch_id):
    with current_app.extensions["db_sessionmaker"]() as db:
        batch = db.get(GenerationBatch, batch_id)
        if batch is None:
            abort(404)
        event = db.get(Event, batch.event_id)
        client = db.get(Client, event.client_id)
        version = db.get(TemplateVersion, batch.template_version_id)
        rows = db.execute(select(Certificate, Participant)
                          .join(Participant, Certificate.participant_id == Participant.id)
                          .where(Certificate.batch_id == batch_id)
                          .order_by(Certificate.id)).all()
    return render_template("certificates/batch.html", batch=batch, event=event, client=client,
                           version=version, rows=rows)


@certificates_bp.get("/batches/<int:batch_id>/zip")
@login_required
def download_zip(batch_id):
    with current_app.extensions["db_sessionmaker"]() as db:
        batch = db.get(GenerationBatch, batch_id)
        if batch is None or not batch.zip_file_key:
            abort(404)
        event = db.get(Event, batch.event_id)
        rows = db.execute(select(Certificate, Participant)
                          .join(Participant, Participant.id == Certificate.participant_id)
                          .where(Certificate.batch_id == batch_id, Certificate.status == "completed")
                          .order_by(Certificate.id)).all()
        if len(rows) != batch.success_count:
            abort(500, description="O lote está incompleto; verifique os certificados individuais.")
        file_key = batch.zip_file_key
    path = _storage() / file_key
    if not path.is_file():
        abort(404)
    download_name = batch_filename(event.title, batch_id)
    with zipfile.ZipFile(path) as source:
        source_names = source.namelist()
        renamed = []
        for _, participant in rows:
            suffix = f"-{participant.id}.pdf"
            source_name = next((name for name in source_names if name.endswith(suffix)), None)
            if source_name is None:
                abort(500, description="O ZIP não contém todos os certificados do lote.")
            renamed.append((source_name, certificate_filename(event.title, participant.first_name,
                                                               participant.last_name, participant.id)))
        if len(source_names) == len(renamed) and all(old == new for old, new in renamed):
            return send_file(path, mimetype="application/zip", as_attachment=True,
                             download_name=download_name)
        temporary = tempfile.TemporaryFile(mode="w+b", dir=_storage())
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as output:
                for old, new in renamed:
                    with source.open(old) as original, output.open(new, "w") as destination:
                        shutil.copyfileobj(original, destination)
            temporary.seek(0)
            response = send_file(temporary, mimetype="application/zip", as_attachment=True,
                                 download_name=download_name)
            response.call_on_close(temporary.close)
            return response
        except Exception:
            temporary.close()
            raise


@certificates_bp.get("/certificates/<int:certificate_id>/pdf")
@login_required
def download_certificate(certificate_id):
    with current_app.extensions["db_sessionmaker"]() as db:
        row = db.execute(select(Certificate, Participant, Event)
                         .join(Participant, Participant.id == Certificate.participant_id)
                         .join(GenerationBatch, GenerationBatch.id == Certificate.batch_id)
                         .join(Event, Event.id == GenerationBatch.event_id)
                         .where(Certificate.id == certificate_id)).one_or_none()
        if row is None:
            abort(404)
        certificate, participant, event = row
        if certificate.status != "completed" or not certificate.file_key:
            abort(404)
        file_key = certificate.file_key
    path = _storage() / file_key
    if not path.is_file():
        abort(404)
    return send_file(path, mimetype="application/pdf", as_attachment=True,
                     download_name=certificate_filename(event.title, participant.first_name,
                                                        participant.last_name, participant.id))
