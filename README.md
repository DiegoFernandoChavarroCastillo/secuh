# secuh

Sistema de videovigilancia inteligente que procesa video en tiempo real (cámaras IP, RTSP, o teléfono vía IP Webcam), detecta específicamente **personas** (no animales ni mascotas), y envía notificaciones inmediatas.

- **Idea y arquitectura:** [`proyecto-deteccion-personas.md`](proyecto-deteccion-personas.md)
- **Plan de desarrollo por fases:** [`plan-de-desarrollo.md`](plan-de-desarrollo.md)
- **Decisiones de arquitectura:** [`docs/adr/`](docs/adr/README.md)

**Estado actual:** Fase 0 — fundaciones y validación de hardware.

## Estructura

```
backend/     Núcleo Python: dominio (core), adaptadores de visión/video/notificaciones
spike/       Scripts descartables de validación (benchmark de Fase 0)
docs/adr/    Registro de decisiones de arquitectura
.github/     CI (lint + tipos + tests)
```

## Desarrollo

Requiere [uv](https://docs.astral.sh/uv/) (aprovisiona Python 3.12 automáticamente):

```bash
cd backend
uv sync --all-groups          # crea .venv e instala todo
uv run pytest tests/unit      # tests unitarios (sin hardware)
uv run ruff check .           # lint
uv run mypy                   # chequeo de tipos
uv run pre-commit install     # hooks de git (lint + secretos), una sola vez
```

## Benchmark de hardware (Fase 0)

Valida que tu máquina sostiene el pipeline antes de construir encima:

```bash
cd backend
uv run python ../spike/benchmark.py --source http://<ip-del-celular>:8080/video --display
```

Ver instrucciones completas en [`docs/adr/0003-linea-base-de-hardware.md`](docs/adr/0003-linea-base-de-hardware.md).
