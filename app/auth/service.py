from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import Admin, LoginAttempt


MAX_FAILURES = 5
WINDOW = timedelta(minutes=15)


def create_admin(app, username: str, password: str) -> None:
    username = username.strip().lower()
    if not username or len(username) > 100:
        raise ValueError("O usuário deve ter entre 1 e 100 caracteres.")
    if len(password) < 12:
        raise ValueError("A senha deve ter pelo menos 12 caracteres.")
    with app.extensions["db_sessionmaker"]() as db:
        if db.scalar(select(Admin.id).limit(1)) is not None:
            raise ValueError("Já existe um administrador. Esta aplicação aceita apenas um.")
        db.add(Admin(username=username, password_hash=generate_password_hash(password, method="pbkdf2:sha256:600000")))
        db.commit()


def reset_password(app, username: str, password: str) -> None:
    if len(password) < 12:
        raise ValueError("A senha deve ter pelo menos 12 caracteres.")
    with app.extensions["db_sessionmaker"]() as db:
        admin = db.scalar(select(Admin).where(Admin.username == username.strip().lower()))
        if admin is None:
            raise ValueError("Administrador não encontrado.")
        admin.password_hash = generate_password_hash(password, method="pbkdf2:sha256:600000")
        admin.session_version += 1
        db.commit()


def authenticate(app, username: str, password: str, remote_addr: str) -> tuple[Admin | None, bool]:
    username = username.strip().lower()[:100]
    key = hashlib.sha256(f"{username}\0{remote_addr}".encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    with app.extensions["db_sessionmaker"]() as db:
        attempt = db.get(LoginAttempt, key)
        if attempt is not None:
            first = _aware(attempt.first_failure_at)
            locked = _aware(attempt.locked_until) if attempt.locked_until else None
            if locked and locked > now:
                return None, True
            if first + WINDOW <= now:
                db.delete(attempt)
                db.flush()
                attempt = None

        admin = db.scalar(select(Admin).where(Admin.username == username))
        if admin is None:
            check_password_hash(app.extensions["dummy_password_hash"], password)
            valid = False
        else:
            valid = check_password_hash(admin.password_hash, password)
        if valid:
            if attempt is not None:
                db.delete(attempt)
                db.commit()
            return admin, False

        if attempt is None:
            attempt = LoginAttempt(key=key, failures=0, first_failure_at=now)
            db.add(attempt)
        attempt.failures += 1
        if attempt.failures >= MAX_FAILURES:
            attempt.locked_until = now + WINDOW
        db.commit()
        return None, False


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

