# Despliegue en un servidor (VPS)

La app corre en un servidor siempre encendido (backend + interfaz + base de datos) y se usa desde el navegador o instalada como app en el móvil (PWA). Caddy pone HTTPS con certificado automático.

```
móvil / PC ──HTTPS──► Caddy (80/443) ──► app (FastAPI + Chromium, :8000 interno)
                                          └─ volumen «datos»: autos.db, fotos de revisiones, copias
```

## ⚠ Riesgo a comprobar antes de fiarse

Los portales pueden tratar distinto a una IP de centro de datos (un VPS) que a una doméstica: kleinanzeigen o AutoScout24 podrían devolver bloqueos (403) o CAPTCHAs. **No está verificado.** Prueba una sync completa el primer día; si falla con «bloqueo», la app lo muestra como error de esa fuente y las demás siguen. Antes de migrar tus datos, conviene comprobarlo con un usuario de prueba.

## 1. Servidor

1. Cuenta en [Hetzner Cloud](https://www.hetzner.com/cloud) → *Add server*: ubicación Núremberg o Falkenstein, imagen **Ubuntu 24.04**, tipo con **2 vCPU y 4 GB de RAM como mínimo** (hoy, serie CX o CPX de unos 4–8 €/mes; los nombres cambian). Añade tu **clave SSH**. Opcional: activar las copias automáticas del proveedor (+20 %).
2. **Dominio:** crea un registro DNS `A` (`autos.tudominio.com → IP del servidor`). Sin dominio propio sirve un subdominio gratuito de [DuckDNS](https://www.duckdns.org). Hace falta HTTPS: el móvil no instala la PWA por HTTP.

## 2. Preparar la máquina (una vez)

```bash
ssh root@IP_DEL_SERVIDOR
apt update && apt -y upgrade
adduser deploy && usermod -aG sudo deploy          # usuario sin root para el día a día
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy   # reutiliza tu clave SSH
curl -fsSL https://get.docker.com | sh && usermod -aG docker deploy
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw --force enable
apt -y install unattended-upgrades                  # parches de seguridad automáticos
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile \
  && echo '/swapfile none swap sw 0 0' >> /etc/fstab   # colchón para Chromium
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config && systemctl reload ssh
```

Desde ahora entra como `deploy` (`ssh deploy@IP`). Docker publica los puertos por su cuenta, saltándose `ufw`: por eso en `docker-compose.yml` solo se publican 80 y 443 y la app (`:8000`) no.

## 3. Arrancar

```bash
git clone https://github.com/TU_USUARIO/autos-alemanes-costa-del-sol.git && cd autos-alemanes-costa-del-sol
cp deploy/env.example .env && chmod 600 .env && nano .env     # DOMINIO, TZ y, si quieres IA, la clave
docker compose up -d --build                                  # la primera vez tarda 5-10 min
docker compose logs -f app                                    # «Application startup complete» → Ctrl+C
```

Abre `https://tu-dominio`. Caddy tarda unos segundos en conseguir el certificado la primera vez.

## 4. Usuarios y datos

**Empezar de cero:** crea cada usuario (te pide la contraseña, mínimo 8 caracteres):

```bash
docker compose exec app python -m app.maintenance crear-usuario gilbert
docker compose exec app python -m app.maintenance crear-usuario amigo
```

**Llevar tus datos del Mac** (coches, favoritos, notas, revisiones, tu usuario y ajustes). Desde el Mac:

```bash
scp backend/data/autos.db deploy@IP:/tmp/autos.db
# solo si tienes fotos de revisiones:  tar czf /tmp/inspections.tgz -C backend/data inspections && scp /tmp/inspections.tgz deploy@IP:/tmp/
```

En el servidor (dentro del repo):

```bash
docker compose stop app
docker compose cp /tmp/autos.db app:/app/backend/data/autos.db
docker compose run --rm --no-deps --user root app chown app:app /app/backend/data/autos.db
docker compose start app
docker compose exec app python -m app.maintenance listar-usuarios   # tu usuario ya existe, con su contraseña
docker compose exec app python -m app.maintenance crear-usuario amigo
```

Después, en el Mac, `scripts/desinstalar-agente.sh`: así no hay dos copias que se desincronicen. Los usuarios entran con su nombre; el amigo verá la pantalla de bienvenida (sus preferencias) y su sync empezará al aceptar.

## 5. Instalar en el móvil

- **iPhone (Safari):** abrir la dirección → Compartir → *Añadir a pantalla de inicio*.
- **Android (Chrome):** menú ⋮ → *Instalar aplicación*.

## 6. Copias de seguridad (no te saltes esto)

Lo único insustituible son `autos.db` y las fotos. Una copia diaria, consistente aunque la app esté escribiendo:

```bash
crontab -e      # y añade:
0 4 * * *  /home/deploy/autos-alemanes-costa-del-sol/deploy/backup.sh >> /home/deploy/autos-backup.log 2>&1
```

Eso guarda las últimas 14 copias en el volumen y en `/var/backups/autos` **del mismo servidor**. Para que sirva ante la pérdida del servidor, copia también fuera: activa las copias del proveedor y/o descomenta `rclone`/`rsync` al final de `backup.sh`. Prueba una vez que `deploy/backup.sh` funciona y que sabes restaurar:

```bash
# restaurar (la app parada): sustituye la base por una copia
docker compose stop app
docker compose cp /var/backups/autos/autos-AAAAMMDD-HHMMSS.db app:/app/backend/data/autos.db
docker compose run --rm --no-deps --user root app chown app:app /app/backend/data/autos.db
docker compose start app
```

## 7. Día a día

| Qué | Comando |
|---|---|
| Actualizar a una versión nueva | `git pull && docker compose up -d --build` (las columnas nuevas de la base se añaden solas) |
| Ver el registro | `docker compose logs -f app` |
| Reiniciar | `docker compose restart app` |
| Cambiar una contraseña | `docker compose exec app python -m app.maintenance cambiar-password NOMBRE` |
| Memoria y CPU | `docker stats` |

- La **sync diaria** (Ajustes → Sincronización) vale ahora: el servidor no se duerme. La hora es la de `TZ` (por defecto Europa/Berlín).
- Solo corre **una sync a la vez**: si ambos sincronizáis, el segundo espera su turno.
- La **clave de IA es del servidor** y la usan todos los usuarios: aún no hay límite de análisis por usuario.
- Los **certificados** viven en el volumen `caddy_data`: no lo borres (Let's Encrypt limita las emisiones).
