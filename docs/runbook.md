# Runbook — operación de secuh

Procedimientos para instalar, operar, diagnosticar y actualizar el sistema.

---

## 1. Instalación

### 1.1 Equipo del cliente (Linux, producción) — Docker

Requisitos: Docker + Docker Compose, red local con las cámaras/celulares.

```bash
git clone <repo> && cd secuh/deploy
cp .env.example .env
# Editar .env: POSTGRES_PASSWORD, SECUH_SECRET_KEY (48+ chars aleatorios),
# SECUH_ADMIN_PASSWORD. Generar clave:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up -d --build
```

Panel: `http://<ip-del-equipo>:8000` — usuario `admin`, contraseña la de
`SECUH_ADMIN_PASSWORD`. Ver `checklist-instalacion.md` para la puesta en
marcha completa en sitio.

### 1.2 Windows (desarrollo, pruebas, o instalación de un solo equipo) — nativo

**No usar Docker Desktop en Windows si hay cámaras RTSP de por medio**: su
red virtualizada (WSL2/Hyper-V) no puede recibir el vídeo cuando la cámara
transmite por UDP (ver ADR 0005). En Windows, usar `run.py`:

```bash
cd backend  && uv sync --all-groups && cd ..
cd frontend && npm install         && cd ..
python run.py
```

Levanta backend + panel juntos con SQLite; genera `backend/.env` con
credenciales la primera vez (se imprimen una sola vez en pantalla).
`Ctrl+C` apaga ambos procesos. Para volver a arrancar en otra sesión, mismo
comando — reutiliza `backend/.env` y `backend/dev.db` ya existentes.

## 2. Diagnóstico rápido

| Síntoma | Revisar |
|---|---|
| Panel no carga | `docker compose ps` (¿backend healthy?), `docker compose logs backend --tail 50` |
| Cámara "sin señal" | ¿El celular tiene IP Webcam abierta y pantalla encendida? ¿Misma red WiFi? Probar la URL del stream en un navegador. Si es una cámara RTSP y corres en **Docker Desktop (Windows)**: puede ser la limitación de red de §2.1 — probar con `run.py` (nativo) para descartarlo |
| El botón "Enviar prueba" del canal funciona, pero **los eventos reales no notifican** | El canal debe **asignarse a la cámara** (Editar cámara → Canales de notificación). Sin canales propios asignados, la cámara usa el canal global del servidor (consola por defecto, o `SECUH_NTFY_TOPIC` si está definida) — no los canales creados en el panel. Verificar en `GET /api/cameras` que `channel_ids` no esté vacío |
| No llegan notificaciones (canal sí asignado) | Panel → Canales → **Enviar prueba**. Si falla: revisar topic/token. Evento con "sin notificar" en el feed = canal caído en ese momento |
| Falsas alarmas | Subir sensibilidad de la cámara (panel) o dibujar zona de detección excluyendo calle/vegetación |
| No detecta | Bajar sensibilidad; verificar horario de vigilancia de la cámara; verificar que está **armada** |
| CPU al 100% sostenido | Ver métricas de la cámara en la API (`/api/cameras`): si `achieved_analysis_fps` < objetivo, bajar `analysis_fps` o `imgsz` (`SECUH_IMGSZ=480`) |

Los logs son JSON por línea: `docker compose logs backend | grep '"level": "ERROR"'`.
En modo nativo (`run.py`), los logs salen directo en la terminal donde corre.

### 2.1 Cámaras RTSP que no conectan

Dos causas distintas, con síntomas parecidos ("sin señal") pero arreglos
distintos:

1. **Docker Desktop en Windows/Mac + cámara que transmite por UDP.** El
   contenedor no puede recibir el vídeo de vuelta (no hay NAT que sepa
   enrutarlo). Síntoma en los logs: la fuente "abre" pero nunca llegan
   frames, o falla directamente. **Arreglo:** correr con `run.py` (nativo) en
   vez de Docker — ver ADR 0005. En un servidor Linux real esto no ocurre.
2. **Incompatibilidad de firmware de la cámara con el cliente RTSP de
   FFmpeg** (el que usa OpenCV). Síntoma en los logs:
   `[rtsp @ ...] Nonmatching transport in server reply`, tanto en Docker como
   nativo, con TCP y con UDP. Para confirmar: probar el mismo link RTSP con
   VLC (Media → Abrir ubicación de red) — si VLC conecta pero secuh no, es
   esto. VLC usa un motor RTSP distinto (`live555`) más tolerante que
   FFmpeg con respuestas de servidor no estándar. **Sin arreglo de
   configuración conocido.** Alternativas: revisar el manual de la cámara
   por un path RTSP alterno (a veces hay uno "para NVR de terceros" que
   negocia distinto del path ONVIF por defecto), o interponer un relay como
   [mediamtx](https://github.com/bluenviron/mediamtx) que sí logre conectar
   con la cámara y republique el stream en un formato que OpenCV sí lea.

## 3. Respaldo y restauración

Respaldar (BD + evidencia):

```bash
docker compose exec db pg_dump -U secuh secuh > backup-$(date +%F).sql
docker run --rm -v deploy_secuh-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/evidencia-$(date +%F).tgz /data
```

Restaurar:

```bash
docker compose exec -T db psql -U secuh secuh < backup-YYYY-MM-DD.sql
```

La evidencia expira sola a los `SECUH_RETENTION_DAYS` días (default 7):
normalmente basta respaldar la BD.

## 4. Actualización de versión

```bash
git pull
cd deploy && docker compose up -d --build   # aplica migraciones al arrancar
```

Las migraciones de BD corren automáticamente (`alembic upgrade head`) antes
de arrancar el servidor. Ver `CHANGELOG.md` antes de actualizar.

## 5. Rotación de secretos

- **Contraseña del panel:** (hasta que exista UI de usuarios) borrar el
  usuario y reiniciar con nueva `SECUH_ADMIN_PASSWORD`:
  `docker compose exec db psql -U secuh secuh -c "DELETE FROM users;"` y
  `docker compose restart backend`.
- **SECUH_SECRET_KEY:** cambiarla en `.env` y `docker compose up -d` —
  invalida todas las sesiones activas (los usuarios vuelven a loguearse).
- **Topic ntfy / token Telegram:** crear el canal nuevo en el panel, probarlo,
  asignarlo a las cámaras y borrar el viejo.

## 6. Prueba de resistencia (antes de entregar una instalación)

1. Armar todas las cámaras del sitio con su configuración final.
2. Dejar corriendo 72 h con actividad normal del negocio.
3. Cada 24 h anotar: RSS del contenedor (`docker stats backend --no-stream`),
   `achieved_analysis_fps` y `uptime_seconds` por cámara (`GET /api/cameras`).
4. Criterio de aceptación: sin reinicios inesperados (`uptime_seconds` crece
   monótono), RSS estable (±15%), fps efectivos ≥ 80% del objetivo, y las
   notificaciones de prueba diarias llegan.

## 7. Privacidad y obligaciones

- Colocar avisos visibles de videovigilancia según la normativa local.
- Orientar cámaras y **zonas de detección** hacia la propiedad; excluir vía
  pública y propiedades de terceros.
- La retención de evidencia es automática (`SECUH_RETENTION_DAYS`); no
  aumentar sin necesidad ni consentimiento del dueño.
- El acceso al panel es personal: no compartir la contraseña; una instalación
  = un responsable identificado.
