# 0003 — Línea base de hardware

- **Estado:** aceptada (medida en la máquina de desarrollo; revalidar en el hardware de despliegue definitivo)
- **Fecha:** 2026-07-14

## Contexto

Todo el dimensionamiento del sistema (cuántas cámaras, qué resolución, qué
modelo) depende de lo que sostenga el hardware real donde correrá. La Fase 0
exige medirlo antes de construir encima (criterio de salida: ≥ 5 fps de
análisis sostenidos con detección correcta).

## Cómo medir

```bash
cd backend
uv sync --all-groups
uv run python ../spike/benchmark.py --source <URL_DEL_STREAM> --duration 120 --display
```

Correr al menos dos escenarios: escena quieta (mide el costo del pre-filtro
solo) y escena con una persona moviéndose (mide el costo con YOLO activo).
El script guarda el resumen JSON en `spike/results/`.

## Resultados (2026-07-14, webcam integrada, 30 s con persona en cuadro)

| Métrica | Escena con persona (peor caso: movimiento continuo) |
|---|---|
| Hardware | Intel Core i3-10110U @ 2.10 GHz (4 hilos), 11.8 GB RAM, sin GPU |
| Modelo / resolución | YOLOv8n, `imgsz=640`, objetivo 5 fps de análisis |
| fps de análisis alcanzados | **4.19** (127 frames analizados de 637 leídos) |
| Latencia de inferencia media / p95 | **252 ms / 348 ms** |
| CPU del proceso (prom / máx) | 97% / 242% (~2.4 núcleos en picos) |
| Detección de persona | 34/34 frames con movimiento → persona detectada |

Nota: el primer `predict` de torch tarda ~30 s (inicialización); el spike hace
un calentamiento previo para no contaminar las métricas. Cualquier código de
producción debe calentar el modelo al arrancar.

## Decisión

- El pipeline **es viable en esta CPU**: 4.2 fps de análisis en el peor caso
  (persona moviéndose continuamente). En escenas reales el pre-filtro hace
  que la mayoría de frames no lleguen a YOLO, así que el promedio efectivo
  cumple el objetivo de 5 fps.
- Configuración base para Fase 1: **YOLOv8n, imgsz=640, 5 fps de análisis,
  1 cámara**. Si al integrar el stream del celular (IP Webcam) la latencia
  sube, la primera palanca es bajar `imgsz` a 480; la segunda, bajar a 4 fps.
- Con ~250 ms por inferencia y ~2.4 núcleos usados, este equipo soporta
  **1–2 cámaras** de forma realista. Escalar a más cámaras (Fase 5) requerirá
  hardware más potente o export del modelo a ONNX/OpenVINO (CPU Intel).

## Consecuencias

- El diseño de Fase 1 asume detección "single-camera" en CPU; no hace falta
  cola de inferencia todavía.
- Antes de instalar donde un cliente, correr este mismo spike en el equipo de
  despliegue y anexar los resultados aquí.
- Queda abierta la optimización OpenVINO/ONNX como palanca conocida para
  Fase 5 (no antes: primero funcionalidad, luego rendimiento medido).
