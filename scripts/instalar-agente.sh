#!/bin/bash
# Instala un agente de launchd que arranca el backend al iniciar sesión y lo reinicia si se cae.
# El backend sirve también la interfaz en http://localhost:8000 (solo accesible desde este Mac).
# Desinstalar: scripts/desinstalar-agente.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.autos-alemanes.costa-del-sol"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/autos-alemanes.log"
UID_NUM="$(id -u)"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

[ -x "$ROOT/backend/.venv/bin/uvicorn" ] || { echo "Falta el entorno de Python: cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2; exit 1; }

# La interfaz compilada la sirve el backend; dist/ no se versiona, así que se genera aquí si falta.
if [ ! -f "$ROOT/frontend/dist/index.html" ]; then
  echo "Compilando la interfaz (npm run build)..."
  (cd "$ROOT/frontend" && npm install --silent && npm run build --silent)
fi

# Si ya hay un backend a mano en el puerto 8000, el agente no podría arrancar.
if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1 && ! launchctl print "gui/$UID_NUM/$LABEL" >/dev/null 2>&1; then
  echo "El puerto 8000 está ocupado por otro proceso. Páralo antes (p. ej. Ctrl+C en su terminal) y vuelve a ejecutar esto." >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$ROOT/backend/.venv/bin/uvicorn</string>
    <string>app.main:app</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>8000</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT/backend</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key><string>$HOME</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF

# Recarga si ya estaba instalado.
launchctl bootout "gui/$UID_NUM/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID_NUM" "$PLIST"

for _ in $(seq 1 30); do
  curl -fs http://localhost:8000/api/health >/dev/null 2>&1 && { echo "Agente instalado y backend en marcha: http://localhost:8000"; echo "Registro: $LOG"; exit 0; }
  sleep 1
done
echo "El agente se instaló pero el backend no respondió en 30 s. Mira el registro: $LOG" >&2
exit 1
