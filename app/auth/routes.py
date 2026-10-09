import hmac
import secrets
from functools import wraps

from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for
from sqlalchemy import select

from app.auth.service import authenticate
from app.models import Admin


auth_bp = Blueprint("auth", __name__)


def csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def require_csrf() -> None:
    supplied = request.form.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")
    expected = session.get("csrf_token", "")
    if not expected or not hmac.compare_digest(supplied, expected):
        abort(400)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        admin_id = session.get("admin_id")
        if admin_id is None:
            return redirect(url_for("auth.login"))
        with current_app.extensions["db_sessionmaker"]() as db:
            admin = db.get(Admin, admin_id)
            if admin is None or session.get("session_version") != admin.session_version:
                session.clear()
                return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("auth/login.html", csrf_token=csrf_token())

    require_csrf()
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    if len(username) > 100 or len(password) > 1024:
        abort(400)
    admin, limited = authenticate(current_app, username, password, request.remote_addr or "unknown")
    if limited:
        return render_template("auth/login.html", csrf_token=csrf_token(), error="Muitas tentativas. Tente novamente mais tarde."), 429
    if admin is None:
        return render_template("auth/login.html", csrf_token=csrf_token(), error="Usuário ou senha inválidos."), 401
    session.clear()
    session["admin_id"] = admin.id
    session["session_version"] = admin.session_version
    session.permanent = True
    return redirect(url_for("home"))


@auth_bp.post("/logout")
@login_required
def logout():
    require_csrf()
    session.clear()
    return redirect(url_for("auth.login"))

