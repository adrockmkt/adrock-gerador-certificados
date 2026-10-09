#!/usr/bin/env bash
set -euo pipefail
umask 077

app_dir=/home/adrock/apps/gerador-certificados
data_dir=/var/lib/gerador-certificados
env_file=/etc/adrock/gerador-certificados.env
bootstrap_file=/root/gerador-certificados-bootstrap.txt

if [ "$(id -u)" -ne 0 ]; then
    echo "Execute como root." >&2
    exit 1
fi
if [ -e "$app_dir" ] || [ -e "$env_file" ] || [ -e "$bootstrap_file" ]; then
    echo "Instalação existente detectada; nenhuma alteração foi feita." >&2
    exit 1
fi
if ss -ltn | grep -q ':8012 '; then
    echo "A porta 8012 já está em uso." >&2
    exit 1
fi

if ! id certgen >/dev/null 2>&1; then
    useradd --system --user-group --no-create-home --shell /usr/sbin/nologin certgen
fi
install -d -m 0700 -o certgen -g certgen "$data_dir" "$data_dir/private"
install -d -m 0700 -o root -g root /etc/adrock

git clone --branch main --depth 1 https://github.com/adrockmkt/adrock-gerador-certificados.git "$app_dir"
python3 -m venv "$app_dir/.venv"
"$app_dir/.venv/bin/python" -m pip install --no-cache-dir -e "${app_dir}[production]"
# O umask 077 protege os segredos, mas o usuário de serviço precisa ler o código
# e atravessar os diretórios do ambiente virtual. Não altera /etc nem /var/lib.
chmod -R a+rX "$app_dir"
runuser -u certgen -- test -x "$app_dir/.venv/bin/gunicorn"
cd "$app_dir"
"$app_dir/.venv/bin/python" -m unittest discover -s tests -q

SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
cat > "$env_file" <<EOF
SECRET_KEY=$SECRET_KEY
DATABASE_URL=sqlite:////var/lib/gerador-certificados/certificates.sqlite3
PRIVATE_STORAGE_DIR=/var/lib/gerador-certificados/private
APPLICATION_ROOT=/gerador-certificados
TRUSTED_HOSTS=mobiledelivery.com.br,www.mobiledelivery.com.br
SESSION_COOKIE_SECURE=1
EOF
chmod 0600 "$env_file"
unset SECRET_KEY

set -a
source "$env_file"
set +a
"$app_dir/.venv/bin/python" - <<'PY'
import os
import secrets
from pathlib import Path

from app import create_app
from app.auth.service import create_admin

app = create_app()
password = secrets.token_urlsafe(30)
create_admin(app, "admin", password)
fd = os.open("/root/gerador-certificados-bootstrap.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as file:
    file.write("Usuário: admin\nSenha inicial: " + password + "\n")
app.extensions["db_engine"].dispose()
PY
chown -R certgen:certgen "$data_dir"

install -m 0644 "$app_dir/deploy/gerador-certificados.service" /etc/systemd/system/gerador-certificados.service
systemctl daemon-reload
systemctl enable --now gerador-certificados.service
systemctl is-active --quiet gerador-certificados.service

status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
    -H 'Host: mobiledelivery.com.br' \
    -H 'X-Forwarded-Prefix: /gerador-certificados' \
    -H 'X-Forwarded-Proto: https' \
    http://127.0.0.1:8012/login)"
if [ "$status" != 200 ]; then
    echo "Serviço iniciou, mas /login retornou HTTP $status." >&2
    exit 1
fi
echo "Aplicação instalada; serviço ativo e login local HTTP 200."
