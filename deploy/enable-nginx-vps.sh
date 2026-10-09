#!/usr/bin/env bash
set -euo pipefail

vhost=/etc/nginx/sites-enabled/agente-palavras-adrock
snippet=/etc/nginx/snippets/gerador-certificados.conf
backup=/root/gerador-certificados-nginx-before.conf
app_dir=/home/adrock/apps/gerador-certificados

if [ "$(id -u)" -ne 0 ]; then
    echo "Execute como root." >&2
    exit 1
fi
if [ -e "$snippet" ] || [ -e "$backup" ]; then
    echo "Configuração ou backup anterior detectado; nenhuma alteração foi feita." >&2
    exit 1
fi
systemctl is-active --quiet gerador-certificados.service
cp -a "$vhost" "$backup"
install -m 0644 "$app_dir/deploy/nginx-gerador-certificados.conf" "$snippet"

python3 - <<'PY'
from pathlib import Path

path = Path("/etc/nginx/sites-enabled/agente-palavras-adrock")
text = path.read_text()
anchor = "    server_name mobiledelivery.com.br www.mobiledelivery.com.br;\n"
if text.count(anchor) != 1 or "gerador-certificados.conf" in text:
    raise SystemExit("Vhost inesperado; inclusão não realizada.")
text = text.replace(anchor, anchor + "    include /etc/nginx/snippets/gerador-certificados.conf;\n", 1)
path.write_text(text)
PY

if ! nginx -t; then
    cp -a "$backup" "$vhost"
    rm -f "$snippet"
    echo "Configuração anterior restaurada após falha no nginx -t." >&2
    exit 1
fi
systemctl reload nginx
echo "NGINX recarregado; backup em $backup."
