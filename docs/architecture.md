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

## Flujo en ejecución (Fase 1)

```
OpenCvVideoSource ──frames──▶ CameraWorker
                               ├─▶ FileClipRecorder.push_frame  (buffer circular pre-evento)
                               └─▶ DetectionPipeline.process_frame  (a analysis_fps)
                                     movimiento (MOG2) → YOLO person → umbral → cooldown
                                     └─ Event ─▶ EventHandler
                                                  1. FileSnapshotStore (JPEG)
                                                  2. Notifier(s)  (ntfy / consola)
                                                  3. FileClipRecorder.record_event (pre+post)
                                                  4. JsonlEventStore (data/events.jsonl)
RetentionJob (hilo de fondo): borra evidencia > N días
```

Decisión de resiliencia: cada paso del handler tolera el fallo de los demás
(sin captura se notifica sin imagen; sin canal disponible el evento igual se
persiste con `notified: false`).

## Estado por fase

- **Fase 0 (hecha):** esqueleto + puertos + pipeline/cooldown testeados +
  benchmark de hardware (`spike/benchmark.py`, ADR 0003).
- **Fase 1 (hecha, pendiente validación con celular real):** adaptadores
  reales (MOG2, YOLO, captura con reconexión, ntfy, clips, retención),
  config YAML validada, logging JSON, entry point `python -m secuh`.
- **Fase 2:** PostgreSQL + API FastAPI + panel React con autenticación.
