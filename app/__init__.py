import os
from datetime import timedelta
from pathlib import Path

import click
from flask import Flask, render_template, request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

from app.auth import auth_bp
from app.auth.routes import csrf_token, login_required
from app.auth.service import create_admin, reset_password
from app.clients import clients_bp
from app.templates_pdf import templates_bp
from app.imports import imports_bp
from app.certificates.routes import certificates_bp
from app.models import Base


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        DATABASE_URL=os.environ.get("DATABASE_URL"),
        PRIVATE_STORAGE_DIR=os.environ.get("PRIVATE_STORAGE_DIR"),
        APPLICATION_ROOT=os.environ.get("APPLICATION_ROOT", "/"),
        TRUSTED_HOSTS=[host.strip() for host in os.environ.get("TRUSTED_HOSTS", "").split(",") if host.strip()] or None,
        SESSION_COOKIE_NAME="adrock_certificates_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    # O serviço de produção aceita conexões apenas no loopback; o NGINX define
    # estes cabeçalhos para o caminho público /gerador-certificados/.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_prefix=1)
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("Defina SECRET_KEY antes de iniciar a aplicação.")

    if not app.config["DATABASE_URL"]:
        Path(app.instance_path).mkdir(parents=True, exist_ok=True)
        app.config["DATABASE_URL"] = f"sqlite:///{Path(app.instance_path) / 'certificates.sqlite3'}"
    if not app.config.get("PRIVATE_STORAGE_DIR"):
        app.config["PRIVATE_STORAGE_DIR"] = str(Path(app.instance_path) / "private")
    app.config["PRIVATE_STORAGE_DIR"] = str(Path(app.config["PRIVATE_STORAGE_DIR"]).expanduser().resolve())

    engine = create_engine(app.config["DATABASE_URL"])
    Base.metadata.create_all(engine)
    app.extensions["db_engine"] = engine
    app.extensions["db_sessionmaker"] = sessionmaker(engine, expire_on_commit=False)
    app.extensions["dummy_password_hash"] = generate_password_hash("not-a-real-account-password", method="pbkdf2:sha256:600000")

    app.register_blueprint(auth_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(templates_bp)
    app.register_blueprint(imports_bp)
    app.register_blueprint(certificates_bp)

    @app.context_processor
    def inject_csrf_token():
        return {"csrf_token": csrf_token()}

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; img-src 'self'; form-action 'self'; frame-ancestors 'none'"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    @login_required
    def home():
        return render_template("home.html", csrf_token=csrf_token())

    @app.cli.command("init-admin")
    @click.option("--username", prompt=True)
    @click.password_option(confirmation_prompt=True)
    def init_admin_command(username, password):
        try:
            create_admin(app, username, password)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo("Administrador criado.")

    @app.cli.command("reset-admin-password")
    @click.option("--username", prompt=True)
    @click.password_option(confirmation_prompt=True)
    def reset_admin_password_command(username, password):
        try:
            reset_password(app, username, password)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo("Senha alterada. Sessões anteriores foram invalidadas.")

    return app

