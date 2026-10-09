import io
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, send_file, url_for
from sqlalchemy import select

from app.auth.routes import csrf_token, login_required, require_csrf
from app.models import PdfTemplate, TemplateVersion
from app.templates_pdf.config import validate_fields
from app.templates_pdf.service import store_template
from app.certificates.render import render_certificate


templates_bp = Blueprint("templates_pdf", __name__)


@templates_bp.get("/downloads/modelo-certificado-template.ai")
@login_required
def illustrator_reference():
    path = Path(__file__).resolve().parents[1] / "assets" / "modelo-certificado-template.ai"
    return send_file(
        path,
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name="modelo-certificado-template.ai",
    )


@templates_bp.get("/templates")
@login_required
def index():
    with current_app.extensions["db_sessionmaker"]() as db:
        templates = db.scalars(select(PdfTemplate).order_by(PdfTemplate.id.desc())).all()
    created_id = request.args.get("template_id", type=int)
    created_template = next((template for template in templates if template.id == created_id), None)
    return render_template("pdf_templates/index.html", templates=templates,
                           created_template=created_template, csrf_token=csrf_token())


@templates_bp.post("/templates")
@login_required
def create():
    require_csrf()
    try:
        template_id = store_template(current_app, request.form.get("name", ""), request.files.get("pdf"))
    except ValueError as exc:
        abort(400, description=str(exc))
    return redirect(url_for("templates_pdf.index", template_id=template_id))


@templates_bp.get("/templates/<int:template_id>/pdf")
@login_required
def original_pdf(template_id):
    with current_app.extensions["db_sessionmaker"]() as db:
        template = db.get(PdfTemplate, template_id)
        if template is None:
            abort(404)
        file_key = template.file_key
    path = Path(current_app.config["PRIVATE_STORAGE_DIR"]) / file_key
    if not path.is_file():
        abort(404)
    return send_file(path, mimetype="application/pdf", as_attachment=False, download_name="template.pdf")


@templates_bp.get("/templates/<int:template_id>/source")
@login_required
def source_pdf(template_id):
    with current_app.extensions["db_sessionmaker"]() as db:
        template = db.get(PdfTemplate, template_id)
        if template is None:
            abort(404)
        file_key = template.file_key
    storage = Path(current_app.config["PRIVATE_STORAGE_DIR"])
    source_path = storage / file_key.replace(".pdf", ".source.pdf")
    path = source_path if source_path.is_file() else storage / file_key
    if not path.is_file():
        abort(404)
    return send_file(path, mimetype="application/pdf", as_attachment=True, download_name="template-enviado.pdf")


@templates_bp.get("/templates/<int:template_id>/edit")
@login_required
def edit(template_id):
    with current_app.extensions["db_sessionmaker"]() as db:
        template = db.get(PdfTemplate, template_id)
        if template is None:
            abort(404)
        latest = db.scalar(select(TemplateVersion).where(TemplateVersion.template_id == template_id).order_by(TemplateVersion.number.desc()))
        fields = latest.fields if latest else []
        version = latest.number if latest else 0
    return render_template("pdf_templates/editor.html", template=template, fields=fields, version=version, csrf_token=csrf_token())


@templates_bp.post("/templates/<int:template_id>/versions")
@login_required
def save_version(template_id):
    require_csrf()
    if not request.is_json:
        abort(400)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        abort(400)
    with current_app.extensions["db_sessionmaker"]() as db:
        template = db.get(PdfTemplate, template_id)
        if template is None:
            abort(404)
        try:
            fields = validate_fields(payload.get("fields"), template.page_width_pt, template.page_height_pt)
        except ValueError as exc:
            abort(400, description=str(exc))
        latest = db.scalar(select(TemplateVersion).where(TemplateVersion.template_id == template_id).order_by(TemplateVersion.number.desc()))
        number = latest.number + 1 if latest else 1
        db.add(TemplateVersion(template_id=template_id, number=number, fields=fields))
        db.commit()
    return jsonify({"version": number}), 201


@templates_bp.post("/templates/<int:template_id>/preview")
@login_required
def preview(template_id):
    require_csrf()
    with current_app.extensions["db_sessionmaker"]() as db:
        template = db.get(PdfTemplate, template_id)
        if template is None:
            abort(404)
        latest = db.scalar(select(TemplateVersion).where(TemplateVersion.template_id == template_id).order_by(TemplateVersion.number.desc()))
        if latest is None:
            abort(400, description="Salve a configuração do template antes da prévia.")
        fields = latest.fields
        file_key = template.file_key
    path = Path(current_app.config["PRIVATE_STORAGE_DIR"]) / file_key
    if not path.is_file():
        abort(404)
    try:
        result = render_certificate(path.read_bytes(), fields, request.form.get("nome", ""), request.form.get("sobrenome", ""))
    except ValueError as exc:
        abort(400, description=str(exc))
    return send_file(io.BytesIO(result), mimetype="application/pdf", as_attachment=False, download_name="previa.pdf")

