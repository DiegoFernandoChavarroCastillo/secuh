# Plan de desarrollo — Sistema de detección de personas para videovigilancia

> Documento complementario a `proyecto-deteccion-personas.md`. Define **cómo** se construye el proyecto: fases, arquitectura de código, prácticas, seguridad y criterios de salida de cada etapa.

---

## 1. Principios rectores

1. **El pipeline de detección es el núcleo; todo lo demás orbita alrededor.** El panel web, la base de datos y las notificaciones son reemplazables; la lógica captura → movimiento → YOLO → cooldown → evento debe ser estable, testeable y sin dependencias hacia afuera.
2. **Dependencias apuntan hacia adentro (arquitectura hexagonal / ports & adapters).** El dominio (`detection`, `events`) define interfaces; los adaptadores (ntfy, Telegram, PostgreSQL, RTSP) las implementan. Ya está planteado para notificaciones — se aplica el mismo patrón a fuentes de video, almacenamiento y persistencia.
3. **Cada fase termina en algo usable y demostrable.** No se avanza a la siguiente fase con la anterior "al 90%".
4. **Configuración explícita y versionable.** Desde el MVP, toda la configuración vive en un archivo validado (Pydantic Settings + variables de entorno para secretos), nunca hardcodeada.
5. **Medir antes de optimizar.** El pre-filtro de movimiento ya es la gran optimización; cualquier otra (batching de inferencia, GPU, resoluciones) se justifica con métricas del hardware real.

---

## 2. Estructura de repositorio propuesta

```
secuh/
├── backend/
│   ├── src/secuh/
│   │   ├── core/              # Dominio puro: sin FastAPI, sin OpenCV directo
│   │   │   ├── models.py      # Entidades: Camera, Event, DetectionResult
│   │   │   ├── ports.py       # Interfaces: VideoSource, Detector, Notifier, EventStore, ClipRecorder
│   │   │   └── pipeline.py    # Orquestación: movimiento → detección → cooldown → evento
│   │   ├── detection/         # Adaptadores de visión
│   │   │   ├── motion.py      # MotionDetector (MOG2)
│   │   │   ├── yolo.py        # YoloPersonDetector (Ultralytics)
│   │   │   └── tracking.py    # (fase 5) ByteTrack
│   │   ├── video/             # Adaptadores de captura
│   │   │   ├── rtsp.py        # RTSP / HTTP / MJPEG (IP Webcam)
│   │   │   └── worker.py      # Hilo/proceso por cámara + reconexión
│   │   ├── notifications/     # Adaptadores de notificación
│   │   │   ├── base.py        # NotificationAdapter (ABC)
│   │   │   ├── ntfy.py
│   │   │   └── telegram.py    # (fase 4)
│   │   ├── storage/           # Clips y capturas
│   │   ├── db/                # SQLAlchemy + Alembic (a partir de fase 2)
│   │   ├── api/               # FastAPI: routers, schemas, deps (a partir de fase 2)
│   │   └── config.py          # Pydantic Settings
│   ├── tests/
│   │   ├── unit/
│   │   └── integration/
│   └── pyproject.toml
├── frontend/                  # React + Vite + TS (a partir de fase 2)
├── deploy/
│   ├── docker-compose.yml
│   └── Dockerfile.backend
├── docs/
│   ├── architecture.md        # Decisiones y diagramas (se actualiza por fase)
│   ├── adr/                   # Architecture Decision Records (1 archivo por decisión)
│   └── runbook.md             # Operación: instalar, arrancar, diagnosticar (fase 6 lo pule)
├── config.example.yaml
└── README.md
```

**Regla de dependencias:** `core/` no importa nada de `detection/`, `video/`, `api/` ni `db/`. Los tests unitarios del pipeline corren sin cámara, sin modelo y sin base de datos, usando fakes de las interfaces de `ports.py`.

---

## 3. Prácticas transversales (aplican desde el día 1)

### Código
- Python ≥ 3.11, type hints en todo el código público, validados con **mypy** (o pyright).
- **ruff** para lint + formato; configuración en `pyproject.toml`.
- **pytest** con cobertura mínima acordada para `core/` (sugerido: 85%+ en el pipeline; los adaptadores de hardware se cubren con tests de integración marcados y opcionales).
- Pre-commit hooks: ruff, mypy, detección de secretos (`gitleaks` o `detect-secrets`).
- Commits atómicos sobre ramas `feature/*` → PR a `develop` → releases a `main`.

### CI (GitHub Actions, desde fase 1)
- Pipeline mínimo: lint → typecheck → tests unitarios en cada push/PR.
- A partir de fase 2: build de imágenes Docker + tests de integración con PostgreSQL en servicio.

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
- Métricas internas simples por cámara: fps procesados, latencia de inferencia, ratio de frames con movimiento, notificaciones enviadas. Primero expuestas en logs/endpoint `/health`; formato Prometheus si algún día hace falta.

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
- [ ] PostgreSQL + SQLAlchemy 2.0 + **Alembic** para migraciones desde la primera tabla.
- [ ] Modelo de datos del documento (§6): `cameras`, `events`, `notification_channels`, más `users`.
- [ ] API FastAPI: auth (login, JWT/cookie), CRUD de cámaras, armar/desarmar, listado de eventos con paginación, servir capturas/clips autenticado.
- [ ] El pipeline lee su configuración de la BD y reacciona a cambios (armar/desarmar sin reiniciar el proceso).
- [ ] `docker-compose.yml`: backend + PostgreSQL + volumen de clips.

Frontend:
- [ ] React + Vite + TS, con lint/format (eslint + prettier) y CI propio.
- [ ] Login, vista general de cámaras (estado armada/desarmada, en línea/desconectada), CRUD de cámaras, feed de eventos con miniaturas.

**Criterio de salida:** un usuario no técnico puede dar de alta una cámara, armarla, y revisar los eventos con foto desde el navegador, sin tocar archivos. `docker compose up` levanta todo.

**Duración estimada:** 3–4 semanas.

---

### Fase 3 — Horarios y zonas de detección
**Objetivo:** reducir falsos positivos y adaptar la vigilancia al horario del negocio.

- [ ] Horarios por cámara: siempre / nocturno predefinido / rango personalizado (cuidar rangos que cruzan medianoche y zona horaria del servidor).
- [ ] Máscaras de zona: polígonos por cámara; el movimiento y las detecciones fuera de la zona se ignoran. Editor visual en el panel (dibujar polígono sobre un snapshot de la cámara).
- [ ] Sensibilidad por cámara desde el panel (umbral de confianza YOLO + umbral de área de movimiento).
- [ ] Alerta de cámara desconectada como notificación (no solo log): "Cámara Entrada sin señal hace 2 min".

**Criterio de salida:** una cámara que ve parcialmente la calle deja de notificar peatones al enmascarar esa zona; la detección se activa/desactiva sola según horario configurado.

**Duración estimada:** 2 semanas.

---

### Fase 4 — Multi-canal de notificaciones
**Objetivo:** explotar el diseño de adaptadores: canales configurables por cámara.

- [ ] `TelegramAdapter` (bot API, foto + texto) y opcionalmente correo (SMTP).
- [ ] CRUD de canales en panel: crear canal, probarlo (botón "enviar notificación de prueba"), asignar canales a cámaras.
- [ ] Política de reintentos/backoff común a todos los adaptadores; registro de `notificado` por evento y por canal.
- [ ] Prioridades: p. ej. detección en horario armado = prioridad alta en ntfy.

**Criterio de salida:** dos cámaras notificando a canales distintos (ntfy y Telegram), configurado 100% desde el panel; el botón de prueba valida un canal antes de asignarlo.

**Duración estimada:** 1–2 semanas.

---

### Fase 5 — Multi-cámara a escala y robustez
**Objetivo:** de "funciona con 2 cámaras" a "funciona con N cámaras de forma sostenida días enteros".

- [ ] Cola de inferencia: los workers de captura encolan frames candidatos; un pool de workers de YOLO (tamaño según CPU/GPU) consume la cola. Backpressure: si la cola se llena, se descartan frames viejos (nunca bloquear la captura).
- [ ] Tracking (ByteTrack) para distinguir "misma persona sigue en cuadro" vs "persona nueva" y mejorar el anti-duplicados.
- [ ] Dashboard en tiempo real: estado de cámaras y eventos vía WebSocket/SSE (sin refrescar la página).
- [ ] Endurecimiento: supervisión del proceso (systemd/docker restart policies), watchdog interno de workers colgados, métricas por cámara visibles en el panel.
- [ ] Prueba de resistencia documentada: N cámaras × 72 h sin fugas de memoria ni degradación (medir RSS y latencia de inferencia).

**Criterio de salida:** el número objetivo de cámaras (definir según hardware del benchmark de fase 0) corre 72 h continuas con notificaciones fiables y el dashboard refleja estado en vivo.

**Duración estimada:** 3–4 semanas.

---

### Fase 6 — Empaquetado como producto
**Objetivo:** que instalarlo en el local de un cliente sea un procedimiento repetible de horas, no un proyecto artesanal.

- [ ] Instalación un-comando (script sobre docker compose) + asistente de primer arranque en el panel (crear usuario admin, dar de alta primera cámara con wizard, probar notificación).
- [ ] Guía de instalación de IP Webcam en el celular del cliente (con capturas), impresa/PDF.
- [ ] `docs/runbook.md` completo: diagnóstico de problemas comunes, backup/restore de BD y configuración, actualización de versión.
- [ ] Actualizaciones: versionado semántico, changelog, procedimiento de upgrade con migraciones automáticas.
- [ ] Checklist de instalación en sitio (red, posición de cámaras, prueba de detección real, entrega al cliente).
- [ ] Definir el modelo de soporte: qué monitoreo remoto (si alguno) se ofrece, y sus implicaciones de privacidad.

**Criterio de salida:** una instalación completa en hardware limpio, siguiendo solo la documentación, sin intervención del desarrollador.

**Duración estimada:** 2–3 semanas.

---

## 5. Resumen de línea de tiempo

| Fase | Alcance | Estimado |
|---|---|---|
| 0 | Fundaciones + benchmark de hardware | 1 sem |
| 1 | MVP: cámara → ntfy | 2–3 sem |
| 2 | Panel web + PostgreSQL | 3–4 sem |
| 3 | Horarios y zonas | 2 sem |
| 4 | Multi-canal | 1–2 sem |
| 5 | Escala y robustez | 3–4 sem |
| 6 | Producto | 2–3 sem |
| **Total** | | **~3.5–5 meses** (a tiempo parcial, ajustar a dedicación real) |

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
