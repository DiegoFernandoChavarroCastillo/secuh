# 0004 — Alcance del escalado (Fase 5): qué se difiere y por qué

- **Estado:** aceptada
- **Fecha:** 2026-07-15

## Contexto

El plan de Fase 5 contemplaba: pool de workers de inferencia con cola,
tracking ByteTrack, dashboard en tiempo real y endurecimiento. El benchmark
(ADR 0003) fijó la capacidad real del hardware actual en **1–2 cámaras**.

## Decisión

**Se implementa ahora:**
- Dashboard en tiempo real por SSE (`/api/stream`): estado de cámaras y
  eventos nuevos sin refrescar el panel.
- Métricas por worker (frames leídos/analizados, fps efectivos, eventos,
  uptime) expuestas en la API.
- Endurecimiento ya presente: reinicio de workers muertos, reconexión de
  streams con backoff, alerta de cámara sin señal, restart policies en compose.

**Se difiere (con la palanca identificada):**
- **Cola de inferencia + pool:** con 1–2 cámaras, el `ThreadSafeDetector`
  (lock sobre un único modelo) ya serializa la inferencia, y el throttle de
  `analysis_fps` en cada worker actúa como backpressure natural (los frames
  intermedios se descartan, nunca se encolan). Una cola explícita solo aporta
  valor con >2–3 cámaras o GPU — es decir, con otro hardware. Implementarla
  ahora sería complejidad sin carga que la justifique.
- **ByteTrack:** el tracking de Ultralytics mantiene estado por modelo, no por
  stream; con el modelo compartido entre cámaras se contaminarían los tracks.
  Requeriría un modelo (o tracker) por cámara — coste de memoria que el
  hardware actual no soporta. El cooldown por cámara cubre el anti-spam.
- **Prueba de resistencia 72 h:** es operativa, no de código; el procedimiento
  queda en `docs/runbook.md` y debe correrse en el hardware de despliegue.

## Consecuencias

- Revisar esta decisión cuando exista una instalación con >2 cámaras o GPU:
  entonces sí, cola de inferencia (y evaluar export a ONNX/OpenVINO).
- Las métricas por worker ya dan la señal para saber cuándo el sistema se
  queda corto (fps efectivos < objetivo de forma sostenida).
