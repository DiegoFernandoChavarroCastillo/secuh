# Arquitectura

> Documento vivo: se actualiza al cierre de cada fase. El diseño original está
> en [`proyecto-deteccion-personas.md`](../proyecto-deteccion-personas.md) y las
> decisiones puntuales en [`adr/`](adr/README.md).

## Estilo: ports & adapters (hexagonal)

El paquete `backend/src/secuh/core/` contiene el dominio puro:

- `models.py` — entidades inmutables: `Camera` (con `Schedule` y zona),
  `Event`, `Detection`, `SceneObject`, `Notification`.
- `ports.py` — interfaces que el dominio necesita del mundo exterior:
  `VideoSource`, `MotionDetector`, `PersonDetector`, `SceneInspector`,
  `Notifier`, `EventStore`, `SnapshotStore`, `RawSnapshotStore`,
  `ClipRecorder`, `Clock`.
- `pipeline.py` — orquestación por frame: horario activo → movimiento →
  detección → umbral de confianza → zona → cooldown → evento.
- `handler.py` — qué hacer con un evento: describir la escena → captura →
  notificar → clip → persistir, tolerando fallos parciales en cada paso.
- `geometry.py` — punto-en-polígono para las zonas (sin OpenCV).

**Regla:** `core/` no importa OpenCV, Ultralytics, FastAPI ni SQLAlchemy.
Los adaptadores (`detection/`, `video/`, `notifications/`, `storage/`, `db/`,
`api/`) implementan los puertos. Los tests unitarios del pipeline corren con
fakes, sin cámara ni modelo (`backend/tests/unit/`).

## Flujo en ejecución (por cámara)

```
OpenCvVideoSource ──frames──▶ CameraWorker  (hilo por cámara; métricas, último frame)
                               ├─▶ FileClipRecorder.push_frame  (buffer circular pre-evento)
                               └─▶ DetectionPipeline.process_frame  (a analysis_fps)
                                     horario activo → movimiento (MOG2, enmascarado a la zona)
                                     → YOLO person → umbral → centro-en-zona → cooldown
                                     └─ Event ─▶ EventHandler
                                                  1. SceneInspector (YOLO sin filtro de clases)
                                                  2. FileRawSnapshotStore (JPEG sin cajas)
                                                  3. AnnotatedSnapshotStore (JPEG con cajas)
                                                  4. Notifier(s) — canales de la cámara
                                                     (ntfy / Telegram) o el global
                                                  5. FileClipRecorder.record_event (pre+post)
                                                  6. EventStore (BD + event_objects;
                                                     JSONL en modo standalone)
RetentionJob (hilo de fondo): borra evidencia > N días
```

Decisión de resiliencia: cada paso del handler tolera el fallo de los demás
(sin captura se notifica sin imagen; sin canal disponible el evento igual se
persiste con `notified: false`; **si la inspección de escena falla, el evento
sigue su curso sin anotar y la notificación sale igual**).

### Anotación de escena (Fase 7)

El paso 1 es una **segunda inferencia**, esta vez sin filtro de clases, sobre
el frame del evento. Registra todo lo que se veía —mascota, bolso, auto, moto—
como contexto de un evento que el pipeline ya confirmó.

Tres cosas que no son obvias y conviene no romper:

- **No participa en la decisión.** Corre después del pipeline, así que qué
  dispara un evento y a quién se notifica sigue siendo exclusivamente personas.
  `pipeline.py` no sabe que esto existe.
- **Comparte modelo y lock con el detector.** `YoloSceneInspector` recibe el
  `YOLO` ya cargado (un modelo por proceso, por RAM) y el supervisor lo envuelve
  con **el mismo lock** que `ThreadSafeDetector`. Dos locks distintos sobre el
  mismo modelo dejarían entrar dos hilos a la vez, que es justo lo que ese lock
  evita.
- **Cuesta una inferencia por evento, no por frame.** ~250 ms dentro de un
  handler que ya bloquea `clip_post_seconds` grabando el clip.

El dibujo (`storage/annotate.py`) **copia el frame antes de pintar**: el mismo
arreglo está en el buffer circular del clip y en `CameraWorker.last_frame`, así
que dibujar sobre él dejaría cajas quemadas en el vídeo y en el preview.

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
- `GET /api/health` (sin autenticación) reporta estado y número de workers
  vivos; es lo que consulta el `healthcheck` del contenedor.
- Toda la configuración del modo servidor entra por variables `SECUH_*`
  (`settings.py`); las que se tocan en una instalación están tabuladas en
  `runbook.md` §8.
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
- La exportación del histórico exige sesión como cualquier otra evidencia, y
  neutraliza la inyección de fórmulas en el CSV: los nombres y zonas de cámara
  los escribe un usuario, y un nombre como `=WEBSERVICE(...)` se ejecutaría al
  abrir el archivo descargado en Excel. Se escapa al exportar, no al guardar.
- Los registros de `event_objects` **sobreviven a la retención de imágenes**:
  a los N días desaparece la foto y queda la fila. Es deliberado (es lo que
  hace posible el análisis) y está declarado en `runbook.md` §8.1.

## Estado por fase

- **Fase 0 (hecha):** esqueleto + puertos + pipeline/cooldown testeados +
  benchmark de hardware (`spike/benchmark.py`, ADR 0003).
- **Fase 1 (hecha, validada con celular real + ntfy):** adaptadores
  reales (MOG2, YOLO, captura con reconexión, ntfy, clips, retención),
  config YAML validada, logging JSON, entry point `python -m secuh`.
- **Fase 2 (hecha, validada con `docker compose up` + PostgreSQL real):** BD +
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
- **Fase 7 (hecha, pendiente de prueba de campo):** anotación de escena
  (`SceneInspector`, tabla `event_objects`, migración `0004`), capturas con
  cajas dibujadas, captura cruda, exportación a CSV/Parquet y
  [`analisis-de-datos.md`](analisis-de-datos.md). Plan y desviaciones en
  [`plan-fase-7-anotacion-de-escena.md`](../plan-fase-7-anotacion-de-escena.md).

Pendientes que no son de código y quedan para la instalación real: la prueba
de resistencia de 72 h (procedimiento en `runbook.md` §6), la decisión de
negocio sobre el modelo de soporte, y la prueba de campo de la Fase 7 (ponerse
delante de la webcam con algo en la mano y mirar la foto que llega).
