import uuid
from pathlib import Path

from flask import Blueprint, abort, current_app, redirect, render_template, request, send_file, url_for
from sqlalchemy import select

from app.auth.routes import csrf_token, login_required, require_csrf
from app.imports.parser import parse_csv, review_rows
from app.models import CsvImport, Event, Participant, PdfTemplate, TemplateVersion


imports_bp = Blueprint("imports", __name__)


@imports_bp.get("/downloads/modelo-participantes.xlsx")
@login_required
def participants_spreadsheet():
    path = Path(__file__).resolve().parents[1] / "assets" / "modelo-participantes.xlsx"
    return send_file(
        path,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="modelo-participantes.xlsx",
    )


def _csv_path(file_key):
    return Path(current_app.config["PRIVATE_STORAGE_DIR"]) / file_key


@imports_bp.get("/events/<int:event_id>/participants")
@login_required
def participants(event_id):
    with current_app.extensions["db_sessionmaker"]() as db:
        event = db.get(Event, event_id)
        if event is None:
            abort(404)
        people = db.scalars(select(Participant).where(Participant.event_id == event_id).order_by(Participant.id)).all()
        template = db.get(PdfTemplate, event.template_id) if event.template_id else None
        version = (db.scalar(select(TemplateVersion).where(TemplateVersion.template_id == template.id)
                             .order_by(TemplateVersion.number.desc())) if template else None)
        templates = (db.scalars(select(PdfTemplate).order_by(PdfTemplate.name)).all()
                     if people and not template else [])
    return render_template("imports/participants.html", event=event, people=people,
                           template=template, version=version, templates=templates,
                           csrf_token=csrf_token())


@imports_bp.post("/events/<int:event_id>/imports")
@login_required
def upload(event_id):
    require_csrf()
    with current_app.extensions["db_sessionmaker"]() as db:
        if db.get(Event, event_id) is None:
            abort(404)
    uploaded = request.files.get("csv")
    if not uploaded or not uploaded.filename or not uploaded.filename.lower().endswith(".csv"):
        abort(400, description="Selecione um arquivo CSV.")
    data = uploaded.stream.read(current_app.config["MAX_CONTENT_LENGTH"] + 1)
    if len(data) > current_app.config["MAX_CONTENT_LENGTH"]:
        abort(413)
    try:
        headers, _ = parse_csv(data)
    except ValueError as exc:
        abort(400, description=str(exc))
    key = uuid.uuid4().hex + ".csv"
    path = _csv_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    try:
        with current_app.extensions["db_sessionmaker"]() as db:
            draft = CsvImport(event_id=event_id, file_key=key, headers=headers, status="pending")
            db.add(draft)
            db.commit()
            import_id = draft.id
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return redirect(url_for("imports.map_columns", import_id=import_id))


@imports_bp.get("/imports/<int:import_id>/map")
@login_required
def map_columns(import_id):
    with current_app.extensions["db_sessionmaker"]() as db:
        draft = db.get(CsvImport, import_id)
        if draft is None or draft.status != "pending":
            abort(404)
        event = db.get(Event, draft.event_id)
    return render_template("imports/map.html", draft=draft, event=event, csrf_token=csrf_token())


def _load_review(import_id):
    with current_app.extensions["db_sessionmaker"]() as db:
        draft = db.get(CsvImport, import_id)
        if draft is None:
            abort(404)
        if draft.status != "pending":
            abort(409, description="Esta importação já foi confirmada.")
        event = db.get(Event, draft.event_id)
        file_key = draft.file_key
    path = _csv_path(file_key)
    if not path.is_file():
        abort(404)
    headers, rows = parse_csv(path.read_bytes())
    first_col = request.form.get("first_col", "")
    last_col = request.form.get("last_col", "")
    valid, invalid, duplicates = review_rows(headers, rows, first_col, last_col)
    return draft, event, valid, invalid, duplicates, first_col, last_col


@imports_bp.post("/imports/<int:import_id>/review")
@login_required
def review(import_id):
    require_csrf()
    try:
        draft, event, valid, invalid, duplicates, first_col, last_col = _load_review(import_id)
    except ValueError as exc:
        abort(400, description=str(exc))
    return render_template("imports/review.html", draft=draft, event=event, valid=valid, invalid=invalid,
                           duplicates=duplicates, first_col=first_col, last_col=last_col, csrf_token=csrf_token())


@imports_bp.post("/imports/<int:import_id>/confirm")
@login_required
def confirm(import_id):
    require_csrf()
    try:
        draft, event, valid, invalid, duplicates, _, _ = _load_review(import_id)
    except ValueError as exc:
        abort(400, description=str(exc))
    if not valid:
        abort(400, description="Nenhum participante válido para importar.")
    with current_app.extensions["db_sessionmaker"]() as db:
        current = db.get(CsvImport, import_id)
        if current.status != "pending":
            abort(409)
        for source_row, first, last in valid:
            db.add(Participant(event_id=event.id, import_id=import_id, source_row=source_row,
                               first_name=first, last_name=last))
        current.status = "confirmed"
        db.commit()
    _csv_path(draft.file_key).unlink(missing_ok=True)
    return redirect(url_for("imports.participants", event_id=event.id))
