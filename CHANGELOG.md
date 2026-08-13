# Changelog

Versionado semántico. Las migraciones de BD se aplican automáticamente al
actualizar (ver `docs/runbook.md` §4).

## 0.6.2 — 2026-08-13

Cierre de los huecos que impedían cumplir el criterio de salida de la Fase 6:
instalar y configurar siguiendo solo la documentación.

### Corregido
- **El paquete no se construía en un entorno limpio:** `backend/pyproject.toml`
  declaraba `readme = "../README.md"` y hatchling rechaza rutas fuera del
  directorio del proyecto, así que `uv sync` fallaba al construir `secuh`
  (visible en el CI de GitHub Actions, donde el entorno siempre es nuevo; en
  local pasaba desapercibido porque el paquete ya estaba instalado). Se quitó
  el campo — el paquete no se publica — y con él el `COPY README.md`
  del `Dockerfile.backend`, que solo existía para sortear esa referencia.
- **Los ajustes operativos no llegaban al contenedor:** compose entrega
  únicamente las variables listadas en su bloque `environment:`, así que
  `SECUH_RETENTION_DAYS` (que el checklist manda acordar con el dueño) y
  `SECUH_IMGSZ` (la palanca de CPU del runbook) no hacían nada por más que se
  definieran en `.env`. Ahora se pasan de forma explícita, junto con la
  duración de los clips y el TTL de sesión.
- **El backend no tenía `healthcheck`** pese a que el runbook mandaba
  comprobar si estaba `healthy`. Añadido contra `GET /api/health`, con tests
  que fijan que ese endpoint siga siendo público.

### Añadido
- `docs/runbook.md` §8: referencia de las variables `SECUH_*` que se tocan en
  una instalación, con sus valores por defecto y cómo se aplican en cada modo
  de ejecución.
- `docs/checklist-instalacion.md`: cubre las dos vías de instalación (Docker
  sobre Linux / nativa con `run.py` en Windows) y añade la sección "Arranque
  desatendido" — `run.py` **no arranca solo al encender el equipo**, así que
  la prueba de reinicio del checklist no se podía aprobar sin configurarlo a
  mano en el Programador de tareas.

### Documentación
- `docs/architecture.md` estaba congelado en un estado anterior a la 0.6.1:
  daba como pendientes validaciones (celular real, `docker compose up` con
  PostgreSQL) que ya se habían hecho el 2026-07-16.
- README y runbook advierten que en Windows `uv` suele no estar en el PATH
  (`python -m uv ...`), y el README ya no dice "fases completadas" sin
  matizar los dos pendientes operativos.

## 0.6.1 — 2026-07-16

Endurecimiento tras la primera puesta en marcha real (Docker + cámaras físicas).

### Añadido
- `run.py`: levanta backend + panel juntos en local **sin Docker**, con
  SQLite. Genera `backend/.env` (clave de sesión + contraseña de admin) en el
  primer arranque. Ver README y ADR 0005 (por qué es la vía recomendada en
  Windows).
- `docs/adr/0005-ejecucion-nativa-vs-docker.md`: por qué Docker Desktop en
  Windows no es viable con cámaras RTSP que transmiten por UDP.

### Corregido
- **Crítico:** el modelo YOLO no cargaba dentro del contenedor Docker
  (`PermissionError` al intentar descargarlo como usuario no-root en
  runtime) — ninguna cámara podía detectar nada. Ahora se pre-descarga en el
  build de la imagen.
- **Imagen Docker no compilaba:** `torch` resolvía por defecto la build CUDA
  completa de NVIDIA (~2.5 GB) aunque no hay GPU; ahora se fija al índice
  CPU-only oficial de PyTorch (~150 MB). `backend/pyproject.toml` declara
  `torch`/`torchvision` como dependencias directas para que la redirección de
  índice de `uv` se aplique de forma confiable.
- El build de Docker no copiaba `README.md` (referenciado por
  `pyproject.toml`) ni podía re-sincronizar el entorno en runtime (usuario
  no-root vs. venv creado como root); ahora invoca los binarios del venv
  directamente.
- **Borrar una cámara con eventos registrados crasheaba** con
  `IntegrityError: NOT NULL constraint failed: events.camera_id`. Faltaba
  `cascade="all, delete-orphan"` en la relación `CameraRow.events`.
- Las alertas de "cámara sin señal"/detección de eventos no llegaban a ntfy
  aunque el botón de prueba funcionara: recordatorio de que un canal debe
  **asignarse explícitamente a cada cámara** (Editar cámara → Canales de
  notificación); sin canales propios, la cámara usa el canal global del
  servidor (consola por defecto). Documentado en el runbook.

### Conocido (sin arreglo de nuestro lado)
- Cámaras RTSP que solo transmiten por UDP pueden fallar dentro de Docker
  Desktop (Windows/Mac): el contenedor no puede enrutar de vuelta los
  paquetes UDP de la cámara (no hay forma de mapear un puerto negociado al
  vuelo). Con `network_mode: host` tampoco funciona en Windows, porque ese
  modo comparte la red de la VM de Docker Desktop, no la del host real. Usar
  `run.py` (ejecución nativa) evita el problema por completo. Ver ADR 0005.
- Algunas cámaras RTSP de firmware genérico no negocian bien el transporte
  con el cliente RTSP de FFmpeg (que usa OpenCV) aunque sí funcionan con VLC
  (motor `live555`, más tolerante). No tiene arreglo de configuración
  conocido; alternativas: revisar si la cámara expone un path RTSP
  alternativo, o interponer un relay como `mediamtx`.

## 0.6.0 — 2026-07-15

Fases 3–6 del plan.

### Añadido
- Horarios de vigilancia por cámara: siempre / nocturno (22:00–06:00) /
  personalizado, con soporte de rangos que cruzan medianoche.
- Zonas de detección: polígono por cámara dibujado sobre el preview en el
  panel; movimiento y personas fuera de la zona se ignoran.
- Alerta de cámara sin señal (y de recuperación) por los canales de la cámara.
- Canales de notificación gestionados desde el panel: ntfy y **Telegram**,
  con botón "Enviar prueba" y asignación por cámara.
- Estado en tiempo real en el panel (SSE): armado/señal y eventos nuevos sin
  refrescar.
- Métricas por cámara (fps efectivos, frames, eventos, uptime) en la API.
- El backend sirve el panel compilado: producto completo en una sola URL.
- Documentación operativa: runbook, guía IP Webcam, checklist de instalación.
- Migraciones 0002 (horarios/zonas) y 0003 (canales).

### Cambiado
- Los eventos se notifican por los canales asignados a la cámara; sin
  canales propios se usa el global del servidor (`SECUH_NTFY_TOPIC`/consola).

## 0.2.0 — 2026-07-14

Fase 2: PostgreSQL + Alembic, API FastAPI autenticada (cookie HttpOnly,
argon2, rate limiting), supervisor de workers con armado/desarmado en
caliente y reinicio de workers muertos, panel React, docker compose.

## 0.1.0 — 2026-07-14

Fases 0–1: benchmark de hardware, núcleo hexagonal testeado, MVP standalone
(`python -m secuh`): cámara → movimiento → YOLO → cooldown → ntfy + clips +
retención.
