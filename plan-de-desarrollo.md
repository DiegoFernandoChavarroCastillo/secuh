# Plan de desarrollo — Sistema de detección de personas para videovigilancia

> Documento complementario a `proyecto-deteccion-personas.md`. Define **cómo** se construye el proyecto: fases, arquitectura de código, prácticas, seguridad y criterios de salida de cada etapa.

> **Estado (2026-08-13, v0.6.2):** fases 0–6 implementadas y verificadas, incluyendo
> `docker compose up` con PostgreSQL real y hardware físico (celular IP Webcam + cámara
> RTSP). Se encontró y corrigió una serie de bugs reales de la puesta en marcha (ver
> `CHANGELOG.md` 0.6.1) y se añadió `run.py` como alternativa nativa a Docker,
> recomendada en Windows (ADR 0005) por una limitación de red de Docker Desktop con
> cámaras RTSP+UDP. La 0.6.2 cerró los huecos que impedían cumplir el criterio de
> salida de la Fase 6 ("instalar siguiendo solo la documentación"): ajustes que no
> llegaban al contenedor, healthcheck del backend y checklist de la vía nativa.
> Pendientes de campo: prueba de resistencia de 72 h en hardware de despliegue, y la
> decisión de negocio sobre el modelo de soporte.

---

## 1. Principios rectores

1. **El pipeline de detección es el núcleo; todo lo demás orbita alrededor.** El panel web, la base de datos y las notificaciones son reemplazables; la lógica captura → movimiento → YOLO → cooldown → evento debe ser estable, testeable y sin dependencias hacia afuera.
2. **Dependencias apuntan hacia adentro (arquitectura hexagonal / ports & adapters).** El dominio (`detection`, `events`) define interfaces; los adaptadores (ntfy, Telegram, PostgreSQL, RTSP) las implementan. Ya está planteado para notificaciones — se aplica el mismo patrón a fuentes de video, almacenamiento y persistencia.
3. **Cada fase termina en algo usable y demostrable.** No se avanza a la siguiente fase con la anterior "al 90%".
4. **Configuración explícita y versionable.** Desde el MVP, toda la configuración vive en un archivo validado (Pydantic Settings + variables de entorno para secretos), nunca hardcodeada.
5. **Medir antes de optimizar.** El pre-filtro de movimiento ya es la gran optimización; cualquier otra (batching de inferencia, GPU, resoluciones) se justifica con métricas del hardware real.

---

## 2. Estructura de repositorio (real, v0.6.2)

```
secuh/
├── backend/
│   ├── src/secuh/
│   │   ├── core/              # Dominio puro: sin FastAPI, sin OpenCV directo
│   │   │   ├── models.py      # Camera, Event, Detection, Schedule, Notification
│   │   │   ├── ports.py       # VideoSource, MotionDetector, PersonDetector, Notifier,
│   │   │   │                  #   EventStore, SnapshotStore, ClipRecorder, Clock
│   │   │   ├── pipeline.py    # horario → movimiento → YOLO → umbral → zona → cooldown → evento
│   │   │   ├── handler.py     # evento: captura → notificar → clip → persistir (tolerante a fallos)
│   │   │   ├── geometry.py    # punto-en-polígono (zonas)
│   │   │   └── clock.py       # MonotonicClock
│   │   ├── detection/         # motion.py (MOG2 + máscara de zona), yolo.py (con warmup)
│   │   ├── video/             # source.py (captura + reconexión + redacción de URLs),
│   │   │                      #   worker.py (hilo por cámara, métricas, último frame)
│   │   ├── notifications/     # ntfy.py, telegram.py, console.py, factory.py (canales)
│   │   ├── storage/           # clips.py (buffer circular), snapshots.py, events.py (JSONL F1),
│   │   │                      #   retention.py (borrado automático de evidencia)
│   │   ├── db/                # models.py (users/cameras/events/channels), session, event_store
│   │   ├── api/               # app.py (fábrica + panel estático), security.py, deps.py,
│   │   │                      #   routers/: auth, cameras, channels, events, stream (SSE)
│   │   ├── runtime/           # supervisor.py: reconcilia BD↔workers, reinicios, alertas de señal
│   │   ├── config.py          # Config YAML del modo standalone (Fase 1)
│   │   ├── settings.py        # ServerSettings por entorno (modo servidor)
│   │   ├── logging_setup.py   # Logging JSON estructurado
│   │   └── __main__.py        # Entry point standalone: python -m secuh
│   ├── migrations/            # Alembic: 0001 inicial, 0002 horarios/zonas, 0003 canales
│   ├── tests/unit/            # 89 tests con fakes de los puertos (sin hardware)
│   ├── alembic.ini
│   └── pyproject.toml         # deps + ruff + mypy (estricto) + pytest
├── frontend/                  # React + Vite + TS: login, cámaras (+editor de zona),
│                              #   eventos, canales; estado en vivo por SSE
├── deploy/                    # docker-compose.yml, Dockerfile.backend (multi-stage con panel),
│                              #   .env.example
├── docs/
│   ├── architecture.md        # Arquitectura y flujo en ejecución (actualizado por fase)
│   ├── adr/                   # 0001 Python+uv · 0002 YOLO · 0003 hardware · 0004 escalado
│   │                          #   · 0005 ejecución nativa vs. Docker en Windows
│   ├── runbook.md             # Operación: instalar, diagnosticar, backup, actualizar,
│   │                          #   referencia de variables SECUH_* (§8)
│   ├── guia-ip-webcam.md      # Para el cliente: celular como cámara
│   └── checklist-instalacion.md  # Imprimible, con las dos vías (Docker / nativa)
├── spike/                     # benchmark.py (Fase 0, descartable)
├── config.example.yaml        # Config del modo standalone
├── run.py                     # Backend + panel juntos en local, sin Docker (ADR 0005)
├── CHANGELOG.md
└── README.md
```

Notas vs. la propuesta original: `video/rtsp.py` se llamó `source.py` (cubre RTSP, MJPEG y USB con una sola clase OpenCV); `detection/tracking.py` no existe (ByteTrack diferido, ADR 0004); `notifications/base.py` no hace falta (la interfaz `Notifier` vive en `core/ports.py`, que es donde el dominio la define).

**Regla de dependencias:** `core/` no importa nada de `detection/`, `video/`, `api/` ni `db/`. Los tests unitarios del pipeline corren sin cámara, sin modelo y sin base de datos, usando fakes de las interfaces de `ports.py`.

---

## 3. Prácticas transversales (aplican desde el día 1)

### Código
- Python 3.12 (fijado en `backend/.python-version`; ver ADR 0001), type hints en todo el código público, validados con **mypy** en modo estricto.
- **ruff** para lint + formato; configuración en `pyproject.toml`.
- **pytest** con cobertura mínima acordada para `core/` (sugerido: 85%+ en el pipeline; los adaptadores de hardware se cubren con tests de integración marcados y opcionales).
- Pre-commit hooks: ruff, mypy, detección de secretos (`gitleaks` o `detect-secrets`).
- Commits atómicos sobre ramas `feature/*` → PR a `develop` → releases a `main`.

### CI (GitHub Actions)
- Backend: ruff (lint + formato) → mypy → pytest en cada push/PR.
- Frontend: eslint → build (incluye chequeo de tipos).
- Pendiente (mejora futura): build de la imagen Docker y tests de integración
  con PostgreSQL como servicio del workflow.

### Seguridad
- **Secretos jamás en el repo**: tokens de ntfy/Telegram y credenciales RTSP van en `.env` (gitignoreado) / variables de entorno; `config.example.yaml` solo con placeholders.
- URLs RTSP contienen credenciales → **nunca loggear la URL completa** (redactar user:pass en logs y en la API).
- Panel web con **autenticación desde su primera versión** (fase 2): aunque sea red local, el panel arma/desarma la vigilancia de un negocio — no puede quedar abierto. JWT o sesión con cookie `HttpOnly`, contraseña con hash argon2/bcrypt.
- API: validación estricta de entrada con Pydantic, CORS restringido, rate limiting básico en login.
- Clips y capturas se sirven solo a usuarios autenticados (nunca directorio estático público).
- Contenedores: usuario no-root, imágenes pinneadas, `docker scout`/`trivy` en CI cuando haya imágenes.
- Dependencias: `pip-audit` / Dependabot activado.
- **Privacidad (es un producto de vigilancia):** política de retención de clips configurable y aplicada automáticamente (borrado tras N días), documentar en el runbook las obligaciones de avisos visibles según normativa local.

### Documentación
- `README.md`: qué es, cómo correr en 5 minutos (quickstart docker compose).
- `docs/adr/`: cada decisión relevante (¿por qué MOG2?, ¿por qué asyncio.Queue y no Redis?, ¿por qué YOLOv8n?) queda registrada en un ADR corto. Evita re-discutir decisiones y facilita onboarding.
- Docstrings en interfaces (`ports.py`) y módulos; OpenAPI autogenerado por FastAPI como contrato del panel.
- `docs/runbook.md`: crece con cada fase (cómo diagnosticar cámara caída, cómo rotar un token, cómo restaurar backup).

### Observabilidad
- Logging estructurado (`structlog` o `logging` + JSON) desde el MVP: cada evento de detección, notificación enviada/fallida y reconexión de cámara queda trazado.
- Métricas internas simples por cámara: fps procesados, latencia de inferencia, ratio de frames con movimiento, notificaciones enviadas. Expuestas en `GET /api/cameras` (por cámara) y en `GET /api/health` (estado global + workers vivos, que es además lo que consulta el healthcheck del contenedor); formato Prometheus si algún día hace falta.

---

## 4. Fases

### Fase 0 — Fundaciones y validación técnica (spike)
**Objetivo:** confirmar que el hardware disponible sostiene el pipeline antes de escribir el sistema "de verdad", y dejar el esqueleto del proyecto listo.

- [x] Scaffold del repo: `pyproject.toml`, ruff, mypy, pytest, pre-commit, CI de lint+test, estructura de carpetas de §2 (con `ports.py`, entidades y pipeline+cooldown testeados).
- [x] Spike descartable: `spike/benchmark.py` — lee stream (IP Webcam / RTSP / USB), corre MOG2 + YOLOv8n y mide fps, latencia y CPU.
- [x] Benchmark documentado en `docs/adr/0003-linea-base-de-hardware.md` (medido en máquina de desarrollo; revalidar en hardware de despliegue y con el stream real de IP Webcam).
- [x] ADRs registrados: Python 3.12 + uv (0001), YOLOv8n provisional (0002), línea base de hardware (0003).

**Criterio de salida:** el spike sostiene ≥ 5 fps de análisis con detección correcta de una persona en el hardware objetivo, y el CI pasa en verde sobre el esqueleto.

**Duración estimada:** 1 semana.

---

### Fase 1 — MVP: una cámara → ntfy (sin panel)
**Objetivo:** el flujo completo de valor funcionando de punta a punta, configurado por archivo.

- [x] `core/`: entidades, interfaces, `pipeline.py` (movimiento → YOLO clase `person` → umbral → cooldown → evento) y `handler.py` (evidencia → notificación → persistencia, tolerante a fallos parciales). **Testeado con fakes, sin hardware.**
- [x] `video/`: `OpenCvVideoSource` con reconexión automática con backoff y redacción de credenciales en logs; `CameraWorker` con throttle de análisis.
- [x] `detection/`: `Mog2MotionDetector` y `YoloPersonDetector` (con calentamiento del modelo al arrancar).
- [x] `notifications/`: `NtfyNotifier` (texto + captura adjunta, reintentos, timeout; fallo no tumba el pipeline) y `ConsoleNotifier` para desarrollo.
- [x] Grabación de clip: buffer circular pre + post, `data/clips/{camara}/{timestamp}.mp4`; captura JPEG en `data/snapshots/`.
- [x] Configuración por `config.yaml` validada con Pydantic; topic de ntfy por variable de entorno `SECUH_NTFY_TOPIC`.
- [x] Retención: job en hilo de fondo que borra evidencia más vieja que N días (pasada al arrancar + cada hora).
- [x] Logging estructurado JSON de todo el flujo.
- [x] Entry point único: `python -m secuh --config config.yaml`.
- [x] Eventos persistidos en `data/events.jsonl` (reemplazado por PostgreSQL en Fase 2).

**Criterio de salida:** con un celular con IP Webcam apuntando a una puerta, una persona entra en cuadro y llega una notificación a ntfy con foto en < 5 segundos; un gato/perro no dispara notificación; la misma persona quieta en cuadro no genera spam (cooldown funciona); desconectar el celular y reconectarlo recupera el stream solo.

> Validado con webcam de laptop (2026-07-14): detección de persona con confianza 88%, notificación (consola) con captura en <2 s desde la conexión de la fuente, clip y evento persistidos. **Pendiente de validar con el setup real:** celular con IP Webcam, topic de ntfy, prueba de mascota y prueba de reconexión física.

**Duración estimada:** 2–3 semanas.

---

### Fase 2 — Panel web básico + persistencia
**Objetivo:** dejar de editar YAML: cámaras y eventos viven en PostgreSQL y se gestionan desde un panel autenticado.

Backend:
- [x] SQLAlchemy 2.0 + **Alembic** (migración `0001`); compatible PostgreSQL (producción) y SQLite (tests/dev).
- [x] Modelo de datos: `users`, `cameras`, `events` (`notification_channels` llega con la Fase 4, que es cuando se usa).
- [x] API FastAPI: login con cookie HttpOnly + rate limiting, CRUD de cámaras (URL con credenciales siempre redactada en las respuestas), armar/desarmar, eventos paginados con filtro por cámara, evidencia servida solo autenticada.
- [x] `CameraSupervisor`: reconcilia la BD con los workers cada 5s — armar/desarmar/editar sin reiniciar el proceso, detecta workers muertos y los reinicia, YOLO compartido entre cámaras con lock.
- [x] Admin inicial por `SECUH_ADMIN_PASSWORD` al primer arranque; toda la config del servidor por variables `SECUH_*`.
- [x] `deploy/`: `docker-compose.yml` (PostgreSQL + backend con volumen de evidencia) + `Dockerfile.backend` (usuario no-root, migraciones al arrancar) + `.env.example`.

Frontend:
- [x] React + Vite + TS con eslint y CI propio; fuentes autoalojadas (funciona sin internet).
- [x] Login, tarjetas de cámara con estado (armada/desarmada, en línea/sin señal, refresco cada 5s), formulario de alta/edición, armar/desarmar, feed de eventos con miniaturas, clip y paginación.

**Criterio de salida:** un usuario no técnico puede dar de alta una cámara, armarla, y revisar los eventos con foto desde el navegador, sin tocar archivos. `docker compose up` levanta todo.

> Validado E2E (2026-07-14, SQLite + uvicorn + webcam): login → crear cámara → armar por API → worker arranca solo, cámara "en línea", persona detectada y persistida en BD con captura y clip descargables (401 sin sesión), desarme en caliente en <6 s.
>
> Validado además (2026-07-16) `docker compose up` con PostgreSQL real y hardware
> físico: requirió corregir varios bugs de la puesta en marcha en Docker (torch
> descargando CUDA innecesario, permisos del modelo YOLO en runtime, README no
> copiado al build, `uv run` reconciliando el venv como usuario incorrecto — ver
> CHANGELOG 0.6.1) y reveló una limitación de red de Docker Desktop en Windows con
> cámaras RTSP que transmiten por UDP (ADR 0005), que llevó a añadir `run.py` como
> vía nativa recomendada en Windows.

**Duración estimada:** 3–4 semanas.

---

### Fase 3 — Horarios y zonas de detección
**Objetivo:** reducir falsos positivos y adaptar la vigilancia al horario del negocio.

- [x] Horarios por cámara: siempre / nocturno predefinido / rango personalizado, con rangos que cruzan medianoche (testeado); fuera de horario no se analiza ni graba.
- [x] Máscaras de zona: polígono normalizado por cámara; el movimiento (MOG2 enmascarado) y las detecciones (centro de caja) fuera de la zona se ignoran. Editor visual en el panel sobre el preview en vivo de la cámara (`GET /api/cameras/{id}/preview`).
- [x] Sensibilidad por cámara desde el panel (slider de umbral de confianza).
- [x] Alerta de cámara sin señal como notificación (y aviso de recuperación), con supresión durante el arranque.
- [x] Migración `0002`.

**Criterio de salida:** una cámara que ve parcialmente la calle deja de notificar peatones al enmascarar esa zona; la detección se activa/desactiva sola según horario configurado.

> Lógica validada con tests (medianoche, polígonos, pipeline); la prueba de campo con calle real queda para la instalación.

**Duración estimada:** 2 semanas.

---

### Fase 4 — Multi-canal de notificaciones
**Objetivo:** explotar el diseño de adaptadores: canales configurables por cámara.

- [x] `TelegramNotifier` (bot API: sendMessage/sendPhoto con reintentos). Correo SMTP queda como extensión futura de la fábrica.
- [x] CRUD de canales en el panel con botón "Enviar prueba" y asignación por cámara (checkboxes). Los secretos (tokens) entran por la API pero solo salen redactados.
- [x] Reintentos con backoff en ambos adaptadores; `notificado` por evento (por-canal llegará si hace falta auditoría más fina).
- [x] Prioridad alta en detecciones, normal en avisos de recuperación de señal.
- [x] El supervisor reconstruye los notificadores del worker cuando cambian los canales asignados o su config (sin reiniciar el proceso). Migración `0003`.

**Criterio de salida:** dos cámaras notificando a canales distintos (ntfy y Telegram), configurado 100% desde el panel; el botón de prueba valida un canal antes de asignarlo.

**Duración estimada:** 1–2 semanas.

---

### Fase 5 — Multi-cámara a escala y robustez
**Objetivo:** de "funciona con 2 cámaras" a "funciona con N cámaras de forma sostenida días enteros".

- [x] ~~Cola de inferencia~~ **diferida con justificación** (ADR 0004): con el hardware actual (1–2 cámaras), el lock del detector compartido + el throttle de `analysis_fps` ya dan la serialización y el backpressure; la cola se implementa cuando haya >2 cámaras o GPU.
- [x] ~~ByteTrack~~ **diferido** (ADR 0004): el tracking de Ultralytics guarda estado por modelo, incompatible con el modelo compartido entre cámaras; requeriría un modelo por cámara que esta RAM no soporta.
- [x] Dashboard en tiempo real vía SSE (`/api/stream`): estado armado/señal y eventos nuevos llegan al panel sin refrescar.
- [x] Endurecimiento: reinicio de workers muertos (F2), reconexión con backoff (F1), alerta de señal (F3), restart policies en compose, métricas por worker (uptime, frames, fps efectivos, eventos) expuestas en `GET /api/cameras`.
- [ ] Prueba de resistencia 72 h: procedimiento y criterios de aceptación documentados en `docs/runbook.md` §6 — **debe correrse en el hardware de despliegue real** (operativa, no automatizable desde aquí).

**Criterio de salida:** el número objetivo de cámaras (definir según hardware del benchmark de fase 0) corre 72 h continuas con notificaciones fiables y el dashboard refleja estado en vivo.

**Duración estimada:** 3–4 semanas.

---

### Fase 6 — Empaquetado como producto
**Objetivo:** que instalarlo en el local de un cliente sea un procedimiento repetible de horas, no un proyecto artesanal.

- [x] Producto en una sola URL: el Dockerfile compila el panel (multi-stage con Node) y el backend lo sirve en `/`; `docker compose up -d --build` levanta todo. El admin se crea solo al primer arranque y los estados vacíos del panel guían el alta de la primera cámara y el primer canal (con botón de prueba).
- [x] `docs/guia-ip-webcam.md`: guía paso a paso para el celular del cliente, con tabla de problemas comunes.
- [x] `docs/runbook.md` completo: instalación, diagnóstico, backup/restore, rotación de secretos, actualización, prueba de resistencia, privacidad.
- [x] Versionado semántico (v0.6.2) + `CHANGELOG.md`; upgrade = `git pull && docker compose up -d --build` (migraciones automáticas al arrancar).
- [x] `docs/checklist-instalacion.md`: checklist imprimible de instalación en sitio con "prueba de fuego" ante el dueño, con las dos vías (Docker/Linux y nativa/Windows) y el arranque desatendido de esta última.
- [x] Configuración operativa alcanzable desde la documentación: variables `SECUH_*` tabuladas en el runbook (§8), expuestas en `docker-compose.yml` y comentadas en `.env.example`; healthcheck del backend contra `/api/health`.
- [ ] Definir el modelo de soporte (decisión de negocio: monitoreo remoto sí/no y sus implicaciones de privacidad — requiere decisión del dueño del proyecto).

**Criterio de salida:** una instalación completa en hardware limpio, siguiendo solo la documentación, sin intervención del desarrollador.

**Duración estimada:** 2–3 semanas.

---

## 5. Resumen de línea de tiempo

| Fase | Alcance | Estimado | Estado |
|---|---|---|---|
| 0 | Fundaciones + benchmark de hardware | 1 sem | ✅ hecha (benchmark en máquina de desarrollo) |
| 1 | MVP: cámara → ntfy | 2–3 sem | ✅ hecha, validada con celular real + ntfy real |
| 2 | Panel web + PostgreSQL | 3–4 sem | ✅ hecha, validada con `docker compose up` + PostgreSQL real |
| 3 | Horarios y zonas | 2 sem | ✅ hecha |
| 4 | Multi-canal (ntfy + Telegram) | 1–2 sem | ✅ hecha, validada con ntfy real (recordar asignar el canal a la cámara) |
| 5 | Escala y robustez | 3–4 sem | ✅ hecha con alcance del ADR 0004 (cola/tracking diferidos; resistencia 72 h pendiente en sitio) |
| 6 | Producto | 2–3 sem | ✅ hecha; `run.py` (ADR 0005) como alternativa nativa en Windows; documentación de instalación cerrada en 0.6.2; falta decisión de modelo de soporte |

---

## 6. Riesgos técnicos principales y mitigación

| Riesgo | Mitigación en el plan |
|---|---|
| El hardware no sostiene el pipeline | Fase 0 lo valida antes de construir nada encima |
| Falsos positivos queman la confianza del cliente | Cooldown (F1), zonas y sensibilidad (F3), tracking (F5) |
| Streams inestables (celular/WiFi) | Reconexión con backoff (F1) + alerta de cámara caída (F3) |
| Fugas de memoria en procesos 24/7 (OpenCV/streams) | Prueba de resistencia de 72 h (F5), watchdog y restart policies |
| Panel expuesto sin protección | Auth obligatoria desde la primera versión del panel (F2) |
| Secretos filtrados (tokens, credenciales RTSP) | `.env` + pre-commit con detección de secretos + redacción en logs (F0/F1) |
