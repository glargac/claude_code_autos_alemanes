#!/bin/bash
# Doble clic para abrir la app: arranca el backend si no está en marcha y abre http://localhost:8000.
# (Con el agente instalado, el backend ya estará arrancado y esto solo abre el navegador.)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="http://localhost:8000"
LABEL="com.autos-alemanes.costa-del-sol"
LOG="$HOME/Library/Logs/autos-alemanes.log"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

up() { curl -fs "$URL/api/health" >/dev/null 2>&1; }

if ! up; then
  if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
    launchctl kickstart "gui/$(id -u)/$LABEL"
  else
    [ -f "$ROOT/frontend/dist/index.html" ] || (cd "$ROOT/frontend" && npm install --silent && npm run build --silent)
    mkdir -p "$HOME/Library/Logs"
    (cd "$ROOT/backend" && nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 >>"$LOG" 2>&1 &)
  fi
  for _ in $(seq 1 30); do up && break; sleep 1; done
fi

up && open "$URL" || { echo "El backend no arrancó. Mira el registro: $LOG"; read -r -p "Pulsa Enter para cerrar"; }
