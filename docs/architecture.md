# Arquitectura

> Documento vivo: se actualiza al cierre de cada fase. El diseño original está
> en [`proyecto-deteccion-personas.md`](../proyecto-deteccion-personas.md) y las
> decisiones puntuales en [`adr/`](adr/README.md).

## Estilo: ports & adapters (hexagonal)

El paquete `backend/src/secuh/core/` contiene el dominio puro:

- `models.py` — entidades inmutables: `Camera` (con `Schedule` y zona),
  `Event`, `Detection`, `Notification`.
- `ports.py` — interfaces que el dominio necesita del mundo exterior:
  `VideoSource`, `MotionDetector`, `PersonDetector`, `Notifier`, `EventStore`,
  `SnapshotStore`, `ClipRecorder`, `Clock`.
- `pipeline.py` — orquestación por frame: horario activo → movimiento →
  detección → umbral de confianza → zona → cooldown → evento.
- `handler.py` — qué hacer con un evento: captura → notificar → clip →
  persistir, tolerando fallos parciales en cada paso.
- `geometry.py` — punto-en-polígono para las zonas (sin OpenCV).

**Regla:** `core/` no importa OpenCV, Ultralytics, FastAPI ni SQLAlchemy.
Los adaptadores (`detection/`, `video/`, `notifications/`, `storage/`, y más
adelante `db/`, `api/`) implementan los puertos. Los tests unitarios del
pipeline corren con fakes, sin cámara ni modelo (`backend/tests/unit/`).

## Flujo en ejecución (por cámara)

```
OpenCvVideoSource ──frames──▶ CameraWorker  (hilo por cámara; métricas, último frame)
                               ├─▶ FileClipRecorder.push_frame  (buffer circular pre-evento)
                               └─▶ DetectionPipeline.process_frame  (a analysis_fps)
                                     horario activo → movimiento (MOG2, enmascarado a la zona)
                                     → YOLO person → umbral → centro-en-zona → cooldown
                                     └─ Event ─▶ EventHandler
                                                  1. FileSnapshotStore (JPEG)
                                                  2. Notifier(s) — canales de la cámara
                                                     (ntfy / Telegram) o el global
                                                  3. FileClipRecorder.record_event (pre+post)
                                                  4. EventStore (BD; JSONL en modo standalone)
RetentionJob (hilo de fondo): borra evidencia > N días
```

Decisión de resiliencia: cada paso del handler tolera el fallo de los demás
(sin captura se notifica sin imagen; sin canal disponible el evento igual se
persiste con `notified: false`).

## Modo servidor

Un solo proceso (`uvicorn --factory secuh.api.app:create_app`) sirve el panel,
la API y corre la detección:

```
FastAPI (api/)                         CameraSupervisor (runtime/)
  panel estático en /                    cada 5s relee cámaras+canales de la BD:
  auth: cookie HttpOnly + rate limit       armada sin worker         -> arranca
  CRUD cámaras y canales ─escribe─▶ BD ─▶  desarmada/borrada         -> detiene
  eventos + evidencia (autenticado)        config/canales cambiaron  -> reinicia
  /api/stream (SSE, estado en vivo)        hilo muerto               -> reinicia
                                         y vigila la señal: cámara armada sin
                                         frames -> notificación "sin señal"
```

- Un worker (hilo) por cámara armada; YOLO se carga una vez por proceso y se
  comparte con un lock (`ThreadSafeDetector`); cola/pool diferidos (ADR 0004).
- Notificadores por cámara construidos desde sus canales en BD
  (`notifications/factory.py`); sin canales asignados se usa el global.
- Eventos → `DbEventStore` (PostgreSQL en producción, SQLite en dev/tests).
- Migraciones con Alembic (`backend/migrations/`); el contenedor corre
  `alembic upgrade head` antes de uvicorn.
- El modo standalone de Fase 1 (`python -m secuh --config config.yaml`) sigue
  disponible para instalaciones mínimas sin panel ni BD.
- `run.py` (raíz del repo) levanta este mismo modo servidor (backend + panel)
  como procesos nativos, con SQLite, sin Docker — recomendado en Windows por
  la limitación de red de Docker Desktop con cámaras RTSP+UDP (ADR 0005).

## Seguridad

- Panel autenticado desde su primera versión: cookie de sesión HttpOnly
  (JWT firmado con `SECUH_SECRET_KEY`), contraseñas con argon2, rate limiting
  de login por IP.
- La evidencia (capturas/clips) se sirve solo con sesión, nunca como estático.
- Secretos solo por entorno (`SECUH_*`); las URLs de cámara (pueden llevar
  credenciales RTSP) y los tokens de canales salen **siempre redactados** de
  la API y de los logs.
- Retención automática de evidencia (`RetentionJob`) como práctica de
  privacidad; obligaciones de campo en `runbook.md` §7.

## Estado por fase

- **Fase 0 (hecha):** esqueleto + puertos + pipeline/cooldown testeados +
  benchmark de hardware (`spike/benchmark.py`, ADR 0003).
- **Fase 1 (hecha, pendiente validación con celular real):** adaptadores
  reales (MOG2, YOLO, captura con reconexión, ntfy, clips, retención),
  config YAML validada, logging JSON, entry point `python -m secuh`.
- **Fase 2 (hecha, pendiente `docker compose up` con PostgreSQL):** BD +
  Alembic, API FastAPI autenticada, supervisor con reconciliación y
  auto-reinicio, panel React (`frontend/`), `deploy/` con compose.
- **Fase 3 (hecha):** horarios por cámara (con cruce de medianoche), zonas de
  detección (polígono aplicado al movimiento y a las detecciones, editor
  visual sobre el preview), alerta de cámara sin señal.
- **Fase 4 (hecha):** canales de notificación en BD (ntfy + Telegram),
  botón de prueba, asignación por cámara, secretos redactados en la API,
  reconstrucción de notificadores en caliente.
- **Fase 5 (hecha con alcance del ADR 0004):** SSE de estado en vivo,
  métricas por worker; cola de inferencia y ByteTrack diferidos.
- **Fase 6 (hecha):** imagen única con panel empaquetado, runbook, guía de
  IP Webcam, checklist de instalación, changelog y versionado.
