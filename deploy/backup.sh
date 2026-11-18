#!/bin/bash
# Copia de seguridad diaria: base de datos + fotos de las revisiones. Pensado para el cron del servidor:
#   0 4 * * *  /ruta/al/repo/deploy/backup.sh >> /var/log/autos-backup.log 2>&1
# 1) Dentro del contenedor, copia consistente a /app/backend/data/backups (se conservan las últimas 14).
# 2) La saca del volumen a DESTINO en el servidor. Para tenerla FUERA del servidor, descomenta rclone/rsync al final
#    (o activa las copias de seguridad de tu proveedor): una copia en la misma máquina no protege si se pierde la máquina.
set -euo pipefail
cd "$(dirname "$0")/.."
DESTINO="${DESTINO:-/var/backups/autos}"
mkdir -p "$DESTINO"

docker compose exec -T app python -m app.maintenance backup --conservar 14
docker compose cp app:/app/backend/data/backups/. "$DESTINO"/

# rclone sync "$DESTINO" remoto:autos-backups
# rsync -az --delete "$DESTINO"/ usuario@otro-servidor:autos-backups/
echo "Copia lista en $DESTINO ($(date))"
