#!/bin/bash
# Imprime cómo conectar el servidor MCP (backend/mcp_server.py) a Claude Desktop y a Claude Code.
# Las rutas se calculan desde la ubicación del repo; no se modifica ninguna configuración.
set -e
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
PY="$RAIZ/backend/.venv/bin/python"
SERVIDOR="$RAIZ/backend/mcp_server.py"

if [ ! -x "$PY" ]; then echo "Falta el entorno virtual: cd backend && python3 -m venv .venv && pip install -r requirements.txt"; exit 1; fi

cat <<TXT
== Claude Code (una línea) ==
claude mcp add autos-alemanes -e AUTOS_USUARIO=TU_USUARIO -e AUTOS_PASSWORD=TU_CONTRASEÑA -- "$PY" "$SERVIDOR"

== Claude Desktop ==
Añade esto a "mcpServers" en ~/Library/Application Support/Claude/claude_desktop_config.json y reinicia Claude Desktop:

    "autos-alemanes": {
      "command": "$PY",
      "args": ["$SERVIDOR"],
      "env": { "AUTOS_USUARIO": "TU_USUARIO", "AUTOS_PASSWORD": "TU_CONTRASEÑA" }
    }

La app exige login: pon el usuario y la contraseña que creaste con "python -m app.maintenance crear-usuario".
Si la app no está en este Mac, añade también AUTOS_API_URL con su dirección.

El backend debe estar en marcha (scripts/abrir.command o el agente de launchd).
TXT
