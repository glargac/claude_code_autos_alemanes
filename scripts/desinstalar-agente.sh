#!/bin/bash
# Quita el agente de launchd: el backend deja de arrancar solo y se detiene. No toca la base de datos.
set -euo pipefail

LABEL="com.autos-alemanes.costa-del-sol"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
rm -f "$PLIST"
echo "Agente desinstalado. Para usar la app a mano: scripts/abrir.command"
