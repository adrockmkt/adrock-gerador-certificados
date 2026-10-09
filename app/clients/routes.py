from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for
from sqlalchemy import select

from app.auth.routes import csrf_token, login_required, require_csrf
from app.clients.deletion import delete_events, deletion_summary, remove_private_files
from app.models import Client, Event, PdfTemplate


clients_bp = Blueprint("clients", __name__)


@clients_bp.get("/clients")
@login_required
def index():
    with current_app.extensions["db_sessionmaker"]() as db:
        clients = db.scalars(select(Client).order_by(Client.name, Client.id)).all()
    return render_template("clients/index.html", clients=clients, csrf_token=csrf_token())


@clients_bp.post("/clients")
@login_required
def create():
    require_csrf()
    name = request.form.get("name", "").strip()
    if not name or len(name) > 200:
        abort(400, description="Informe um nome de cliente com até 200 caracteres.")
    with current_app.extensions["db_sessionmaker"]() as db:
        client = Client(name=name)
        db.add(client)
        db.commit()
        client_id = client.id
    return redirect(url_for("clients.detail", client_id=client_id))


@clients_bp.get("/clients/<int:client_id>")
@login_required
def detail(client_id):
    with current_app.extensions["db_sessionmaker"]() as db:
        client = db.get(Client, client_id)
        if client is None:
            abort(404)
        events = db.scalars(select(Event).where(Event.client_id == client_id).order_by(Event.id.desc())).all()
    return render_template("clients/detail.html", client=client, events=events, csrf_token=csrf_token())


@clients_bp.post("/clients/<int:client_id>/edit")
@login_required
def edit_client(client_id):
    require_csrf()
    name = request.form.get("name", "").strip()
    if not name or len(name) > 200:
        abort(400, description="Informe um nome de cliente com até 200 caracteres.")
    with current_app.extensions["db_sessionmaker"]() as db:
        client = db.get(Client, client_id)
        if client is None:
            abort(404)
        client.name = name
        db.commit()
    return redirect(url_for("clients.detail", client_id=client_id))


@clients_bp.get("/clients/<int:client_id>/delete")
@login_required
def confirm_delete_client(client_id):
    with current_app.extensions["db_sessionmaker"]() as db:
        client = db.get(Client, client_id)
        if client is None:
            abort(404)
        event_ids = db.scalars(select(Event.id).where(Event.client_id == client_id)).all()
        summary = deletion_summary(db, event_ids)
    return render_template("clients/confirm_delete.html", kind="cliente", item=client,
                           summary=summary, action=url_for("clients.delete_client", client_id=client_id),
                           cancel=url_for("clients.detail", client_id=client_id), csrf_token=csrf_token())


@clients_bp.post("/clients/<int:client_id>/delete")
@login_required
def delete_client(client_id):
    require_csrf()
    if request.form.get("confirm") != "yes":
        abort(400, description="Confirme a exclusão do cliente e de seus eventos.")
    with current_app.extensions["db_sessionmaker"]() as db:
        client = db.get(Client, client_id)
        if client is None:
            abort(404)
        event_ids = db.scalars(select(Event.id).where(Event.client_id == client_id)).all()
        batch_ids, csv_keys = delete_events(db, event_ids)
        db.delete(client)
        db.commit()
    remove_private_files(current_app.config["PRIVATE_STORAGE_DIR"], batch_ids, csv_keys)
    return redirect(url_for("clients.index"))


@clients_bp.get("/events/<int:event_id>")
@login_required
def event_detail(event_id):
    with current_app.extensions["db_sessionmaker"]() as db:
        event = db.get(Event, event_id)
        if event is None:
            abort(404)
        client = db.get(Client, event.client_id)
        template = db.get(PdfTemplate, event.template_id) if event.template_id else None
        templates = db.scalars(select(PdfTemplate).order_by(PdfTemplate.name)).all()
    return render_template("clients/event.html", event=event, client=client, template=template, templates=templates, csrf_token=csrf_token())


@clients_bp.post("/events/<int:event_id>/edit")
@login_required
def edit_event(event_id):
    require_csrf()
    title = request.form.get("title", "").strip()
    if not title or len(title) > 200:
        abort(400, description="Informe um evento com até 200 caracteres.")
    with current_app.extensions["db_sessionmaker"]() as db:
        event = db.get(Event, event_id)
        if event is None:
            abort(404)
        event.title = title
        db.commit()
    return redirect(url_for("clients.event_detail", event_id=event_id))


@clients_bp.get("/events/<int:event_id>/delete")
@login_required
def confirm_delete_event(event_id):
    with current_app.extensions["db_sessionmaker"]() as db:
        event = db.get(Event, event_id)
        if event is None:
            abort(404)
        summary = deletion_summary(db, [event_id])
    return render_template("clients/confirm_delete.html", kind="evento", item=event,
                           summary=summary, action=url_for("clients.delete_event", event_id=event_id),
                           cancel=url_for("clients.event_detail", event_id=event_id), csrf_token=csrf_token())


@clients_bp.post("/events/<int:event_id>/delete")
@login_required
def delete_event(event_id):
    require_csrf()
    if request.form.get("confirm") != "yes":
        abort(400, description="Confirme a exclusão do evento e de seus dados.")
    with current_app.extensions["db_sessionmaker"]() as db:
        event = db.get(Event, event_id)
        if event is None:
            abort(404)
        client_id = event.client_id
        batch_ids, csv_keys = delete_events(db, [event_id])
        db.commit()
    remove_private_files(current_app.config["PRIVATE_STORAGE_DIR"], batch_ids, csv_keys)
    return redirect(url_for("clients.detail", client_id=client_id))


@clients_bp.post("/events/<int:event_id>/template")
@login_required
def assign_template(event_id):
    require_csrf()
    try:
        template_id = int(request.form.get("template_id", ""))
    except ValueError:
        abort(400)
    with current_app.extensions["db_sessionmaker"]() as db:
        event = db.get(Event, event_id)
        template = db.get(PdfTemplate, template_id)
        if event is None or template is None:
            abort(404)
        event.template_id = template.id
        db.commit()
    if request.form.get("return_to") == "participants":
        return redirect(url_for("imports.participants", event_id=event_id))
    return redirect(url_for("clients.event_detail", event_id=event_id))


@clients_bp.post("/clients/<int:client_id>/events")
@login_required
def create_event(client_id):
    require_csrf()
    title = request.form.get("title", "").strip()
    if not title or len(title) > 200:
        abort(400, description="Informe um evento com até 200 caracteres.")
    with current_app.extensions["db_sessionmaker"]() as db:
        if db.get(Client, client_id) is None:
            abort(404)
        db.add(Event(client_id=client_id, title=title))
        db.commit()
    return redirect(url_for("clients.detail", client_id=client_id))

