# Arquitectura

> Documento vivo: se actualiza al cierre de cada fase. El diseño original está
> en [`proyecto-deteccion-personas.md`](../proyecto-deteccion-personas.md) y las
> decisiones puntuales en [`adr/`](adr/README.md).

## Estilo: ports & adapters (hexagonal)

El paquete `backend/src/secuh/core/` contiene el dominio puro:

- `models.py` — entidades (`Camera`, `Event`, `Detection`...), inmutables.
- `ports.py` — interfaces que el dominio necesita del mundo exterior:
  `VideoSource`, `MotionDetector`, `PersonDetector`, `Notifier`, `EventStore`,
  `ClipRecorder`, `Clock`.
- `pipeline.py` — orquestación: movimiento → detección → umbral → cooldown → evento.

**Regla:** `core/` no importa OpenCV, Ultralytics, FastAPI ni SQLAlchemy.
Los adaptadores (`detection/`, `video/`, `notifications/`, `storage/`, y más
adelante `db/`, `api/`) implementan los puertos. Los tests unitarios del
pipeline corren con fakes, sin cámara ni modelo (`backend/tests/unit/`).

## Estado por fase

- **Fase 0 (actual):** esqueleto + puertos definidos + lógica de pipeline y
  cooldown testeada + spike de benchmark (`spike/benchmark.py`).
- **Fase 1:** adaptadores reales (MOG2, YOLO, RTSP/MJPEG, ntfy, clips) y
  entry point `python -m secuh`.
