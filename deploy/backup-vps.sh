#!/usr/bin/env bash
set -euo pipefail
umask 077

if [ "$(id -u)" -ne 0 ]; then
    echo "Execute como root." >&2
    exit 1
fi

service=gerador-certificados.service
archive_dir=/var/backups/gerador-certificados
data_dir=/var/lib/gerador-certificados
install -d -m 0700 -o root -g root "$archive_dir"
test -f "$data_dir/certificates.sqlite3"

was_active=0
if systemctl is-active --quiet "$service"; then
    was_active=1
    systemctl stop "$service"
fi
restore_service() {
    if [ "$was_active" -eq 1 ]; then
        systemctl start "$service"
    fi
}
trap restore_service EXIT

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
temp_archive="$(mktemp "$archive_dir/.backup-XXXXXXXX")"
tar -C /var/lib -czf "$temp_archive" gerador-certificados
tar -tzf "$temp_archive" >/dev/null
archive="$archive_dir/backup-$stamp.tar.gz"
mv "$temp_archive" "$archive"
chmod 0600 "$archive"
find "$archive_dir" -maxdepth 1 -type f -name 'backup-*.tar.gz' -mtime +14 -delete
echo "Backup criado: $archive"
