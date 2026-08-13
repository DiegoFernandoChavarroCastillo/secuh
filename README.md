# secuh

Sistema de videovigilancia inteligente que procesa video en tiempo real (cámaras IP RTSP, celular vía IP Webcam, o webcam USB), detecta específicamente **personas** (no animales ni mascotas), y envía notificaciones inmediatas con foto al teléfono del dueño — mientras está ocurriendo, no después.

**Estado:** v0.6.1 — fases 0–6 del plan completadas ([`CHANGELOG.md`](CHANGELOG.md)).

| Qué hace | Cómo |
|---|---|
| Detección eficiente | Pre-filtro de movimiento (MOG2) → YOLOv8n solo clase persona → anti-spam por cooldown |
| Alertas al teléfono | Canales ntfy y Telegram, configurables por cámara desde el panel, con botón de prueba |
| Evidencia | Captura JPEG + clip mp4 (pre/post evento); retención automática configurable |
| Panel web | Login, cámaras (armar/desarmar en caliente), feed de eventos, estado en vivo (SSE) |
| Afinado por cámara | Sensibilidad, horario de vigilancia (incl. nocturno) y zona de detección dibujable |
| Operación | Alerta si una cámara pierde señal; reconexión y reinicio de workers automáticos |

## Documentación

- [`proyecto-deteccion-personas.md`](proyecto-deteccion-personas.md) — la idea y el diseño original
- [`plan-de-desarrollo.md`](plan-de-desarrollo.md) — plan por fases con su estado
- [`docs/architecture.md`](docs/architecture.md) — arquitectura (hexagonal) y flujo en ejecución
- [`docs/adr/`](docs/adr/README.md) — decisiones de arquitectura registradas
- Operación: [runbook](docs/runbook.md) · [guía IP Webcam](docs/guia-ip-webcam.md) · [checklist de instalación](docs/checklist-instalacion.md)

## Ejecutar el producto

### Opción A — Nativo, sin Docker (recomendado en Windows, y para desarrollo)

Requiere una vez: [uv](https://docs.astral.sh/uv/) + Node 22+.

```bash
cd backend  && uv sync --all-groups && cd ..
cd frontend && npm install         && cd ..
python run.py
```

Levanta backend (`http://localhost:8000`) y panel con recarga en caliente
(`http://localhost:5173`) juntos, con SQLite (no hace falta PostgreSQL). La
primera vez genera `backend/.env` con una contraseña de admin aleatoria y la
imprime en pantalla — no se vuelve a mostrar, pero queda guardada ahí.
`Ctrl+C` apaga los dos procesos.

**¿Por qué nativo y no Docker?** Docker Desktop en Windows virtualiza la red
(WSL2/Hyper-V): las cámaras RTSP que transmiten vídeo por UDP no pueden
recibirse dentro del contenedor porque el paquete de vuelta no tiene cómo
enrutarse. En ejecución nativa no hay esa capa de por medio. Detalle en
[ADR 0005](docs/adr/0005-ejecucion-nativa-vs-docker.md).

### Opción B — Docker (recomendado para producción en Linux)

```bash
cd deploy
cp .env.example .env         # completar secretos (instrucciones dentro)
docker compose up -d --build # panel + API + PostgreSQL en http://localhost:8000
```

En ambas opciones: entra con `admin` / la contraseña generada, **crea un
canal de notificación y asígnalo a cada cámara** (Editar cámara → Canales de
notificación — sin esto, los eventos no se notifican aunque el botón
"Enviar prueba" del canal sí funcione), da de alta una cámara y ármala. Para
usar un celular como cámara: [`docs/guia-ip-webcam.md`](docs/guia-ip-webcam.md).

## Desarrollo

```bash
cd backend
uv sync --all-groups            # crea .venv e instala todo
uv run pytest tests/unit        # tests (sin cámara ni modelo: fakes)
uv run ruff check . ; uv run mypy
uv run pre-commit install       # hooks de git (lint + secretos), una vez
```

```bash
cd frontend
npm install
npm run dev     # http://localhost:5173, con proxy /api -> localhost:8000
npm run lint ; npm run build
```

## Otros modos de ejecución

- **Standalone sin panel (Fase 1):** una cámara configurada por archivo, sin BD.
  `cp config.example.yaml config.yaml`, ajustar, y `cd backend && uv run python -m secuh --config ../config.yaml`.
  El topic de ntfy va por entorno: `SECUH_NTFY_TOPIC=https://ntfy.sh/<topic-aleatorio>`.
- **Benchmark de hardware:** valida que una máquina sostiene el pipeline antes de instalar:
  `cd backend && uv run python ../spike/benchmark.py --source <stream> --display`
  (ver [`docs/adr/0003-linea-base-de-hardware.md`](docs/adr/0003-linea-base-de-hardware.md)).

## Estructura del repositorio

```
run.py              Levanta backend + panel juntos en local, sin Docker (ver Opción A)
backend/
  src/secuh/
    core/           Dominio puro: entidades, puertos, pipeline, handler (sin OpenCV/FastAPI)
    detection/      MOG2 (con máscara de zona) y YOLO
    video/          Captura con reconexión + worker por cámara (métricas, último frame)
    notifications/  ntfy, Telegram, consola + fábrica de canales
    storage/        Clips (buffer circular), snapshots, retención
    db/             SQLAlchemy (users, cameras, events, channels) + event store
    api/            FastAPI: auth, cámaras, canales, eventos, SSE; sirve el panel en /
    runtime/        Supervisor: reconcilia BD <-> workers (armado en caliente)
  migrations/       Alembic (0001-0003)
  tests/unit/       87 tests con fakes (sin hardware)
frontend/           Panel React + Vite + TS (login, cámaras, eventos, canales, editor de zona)
deploy/             docker-compose + Dockerfile multi-stage (panel empaquetado)
spike/              Benchmark descartable de Fase 0
docs/               Arquitectura, ADRs, runbook, guías de campo
.github/            CI: lint + tipos + tests (backend) y lint + build (frontend)
```

## Seguridad (resumen)

Autenticación obligatoria en el panel (cookie HttpOnly, argon2, rate limiting de login); evidencia servida solo con sesión; URLs de cámara y tokens de canales **siempre redactados** en las respuestas de la API y en los logs; secretos únicamente por variables de entorno; retención automática de evidencia como práctica de privacidad. Detalle en [`plan-de-desarrollo.md`](plan-de-desarrollo.md) §3 y [`docs/runbook.md`](docs/runbook.md) §7.
